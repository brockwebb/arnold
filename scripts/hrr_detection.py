#!/usr/bin/env python3
"""
HRR Detection via Non-Rising Runs

Simplified approach: detect contiguous periods where HR is not rising,
backtrack to find peak, apply three quality gates.

This replaces the complex onset detection and 7-gate approach that failed.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


@dataclass
class HRRDetectionConfig:
    """Configuration for non-rising-run HRR detection."""
    
    # Smoothing (median filter → moving average)
    median_kernel: int = 3
    ma_kernel: int = 3
    
    # Non-rising detection
    allowed_up_per_sec: float = 0.2  # bpm/s tolerance for "non-rising"
    min_run_duration_sec: int = 60   # minimum run length to consider
    
    # Peak backtrack
    lookback_peak_sec: int = 20  # how far back from run start to find peak
    
    # Local rest estimation (window before peak)
    rest_window_start_sec: int = 180  # start of window (seconds before peak)
    rest_window_end_sec: int = 60     # end of window (seconds before peak)
    
    # Quality gates (only 3!)
    min_total_drop: float = 5.0       # HR_peak - HR_end must exceed this
    min_peak_minus_rest: float = 20.0  # peak must be this much above local rest


@dataclass
class DetectedInterval:
    """A detected recovery interval with computed features."""
    
    # Indices into the HR array
    run_start_idx: int
    run_end_idx: int
    peak_idx: int
    
    # Core values
    hr_peak: float
    hr_end: float  # HR at run end
    hr_nadir: float  # minimum HR during run
    nadir_idx: int
    
    # Computed metrics
    total_drop: float  # hr_peak - hr_nadir
    duration_sec: int
    
    # Local rest estimation
    local_hr_rest: Optional[float] = None
    peak_minus_rest: Optional[float] = None
    
    # HRR at specific timepoints (from peak)
    hr_30s: Optional[float] = None
    hr_60s: Optional[float] = None
    hr_120s: Optional[float] = None
    hrr30_abs: Optional[float] = None
    hrr60_abs: Optional[float] = None
    hrr120_abs: Optional[float] = None
    
    # Quality flags
    passed_gates: bool = False
    gate_failures: list = field(default_factory=list)


def get_db_connection():
    """Get database connection from environment."""
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def load_session_hr(conn, session_id: int) -> tuple[np.ndarray, np.ndarray, list[datetime]]:
    """
    Load HR samples for a session.
    
    Returns:
        timestamps_sec: seconds since session start (float array)
        hr_values: HR values (int array)
        datetimes: actual datetime objects for each sample
    """
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
        return np.array([]), np.array([]), []
    
    datetimes = [row[0] for row in rows]
    hr_values = np.array([row[1] for row in rows], dtype=float)
    
    t0 = datetimes[0]
    timestamps_sec = np.array([(dt - t0).total_seconds() for dt in datetimes])
    
    return timestamps_sec, hr_values, datetimes


def smooth_hr(hr: np.ndarray, config: HRRDetectionConfig) -> np.ndarray:
    """Apply median filter then moving average."""
    if len(hr) < config.median_kernel:
        return hr.copy()
    
    # Median filter
    med = median_filter(hr, size=config.median_kernel, mode='nearest')
    
    # Moving average
    kernel = np.ones(config.ma_kernel) / config.ma_kernel
    ma = np.convolve(med, kernel, mode='same')
    
    return ma


def find_non_rising_runs(hr_smooth: np.ndarray, config: HRRDetectionConfig) -> list[tuple[int, int]]:
    """
    Find contiguous runs where HR is non-rising for >= min_duration.
    
    Returns:
        List of (start_idx, end_idx) tuples
    """
    if len(hr_smooth) < 2:
        return []
    
    # Compute per-second diff
    diff = np.diff(hr_smooth)
    
    # Mark non-rising (including small allowed upticks)
    non_rising = diff <= config.allowed_up_per_sec
    
    # Find contiguous runs
    runs = []
    in_run = False
    run_start = 0
    
    for i, nr in enumerate(non_rising):
        if nr and not in_run:
            # Start of a new run
            in_run = True
            run_start = i
        elif not nr and in_run:
            # End of run (i is the index in diff, which corresponds to hr[i+1])
            run_end = i  # last non-rising diff was at i-1, so run covers hr[run_start:i+1]
            if run_end - run_start >= config.min_run_duration_sec:
                runs.append((run_start, run_end))
            in_run = False
    
    # Handle run that extends to end
    if in_run:
        run_end = len(non_rising)
        if run_end - run_start >= config.min_run_duration_sec:
            runs.append((run_start, run_end))
    
    return runs


def extract_interval_features(
    hr_raw: np.ndarray,
    hr_smooth: np.ndarray,
    run_start: int,
    run_end: int,
    config: HRRDetectionConfig
) -> Optional[DetectedInterval]:
    """
    Extract features for a detected run.
    
    - Backtrack from run_start to find peak
    - Compute local_hr_rest from window before peak
    - Apply quality gates
    - Compute HRR at 30/60/120s
    """
    
    # Backtrack to find peak
    lookback_start = max(0, run_start - config.lookback_peak_sec)
    peak_search_region = hr_smooth[lookback_start:run_start + 1]
    
    if len(peak_search_region) == 0:
        return None
    
    local_peak_idx = np.argmax(peak_search_region)
    peak_idx = lookback_start + local_peak_idx
    hr_peak = float(hr_smooth[peak_idx])
    
    # Find nadir within run
    run_region = hr_smooth[run_start:run_end + 1]
    local_nadir_idx = np.argmin(run_region)
    nadir_idx = run_start + local_nadir_idx
    hr_nadir = float(hr_smooth[nadir_idx])
    
    # HR at run end
    hr_end = float(hr_smooth[run_end])
    
    # Duration (from peak to run end)
    duration_sec = run_end - peak_idx
    
    # Total drop
    total_drop = hr_peak - hr_nadir
    
    # Create interval object
    interval = DetectedInterval(
        run_start_idx=run_start,
        run_end_idx=run_end,
        peak_idx=peak_idx,
        hr_peak=hr_peak,
        hr_end=hr_end,
        hr_nadir=hr_nadir,
        nadir_idx=nadir_idx,
        total_drop=total_drop,
        duration_sec=duration_sec,
    )
    
    # Compute local_hr_rest (median in window before peak)
    rest_start = max(0, peak_idx - config.rest_window_start_sec)
    rest_end = max(0, peak_idx - config.rest_window_end_sec)
    
    if rest_end > rest_start:
        rest_window = hr_smooth[rest_start:rest_end]
        if len(rest_window) >= 10:  # need reasonable sample
            interval.local_hr_rest = float(np.median(rest_window))
            interval.peak_minus_rest = hr_peak - interval.local_hr_rest
    
    # Compute HRR at specific timepoints (from peak_idx)
    def hr_at_offset(offset_sec: int) -> Optional[float]:
        idx = peak_idx + offset_sec
        if 0 <= idx < len(hr_smooth):
            return float(hr_smooth[idx])
        return None
    
    interval.hr_30s = hr_at_offset(30)
    interval.hr_60s = hr_at_offset(60)
    interval.hr_120s = hr_at_offset(120)
    
    if interval.hr_30s is not None:
        interval.hrr30_abs = hr_peak - interval.hr_30s
    if interval.hr_60s is not None:
        interval.hrr60_abs = hr_peak - interval.hr_60s
    if interval.hr_120s is not None:
        interval.hrr120_abs = hr_peak - interval.hr_120s
    
    # Apply quality gates
    interval.gate_failures = []
    
    # Gate 1: Duration (already enforced by find_non_rising_runs, but check from peak)
    if duration_sec < config.min_run_duration_sec:
        interval.gate_failures.append(f"duration={duration_sec}s < {config.min_run_duration_sec}s")
    
    # Gate 2: Total drop
    if total_drop < config.min_total_drop:
        interval.gate_failures.append(f"total_drop={total_drop:.1f} < {config.min_total_drop}")
    
    # Gate 3: Peak minus rest (only if we could compute it)
    if interval.peak_minus_rest is not None:
        if interval.peak_minus_rest < config.min_peak_minus_rest:
            interval.gate_failures.append(
                f"peak_minus_rest={interval.peak_minus_rest:.1f} < {config.min_peak_minus_rest}"
            )
    # If we couldn't compute peak_minus_rest (not enough data before peak), skip gate
    
    interval.passed_gates = len(interval.gate_failures) == 0
    
    return interval


def detect_recovery_intervals(
    session_id: int,
    config: Optional[HRRDetectionConfig] = None,
    conn=None
) -> tuple[list[DetectedInterval], np.ndarray, np.ndarray, list[datetime]]:
    """
    Main detection function.
    
    Returns:
        intervals: list of DetectedInterval objects
        timestamps_sec: time array
        hr_smooth: smoothed HR array
        datetimes: datetime objects
    """
    if config is None:
        config = HRRDetectionConfig()
    
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    try:
        # Load data
        timestamps_sec, hr_raw, datetimes = load_session_hr(conn, session_id)
        
        if len(hr_raw) == 0:
            return [], np.array([]), np.array([]), []
        
        # Smooth
        hr_smooth = smooth_hr(hr_raw, config)
        
        # Find non-rising runs
        runs = find_non_rising_runs(hr_smooth, config)
        
        # Extract features for each run
        intervals = []
        for run_start, run_end in runs:
            interval = extract_interval_features(hr_raw, hr_smooth, run_start, run_end, config)
            if interval is not None:
                intervals.append(interval)
        
        return intervals, timestamps_sec, hr_smooth, datetimes
    
    finally:
        if close_conn:
            conn.close()


def summarize_intervals(intervals: list[DetectedInterval]) -> dict:
    """Produce summary statistics for detected intervals."""
    valid = [i for i in intervals if i.passed_gates]
    rejected = [i for i in intervals if not i.passed_gates]
    
    summary = {
        'total_detected': len(intervals),
        'valid': len(valid),
        'rejected': len(rejected),
        'valid_intervals': valid,
        'rejected_intervals': rejected,
    }
    
    if valid:
        hrr60_values = [i.hrr60_abs for i in valid if i.hrr60_abs is not None]
        if hrr60_values:
            summary['hrr60_mean'] = np.mean(hrr60_values)
            summary['hrr60_median'] = np.median(hrr60_values)
            summary['hrr60_std'] = np.std(hrr60_values)
    
    return summary


if __name__ == '__main__':
    # Quick test
    import argparse
    
    parser = argparse.ArgumentParser(description='Test HRR detection')
    parser.add_argument('--session-id', type=int, required=True)
    args = parser.parse_args()
    
    config = HRRDetectionConfig()
    intervals, ts, hr, dts = detect_recovery_intervals(args.session_id, config)
    
    print(f"\nSession {args.session_id}")
    print(f"Duration: {ts[-1]/60:.1f} min, {len(hr)} samples")
    print(f"Detected {len(intervals)} intervals")
    
    for i, interval in enumerate(intervals):
        status = "✓" if interval.passed_gates else "✗"
        print(f"\n  {status} Interval {i+1}:")
        print(f"    Peak idx: {interval.peak_idx}, HR: {interval.hr_peak:.0f}")
        print(f"    Duration: {interval.duration_sec}s")
        print(f"    Total drop: {interval.total_drop:.1f}")
        print(f"    HRR60: {interval.hrr60_abs}")
        if interval.peak_minus_rest:
            print(f"    Peak-rest: {interval.peak_minus_rest:.1f}")
        if interval.gate_failures:
            print(f"    Gate failures: {interval.gate_failures}")
    
    summary = summarize_intervals(intervals)
    print(f"\nSummary: {summary['valid']} valid, {summary['rejected']} rejected")
