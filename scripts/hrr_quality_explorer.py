#!/usr/bin/env python3
"""
HRR Quality Explorer - Tiered detection-based quality gates

Tiered approach:
  - HRR60: Valley/peak detection scoped to first 60s only
  - HRR120: Linear fit to 90-120s window, check slope sign
  - HRR300: TBD (stricter for deliberate tests)

The key insight: the DETECTABILITY of features is the signal, not magnitude.

Usage:
    python scripts/hrr_quality_explorer.py --session-id 71
    python scripts/hrr_quality_explorer.py --output /tmp/hrr_quality.csv

Author: Arnold Project
Date: 2026-01-14
"""

import argparse
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy.signal import find_peaks
from scipy.ndimage import median_filter

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class QualityConfig:
    """Detection parameters (not thresholds!)"""
    
    # Current gate (for comparison)
    min_r2_actionable: float = 0.75
    
    # Peak/valley detection parameters (scipy find_peaks)
    # These control SENSITIVITY of detection, not pass/fail thresholds
    peak_prominence: float = 5.0   # min prominence for peak detection
    peak_distance: int = 10        # min samples between peaks
    valley_prominence: float = 5.0  # min prominence for valley detection
    valley_distance: int = 10       # min samples between valleys
    
    # HRR60 window for valley/peak checks
    hrr60_window: int = 60
    
    # HRR120 late-window slope check
    hrr120_slope_start: int = 90   # start of slope window
    hrr120_slope_end: int = 120    # end of slope window


@dataclass
class IntervalQuality:
    """Quality metrics for a single HRR interval."""
    
    # Identification
    interval_id: int
    session_id: int
    start_time: datetime
    duration_sec: int
    
    # Existing metrics
    hr_peak: int
    hrr60: Optional[int]
    hrr120: Optional[int]
    r2_60: Optional[float]
    current_actionable: bool
    
    # Gate 1: Valley detection (HRR60 quality)
    valley_detected: bool = False
    valley_count: int = 0
    valley_positions: str = ""
    valley_prominences: str = ""
    
    # Gate 2: Peak detection (HRR60 quality) - THE KEY GATE
    peak_in_interval: bool = False      # Any peak detected after initial 5s
    peak_near_end: bool = False         # Peak at 55-65s (hard fail zone)
    peak_count: int = 0
    peak_positions: str = ""
    nearest_peak_to_end: Optional[int] = None  # How close is nearest peak to 60s
    
    # Gate 3: Positive run detection
    max_positive_run_sec: int = 0
    positive_run_start: Optional[int] = None
    
    # Gate 4: Late window slope (HRR120 quality)
    has_120s_data: bool = False
    late_slope: Optional[float] = None  # bpm/sec, negative = good
    late_slope_r2: Optional[float] = None
    late_window_uptick: bool = False
    
    # Pass/fail summary
    gate1_pass: bool = True   # no problematic valleys
    gate2_pass: bool = True   # no peaks near measurement point
    proposed_actionable: bool = True
    
    # Diff tracking
    status_changed: bool = False
    flip_reason: str = ""


# =============================================================================
# Database
# =============================================================================

def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def get_intervals(conn, session_ids: List[int] = None) -> pd.DataFrame:
    """Get intervals from hr_recovery_intervals."""
    
    query = """
        SELECT 
            id,
            polar_session_id as session_id,
            start_time,
            end_time,
            duration_seconds,
            hr_peak,
            hr_60s,
            hr_120s,
            hrr60_abs,
            hrr120_abs,
            tau_fit_r2 as r2_60,
            actionable
        FROM hr_recovery_intervals
        WHERE polar_session_id IS NOT NULL
    """
    
    if session_ids:
        query += f" AND polar_session_id IN ({','.join(map(str, session_ids))})"
    
    query += " ORDER BY start_time"
    
    return pd.read_sql(query, conn)


def load_hr_window(conn, session_id: int, start_time: datetime, duration_sec: int) -> Tuple[np.ndarray, np.ndarray]:
    """Load HR samples for a specific interval window."""
    
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
    
    t = np.array([r[0] for r in rows])
    hr = np.array([r[1] for r in rows], dtype=float)
    
    return t, hr


# =============================================================================
# Detection Functions
# =============================================================================

def detect_valleys(hr: np.ndarray, cfg: QualityConfig, max_idx: int = None) -> Tuple[bool, int, List[int], List[float]]:
    """
    Detect valleys in HR window.
    
    Args:
        hr: HR array
        cfg: Config
        max_idx: Only check up to this index (for scoping to first 60s)
    
    Returns: (valley_detected, count, positions, prominences)
    """
    if max_idx is not None:
        hr_window = hr[:max_idx]
    else:
        hr_window = hr
    
    if len(hr_window) < 20:
        return False, 0, [], []
    
    # Find valleys by inverting signal
    valleys, properties = find_peaks(
        -hr_window,
        prominence=cfg.valley_prominence,
        distance=cfg.valley_distance
    )
    
    if len(valleys) == 0:
        return False, 0, [], []
    
    prominences = list(properties.get('prominences', []))
    
    return True, len(valleys), valleys.tolist(), prominences


def detect_peaks_in_window(hr: np.ndarray, cfg: QualityConfig, start_idx: int = 5, end_idx: int = None) -> Tuple[bool, int, List[int]]:
    """
    Detect peaks in HR window (skipping initial peak region).
    
    Args:
        hr: HR array
        cfg: Config  
        start_idx: Skip first N samples (initial peak region)
        end_idx: Only check up to this index
    
    Returns: (peak_detected, count, positions)
    """
    if end_idx is not None:
        hr_window = hr[start_idx:end_idx]
    else:
        hr_window = hr[start_idx:]
    
    if len(hr_window) < 10:
        return False, 0, []
    
    peaks, _ = find_peaks(
        hr_window,
        prominence=cfg.peak_prominence,
        distance=cfg.peak_distance
    )
    
    # Adjust indices back to full array
    peaks = peaks + start_idx
    
    if len(peaks) == 0:
        return False, 0, []
    
    return True, len(peaks), peaks.tolist()


def detect_positive_runs(hr: np.ndarray) -> Tuple[int, Optional[int]]:
    """
    Find longest consecutive positive run (HR increasing).
    
    Returns: (max_run_length, start_position)
    """
    if len(hr) < 2:
        return 0, None
    
    diffs = np.diff(hr)
    max_run = 0
    max_run_start = None
    current_run = 0
    current_start = None
    
    for i, d in enumerate(diffs):
        if d > 0:  # HR increasing
            if current_run == 0:
                current_start = i
            current_run += 1
        else:
            if current_run > max_run:
                max_run = current_run
                max_run_start = current_start
            current_run = 0
    
    # Check final run
    if current_run > max_run:
        max_run = current_run
        max_run_start = current_start
    
    return max_run, max_run_start


def compute_late_window_slope(hr: np.ndarray, start_sec: int, end_sec: int) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute linear fit slope over late window (e.g., 90-120s).
    
    Returns: (slope in bpm/sec, r2 of fit)
    
    Negative slope = still recovering (good)
    Zero slope = asymptotic (fine)
    Positive slope = uptick (bad)
    """
    if len(hr) <= end_sec:
        return None, None
    
    window = hr[start_sec:end_sec + 1]
    
    if len(window) < 10:
        return None, None
    
    t = np.arange(len(window))
    
    # Linear fit
    try:
        coeffs = np.polyfit(t, window, 1)
        slope = coeffs[0]  # bpm/sec
        
        # Compute R²
        predicted = np.polyval(coeffs, t)
        ss_res = np.sum((window - predicted) ** 2)
        ss_tot = np.sum((window - np.mean(window)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        return round(slope, 4), round(r2, 3)
    except Exception:
        return None, None


def analyze_interval(conn, row: pd.Series, cfg: QualityConfig) -> IntervalQuality:
    """Compute all quality metrics for a single interval."""
    
    t, hr = load_hr_window(
        conn,
        row['session_id'],
        row['start_time'],
        row['duration_seconds']
    )
    
    # Cast to float to avoid decimal.Decimal issues
    hr = np.array([float(h) for h in hr])
    
    result = IntervalQuality(
        interval_id=row['id'],
        session_id=row['session_id'],
        start_time=row['start_time'],
        duration_sec=row['duration_seconds'],
        hr_peak=row['hr_peak'],
        hrr60=row.get('hrr60_abs'),
        hrr120=row.get('hrr120_abs'),
        r2_60=row.get('r2_60'),
        current_actionable=bool(row.get('actionable', False))
    )
    
    if len(hr) < 30:
        result.proposed_actionable = result.current_actionable
        return result
    
    # ====================
    # Gate 1: Valley detection (in full interval, scoped to HRR60 window)
    # ====================
    hrr60_end = min(cfg.hrr60_window + 5, len(hr))  # Check up to 65s
    valley_detected, valley_count, valley_pos, valley_prom = detect_valleys(hr, cfg, max_idx=hrr60_end)
    result.valley_detected = valley_detected
    result.valley_count = valley_count
    result.valley_positions = ",".join(map(str, valley_pos))
    result.valley_prominences = ",".join(f"{p:.1f}" for p in valley_prom)
    
    # Gate 1 passes if no valleys detected
    result.gate1_pass = not valley_detected
    
    # ====================
    # Gate 2: Peak detection - THE KEY GATE
    # Peak near measurement boundary (55-65s) = HARD FAIL
    # ====================
    # Check for peaks in full interval (after initial 5s)
    peak_detected, peak_count, peak_pos = detect_peaks_in_window(hr, cfg, start_idx=5, end_idx=None)
    result.peak_in_interval = peak_detected
    result.peak_count = peak_count
    result.peak_positions = ",".join(map(str, peak_pos))
    
    # Check if any peak is near the measurement boundary (55-65s = ±10% of 60s)
    BOUNDARY_LOW = 55
    BOUNDARY_HIGH = 65
    
    if peak_detected:
        # Find nearest peak to 60s
        distances_to_60 = [abs(p - 60) for p in peak_pos]
        nearest_idx = np.argmin(distances_to_60)
        nearest_peak = peak_pos[nearest_idx]
        result.nearest_peak_to_end = nearest_peak
        
        # Check if any peak is in the danger zone
        peaks_near_end = [p for p in peak_pos if BOUNDARY_LOW <= p <= BOUNDARY_HIGH]
        result.peak_near_end = len(peaks_near_end) > 0
    
    # Gate 2 passes if NO peak near measurement boundary
    result.gate2_pass = not result.peak_near_end
    
    # ====================
    # Gate 3: Positive run detection
    # ====================
    run_len, run_start = detect_positive_runs(hr[:hrr60_end])
    result.max_positive_run_sec = run_len
    result.positive_run_start = run_start
    
    # ====================
    # Gate 4: Late window slope (HRR120 quality)
    # ====================
    result.has_120s_data = len(hr) > cfg.hrr120_slope_end
    
    if result.has_120s_data:
        slope, slope_r2 = compute_late_window_slope(
            hr, 
            cfg.hrr120_slope_start, 
            cfg.hrr120_slope_end
        )
        result.late_slope = slope
        result.late_slope_r2 = slope_r2
        if slope is not None:
            result.late_window_uptick = slope > 0
    
    # ====================
    # Proposed actionable status
    # ====================
    # Must pass R² gate AND peak gate (Gate 2)
    # Valley gate (Gate 1) is informational - doesn't auto-fail
    current_r2_pass = (result.r2_60 or 0) >= cfg.min_r2_actionable
    result.proposed_actionable = current_r2_pass and result.gate2_pass
    
    # Track changes
    result.status_changed = result.current_actionable != result.proposed_actionable
    
    if result.status_changed and result.current_actionable and not result.proposed_actionable:
        reasons = []
        if result.peak_near_end:
            result.flip_reason = f"HARD_FAIL: peak_near_60s(@{result.nearest_peak_to_end}s)"
        elif not current_r2_pass:
            result.flip_reason = f"FAIL: R²={result.r2_60:.3f} < {cfg.min_r2_actionable}"
        else:
            result.flip_reason = "FAIL: unknown"
    elif result.status_changed:
        result.flip_reason = "PASS: gates cleared"
    
    return result


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='HRR Quality Explorer (Tiered)')
    parser.add_argument('--session-id', type=int, nargs='+',
                       help='Analyze only these session ID(s)')
    parser.add_argument('--output', type=str,
                       help='Output CSV path')
    parser.add_argument('--show-diffs', action='store_true',
                       help='Only show intervals where status changed')
    
    # Detection sensitivity
    parser.add_argument('--peak-prominence', type=float, default=5.0,
                       help='Peak detection sensitivity (default 5.0 bpm)')
    parser.add_argument('--valley-prominence', type=float, default=5.0,
                       help='Valley detection sensitivity (default 5.0 bpm)')
    
    args = parser.parse_args()
    
    cfg = QualityConfig(
        peak_prominence=args.peak_prominence,
        valley_prominence=args.valley_prominence,
    )
    
    print("HRR Quality Explorer (Tiered Detection)")
    print("=" * 60)
    print("Detection sensitivity:")
    print(f"  Peak prominence: {cfg.peak_prominence} bpm")
    print(f"  Valley prominence: {cfg.valley_prominence} bpm")
    print()
    print("Gates:")
    print(f"  HRR60: Valley/peak detection in 0-{cfg.hrr60_window}s")
    print(f"  HRR120: Linear slope of {cfg.hrr120_slope_start}-{cfg.hrr120_slope_end}s window")
    print()
    
    conn = get_db_connection()
    df = get_intervals(conn, args.session_id)
    print(f"Found {len(df)} intervals to analyze")
    
    if len(df) == 0:
        conn.close()
        return
    
    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i+1}/{len(df)}...")
        try:
            result = analyze_interval(conn, row, cfg)
            results.append(asdict(result))
        except Exception as e:
            print(f"  Error on interval {row['id']}: {e}")
    
    conn.close()
    results_df = pd.DataFrame(results)
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    n_current = results_df['current_actionable'].sum()
    n_proposed = results_df['proposed_actionable'].sum()
    n_changed = results_df['status_changed'].sum()
    
    print(f"Total intervals: {len(results_df)}")
    print(f"Currently actionable: {n_current}")
    print(f"Proposed actionable: {n_proposed}")
    print(f"Status changed: {n_changed} ({n_changed/len(results_df)*100:.1f}%)")
    
    # Gate stats
    print()
    print("Detection Stats:")
    print(f"  Valleys detected: {results_df['valley_detected'].sum()} ({results_df['valley_detected'].mean()*100:.1f}%)")
    print(f"  Peaks in interval: {results_df['peak_in_interval'].sum()} ({results_df['peak_in_interval'].mean()*100:.1f}%)")
    print(f"  PEAKS NEAR 60s (55-65s): {results_df['peak_near_end'].sum()} ({results_df['peak_near_end'].mean()*100:.1f}%) <- HARD FAIL")
    
    print()
    print("Gate Pass Rates:")
    print(f"  Gate 1 (no valley): {results_df['gate1_pass'].mean()*100:.1f}%")
    print(f"  Gate 2 (no peak near 60s): {results_df['gate2_pass'].mean()*100:.1f}%")
    
    # HRR120 gate stats
    has_120 = results_df[results_df['has_120s_data'] == True]
    if len(has_120) > 0:
        print()
        print(f"Late Window (90-120s) - {len(has_120)} intervals with 120s data:")
        print(f"  Late window upticks: {has_120['late_window_uptick'].sum()} ({has_120['late_window_uptick'].mean()*100:.1f}%)")
        
        slopes = has_120['late_slope'].dropna()
        if len(slopes) > 0:
            print(f"  Slope distribution: mean={slopes.mean():.4f}, min={slopes.min():.4f}, max={slopes.max():.4f} bpm/sec")
    
    # Among currently actionable - what would change?
    current_passing = results_df[results_df['current_actionable'] == True]
    if len(current_passing) > 0:
        print()
        print("Among currently actionable:")
        print(f"  Would HARD FAIL (peak near 60s): {(~current_passing['gate2_pass']).sum()}")
        print(f"  Have valleys (informational): {current_passing['valley_detected'].sum()}")
    
    # Show peaks near end details
    peaks_near = results_df[results_df['peak_near_end'] == True]
    if len(peaks_near) > 0:
        print()
        print("=" * 60)
        print(f"HARD FAIL: Peaks near 60s ({len(peaks_near)} intervals)")
        print("=" * 60)
        print(f"\n{'ID':>4} {'Sess':>4} {'HRR60':>6} {'R²':>6} {'PeakPos':>8} {'Nearest':>8}")
        print("-" * 50)
        for _, row in peaks_near.iterrows():
            hrr60 = int(row['hrr60']) if pd.notna(row['hrr60']) else 0
            r2 = row['r2_60'] if pd.notna(row['r2_60']) else 0
            print(f"{int(row['interval_id']):>4} {int(row['session_id']):>4} {hrr60:>6} "
                  f"{r2:.3f} {row['peak_positions']:>8} {row['nearest_peak_to_end'] or '-':>8}")
    
    # Show diffs
    if args.show_diffs or n_changed > 0:
        print()
        print("=" * 60)
        print("INTERVALS WITH STATUS CHANGE")
        print("=" * 60)
        
        diffs = results_df[results_df['status_changed'] == True]
        if len(diffs) > 0:
            for _, row in diffs.iterrows():
                print(f"\nInterval {row['interval_id']} (session {row['session_id']}):")
                print(f"  Duration: {row['duration_sec']}s, Peak HR: {row['hr_peak']}, HRR60: {row['hrr60']}, R²: {row['r2_60']}")
                print(f"  Valley detected: {row['valley_detected']}, @{row['valley_positions']}s")
                print(f"  Peak in interval: {row['peak_in_interval']}, @{row['peak_positions']}s")
                print(f"  Peak near 60s: {row['peak_near_end']} (nearest: {row['nearest_peak_to_end']})")
                if row['has_120s_data']:
                    print(f"  Late slope (90-120s): {row['late_slope']:.4f} bpm/sec, uptick={row['late_window_uptick']}")
                print(f"  → {row['flip_reason']}")
        else:
            print("No status changes detected.")
    
    if args.output:
        results_df.to_csv(args.output, index=False)
        print(f"\nSaved: {args.output}")
        if n_changed > 0:
            diff_path = args.output.replace('.csv', '_diffs.csv')
            diffs = results_df[results_df['status_changed'] == True]
            diffs.to_csv(diff_path, index=False)
            print(f"Saved diffs: {diff_path}")
    
    print()
    print("Next steps:")
    print("  1. Visualize flagged intervals: python scripts/hrr_qc_viz.py --session-id <id>")
    print("  2. Adjust detection sensitivity with --peak-prominence, --valley-prominence")
    print("  3. Run on full dataset to see detection rates")


if __name__ == '__main__':
    main()
