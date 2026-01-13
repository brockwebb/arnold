#!/usr/bin/env python3
"""
Robust "true drop" detection for heart-rate recovery.

Based on ensemble approach: trend test + magnitude + persistence + fit quality.
All gates must pass for a drop to be considered valid.

Source: ChatGPT Health analysis, adapted for Arnold pipeline.
"""

import math
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from scipy.signal import medfilt
from scipy.stats import theilslopes, linregress
from scipy.optimize import curve_fit

# ------------------- helper functions -------------------

def ensure_datetime_index(df: pd.DataFrame, ts_col: str = "ts") -> pd.DataFrame:
    df = df.copy()
    # Check if already datetime-like (handles timezone-aware datetimes)
    if not pd.api.types.is_datetime64_any_dtype(df[ts_col]):
        try:
            df[ts_col] = pd.to_datetime(df[ts_col], unit='s')
        except Exception:
            df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.set_index(ts_col).sort_index()
    return df

def resample_to_1hz(df: pd.DataFrame) -> pd.DataFrame:
    """Resample to 1Hz, interpolating small gaps."""
    df = df.copy()
    df = df.resample("1s").mean().interpolate(limit=5)
    return df

def smooth_hr(series: pd.Series, med_k: int = 5, ma_k: int = 5) -> pd.Series:
    """Apply median filter then moving average for robust smoothing."""
    mk = med_k if med_k % 2 == 1 else med_k + 1
    arr = series.to_numpy()
    if len(arr) < mk:
        return series
    med = medfilt(arr, kernel_size=mk)
    ma = pd.Series(med).rolling(window=ma_k, min_periods=1, center=True).mean().to_numpy()
    return pd.Series(ma, index=series.index)

def exp_model(t, A, tau, hr_inf):
    """Exponential decay: HR(t) = A * exp(-t/tau) + hr_inf"""
    return A * np.exp(-t / tau) + hr_inf

def fit_exponential(time_s: np.ndarray, hr: np.ndarray, tmax: float = 120.0):
    """Fit HR(t) = A * exp(-t/tau) + hr_inf for t in [0, tmax]."""
    mask = (time_s >= 0) & (time_s <= tmax)
    t = time_s[mask]
    y = hr[mask]
    if len(t) < 10:
        return None
    
    A0 = float(max(y) - min(y))
    tau0 = 40.0
    hr_inf0 = float(min(y))
    
    try:
        p0 = [A0, tau0, hr_inf0]
        popt, pcov = curve_fit(exp_model, t, y, p0=p0, maxfev=2000,
                               bounds=([0, 1, 30], [200, 300, 200]))
        yhat = exp_model(t, *popt)
        ss_res = np.sum((y - yhat) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return {"popt": popt, "pcov": pcov, "r2": float(r2)}
    except Exception:
        return None


# ------------------- main detection function -------------------

DEFAULT_PARAMS = {
    "med_k": 5,
    "ma_k": 5,
    "slope_window_s": 30,
    "confirm_window_s": 30,
    "persist_window_s": 30,
    "delta_slope_thresh": -0.05,  # bpm/s (negative)
    "min_abs_drop": 5,  # bpm
    "min_frac_drop": 0.15,  # fraction of (peak-rest)
    "min_peak_minus_rest": 20,  # short-circuit low-signal below this
    "abs_fallback": 10,  # bigger absolute fallback
    "persist_tolerance_bpm": 2.0,
    "persist_allowed_spikes_prop": 0.10,
    "fit_tmax": 120.0,
    "fit_r2_min": 0.6,
}


def detect_true_drop(
    df_in: pd.DataFrame,
    ts_col: str = "ts",
    hr_col: str = "hr",
    hr_peak: Optional[float] = None,
    hr_rest: Optional[float] = None,
    params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Detect a robust HR drop in the recovery window.
    
    Args:
        df_in: DataFrame with timestamp and HR columns
        ts_col: Name of timestamp column
        hr_col: Name of HR column
        hr_peak: Override peak HR (if known from caller)
        hr_rest: Override rest HR / RHR baseline
        params: Override default parameters
    
    Returns:
        Diagnostics dict with pass/fail for each gate and overall decision
    """
    p = DEFAULT_PARAMS.copy()
    if params:
        p.update(params)

    df = df_in.copy()
    
    # Prepare dataframe with datetime index
    if ts_col in df.columns:
        df = ensure_datetime_index(df, ts_col=ts_col)
    
    # Resample to 1Hz
    df = resample_to_1hz(df)
    
    if hr_col not in df.columns:
        raise ValueError("hr column missing")

    # Smoothing
    df["hr_smooth"] = smooth_hr(
        df[hr_col].ffill().bfill(),
        med_k=p["med_k"], 
        ma_k=p["ma_k"]
    )

    hr_series = df["hr_smooth"]
    
    # t0 = start of recovery (first sample)
    t0 = df.index[0]
    
    # Create relative time column (seconds from start)
    df["t_rel_s"] = (df.index - t0).total_seconds()
    
    # HR_peak: use provided or max in first 15s
    if hr_peak is not None:
        HR_peak = float(hr_peak)
    else:
        peak_mask = df["t_rel_s"] <= 15
        HR_peak = float(df.loc[peak_mask, "hr_smooth"].max()) if peak_mask.sum() > 0 else float(hr_series.max())
    
    # HR_rest: use provided or estimate from later in window
    if hr_rest is not None:
        HR_rest = float(hr_rest)
    else:
        # Use minimum as proxy for rest
        HR_rest = float(hr_series.min())
    
    peak_minus_rest = HR_peak - HR_rest
    low_signal = peak_minus_rest < p["min_peak_minus_rest"]

    # =========================================================================
    # Gate 1: Trend test (Theil-Sen slope + linear regression p-value)
    # =========================================================================
    slope_mask = (df["t_rel_s"] >= 0) & (df["t_rel_s"] <= p["slope_window_s"])
    tvals = df.loc[slope_mask, "t_rel_s"].to_numpy()
    hrvals = df.loc[slope_mask, "hr_smooth"].to_numpy()
    
    trend_pass = False
    slope = None
    lin_p = None
    theil = None
    
    if len(tvals) >= 5:
        try:
            theil_result = theilslopes(hrvals, tvals, 0.90)
            theil_slope = float(theil_result[0])
            theil = {
                "slope": theil_slope, 
                "ci_low": float(theil_result[1]), 
                "ci_high": float(theil_result[2])
            }
            lr = linregress(tvals, hrvals)
            slope = lr.slope
            lin_p = lr.pvalue
            
            # Require negative slope AND statistical significance
            if (theil_slope <= p["delta_slope_thresh"]) and (lin_p < 0.05):
                trend_pass = True
        except Exception:
            pass

    # =========================================================================
    # Gate 2: Magnitude check (absolute and fractional drop)
    # =========================================================================
    confirm_mask = (df["t_rel_s"] > 0) & (df["t_rel_s"] <= p["confirm_window_s"])
    if confirm_mask.sum() >= 1:
        hr_confirm = float(df.loc[confirm_mask, "hr_smooth"].median())
    else:
        hr_confirm = float(hr_series.iloc[:p["confirm_window_s"]].median())

    hr_drop_abs = HR_peak - hr_confirm
    hr_drop_frac = hr_drop_abs / peak_minus_rest if peak_minus_rest > 0 else 0.0

    magnitude_pass = False
    if (hr_drop_abs >= p["min_abs_drop"] and hr_drop_frac >= p["min_frac_drop"]) or \
       (hr_drop_abs >= p["abs_fallback"]):
        magnitude_pass = True
    
    # Raise bar for low-signal intervals
    if low_signal and hr_drop_abs < p["abs_fallback"]:
        magnitude_pass = False

    # =========================================================================
    # Gate 3: Persistence check (drop must be sustained)
    # =========================================================================
    persist_start = p["confirm_window_s"]
    persist_end = p["confirm_window_s"] + p["persist_window_s"]
    persist_mask = (df["t_rel_s"] > persist_start) & (df["t_rel_s"] <= persist_end)
    
    persist_pass = False
    persist_stats = {}
    
    if persist_mask.sum() >= 1:
        hr_persist = df.loc[persist_mask, "hr_smooth"]
        median_persist = float(hr_persist.median())
        
        # Expected floor: HR should stay at or below this
        expected_floor = HR_peak - hr_drop_abs + p["persist_tolerance_bpm"]
        spikes_prop = float((hr_persist > expected_floor).sum()) / max(1, len(hr_persist))
        
        if median_persist <= expected_floor and spikes_prop <= p["persist_allowed_spikes_prop"]:
            persist_pass = True
        
        persist_stats = {
            "median_persist": median_persist, 
            "expected_floor": expected_floor, 
            "spikes_prop": spikes_prop, 
            "n": len(hr_persist)
        }
    else:
        # Not enough data for persistence check - interval too short
        persist_stats = {"error": "insufficient_data", "n": 0}

    # =========================================================================
    # Gate 4: Exponential fit quality (optional but informative)
    # =========================================================================
    fit_info = fit_exponential(
        df["t_rel_s"].to_numpy(), 
        df["hr_smooth"].to_numpy(), 
        tmax=p["fit_tmax"]
    )
    
    fit_pass = False
    tau = None
    fit_r2 = None
    
    if fit_info is not None:
        fit_r2 = fit_info.get("r2", 0.0)
        if fit_r2 >= p["fit_r2_min"]:
            A, tau, hr_inf = fit_info["popt"]
            hr60_pred = exp_model(60.0, A, tau, hr_inf)
            if HR_peak - hr60_pred >= p["min_abs_drop"]:
                fit_pass = True
            tau = float(fit_info["popt"][1])

    # =========================================================================
    # Overall decision: require trend + magnitude + persistence
    # Fit is optional (provides tau but not required for validity)
    # =========================================================================
    overall = trend_pass and magnitude_pass and persist_pass

    diagnostics = {
        "HR_peak": HR_peak,
        "HR_rest": HR_rest,
        "peak_minus_rest": peak_minus_rest,
        "low_signal": low_signal,
        "trend": {
            "pass": trend_pass, 
            "theil": theil, 
            "linreg_slope": slope, 
            "linreg_p": lin_p
        },
        "magnitude": {
            "pass": magnitude_pass, 
            "hr_drop_abs": hr_drop_abs, 
            "hr_drop_frac": hr_drop_frac
        },
        "persistence": {
            "pass": persist_pass, 
            **persist_stats
        },
        "fit": {
            "pass": fit_pass, 
            "tau": tau, 
            "r2": fit_r2
        },
        "overall": overall,
    }
    
    return diagnostics


def validate_recovery_interval(
    samples: list,
    hr_peak: int,
    rhr: int,
    params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Convenience wrapper for validating a RecoveryInterval's samples.
    
    Args:
        samples: List of HRSample objects with timestamp and hr_value
        hr_peak: Peak HR at start of interval
        rhr: Resting heart rate baseline
        params: Override default parameters
    
    Returns:
        Diagnostics dict from detect_true_drop
    """
    if not samples or len(samples) < 30:
        return {
            "overall": False,
            "error": "insufficient_samples",
            "n_samples": len(samples) if samples else 0
        }
    
    # Convert samples to DataFrame
    df = pd.DataFrame([
        {"ts": s.timestamp, "hr": s.hr_value}
        for s in samples
    ])
    
    return detect_true_drop(
        df,
        ts_col="ts",
        hr_col="hr",
        hr_peak=hr_peak,
        hr_rest=rhr,
        params=params
    )
