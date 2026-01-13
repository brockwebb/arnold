#!/usr/bin/env python3
"""
HRR Detection - Peak First Approach

Simple: find peaks, scan forward for nadir, compute features, gate.
Matches what the eye does.

Usage:
    python scripts/hrr_peak_first.py --session-id 31
    python scripts/hrr_peak_first.py --list
"""

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import psycopg2
from dotenv import load_dotenv
from scipy.signal import find_peaks
from scipy.ndimage import median_filter

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


@dataclass
class Config:
    # Smoothing
    smooth_kernel: int = 5
    
    # Peak detection
    peak_prominence: float = 10.0  # minimum prominence to be a peak
    peak_distance: int = 30        # minimum seconds between peaks
    
    # Recovery window
    max_recovery_sec: int = 180    # how far forward to look for nadir
    min_recovery_sec: int = 60     # minimum recovery duration
    
    # Quality gates
    min_drop: float = 9.0          # peak - nadir must exceed this
    min_peak_minus_rest: float = 8.0  # peak must be this much above pre-peak baseline


@dataclass 
class Interval:
    peak_idx: int
    nadir_idx: int
    hr_peak: float
    hr_nadir: float
    total_drop: float
    duration_sec: int
    peak_minus_rest: float
    hrr60: float = None
    hrr120: float = None
    passed: bool = False
    rejection_reason: str = None


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def load_session(conn, session_id: int):
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
        return None, None, None
    
    datetimes = [r[0] for r in rows]
    hr = np.array([r[1] for r in rows], dtype=float)
    t0 = datetimes[0]
    ts = np.array([(dt - t0).total_seconds() for dt in datetimes])
    
    return ts, hr, datetimes


def smooth(hr: np.ndarray, k: int) -> np.ndarray:
    if len(hr) < k:
        return hr.copy()
    med = median_filter(hr, size=k, mode='nearest')
    kernel = np.ones(k) / k
    return np.convolve(med, kernel, mode='same')


def detect_intervals(hr: np.ndarray, cfg: Config) -> list[Interval]:
    """
    Peak-first detection:
    1. Smooth signal
    2. Find peaks by prominence
    3. For each peak, find nadir in forward window
    4. Compute features, apply gates
    """
    
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    
    # Find peaks
    peaks, properties = find_peaks(
        hr_smooth,
        prominence=cfg.peak_prominence,
        distance=cfg.peak_distance
    )
    
    intervals = []
    
    for peak_idx in peaks:
        hr_peak = hr_smooth[peak_idx]
        
        # Forward window for nadir search
        window_end = min(len(hr_smooth), peak_idx + cfg.max_recovery_sec)
        if window_end - peak_idx < cfg.min_recovery_sec:
            continue  # not enough room for recovery
        
        # Find nadir in forward window
        window = hr_smooth[peak_idx:window_end]
        local_nadir_idx = np.argmin(window)
        nadir_idx = peak_idx + local_nadir_idx
        hr_nadir = hr_smooth[nadir_idx]
        
        # Duration and drop
        duration_sec = nadir_idx - peak_idx
        total_drop = hr_peak - hr_nadir
        
        # Pre-peak baseline (60-180s before peak)
        baseline_start = max(0, peak_idx - 180)
        baseline_end = max(0, peak_idx - 60)
        if baseline_end > baseline_start:
            baseline = np.median(hr_smooth[baseline_start:baseline_end])
        else:
            baseline = np.median(hr_smooth[max(0, peak_idx-30):peak_idx])
        
        peak_minus_rest = hr_peak - baseline
        
        # HRR at timepoints
        hrr60 = None
        hrr120 = None
        
        idx_60 = peak_idx + 60
        if idx_60 < len(hr_smooth):
            hrr60 = hr_peak - hr_smooth[idx_60]
        
        idx_120 = peak_idx + 120
        if idx_120 < len(hr_smooth):
            hrr120 = hr_peak - hr_smooth[idx_120]
        
        # Create interval
        interval = Interval(
            peak_idx=peak_idx,
            nadir_idx=nadir_idx,
            hr_peak=hr_peak,
            hr_nadir=hr_nadir,
            total_drop=total_drop,
            duration_sec=duration_sec,
            peak_minus_rest=peak_minus_rest,
            hrr60=hrr60,
            hrr120=hrr120,
        )
        
        # Apply gates
        if duration_sec < cfg.min_recovery_sec:
            interval.rejection_reason = f"dur={duration_sec}"
        elif total_drop < cfg.min_drop:
            interval.rejection_reason = f"drop={total_drop:.1f}"
        elif peak_minus_rest < cfg.min_peak_minus_rest:
            interval.rejection_reason = f"p-r={peak_minus_rest:.1f}"
        else:
            interval.passed = True
        
        intervals.append(interval)
    
    return intervals


def plot_session(session_id: int, ts: np.ndarray, hr: np.ndarray, 
                 datetimes: list, intervals: list[Interval], cfg: Config,
                 output_path: str, show: bool = True):
    
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    times_min = ts / 60
    
    valid = [i for i in intervals if i.passed]
    rejected = [i for i in intervals if not i.passed]
    has_120 = [i for i in valid if i.hrr120 is not None and i.duration_sec >= 120]
    
    fig, ax = plt.subplots(figsize=(16, 6))
    
    session_date = datetimes[0].strftime('%Y-%m-%d %H:%M')
    duration_min = ts[-1] / 60
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min)"
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    # Plot HR
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1)
    
    # Rejected (gray)
    for interval in rejected:
        start_min = ts[interval.peak_idx] / 60
        end_min = ts[interval.nadir_idx] / 60
        ax.axvspan(start_min, end_min, alpha=0.15, color='gray')
        ax.plot(start_min, interval.hr_peak, 'v', color='gray', markersize=6)
        ax.annotate(f"✗{interval.rejection_reason}", 
                   xy=(start_min, interval.hr_peak + 3),
                   fontsize=6, color='gray', ha='center')
    
    # Valid
    for i, interval in enumerate(valid):
        start_min = ts[interval.peak_idx] / 60
        end_min = ts[interval.nadir_idx] / 60
        
        # Gold for HRR120, green otherwise
        if interval in has_120:
            color, alpha = 'gold', 0.35
        else:
            color, alpha = 'green', 0.25
        
        ax.axvspan(start_min, end_min, alpha=alpha, color=color)
        ax.plot(start_min, interval.hr_peak, 'rv', markersize=8)
        ax.plot(end_min, interval.hr_nadir, 'g^', markersize=6)
        
        # Label
        if interval.hrr120 is not None and interval.duration_sec >= 120:
            hrr_str = f"HRR120={interval.hrr120:.0f}★"
        elif interval.hrr60 is not None:
            hrr_str = f"HRR60={interval.hrr60:.0f}"
        else:
            hrr_str = f"drop={interval.total_drop:.0f}"
        
        mid_min = (start_min + end_min) / 2
        ax.annotate(f"#{i+1}\n{hrr_str}\n{interval.duration_sec}s",
                   xy=(mid_min, interval.hr_peak + 5),
                   fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(min(hr_smooth) - 10, max(hr_smooth) + 25)
    ax.grid(True, alpha=0.3)
    
    # Legend
    legend_elements = [
        mpatches.Patch(facecolor='gold', alpha=0.35, label=f'HRR120 ({len(has_120)})'),
        mpatches.Patch(facecolor='green', alpha=0.25, label=f'Valid ({len(valid) - len(has_120)})'),
        mpatches.Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({len(rejected)})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    # Config
    cfg_str = f"prominence={cfg.peak_prominence}, min_drop={cfg.min_drop}, min_p-r={cfg.min_peak_minus_rest}"
    ax.text(0.01, 0.01, cfg_str, transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    plt.close()


def print_summary(intervals: list[Interval], session_id: int):
    valid = [i for i in intervals if i.passed]
    rejected = [i for i in intervals if not i.passed]
    
    print(f"\n{'='*50}")
    print(f"Session {session_id}: {len(valid)} valid, {len(rejected)} rejected")
    print(f"{'='*50}")
    
    for i, interval in enumerate(valid):
        hrr120_flag = " ★" if interval.hrr120 and interval.duration_sec >= 120 else ""
        print(f"  #{i+1}: peak={interval.hr_peak:.0f} → nadir={interval.hr_nadir:.0f} | "
              f"drop={interval.total_drop:.0f} | {interval.duration_sec}s | "
              f"HRR60={interval.hrr60:.0f if interval.hrr60 else '?'}{hrr120_flag}")


def list_sessions(conn):
    query = """
        SELECT session_id, COUNT(*), 
               MIN(sample_time),
               EXTRACT(EPOCH FROM (MAX(sample_time) - MIN(sample_time)))/60
        FROM hr_samples
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        ORDER BY MIN(sample_time) DESC
        LIMIT 15
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    
    print("\nRecent sessions:")
    for sid, samples, start, dur in rows:
        print(f"  {sid}: {start.strftime('%Y-%m-%d %H:%M')} | {dur:.0f} min")


def main():
    parser = argparse.ArgumentParser(description='HRR Peak-First Detection')
    parser.add_argument('--session-id', type=int)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--output-dir', default='/tmp')
    parser.add_argument('--no-show', action='store_true')
    
    # Config
    parser.add_argument('--prominence', type=float, default=10.0)
    parser.add_argument('--min-drop', type=float, default=9.0)
    parser.add_argument('--min-peak-rest', type=float, default=8.0)
    
    args = parser.parse_args()
    
    conn = get_db_connection()
    
    if args.list:
        list_sessions(conn)
        conn.close()
        return
    
    if not args.session_id:
        parser.error("--session-id required")
    
    cfg = Config(
        peak_prominence=args.prominence,
        min_drop=args.min_drop,
        min_peak_minus_rest=args.min_peak_rest,
    )
    
    ts, hr, dts = load_session(conn, args.session_id)
    conn.close()
    
    if hr is None:
        print(f"No data for session {args.session_id}")
        return
    
    intervals = detect_intervals(hr, cfg)
    
    output_path = f"{args.output_dir}/hrr_peakfirst_{args.session_id}.png"
    plot_session(args.session_id, ts, hr, dts, intervals, cfg, output_path, not args.no_show)
    
    print_summary(intervals, args.session_id)


if __name__ == '__main__':
    main()
