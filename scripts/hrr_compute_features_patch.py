#!/usr/bin/env python3
"""
HRR Feature Extraction - Patched compute_features()

This is the corrected compute_features function with:
1. Upfront imputation of HR series
2. R²-gated HRR drops (only populated when R² >= 0.75)
3. Both medical standard windows AND detected segment metrics

Copy this function to replace the existing compute_features() in hrr_feature_extraction.py
"""

import numpy as np
from scipy.optimize import curve_fit
from typing import Optional, List, Tuple, Dict
from datetime import datetime

R2_THRESHOLD = 0.75  # Minimum R² to trust HRR value


def impute_hr_series(samples, max_seconds: int = 300) -> Tuple[np.ndarray, int]:
    """
    Create a complete second-by-second HR array with gaps filled via linear interpolation.
    
    Args:
        samples: List of HRSample objects with timestamp and hr_value
        max_seconds: Maximum seconds to include (default 300 = 5 minutes)
    
    Returns:
        (hr_array, actual_length) where:
        - hr_array[i] = HR value at second i (0-indexed from first sample)
        - actual_length = how many seconds of real data we have
    """
    if not samples:
        return np.array([]), 0
    
    t0 = samples[0].timestamp
    
    # Build sparse dict of known values
    hr_at_sec: Dict[int, int] = {}
    max_sec_seen = 0
    
    for s in samples:
        sec = int((s.timestamp - t0).total_seconds())
        if sec <= max_seconds:
            hr_at_sec[sec] = s.hr_value
            max_sec_seen = max(max_sec_seen, sec)
    
    if not hr_at_sec:
        return np.array([]), 0
    
    # Create output array
    length = min(max_sec_seen + 1, max_seconds + 1)
    hr_array = np.zeros(length, dtype=float)
    
    # Fill known values
    for sec, hr in hr_at_sec.items():
        if sec < length:
            hr_array[sec] = hr
    
    # Impute gaps via linear interpolation
    known_secs = sorted(hr_at_sec.keys())
    
    for i in range(len(known_secs) - 1):
        start_sec = known_secs[i]
        end_sec = known_secs[i + 1]
        
        if end_sec - start_sec > 1:  # There's a gap
            start_hr = hr_at_sec[start_sec]
            end_hr = hr_at_sec[end_sec]
            
            # Linear interpolation
            for sec in range(start_sec + 1, end_sec):
                if sec < length:
                    frac = (sec - start_sec) / (end_sec - start_sec)
                    hr_array[sec] = start_hr + frac * (end_hr - start_hr)
    
    return hr_array, max_sec_seen


def fit_window_r2_from_array(hr_array: np.ndarray, start_sec: int, end_sec: int) -> Optional[float]:
    """
    Fit exponential to hr_array[start_sec:end_sec+1] and return R².
    
    Uses min(end_sec, len(hr_array)-1) as actual end.
    Returns None if insufficient data or fit fails.
    """
    # Adjust end to available data
    actual_end = min(end_sec, len(hr_array) - 1)
    
    if start_sec >= actual_end or actual_end - start_sec < 10:
        return None
    
    # Extract segment
    t = np.arange(0, actual_end - start_sec + 1, dtype=float)
    hr = hr_array[start_sec:actual_end + 1].copy()
    
    if len(hr) < 10:
        return None
    
    # Initial guesses
    a0 = hr[0] - hr[-1]
    tau0 = 30.0
    c0 = hr[-1]
    
    def exp_decay(t, a, tau, c):
        return a * np.exp(-t / tau) + c
    
    try:
        popt, _ = curve_fit(
            exp_decay,
            t, hr,
            p0=[a0, tau0, c0],
            bounds=([0, 1, 30], [200, 300, 200]),
            maxfev=500
        )
        
        hr_pred = exp_decay(t, *popt)
        ss_res = np.sum((hr - hr_pred) ** 2)
        ss_tot = np.sum((hr - np.mean(hr)) ** 2)
        
        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
    except Exception:
        return None


def compute_late_slope_from_array(hr_array: np.ndarray, start_sec: int = 90, 
                                   end_sec: int = 120) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute linear slope for late recovery segment from imputed array.
    Returns (slope_bpm_per_sec, r2).
    """
    actual_end = min(end_sec, len(hr_array) - 1)
    
    if start_sec >= actual_end or actual_end - start_sec < 10:
        return None, None
    
    t = np.arange(start_sec, actual_end + 1, dtype=float)
    hr = hr_array[start_sec:actual_end + 1]
    
    try:
        coeffs = np.polyfit(t, hr, 1)
        slope = coeffs[0]
        
        hr_pred = np.polyval(coeffs, t)
        ss_res = np.sum((hr - hr_pred) ** 2)
        ss_tot = np.sum((hr - np.mean(hr)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return slope, r2
    except Exception:
        return None, None


# =============================================================================
# REPLACEMENT compute_features() FUNCTION
# =============================================================================

def compute_features(interval, config, 
                     estimated_max_hr: int = 180,
                     session_id: Optional[int] = None):
    """
    Compute all features for a recovery interval.
    
    KEY CHANGES:
    1. Impute HR series ONCE upfront (linear interpolation)
    2. Compute R² for ALL medical standard windows (always, for diagnostics)
    3. Only populate HRR drops when R² >= 0.75 (gated)
    """
    from hrr_feature_extraction import detect_decline_onset, fit_exponential_decay, logger
    
    # Generate peak label (e.g., "S71:p03")
    if session_id is not None:
        interval.peak_label = f"S{session_id}:p{interval.interval_order:02d}"
    
    samples = interval.samples
    if not samples:
        return interval
    
    # Detect delayed onset (catch-breath phase)
    onset_delay, onset_hr, onset_conf = detect_decline_onset(samples, config)
    interval.onset_delay_sec = onset_delay if onset_delay > 0 else None
    interval.adjusted_peak_hr = onset_hr if onset_delay > 0 else None
    interval.onset_confidence = onset_conf if onset_delay > 0 else None
    
    # Use adjusted peak for HRR calculations if onset was delayed
    effective_peak = onset_hr if onset_delay > 0 else interval.hr_peak
    
    # =========================================================================
    # STEP 1: IMPUTE FULL HR SERIES (from r2_samples, which extends to 300s)
    # =========================================================================
    r2_samples = interval.r2_samples if interval.r2_samples else samples
    
    # Adjust for onset: slice from onset point
    if onset_delay > 0 and onset_delay < len(r2_samples):
        onset_samples = r2_samples[onset_delay:]
    else:
        onset_samples = r2_samples
    
    # Create imputed series
    hr_array, actual_length = impute_hr_series(onset_samples, max_seconds=300)
    
    if actual_length < 30:
        logger.debug(f"Interval #{interval.interval_order}: insufficient data ({actual_length}s)")
        return interval
    
    # =========================================================================
    # STEP 2: COMPUTE R² FOR ALL WINDOWS (always, for diagnostics)
    # =========================================================================
    
    # Diagnostic segments
    interval.r2_0_30 = fit_window_r2_from_array(hr_array, 0, 30)
    interval.r2_30_60 = fit_window_r2_from_array(hr_array, 30, 60)
    interval.r2_30_90 = fit_window_r2_from_array(hr_array, 30, 90)
    
    if interval.r2_0_30 is not None and interval.r2_30_60 is not None:
        interval.r2_delta = interval.r2_0_30 - interval.r2_30_60
    
    # Medical standard windows
    interval.r2_0_60 = fit_window_r2_from_array(hr_array, 0, 60)
    interval.r2_0_120 = fit_window_r2_from_array(hr_array, 0, 120)
    interval.r2_0_180 = fit_window_r2_from_array(hr_array, 0, 180)
    interval.r2_0_240 = fit_window_r2_from_array(hr_array, 0, 240)
    interval.r2_0_300 = fit_window_r2_from_array(hr_array, 0, 300)
    
    # Late slope
    slope, slope_r2 = compute_late_slope_from_array(hr_array, 90, 120)
    interval.slope_90_120 = slope
    interval.slope_90_120_r2 = slope_r2
    
    # =========================================================================
    # STEP 3: HR AT TIMEPOINTS (always from imputed array)
    # =========================================================================
    
    def get_hr_at(sec):
        if sec < len(hr_array):
            return int(hr_array[sec])
        return None
    
    interval.hr_30s = get_hr_at(30)
    interval.hr_60s = get_hr_at(60)
    interval.hr_90s = get_hr_at(90)
    interval.hr_120s = get_hr_at(120)
    interval.hr_180s = get_hr_at(180)
    interval.hr_240s = get_hr_at(240)
    interval.hr_300s = get_hr_at(300)
    interval.hr_nadir = int(np.min(hr_array[:actual_length+1])) if actual_length > 0 else None
    
    # =========================================================================
    # STEP 4: HRR DROPS - ONLY WHEN R² PASSES THRESHOLD
    # =========================================================================
    
    # HRR30 - gated by r2_0_30 (use r2_0_30 since we don't have r2_0_30 specifically)
    # Actually for 30s, use r2_0_30
    if interval.hr_30s is not None and interval.r2_0_30 is not None and interval.r2_0_30 >= R2_THRESHOLD:
        interval.hrr30_abs = effective_peak - interval.hr_30s
    else:
        interval.hrr30_abs = None
    
    # HRR60 - gated by r2_0_60
    if interval.hr_60s is not None and interval.r2_0_60 is not None and interval.r2_0_60 >= R2_THRESHOLD:
        interval.hrr60_abs = effective_peak - interval.hr_60s
    else:
        interval.hrr60_abs = None
    
    # HRR90 - gated by r2_0_90 (we don't have this, use 0_60 as proxy? or skip)
    # For now, gate by r2_0_60 since it's the nearest lower bound
    if interval.hr_90s is not None and interval.r2_0_60 is not None and interval.r2_0_60 >= R2_THRESHOLD:
        interval.hrr90_abs = effective_peak - interval.hr_90s
    else:
        interval.hrr90_abs = None
    
    # HRR120 - gated by r2_0_120
    if interval.hr_120s is not None and interval.r2_0_120 is not None and interval.r2_0_120 >= R2_THRESHOLD:
        interval.hrr120_abs = effective_peak - interval.hr_120s
    else:
        interval.hrr120_abs = None
    
    # HRR180 - gated by r2_0_180
    if interval.hr_180s is not None and interval.r2_0_180 is not None and interval.r2_0_180 >= R2_THRESHOLD:
        interval.hrr180_abs = effective_peak - interval.hr_180s
    else:
        interval.hrr180_abs = None
    
    # HRR240 - gated by r2_0_240
    if interval.hr_240s is not None and interval.r2_0_240 is not None and interval.r2_0_240 >= R2_THRESHOLD:
        interval.hrr240_abs = effective_peak - interval.hr_240s
    else:
        interval.hrr240_abs = None
    
    # HRR300 - gated by r2_0_300
    if interval.hr_300s is not None and interval.r2_0_300 is not None and interval.r2_0_300 >= R2_THRESHOLD:
        interval.hrr300_abs = effective_peak - interval.hr_300s
    else:
        interval.hrr300_abs = None
    
    # Total drop (from peak to nadir) - always compute
    if interval.hr_nadir is not None:
        interval.total_drop = effective_peak - interval.hr_nadir
    
    # =========================================================================
    # STEP 5: NORMALIZED METRICS (fractional) - also gated
    # =========================================================================
    
    if interval.rhr_baseline:
        interval.hr_reserve = effective_peak - interval.rhr_baseline
        
        if interval.hr_reserve > 0:
            # Fractions only if absolute was computed (R² passed)
            if interval.hrr30_abs is not None:
                interval.hrr30_frac = interval.hrr30_abs / interval.hr_reserve
            if interval.hrr60_abs is not None:
                interval.hrr60_frac = interval.hrr60_abs / interval.hr_reserve
            if interval.hrr90_abs is not None:
                interval.hrr90_frac = interval.hrr90_abs / interval.hr_reserve
            if interval.hrr120_abs is not None:
                interval.hrr120_frac = interval.hrr120_abs / interval.hr_reserve
            
            # Recovery ratio (total_drop / reserve) - not gated
            if interval.total_drop is not None:
                interval.recovery_ratio = interval.total_drop / interval.hr_reserve
        
        interval.is_low_signal = interval.hr_reserve < config.low_signal_threshold_bpm
    
    # Peak as % of max
    interval.peak_pct_max = effective_peak / estimated_max_hr
    
    # =========================================================================
    # STEP 6: DETECTED SEGMENT TAU (from original interval samples)
    # =========================================================================
    
    if onset_delay > 0 and onset_delay < len(samples):
        onset_interval_samples = samples[onset_delay:]
    else:
        onset_interval_samples = samples
    
    fit_result = fit_exponential_decay(onset_interval_samples, config)
    interval.tau_seconds = fit_result.tau
    interval.tau_fit_r2 = fit_result.r2
    interval.fit_amplitude = fit_result.amplitude
    interval.fit_asymptote = fit_result.asymptote
    
    # =========================================================================
    # STEP 7: LINEAR SLOPES (from original samples, not imputed)
    # =========================================================================
    
    t0 = samples[0].timestamp
    hr_values = np.array([s.hr_value for s in samples])
    times = np.array([(s.timestamp - t0).total_seconds() for s in samples])
    
    # Slope for first 30s
    mask_30 = times <= 30
    if np.sum(mask_30) >= 5:
        slope, _ = np.polyfit(times[mask_30], hr_values[mask_30], 1)
        interval.decline_slope_30s = slope
    
    # Slope for first 60s
    mask_60 = times <= 60
    if np.sum(mask_60) >= 10:
        slope, _ = np.polyfit(times[mask_60], hr_values[mask_60], 1)
        interval.decline_slope_60s = slope
    
    # Time to 50% recovery
    if interval.hr_reserve and interval.hr_reserve > 0:
        target_hr = interval.hr_peak - (interval.hr_reserve * 0.5)
        for i, s in enumerate(samples):
            if s.hr_value <= target_hr:
                interval.time_to_50pct_sec = int((s.timestamp - t0).total_seconds())
                break
    
    # Area under curve (first 60s)
    if np.sum(mask_60) >= 10:
        interval.auc_60s = np.trapezoid(hr_values[mask_60], times[mask_60])
    
    # Sample quality
    interval.sample_completeness = len(samples) / interval.duration_seconds if interval.duration_seconds > 0 else 0
    interval.is_clean = interval.sample_completeness >= config.min_sample_completeness
    
    # =========================================================================
    # STEP 8: QUALITY FLAGS
    # =========================================================================
    
    interval.quality_flags = []
    interval.quality_status = 'pending'
    
    if interval.r2_delta is not None and interval.r2_delta > 0.3:
        interval.quality_flags.append('HIGH_R2_DELTA')
    
    if interval.slope_90_120 is not None and interval.slope_90_120 > 0:
        interval.quality_flags.append('LATE_RISE')
    
    if interval.tau_fit_r2 is not None and interval.tau_fit_r2 < 0.7:
        interval.quality_flags.append('LOW_R2')
    
    if interval.onset_confidence == 'low':
        interval.quality_flags.append('ONSET_DISAGREEMENT')
    
    if interval.is_low_signal:
        interval.quality_flags.append('LOW_SIGNAL')
    
    # Quality score
    score = 1.0
    score -= len(interval.quality_flags) * 0.1
    if interval.tau_fit_r2:
        score = score * 0.5 + interval.tau_fit_r2 * 0.5
    interval.quality_score = max(0, min(1, score))
    
    # Review priority
    if interval.quality_flags:
        interval.review_priority = 1 if len(interval.quality_flags) >= 2 else 2
    else:
        interval.review_priority = 3
    
    # Log debug info
    logger.debug(f"Interval #{interval.interval_order}: imputed_length={actual_length}s, "
                f"r2_0_60={interval.r2_0_60}, r2_0_120={interval.r2_0_120}, "
                f"hrr60={interval.hrr60_abs}, hrr120={interval.hrr120_abs}")
    
    return interval
