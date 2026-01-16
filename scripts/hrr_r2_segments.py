#!/usr/bin/env python3
"""
HRR R² Segment Analysis

Test Brock's hypothesis: compare R² on 0-30s vs 30-60s vs 0-60s.
If second half R² is significantly worse, something happened mid-recovery.

Author: Arnold Project
Date: 2026-01-14
"""

import os
from pathlib import Path
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy.optimize import curve_fit

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def exp_decay(t, hr_peak, hr_asymptote, tau):
    """Standard exponential decay."""
    return hr_asymptote + (hr_peak - hr_asymptote) * np.exp(-t / tau)


def fit_segment(t: np.ndarray, hr: np.ndarray, 
                t_start: float, t_end: float) -> Optional[Dict]:
    """
    Fit exponential decay to a time segment.
    Returns dict with tau, r2, n_points or None if fit fails.
    """
    mask = (t >= t_start) & (t <= t_end)
    t_seg = t[mask]
    hr_seg = hr[mask]
    
    if len(t_seg) < 10:
        return None
    
    # Shift time to start at 0 for the segment
    t_shifted = t_seg - t_seg.min()
    
    try:
        hr_peak_guess = hr_seg[0]
        hr_asymptote_guess = hr_seg[-1]
        tau_guess = 30.0
        
        # Dynamic bounds
        hr_min = min(hr_seg.min(), hr_asymptote_guess) - 20
        hr_max = max(hr_seg.max(), hr_peak_guess) + 20
        
        bounds = (
            [hr_min, hr_min, 1],
            [hr_max, hr_max, 300]
        )
        
        popt, _ = curve_fit(
            exp_decay, t_shifted, hr_seg,
            p0=[hr_peak_guess, hr_asymptote_guess, tau_guess],
            bounds=bounds,
            maxfev=2000
        )
        
        # Compute R²
        predicted = exp_decay(t_shifted, *popt)
        ss_res = np.sum((hr_seg - predicted) ** 2)
        ss_tot = np.sum((hr_seg - np.mean(hr_seg)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        return {
            'tau': popt[2],
            'r2': r2,
            'n_points': len(t_seg),
            'hr_start': hr_seg[0],
            'hr_end': hr_seg[-1],
            'hr_drop': hr_seg[0] - hr_seg[-1]
        }
    except Exception:
        return None


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def get_intervals(conn, min_duration: int = 65) -> pd.DataFrame:
    """Get intervals with at least 65s (need full 60s + buffer)."""
    query = f"""
        SELECT 
            id,
            COALESCE(polar_session_id, endurance_session_id) as session_id,
            polar_session_id IS NOT NULL as is_polar,
            start_time,
            duration_seconds,
            hr_peak,
            hrr60_abs,
            tau_fit_r2,
            tau_seconds
        FROM hr_recovery_intervals
        WHERE duration_seconds >= {min_duration}
        ORDER BY start_time
    """
    return pd.read_sql(query, conn)


def load_hr_samples(conn, session_id: int, is_polar: bool, 
                    start_time, duration_sec: int) -> Tuple[np.ndarray, np.ndarray]:
    """Load HR samples for interval."""
    if is_polar:
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
    else:
        query = """
            SELECT 
                EXTRACT(EPOCH FROM (sample_time - %s)) as t_sec,
                hr_value
            FROM hr_samples
            WHERE endurance_session_id = %s
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


@dataclass
class SegmentResult:
    interval_id: int
    hr_peak: int
    hrr60_abs: Optional[int]
    tau_recorded: Optional[float]
    r2_recorded: Optional[float]
    
    # Full interval 0-60s
    r2_full: Optional[float] = None
    tau_full: Optional[float] = None
    
    # First half 0-30s
    r2_first: Optional[float] = None
    tau_first: Optional[float] = None
    
    # Second half 30-60s
    r2_second: Optional[float] = None
    tau_second: Optional[float] = None
    
    # Derived metrics
    r2_delta: Optional[float] = None  # r2_first - r2_second
    r2_ratio: Optional[float] = None  # r2_second / r2_first
    
    # Signal strength
    hr_drop_first: Optional[float] = None
    hr_drop_second: Optional[float] = None


def analyze_interval(conn, row: pd.Series) -> SegmentResult:
    """Analyze single interval with segment comparisons."""
    
    result = SegmentResult(
        interval_id=row['id'],
        hr_peak=row['hr_peak'],
        hrr60_abs=row.get('hrr60_abs'),
        tau_recorded=float(row['tau_seconds']) if pd.notna(row.get('tau_seconds')) else None,
        r2_recorded=float(row['tau_fit_r2']) if pd.notna(row.get('tau_fit_r2')) else None
    )
    
    t, hr = load_hr_samples(
        conn, 
        row['session_id'], 
        row['is_polar'],
        row['start_time'], 
        65  # Load 65s to ensure we have full 60
    )
    
    if len(hr) < 50:
        return result
    
    # Fit full 0-60s
    full = fit_segment(t, hr, 0, 60)
    if full:
        result.r2_full = round(full['r2'], 4)
        result.tau_full = round(full['tau'], 1)
    
    # Fit first half 0-30s
    first = fit_segment(t, hr, 0, 30)
    if first:
        result.r2_first = round(first['r2'], 4)
        result.tau_first = round(first['tau'], 1)
        result.hr_drop_first = round(first['hr_drop'], 1)
    
    # Fit second half 30-60s
    second = fit_segment(t, hr, 30, 60)
    if second:
        result.r2_second = round(second['r2'], 4)
        result.tau_second = round(second['tau'], 1)
        result.hr_drop_second = round(second['hr_drop'], 1)
    
    # Derived metrics
    if result.r2_first is not None and result.r2_second is not None:
        result.r2_delta = round(result.r2_first - result.r2_second, 4)
        if result.r2_first > 0:
            result.r2_ratio = round(result.r2_second / result.r2_first, 4)
    
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HRR R² Segment Analysis')
    parser.add_argument('--output', type=str, default='outputs/hrr_r2_segments.csv')
    parser.add_argument('--min-duration', type=int, default=65)
    args = parser.parse_args()
    
    print("HRR R² Segment Analysis")
    print("=" * 60)
    print("Testing: Does R² differ between 0-30s and 30-60s?")
    print()
    
    conn = get_db_connection()
    df = get_intervals(conn, args.min_duration)
    print(f"Found {len(df)} intervals with duration >= {args.min_duration}s")
    
    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i+1}/{len(df)}...")
        try:
            result = analyze_interval(conn, row)
            results.append(asdict(result))
        except Exception as e:
            print(f"  Error on interval {row['id']}: {e}")
    
    conn.close()
    
    results_df = pd.DataFrame(results)
    
    # Stats
    has_both = results_df[
        results_df['r2_first'].notna() & 
        results_df['r2_second'].notna()
    ]
    
    print(f"\nIntervals with both segments fit: {len(has_both)}/{len(results_df)}")
    
    if len(has_both) > 0:
        print(f"\n{'='*60}")
        print("R² by segment:")
        print(f"{'='*60}")
        print(f"  Full (0-60s):   mean={has_both['r2_full'].mean():.3f}, std={has_both['r2_full'].std():.3f}")
        print(f"  First (0-30s):  mean={has_both['r2_first'].mean():.3f}, std={has_both['r2_first'].std():.3f}")
        print(f"  Second (30-60s): mean={has_both['r2_second'].mean():.3f}, std={has_both['r2_second'].std():.3f}")
        
        print(f"\n{'='*60}")
        print("R² Delta (first - second):")
        print(f"{'='*60}")
        delta = has_both['r2_delta']
        print(f"  Mean:   {delta.mean():.4f}")
        print(f"  Std:    {delta.std():.4f}")
        print(f"  Min:    {delta.min():.4f}")
        print(f"  Max:    {delta.max():.4f}")
        
        print(f"\n  Percentiles:")
        for pct in [5, 10, 25, 50, 75, 90, 95]:
            print(f"    {pct:3d}th: {delta.quantile(pct/100):.4f}")
        
        print(f"\n  Delta > 0 (first half fits better): {(delta > 0).sum()} ({(delta > 0).mean()*100:.1f}%)")
        print(f"  Delta > 0.1: {(delta > 0.1).sum()} ({(delta > 0.1).mean()*100:.1f}%)")
        print(f"  Delta > 0.2: {(delta > 0.2).sum()} ({(delta > 0.2).mean()*100:.1f}%)")
        print(f"  Delta > 0.3: {(delta > 0.3).sum()} ({(delta > 0.3).mean()*100:.1f}%)")
        
        print(f"\n  Delta < 0 (second half fits better): {(delta < 0).sum()} ({(delta < 0).mean()*100:.1f}%)")
        print(f"  Delta < -0.1: {(delta < -0.1).sum()} ({(delta < -0.1).mean()*100:.1f}%)")
        
        # Correlation with overall R²
        print(f"\n{'='*60}")
        print("Correlations:")
        print(f"{'='*60}")
        corr_full_delta = has_both['r2_full'].corr(has_both['r2_delta'])
        corr_first_second = has_both['r2_first'].corr(has_both['r2_second'])
        print(f"  r2_full vs r2_delta: {corr_full_delta:.3f}")
        print(f"  r2_first vs r2_second: {corr_first_second:.3f}")
        
        # Key question: does high r2_full mask bad r2_second?
        print(f"\n{'='*60}")
        print("Key question: High overall R² but bad second half?")
        print(f"{'='*60}")
        
        good_overall = has_both[has_both['r2_full'] >= 0.75]
        print(f"\nAmong intervals with r2_full >= 0.75 (n={len(good_overall)}):")
        if len(good_overall) > 0:
            print(f"  r2_second mean: {good_overall['r2_second'].mean():.3f}")
            print(f"  r2_second < 0.5: {(good_overall['r2_second'] < 0.5).sum()} ({(good_overall['r2_second'] < 0.5).mean()*100:.1f}%)")
            print(f"  r2_second < 0.3: {(good_overall['r2_second'] < 0.3).sum()} ({(good_overall['r2_second'] < 0.3).mean()*100:.1f}%)")
            print(f"  r2_delta > 0.3: {(good_overall['r2_delta'] > 0.3).sum()} ({(good_overall['r2_delta'] > 0.3).mean()*100:.1f}%)")
        
        # Show worst offenders
        print(f"\n{'='*60}")
        print("Worst cases: High overall R², poor second half")
        print(f"{'='*60}")
        
        masked_bad = has_both[
            (has_both['r2_full'] >= 0.75) & 
            (has_both['r2_second'] < 0.5)
        ].sort_values('r2_second')
        
        if len(masked_bad) > 0:
            print(f"\nFound {len(masked_bad)} intervals with r2_full>=0.75 but r2_second<0.5:")
            print(f"{'ID':>8} {'r2_full':>8} {'r2_first':>9} {'r2_second':>10} {'delta':>8} {'hrr60':>6}")
            print("-" * 55)
            for _, r in masked_bad.head(15).iterrows():
                print(f"{r['interval_id']:>8} {r['r2_full']:>8.3f} {r['r2_first']:>9.3f} {r['r2_second']:>10.3f} {r['r2_delta']:>8.3f} {r['hrr60_abs'] or 'N/A':>6}")
        else:
            print("\nNo intervals found where high overall R² masks poor second half fit.")
            print("This suggests the overall R² gate is working adequately.")
        
        # HR drop comparison
        print(f"\n{'='*60}")
        print("Signal strength by segment:")
        print(f"{'='*60}")
        hr_drop_first = has_both['hr_drop_first'].dropna()
        hr_drop_second = has_both['hr_drop_second'].dropna()
        print(f"  HR drop 0-30s:  mean={hr_drop_first.mean():.1f} bpm")
        print(f"  HR drop 30-60s: mean={hr_drop_second.mean():.1f} bpm")
        print(f"  Ratio (first/second): {hr_drop_first.mean() / hr_drop_second.mean():.2f}x")
    
    # Save
    output_path = PROJECT_ROOT / args.output
    results_df.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path}")


if __name__ == '__main__':
    main()
