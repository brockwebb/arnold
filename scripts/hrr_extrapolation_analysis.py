#!/usr/bin/env python3
"""
HRR Extrapolation Analysis - Data-driven quality gates

Approach:
1. Fit exponential decay to first 30s of recovery (cleanest region)
2. Extrapolate to predict HR at 35, 40, 45, 50, 55, 60s
3. Compare actual vs predicted at each checkpoint
4. Use residual pattern to detect quality issues

The key insight: let the EARLY data predict what LATE data should be.
Deviations from prediction indicate recovery curve problems.

Author: Arnold Project
Date: 2026-01-14
"""

import os
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy.optimize import curve_fit

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


# =============================================================================
# Exponential decay model
# =============================================================================

def exp_decay(t, hr_peak, hr_asymptote, tau):
    """Standard exponential decay: HR(t) = asymptote + (peak - asymptote) * exp(-t/tau)"""
    return hr_asymptote + (hr_peak - hr_asymptote) * np.exp(-t / tau)


def fit_early_window(t: np.ndarray, hr: np.ndarray, window_end: int = 30) -> Optional[Dict]:
    """
    Fit exponential decay to first `window_end` seconds.
    
    Returns dict with params (hr_peak, hr_asymptote, tau) and fit stats,
    or None if fit fails.
    """
    mask = t <= window_end
    t_fit = t[mask]
    hr_fit = hr[mask]
    
    if len(t_fit) < 15:  # Need enough points
        print(f"Too few points: {len(t_fit)} in first {window_end}s")  # Debug
        return None
    
    try:
        # Initial guesses
        hr_peak_guess = hr_fit[0]
        hr_asymptote_guess = hr_fit[-1]
        tau_guess = 30.0
        
        # Bounds: peak > asymptote, tau > 0
        # Dynamic bounds based on actual data range
        hr_min = min(hr_fit.min(), hr_asymptote_guess) - 20
        hr_max = max(hr_fit.max(), hr_peak_guess) + 20
        
        bounds = (
            [hr_min, hr_min, 5],        # lower: [peak, asymptote, tau]
            [hr_max, hr_max, 300]       # upper: allow longer tau for slow recovery
        )
        
        popt, pcov = curve_fit(
            exp_decay, t_fit, hr_fit,
            p0=[hr_peak_guess, hr_asymptote_guess, tau_guess],
            bounds=bounds,
            maxfev=2000
        )
        
        hr_peak, hr_asymptote, tau = popt
        
        # Compute R² of early fit
        predicted = exp_decay(t_fit, *popt)
        ss_res = np.sum((hr_fit - predicted) ** 2)
        ss_tot = np.sum((hr_fit - np.mean(hr_fit)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        return {
            'hr_peak': hr_peak,
            'hr_asymptote': hr_asymptote,
            'tau': tau,
            'r2_early': r2,
            'n_points': len(t_fit)
        }
    except Exception as e:
        print(f"Fit failed: {e}")  # Debug
        return None


def predict_hr_at(fit_params: Dict, t_sec: float) -> float:
    """Predict HR at time t using fitted parameters."""
    return exp_decay(t_sec, fit_params['hr_peak'], fit_params['hr_asymptote'], fit_params['tau'])


def get_actual_hr_at(t: np.ndarray, hr: np.ndarray, target_sec: float, window: int = 2) -> Optional[float]:
    """Get actual HR at target time (average over small window for noise reduction)."""
    mask = (t >= target_sec - window) & (t <= target_sec + window)
    if mask.sum() == 0:
        return None
    return np.mean(hr[mask])


# =============================================================================
# Database
# =============================================================================

def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def get_intervals(conn, session_ids: List[int] = None, min_duration: int = 60) -> pd.DataFrame:
    """Get intervals with at least min_duration seconds."""
    query = f"""
        SELECT 
            id,
            polar_session_id as session_id,
            start_time,
            duration_seconds,
            hr_peak,
            hrr60_abs,
            tau_fit_r2 as r2_60,
            actionable
        FROM hr_recovery_intervals
        WHERE polar_session_id IS NOT NULL
          AND duration_seconds >= {min_duration}
    """
    if session_ids:
        query += f" AND polar_session_id IN ({','.join(map(str, session_ids))})"
    query += " ORDER BY start_time"
    return pd.read_sql(query, conn)


def load_hr_window(conn, session_id: int, start_time, duration_sec: int) -> Tuple[np.ndarray, np.ndarray]:
    """Load HR samples for interval."""
    query = """
        SELECT 
            EXTRACT(EPOCH FROM (sample_time - %s)) as t_sec,
            hr_value
        FROM hr_samples
        WHERE session_id = %s
          AND sample_time >= %s
          AND sample_time < %s + interval '%s seconds'
        ORDER BY sample_time
    """
    with conn.cursor() as cur:
        cur.execute(query, (start_time, session_id, start_time, start_time, duration_sec + 1))
        rows = cur.fetchall()
    
    if not rows:
        return np.array([]), np.array([])
    
    t = np.array([float(r[0]) for r in rows])
    hr = np.array([float(r[1]) for r in rows])
    return t, hr


# =============================================================================
# Analysis
# =============================================================================

@dataclass
class ExtrapolationResult:
    """Results of extrapolation analysis for one interval."""
    interval_id: int
    session_id: int
    duration_sec: int
    hr_peak: int
    hrr60_recorded: Optional[int]
    r2_60_recorded: Optional[float]
    
    # Early fit (0-30s)
    fit_success: bool = False
    fit_hr_peak: Optional[float] = None
    fit_hr_asymptote: Optional[float] = None
    fit_tau: Optional[float] = None
    r2_early: Optional[float] = None
    
    # Predictions vs actuals at checkpoints
    checkpoints: List[int] = field(default_factory=lambda: [30, 35, 40, 45, 50, 55, 60])
    predicted: Dict[int, float] = field(default_factory=dict)
    actual: Dict[int, float] = field(default_factory=dict)
    residual: Dict[int, float] = field(default_factory=dict)  # actual - predicted
    
    # Summary metrics
    max_residual: Optional[float] = None  # worst single-point deviation
    max_residual_at: Optional[int] = None
    accumulated_error: Optional[float] = None  # sum of absolute residuals
    residual_at_60: Optional[float] = None  # key metric: deviation at measurement point
    late_residual_trend: Optional[float] = None  # slope of residuals 45-60s (positive = getting worse)


def analyze_interval(conn, row: pd.Series) -> ExtrapolationResult:
    """Analyze single interval using extrapolation approach."""
    
    result = ExtrapolationResult(
        interval_id=row['id'],
        session_id=row['session_id'],
        duration_sec=row['duration_seconds'],
        hr_peak=row['hr_peak'],
        hrr60_recorded=row.get('hrr60_abs'),
        r2_60_recorded=row.get('r2_60')
    )
    
    t, hr = load_hr_window(conn, row['session_id'], row['start_time'], row['duration_seconds'])
    
    if len(hr) < 30:
        # print(f"Interval {row['id']}: Only {len(hr)} HR samples loaded")
        return result
    
    # Debug first interval
    # if row['id'] == df.iloc[0]['id']:
    #     print(f"First interval: {len(hr)} HR samples, t range [{t.min():.1f}, {t.max():.1f}]s")
    
    # Fit to first 30s
    fit = fit_early_window(t, hr, window_end=30)
    
    if fit is None:
        return result
    
    result.fit_success = True
    result.fit_hr_peak = round(fit['hr_peak'], 1)
    result.fit_hr_asymptote = round(fit['hr_asymptote'], 1)
    result.fit_tau = round(fit['tau'], 1)
    result.r2_early = round(fit['r2_early'], 3)
    
    # Predict and compare at checkpoints
    residuals = []
    late_residuals = []  # 45-60s
    
    for checkpoint in result.checkpoints:
        if t.max() < checkpoint:
            continue
            
        pred = predict_hr_at(fit, checkpoint)
        act = get_actual_hr_at(t, hr, checkpoint)
        
        if act is not None:
            result.predicted[checkpoint] = round(pred, 1)
            result.actual[checkpoint] = round(act, 1)
            resid = act - pred
            result.residual[checkpoint] = round(resid, 1)
            residuals.append((checkpoint, resid))
            
            if checkpoint >= 45:
                late_residuals.append((checkpoint, resid))
    
    if not residuals:
        return result
    
    # Summary metrics
    abs_residuals = [(c, abs(r)) for c, r in residuals]
    max_resid_item = max(abs_residuals, key=lambda x: x[1])
    result.max_residual = max_resid_item[1]
    result.max_residual_at = max_resid_item[0]
    result.accumulated_error = round(sum(r for _, r in abs_residuals), 1)
    
    if 60 in result.residual:
        result.residual_at_60 = result.residual[60]
    
    # Late residual trend (are residuals getting worse over time?)
    if len(late_residuals) >= 3:
        t_late = np.array([c for c, _ in late_residuals])
        r_late = np.array([r for _, r in late_residuals])
        # Simple linear fit to residuals
        slope = np.polyfit(t_late, r_late, 1)[0]
        result.late_residual_trend = round(slope, 3)  # bpm/sec of residual growth
    
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HRR Extrapolation Analysis')
    parser.add_argument('--session-id', type=int, nargs='+', help='Session IDs')
    parser.add_argument('--output', type=str, help='Output CSV')
    parser.add_argument('--min-duration', type=int, default=60, help='Min interval duration')
    args = parser.parse_args()
    
    print("HRR Extrapolation Analysis")
    print("=" * 60)
    print("Approach: Fit exponential to first 30s, extrapolate to 60s")
    print("Compare predicted vs actual at 35, 40, 45, 50, 55, 60s")
    print()
    
    conn = get_db_connection()
    df = get_intervals(conn, args.session_id, args.min_duration)
    print(f"Found {len(df)} intervals")
    
    results = []
    debug_shown = False
    for i, (_, row) in enumerate(df.iterrows()):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i+1}/{len(df)}...")
        try:
            result = analyze_interval(conn, row)
            results.append(asdict(result))
            
            # Debug: show first few intervals' status
            if not debug_shown and i < 3:
                t, hr = load_hr_window(conn, row['session_id'], row['start_time'], row['duration_seconds'])
                print(f"  Debug interval {row['id']}: {len(hr)} HR samples, fit_success={result.fit_success}")
                if len(hr) > 0:
                    print(f"    t range: [{t.min():.1f}, {t.max():.1f}]s, HR range: [{hr.min():.0f}, {hr.max():.0f}]")
                if i == 2:
                    debug_shown = True
        except Exception as e:
            print(f"  Error on interval {row['id']}: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    
    results_df = pd.DataFrame(results)
    
    # Stats
    fitted = results_df[results_df['fit_success'] == True]
    print(f"\nFit success: {len(fitted)}/{len(results_df)} ({len(fitted)/len(results_df)*100:.1f}%)")
    
    if len(fitted) > 0:
        print(f"\nEarly fit R² (0-30s): mean={fitted['r2_early'].mean():.3f}, min={fitted['r2_early'].min():.3f}")
        
        # Residual stats
        has_60 = fitted[fitted['residual_at_60'].notna()]
        if len(has_60) > 0:
            r60 = has_60['residual_at_60']
            print(f"\nResidual at 60s (actual - predicted):")
            print(f"  Mean: {r60.mean():.1f} bpm")
            print(f"  Std:  {r60.std():.1f} bpm")
            print(f"  Min:  {r60.min():.1f} bpm (prediction overshot)")
            print(f"  Max:  {r60.max():.1f} bpm (prediction undershot)")
            
            for pct in [50, 75, 90, 95, 99]:
                val = r60.quantile(pct/100)
                print(f"  {pct}th percentile: {val:.1f} bpm")
            
            # Positive residual = actual HR HIGHER than predicted = recovery slower than expected
            print(f"\n  Intervals with residual > 0 (slower than predicted): {(r60 > 0).sum()} ({(r60 > 0).mean()*100:.1f}%)")
            print(f"  Intervals with residual > 5 bpm: {(r60 > 5).sum()} ({(r60 > 5).mean()*100:.1f}%)")
            print(f"  Intervals with residual > 10 bpm: {(r60 > 10).sum()} ({(r60 > 10).mean()*100:.1f}%)")
        
        # Accumulated error
        acc = fitted['accumulated_error']
        print(f"\nAccumulated error (sum of |residuals| across checkpoints):")
        print(f"  Mean: {acc.mean():.1f} bpm")
        print(f"  Std:  {acc.std():.1f} bpm")
        for pct in [50, 75, 90, 95]:
            print(f"  {pct}th percentile: {acc.quantile(pct/100):.1f} bpm")
        
        # Late trend
        has_trend = fitted[fitted['late_residual_trend'].notna()]
        if len(has_trend) > 0:
            trend = has_trend['late_residual_trend']
            print(f"\nLate residual trend (45-60s, bpm/sec):")
            print(f"  Mean: {trend.mean():.4f}")
            print(f"  Positive (residuals growing): {(trend > 0).sum()} ({(trend > 0).mean()*100:.1f}%)")
            print(f"  Strongly positive (>0.1): {(trend > 0.1).sum()} ({(trend > 0.1).mean()*100:.1f}%)")
    
    if args.output:
        # Flatten dicts for CSV
        flat_results = []
        for r in results:
            flat = {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
            # Add residuals at each checkpoint
            for cp in [30, 35, 40, 45, 50, 55, 60]:
                flat[f'pred_{cp}'] = r['predicted'].get(cp)
                flat[f'actual_{cp}'] = r['actual'].get(cp)
                flat[f'resid_{cp}'] = r['residual'].get(cp)
            flat_results.append(flat)
        
        pd.DataFrame(flat_results).to_csv(args.output, index=False)
        print(f"\nSaved: {args.output}")


if __name__ == '__main__':
    main()
