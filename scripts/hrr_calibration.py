#!/usr/bin/env python3
"""
HRR Detection Calibration

Data-driven threshold derivation based on measurement properties:
1. Estimate instrument noise from stable HR periods
2. Compute within-subject typical error (TE) for key metrics
3. Derive thresholds using statistical formulas

Run periodically or when device/setup changes.

Usage:
    python scripts/hrr_calibration.py
    python scripts/hrr_calibration.py --sessions 31 70 64
    python scripts/hrr_calibration.py --output-dir ./outputs
"""

import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter
from scipy import stats

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


# =============================================================================
# Database
# =============================================================================

def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def load_session_hr(conn, session_id: int) -> tuple[np.ndarray, np.ndarray]:
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


def get_all_sessions(conn, min_samples: int = 1000) -> list[int]:
    """Get all sessions with sufficient data."""
    query = """
        SELECT session_id, COUNT(*) as samples
        FROM hr_samples
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        HAVING COUNT(*) >= %s
        ORDER BY MIN(sample_time) DESC
    """
    with conn.cursor() as cur:
        cur.execute(query, (min_samples,))
        rows = cur.fetchall()
    return [r[0] for r in rows]


# =============================================================================
# Noise Estimation
# =============================================================================

def find_stable_periods(hr: np.ndarray, window_size: int = 30, max_range: float = 5.0) -> list[tuple[int, int]]:
    """
    Find periods where HR is relatively stable (low variance).
    
    Returns list of (start_idx, end_idx) for stable windows.
    """
    stable_periods = []
    
    for i in range(0, len(hr) - window_size, window_size // 2):
        window = hr[i:i + window_size]
        hr_range = np.max(window) - np.min(window)
        
        if hr_range <= max_range:
            stable_periods.append((i, i + window_size))
    
    return stable_periods


def estimate_noise_from_stable_periods(hr: np.ndarray, stable_periods: list[tuple[int, int]]) -> dict:
    """
    Estimate measurement noise from stable HR periods.
    
    Returns noise statistics.
    """
    all_diffs = []
    
    for start, end in stable_periods:
        segment = hr[start:end]
        diffs = np.diff(segment)
        all_diffs.extend(diffs)
    
    if not all_diffs:
        return None
    
    all_diffs = np.array(all_diffs)
    
    return {
        'n_periods': len(stable_periods),
        'n_diffs': len(all_diffs),
        'diff_mean': float(np.mean(all_diffs)),
        'diff_std': float(np.std(all_diffs)),
        'diff_abs_mean': float(np.mean(np.abs(all_diffs))),
        'diff_abs_median': float(np.median(np.abs(all_diffs))),
        'diff_percentile_95': float(np.percentile(np.abs(all_diffs), 95)),
        'diff_percentile_99': float(np.percentile(np.abs(all_diffs), 99)),
    }


def estimate_noise_across_sessions(conn, session_ids: list[int]) -> dict:
    """
    Estimate noise across multiple sessions.
    """
    all_noise_stats = []
    all_diffs = []
    
    for sid in session_ids:
        ts, hr = load_session_hr(conn, sid)
        if len(hr) < 100:
            continue
        
        stable = find_stable_periods(hr)
        if not stable:
            continue
        
        for start, end in stable:
            segment = hr[start:end]
            diffs = np.diff(segment)
            all_diffs.extend(diffs)
        
        stats = estimate_noise_from_stable_periods(hr, stable)
        if stats:
            stats['session_id'] = sid
            all_noise_stats.append(stats)
    
    if not all_diffs:
        return {'error': 'No stable periods found'}
    
    all_diffs = np.array(all_diffs)
    
    return {
        'sessions_analyzed': len(all_noise_stats),
        'total_stable_diffs': len(all_diffs),
        'instrument_noise_sd': float(np.std(all_diffs)),
        'instrument_noise_abs_mean': float(np.mean(np.abs(all_diffs))),
        'instrument_noise_abs_median': float(np.median(np.abs(all_diffs))),
        'instrument_noise_p95': float(np.percentile(np.abs(all_diffs), 95)),
        'instrument_noise_p99': float(np.percentile(np.abs(all_diffs), 99)),
        'per_session': all_noise_stats,
    }


# =============================================================================
# Interval Detection (permissive settings for calibration)
# =============================================================================

def smooth_hr(hr: np.ndarray, kernel: int = 5) -> np.ndarray:
    if len(hr) < kernel:
        return hr.copy()
    med = median_filter(hr, size=kernel, mode='nearest')
    k = np.ones(kernel) / kernel
    return np.convolve(med, k, mode='same')


def detect_intervals_permissive(hr: np.ndarray, allowed_up: float = 1.0, 
                                 min_duration: int = 60, smooth_k: int = 5) -> list[dict]:
    """
    Detect intervals with permissive settings to gather calibration data.
    No quality gates applied - we want all potential intervals.
    """
    hr_smooth = smooth_hr(hr, smooth_k)
    
    if len(hr_smooth) < 2:
        return []
    
    diff = np.diff(hr_smooth)
    non_rising = diff <= allowed_up
    
    # Find runs
    runs = []
    in_run = False
    run_start = 0
    
    for i, nr in enumerate(non_rising):
        if nr and not in_run:
            in_run = True
            run_start = i
        elif not nr and in_run:
            if i - run_start >= min_duration:
                runs.append((run_start, i))
            in_run = False
    
    if in_run and len(non_rising) - run_start >= min_duration:
        runs.append((run_start, len(non_rising)))
    
    # Extract features for each run
    intervals = []
    for run_start, run_end in runs:
        # Find peak (lookback 30s)
        lookback = max(0, run_start - 30)
        peak_region = hr_smooth[lookback:run_start + 1]
        if len(peak_region) == 0:
            continue
        
        peak_idx = lookback + np.argmax(peak_region)
        hr_peak = float(hr_smooth[peak_idx])
        
        # Find nadir
        run_region = hr_smooth[run_start:run_end + 1]
        nadir_idx = run_start + np.argmin(run_region)
        hr_nadir = float(hr_smooth[nadir_idx])
        
        # Duration from peak
        duration = run_end - peak_idx
        total_drop = hr_peak - hr_nadir
        
        # Local rest (60-180s before peak)
        rest_start = max(0, peak_idx - 180)
        rest_end = max(0, peak_idx - 60)
        local_rest = None
        peak_minus_rest = None
        if rest_end > rest_start:
            rest_window = hr_smooth[rest_start:rest_end]
            if len(rest_window) >= 10:
                local_rest = float(np.median(rest_window))
                peak_minus_rest = hr_peak - local_rest
        
        # HRR values
        def hr_at(offset):
            idx = peak_idx + offset
            return float(hr_smooth[idx]) if 0 <= idx < len(hr_smooth) else None
        
        hr_60 = hr_at(60)
        hrr60 = hr_peak - hr_60 if hr_60 else None
        
        hr_120 = hr_at(120)
        hrr120 = hr_peak - hr_120 if hr_120 else None
        
        intervals.append({
            'peak_idx': peak_idx,
            'hr_peak': hr_peak,
            'hr_nadir': hr_nadir,
            'total_drop': total_drop,
            'duration_sec': duration,
            'local_rest': local_rest,
            'peak_minus_rest': peak_minus_rest,
            'hrr60': hrr60,
            'hrr120': hrr120,
        })
    
    return intervals


# =============================================================================
# Typical Error Computation
# =============================================================================

def compute_typical_error(values: list[float]) -> dict:
    """
    Compute typical error (TE) statistics.
    
    TE = SD of differences / sqrt(2) for test-retest
    
    For within-session variability, we use SD directly.
    SDD = 1.96 * sqrt(2) * SEM ≈ 2.77 * SEM
    """
    if len(values) < 3:
        return None
    
    arr = np.array(values)
    
    # Basic stats
    mean = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1))
    sem = sd / np.sqrt(len(arr))
    
    # Typical error (using SD as proxy for within-subject variability)
    te = sd / np.sqrt(2)
    
    # Smallest detectable difference
    sdd = 1.96 * np.sqrt(2) * sem
    
    # Coefficient of variation
    cv = (sd / mean * 100) if mean != 0 else None
    
    return {
        'n': len(arr),
        'mean': mean,
        'sd': sd,
        'sem': sem,
        'te': te,
        'sdd': sdd,
        'cv_percent': cv,
        'min': float(np.min(arr)),
        'max': float(np.max(arr)),
        'range': float(np.max(arr) - np.min(arr)),
    }


def gather_interval_metrics(conn, session_ids: list[int]) -> pd.DataFrame:
    """
    Gather interval metrics across sessions for TE computation.
    """
    all_intervals = []
    
    for sid in session_ids:
        ts, hr = load_session_hr(conn, sid)
        if len(hr) < 100:
            continue
        
        intervals = detect_intervals_permissive(hr)
        
        for interval in intervals:
            interval['session_id'] = sid
            all_intervals.append(interval)
    
    return pd.DataFrame(all_intervals)


# =============================================================================
# Threshold Derivation
# =============================================================================

@dataclass
class CalibratedThresholds:
    """Thresholds derived from calibration data."""
    
    # Derived values
    min_peak_minus_rest: float
    min_total_drop: float
    allowed_up_per_sec: float
    
    # Recommended smoothing (based on noise level)
    smooth_kernel: int
    
    # Source statistics
    instrument_noise_sd: float
    te_peak_minus_rest: float
    te_total_drop: float
    te_hrr60: float
    
    # Metadata
    sessions_analyzed: int
    intervals_analyzed: int
    calibration_date: str


def derive_thresholds(noise_stats: dict, te_stats: dict) -> CalibratedThresholds:
    """
    Derive thresholds from noise and TE statistics.
    
    Formulas:
    - min_peak_minus_rest = max(5, 2 * noise, 1.5 * TE)
    - min_total_drop = max(5, 2 * noise, 1.5 * TE)
    - allowed_up_per_sec = noise_p95 (allow fluctuations up to 95th percentile)
    - smooth_kernel = depends on noise level
    """
    
    noise_sd = noise_stats.get('instrument_noise_sd', 1.0)
    noise_p95 = noise_stats.get('instrument_noise_p95', 1.0)
    
    te_pmr = te_stats.get('peak_minus_rest', {}).get('te', 5.0) if te_stats.get('peak_minus_rest') else 5.0
    te_drop = te_stats.get('total_drop', {}).get('te', 5.0) if te_stats.get('total_drop') else 5.0
    te_hrr60 = te_stats.get('hrr60', {}).get('te', 5.0) if te_stats.get('hrr60') else 5.0
    
    # Derive thresholds
    min_peak_minus_rest = max(5.0, 2 * noise_sd, 1.5 * te_pmr)
    min_total_drop = max(5.0, 2 * noise_sd, 1.5 * te_drop)
    
    # allowed_up: use 95th percentile of noise, but cap at reasonable range
    allowed_up = min(max(noise_p95, 0.3), 1.0)
    
    # Smoothing: higher noise → more smoothing
    if noise_sd < 0.5:
        smooth_k = 3
    elif noise_sd < 1.0:
        smooth_k = 5
    else:
        smooth_k = 7
    
    return CalibratedThresholds(
        min_peak_minus_rest=round(min_peak_minus_rest, 1),
        min_total_drop=round(min_total_drop, 1),
        allowed_up_per_sec=round(allowed_up, 2),
        smooth_kernel=smooth_k,
        instrument_noise_sd=round(noise_sd, 3),
        te_peak_minus_rest=round(te_pmr, 2),
        te_total_drop=round(te_drop, 2),
        te_hrr60=round(te_hrr60, 2),
        sessions_analyzed=noise_stats.get('sessions_analyzed', 0),
        intervals_analyzed=te_stats.get('n_intervals', 0),
        calibration_date=datetime.now().isoformat(),
    )


# =============================================================================
# Main Calibration Routine
# =============================================================================

def run_calibration(session_ids: list[int] = None, output_dir: str = '/tmp') -> CalibratedThresholds:
    """
    Run full calibration routine.
    """
    conn = get_db_connection()
    output_path = Path(output_dir)
    
    # Get sessions
    if session_ids is None:
        session_ids = get_all_sessions(conn)
    
    print(f"Running calibration on {len(session_ids)} sessions...")
    
    # Step 1: Estimate noise
    print("\n1. Estimating instrument noise from stable HR periods...")
    noise_stats = estimate_noise_across_sessions(conn, session_ids)
    
    print(f"   Stable periods analyzed: {noise_stats.get('total_stable_diffs', 0)} samples")
    print(f"   Instrument noise SD: {noise_stats.get('instrument_noise_sd', 'N/A'):.3f} bpm")
    print(f"   Noise P95: {noise_stats.get('instrument_noise_p95', 'N/A'):.3f} bpm")
    print(f"   Noise P99: {noise_stats.get('instrument_noise_p99', 'N/A'):.3f} bpm")
    
    # Step 2: Gather intervals with permissive detection
    print("\n2. Detecting intervals (permissive settings)...")
    df = gather_interval_metrics(conn, session_ids)
    conn.close()
    
    print(f"   Total intervals detected: {len(df)}")
    print(f"   Sessions with intervals: {df['session_id'].nunique()}")
    
    # Step 3: Compute TE for each metric
    print("\n3. Computing typical error (TE) for metrics...")
    
    te_stats = {'n_intervals': len(df)}
    
    metrics = ['peak_minus_rest', 'total_drop', 'hrr60', 'hrr120']
    for metric in metrics:
        values = df[metric].dropna().tolist()
        if values:
            te = compute_typical_error(values)
            te_stats[metric] = te
            if te:
                print(f"   {metric}: mean={te['mean']:.1f}, SD={te['sd']:.1f}, TE={te['te']:.2f}, CV={te['cv_percent']:.1f}%")
    
    # Step 4: Derive thresholds
    print("\n4. Deriving thresholds...")
    thresholds = derive_thresholds(noise_stats, te_stats)
    
    print(f"\n{'='*60}")
    print("CALIBRATED THRESHOLDS")
    print('='*60)
    print(f"   min_peak_minus_rest: {thresholds.min_peak_minus_rest} bpm")
    print(f"   min_total_drop: {thresholds.min_total_drop} bpm")
    print(f"   allowed_up_per_sec: {thresholds.allowed_up_per_sec} bpm/s")
    print(f"   smooth_kernel: {thresholds.smooth_kernel}")
    print('='*60)
    
    # Step 5: Save outputs
    
    # Calibration results JSON
    cal_path = output_path / 'hrr_calibration.json'
    with open(cal_path, 'w') as f:
        json.dump(asdict(thresholds), f, indent=2)
    print(f"\nSaved calibration to: {cal_path}")
    
    # Detailed stats CSV
    stats_data = {
        'metric': [],
        'n': [],
        'mean': [],
        'sd': [],
        'te': [],
        'sdd': [],
        'cv_percent': [],
    }
    for metric in metrics:
        if metric in te_stats and te_stats[metric]:
            te = te_stats[metric]
            stats_data['metric'].append(metric)
            stats_data['n'].append(te['n'])
            stats_data['mean'].append(te['mean'])
            stats_data['sd'].append(te['sd'])
            stats_data['te'].append(te['te'])
            stats_data['sdd'].append(te['sdd'])
            stats_data['cv_percent'].append(te['cv_percent'])
    
    stats_df = pd.DataFrame(stats_data)
    stats_path = output_path / 'hrr_calibration_te_stats.csv'
    stats_df.to_csv(stats_path, index=False)
    print(f"Saved TE stats to: {stats_path}")
    
    # Raw intervals for inspection
    intervals_path = output_path / 'hrr_calibration_intervals.csv'
    df.to_csv(intervals_path, index=False)
    print(f"Saved interval data to: {intervals_path}")
    
    # Comparison plot
    create_calibration_plots(df, noise_stats, thresholds, output_path)
    
    return thresholds


def create_calibration_plots(df: pd.DataFrame, noise_stats: dict, 
                              thresholds: CalibratedThresholds, output_path: Path):
    """Create calibration visualization plots."""
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # 1. Noise distribution
    ax = axes[0, 0]
    # We don't have raw diffs saved, so skip histogram
    ax.text(0.5, 0.5, f"Instrument Noise\n\nSD: {noise_stats.get('instrument_noise_sd', 0):.3f} bpm\n"
            f"P95: {noise_stats.get('instrument_noise_p95', 0):.3f} bpm\n"
            f"P99: {noise_stats.get('instrument_noise_p99', 0):.3f} bpm",
            ha='center', va='center', fontsize=12, transform=ax.transAxes)
    ax.set_title('Instrument Noise (from stable periods)')
    ax.axis('off')
    
    # 2. peak_minus_rest distribution with threshold
    ax = axes[0, 1]
    pmr = df['peak_minus_rest'].dropna()
    if len(pmr) > 0:
        ax.hist(pmr, bins=30, alpha=0.7, color='steelblue', edgecolor='white')
        ax.axvline(thresholds.min_peak_minus_rest, color='red', linestyle='--', 
                   label=f'Threshold: {thresholds.min_peak_minus_rest}')
        ax.axvline(5.0, color='gray', linestyle=':', label='Floor: 5.0')
        ax.set_xlabel('peak_minus_rest (bpm)')
        ax.set_ylabel('Count')
        ax.legend()
    ax.set_title('Peak Minus Rest Distribution')
    
    # 3. total_drop distribution with threshold
    ax = axes[1, 0]
    td = df['total_drop'].dropna()
    if len(td) > 0:
        ax.hist(td, bins=30, alpha=0.7, color='forestgreen', edgecolor='white')
        ax.axvline(thresholds.min_total_drop, color='red', linestyle='--',
                   label=f'Threshold: {thresholds.min_total_drop}')
        ax.axvline(5.0, color='gray', linestyle=':', label='Floor: 5.0')
        ax.set_xlabel('total_drop (bpm)')
        ax.set_ylabel('Count')
        ax.legend()
    ax.set_title('Total Drop Distribution')
    
    # 4. HRR60 distribution
    ax = axes[1, 1]
    hrr60 = df['hrr60'].dropna()
    if len(hrr60) > 0:
        ax.hist(hrr60, bins=30, alpha=0.7, color='darkorange', edgecolor='white')
        ax.set_xlabel('HRR60 (bpm)')
        ax.set_ylabel('Count')
        
        mean = hrr60.mean()
        ax.axvline(mean, color='red', linestyle='--', label=f'Mean: {mean:.1f}')
        ax.legend()
    ax.set_title('HRR60 Distribution')
    
    plt.suptitle(f'HRR Calibration Results\n'
                 f'Sessions: {thresholds.sessions_analyzed}, '
                 f'Intervals: {thresholds.intervals_analyzed}', 
                 fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    plot_path = output_path / 'hrr_calibration_plots.png'
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"Saved plots to: {plot_path}")
    plt.close()


# =============================================================================
# Main
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HRR Detection Calibration')
    parser.add_argument('--sessions', type=int, nargs='+', help='Specific session IDs')
    parser.add_argument('--output-dir', type=str, default='/tmp')
    
    args = parser.parse_args()
    
    run_calibration(args.sessions, args.output_dir)


if __name__ == '__main__':
    main()
