"""
HRR Feature Extraction - Metrics Computation

R² calculations, exponential decay fitting, and quality assessment.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
from scipy.optimize import curve_fit

from .types import HRSample, RecoveryInterval, HRRConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Exponential Decay Fitting
# =============================================================================

def exp_decay(t, baseline, amplitude, tau):
    """Exponential decay model: HR(t) = baseline + amplitude * exp(-t/tau)"""
    return baseline + amplitude * np.exp(-t / tau)


def fit_exponential_decay(
    samples: List[HRSample],
    interval: RecoveryInterval,
    config: HRRConfig
) -> RecoveryInterval:
    """
    Fit exponential decay model to recovery interval.
    Updates interval with tau, R², and other fit parameters.
    """
    if interval.duration_seconds < config.tau_min_points:
        return interval

    # Get HR values as numpy array
    hr_values = np.array([s.hr_value for s in samples[:interval.duration_seconds + 1]])
    t = np.arange(len(hr_values))

    if len(hr_values) < config.tau_min_points:
        return interval

    # Initial parameter estimates
    amplitude_init = hr_values[0] - hr_values[-1]
    baseline_init = hr_values[-1]
    tau_init = interval.duration_seconds / 3  # Rough estimate

    try:
        # Fit the model
        popt, pcov = curve_fit(
            exp_decay,
            t,
            hr_values,
            p0=[baseline_init, amplitude_init, tau_init],
            bounds=(
                [0, 0, 1],  # Lower bounds
                [200, 100, config.tau_max_seconds]  # Upper bounds
            ),
            maxfev=5000
        )

        baseline, amplitude, tau = popt

        # Calculate R²
        predicted = exp_decay(t, baseline, amplitude, tau)
        ss_res = np.sum((hr_values - predicted) ** 2)
        ss_tot = np.sum((hr_values - np.mean(hr_values)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Update interval - canonical field names
        interval.tau_seconds = round(tau, 2)
        interval.tau_fit_r2 = round(r2, 4)
        interval.fit_amplitude = round(amplitude, 2)
        interval.fit_asymptote = round(baseline, 2)

    except (RuntimeError, ValueError) as e:
        logger.debug(f"Exponential fit failed: {e}")
        # Leave tau fields as None

    return interval


# =============================================================================
# Segment R² Computation
# =============================================================================

def compute_segment_r2(hr_values: np.ndarray, start_sec: int, end_sec: int) -> Optional[float]:
    """
    Compute R² for exponential fit on a specific time segment.

    Returns:
        R² value (0-1) if fit succeeds
        -1.0 if fit fails (triggers rejection via <0.75 check)
        None if insufficient data (no samples in window)
    """
    if end_sec > len(hr_values) or end_sec - start_sec < 10:
        return None

    segment = hr_values[start_sec:end_sec]
    t = np.arange(len(segment))

    if len(segment) < 10:
        return None

    # Initial estimates
    amplitude_init = segment[0] - segment[-1]
    baseline_init = segment[-1]
    tau_init = len(segment) / 3

    try:
        popt, _ = curve_fit(
            exp_decay,
            t,
            segment,
            p0=[baseline_init, amplitude_init, tau_init],
            bounds=([0, 0, 1], [200, 100, 300]),
            maxfev=2000
        )

        predicted = exp_decay(t, *popt)
        ss_res = np.sum((segment - predicted) ** 2)
        ss_tot = np.sum((segment - np.mean(segment)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        return round(r2, 4)

    except (RuntimeError, ValueError):
        # Fit failed - return impossible R² value to trigger quality gates
        return -1.0


def compute_all_segment_r2(
    samples: List[HRSample],
    interval: RecoveryInterval
) -> RecoveryInterval:
    """
    Compute R² for all standard segments.

    Philosophy: compute all windows where data exists (≥10 samples).
    NULL = "no data", -1.0 = "skipped/failed", value = "computed".

    Early-exit: if a critical segment fails (r2 < 0.75), downstream
    segments are marked -1.0 (skipped) rather than computed.

    Key segments for quality validation:
    - r2_0_30 + r2_30_60 validate HRR60 measurement quality
    - r2_0_60 + r2_30_90 validate HRR90 quality
    - r2_delta = r2_0_30 - r2_30_60 catches disrupted recovery (double-bounce)
    """
    hr_values = np.array([s.hr_value for s in samples[:interval.duration_seconds + 1]])

    # === First 30s - critical for detecting plateau/double-peak ===
    interval.r2_0_30 = compute_segment_r2(hr_values, 0, 30)

    # === 15-45s centered window - diagnostic for edge artifacts ===
    # Hypothesis: robust to boundary artifacts that hurt r2_30_60
    interval.r2_15_45 = compute_segment_r2(hr_values, 15, 45)

    # === 30-60s - CRITICAL for HRR60 quality ===
    interval.r2_30_60 = compute_segment_r2(hr_values, 30, 60)

    # === 0-60s - validates HRR60 ===
    interval.r2_0_60 = compute_segment_r2(hr_values, 0, 60)

    # Early exit check: if 30-60 is garbage, skip longer windows
    if interval.r2_30_60 is not None and interval.r2_30_60 < 0.75:
        # Mid-interval failed - longer windows are meaningless
        interval.r2_30_90 = None
        interval.r2_0_90 = None
        interval.r2_0_120 = None
        interval.r2_0_180 = None
        interval.r2_0_240 = None
        interval.r2_0_300 = None
        interval.r2_detected = compute_segment_r2(hr_values, 0, min(interval.duration_seconds, len(hr_values)))
        return interval

    # === 30-90s - transition zone, validates HRR90/120 ===
    interval.r2_30_90 = compute_segment_r2(hr_values, 30, 90)
    interval.r2_0_90 = compute_segment_r2(hr_values, 0, 90)

    # Early exit check: if 30-90 is garbage, skip even longer windows
    if interval.r2_30_90 is not None and interval.r2_30_90 < 0.75:
        interval.r2_0_120 = None
        interval.r2_0_180 = None
        interval.r2_0_240 = None
        interval.r2_0_300 = None
        interval.r2_detected = compute_segment_r2(hr_values, 0, min(interval.duration_seconds, len(hr_values)))
        return interval

    # === Longer windows ===
    interval.r2_0_120 = compute_segment_r2(hr_values, 0, 120)
    interval.r2_0_180 = compute_segment_r2(hr_values, 0, 180)
    interval.r2_0_240 = compute_segment_r2(hr_values, 0, 240)
    interval.r2_0_300 = compute_segment_r2(hr_values, 0, 300)

    # R² for detected window
    interval.r2_detected = compute_segment_r2(hr_values, 0, min(interval.duration_seconds, len(hr_values)))

    return interval


# =============================================================================
# Late Slope Analysis
# =============================================================================

def compute_late_slope(
    samples: List[HRSample],
    interval: RecoveryInterval,
    start_sec: int = 90,
    end_sec: int = 120
) -> RecoveryInterval:
    """
    Compute slope in the 90-120 second window to detect early activity resumption.
    Positive slope suggests the person started moving again.
    """
    if interval.duration_seconds < end_sec:
        return interval

    hr_values = np.array([s.hr_value for s in samples[start_sec:end_sec + 1]])
    t = np.arange(len(hr_values))

    if len(hr_values) < 10:
        return interval

    # Linear regression for slope
    try:
        coeffs = np.polyfit(t, hr_values, 1)
        slope = coeffs[0]  # bpm per second

        # R² for the linear fit
        predicted = np.polyval(coeffs, t)
        ss_res = np.sum((hr_values - predicted) ** 2)
        ss_tot = np.sum((hr_values - np.mean(hr_values)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        interval.slope_90_120 = round(slope, 4)
        interval.slope_90_120_r2 = round(r2, 4)

    except (np.linalg.LinAlgError, ValueError):
        pass

    return interval


# =============================================================================
# Quality Assessment
# =============================================================================

def assess_quality(interval: RecoveryInterval, config: HRRConfig) -> RecoveryInterval:
    """Assess interval quality and set flags/status.

    Args:
        interval: RecoveryInterval with computed metrics
        config: HRRConfig with threshold settings

    Returns:
        interval: Updated with quality_status, quality_flags, review_priority

    Notes:
        - Hard reject criteria: slope_90_120 > 0.1, best R² < 0.75, r2_30_60 < 0.75, r2_0_30 < 0.5, tau >= 299
        - r2_30_90 is diagnostic only (validates HRR120), not a hard reject
        - tau_clipped rejects intervals where exponential fit hit ceiling (shape invalid)
        - Warning flags demote status to "flagged": LATE_RISE, ONSET_DISAGREEMENT, LOW_SIGNAL
        - Informational flags preserve "pass" status: PLATEAU_RESOLVED, MANUAL_ADJUSTED, ONSET_ADJUSTED
        - Informational flags indicate successful corrections, not quality problems
    """
    # Sample quality
    interval.quality_status = 'pending'
    hard_reject = False
    reject_reason = None

    # === HARD REJECT CRITERIA ===

    # 0. Insufficient duration - can't compute HRR60
    if interval.r2_0_60 is None:
        hard_reject = True
        reject_reason = 'insufficient_duration'

    # 1. Late slope > 0.1 bpm/sec = definite activity resumption
    if interval.slope_90_120 is not None and interval.slope_90_120 > 0.1:
        hard_reject = True
        reject_reason = 'activity_resumed'

    # 2. Best segment R² < 0.75 = statistically validated junk threshold
    # Find best R² across valid windows (exclude r2_0_30 - too short for HRR60)
    r2_values = {
        'r2_0_60': interval.r2_0_60,
        'r2_0_120': interval.r2_0_120,
        'r2_0_180': interval.r2_0_180,
        'r2_0_240': interval.r2_0_240,
        'r2_0_300': interval.r2_0_300,
    }
    valid_r2 = {k: v for k, v in r2_values.items() if v is not None}
    best_r2 = max(valid_r2.values()) if valid_r2 else None

    if best_r2 is None:
        # No valid windows to evaluate - too short or all fits failed
        hard_reject = True
        reject_reason = 'no_valid_r2_windows'
    elif best_r2 < 0.75:
        hard_reject = True
        reject_reason = 'poor_fit_quality'

    # 3. Gate 8: Segment quality check (r2_30_60 validates HRR60 measurement)
    # Threshold is 0.75 - same as other R² gates
    # None means no data (too short, fit failed, or skipped)
    if interval.r2_30_60 is not None and interval.r2_30_60 < 0.75:
        hard_reject = True
        reject_reason = 'r2_30_60_below_0.75'

    # 4. r2_30_90 validates HRR120 measurement (NOT a hard reject)
    # Mid-interval bounce invalidates the 120s window, but HRR60 can still be valid
    # This is a diagnostic marker, not a rejection gate
    # TODO: Add hrr120_valid field to track this separately

    # 5. Gate 10: r2_0_30 < 0.5 = double-peak detection (Issue #015)
    # If first 30s doesn't fit exponential decay, we caught a false start
    # (plateau or rise before the real recovery began)
    if interval.r2_0_30 is not None and interval.r2_0_30 < 0.5:
        hard_reject = True
        reject_reason = 'double_peak'

    # 6. Gate: tau_clipped - exponential fit hit ceiling
    # tau=300 (max bound) means recovery shape doesn't fit expected physiology.
    # Even with acceptable R² values, the shape is wrong. Often indicates:
    # - Zone 1-2 flutter/pause rather than real recovery
    # - Plateau patterns that don't match exponential decay
    # See hrr_quality_gates.md for detailed rationale and monitoring notes.
    if not hard_reject and interval.tau_seconds is not None and interval.tau_seconds >= 299:
        hard_reject = True
        reject_reason = 'tau_clipped'

    # === FLAG CRITERIA (for human review, not auto-reject) ===

    # Minor late rise (0 < slope <= 0.1) - could be noise or minor fidgeting
    if interval.slope_90_120 is not None and 0 < interval.slope_90_120 <= 0.1:
        interval.quality_flags.append('LATE_RISE')



    # Onset disagreement - methods disagree on when recovery started
    if interval.onset_confidence == 'low':
        interval.quality_flags.append('ONSET_DISAGREEMENT')

    # Low signal - peak wasn't very high above resting
    if interval.is_low_signal:
        interval.quality_flags.append('LOW_SIGNAL')

    # ONSET_ADJUSTED flag - onset was adjusted from scipy detection point (Issue #015)
    # Only flag if adjustment > 15 seconds (small adjustments are normal)
    if config.is_flag_enabled('ONSET_ADJUSTED'):
        if interval.onset_delay_sec and interval.onset_delay_sec > 15:
            interval.quality_flags.append('ONSET_ADJUSTED')

    # Store reject reason
    if hard_reject:
        interval.auto_reject_reason = reject_reason

    # === SET REVIEW PRIORITY ===
    if hard_reject:
        interval.review_priority = 0  # Auto-rejected
        interval.needs_review = False
    elif 'HIGH_R2_DELTA' in interval.quality_flags or 'LATE_RISE' in interval.quality_flags:
        interval.review_priority = 1  # High - concerning flags
        interval.needs_review = True
    elif interval.quality_flags:
        interval.review_priority = 2  # Medium - minor issues
        interval.needs_review = True
    else:
        interval.review_priority = 3  # Low - clean
        interval.needs_review = False

    # === SET STATUS ===
    # Informational flags indicate successful corrections, not problems
    INFORMATIONAL_FLAGS = {'PLATEAU_RESOLVED', 'MANUAL_ADJUSTED', 'ONSET_ADJUSTED'}
    warning_flags = [f for f in interval.quality_flags if f not in INFORMATIONAL_FLAGS]

    if hard_reject:
        interval.quality_status = 'rejected'
    elif not warning_flags:
        interval.quality_status = 'pass'
    else:
        interval.quality_status = 'flagged'

    # Sample completeness
    # (This is computed elsewhere but ensure it's set)
    if not hasattr(interval, 'sample_completeness') or interval.sample_completeness is None:
        interval.sample_completeness = 1.0
    interval.is_clean = interval.sample_completeness >= config.min_sample_completeness

    return interval
