#!/usr/bin/env python3
"""
HRR Detection - Observer with Stopwatch v2

Algorithm:
1. Track running max until drop detected → candidate peak
2. Run 7-second test with strict noise tolerance
3. If FAIL: skip forward to next negative step, restart search
4. If PASS: extend interval, tracking nadir
5. Survives 60s → valid HRR60, try for 120s  
6. Dies 50-60s → show as gray rejected with duration
7. Dies <50s → no display
"""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import psycopg2
from dotenv import load_dotenv
from scipy.signal import find_peaks
from scipy.ndimage import median_filter
from scipy.optimize import curve_fit

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


@dataclass
class Config:
    smooth_kernel: int = 5
    
    # 7-second test
    initial_test_sec: int = 7
    max_single_rise: float = 1.0      # Max allowed single rise
    steady_tolerance: float = 0.5     # ±0.5 = "equal"
    
    # Extension phase  
    max_rise_from_nadir: float = 3.0  # End if rise exceeds this
    max_plateau_sec: int = 5          # End if rise persists this long
    
    # Quality
    min_hrr60: float = 9.0
    min_hrr120: float = 12.0
    
    # Display
    min_display_duration: int = 50    # Show rejected if >= this duration


@dataclass 
class HRRMeasurement:
    peak_idx: int
    peak_hr: float
    end_idx: int
    duration: int
    end_reason: str
    
    nadir_hr: float
    nadir_idx: int
    
    hrr60: Optional[float] = None
    hrr120: Optional[float] = None
    
    r2_60: Optional[float] = None   # Exponential fit R² at 60s
    r2_120: Optional[float] = None  # Exponential fit R² at 120s
    
    valid_60: bool = False
    valid_120: bool = False
    rejection_reason: Optional[str] = None


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


def find_candidate_peak(hr: np.ndarray, start: int, cfg: Config) -> Optional[int]:
    """
    DEPRECATED - now using scipy find_peaks.
    """
    return None


def get_all_peaks(hr: np.ndarray, cfg: Config) -> np.ndarray:
    """
    Use scipy to find ALL peaks with sufficient prominence.
    Returns array of peak indices.
    """
    # prominence=5 means peak must be at least 5bpm above surrounding valleys
    peaks, properties = find_peaks(hr, prominence=5, distance=10)
    return peaks


def exp_decay(t, hr_final, delta_hr, tau):
    """HR(t) = hr_final + delta_hr * exp(-t/tau)"""
    return hr_final + delta_hr * np.exp(-t / tau)


def fit_exponential_r2(hr_window: np.ndarray) -> float:
    """
    Fit exponential decay to HR window, return R².
    """
    n = len(hr_window)
    if n < 10:
        return 0.0
    
    t = np.arange(n)
    hr_peak = hr_window[0]
    hr_final = hr_window[-1]
    
    # Check if there's any descent
    if hr_final >= hr_peak:
        return 0.0
    
    try:
        delta_hr_guess = hr_peak - hr_final
        tau_guess = n / 3
        
        popt, _ = curve_fit(
            exp_decay, t, hr_window,
            p0=[hr_final, delta_hr_guess, tau_guess],
            bounds=(
                [0, 0, 5],           # Lower bounds
                [hr_peak, 100, 300]  # Upper bounds
            ),
            maxfev=1000
        )
        
        predicted = exp_decay(t, *popt)
        ss_res = np.sum((hr_window - predicted) ** 2)
        ss_tot = np.sum((hr_window - np.mean(hr_window)) ** 2)
        
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        return r2
        
    except Exception:
        return 0.0


def classify_step(hr_prev: float, hr_curr: float, cfg: Config) -> str:
    """Classify a step as 'rise', 'fall', or 'equal'."""
    diff = hr_curr - hr_prev
    if diff > cfg.steady_tolerance:
        return 'rise'
    elif diff < -cfg.steady_tolerance:
        return 'fall'
    else:
        return 'equal'


def test_7s_descent(hr: np.ndarray, peak_idx: int, cfg: Config, debug: bool = False) -> Tuple[bool, int]:
    """
    Initial descent test using linear fit on first 15 seconds.
    
    Requirements:
    - Slope must be negative (descending)
    - R² > 0.5 (decent fit, not noise)
    
    Returns: (passed, skip_to_idx)
    """
    n = len(hr)
    window_len = 15
    end = min(peak_idx + window_len, n - 1)
    
    if end - peak_idx < 10:
        return False, peak_idx + 1
    
    window = hr[peak_idx:end + 1]
    t = np.arange(len(window))
    
    # Linear regression
    slope, intercept = np.polyfit(t, window, 1)
    predicted = slope * t + intercept
    
    ss_res = np.sum((window - predicted) ** 2)
    ss_tot = np.sum((window - np.mean(window)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    if debug:
        print(f"    15s linear fit: slope={slope:.3f}, r2={r2:.3f}")
    
    # Must be descending with decent fit
    if slope >= 0:
        if debug:
            print(f"    FAIL: slope not negative")
        return False, peak_idx + 1
    
    if r2 < 0.5:
        if debug:
            print(f"    FAIL: r2={r2:.2f} < 0.5")
        return False, peak_idx + 1
    
    return True, peak_idx


def find_next_fall(hr: np.ndarray, start: int, cfg: Config) -> int:
    """Find the next index where a falling step begins."""
    n = len(hr)
    for t in range(start, n - 1):
        if hr[t + 1] < hr[t] - cfg.steady_tolerance:
            return t
    return n  # End of data


def extend_interval(hr: np.ndarray, peak_idx: int, cfg: Config, debug: bool = False) -> Tuple[int, int, float, str]:
    """
    Extend from validated peak toward 60s/120s.
    
    Track nadir. End if:
    - HR rises > max_rise_from_nadir above nadir AND stays > max_plateau_sec
    - 120 seconds reached
    - End of data
    
    Returns: (end_idx, nadir_idx, nadir_hr, end_reason)
    """
    n = len(hr)
    
    nadir = hr[peak_idx]
    nadir_idx = peak_idx
    
    seconds_above_threshold = 0
    
    for t in range(peak_idx + 1, min(peak_idx + 121, n)):
        if hr[t] < nadir:
            nadir = hr[t]
            nadir_idx = t
            seconds_above_threshold = 0
        else:
            rise_from_nadir = hr[t] - nadir
            if rise_from_nadir > cfg.max_rise_from_nadir:
                seconds_above_threshold += 1
                if seconds_above_threshold > cfg.max_plateau_sec:
                    if debug:
                        print(f"    Plateau at t={t-peak_idx}s: rose {rise_from_nadir:.1f}bpm for {seconds_above_threshold}s")
                    return t, nadir_idx, nadir, f"plateau@{t-peak_idx}s"
            else:
                # Small rise - tolerable, reset counter
                seconds_above_threshold = 0
    
    # Made it through
    end_idx = min(peak_idx + 120, n - 1)
    if peak_idx + 120 <= n:
        return end_idx, nadir_idx, nadir, "reached_120"
    else:
        return end_idx, nadir_idx, nadir, "end_of_data"


def detect_hrr(hr: np.ndarray, cfg: Config, debug: bool = False) -> Tuple[list[HRRMeasurement], list[HRRMeasurement], np.ndarray]:
    """
    Main detection loop - scipy peaks + our validation.
    
    1. Get all peaks from scipy
    2. For each peak (in order), run 7s test
    3. If passes, extend interval
    4. Skip peaks that fall within a used interval
    
    Returns: (valid_measurements, rejected_measurements, all_peaks)
    """
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    n = len(hr_smooth)
    
    # Get all peaks
    all_peaks = get_all_peaks(hr_smooth, cfg)
    
    if debug:
        print(f"  scipy found {len(all_peaks)} peaks")
    
    valid = []
    rejected = []
    
    used_until = 0  # Don't consider peaks before this index
    
    for peak_idx in all_peaks:
        # Skip if this peak is within a previous interval
        if peak_idx < used_until:
            continue
        
        # Skip if not enough room for 60s
        if peak_idx >= n - 60:
            continue
        
        if debug:
            print(f"\n  Peak at t={peak_idx} ({peak_idx/60:.1f}m), hr={hr_smooth[peak_idx]:.1f}")
        
        # Run 7-second test
        passed, skip_to = test_7s_descent(hr_smooth, peak_idx, cfg, debug)
        
        if not passed:
            if debug:
                print(f"    7s test FAILED")
            continue
        
        if debug:
            print(f"    7s test PASSED")
        
        # Extend interval
        end_idx, nadir_idx, nadir_hr, end_reason = extend_interval(hr_smooth, peak_idx, cfg, debug)
        duration = end_idx - peak_idx
        
        if debug:
            print(f"    Extended: duration={duration}s, nadir={nadir_hr:.1f}, reason={end_reason}")
        
        # Build measurement
        m = HRRMeasurement(
            peak_idx=peak_idx,
            peak_hr=hr_smooth[peak_idx],
            end_idx=end_idx,
            duration=duration,
            end_reason=end_reason,
            nadir_hr=nadir_hr,
            nadir_idx=nadir_idx,
        )
        
        # Check if valid
        if duration >= 60:
            idx_60 = peak_idx + 60
            m.hrr60 = hr_smooth[peak_idx] - hr_smooth[idx_60]
            
            # Calculate R² at 60s (diagnostic, not gate)
            window_60 = hr_smooth[peak_idx:idx_60 + 1]
            m.r2_60 = round(fit_exponential_r2(window_60), 3)
            
            if m.hrr60 >= cfg.min_hrr60:
                m.valid_60 = True
                
                # Check for 120s
                if duration >= 120:
                    idx_120 = peak_idx + 120
                    m.hrr120 = hr_smooth[peak_idx] - hr_smooth[idx_120]
                    
                    # Calculate R² at 120s
                    window_120 = hr_smooth[peak_idx:idx_120 + 1]
                    m.r2_120 = round(fit_exponential_r2(window_120), 3)
                    
                    if m.hrr120 >= cfg.min_hrr120:
                        m.valid_120 = True
            else:
                m.rejection_reason = f"hrr60={m.hrr60:.0f}<{cfg.min_hrr60}"
        else:
            m.rejection_reason = f"duration={duration}s<60"
        
        # Categorize result
        if m.valid_60 or m.valid_120:
            valid.append(m)
            # Mark this interval as used
            if m.valid_120:
                used_until = peak_idx + 120
            else:
                used_until = peak_idx + 60
            if debug:
                status = "HRR120" if m.valid_120 else "HRR60"
                r2_val = m.r2_120 if m.valid_120 else m.r2_60
                print(f"    VALID {status} (r²={r2_val}), used_until={used_until}")
        else:
            # Show as rejected if duration >= min_display_duration
            if duration >= cfg.min_display_duration:
                rejected.append(m)
                if debug:
                    r2_str = f", r²={m.r2_60}" if m.r2_60 else ""
                    print(f"    REJECTED (will display): {m.rejection_reason}{r2_str}")
            else:
                if debug:
                    print(f"    REJECTED (no display): {m.rejection_reason}")
            # Still advance used_until to end_idx to avoid re-checking
            used_until = end_idx
    
    return valid, rejected, all_peaks


def plot_session(session_id: int, ts: np.ndarray, hr: np.ndarray,
                 datetimes: list, valid: list[HRRMeasurement], 
                 rejected: list[HRRMeasurement], all_peaks: np.ndarray,
                 cfg: Config, output_path: str, show: bool = True):
    
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    times_min = ts / 60
    
    fig, ax = plt.subplots(figsize=(16, 6))
    
    session_date = datetimes[0].strftime('%Y-%m-%d %H:%M')
    duration_min = ts[-1] / 60
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min)"
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1, alpha=0.8)
    
    # Draw vertical dashed lines at ALL scipy peaks
    for peak_idx in all_peaks:
        peak_min = ts[peak_idx] / 60
        ax.axvline(x=peak_min, color='lightblue', linestyle='--', linewidth=0.8, alpha=0.7)
    
    # Plot rejected (gray) with duration and R²
    for m in rejected:
        start_min = ts[m.peak_idx] / 60
        end_min = ts[m.end_idx] / 60
        nadir_min = ts[m.nadir_idx] / 60
        
        ax.axvspan(start_min, end_min, alpha=0.15, color='gray')
        ax.plot(start_min, m.peak_hr, 'v', color='gray', markersize=6)
        ax.plot(nadir_min, m.nadir_hr, '^', color='gray', markersize=5)
        
        mid_min = (start_min + end_min) / 2
        r2_str = f"\nr²={m.r2_60}" if m.r2_60 else ""
        ax.annotate(f"✗{m.duration}s{r2_str}",
                   xy=(mid_min, m.peak_hr + 3), fontsize=7, ha='center', color='gray')
    
    # Plot valid
    label_num = 0
    for m in valid:
        label_num += 1
        start_min = ts[m.peak_idx] / 60
        
        if m.valid_120:
            end_min = ts[m.peak_idx + 120] / 60
            color = 'gold'
            alpha = 0.35
            label = f"HRR120={m.hrr120:.0f}★\nr²={m.r2_120}"
            dur_label = "120s"
        else:
            end_min = ts[m.peak_idx + 60] / 60
            color = 'green'
            alpha = 0.25
            label = f"HRR60={m.hrr60:.0f}\nr²={m.r2_60}"
            dur_label = "60s"
        
        nadir_min = ts[m.nadir_idx] / 60
        
        ax.axvspan(start_min, end_min, alpha=alpha, color=color)
        ax.plot(start_min, m.peak_hr, 'rv', markersize=8)
        ax.plot(nadir_min, m.nadir_hr, 'g^', markersize=6)
        
        mid_min = (start_min + end_min) / 2
        ax.annotate(f"#{label_num}\n{label}\n{dur_label}",
                   xy=(mid_min, m.peak_hr + 5), fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(min(hr_smooth) - 10, max(hr_smooth) + 25)
    ax.grid(True, alpha=0.3)
    
    hrr60_ct = len([m for m in valid if not m.valid_120])
    hrr120_ct = len([m for m in valid if m.valid_120])
    rejected_ct = len(rejected)
    
    legend_elements = [
        mpatches.Patch(facecolor='gold', alpha=0.35, label=f'HRR120 ({hrr120_ct})'),
        mpatches.Patch(facecolor='green', alpha=0.25, label=f'HRR60 ({hrr60_ct})'),
        mpatches.Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({rejected_ct})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    cfg_str = f"7s_rise<{cfg.max_single_rise}bpm, plateau>{cfg.max_rise_from_nadir}bpm/{cfg.max_plateau_sec}s"
    ax.text(0.01, 0.01, cfg_str, transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    plt.close()


def print_summary(valid: list[HRRMeasurement], rejected: list[HRRMeasurement], session_id: int):
    hrr60_ct = len([m for m in valid if not m.valid_120])
    hrr120_ct = len([m for m in valid if m.valid_120])
    
    print(f"\n{'='*80}")
    print(f"Session {session_id}: {len(valid)} valid ({hrr60_ct} HRR60, {hrr120_ct} HRR120), "
          f"{len(rejected)} near-miss rejected")
    print('='*80)
    
    print("\nVALID:")
    for n, m in enumerate(valid):
        t_min = m.peak_idx / 60
        if m.valid_120:
            print(f"  #{n+1} @{t_min:.1f}m: {m.peak_hr:.0f}→{m.nadir_hr:.0f} | HRR120={m.hrr120:.0f}★ r²={m.r2_120}")
        else:
            print(f"  #{n+1} @{t_min:.1f}m: {m.peak_hr:.0f}→{m.nadir_hr:.0f} | HRR60={m.hrr60:.0f} r²={m.r2_60}")
    
    if rejected:
        print(f"\nREJECTED (>{50}s):")
        for m in rejected:
            t_min = m.peak_idx / 60
            r2_str = f"r²={m.r2_60}" if m.r2_60 else "r²=N/A"
            print(f"  @{t_min:.1f}m: {m.peak_hr:.0f}→{m.nadir_hr:.0f} | {m.duration}s | {m.rejection_reason} | {r2_str}")


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
    parser = argparse.ArgumentParser(description='HRR Detection - Observer with Stopwatch')
    parser.add_argument('--session-id', type=int)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--output-dir', default='/tmp')
    parser.add_argument('--no-show', action='store_true')
    parser.add_argument('--debug', action='store_true')
    
    parser.add_argument('--smooth-kernel', type=int, default=5)
    parser.add_argument('--initial-test-sec', type=int, default=7)
    parser.add_argument('--max-single-rise', type=float, default=1.0)
    parser.add_argument('--steady-tolerance', type=float, default=0.5)
    parser.add_argument('--max-rise-from-nadir', type=float, default=3.0)
    parser.add_argument('--max-plateau-sec', type=int, default=5)
    parser.add_argument('--min-hrr60', type=float, default=9.0)
    parser.add_argument('--min-hrr120', type=float, default=12.0)
    parser.add_argument('--min-display-duration', type=int, default=50)
    
    args = parser.parse_args()
    
    conn = get_db_connection()
    
    if args.list:
        list_sessions(conn)
        conn.close()
        return
    
    if not args.session_id:
        parser.error("--session-id required (or use --list)")
    
    cfg = Config(
        smooth_kernel=args.smooth_kernel,
        initial_test_sec=args.initial_test_sec,
        max_single_rise=args.max_single_rise,
        steady_tolerance=args.steady_tolerance,
        max_rise_from_nadir=args.max_rise_from_nadir,
        max_plateau_sec=args.max_plateau_sec,
        min_hrr60=args.min_hrr60,
        min_hrr120=args.min_hrr120,
        min_display_duration=args.min_display_duration,
    )
    
    ts, hr, dts = load_session(conn, args.session_id)
    conn.close()
    
    if hr is None:
        print(f"No data for session {args.session_id}")
        return
    
    print(f"Loaded session {args.session_id}: {len(hr)} samples, {ts[-1]/60:.0f} minutes")
    
    valid, rejected, all_peaks = detect_hrr(hr, cfg, debug=args.debug)
    
    output_path = f"{args.output_dir}/hrr_simple_{args.session_id}.png"
    plot_session(args.session_id, ts, hr, dts, valid, rejected, all_peaks, cfg, output_path, not args.no_show)
    
    print_summary(valid, rejected, args.session_id)


if __name__ == '__main__':
    main()
