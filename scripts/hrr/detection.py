"""
HRR Feature Extraction - Peak/Valley Detection

Functions for detecting peaks, valleys, and recovery intervals.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Dict

import numpy as np
from scipy import signal

from .types import HRSample, RecoveryInterval, HRRConfig
from .metrics import fit_exponential_decay, compute_all_segment_r2, compute_late_slope, assess_quality
from .reanchoring import attempt_plateau_reanchor

logger = logging.getLogger(__name__)


# =============================================================================
# Peak Detection
# =============================================================================

def detect_peaks(samples: List[HRSample], config: HRRConfig) -> List[int]:
    """
    Detect HR peaks using scipy.signal.find_peaks.
    Returns indices of peak samples.
    """
    if len(samples) < config.min_sustained_effort_sec:
        return []

    hr_values = np.array([s.hr_value for s in samples])

    # Smooth the signal slightly to reduce noise
    if len(hr_values) > 5:
        kernel_size = 5
        kernel = np.ones(kernel_size) / kernel_size
        hr_smoothed = np.convolve(hr_values, kernel, mode='same')
    else:
        hr_smoothed = hr_values

    # Find peaks with prominence requirement
    peaks, properties = signal.find_peaks(
        hr_smoothed,
        prominence=config.peak_prominence,
        distance=config.peak_distance_sec  # Permissive - let quality gates filter
    )

    return peaks.tolist()


def validate_peak(samples: List[HRSample], peak_idx: int, resting_hr: int, config: HRRConfig) -> bool:
    """
    Validate that a peak represents genuine elevated effort.
    """
    if peak_idx >= len(samples):
        return False

    peak_hr = samples[peak_idx].hr_value
    elevation = peak_hr - resting_hr

    # Must be sufficiently elevated above resting
    if elevation < config.min_elevation_bpm:
        return False

    # Check for sustained effort before peak
    if peak_idx < config.min_sustained_effort_sec:
        return False

    # Verify HR was elevated for minimum duration before peak
    pre_peak_samples = samples[max(0, peak_idx - config.min_sustained_effort_sec):peak_idx]
    elevated_count = sum(1 for s in pre_peak_samples if s.hr_value > resting_hr + 15)

    if elevated_count < config.min_sustained_effort_sec * 0.7:  # 70% must be elevated
        return False

    return True


# =============================================================================
# Valley-Based Peak Discovery (Issue #020)
# =============================================================================

def detect_valley_peaks(samples: List[HRSample], resting_hr: int, config: HRRConfig) -> List[int]:
    """
    Discover recovery intervals by finding valleys (local minima) in HR,
    then looking back to find the corresponding peak.

    This complements scipy peak detection by catching plateau-to-decline
    patterns that lack prominence but represent real recoveries.

    Returns list of peak indices (to feed into same pipeline as detect_peaks).
    """
    if len(samples) < 120:  # Need enough data for meaningful valleys
        return []

    hr_values = np.array([s.hr_value for s in samples])

    # Smooth to reduce noise
    kernel = np.ones(5) / 5
    hr_smooth = np.convolve(hr_values, kernel, mode='same')

    # Find valleys (invert signal, find peaks)
    valleys, _ = signal.find_peaks(
        -hr_smooth,
        prominence=config.valley_prominence,
        distance=config.valley_distance_sec
    )

    peak_indices = []

    for valley_idx in valleys:
        valley_hr = hr_values[valley_idx]

        # Look back to find the MOST RECENT peak before this valley
        # (Not absolute max - that finds older, irrelevant peaks)
        lookback = min(valley_idx, config.valley_lookback_sec)
        search_start = valley_idx - lookback
        search_window = hr_smooth[search_start:valley_idx]

        if len(search_window) < 30:
            continue

        # Find local peaks in the search window
        local_peaks, _ = signal.find_peaks(
            search_window,
            prominence=config.valley_local_peak_prominence,
            distance=config.valley_local_peak_distance
        )

        if len(local_peaks) == 0:
            # No prominent peaks - fall back to simple max
            local_max_idx = np.argmax(search_window)
            max_idx = search_start + local_max_idx
        else:
            # Use the LAST (most recent) local peak before the valley
            last_peak = local_peaks[-1]
            max_idx = search_start + last_peak

        max_hr = hr_values[max_idx]
        drop = max_hr - valley_hr

        # Validate: must be elevated and have real drop
        if max_hr < resting_hr + config.min_elevation_bpm:
            continue
        if drop < config.valley_min_drop_bpm:
            continue

        peak_indices.append(max_idx)

    return peak_indices


def merge_peak_candidates(
    peak_detected: List[int],
    valley_detected: List[int],
    samples: List[HRSample],
    config: HRRConfig
) -> List[int]:
    """
    Merge peak-detected and valley-detected candidates.

    Rules:
    1. Peak detection takes priority (proven method)
    2. Valley candidates are added only if not near existing peak
    3. Final list is sorted by time
    4. Measurement window constraint enforced in extract_features loop
    """
    # Start with peak-detected (priority)
    all_candidates = set(peak_detected)

    # Add valley-detected if not within 30s of any peak-detected
    for valley_peak in valley_detected:
        is_duplicate = False
        for peak in peak_detected:
            if abs(valley_peak - peak) <= 30:
                is_duplicate = True
                break
        if not is_duplicate:
            all_candidates.add(valley_peak)

    # Sort by time
    return sorted(all_candidates)


# =============================================================================
# Recovery Interval Detection
# =============================================================================

def find_recovery_end(samples: List[HRSample], start_idx: int, config: HRRConfig) -> Optional[int]:
    """
    Find the end of a recovery interval starting from a peak.
    Returns the index where recovery ends (either plateau, rise, or max duration).
    """
    if start_idx >= len(samples) - 1:
        return None

    peak_hr = samples[start_idx].hr_value
    current_min = peak_hr
    consecutive_rises = 0

    for i in range(start_idx + 1, min(start_idx + config.max_interval_duration_sec + 1, len(samples))):
        hr = samples[i].hr_value

        if hr < current_min:
            current_min = hr
            consecutive_rises = 0
        elif hr > current_min + config.decline_tolerance_bpm:
            consecutive_rises += 1
            if consecutive_rises >= 5:  # 5 consecutive seconds of rising
                return i - 5  # Return point before rise started
        else:
            consecutive_rises = 0

    # Reached max duration or end of samples
    end_idx = min(start_idx + config.max_interval_duration_sec, len(samples) - 1)

    # Ensure minimum duration
    if end_idx - start_idx < config.min_decline_duration_sec:
        return None

    return end_idx


def detect_onset_maxhr(samples: List[HRSample], start_idx: int, end_idx: int, config: HRRConfig) -> Tuple[int, int]:
    """
    Detect recovery onset using max HR method.
    Returns (onset_delay_seconds, max_hr_index).
    """
    if end_idx <= start_idx:
        return 0, start_idx

    interval_samples = samples[start_idx:end_idx + 1]
    hr_values = [s.hr_value for s in interval_samples]

    # Find max HR within the interval (may not be at start due to catch-breath)
    # Use LAST occurrence of max to find end of plateau (Issue #015)
    # np.argmax returns first occurrence, but we want end of flat/rising section
    max_hr = max(hr_values)
    max_indices = [i for i, hr in enumerate(hr_values) if hr == max_hr]
    max_hr_idx = max_indices[-1] if max_indices else 0
    onset_delay = max_hr_idx  # seconds from interval start

    # Cap the delay
    if onset_delay > config.onset_max_delay:
        onset_delay = 0
        max_hr_idx = 0

    return onset_delay, start_idx + max_hr_idx


def detect_onset_slope(samples: List[HRSample], start_idx: int, end_idx: int, config: HRRConfig) -> Tuple[int, str]:
    """
    Detect recovery onset using slope method.
    Returns (onset_delay_seconds, confidence).
    """
    if end_idx <= start_idx:
        return 0, 'low'

    interval_samples = samples[start_idx:end_idx + 1]
    hr_values = np.array([s.hr_value for s in interval_samples])

    # Calculate rolling slope (5-second window)
    window = 5
    if len(hr_values) < window + config.onset_min_consecutive:
        return 0, 'low'

    slopes = []
    for i in range(len(hr_values) - window):
        slope = (hr_values[i + window] - hr_values[i]) / window
        slopes.append(slope)

    # Find first point of sustained decline
    consecutive_decline = 0
    onset_idx = 0

    for i, slope in enumerate(slopes):
        if slope <= config.onset_min_slope:
            consecutive_decline += 1
            if consecutive_decline >= config.onset_min_consecutive:
                onset_idx = max(0, i - config.onset_min_consecutive + 1)
                break
        else:
            consecutive_decline = 0

    # Determine confidence
    if consecutive_decline >= config.onset_min_consecutive * 2:
        confidence = 'high'
    elif consecutive_decline >= config.onset_min_consecutive:
        confidence = 'medium'
    else:
        confidence = 'low'

    return onset_idx, confidence


def create_recovery_interval(
    samples: List[HRSample],
    start_idx: int,
    end_idx: int,
    interval_order: int,
    resting_hr: int,
    config: HRRConfig
) -> Optional[RecoveryInterval]:
    """
    Create a RecoveryInterval from detected peak to end.
    """
    if end_idx <= start_idx:
        return None

    interval_samples = samples[start_idx:end_idx + 1]
    duration = end_idx - start_idx

    if duration < config.min_decline_duration_sec:
        return None

    # Detect onset using both methods
    onset_maxhr, max_hr_idx = detect_onset_maxhr(samples, start_idx, end_idx, config)
    onset_slope, slope_confidence = detect_onset_slope(samples, start_idx, end_idx, config)

    # Use max HR onset as primary (more reliable for catch-breath detection)
    effective_start_idx = max_hr_idx
    effective_samples = samples[effective_start_idx:end_idx + 1]

    if len(effective_samples) < config.min_decline_duration_sec:
        effective_start_idx = start_idx
        effective_samples = interval_samples

    hr_values = [s.hr_value for s in effective_samples]
    hr_peak = max(hr_values)
    hr_nadir = min(hr_values)

    # Find nadir time
    nadir_idx = hr_values.index(hr_nadir)
    nadir_time_sec = nadir_idx

    # Calculate HR at specific times (from effective start) - canonical naming hr_Xs
    hr_30s = hr_values[30] if len(hr_values) > 30 else None
    hr_60s = hr_values[60] if len(hr_values) > 60 else None
    hr_90s = hr_values[90] if len(hr_values) > 90 else None
    hr_120s = hr_values[120] if len(hr_values) > 120 else None
    hr_180s = hr_values[180] if len(hr_values) > 180 else None
    hr_240s = hr_values[240] if len(hr_values) > 240 else None
    hr_300s = hr_values[300] if len(hr_values) > 300 else None

    # Calculate HRR values - absolute drops (canonical: hrrX_abs)
    hrr30_abs = hr_peak - hr_30s if hr_30s else None
    hrr60_abs = hr_peak - hr_60s if hr_60s else None
    hrr90_abs = hr_peak - hr_90s if hr_90s else None
    hrr120_abs = hr_peak - hr_120s if hr_120s else None
    hrr180_abs = hr_peak - hr_180s if hr_180s else None
    hrr240_abs = hr_peak - hr_240s if hr_240s else None
    hrr300_abs = hr_peak - hr_300s if hr_300s else None
    total_drop = hr_peak - hr_nadir

    # HR reserve (peak - resting)
    hr_reserve = hr_peak - resting_hr

    # Normalized metrics
    recovery_ratio = (total_drop / hr_reserve) if total_drop and hr_reserve > 0 else None
    peak_pct_max = hr_peak / config.default_max_hr if hr_peak else None

    # Determine onset confidence
    if abs(onset_maxhr - onset_slope) <= 5:
        onset_confidence = 'high'
    elif abs(onset_maxhr - onset_slope) <= 15:
        onset_confidence = 'medium'
    else:
        onset_confidence = 'low'

    # Check for low signal
    is_low_signal = hr_reserve < config.low_signal_threshold_bpm

    # Sample counts
    sample_count = len(effective_samples)
    expected_sample_count = len(effective_samples)  # 1Hz = 1 sample per second expected

    interval = RecoveryInterval(
        start_time=effective_samples[0].timestamp,
        end_time=effective_samples[-1].timestamp,
        duration_seconds=len(effective_samples) - 1,
        interval_order=interval_order,
        hr_peak=hr_peak,
        hr_nadir=hr_nadir,
        hr_30s=hr_30s,
        hr_60s=hr_60s,
        hr_90s=hr_90s,
        hr_120s=hr_120s,
        hr_180s=hr_180s,
        hr_240s=hr_240s,
        hr_300s=hr_300s,
        rhr_baseline=resting_hr,
        hr_reserve=hr_reserve,
        hrr30_abs=hrr30_abs,
        hrr60_abs=hrr60_abs,
        hrr90_abs=hrr90_abs,
        hrr120_abs=hrr120_abs,
        hrr180_abs=hrr180_abs,
        hrr240_abs=hrr240_abs,
        hrr300_abs=hrr300_abs,
        total_drop=total_drop,
        recovery_ratio=recovery_ratio,
        peak_pct_max=peak_pct_max,
        nadir_time_sec=nadir_time_sec,
        onset_delay_sec=onset_maxhr,
        onset_confidence=onset_confidence,
        is_low_signal=is_low_signal,
        sample_count=sample_count,
        expected_sample_count=expected_sample_count,
        peak_label=f"Peak {interval_order}"
    )

    return interval


# =============================================================================
# Feature Extraction Pipeline
# =============================================================================

def extract_features(
    samples: List[HRSample],
    resting_hr: int,
    config: HRRConfig = None,
    peak_adjustments: Dict[int, int] = None
) -> List[RecoveryInterval]:
    """
    Main feature extraction pipeline.
    Detects recovery intervals and computes all features.

    Args:
        samples: List of HR samples
        resting_hr: Resting heart rate for this session
        config: HRR configuration
        peak_adjustments: Dict mapping interval_order -> shift_seconds for manual overrides
    """
    if config is None:
        config = HRRConfig()

    if len(samples) < config.min_decline_duration_sec:
        logger.warning(f"Insufficient samples: {len(samples)}")
        return []

    # Detect peaks (primary method)
    peak_indices = detect_peaks(samples, config)
    logger.info(f"Found {len(peak_indices)} candidate peaks (scipy)")

    # Detect valley-based peaks (Issue #020 - catches plateau-to-decline)
    valley_peaks = detect_valley_peaks(samples, resting_hr, config)
    logger.info(f"Found {len(valley_peaks)} candidate peaks (valley)")

    # Merge candidates (peak detection takes priority)
    all_candidates = merge_peak_candidates(peak_indices, valley_peaks, samples, config)
    logger.info(f"Merged to {len(all_candidates)} unique candidates")

    # Filter valid peaks
    valid_peaks = [
        idx for idx in all_candidates
        if validate_peak(samples, idx, resting_hr, config)
    ]
    logger.info(f"Validated {len(valid_peaks)} peaks")

    intervals = []
    interval_order = 1
    last_interval_end = -1  # Track end of previous interval for measurement window constraint

    for peak_idx in valid_peaks:
        # Apply manual peak adjustment if one exists for this interval_order
        if peak_adjustments and interval_order in peak_adjustments:
            shift = peak_adjustments[interval_order]
            original_peak_idx = peak_idx
            peak_idx = peak_idx + shift
            logger.info(f"Applied manual adjustment: peak {interval_order} shifted by {shift}s (index {original_peak_idx} -> {peak_idx})")

            # Validate new peak is within bounds
            if peak_idx < 0 or peak_idx >= len(samples):
                logger.warning(f"Adjusted peak {interval_order} out of bounds, skipping")
                interval_order += 1
                continue

            # Flag to add later to indicate manual adjustment
            manual_adjustment_applied = True
        else:
            manual_adjustment_applied = False

        # Measurement window constraint: new peak can't start within previous interval
        if peak_idx <= last_interval_end:
            continue

        # Find recovery end
        end_idx = find_recovery_end(samples, peak_idx, config)
        if end_idx is None:
            continue

        # Create interval
        interval = create_recovery_interval(
            samples, peak_idx, end_idx, interval_order, resting_hr, config
        )

        if interval is None:
            continue

        # Get samples for this interval - use onset-adjusted start (Issue #015)
        # The interval already has onset_delay_sec computed by create_recovery_interval()
        # This ensures R² is computed from the true max HR, not scipy's detection point
        onset_offset = interval.onset_delay_sec or 0
        adjusted_start_idx = peak_idx + onset_offset
        interval_samples = samples[adjusted_start_idx:end_idx + 1]

        # Fit exponential decay
        interval = fit_exponential_decay(interval_samples, interval, config)

        # Compute segment R² values
        interval = compute_all_segment_r2(interval_samples, interval)

        # Plateau detection: if r2_0_30 < threshold, try to re-anchor to true peak
        # This catches double-peak patterns where scipy detected the wrong peak
        if interval.r2_0_30 is not None and interval.r2_0_30 < config.gate_r2_0_30_threshold:
            logger.info(f"Interval {interval_order}: r2_0_30={interval.r2_0_30:.3f} < {config.gate_r2_0_30_threshold}, attempting re-anchor")

            success, new_interval, new_samples, new_end, reason = attempt_plateau_reanchor(
                samples, interval, interval_samples, adjusted_start_idx, end_idx,
                interval_order, resting_hr, config
            )

            if success:
                logger.info(f"Interval {interval_order}: {reason}")
                interval = new_interval
                interval_samples = new_samples
                end_idx = new_end
            else:
                logger.info(f"Interval {interval_order}: re-anchor failed - {reason}")

        # Compute late slope
        interval = compute_late_slope(interval_samples, interval)

        # Quality assessment
        interval = assess_quality(interval, config)

        # Add manual adjustment flag if applicable
        if manual_adjustment_applied:
            if 'MANUAL_ADJUSTED' not in interval.quality_flags:
                interval.quality_flags.append('MANUAL_ADJUSTED')

        intervals.append(interval)
        interval_order += 1

        # Update measurement window constraint tracker
        last_interval_end = end_idx

    # Overlap detection (Issue #015)
    # If interval N's window overlaps interval N+1's, reject N as duplicate
    # This catches cases where onset adjustment collapses one peak onto the next
    for i in range(len(intervals) - 1):
        curr = intervals[i]
        next_int = intervals[i + 1]

        # Check if current interval's end overlaps next interval's start
        # Or if current's adjusted start >= next's adjusted start (collapsed past it)
        if curr.start_time >= next_int.start_time:
            # Current interval collapsed onto next one - reject as duplicate
            curr.quality_status = 'rejected'
            curr.auto_reject_reason = 'overlap_duplicate'
            curr.needs_review = False
            curr.review_priority = 0
            if 'OVERLAP' not in curr.quality_flags:
                curr.quality_flags.append('OVERLAP')

    logger.info(f"Extracted {len(intervals)} valid recovery intervals")
    return intervals
