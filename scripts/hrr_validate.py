#!/usr/bin/env python3
"""
HRR Validation Plots

Visual validation of non-rising-run detection.
Produces overlay plots showing detected intervals on HR trace.
"""

import argparse
import os
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from dotenv import load_dotenv

# Add scripts directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from hrr_detection import (
    HRRDetectionConfig, DetectedInterval,
    detect_recovery_intervals, get_db_connection, load_session_hr
)

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def plot_session_with_intervals(
    session_id: int,
    intervals: list[DetectedInterval],
    timestamps_sec: np.ndarray,
    hr_smooth: np.ndarray,
    datetimes: list[datetime],
    config: HRRDetectionConfig,
    output_path: str = None,
    show: bool = True
):
    """
    Plot HR trace with detected intervals highlighted.
    
    - Green shading: valid intervals (passed all gates)
    - Gray shading: rejected intervals
    - Red triangle: peak
    - Green triangle: nadir
    - Annotations: HRR60, duration, gate failures
    """
    
    if len(hr_smooth) == 0:
        print("No data to plot")
        return
    
    times_min = timestamps_sec / 60
    
    # Separate valid and rejected
    valid = [i for i in intervals if i.passed_gates]
    rejected = [i for i in intervals if not i.passed_gates]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 6))
    
    session_date = datetimes[0].strftime('%Y-%m-%d %H:%M') if datetimes else 'Unknown'
    duration_min = timestamps_sec[-1] / 60 if len(timestamps_sec) > 0 else 0
    title = f"Session {session_id} - {session_date} ({duration_min:.0f} min)"
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    # Plot HR trace
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1, label='Smoothed HR')
    
    # Plot REJECTED intervals (gray)
    for interval in rejected:
        start_min = timestamps_sec[interval.peak_idx] / 60
        end_min = timestamps_sec[interval.run_end_idx] / 60
        
        ax.axvspan(start_min, end_min, alpha=0.15, color='gray')
        ax.plot(start_min, interval.hr_peak, 'v', color='gray', markersize=6, alpha=0.7)
        
        # Show why rejected (abbreviated)
        if interval.gate_failures:
            short_reason = interval.gate_failures[0].split('=')[0][:8]
            ax.annotate(f"✗{short_reason}", 
                       xy=(start_min, interval.hr_peak + 3),
                       fontsize=6, color='gray', ha='center')
    
    # Plot VALID intervals (green)
    for i, interval in enumerate(valid):
        start_min = timestamps_sec[interval.peak_idx] / 60
        end_min = timestamps_sec[interval.run_end_idx] / 60
        nadir_min = timestamps_sec[interval.nadir_idx] / 60
        
        ax.axvspan(start_min, end_min, alpha=0.25, color='green')
        
        # Peak marker (red triangle)
        ax.plot(start_min, interval.hr_peak, 'rv', markersize=8)
        
        # Nadir marker (green triangle)
        ax.plot(nadir_min, interval.hr_nadir, 'g^', markersize=6)
        
        # Annotation
        mid_min = (start_min + end_min) / 2
        
        hrr60_str = f"HRR60={interval.hrr60_abs:.0f}" if interval.hrr60_abs else "HRR60=?"
        drop_str = f"drop={interval.total_drop:.0f}"
        dur_str = f"{interval.duration_sec}s"
        prest_str = f"p-r={interval.peak_minus_rest:.0f}" if interval.peak_minus_rest else ""
        
        label = f"#{i+1}\n{hrr60_str}\n{drop_str}\n{dur_str}"
        if prest_str:
            label += f"\n{prest_str}"
        
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
        mpatches.Patch(facecolor='green', alpha=0.25, label=f'Valid ({len(valid)})'),
        mpatches.Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({len(rejected)})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
    
    # Config note at bottom
    config_str = f"allowed_up={config.allowed_up_per_sec}, min_drop={config.min_total_drop}, min_p-r={config.min_peak_minus_rest}"
    ax.text(0.01, 0.01, config_str, transform=ax.transAxes, fontsize=7, color='gray')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    
    plt.close()


def plot_interval_detail(
    interval: DetectedInterval,
    timestamps_sec: np.ndarray,
    hr_smooth: np.ndarray,
    interval_num: int,
    config: HRRDetectionConfig,
    output_path: str = None,
    show: bool = True
):
    """
    Detailed plot of a single interval.
    Shows the HR decay from peak with HRR timepoints marked.
    """
    
    # Extract interval data
    start_idx = max(0, interval.peak_idx - 30)  # show 30s before peak
    end_idx = min(len(hr_smooth), interval.run_end_idx + 30)  # show 30s after
    
    t_rel = timestamps_sec[start_idx:end_idx] - timestamps_sec[interval.peak_idx]
    hr_segment = hr_smooth[start_idx:end_idx]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot HR
    ax.plot(t_rel, hr_segment, 'b.-', linewidth=1, markersize=2, label='Smoothed HR')
    
    # Mark peak
    ax.axvline(x=0, color='red', linestyle='--', alpha=0.5, label='Peak')
    ax.plot(0, interval.hr_peak, 'rv', markersize=10)
    
    # Mark nadir
    nadir_t = timestamps_sec[interval.nadir_idx] - timestamps_sec[interval.peak_idx]
    ax.plot(nadir_t, interval.hr_nadir, 'g^', markersize=10, label='Nadir')
    
    # Mark HRR timepoints
    for t, hr_val, label in [
        (30, interval.hr_30s, 'HRR30'),
        (60, interval.hr_60s, 'HRR60'),
        (120, interval.hr_120s, 'HRR120'),
    ]:
        if hr_val is not None and t <= t_rel[-1]:
            ax.axvline(x=t, color='gray', linestyle=':', alpha=0.5)
            ax.plot(t, hr_val, 'ko', markersize=6)
            hrr = interval.hr_peak - hr_val
            ax.annotate(f'{label}={hrr:.0f}', xy=(t, hr_val - 3), fontsize=8, ha='center')
    
    # Mark run boundaries
    run_start_t = timestamps_sec[interval.run_start_idx] - timestamps_sec[interval.peak_idx]
    run_end_t = timestamps_sec[interval.run_end_idx] - timestamps_sec[interval.peak_idx]
    ax.axvspan(run_start_t, run_end_t, alpha=0.1, color='green', label='Non-rising run')
    
    # Info box
    status = "✓ VALID" if interval.passed_gates else "✗ REJECTED"
    info = f"""Interval #{interval_num} {status}
Peak HR: {interval.hr_peak:.0f} bpm
Nadir HR: {interval.hr_nadir:.0f} bpm
Total drop: {interval.total_drop:.1f} bpm
Duration: {interval.duration_sec}s
Peak-rest: {interval.peak_minus_rest:.1f if interval.peak_minus_rest else '?'} bpm
"""
    if interval.gate_failures:
        info += f"\nGate failures:\n" + "\n".join(f"  - {f}" for f in interval.gate_failures)
    
    ax.text(0.98, 0.98, info, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
            family='monospace')
    
    ax.set_xlabel('Time relative to peak (seconds)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_title(f'Interval #{interval_num} Detail')
    ax.legend(loc='lower right', fontsize=8)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_path}")
    
    if show:
        plt.show()
    
    plt.close()


def list_recent_sessions(n: int = 10):
    """List recent sessions with HR data."""
    conn = get_db_connection()
    query = """
        SELECT 
            session_id,
            COUNT(*) as samples,
            MIN(sample_time) as start_time,
            MAX(sample_time) as end_time,
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
    conn.close()
    
    print(f"\nRecent {n} sessions with HR data:")
    print("-" * 70)
    for row in rows:
        sid, samples, start, end, dur = row
        print(f"  Session {sid:3d}: {start.strftime('%Y-%m-%d %H:%M')} | {dur:.0f} min | {samples} samples")
    print()


def main():
    parser = argparse.ArgumentParser(description='Validate HRR detection with plots')
    parser.add_argument('--session-id', type=int, help='Session ID to analyze')
    parser.add_argument('--list', action='store_true', help='List recent sessions')
    parser.add_argument('--output', '-o', type=str, help='Output file path (PNG)')
    parser.add_argument('--detail', type=int, help='Show detail plot for interval N')
    parser.add_argument('--no-show', action='store_true', help='Do not display (just save)')
    
    # Config overrides
    parser.add_argument('--allowed-up', type=float, default=0.2, help='allowed_up_per_sec')
    parser.add_argument('--min-drop', type=float, default=5.0, help='min_total_drop')
    parser.add_argument('--min-peak-rest', type=float, default=20.0, help='min_peak_minus_rest')
    
    args = parser.parse_args()
    
    if args.list:
        list_recent_sessions()
        return
    
    if not args.session_id:
        parser.error("--session-id required (or use --list to see sessions)")
    
    # Build config
    config = HRRDetectionConfig(
        allowed_up_per_sec=args.allowed_up,
        min_total_drop=args.min_drop,
        min_peak_minus_rest=args.min_peak_rest,
    )
    
    # Run detection
    print(f"Detecting intervals for session {args.session_id}...")
    intervals, ts, hr, dts = detect_recovery_intervals(args.session_id, config)
    
    valid = [i for i in intervals if i.passed_gates]
    rejected = [i for i in intervals if not i.passed_gates]
    print(f"Found {len(intervals)} intervals: {len(valid)} valid, {len(rejected)} rejected")
    
    if args.detail:
        # Show detail for specific interval
        if 1 <= args.detail <= len(intervals):
            interval = intervals[args.detail - 1]
            output_path = args.output or f"/tmp/hrr_session_{args.session_id}_interval_{args.detail}.png"
            plot_interval_detail(interval, ts, hr, args.detail, config, output_path, not args.no_show)
        else:
            print(f"Invalid interval number. Valid range: 1-{len(intervals)}")
    else:
        # Show full session
        output_path = args.output or f"/tmp/hrr_session_{args.session_id}.png"
        plot_session_with_intervals(args.session_id, intervals, ts, hr, dts, config, output_path, not args.no_show)


if __name__ == '__main__':
    main()
