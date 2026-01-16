#!/usr/bin/env python3
"""
HRR Late Slope Analysis (90-120s)

Test hypothesis: HR should still be declining (or flat) in the 90-120s window.
Positive slope suggests activity resumed or artifact.

Author: Arnold Project
Date: 2026-01-15
"""

import os
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def get_intervals(conn, min_duration: int = 125) -> pd.DataFrame:
    """Get intervals with at least 125s (need full 120s + buffer)."""
    query = f"""
        SELECT 
            id,
            COALESCE(polar_session_id, endurance_session_id) as session_id,
            polar_session_id IS NOT NULL as is_polar,
            start_time,
            duration_seconds,
            hr_peak,
            hrr60_abs,
            hrr120_abs,
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


def fit_linear_slope(t: np.ndarray, hr: np.ndarray, 
                     t_start: float, t_end: float) -> Optional[dict]:
    """
    Fit linear slope to a time segment.
    Returns dict with slope, intercept, r2, n_points or None if insufficient data.
    """
    mask = (t >= t_start) & (t <= t_end)
    t_seg = t[mask]
    hr_seg = hr[mask]
    
    if len(t_seg) < 10:
        return None
    
    try:
        # Linear fit: hr = slope * t + intercept
        coeffs = np.polyfit(t_seg, hr_seg, 1)
        slope, intercept = coeffs
        
        # Compute R²
        predicted = slope * t_seg + intercept
        ss_res = np.sum((hr_seg - predicted) ** 2)
        ss_tot = np.sum((hr_seg - np.mean(hr_seg)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        return {
            'slope': slope,
            'intercept': intercept,
            'r2': r2,
            'n_points': len(t_seg),
            'hr_start': hr_seg[0],
            'hr_end': hr_seg[-1],
            'hr_mean': np.mean(hr_seg),
            'hr_std': np.std(hr_seg)
        }
    except Exception:
        return None


@dataclass
class LateSleopeResult:
    interval_id: int
    hr_peak: int
    hrr60_abs: Optional[int]
    hrr120_abs: Optional[int]
    r2_recorded: Optional[float]
    
    # 90-120s linear fit
    slope_90_120: Optional[float] = None  # bpm/sec
    slope_90_120_r2: Optional[float] = None
    hr_at_90: Optional[float] = None
    hr_at_120: Optional[float] = None
    hr_change_90_120: Optional[float] = None  # hr_120 - hr_90
    
    # For comparison: 60-90s slope
    slope_60_90: Optional[float] = None
    
    # Noise indicator
    hr_std_90_120: Optional[float] = None


def analyze_interval(conn, row: pd.Series) -> LateSleopeResult:
    """Analyze single interval for late slope."""
    
    result = LateSleopeResult(
        interval_id=row['id'],
        hr_peak=row['hr_peak'],
        hrr60_abs=row.get('hrr60_abs'),
        hrr120_abs=row.get('hrr120_abs'),
        r2_recorded=float(row['tau_fit_r2']) if pd.notna(row.get('tau_fit_r2')) else None
    )
    
    t, hr = load_hr_samples(
        conn, 
        row['session_id'], 
        row['is_polar'],
        row['start_time'], 
        130  # Load 130s to ensure we have full 120
    )
    
    if len(hr) < 100:
        return result
    
    # Fit 90-120s
    late = fit_linear_slope(t, hr, 90, 120)
    if late:
        result.slope_90_120 = round(late['slope'], 4)
        result.slope_90_120_r2 = round(late['r2'], 4)
        result.hr_at_90 = round(late['hr_start'], 1)
        result.hr_at_120 = round(late['hr_end'], 1)
        result.hr_change_90_120 = round(late['hr_end'] - late['hr_start'], 1)
        result.hr_std_90_120 = round(late['hr_std'], 2)
    
    # Fit 60-90s for comparison
    mid = fit_linear_slope(t, hr, 60, 90)
    if mid:
        result.slope_60_90 = round(mid['slope'], 4)
    
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HRR Late Slope Analysis (90-120s)')
    parser.add_argument('--output', type=str, default='outputs/hrr_late_slope.csv')
    parser.add_argument('--min-duration', type=int, default=125)
    args = parser.parse_args()
    
    print("HRR Late Slope Analysis (90-120s)")
    print("=" * 60)
    print("Hypothesis: Slope should be <= 0 (still declining or flat)")
    print("Positive slope suggests activity resumed or artifact")
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
    
    # Filter to those with valid slope
    has_slope = results_df[results_df['slope_90_120'].notna()]
    
    print(f"\nIntervals with 90-120s slope computed: {len(has_slope)}/{len(results_df)}")
    
    if len(has_slope) > 0:
        slope = has_slope['slope_90_120']
        
        print(f"\n{'='*60}")
        print("90-120s Slope (bpm/sec):")
        print(f"{'='*60}")
        print(f"  Mean:   {slope.mean():.4f}")
        print(f"  Std:    {slope.std():.4f}")
        print(f"  Min:    {slope.min():.4f}")
        print(f"  Max:    {slope.max():.4f}")
        
        print(f"\n  Percentiles:")
        for pct in [5, 10, 25, 50, 75, 90, 95]:
            print(f"    {pct:3d}th: {slope.quantile(pct/100):.4f}")
        
        print(f"\n  Slope <= 0 (still declining/flat): {(slope <= 0).sum()} ({(slope <= 0).mean()*100:.1f}%)")
        print(f"  Slope > 0 (HR rising): {(slope > 0).sum()} ({(slope > 0).mean()*100:.1f}%)")
        print(f"  Slope > 0.1 (HR rising fast): {(slope > 0.1).sum()} ({(slope > 0.1).mean()*100:.1f}%)")
        print(f"  Slope > 0.2 (HR rising very fast): {(slope > 0.2).sum()} ({(slope > 0.2).mean()*100:.1f}%)")
        
        # Convert to bpm over 30s for intuition
        print(f"\n  Intuition (slope × 30s = HR change over window):")
        print(f"    Mean HR change 90→120s: {slope.mean() * 30:.1f} bpm")
        print(f"    95th percentile: {slope.quantile(0.95) * 30:.1f} bpm")
        
        # Noise analysis
        print(f"\n{'='*60}")
        print("Noise in 90-120s window:")
        print(f"{'='*60}")
        hr_std = has_slope['hr_std_90_120']
        print(f"  HR std dev: mean={hr_std.mean():.2f}, median={hr_std.median():.2f}")
        print(f"  High noise (std > 5): {(hr_std > 5).sum()} ({(hr_std > 5).mean()*100:.1f}%)")
        
        # Compare 60-90 vs 90-120 slopes
        has_both = has_slope[has_slope['slope_60_90'].notna()]
        if len(has_both) > 0:
            print(f"\n{'='*60}")
            print("Slope comparison (60-90s vs 90-120s):")
            print(f"{'='*60}")
            print(f"  60-90s slope mean: {has_both['slope_60_90'].mean():.4f}")
            print(f"  90-120s slope mean: {has_both['slope_90_120'].mean():.4f}")
            
            # How often does slope flip from negative to positive?
            flip_to_positive = (has_both['slope_60_90'] <= 0) & (has_both['slope_90_120'] > 0)
            print(f"\n  Slope flips negative→positive: {flip_to_positive.sum()} ({flip_to_positive.mean()*100:.1f}%)")
        
        # Correlation with existing quality metrics
        print(f"\n{'='*60}")
        print("Correlation with other quality indicators:")
        print(f"{'='*60}")
        
        # Positive slope vs low overall R²
        if 'r2_recorded' in has_slope.columns:
            has_r2 = has_slope[has_slope['r2_recorded'].notna()]
            if len(has_r2) > 0:
                corr = has_r2['slope_90_120'].corr(has_r2['r2_recorded'])
                print(f"  slope_90_120 vs r2_recorded: {corr:.3f}")
                
                # Among positive slope intervals, what's the R² distribution?
                pos_slope = has_r2[has_r2['slope_90_120'] > 0]
                neg_slope = has_r2[has_r2['slope_90_120'] <= 0]
                if len(pos_slope) > 0 and len(neg_slope) > 0:
                    print(f"\n  R² when slope > 0: mean={pos_slope['r2_recorded'].mean():.3f}")
                    print(f"  R² when slope <= 0: mean={neg_slope['r2_recorded'].mean():.3f}")
        
        # Show worst offenders
        print(f"\n{'='*60}")
        print("Worst cases: Highest positive slope (HR rising in late recovery)")
        print(f"{'='*60}")
        
        worst = has_slope.nlargest(10, 'slope_90_120')
        print(f"\n{'ID':>8} {'slope':>8} {'hr_90':>7} {'hr_120':>8} {'change':>8} {'hrr120':>7}")
        print("-" * 55)
        for _, r in worst.iterrows():
            hrr120_str = f"{r['hrr120_abs']:.0f}" if pd.notna(r['hrr120_abs']) else "N/A"
            print(f"{r['interval_id']:>8} {r['slope_90_120']:>8.4f} {r['hr_at_90']:>7.1f} {r['hr_at_120']:>8.1f} {r['hr_change_90_120']:>8.1f} {hrr120_str:>7}")
    
    # Save
    output_path = PROJECT_ROOT / args.output
    results_df.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path}")


if __name__ == '__main__':
    main()
