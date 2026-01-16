#!/usr/bin/env python3
"""
HRR Imputation and R²-gated HRR Patch

This file contains the key functions to patch into hrr_feature_extraction.py:

1. impute_hr_series() - Create complete second-by-second HR array with gaps filled
2. fit_window_r2() - Compute R² for a fixed window using imputed data
3. compute_gated_hrr() - Only compute HRR drops where R² >= threshold

Architecture:
- R² is always computed (diagnostic - shows WHERE fit breaks down)
- HRR drop is only computed when R² passes (0.75 threshold)
- Both medical standard windows (0-60, 0-120, etc.) AND detected segment metrics
"""

import numpy as np
from scipy.optimize import curve_fit
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass


# =============================================================================
# IMPUTATION
# =============================================================================

def impute_hr_series(samples: List, max_seconds: int = 300) -> Tuple[np.ndarray, int]:
    """
    Create a complete second-by-second HR array with gaps filled.
    
    Args:
        samples: List of HRSample objects with timestamp and hr_value
        max_seconds: Maximum seconds to include (default 300 = 5 minutes)
    
    Returns:
        (hr_array, actual_length) where:
        - hr_array[i] = HR value at second i (0-indexed from first sample)
        - actual_length = how many seconds of real data we have
    
    Imputation: Linear interpolation between gap endpoints.
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


# =============================================================================
# EXPONENTIAL FIT
# =============================================================================

def exponential_decay(t: np.ndarray, a: float, tau: float, c: float) -> np.ndarray:
    """HR(t) = a * exp(-t/tau) + c"""
    return a * np.exp(-t / tau) + c


def fit_window_r2(hr_array: np.ndarray, start_sec: int, end_sec: int) -> Optional[float]:
    """
    Fit exponential to hr_array[start_sec:end_sec+1] and return R².
    
    Args:
        hr_array: Imputed second-by-second HR values
        start_sec: Start of window (inclusive)
        end_sec: End of window (inclusive)
    
    Returns:
        R² value, or None if fit fails or insufficient data
    """
    # Check bounds
    if end_sec >= len(hr_array):
        end_sec = len(hr_array) - 1
    
    if start_sec >= end_sec or end_sec - start_sec < 10:
        return None
    
    # Extract segment
    t = np.arange(0, end_sec - start_sec + 1, dtype=float)
    hr = hr_array[start_sec:end_sec + 1]
    
    if len(hr) < 10:
        return None
    
    # Initial guesses
    a0 = hr[0] - hr[-1]
    tau0 = 30.0
    c0 = hr[-1]
    
    try:
        popt, _ = curve_fit(
            exponential_decay,
            t, hr,
            p0=[a0, tau0, c0],
            bounds=([0, 1, 30], [200, 300, 200]),
            maxfev=500
        )
        
        hr_pred = exponential_decay(t, *popt)
        ss_res = np.sum((hr - hr_pred) ** 2)
        ss_tot = np.sum((hr - np.mean(hr)) ** 2)
        
        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
    except Exception:
        return None


# =============================================================================
# R²-GATED HRR COMPUTATION
# =============================================================================

R2_THRESHOLD = 0.75  # Minimum R² to trust HRR value


@dataclass
class WindowResult:
    """Result for a single time window."""
    window_sec: int      # e.g., 60, 120, 180
    r2: Optional[float]  # Always computed if data exists
    hr_at_t: Optional[int]   # HR value at this timepoint
    hrr_abs: Optional[int]   # Only if R² >= threshold
    hrr_frac: Optional[float]  # Only if R² >= threshold


def compute_window_metrics(
    hr_array: np.ndarray,
    onset_sec: int,
    peak_hr: int,
    rhr: int,
    windows: List[int] = [30, 60, 90, 120, 180, 240, 300]
) -> Dict[int, WindowResult]:
    """
    Compute R² and HRR for each medical standard window.
    
    HRR is ONLY populated when R² passes threshold.
    
    Args:
        hr_array: Imputed HR series (from onset, not original peak)
        onset_sec: Offset into hr_array where true onset begins
        peak_hr: HR at onset (adjusted peak)
        rhr: Resting heart rate
        windows: List of window endpoints in seconds
    
    Returns:
        Dict mapping window_sec -> WindowResult
    """
    results = {}
    hr_reserve = peak_hr - rhr
    
    for window_sec in windows:
        result = WindowResult(
            window_sec=window_sec,
            r2=None,
            hr_at_t=None,
            hrr_abs=None,
            hrr_frac=None
        )
        
        # Check if we have data for this window
        if window_sec < len(hr_array):
            # Get HR at this timepoint
            result.hr_at_t = int(hr_array[window_sec])
            
            # Compute R² for 0 to window_sec
            result.r2 = fit_window_r2(hr_array, 0, window_sec)
            
            # Only compute HRR if R² passes threshold
            if result.r2 is not None and result.r2 >= R2_THRESHOLD:
                result.hrr_abs = peak_hr - result.hr_at_t
                if hr_reserve > 0:
                    result.hrr_frac = result.hrr_abs / hr_reserve
        
        results[window_sec] = result
    
    return results


def compute_detected_segment_metrics(
    hr_array: np.ndarray,
    detected_duration: int,
    peak_hr: int,
    rhr: int
) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    """
    Compute metrics for the detected (organic) interval.
    
    Returns:
        (r2_detected, tau_detected, hrr_at_end, hr_at_end)
    """
    if detected_duration < 30 or detected_duration >= len(hr_array):
        return None, None, None, None
    
    # R² for detected segment
    r2 = fit_window_r2(hr_array, 0, detected_duration)
    
    # Tau for detected segment
    tau = None
    if detected_duration >= 20:
        t = np.arange(0, detected_duration + 1, dtype=float)
        hr = hr_array[0:detected_duration + 1]
        
        try:
            a0 = hr[0] - hr[-1]
            popt, _ = curve_fit(
                exponential_decay,
                t, hr,
                p0=[a0, 60.0, hr[-1]],
                bounds=([0, 1, 30], [200, 300, 200]),
                maxfev=500
            )
            tau = popt[1]
        except Exception:
            pass
    
    # HR at end of detected interval
    hr_at_end = int(hr_array[detected_duration])
    hrr_at_end = peak_hr - hr_at_end
    
    return r2, tau, hrr_at_end, hr_at_end


# =============================================================================
# LATE SLOPE (90-120s)
# =============================================================================

def compute_late_slope(hr_array: np.ndarray, start_sec: int = 90, 
                       end_sec: int = 120) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute linear slope for late recovery segment.
    
    Returns:
        (slope_bpm_per_sec, r2)
    """
    if end_sec >= len(hr_array):
        end_sec = len(hr_array) - 1
    
    if start_sec >= end_sec or end_sec - start_sec < 10:
        return None, None
    
    t = np.arange(start_sec, end_sec + 1, dtype=float)
    hr = hr_array[start_sec:end_sec + 1]
    
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
# MAIN INTEGRATION FUNCTION
# =============================================================================

def compute_all_hrr_features(
    samples,  # List[HRSample] - raw samples from onset to 300s
    detected_duration: int,  # Duration of detected interval
    peak_hr: int,  # HR at onset (adjusted peak)
    rhr: int,  # Resting heart rate
) -> dict:
    """
    Compute ALL HRR features using imputed data.
    
    Returns dict with:
    - Medical standard windows: r2_0_60, hr_60s, hrr60_abs, hrr60_frac, etc.
    - Detected segment: r2_detected, tau_detected, hrr_at_end
    - Diagnostic: r2_0_30, r2_30_60, r2_30_90, slope_90_120
    """
    # Step 1: Impute full HR series
    hr_array, actual_length = impute_hr_series(samples, max_seconds=300)
    
    if actual_length < 30:
        return {}  # Not enough data
    
    result = {
        'imputed_length': actual_length,
    }
    
    # Step 2: Medical standard windows
    windows = compute_window_metrics(hr_array, 0, peak_hr, rhr)
    
    for window_sec, wr in windows.items():
        suffix = str(window_sec)
        result[f'r2_0_{suffix}'] = wr.r2
        result[f'hr_{suffix}s'] = wr.hr_at_t
        result[f'hrr{suffix}_abs'] = wr.hrr_abs  # None if R² failed
        result[f'hrr{suffix}_frac'] = wr.hrr_frac  # None if R² failed
    
    # Step 3: Detected segment metrics
    r2_det, tau_det, hrr_end, hr_end = compute_detected_segment_metrics(
        hr_array, detected_duration, peak_hr, rhr
    )
    result['r2_detected'] = r2_det
    result['tau_detected'] = tau_det
    result['hrr_at_end'] = hrr_end
    result['hr_at_end'] = hr_end
    
    # Step 4: Diagnostic segments
    result['r2_0_30'] = fit_window_r2(hr_array, 0, 30)
    result['r2_30_60'] = fit_window_r2(hr_array, 30, 60)
    result['r2_30_90'] = fit_window_r2(hr_array, 30, 90)
    
    if result['r2_0_30'] is not None and result['r2_30_60'] is not None:
        result['r2_delta'] = result['r2_0_30'] - result['r2_30_60']
    
    # Step 5: Late slope
    slope, slope_r2 = compute_late_slope(hr_array, 90, 120)
    result['slope_90_120'] = slope
    result['slope_90_120_r2'] = slope_r2
    
    # Step 6: Nadir
    result['hr_nadir'] = int(np.min(hr_array[:actual_length+1]))
    result['total_drop'] = peak_hr - result['hr_nadir']
    
    return result


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == '__main__':
    # Demo with synthetic data
    print("HRR Imputation Patch - Key Functions")
    print("=" * 50)
    print()
    print("Functions to integrate into hrr_feature_extraction.py:")
    print("  1. impute_hr_series(samples, max_seconds=300)")
    print("  2. fit_window_r2(hr_array, start_sec, end_sec)")
    print("  3. compute_window_metrics(hr_array, onset_sec, peak_hr, rhr)")
    print("  4. compute_detected_segment_metrics(hr_array, detected_duration, peak_hr, rhr)")
    print("  5. compute_all_hrr_features(samples, detected_duration, peak_hr, rhr)")
    print()
    print("Key principle:")
    print("  - R² is ALWAYS computed (diagnostic)")
    print("  - HRR drop is ONLY populated when R² >= 0.75")
