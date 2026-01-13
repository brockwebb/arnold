#!/usr/bin/env python3
"""
HRR Detection - Sliding Window v2

Algorithm:
0a. Peak must be higher than preceding lookback avg (confirms it's a real peak)
0b. t=0 must be max in lookahead window (catch double-peaks)
1. First 7s must be mostly negative (allow small uptick for wobble)
2. Check FIXED 60s window:
   - Can't exceed running nadir by > max_rise_60 bpm
   - Can't stay above nadir for > plateau_sec consecutive seconds
3. If 60s passes, check extension to FIXED 120s:
   - Can't exceed running nadir by > max_rise_120 bpm
   - Same plateau rule
4. Report 60s or 120s intervals only - no variable lengths
5. Resume search from end of interval

Key CLI parameters:
  --max-rise-60    Max rise above nadir during 0-60s (default: 3.0)
  --max-rise-120   Max rise above nadir during 61-120s (default: 5.0)
  --peak-lookahead Seconds ahead to check for double-peaks (default: 15)
  --plateau-sec    End if HR stays above nadir this long (default: 15)
  --debug-range    Debug specific time ranges, e.g. "12-15,74-77"
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
    # Smoothing
    smooth_kernel: int = 5
    
    # Peak validation
    initial_descent_sec: int = 7     # first N seconds must be mostly negative
    initial_uptick_tolerance: float = 1.0  # allow this much total uptick in initial descent
    lookback_sec: int = 15           # peak must be higher than avg of this window before
    min_rise_before_peak: float = 5.0  # peak must be at least this much above lookback avg
    peak_lookahead_sec: int = 15     # look this far ahead to catch double-peaks
    
    # Tolerance for rise above running nadir (999 = effectively disabled)
    max_rise_60: float = 999.0       # max rise above nadir during 0-60s
    max_rise_120: float = 999.0      # max rise above nadir during 61-120s
    plateau_sec: int = 999           # end if HR stays above nadir this long
    
    # Quality gates
    min_drop: float = 9.0
    min_peak_minus_rest: float = 8.0


@dataclass
class Interval:
    start_idx: int      # peak
    end_idx: int        # where descent ended
    nadir_idx: int      # lowest point
    hr_peak: float
    hr_nadir: float
    total_drop: float
    duration_sec: int
    peak_minus_rest: float
    hrr60: float = None
    hrr120: float = None
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
    """Basic smoothing: median filter + moving average."""
    if len(hr) < k:
        return hr.copy()
    med = median_filter(hr, size=k, mode='nearest')
    kernel = np.ones(k) / k
    return np.convolve(med, kernel, mode='same')


def compute_blunted_slope(hr: np.ndarray) -> np.ndarray:
    """
    4-point blunted slope at each point.
    slope[t] = avg(hr[t-2], hr[t-1], hr[t], hr[t+1]) - avg(hr[t-3], hr[t-2], hr[t-1], hr[t])
    
    Smooths out single-sample noise in slope calculation.
    """
    n = len(hr)
    slope = np.zeros(n)
    
    for t in range(3, n - 1):
        avg_current = (hr[t-2] + hr[t-1] + hr[t] + hr[t+1]) / 4
        avg_prev = (hr[t-3] + hr[t-2] + hr[t-1] + hr[t]) / 4
        slope[t] = avg_current - avg_prev
    
    return slope


def find_interval_from(hr: np.ndarray, start: int, cfg: Config, debug: bool = False) -> tuple[bool, int, int, bool]:
    """
    Try to find a valid HRR interval starting at 'start'.
    
    Returns: (found, end_idx, nadir_idx, is_120)
    
    Rules:
    0a. Peak must be higher than preceding lookback window (it's actually a peak)
    0b. t=0 must be max in lookahead window (catch double-peaks)
    1. First 7s must be mostly negative (allow small uptick)
    2. Check FULL 60s: can't exceed nadir by > cfg.max_rise_60, can't plateau > cfg.plateau_sec
    3. If 60s passes, check 61-120s: can't exceed nadir by > cfg.max_rise_120, same plateau rule
    4. Return either 60s or 120s - no variable lengths
    """
    n = len(hr)
    
    # Not enough room for 60s
    if start + 60 >= n:
        return False, start, start, False
    
    # Gate 0a: Is this actually a peak? Must be higher than preceding window
    lookback_start = max(0, start - cfg.lookback_sec)
    if lookback_start < start:
        lookback_avg = np.mean(hr[lookback_start:start])
        if hr[start] - lookback_avg < cfg.min_rise_before_peak:
            if debug:
                print(f"    t={start} ({start/60:.1f}m): FAIL 0a - hr={hr[start]:.1f}, lookback={lookback_avg:.1f}, diff={hr[start]-lookback_avg:.1f}")
            return False, start, start, False
    
    # Gate 0b: t=0 must be max in a wider window (catch double-peaks)
    check_end = min(n, start + cfg.peak_lookahead_sec)
    window_max = np.max(hr[start:check_end])
    if window_max > hr[start] + 0.5:
        if debug:
            print(f"    t={start} ({start/60:.1f}m): FAIL 0b - hr={hr[start]:.1f}, window_max={window_max:.1f} (in {cfg.peak_lookahead_sec}s)")
        return False, start, start, False
    
    if debug:
        print(f"    t={start} ({start/60:.1f}m): PASS 0a,0b - hr={hr[start]:.1f}")
    
    # Gate 1: First N seconds must be mostly negative (allow small uptick budget)
    cumulative_uptick = 0.0
    for t in range(start, start + cfg.initial_descent_sec):
        if t + 1 >= n:
            return False, start, start, False
        step = hr[t + 1] - hr[t]
        if step > 0:
            cumulative_uptick += step
            if cumulative_uptick > cfg.initial_uptick_tolerance:
                if debug:
                    print(f"    t={start} ({start/60:.1f}m): FAIL G1 - uptick={cumulative_uptick:.1f} at t+{t-start}")
                return False, start, start, False
    
    if debug:
        print(f"    t={start} ({start/60:.1f}m): PASS G1")
    
    # Track running nadir through the interval
    running_nadir = hr[start]
    nadir_idx = start
    
    # Update nadir for initial descent
    for t in range(start, start + cfg.initial_descent_sec + 1):
        if hr[t] < running_nadir:
            running_nadir = hr[t]
            nadir_idx = t
    
    # Gate 2: Check FULL 60s window with configurable tolerance
    # Also: if HR stays above nadir for too long, end (plateau = still working)
    seconds_above_nadir = 0
    for t in range(start + cfg.initial_descent_sec, start + 60):
        if t >= n:
            return False, start, start, False
        
        if hr[t] < running_nadir:
            running_nadir = hr[t]
            nadir_idx = t
            seconds_above_nadir = 0  # reset counter
        else:
            seconds_above_nadir += 1
            if seconds_above_nadir > cfg.plateau_sec:
                if debug:
                    print(f"    t={start} ({start/60:.1f}m): FAIL G2 plateau at t+{t-start} - {seconds_above_nadir}s above nadir")
                return False, start, start, False
        
        rise = hr[t] - running_nadir
        if rise > cfg.max_rise_60:
            if debug:
                print(f"    t={start} ({start/60:.1f}m): FAIL G2 at t+{t-start} - hr={hr[t]:.1f}, nadir={running_nadir:.1f}, rise={rise:.1f} > {cfg.max_rise_60}")
            return False, start, start, False
    
    if debug:
        print(f"    t={start} ({start/60:.1f}m): PASS G2 (60s) - nadir={running_nadir:.1f}")
    
    # 60s passed! Now check if we can extend to 120s
    if start + 120 >= n:
        # Not enough room for 120s, return 60s
        return True, start + 60, nadir_idx, False
    
    # Gate 3: Check 61-120s with more relaxed tolerance
    nadir_at_60 = running_nadir
    nadir_idx_at_60 = nadir_idx
    seconds_above_nadir = 0  # reset for second half
    
    for t in range(start + 60, start + 120):
        if t >= n:
            # Ran out of data, return 60s
            return True, start + 60, nadir_idx_at_60, False
        
        if hr[t] < running_nadir:
            running_nadir = hr[t]
            nadir_idx = t
            seconds_above_nadir = 0
        else:
            seconds_above_nadir += 1
            if seconds_above_nadir > cfg.plateau_sec:
                if debug:
                    print(f"    t={start} ({start/60:.1f}m): FAIL G3 plateau at t+{t-start} - returning 60s")
                return True, start + 60, nadir_idx_at_60, False
        
        rise = hr[t] - running_nadir
        if rise > cfg.max_rise_120:
            # Failed 120s check, return 60s
            if debug:
                print(f"    t={start} ({start/60:.1f}m): FAIL G3 at t+{t-start} - rise={rise:.1f} > {cfg.max_rise_120} - returning 60s")
            return True, start + 60, nadir_idx_at_60, False
    
    if debug:
        print(f"    t={start} ({start/60:.1f}m): PASS G3 (120s)")
    
    # 120s passed!
    return True, start + 120, nadir_idx, True


def detect_intervals(hr: np.ndarray, cfg: Config, debug_ranges: list = None) -> list[Interval]:
    """
    Slide through signal finding valid 60s or 120s intervals.
    
    debug_ranges: list of (start_min, end_min) tuples to debug
    """
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    
    intervals = []
    i = 0
    n = len(hr_smooth)
    
    while i < n - 60:  # need at least 60s
        # Check if we're in a debug range
        debug = False
        if debug_ranges:
            t_min = i / 60
            for start_min, end_min in debug_ranges:
                if start_min <= t_min <= end_min:
                    debug = True
                    break
        
        found, end_idx, nadir_idx, is_120 = find_interval_from(hr_smooth, i, cfg, debug)
        
        if not found:
            i += 1
            continue
        
        # Found a valid interval (either 60s or 120s)
        hr_peak = hr_smooth[i]
        hr_nadir = hr_smooth[nadir_idx]
        total_drop = hr_peak - hr_nadir
        duration_sec = 120 if is_120 else 60
        
        # Pre-peak baseline (60-180s before)
        baseline_start = max(0, i - 180)
        baseline_end = max(0, i - 60)
        if baseline_end > baseline_start:
            baseline = np.median(hr_smooth[baseline_start:baseline_end])
        else:
            baseline = np.median(hr_smooth[max(0, i - 30):i]) if i > 30 else hr_peak
        
        peak_minus_rest = hr_peak - baseline
        
        # HRR at fixed timepoints
        idx_60 = i + 60
        hrr60 = hr_peak - hr_smooth[idx_60] if idx_60 < n else None
        
        hrr120 = None
        if is_120:
            idx_120 = i + 120
            hrr120 = hr_peak - hr_smooth[idx_120] if idx_120 < n else None
        
        interval = Interval(
            start_idx=i,
            end_idx=end_idx,
            nadir_idx=nadir_idx,
            hr_peak=hr_peak,
            hr_nadir=hr_nadir,
            total_drop=total_drop,
            duration_sec=duration_sec,
            peak_minus_rest=peak_minus_rest,
            hrr60=hrr60,
            hrr120=hrr120,
        )
        
        # Quality gates
        if total_drop < cfg.min_drop:
            interval.passed = False
            interval.rejection_reason = f"drop={total_drop:.0f}"
        elif peak_minus_rest < cfg.min_peak_minus_rest:
            interval.passed = False
            interval.rejection_reason = f"p-r={peak_minus_rest:.1f}"
        
        intervals.append(interval)
        
        # Resume from end of this interval
        i = end_idx + 1
    
    return intervals


def plot_session(session_id: int, ts: np.ndarray, hr: np.ndarray,
                 datetimes: list, intervals: list[Interval], cfg: Config,
                 output_path: str, show: bool = True):
    
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    times_min = ts / 60
    
    valid = [iv for iv in intervals if iv.passed]
    rejected = [iv for iv in intervals if not iv.passed]
    
    fig, ax = plt.subplots(figsize=(16, 6))
    
    session_date = datetimes[0].strftime('%Y-%m-%d %H:%M')
    duration_min = ts[-1] / 60
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min)"
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1)
    
    # Rejected (gray)
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
        
        color = 'gold' if iv.hrr120 is not None else 'green'
        alpha = 0.35 if iv.hrr120 is not None else 0.25
        
        ax.axvspan(start_min, end_min, alpha=alpha, color=color)
        ax.plot(start_min, iv.hr_peak, 'rv', markersize=8)
        ax.plot(nadir_min, iv.hr_nadir, 'g^', markersize=6)
        
        # Label
        if iv.hrr120 is not None:
            label = f"HRR120={iv.hrr120:.0f}★"
        else:
            label = f"HRR60={iv.hrr60:.0f}"
        
        mid_min = (start_min + end_min) / 2
        ax.annotate(f"#{n+1}\n{label}\n{iv.duration_sec}s",
                   xy=(mid_min, iv.hr_peak + 5), fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(min(hr_smooth) - 10, max(hr_smooth) + 25)
    ax.grid(True, alpha=0.3)
    
    hrr60_valid = [iv for iv in valid if iv.hrr120 is None]
    hrr120_valid = [iv for iv in valid if iv.hrr120 is not None]
    
    legend_elements = [
        mpatches.Patch(facecolor='gold', alpha=0.35, label=f'HRR120 ({len(hrr120_valid)})'),
        mpatches.Patch(facecolor='green', alpha=0.25, label=f'HRR60 ({len(hrr60_valid)})'),
        mpatches.Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({len(rejected)})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    cfg_str = f"60s@{cfg.max_rise_60}bpm, 120s@{cfg.max_rise_120}bpm, plateau>{cfg.plateau_sec}s, lookahead={cfg.peak_lookahead_sec}s"
    ax.text(0.01, 0.01, cfg_str, transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    plt.close()


def print_summary(intervals: list[Interval], session_id: int, cfg: Config):
    valid = [iv for iv in intervals if iv.passed]
    rejected = [iv for iv in intervals if not iv.passed]
    hrr60_count = len([iv for iv in valid if iv.hrr120 is None])
    hrr120_count = len([iv for iv in valid if iv.hrr120 is not None])
    
    print(f"\n{'='*60}")
    print(f"Config: max_rise_60={cfg.max_rise_60}, max_rise_120={cfg.max_rise_120}, lookahead={cfg.peak_lookahead_sec}s")
    print(f"Session {session_id}: {len(valid)} valid ({hrr60_count} HRR60, {hrr120_count} HRR120), {len(rejected)} rejected")
    print('='*60)
    
    for n, iv in enumerate(valid):
        if iv.hrr120 is not None:
            hrr_str = f"HRR120={iv.hrr120:.0f} ★"
        else:
            hrr_str = f"HRR60={iv.hrr60:.0f}"
        print(f"  #{n+1}: {iv.hr_peak:.0f}→{iv.hr_nadir:.0f} | {iv.duration_sec}s | {hrr_str}")


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
    parser = argparse.ArgumentParser(description='HRR Sliding Window v2')
    parser.add_argument('--session-id', type=int)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--output-dir', default='/tmp')
    parser.add_argument('--no-show', action='store_true')
    
    # Config
    parser.add_argument('--initial-descent', type=int, default=7)
    parser.add_argument('--initial-uptick', type=float, default=1.0, help='Max uptick allowed in initial descent')
    parser.add_argument('--lookback', type=int, default=15, help='Seconds before peak to check')
    parser.add_argument('--min-rise-before', type=float, default=5.0, help='Peak must be this much above lookback avg')
    parser.add_argument('--peak-lookahead', type=int, default=15, help='Seconds ahead to check for double-peaks')
    parser.add_argument('--max-rise-60', type=float, default=999.0, help='Max rise above nadir during 0-60s (999=disabled)')
    parser.add_argument('--max-rise-120', type=float, default=999.0, help='Max rise above nadir during 61-120s (999=disabled)')
    parser.add_argument('--plateau-sec', type=int, default=999, help='End if HR stays above nadir this long (999=disabled)')
    parser.add_argument('--min-drop', type=float, default=9.0)
    parser.add_argument('--min-peak-rest', type=float, default=8.0)
    parser.add_argument('--debug-range', type=str, help='Debug specific time range, e.g. "32-35,74-77"')
    
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
        initial_uptick_tolerance=args.initial_uptick,
        lookback_sec=args.lookback,
        min_rise_before_peak=args.min_rise_before,
        peak_lookahead_sec=args.peak_lookahead,
        max_rise_60=args.max_rise_60,
        max_rise_120=args.max_rise_120,
        plateau_sec=args.plateau_sec,
        min_drop=args.min_drop,
        min_peak_minus_rest=args.min_peak_rest,
    )
    
    ts, hr, dts = load_session(conn, args.session_id)
    conn.close()
    
    if hr is None:
        print(f"No data for session {args.session_id}")
        return
    
    # Parse debug ranges
    debug_ranges = None
    if args.debug_range:
        debug_ranges = []
        for r in args.debug_range.split(','):
            start, end = r.strip().split('-')
            debug_ranges.append((float(start), float(end)))
        print(f"Debug ranges: {debug_ranges}")
    
    intervals = detect_intervals(hr, cfg, debug_ranges)
    
    output_path = f"{args.output_dir}/hrr_v2_{args.session_id}.png"
    plot_session(args.session_id, ts, hr, dts, intervals, cfg, output_path, not args.no_show)
    
    print_summary(intervals, args.session_id, cfg)


if __name__ == '__main__':
    main()
