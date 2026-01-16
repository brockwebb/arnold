#!/usr/bin/env python3
"""
HRR Quality Inspection Visualization

Renders HR time series with STORED intervals from hr_recovery_intervals.
This is a read-only visualization - NO detection logic.

Shows exactly what was written to the database by hrr_batch.py.

Usage:
    python scripts/hrr_qc_viz.py --list                    # List sessions with HRR data
    python scripts/hrr_qc_viz.py --session-id 31           # Visualize session 31
    python scripts/hrr_qc_viz.py --session-id 31 --no-show # Save only, don't display
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def smooth(hr: np.ndarray, k: int = 5) -> np.ndarray:
    """Smooth HR for display (same as detection used)."""
    if len(hr) < k:
        return hr.copy()
    med = median_filter(hr, size=k, mode='nearest')
    kernel = np.ones(k) / k
    return np.convolve(med, kernel, mode='same')


def load_hr_samples(conn, session_id: int) -> Tuple[np.ndarray, np.ndarray, list, datetime]:
    """Load HR samples for a session."""
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
        return None, None, None, None
    
    datetimes = [r[0] for r in rows]
    hr = np.array([r[1] for r in rows], dtype=float)
    t0 = datetimes[0]
    ts = np.array([(dt - t0).total_seconds() for dt in datetimes])
    
    return ts, hr, datetimes, t0


def load_stored_intervals(conn, session_id: int) -> List[dict]:
    """
    Load STORED intervals from hr_recovery_intervals.
    
    This is the authoritative data - what hrr_batch.py wrote after detection.
    Gracefully handles missing columns for backward compatibility.
    """
    # Query ALL columns for full QC visibility
    query = """
        SELECT 
            id, start_time, end_time, duration_seconds,
            hr_peak, hr_30s, hr_60s, hr_90s, hr_120s, hr_180s, hr_240s, hr_300s, hr_nadir, rhr_baseline,
            hrr30_abs, hrr60_abs, hrr90_abs, hrr120_abs, hrr180_abs, hrr240_abs, hrr300_abs, total_drop,
            hr_reserve, recovery_ratio,
            tau_seconds, tau_fit_r2,
            r2_0_30, r2_30_60, r2_delta,
            slope_90_120, slope_90_120_r2,
            onset_delay_sec, onset_confidence,
            is_clean, actionable, confidence, stratum, is_deliberate, protocol_type,
            interval_order, quality_status, quality_flags, quality_score, review_priority
        FROM hr_recovery_intervals
        WHERE polar_session_id = %s
        ORDER BY start_time
    """
    
    # Fallback query without new columns
    fallback_query = """
        SELECT 
            id,
            start_time,
            end_time,
            duration_seconds,
            hr_peak,
            hr_60s,
            hr_120s,
            hr_180s,
            hr_300s,
            hr_nadir,
            hrr60_abs,
            hrr120_abs,
            hrr180_abs,
            hrr300_abs,
            tau_fit_r2,
            r2_300,
            is_clean,
            actionable,
            confidence,
            stratum,
            is_deliberate,
            protocol_type
        FROM hr_recovery_intervals
        WHERE polar_session_id = %s
        ORDER BY start_time
    """
    
    use_new_columns = True
    try:
        with conn.cursor() as cur:
            cur.execute(query, (session_id,))
            rows = cur.fetchall()
    except Exception as e:
        # Fallback to old schema
        use_new_columns = False
        conn.rollback()  # Clear the failed transaction
        with conn.cursor() as cur:
            cur.execute(fallback_query, (session_id,))
            rows = cur.fetchall()
    
    intervals = []
    for idx, row in enumerate(rows):
        # Parse based on new column order
        # id, start_time, end_time, duration_seconds,
        # hr_peak, hr_30s, hr_60s, hr_90s, hr_120s, hr_180s, hr_240s, hr_300s, hr_nadir, rhr_baseline,
        # hrr30_abs, hrr60_abs, hrr90_abs, hrr120_abs, hrr180_abs, hrr240_abs, hrr300_abs, total_drop,
        # hr_reserve, recovery_ratio,
        # tau_seconds, tau_fit_r2,
        # r2_0_30, r2_30_60, r2_delta,
        # slope_90_120, slope_90_120_r2,
        # onset_delay_sec, onset_confidence,
        # is_clean, actionable, confidence, stratum, is_deliberate, protocol_type,
        # interval_order, quality_status, quality_flags, quality_score, review_priority
        if use_new_columns:
            interval = {
                'id': row[0], 'start_time': row[1], 'end_time': row[2], 'duration_seconds': row[3],
                'hr_peak': row[4], 'hr_30s': row[5], 'hr_60s': row[6], 'hr_90s': row[7],
                'hr_120s': row[8], 'hr_180s': row[9], 'hr_240s': row[10], 'hr_300s': row[11],
                'hr_nadir': row[12], 'rhr_baseline': row[13],
                'hrr30_abs': row[14], 'hrr60_abs': row[15], 'hrr90_abs': row[16], 'hrr120_abs': row[17],
                'hrr180_abs': row[18], 'hrr240_abs': row[19], 'hrr300_abs': row[20], 'total_drop': row[21],
                'hr_reserve': row[22], 'recovery_ratio': row[23],
                'tau_seconds': row[24], 'tau_fit_r2': row[25],
                'r2_0_30': row[26], 'r2_30_60': row[27], 'r2_delta': row[28],
                'slope_90_120': row[29], 'slope_90_120_r2': row[30],
                'onset_delay_sec': row[31], 'onset_confidence': row[32],
                'is_clean': row[33], 'actionable': row[34], 'confidence': row[35],
                'stratum': row[36], 'is_deliberate': row[37], 'protocol_type': row[38],
                'interval_order': row[39], 'quality_status': row[40], 'quality_flags': row[41],
                'quality_score': row[42], 'review_priority': row[43],
                'r2_30_90': None,  # Not in DB yet
            }
        else:
            # Fallback for old schema
            interval = {
                'id': row[0], 'start_time': row[1], 'end_time': row[2], 'duration_seconds': row[3],
                'hr_peak': row[4], 'hr_60s': row[5], 'hr_120s': row[6], 'hr_180s': row[7],
                'hr_300s': row[8], 'hr_nadir': row[9],
                'hrr60_abs': row[10], 'hrr120_abs': row[11], 'hrr180_abs': row[12], 'hrr300_abs': row[13],
                'tau_fit_r2': row[14], 'is_clean': row[16], 'actionable': row[17],
                'confidence': row[18], 'stratum': row[19], 'is_deliberate': row[20], 'protocol_type': row[21],
                'interval_order': idx + 1,
                # Fill in missing fields
                'hr_30s': None, 'hr_90s': None, 'hr_240s': None, 'rhr_baseline': None,
                'hrr30_abs': None, 'hrr90_abs': None, 'hrr240_abs': None, 'total_drop': None,
                'hr_reserve': None, 'recovery_ratio': None, 'tau_seconds': None,
                'r2_0_30': None, 'r2_30_60': None, 'r2_30_90': None, 'r2_delta': None,
                'slope_90_120': None, 'slope_90_120_r2': None,
                'onset_delay_sec': None, 'onset_confidence': None,
                'quality_status': None, 'quality_flags': None, 'quality_score': None, 'review_priority': None,
            }
        
        intervals.append(interval)
    
    return intervals


def get_session_metadata(conn, session_id: int) -> dict:
    """Get session metadata from polar_sessions."""
    query = """
        SELECT 
            id,
            start_time,
            sport_type,
            duration_seconds
        FROM polar_sessions
        WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        row = cur.fetchone()
    
    if not row:
        return None
    
    return {
        'id': row[0],
        'start_time': row[1],
        'sport_type': row[2],
        'duration_seconds': row[3],
    }


def list_sessions_with_intervals(conn, n: int = 20):
    """List sessions that have stored HRR intervals."""
    query = """
        SELECT 
            hri.polar_session_id,
            ps.start_time,
            ps.sport_type,
            ps.duration_seconds / 60 as duration_min,
            COUNT(*) as interval_count,
            SUM(CASE WHEN hri.hrr120_abs IS NOT NULL THEN 1 ELSE 0 END) as hrr120_count,
            SUM(CASE WHEN hri.actionable THEN 1 ELSE 0 END) as actionable_count,
            AVG(hri.hrr60_abs) as avg_hrr60
        FROM hr_recovery_intervals hri
        JOIN polar_sessions ps ON ps.id = hri.polar_session_id
        GROUP BY hri.polar_session_id, ps.start_time, ps.sport_type, ps.duration_seconds
        ORDER BY ps.start_time DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (n,))
        rows = cur.fetchall()
    
    print(f"\n{'='*90}")
    print(f"Sessions with stored HRR intervals (most recent {n})")
    print(f"{'='*90}")
    print(f"{'ID':>5} | {'Date':^19} | {'Sport':<20} | {'Min':>4} | {'Tot':>3} | {'120':>3} | {'Act':>3} | {'Avg HRR60':>9}")
    print(f"{'-'*90}")
    
    for row in rows:
        sid, start, sport, dur, total, hrr120, actionable, avg_hrr = row
        sport_short = (sport or 'UNKNOWN')[:20]
        print(f"{sid:>5} | {start.strftime('%Y-%m-%d %H:%M'):^19} | {sport_short:<20} | {dur:>4.0f} | {total:>3} | {hrr120:>3} | {actionable:>3} | {avg_hrr:>9.1f}")
    
    print(f"\nLegend: Tot=Total intervals, 120=HRR120 intervals, Act=Actionable (R²≥0.75)")
    print()


def get_scipy_peaks(hr_smooth: np.ndarray) -> np.ndarray:
    """
    Get ALL scipy-detected peaks using same parameters as hrr_batch.py.
    
    These are shown as vertical blue dashed lines to indicate what
    the algorithm considered as potential recovery start points.
    
    Parameters match hrr_batch.py Config:
    - prominence=5.0
    - distance=10
    """
    peaks, _ = find_peaks(hr_smooth, prominence=5.0, distance=10)
    return peaks


def get_peak_label(session_id: int, interval: dict) -> str:
    """Generate peak label like S71:p03 for QC identification."""
    order = interval.get('interval_order')
    if order is not None:
        return f"S{session_id}:p{order:02d}"
    return f"S{session_id}:p??"


def get_status_indicator(interval: dict) -> str:
    """Get status indicator for annotation based on quality status."""
    status = interval.get('quality_status')
    priority = interval.get('review_priority')
    
    if status == 'pass' and (priority is None or priority == 3):
        return '✓'  # Clean pass
    elif status == 'flagged' or priority == 1:
        return '⚠'  # Needs review
    elif priority == 2:
        return '?'  # Minor issues
    return ''


def plot_session_qc(
    session_id: int,
    ts: np.ndarray,
    hr: np.ndarray,
    datetimes: list,
    session_start: datetime,
    intervals: List[dict],
    metadata: dict,
    output_path: str,
    show: bool = True,
    min_r2: float = 0.75,
    age: int = 50,
    rhr: int = 60
):
    """
    Plot HR time series with STORED intervals from database.
    
    Shows:
    - KARVONEN ZONE LINES: Subtle colored dashed lines at zone boundaries (Z1-Z5, HRmax)
    - BLUE DASHED LINES: All scipy-detected peaks (potential recovery points)
    - PURPLE shading (#DDA0DD): HRR300/5-min deliberate tests (duration >= 240s)
    - GOLD shading: HRR120 intervals (120s window)
    - GREEN shading: HRR60 intervals (60s window, hrr60_abs >= 9)
    - GRAY shading: Rejected intervals (didn't meet R² threshold)
    
    Y-axis scaled to Karvonen zones (Z1 floor to HRmax) for visual context.
    Zone colors match Polar convention (gray→blue→green→yellow→red).
    Annotations show stored values from database.
    Deliberate tests marked with ★ if is_deliberate=true.
    """
    hr_smooth = smooth(hr, k=5)
    times_min = ts / 60
    
    # Get ALL scipy peaks (same params as detection)
    all_peaks = get_scipy_peaks(hr_smooth)
    
    fig, ax = plt.subplots(figsize=(16, 6))
    
    # Title with metadata and counts
    session_date = metadata['start_time'].strftime('%Y-%m-%d %H:%M') if metadata else 'Unknown'
    sport = metadata.get('sport_type', 'UNKNOWN') if metadata else 'UNKNOWN'
    duration_min = ts[-1] / 60
    
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min) [{sport}]"
    
    # Plot HR trace
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1, alpha=0.8, label='Smoothed HR')
    
    # Calculate Karvonen zones (HRR-based)
    hr_max = 208 - (0.7 * age)
    hrr = hr_max - rhr  # Heart Rate Reserve
    
    # Zone boundaries: Z1(50-60%), Z2(60-70%), Z3(70-80%), Z4(80-90%), Z5(90-100%)
    zone_pcts = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00]
    zone_hrs = [rhr + (hrr * pct) for pct in zone_pcts]
    
    # Polar-style colors (subtle)
    zone_colors = [
        '#808080',  # Z1 floor - gray
        '#3498db',  # Z2 floor - blue  
        '#2ecc71',  # Z3 floor - green (VT1)
        '#f1c40f',  # Z4 floor - yellow
        '#e74c3c',  # Z5 floor - red
        '#c0392b',  # HRmax - dark red
    ]
    zone_labels = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Max']
    
    # Set y-axis range based on zones
    # Bottom: round down to nearest 10 below (Z1 floor - 20)
    # Top: round up to nearest 10 above HRmax
    y_min = int((zone_hrs[0] - 20) // 10) * 10
    y_max = (int(hr_max // 10) + 1) * 10
    
    # Draw zone boundary lines with labels on left
    for i, (hr_val, color, label) in enumerate(zip(zone_hrs, zone_colors, zone_labels)):
        ax.axhline(y=hr_val, color=color, linestyle='--', linewidth=1.0, alpha=0.4)
        # Label on left side
        ax.text(times_min[0] + 0.3, hr_val + 1, f'{label} ({hr_val:.0f})', 
                fontsize=7, ha='left', va='bottom', color=color, alpha=0.8)
    
    # Collect peaks that are used by intervals (to show unused peaks as gray)
    used_peak_times = set()
    
    # Categorize intervals
    # Priority: HRR300 (5-min) > HRR120 > HRR60 > rejected
    # R² >= 0.75 is the actionable threshold - anything below goes to rejected
    hrr300_intervals = []  # 5-minute deliberate tests (light purple)
    hrr120_intervals = []  # 2-minute intervals (gold)
    hrr60_intervals = []   # 1-minute intervals (green)
    rejected_intervals = [] # Didn't meet quality gates (gray)
    
    for interval in intervals:
        r2 = interval['tau_fit_r2']
        duration = interval['duration_seconds'] or 0
        
        # Quality gate: R² must meet threshold
        # Peak HR is NOT a validity criterion - recovery kinetics determine validity
        if r2 is None or r2 < min_r2:
            rejected_intervals.append(interval)
        # 5-minute deliberate tests (duration >= 240s with hrr300 data)
        elif duration >= 240 and interval['hrr300_abs'] is not None:
            hrr300_intervals.append(interval)
        elif interval['hrr120_abs'] is not None and duration >= 120:
            hrr120_intervals.append(interval)
        elif interval['hrr60_abs'] is not None and interval['hrr60_abs'] >= 9:
            hrr60_intervals.append(interval)
        else:
            rejected_intervals.append(interval)
    
    # Set title
    fig.suptitle(title, fontsize=11, fontweight='bold')
    
    # Plot rejected (gray window, red triangle) - 60s fixed window
    for interval in rejected_intervals:
        start_offset = (interval['start_time'] - session_start).total_seconds()
        start_min = start_offset / 60
        end_min = start_min + 1.0  # Fixed 60s window
        
        ax.axvspan(start_min, end_min, alpha=0.20, color='gray')
        
        if interval['hr_peak']:
            ax.plot(start_min, interval['hr_peak'], 'v', color='red', markersize=5, alpha=0.8)
            used_peak_times.add(round(start_min, 2))
        
        # Annotation with peak label
        mid_min = start_min + 0.5
        peak_label = get_peak_label(session_id, interval)
        hrr60_val = interval['hrr60_abs'] or '?'
        r2_val = f"{interval['tau_fit_r2']:.2f}" if interval['tau_fit_r2'] else '?'
        ax.annotate(f"✗ {peak_label}\nHRR60={hrr60_val} r²={r2_val}",
                   xy=(mid_min, (interval['hr_peak'] or 120) + 3), 
                   fontsize=6, ha='center', color='gray', alpha=0.8)
    
    # Plot HRR60 (green triangle, green window) - 60 seconds
    for interval in hrr60_intervals:
        start_offset = (interval['start_time'] - session_start).total_seconds()
        start_min = start_offset / 60
        end_min = start_min + 1.0  # 60s window
        
        ax.axvspan(start_min, end_min, alpha=0.25, color='green')
        
        if interval['hr_peak']:
            ax.plot(start_min, interval['hr_peak'], 'v', color='green', markersize=5)
            used_peak_times.add(round(start_min, 2))
        
        # Annotation with peak label and status
        mid_min = start_min + 0.5
        peak_label = get_peak_label(session_id, interval)
        status = get_status_indicator(interval)
        hrr60 = interval['hrr60_abs'] or '?'
        r2 = interval['tau_fit_r2']
        r2_str = f"{r2:.2f}" if r2 else '?'
        
        ax.annotate(f"{status} {peak_label}\nHRR60={hrr60} r²={r2_str}",
                   xy=(mid_min, (interval['hr_peak'] or 140) + 5),
                   fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))
    
    # Plot HRR120 (gold triangle, gold window) - 120 seconds
    for interval in hrr120_intervals:
        start_offset = (interval['start_time'] - session_start).total_seconds()
        start_min = start_offset / 60
        end_min = start_min + 2.0  # 120s window
        
        ax.axvspan(start_min, end_min, alpha=0.35, color='gold')
        
        if interval['hr_peak']:
            ax.plot(start_min, interval['hr_peak'], 'v', color='goldenrod', markersize=5)
            used_peak_times.add(round(start_min, 2))
        
        # Annotation with peak label and status
        mid_min = start_min + 1.0
        peak_label = get_peak_label(session_id, interval)
        status = get_status_indicator(interval)
        hrr120 = interval['hrr120_abs'] or '?'
        r2 = interval['tau_fit_r2']
        r2_str = f"{r2:.2f}" if r2 else '?'
        
        ax.annotate(f"{status} {peak_label}\nHRR120={hrr120} r²={r2_str}",
                   xy=(mid_min, (interval['hr_peak'] or 140) + 5),
                   fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))
    
    # Plot HRR300 (purple triangle, purple window) - 5-minute deliberate tests
    for interval in hrr300_intervals:
        start_offset = (interval['start_time'] - session_start).total_seconds()
        duration = min(interval['duration_seconds'] or 300, 300)
        start_min = start_offset / 60
        end_min = start_min + (duration / 60)
        
        ax.axvspan(start_min, end_min, alpha=0.30, color='#DDA0DD')  # plum
        
        if interval['hr_peak']:
            ax.plot(start_min, interval['hr_peak'], 'v', color='purple', markersize=5)
            used_peak_times.add(round(start_min, 2))
        
        # Annotation with peak label and extended HRR values
        mid_min = (start_min + end_min) / 2
        peak_label = get_peak_label(session_id, interval)
        status = get_status_indicator(interval)
        hrr60 = interval['hrr60_abs'] or '?'
        hrr120 = interval['hrr120_abs'] or '?'
        hrr300 = interval['hrr300_abs'] or '?'
        r2 = interval['r2_300'] or interval['tau_fit_r2']
        r2_str = f"{float(r2):.2f}" if r2 else '?'
        
        # Show deliberate test marker if annotated
        deliberate_marker = '★ ' if interval.get('is_deliberate') else ''
        
        ax.annotate(f"{status} {peak_label} {deliberate_marker}\nHRR 60/120/300={hrr60}/{hrr120}/{hrr300} r²={r2_str}",
                   xy=(mid_min, (interval['hr_peak'] or 140) + 5),
                   fontsize=7, ha='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='#F5E6F5', alpha=0.9))
    
    # Draw unused scipy peaks as gray triangles
    for peak_idx in all_peaks:
        peak_min = round(ts[peak_idx] / 60, 2)
        if peak_min not in used_peak_times:
            ax.plot(peak_min, hr_smooth[peak_idx], 'v', color='gray', markersize=5, alpha=0.4)
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(y_min, y_max)
    ax.grid(True, alpha=0.3)
    
    # Config note
    valid_ct = len(hrr300_intervals) + len(hrr120_intervals) + len(hrr60_intervals)
    ax.text(0.01, 0.01, 
            f"Source: hr_recovery_intervals | Valid (R²≥{min_r2}): {valid_ct}/{len(intervals)}",
            transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    plt.close()


def print_interval_details(intervals: List[dict], session_id: int):
    """Print detailed table of stored intervals with ALL QC metrics."""
    print(f"\n{'='*200}")
    print(f"Session {session_id} - FULL QC METRICS")
    print(f"{'='*200}")
    
    # Summary counts
    hrr300_ct = sum(1 for i in intervals if (i['duration_seconds'] or 0) >= 240 and i['hrr300_abs'] is not None)
    hrr120_ct = sum(1 for i in intervals if i['hrr120_abs'] is not None and (i['duration_seconds'] or 0) < 240)
    hrr60_ct = sum(1 for i in intervals if i['hrr60_abs'] is not None and i['hrr120_abs'] is None)
    actionable_ct = sum(1 for i in intervals if i['actionable'])
    flagged_ct = sum(1 for i in intervals if i.get('quality_status') == 'flagged' or i.get('review_priority') == 1)
    
    print(f"Total: {len(intervals)} | HRR300: {hrr300_ct} | HRR120: {hrr120_ct} | HRR60: {hrr60_ct} | Actionable: {actionable_ct} | Flagged: {flagged_ct}")
    print()
    print("Gate thresholds: G2:reserve>=25 | G5:hrr60>=5 | G6:hr60-nadir<=15 | G7:tau<200,r²>=0.5,ratio>=10% | G8:r²_30-60>=0.75")
    print()
    
    for interval in intervals:
        label = get_peak_label(session_id, interval)
        dur = interval['duration_seconds'] or 0
        
        # Basic info
        print(f"--- {label} (dur={dur}s) ---")
        
        # HR values
        pk = interval['hr_peak'] or '-'
        h30 = interval.get('hr_30s') or '-'
        h60 = interval.get('hr_60s') or '-'
        h90 = interval.get('hr_90s') or '-'
        h120 = interval.get('hr_120s') or '-'
        h180 = interval.get('hr_180s') or '-'
        h240 = interval.get('hr_240s') or '-'
        h300 = interval.get('hr_300s') or '-'
        nad = interval.get('hr_nadir') or '-'
        rhr = interval.get('rhr_baseline') or '-'
        
        print(f"  HR:  peak={pk} | 30s={h30} | 60s={h60} | 90s={h90} | 120s={h120} | 180s={h180} | 240s={h240} | 300s={h300} | nadir={nad} | rhr={rhr}")
        
        # HRR values (absolute drops)
        hrr30 = interval.get('hrr30_abs')
        hrr60 = interval.get('hrr60_abs')
        hrr90 = interval.get('hrr90_abs')
        hrr120 = interval.get('hrr120_abs')
        hrr180 = interval.get('hrr180_abs')
        hrr240 = interval.get('hrr240_abs')
        hrr300 = interval.get('hrr300_abs')
        total = interval.get('total_drop')
        
        def fmt_hrr(v): return f"{v}" if v is not None else '-'
        print(f"  HRR: 30={fmt_hrr(hrr30)} | 60={fmt_hrr(hrr60)} | 90={fmt_hrr(hrr90)} | 120={fmt_hrr(hrr120)} | 180={fmt_hrr(hrr180)} | 240={fmt_hrr(hrr240)} | 300={fmt_hrr(hrr300)} | total={fmt_hrr(total)}")
        
        # Gate metrics
        rsv = interval.get('hr_reserve') or 0
        ratio = interval.get('recovery_ratio')
        tau = interval.get('tau_seconds')
        tau_r2 = interval.get('tau_fit_r2')
        
        rsv_flag = '*' if rsv < 25 else ''
        hrr60_flag = '*' if hrr60 is not None and hrr60 < 5 else ''
        tau_flag = '*' if tau is not None and tau >= 200 else ''
        tau_r2_flag = '*' if tau_r2 is not None and tau_r2 < 0.5 else ''
        ratio_flag = '*' if ratio is not None and ratio < 0.10 else ''
        
        tau_s = f"{tau:.1f}" if tau is not None else '-'
        tau_r2_s = f"{tau_r2:.3f}" if tau_r2 is not None else '-'
        ratio_s = f"{ratio:.1%}" if ratio is not None else '-'
        
        # hr_60s - nadir check (G6)
        hr_60s_val = interval.get('hr_60s')
        nad_val = interval.get('hr_nadir')
        diff_60_nad = (hr_60s_val - nad_val) if hr_60s_val and nad_val else None
        diff_flag = '*' if diff_60_nad is not None and diff_60_nad > 15 and dur <= 120 else ''
        diff_s = f"{diff_60_nad}" if diff_60_nad is not None else '-'
        
        print(f"  G2-7: reserve={rsv}{rsv_flag} | hrr60={fmt_hrr(hrr60)}{hrr60_flag} | 60-nad={diff_s}{diff_flag} | tau={tau_s}{tau_flag} | tau_r²={tau_r2_s}{tau_r2_flag} | ratio={ratio_s}{ratio_flag}")
        
        # Segment R² (Gate 8)
        r2_030 = interval.get('r2_0_30')
        r2_3060 = interval.get('r2_30_60')
        r2_3090 = interval.get('r2_30_90')
        r2_delta = interval.get('r2_delta')
        
        r2_3060_flag = '*' if r2_3060 is not None and r2_3060 < 0.75 else ''
        r2_3090_flag = '*' if r2_3090 is not None and r2_3090 < 0.75 else ''
        
        r2_030_s = f"{r2_030:.3f}" if r2_030 is not None else '-'
        r2_3060_s = f"{r2_3060:.3f}" if r2_3060 is not None else '-'
        r2_3090_s = f"{r2_3090:.3f}" if r2_3090 is not None else '-'
        r2_delta_s = f"{r2_delta:+.3f}" if r2_delta is not None else '-'
        
        print(f"  G8:  r²_0-30={r2_030_s} | r²_30-60={r2_3060_s}{r2_3060_flag} | r²_30-90={r2_3090_s}{r2_3090_flag} | delta={r2_delta_s}")
        
        # Onset & other
        ons = interval.get('onset_delay_sec') or 0
        ons_conf = interval.get('onset_confidence') or '-'
        slope = interval.get('slope_90_120')
        slope_r2 = interval.get('slope_90_120_r2')
        
        slope_s = f"{slope:.4f}" if slope is not None else '-'
        slope_r2_s = f"{slope_r2:.3f}" if slope_r2 is not None else '-'
        
        print(f"  Other: onset={ons}s({ons_conf}) | slope_90-120={slope_s} (r²={slope_r2_s})")
        
        # Quality
        status = interval.get('quality_status') or '?'
        flags = interval.get('quality_flags') or ''
        if isinstance(flags, list):
            flags = '|'.join(flags)
        score = interval.get('quality_score')
        score_s = f"{score:.2f}" if score is not None else '-'
        
        print(f"  QC:  status={status} | score={score_s} | flags={flags if flags else 'none'}")
        print()
    
    print(f"* = fails gate threshold")


def main():
    parser = argparse.ArgumentParser(
        description='HRR Quality Inspection - Visualize STORED intervals from database'
    )
    parser.add_argument('--session-id', type=int, help='Session ID to visualize')
    parser.add_argument('--list', action='store_true', help='List sessions with HRR intervals')
    parser.add_argument('--output-dir', default='/tmp', help='Output directory for PNG')
    parser.add_argument('--no-show', action='store_true', help='Save only, do not display')
    parser.add_argument('--details', action='store_true', help='Print detailed interval table')
    parser.add_argument('--min-r2', type=float, default=0.75,
                       help='Minimum R² threshold for valid intervals (default: 0.75)')
    parser.add_argument('--age', type=int, default=None,
                       help='Age for Karvonen zone calculation (default: 50)')
    parser.add_argument('--rhr', type=int, default=60,
                       help='Resting heart rate for Karvonen zone calculation (default: 60)')
    
    args = parser.parse_args()
    
    conn = get_db_connection()
    
    if args.list:
        list_sessions_with_intervals(conn)
        conn.close()
        return
    
    if not args.session_id:
        parser.error("--session-id required (or use --list)")
    
    # Load data
    print(f"Loading session {args.session_id}...")
    
    ts, hr, dts, session_start = load_hr_samples(conn, args.session_id)
    if hr is None:
        print(f"No HR samples found for session {args.session_id}")
        conn.close()
        return
    
    intervals = load_stored_intervals(conn, args.session_id)
    if not intervals:
        print(f"No stored intervals found for session {args.session_id}")
        print("Run hrr_batch.py to detect and store intervals first.")
        conn.close()
        return
    
    metadata = get_session_metadata(conn, args.session_id)
    
    conn.close()
    
    print(f"Loaded {len(hr)} HR samples, {len(intervals)} stored intervals")
    
    # Print details if requested
    if args.details:
        print_interval_details(intervals, args.session_id)
    
    # Age and RHR for Karvonen zone display
    age = args.age or 50
    rhr = args.rhr
    hr_max = 208 - (0.7 * age)
    print(f"Zone calc: Age {age}, RHR {rhr}, HRmax={hr_max:.0f} bpm")
    
    # Generate visualization
    output_path = f"{args.output_dir}/hrr_qc_{args.session_id}.png"
    plot_session_qc(
        args.session_id, ts, hr, dts, session_start,
        intervals, metadata, output_path, not args.no_show,
        min_r2=args.min_r2,
        age=age,
        rhr=rhr
    )
    
    # Always print summary
    hrr300_ct = sum(1 for i in intervals if (i['duration_seconds'] or 0) >= 240 and i['hrr300_abs'] is not None)
    hrr120_ct = sum(1 for i in intervals if i['hrr120_abs'] is not None and (i['duration_seconds'] or 0) < 240)
    hrr60_ct = sum(1 for i in intervals if i['hrr60_abs'] is not None and i['hrr120_abs'] is None)
    actionable_ct = sum(1 for i in intervals if i['actionable'])
    deliberate_ct = sum(1 for i in intervals if i.get('is_deliberate'))
    
    print(f"\nSummary: {len(intervals)} intervals | {hrr300_ct} HRR300 | {hrr120_ct} HRR120 | {hrr60_ct} HRR60 | {actionable_ct} actionable | {deliberate_ct} deliberate")


if __name__ == '__main__':
    main()
