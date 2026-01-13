#!/usr/bin/env python3
"""
HRR Detection - Sliding Window Cumulative Drop

Algorithm (per user spec):
1. At each second, check: can we slide 60s forward with HR staying negative?
2. Track cumulative "uptick budget" - allow +3 bpm total for 60s window
3. If 60s passes, continue to 120s with +5 bpm budget over 10s max
4. Record peak (start), nadir (lowest point), compute HRR

Simple. No overthinking.
"""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


@dataclass
class Config:
    smooth_kernel: int = 5
    
    # Initial descent gate
    initial_descent_sec: int = 7      # first N seconds must be negative
    
    # 60s window
    window_60s: int = 60
    uptick_budget_60s: float = 3.0  # max cumulative uptick allowed
    
    # 120s extension
    window_120s: int = 120
    uptick_budget_120s: float = 5.0  # additional budget for 60-120s
    uptick_window_120s: int = 10     # uptick must recover within this many seconds
    
    # Quality gates
    min_drop: float = 9.0
    min_peak_minus_rest: float = 8.0


@dataclass
class Interval:
    start_idx: int      # peak
    end_idx: int        # where recovery ends (60s or 120s)
    nadir_idx: int      # lowest point
    hr_peak: float
    hr_nadir: float
    hr_end: float
    total_drop: float
    duration_sec: int
    peak_minus_rest: float
    hrr60: float = None
    hrr120: float = None
    has_120: bool = False
    passed: bool = True
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


def check_60s_window(hr: np.ndarray, start: int, cfg: Config) -> tuple[bool, int]:
    """
    Check if 60s window from start is valid recovery.
    Returns (passed, nadir_idx).
    
    Rules:
    - First N seconds MUST be negative (no upticks) - ensures we're at peak
    - Then track cumulative uptick budget
    - If cumulative uptick exceeds budget, fail
    """
    end = start + cfg.window_60s
    if end >= len(hr):
        return False, start
    
    # Gate 1: First N seconds must be strictly descending
    for i in range(start, start + cfg.initial_descent_sec):
        if i + 1 >= len(hr):
            return False, start
        step = hr[i + 1] - hr[i]
        if step > 0:  # any uptick in initial descent = not at peak
            return False, start
    
    # Gate 2: Rest of window with uptick budget
    cumulative_uptick = 0.0
    nadir_idx = start
    nadir_val = hr[start]
    
    for i in range(start + cfg.initial_descent_sec, end):
        step = hr[i + 1] - hr[i]
        
        if step > 0:
            cumulative_uptick += step
            if cumulative_uptick > cfg.uptick_budget_60s:
                return False, nadir_idx
        else:
            # Going down - decay the uptick accumulator
            cumulative_uptick = max(0, cumulative_uptick + step)
        
        # Track nadir
        if hr[i + 1] < nadir_val:
            nadir_val = hr[i + 1]
            nadir_idx = i + 1
    
    # Also check initial descent period for nadir
    for i in range(start, start + cfg.initial_descent_sec + 1):
        if hr[i] < nadir_val:
            nadir_val = hr[i]
            nadir_idx = i
    
    return True, nadir_idx


def check_120s_extension(hr: np.ndarray, start: int, cfg: Config) -> tuple[bool, int]:
    """
    Check if we can extend from 60s to 120s.
    
    Rules:
    - Continue from 60s mark
    - Allow +5 bpm uptick but must recover within 10s
    """
    start_120 = start + cfg.window_60s
    end_120 = start + cfg.window_120s
    
    if end_120 >= len(hr):
        return False, start_120
    
    nadir_idx = start_120
    nadir_val = hr[start_120]
    
    uptick_start = None
    uptick_amount = 0.0
    
    for i in range(start_120, end_120):
        step = hr[i + 1] - hr[i]
        
        if step > 0:
            if uptick_start is None:
                uptick_start = i
                uptick_amount = step
            else:
                uptick_amount += step
                
                # Check if we've exceeded budget
                if uptick_amount > cfg.uptick_budget_120s:
                    return False, nadir_idx
                
                # Check if we've exceeded time window
                if (i - uptick_start) > cfg.uptick_window_120s:
                    return False, nadir_idx
        else:
            # Going down - reset uptick tracking
            uptick_start = None
            uptick_amount = 0.0
        
        # Track nadir
        if hr[i + 1] < nadir_val:
            nadir_val = hr[i + 1]
            nadir_idx = i + 1
    
    return True, nadir_idx


def detect_intervals(hr: np.ndarray, cfg: Config) -> list[Interval]:
    """
    Slide through signal, find valid 60s (and optionally 120s) recovery windows.
    """
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    
    intervals = []
    i = 0
    
    while i < len(hr_smooth) - cfg.window_60s:
        # Check 60s window
        passed_60, nadir_idx = check_60s_window(hr_smooth, i, cfg)
        
        if not passed_60:
            i += 1
            continue
        
        # Found valid 60s window starting at i
        hr_peak = hr_smooth[i]
        hr_nadir = hr_smooth[nadir_idx]
        total_drop = hr_peak - hr_nadir
        
        # Check 120s extension
        has_120 = False
        final_nadir_idx = nadir_idx
        
        passed_120, nadir_idx_120 = check_120s_extension(hr_smooth, i, cfg)
        if passed_120:
            has_120 = True
            if hr_smooth[nadir_idx_120] < hr_smooth[final_nadir_idx]:
                final_nadir_idx = nadir_idx_120
        
        # Compute end index
        if has_120:
            end_idx = i + cfg.window_120s
        else:
            end_idx = i + cfg.window_60s
        
        duration_sec = end_idx - i
        hr_end = hr_smooth[min(end_idx, len(hr_smooth) - 1)]
        hr_nadir = hr_smooth[final_nadir_idx]
        total_drop = hr_peak - hr_nadir
        
        # Pre-peak baseline
        baseline_start = max(0, i - 180)
        baseline_end = max(0, i - 60)
        if baseline_end > baseline_start:
            baseline = np.median(hr_smooth[baseline_start:baseline_end])
        else:
            baseline = np.median(hr_smooth[max(0, i - 30):i]) if i > 30 else hr_peak
        
        peak_minus_rest = hr_peak - baseline
        
        # HRR values
        hrr60 = None
        hrr120 = None
        
        idx_60 = i + 60
        if idx_60 < len(hr_smooth):
            hrr60 = hr_peak - hr_smooth[idx_60]
        
        if has_120:
            idx_120 = i + 120
            if idx_120 < len(hr_smooth):
                hrr120 = hr_peak - hr_smooth[idx_120]
        
        # Create interval
        interval = Interval(
            start_idx=i,
            end_idx=end_idx,
            nadir_idx=final_nadir_idx,
            hr_peak=hr_peak,
            hr_nadir=hr_nadir,
            hr_end=hr_end,
            total_drop=total_drop,
            duration_sec=duration_sec,
            peak_minus_rest=peak_minus_rest,
            hrr60=hrr60,
            hrr120=hrr120,
            has_120=has_120,
        )
        
        # Quality gates
        if total_drop < cfg.min_drop:
            interval.passed = False
            interval.rejection_reason = f"drop={total_drop:.1f}"
        elif peak_minus_rest < cfg.min_peak_minus_rest:
            interval.passed = False
            interval.rejection_reason = f"p-r={peak_minus_rest:.1f}"
        
        intervals.append(interval)
        
        # Skip past this interval to avoid overlaps
        i = end_idx + 1
    
    return intervals


def plot_session(session_id: int, ts: np.ndarray, hr: np.ndarray,
                 datetimes: list, intervals: list[Interval], cfg: Config,
                 output_path: str, show: bool = True):
    
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    times_min = ts / 60
    
    valid = [iv for iv in intervals if iv.passed]
    rejected = [iv for iv in intervals if not iv.passed]
    has_120 = [iv for iv in valid if iv.has_120]
    
    fig, ax = plt.subplots(figsize=(16, 6))
    
    session_date = datetimes[0].strftime('%Y-%m-%d %H:%M')
    duration_min = ts[-1] / 60
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min)"
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1)
    
    # Rejected
    for iv in rejected:
        start_min = ts[iv.start_idx] / 60
        end_min = ts[iv.end_idx] / 60 if iv.end_idx < len(ts) else times_min[-1]
        ax.axvspan(start_min, end_min, alpha=0.15, color='gray')
        ax.plot(start_min, iv.hr_peak, 'v', color='gray', markersize=6)
        ax.annotate(f"✗{iv.rejection_reason}", xy=(start_min, iv.hr_peak + 3),
                   fontsize=6, color='gray', ha='center')
    
    # Valid
    for n, iv in enumerate(valid):
        start_min = ts[iv.start_idx] / 60
        end_min = ts[iv.end_idx] / 60 if iv.end_idx < len(ts) else times_min[-1]
        nadir_min = ts[iv.nadir_idx] / 60
        
        color = 'gold' if iv.has_120 else 'green'
        alpha = 0.35 if iv.has_120 else 0.25
        
        ax.axvspan(start_min, end_min, alpha=alpha, color=color)
        ax.plot(start_min, iv.hr_peak, 'rv', markersize=8)
        ax.plot(nadir_min, iv.hr_nadir, 'g^', markersize=6)
        
        # Label
        if iv.has_120 and iv.hrr120:
            label = f"HRR120={iv.hrr120:.0f}★"
        elif iv.hrr60:
            label = f"HRR60={iv.hrr60:.0f}"
        else:
            label = f"drop={iv.total_drop:.0f}"
        
        mid_min = (start_min + end_min) / 2
        ax.annotate(f"#{n+1}\n{label}\n{iv.duration_sec}s",
                   xy=(mid_min, iv.hr_peak + 5), fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(min(hr_smooth) - 10, max(hr_smooth) + 25)
    ax.grid(True, alpha=0.3)
    
    legend_elements = [
        mpatches.Patch(facecolor='gold', alpha=0.35, label=f'HRR120 ({len(has_120)})'),
        mpatches.Patch(facecolor='green', alpha=0.25, label=f'Valid ({len(valid) - len(has_120)})'),
        mpatches.Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({len(rejected)})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    cfg_str = f"init_descent={cfg.initial_descent_sec}s, uptick_60={cfg.uptick_budget_60s}, min_drop={cfg.min_drop}"
    ax.text(0.01, 0.01, cfg_str, transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    plt.close()


def print_summary(intervals: list[Interval], session_id: int):
    valid = [iv for iv in intervals if iv.passed]
    rejected = [iv for iv in intervals if not iv.passed]
    
    print(f"\n{'='*60}")
    print(f"Session {session_id}: {len(valid)} valid, {len(rejected)} rejected")
    print('='*60)
    
    for n, iv in enumerate(valid):
        flag = " ★" if iv.has_120 else ""
        hrr_str = f"HRR60={iv.hrr60:.0f}" if iv.hrr60 else "?"
        if iv.has_120 and iv.hrr120:
            hrr_str = f"HRR120={iv.hrr120:.0f}"
        print(f"  #{n+1}: {iv.hr_peak:.0f}→{iv.hr_nadir:.0f} | drop={iv.total_drop:.0f} | "
              f"{iv.duration_sec}s | {hrr_str}{flag}")


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
    parser = argparse.ArgumentParser(description='HRR Sliding Window Detection')
    parser.add_argument('--session-id', type=int)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--output-dir', default='/tmp')
    parser.add_argument('--no-show', action='store_true')
    
    parser.add_argument('--initial-descent', type=int, default=7)
    parser.add_argument('--uptick-60', type=float, default=3.0)
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
        initial_descent_sec=args.initial_descent,
        uptick_budget_60s=args.uptick_60,
        min_drop=args.min_drop,
        min_peak_minus_rest=args.min_peak_rest,
    )
    
    ts, hr, dts = load_session(conn, args.session_id)
    conn.close()
    
    if hr is None:
        print(f"No data for session {args.session_id}")
        return
    
    intervals = detect_intervals(hr, cfg)
    
    output_path = f"{args.output_dir}/hrr_sliding_{args.session_id}.png"
    plot_session(args.session_id, ts, hr, dts, intervals, cfg, output_path, not args.no_show)
    
    print_summary(intervals, args.session_id)


if __name__ == '__main__':
    main()
