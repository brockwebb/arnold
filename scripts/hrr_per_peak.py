#!/usr/bin/env python3
"""
Per-Peak Drop Detection for Heart Rate Recovery

ChatGPT Health's recommended approach: evaluate each peak→trough pair independently
rather than treating the whole session as one event.

Source: ChatGPT Health analysis, 2026-01-11
"""

from scipy.signal import find_peaks
from scipy.stats import theilslopes, linregress
from scipy.optimize import curve_fit
import numpy as np
import pandas as pd

def exp_model(t, A, tau, hr_inf): 
    return A * np.exp(-t / tau) + hr_inf


def per_peak_drops(df, hr_col='hr_smooth',
                   prom=6, min_distance_s=30,
                   max_trough_search_s=180,
                   confirm_window_s=30, persist_window_s=30,
                   min_abs_drop=5, min_frac_drop=0.15,
                   min_peak_minus_rest=20, abs_fallback=10,
                   fit_r2_min=0.6, fit_tmax=120):
    """
    Detect peaks and evaluate recovery per peak->trough pair.
    
    Args:
        df: DataFrame with datetime index and hr_col column (1Hz resampled)
        hr_col: Name of HR column
        prom: Minimum prominence (bpm) for peaks
        min_distance_s: Minimum seconds between peaks
        max_trough_search_s: Maximum seconds to search for trough after peak
        confirm_window_s: Window for confirming drop magnitude
        persist_window_s: Window for checking drop persistence
        min_abs_drop: Minimum absolute HR drop (bpm)
        min_frac_drop: Minimum fractional drop (0-1)
        min_peak_minus_rest: Minimum signal threshold
        abs_fallback: Absolute fallback for low-signal
        fit_r2_min: Minimum R² for exponential fit
        fit_tmax: Maximum time for exponential fit
    
    Returns:
        List of dicts, one per peak/trough evaluation
    """
    # Index must be datetime index with 1Hz rows
    t_sec = (df.index - df.index[0]).total_seconds().astype(float)
    hr = df[hr_col].to_numpy()

    # Find peaks
    peaks_idx, props = find_peaks(hr, prominence=prom, distance=min_distance_s)
    results = []
    
    for i, pidx in enumerate(peaks_idx):
        peak_time = df.index[pidx]
        HR_peak = float(hr[pidx])
        
        # Search for trough: between this peak and either next peak or +max_trough_search_s
        next_limit_idx = len(hr) - 1
        if i + 1 < len(peaks_idx):
            # Search up to next peak (exclusive)
            next_limit_idx = peaks_idx[i+1]
        else:
            # Limit by time
            max_idx = np.searchsorted(t_sec, t_sec[pidx] + max_trough_search_s)
            next_limit_idx = min(len(hr)-1, max_idx)

        # Trough is the minimum HR between pidx and next_limit_idx
        if next_limit_idx <= pidx:
            continue
        trough_rel_idx = pidx + np.argmin(hr[pidx:next_limit_idx+1])
        trough_time = df.index[trough_rel_idx]
        HR_trough = float(hr[trough_rel_idx])

        # Build local t_rel relative to peak_time
        t_rel = (df.index[pidx:next_limit_idx+1] - peak_time).total_seconds().astype(float)
        hr_segment = hr[pidx:next_limit_idx+1]

        # Compute HRR at specific offsets
        def hr_at_offset(offset_s):
            idx = np.searchsorted(t_rel, offset_s)
            if idx < len(hr_segment):
                return float(hr_segment[idx])
            return None

        hr30 = hr_at_offset(30)
        hr60 = hr_at_offset(60)
        hr_confirm = hr_at_offset(confirm_window_s)
        hr_drop_abs = HR_peak - (hr_confirm if hr_confirm is not None else HR_trough)
        
        # Estimate HR_rest locally as median of 60-180s before peak if present
        pre_start_idx = max(0, pidx - 180)
        HR_rest = float(np.median(hr[pre_start_idx:pidx])) if pidx - pre_start_idx >= 30 else float(np.median(hr[:max(1,pidx)]))
        peak_minus_rest = HR_peak - HR_rest
        hr_drop_frac = hr_drop_abs / peak_minus_rest if peak_minus_rest > 0 else 0.0

        # Trend (Theil-Sen) over first slope window (0..confirm_window_s)
        slope_mask = (t_rel >= 0) & (t_rel <= confirm_window_s)
        trend_pass = False
        try:
            if slope_mask.sum() >= 5:
                theil_slope = theilslopes(hr_segment[slope_mask], t_rel[slope_mask], 0.90)[0]
                lr = linregress(t_rel[slope_mask], hr_segment[slope_mask])
                trend_pass = (theil_slope <= -0.05) and (lr.pvalue < 0.05)
        except Exception:
            trend_pass = False

        # Magnitude decision
        magnitude_pass = ((hr_drop_abs >= min_abs_drop and hr_drop_frac >= min_frac_drop) or 
                         (hr_drop_abs >= abs_fallback))
        if peak_minus_rest < min_peak_minus_rest and hr_drop_abs < abs_fallback:
            magnitude_pass = False  # low-signal

        # Persistence: median in [confirm_window..confirm+persist]
        persist_mask = (t_rel > confirm_window_s) & (t_rel <= confirm_window_s + persist_window_s)
        persist_pass = False
        if persist_mask.sum() > 0:
            median_persist = float(np.median(hr_segment[persist_mask]))
            expected_floor = HR_peak - hr_drop_abs + 1.0
            spikes = np.mean(hr_segment[persist_mask] > expected_floor)
            persist_pass = (median_persist <= expected_floor) and (spikes <= 0.10)

        # Exponential fit on 0..fit_tmax or until trough
        fit_pass = False
        tau = None
        r2 = None
        try:
            t_fit_mask = (t_rel >= 0) & (t_rel <= min(fit_tmax, t_rel[-1]))
            if t_fit_mask.sum() >= 10:
                tfit = t_rel[t_fit_mask]
                yfit = hr_segment[t_fit_mask]
                popt, _ = curve_fit(exp_model, tfit, yfit, 
                                   p0=[HR_peak-HR_trough, 40, HR_trough], 
                                   maxfev=2000,
                                   bounds=([0, 1, 30], [200, 300, 200]))
                yhat = exp_model(tfit, *popt)
                ss_res = np.sum((yfit - yhat)**2)
                ss_tot = np.sum((yfit - yfit.mean())**2)
                r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0.0
                tau = popt[1]
                hr60_pred = exp_model(60.0, *popt) if 60.0 <= tfit[-1] else None
                if r2 >= fit_r2_min and (HR_peak - (hr60_pred if hr60_pred is not None else yhat[-1]) >= min_abs_drop):
                    fit_pass = True
        except Exception:
            fit_pass = False

        overall = trend_pass and magnitude_pass and persist_pass

        results.append({
            "peak_idx": int(pidx), 
            "peak_time": peak_time, 
            "HR_peak": HR_peak,
            "trough_idx": int(trough_rel_idx), 
            "trough_time": trough_time, 
            "HR_trough": HR_trough,
            "hr30": hr30,
            "hr60": hr60,
            "hr_drop_abs": hr_drop_abs, 
            "hr_drop_frac": hr_drop_frac,
            "peak_minus_rest": peak_minus_rest,
            "HR_rest_local": HR_rest,
            "trend_pass": trend_pass, 
            "magnitude_pass": magnitude_pass,
            "persist_pass": persist_pass, 
            "fit_pass": fit_pass,
            "tau": tau,
            "fit_r2": r2,
            "overall": overall
        })
    
    return results


def prepare_hr_dataframe(samples, hr_col='hr'):
    """
    Convert list of HRSample objects to 1Hz resampled DataFrame.
    
    Args:
        samples: List of objects with .timestamp and .hr_value attributes
        hr_col: Name for HR column in output
    
    Returns:
        DataFrame with datetime index and hr_col column
    """
    df = pd.DataFrame([
        {"ts": s.timestamp, hr_col: s.hr_value}
        for s in samples
    ])
    df = df.set_index("ts").sort_index()
    
    # Resample to 1Hz
    df = df.resample("1s").mean().interpolate(limit=5)
    
    return df
