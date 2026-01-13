#!/usr/bin/env python3
"""
HRR Detection Pipeline

Single command: detect intervals, generate validation plot, print summary.
Flags intervals with HRR120 (≥120s duration) as high-value.

Usage:
    python scripts/hrr_pipeline.py --session-id 70
    python scripts/hrr_pipeline.py --session-id 70 --no-show  # just save plot
    python scripts/hrr_pipeline.py --list  # show available sessions
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class HRRDetectionConfig:
    """Configuration for non-rising-run HRR detection."""
    
    # Smoothing (median filter → moving average)
    median_kernel: int = 5
    ma_kernel: int = 5
    
    # Non-rising detection
    allowed_up_per_sec: float = 0.65  # bpm/s tolerance for "non-rising"
    min_run_duration_sec: int = 60   # minimum run length to consider
    
    # Peak backtrack
    lookback_peak_sec: int = 40  # how far back from run start to find peak
    
    # Local rest estimation (window before peak)
    rest_window_start_sec: int = 180  # start of window (seconds before peak)
    rest_window_end_sec: int = 60     # end of window (seconds before peak)
    
    # Quality gates (only 3!)
    min_total_drop: float = 9.0       # HR_peak - HR_nadir must exceed this
    min_peak_minus_rest: float = 8.0  # peak must be this much above local rest (noise floor)


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
    
    @property
    def has_hrr120(self) -> bool:
        """True if interval has valid HRR120 measurement."""
        return self.hrr120_abs is not None and self.duration_sec >= 120


# =============================================================================
# Database
# =============================================================================

def get_db_connection():
    """Get database connection from environment."""
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def load_session_hr(conn, session_id: int) -> tuple[np.ndarray, np.ndarray, list[datetime]]:
    """
    Load HR samples for a session.
    
    Returns:
        timestamps_sec: seconds since session start (float array)
        hr_values: HR values (float array)
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


def list_recent_sessions(conn, n: int = 10):
    """List recent sessions with HR data."""
    query = """
        SELECT 
            session_id,
            COUNT(*) as samples,
            MIN(sample_time) as start_time,
            EXTRACT(EPOCH FROM (MAX(sample_time) - MIN(sample_time)))/60 as duration_min
        FROM hr_samples
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        ORDER BY start_time DESC
        LIMIT %s
    """
    
    with conn.cursor() as cur:
        cur.execute(query, (n,))
        rows = cur.fetchall()
    
    print(f"\nRecent {n} sessions with HR data:")
    print("-" * 60)
    for row in rows:
        sid, samples, start, dur = row
        print(f"  Session {sid:3d}: {start.strftime('%Y-%m-%d %H:%M')} | {dur:.0f} min | {samples} samples")
    print()


# =============================================================================
# Detection
# =============================================================================

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
            in_run = True
            run_start = i
        elif not nr and in_run:
            run_end = i
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
    
    hr_end = float(hr_smooth[run_end])
    duration_sec = run_end - peak_idx
    total_drop = hr_peak - hr_nadir
    
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
    
    # Compute local_hr_rest
    rest_start = max(0, peak_idx - config.rest_window_start_sec)
    rest_end = max(0, peak_idx - config.rest_window_end_sec)
    
    if rest_end > rest_start:
        rest_window = hr_smooth[rest_start:rest_end]
        if len(rest_window) >= 10:
            interval.local_hr_rest = float(np.median(rest_window))
            interval.peak_minus_rest = hr_peak - interval.local_hr_rest
    
    # Compute HRR at specific timepoints
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
    
    if duration_sec < config.min_run_duration_sec:
        interval.gate_failures.append(f"duration={duration_sec}s")
    
    if total_drop < config.min_total_drop:
        interval.gate_failures.append(f"drop={total_drop:.1f}")
    
    if interval.peak_minus_rest is not None:
        if interval.peak_minus_rest < config.min_peak_minus_rest:
            interval.gate_failures.append(f"p-r={interval.peak_minus_rest:.1f}")
    
    interval.passed_gates = len(interval.gate_failures) == 0
    
    return interval


def detect_intervals(
    timestamps_sec: np.ndarray,
    hr_raw: np.ndarray,
    config: HRRDetectionConfig
) -> tuple[list[DetectedInterval], np.ndarray]:
    """
    Run detection on HR data.
    
    Returns:
        intervals: list of DetectedInterval
        hr_smooth: smoothed HR array
    """
    if len(hr_raw) == 0:
        return [], np.array([])
    
    hr_smooth = smooth_hr(hr_raw, config)
    runs = find_non_rising_runs(hr_smooth, config)
    
    intervals = []
    for run_start, run_end in runs:
        interval = extract_interval_features(hr_raw, hr_smooth, run_start, run_end, config)
        if interval is not None:
            intervals.append(interval)
    
    return intervals, hr_smooth


# =============================================================================
# Visualization
# =============================================================================

def plot_session(
    session_id: int,
    intervals: list[DetectedInterval],
    timestamps_sec: np.ndarray,
    hr_smooth: np.ndarray,
    datetimes: list[datetime],
    config: HRRDetectionConfig,
    output_path: str,
    show: bool = True
):
    """Plot HR trace with detected intervals."""
    
    if len(hr_smooth) == 0:
        print("No data to plot")
        return
    
    times_min = timestamps_sec / 60
    
    valid = [i for i in intervals if i.passed_gates]
    rejected = [i for i in intervals if not i.passed_gates]
    hrr120_intervals = [i for i in valid if i.has_hrr120]
    
    fig, ax = plt.subplots(figsize=(16, 6))
    
    session_date = datetimes[0].strftime('%Y-%m-%d %H:%M') if datetimes else 'Unknown'
    duration_min = timestamps_sec[-1] / 60 if len(timestamps_sec) > 0 else 0
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min)"
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    # HR trace
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1, label='Smoothed HR')
    
    # Rejected intervals (gray)
    for interval in rejected:
        start_min = timestamps_sec[interval.peak_idx] / 60
        end_min = timestamps_sec[interval.run_end_idx] / 60
        
        ax.axvspan(start_min, end_min, alpha=0.15, color='gray')
        ax.plot(start_min, interval.hr_peak, 'v', color='gray', markersize=6, alpha=0.7)
        
        if interval.gate_failures:
            short_reason = interval.gate_failures[0][:10]
            ax.annotate(f"✗{short_reason}", 
                       xy=(start_min, interval.hr_peak + 3),
                       fontsize=6, color='gray', ha='center')
    
    # Valid intervals
    for i, interval in enumerate(valid):
        start_min = timestamps_sec[interval.peak_idx] / 60
        end_min = timestamps_sec[interval.run_end_idx] / 60
        nadir_min = timestamps_sec[interval.nadir_idx] / 60
        
        # HRR120 intervals get special color (gold)
        if interval.has_hrr120:
            color = 'gold'
            alpha = 0.35
        else:
            color = 'green'
            alpha = 0.25
        
        ax.axvspan(start_min, end_min, alpha=alpha, color=color)
        
        # Peak (red triangle)
        ax.plot(start_min, interval.hr_peak, 'rv', markersize=8)
        
        # Nadir (green triangle)
        ax.plot(nadir_min, interval.hr_nadir, 'g^', markersize=6)
        
        # Annotation
        mid_min = (start_min + end_min) / 2
        
        # Build label - prioritize HRR120 if available
        if interval.has_hrr120:
            hrr_str = f"HRR120={interval.hrr120_abs:.0f}★"
        elif interval.hrr60_abs:
            hrr_str = f"HRR60={interval.hrr60_abs:.0f}"
        else:
            hrr_str = f"HRR30={interval.hrr30_abs:.0f}" if interval.hrr30_abs else "?"
        
        drop_str = f"drop={interval.total_drop:.0f}"
        dur_str = f"{interval.duration_sec}s"
        
        label = f"#{i+1}\n{hrr_str}\n{drop_str}\n{dur_str}"
        
        ax.annotate(label,
                   xy=(mid_min, interval.hr_peak + 5),
                   fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(min(hr_smooth) - 10, max(hr_smooth) + 25)
    ax.grid(True, alpha=0.3)
    
    # Legend
    legend_elements = [
        mpatches.Patch(facecolor='gold', alpha=0.35, label=f'HRR120 ({len(hrr120_intervals)})'),
        mpatches.Patch(facecolor='green', alpha=0.25, label=f'Valid ({len(valid) - len(hrr120_intervals)})'),
        mpatches.Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({len(rejected)})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
    
    # Config note
    config_str = f"allowed_up={config.allowed_up_per_sec}, min_drop={config.min_total_drop}, min_p-r={config.min_peak_minus_rest}"
    ax.text(0.01, 0.01, config_str, transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    
    plt.close()


# =============================================================================
# Summary
# =============================================================================

def print_summary(intervals: list[DetectedInterval], session_id: int):
    """Print detection summary."""
    valid = [i for i in intervals if i.passed_gates]
    rejected = [i for i in intervals if not i.passed_gates]
    hrr120 = [i for i in valid if i.has_hrr120]
    
    print(f"\n{'='*60}")
    print(f"Session {session_id} Detection Summary")
    print(f"{'='*60}")
    print(f"Total intervals detected: {len(intervals)}")
    print(f"  Valid: {len(valid)}")
    print(f"  Rejected: {len(rejected)}")
    print(f"  With HRR120: {len(hrr120)} ★")
    
    if valid:
        print(f"\nValid Intervals:")
        print("-" * 60)
        for i, interval in enumerate(valid):
            hrr120_flag = " ★" if interval.has_hrr120 else ""
            print(f"  #{i+1}: peak={interval.hr_peak:.0f} | "
                  f"drop={interval.total_drop:.0f} | "
                  f"dur={interval.duration_sec}s | "
                  f"HRR60={interval.hrr60_abs:.0f if interval.hrr60_abs else '?'}"
                  f"{hrr120_flag}")
            if interval.has_hrr120:
                print(f"       HRR120={interval.hrr120_abs:.0f}")
    
    if rejected:
        print(f"\nRejected Intervals:")
        print("-" * 60)
        for i, interval in enumerate(rejected):
            print(f"  #{i+1}: peak={interval.hr_peak:.0f} | "
                  f"gates: {', '.join(interval.gate_failures)}")
    
    # Aggregate stats for valid intervals
    if valid:
        hrr60_vals = [i.hrr60_abs for i in valid if i.hrr60_abs]
        if hrr60_vals:
            print(f"\nHRR60 Stats (n={len(hrr60_vals)}):")
            print(f"  Mean: {np.mean(hrr60_vals):.1f}")
            print(f"  Median: {np.median(hrr60_vals):.1f}")
            print(f"  Range: {min(hrr60_vals):.0f} - {max(hrr60_vals):.0f}")
        
        if hrr120:
            hrr120_vals = [i.hrr120_abs for i in hrr120]
            print(f"\nHRR120 Stats (n={len(hrr120_vals)}):")
            print(f"  Mean: {np.mean(hrr120_vals):.1f}")
            print(f"  Median: {np.median(hrr120_vals):.1f}")
            print(f"  Range: {min(hrr120_vals):.0f} - {max(hrr120_vals):.0f}")
    
    print()


# =============================================================================
# Main Pipeline
# =============================================================================

def run_pipeline(
    session_id: int,
    config: HRRDetectionConfig,
    output_dir: str = "/tmp",
    show: bool = True
):
    """
    Full pipeline: load → detect → plot → summarize.
    """
    conn = get_db_connection()
    
    try:
        # Load
        print(f"Loading session {session_id}...")
        timestamps_sec, hr_raw, datetimes = load_session_hr(conn, session_id)
        
        if len(hr_raw) == 0:
            print(f"No HR data for session {session_id}")
            return
        
        print(f"  {len(hr_raw)} samples, {timestamps_sec[-1]/60:.1f} min")
        
        # Detect
        print("Detecting intervals...")
        intervals, hr_smooth = detect_intervals(timestamps_sec, hr_raw, config)
        
        # Plot
        output_path = f"{output_dir}/hrr_session_{session_id}.png"
        plot_session(session_id, intervals, timestamps_sec, hr_smooth, datetimes, config, output_path, show)
        
        # Summary
        print_summary(intervals, session_id)
        
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='HRR Detection Pipeline')
    parser.add_argument('--session-id', type=int, help='Session ID to analyze')
    parser.add_argument('--list', action='store_true', help='List recent sessions')
    parser.add_argument('--output-dir', type=str, default='/tmp', help='Output directory for plots')
    parser.add_argument('--no-show', action='store_true', help='Do not display plot')
    
    # Config overrides
    parser.add_argument('--allowed-up', type=float, default=0.65)
    parser.add_argument('--smooth', type=int, default=5, help='Smoothing kernel size (median and MA)')
    parser.add_argument('--min-drop', type=float, default=9.0)
    parser.add_argument('--min-peak-rest', type=float, default=8.0)
    
    args = parser.parse_args()
    
    if args.list:
        conn = get_db_connection()
        list_recent_sessions(conn)
        conn.close()
        return
    
    if not args.session_id:
        parser.error("--session-id required (or use --list)")
    
    config = HRRDetectionConfig(
        allowed_up_per_sec=args.allowed_up,
        median_kernel=args.smooth,
        ma_kernel=args.smooth,
        min_total_drop=args.min_drop,
        min_peak_minus_rest=args.min_peak_rest,
    )
    
    run_pipeline(args.session_id, config, args.output_dir, not args.no_show)


if __name__ == '__main__':
    main()
