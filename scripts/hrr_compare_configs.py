#!/usr/bin/env python3
"""
Compare Grid Search vs Calibration thresholds across all sessions.
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def load_session_hr(conn, session_id: int):
    query = """
        SELECT sample_time, hr_value
        FROM hr_samples
        WHERE session_id = %s
        ORDER BY sample_time
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()
    
    if not rows:
        return np.array([]), np.array([])
    
    hr_values = np.array([row[1] for row in rows], dtype=float)
    datetimes = [row[0] for row in rows]
    t0 = datetimes[0]
    timestamps_sec = np.array([(dt - t0).total_seconds() for dt in datetimes])
    
    return timestamps_sec, hr_values


def get_all_sessions(conn):
    query = """
        SELECT session_id, COUNT(*) as samples,
               EXTRACT(EPOCH FROM (MAX(sample_time) - MIN(sample_time)))/60 as duration_min
        FROM hr_samples
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        HAVING COUNT(*) >= 1000
        ORDER BY MIN(sample_time)
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def smooth_hr(hr: np.ndarray, kernel: int) -> np.ndarray:
    if len(hr) < kernel:
        return hr.copy()
    med = median_filter(hr, size=kernel, mode='nearest')
    k = np.ones(kernel) / kernel
    return np.convolve(med, k, mode='same')


def detect_intervals(hr: np.ndarray, allowed_up: float, smooth_k: int,
                     min_drop: float, min_peak_rest: float) -> dict:
    """Run detection with given params."""
    
    hr_smooth = smooth_hr(hr, smooth_k)
    
    if len(hr_smooth) < 2:
        return {'total': 0, 'valid': 0, 'hrr60_vals': [], 'hrr120_count': 0}
    
    diff = np.diff(hr_smooth)
    non_rising = diff <= allowed_up
    
    # Find runs >= 60s
    runs = []
    in_run = False
    run_start = 0
    
    for i, nr in enumerate(non_rising):
        if nr and not in_run:
            in_run = True
            run_start = i
        elif not nr and in_run:
            if i - run_start >= 60:
                runs.append((run_start, i))
            in_run = False
    
    if in_run and len(non_rising) - run_start >= 60:
        runs.append((run_start, len(non_rising)))
    
    # Extract and gate
    valid_count = 0
    hrr60_vals = []
    hrr120_count = 0
    
    for run_start, run_end in runs:
        # Find peak
        lookback = max(0, run_start - 20)
        peak_region = hr_smooth[lookback:run_start + 1]
        if len(peak_region) == 0:
            continue
        
        peak_idx = lookback + np.argmax(peak_region)
        hr_peak = float(hr_smooth[peak_idx])
        
        # Nadir
        nadir_idx = run_start + np.argmin(hr_smooth[run_start:run_end + 1])
        hr_nadir = float(hr_smooth[nadir_idx])
        
        total_drop = hr_peak - hr_nadir
        duration = run_end - peak_idx
        
        # Local rest
        rest_start = max(0, peak_idx - 180)
        rest_end = max(0, peak_idx - 60)
        peak_minus_rest = None
        if rest_end > rest_start:
            rest_window = hr_smooth[rest_start:rest_end]
            if len(rest_window) >= 10:
                peak_minus_rest = hr_peak - float(np.median(rest_window))
        
        # Gates
        if duration < 60:
            continue
        if total_drop < min_drop:
            continue
        if peak_minus_rest is not None and peak_minus_rest < min_peak_rest:
            continue
        
        valid_count += 1
        
        # HRR60
        idx_60 = peak_idx + 60
        if 0 <= idx_60 < len(hr_smooth):
            hrr60 = hr_peak - hr_smooth[idx_60]
            hrr60_vals.append(hrr60)
        
        # HRR120
        idx_120 = peak_idx + 120
        if 0 <= idx_120 < len(hr_smooth):
            hrr120_count += 1
    
    return {
        'total': len(runs),
        'valid': valid_count,
        'hrr60_vals': hrr60_vals,
        'hrr120_count': hrr120_count,
    }


def main():
    conn = get_db_connection()
    sessions = get_all_sessions(conn)
    
    print(f"Testing {len(sessions)} sessions\n")
    
    # Two configurations
    configs = {
        'grid_search': {
            'allowed_up': 0.5,
            'smooth_k': 7,
            'min_drop': 5.0,
            'min_peak_rest': 5.0,
        },
        'calibration': {
            'allowed_up': 1.0,
            'smooth_k': 3,
            'min_drop': 17.3,
            'min_peak_rest': 13.6,
        },
    }
    
    results = {name: [] for name in configs}
    
    for sid, samples, duration in sessions:
        ts, hr = load_session_hr(conn, sid)
        if len(hr) < 100:
            continue
        
        for name, cfg in configs.items():
            stats = detect_intervals(hr, cfg['allowed_up'], cfg['smooth_k'],
                                     cfg['min_drop'], cfg['min_peak_rest'])
            results[name].append({
                'session_id': sid,
                'duration_min': duration,
                'runs_detected': stats['total'],
                'valid': stats['valid'],
                'hrr60_count': len(stats['hrr60_vals']),
                'hrr60_mean': np.mean(stats['hrr60_vals']) if stats['hrr60_vals'] else None,
                'hrr120_count': stats['hrr120_count'],
            })
    
    conn.close()
    
    # Summary
    print("=" * 70)
    print("COMPARISON: Grid Search vs Calibration")
    print("=" * 70)
    
    for name, cfg in configs.items():
        df = pd.DataFrame(results[name])
        
        print(f"\n{name.upper()}")
        print(f"  Config: allowed_up={cfg['allowed_up']}, smooth={cfg['smooth_k']}, "
              f"min_drop={cfg['min_drop']}, min_p-r={cfg['min_peak_rest']}")
        print(f"  -" * 30)
        print(f"  Sessions: {len(df)}")
        print(f"  Total valid intervals: {df['valid'].sum()}")
        print(f"  Intervals per session: {df['valid'].mean():.1f} ± {df['valid'].std():.1f}")
        print(f"  Sessions with 0 intervals: {(df['valid'] == 0).sum()}")
        print(f"  HRR60 count: {df['hrr60_count'].sum()}")
        print(f"  HRR120 count: {df['hrr120_count'].sum()}")
        
        hrr60_means = df['hrr60_mean'].dropna()
        if len(hrr60_means) > 0:
            print(f"  HRR60 mean (across sessions): {hrr60_means.mean():.1f} ± {hrr60_means.std():.1f}")
    
    # Per-session comparison
    print("\n" + "=" * 70)
    print("PER-SESSION BREAKDOWN")
    print("=" * 70)
    print(f"{'Session':<10} {'Duration':<10} {'Grid':<8} {'Calib':<8} {'Diff':<8}")
    print("-" * 70)
    
    df_grid = pd.DataFrame(results['grid_search'])
    df_cal = pd.DataFrame(results['calibration'])
    
    for i in range(len(df_grid)):
        sid = df_grid.iloc[i]['session_id']
        dur = df_grid.iloc[i]['duration_min']
        grid_v = df_grid.iloc[i]['valid']
        cal_v = df_cal.iloc[i]['valid']
        diff = grid_v - cal_v
        print(f"{sid:<10} {dur:<10.0f} {grid_v:<8} {cal_v:<8} {diff:+<8}")
    
    print("-" * 70)
    print(f"{'TOTAL':<10} {'':<10} {df_grid['valid'].sum():<8} {df_cal['valid'].sum():<8} "
          f"{df_grid['valid'].sum() - df_cal['valid'].sum():+}")


if __name__ == '__main__':
    main()
