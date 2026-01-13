#!/usr/bin/env python3
"""
HRR Visualization Tool

Generates plots of HR time series with detected recovery intervals highlighted.
Essential for validating the detection algorithm and understanding the data.

Usage:
    python scripts/hrr_visualize.py --session-id 1 --source endurance
    python scripts/hrr_visualize.py --session-id 1 --source endurance --output hr_session_1.png
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import numpy as np

# Add scripts directory to path for local imports BEFORE any local imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError as e:
    print(f"ERROR: matplotlib not installed: {e}")
    exit(1)

import psycopg2
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Import from our feature extraction module
from hrr_feature_extraction import (
    HRRConfig, HRSample, RecoveryInterval,
    get_hr_samples, get_rhr_for_date,
    detect_recovery_intervals, compute_features, preprocess_samples,
    filter_quality_intervals
)


def get_db_connection():
    """Get database connection from environment."""
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def plot_hrr60_distribution(
    valid_intervals: List[RecoveryInterval],
    title: str = "HRR60 Distribution",
    output_path: Optional[str] = None,
    show: bool = True
):
    """
    Beeswarm plot of HRR60 values from valid intervals.
    Shows distribution of 60-second HR drops (from onset point).
    """
    
    hrr60_values = [i.hrr60_abs for i in valid_intervals if i.hrr60_abs is not None]
    
    if not hrr60_values:
        print("No HRR60 values to plot")
        return
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Beeswarm-style: strip plot with jitter
    y = np.ones(len(hrr60_values))
    jitter = np.random.uniform(-0.1, 0.1, len(hrr60_values))
    
    ax.scatter(hrr60_values, y + jitter, alpha=0.6, s=80, c='steelblue', edgecolors='white')
    
    # Add mean and median lines
    mean_val = np.mean(hrr60_values)
    median_val = np.median(hrr60_values)
    
    ax.axvline(x=mean_val, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_val:.1f}')
    ax.axvline(x=median_val, color='green', linestyle='-', linewidth=2, label=f'Median: {median_val:.1f}')
    
    # Reference line at threshold
    ax.axvline(x=5, color='gray', linestyle=':', linewidth=1, alpha=0.7, label='Min threshold (5)')
    
    ax.set_xlabel('HRR60 (bpm drop in 60s from onset)', fontsize=11)
    ax.set_yticks([])
    ax.set_ylim(0.5, 1.5)
    ax.set_xlim(0, max(hrr60_values) + 5)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(True, axis='x', alpha=0.3)
    
    # Add stats text
    stats_text = f"n={len(hrr60_values)}  |  range: {min(hrr60_values)}-{max(hrr60_values)}  |  std: {np.std(hrr60_values):.1f}"
    ax.text(0.5, 0.02, stats_text, transform=ax.transAxes, ha='center', fontsize=9, color='gray')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved distribution plot to: {output_path}")
    
    if show:
        plt.show()
    
    plt.close()


def plot_session_with_intervals(
    samples: List[HRSample],
    valid_intervals: List[RecoveryInterval],
    noise_intervals: List[RecoveryInterval],
    rejected_intervals: List[RecoveryInterval],
    rhr: int,
    config: HRRConfig,
    title: str = "HR Session with Recovery Intervals",
    output_path: Optional[str] = None,
    show: bool = True
):
    """
    Plot HR time series with detected recovery intervals.
    
    Simplified color coding:
    - GREEN shading: Valid intervals (real recovery signal)
    - GRAY shading: Rejected intervals (noise + insufficient recovery)
    """
    
    if not samples:
        print("No samples to plot")
        return
    
    # Combine noise and rejected into single "rejected" category
    all_rejected = noise_intervals + rejected_intervals
    
    # Prepare data
    t0 = samples[0].timestamp
    times_sec = np.array([(s.timestamp - t0).total_seconds() for s in samples])
    times_min = times_sec / 60
    hr_raw = np.array([s.hr_value for s in samples])
    hr_smooth = preprocess_samples(samples, window=5)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 6))
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    # Plot HR trace
    ax.plot(times_min, hr_raw, 'lightgray', alpha=0.5, linewidth=0.5, label='Raw HR')
    ax.plot(times_min, hr_smooth, 'b-', linewidth=1, label='Smoothed HR')
    
    # RHR baseline
    ax.axhline(y=rhr, color='green', linestyle='--', linewidth=1, alpha=0.7, label=f'RHR ({rhr})')
    
    # Elevation threshold
    threshold = rhr + config.min_elevation_bpm
    ax.axhline(y=threshold, color='red', linestyle='--', linewidth=1, alpha=0.5)
    
    # Plot REJECTED intervals (gray)
    for interval in all_rejected:
        start_min = (interval.start_time - t0).total_seconds() / 60
        end_min = (interval.end_time - t0).total_seconds() / 60
        
        ax.axvspan(start_min, end_min, alpha=0.15, color='gray')
        ax.plot(start_min, interval.hr_peak, 'x', color='gray', markersize=6, alpha=0.7)
    
    # Plot VALID intervals (green)
    for interval in valid_intervals:
        start_min = (interval.start_time - t0).total_seconds() / 60
        end_min = (interval.end_time - t0).total_seconds() / 60
        
        ax.axvspan(start_min, end_min, alpha=0.25, color='green')
        
        # Mark peak
        ax.plot(start_min, interval.hr_peak, 'rv', markersize=8)
        
        # Mark onset if delayed
        if interval.onset_delay_sec and interval.adjusted_peak_hr:
            onset_min = start_min + interval.onset_delay_sec / 60
            ax.plot(onset_min, interval.adjusted_peak_hr, 'g>', markersize=6)  # Green arrow at onset
        
        # Mark nadir
        if interval.hr_nadir:
            ax.plot(end_min, interval.hr_nadir, 'g^', markersize=6)
        
        # Annotate with key metrics
        mid_min = (start_min + end_min) / 2
        label_y = interval.hr_peak + 5
        
        hrr60_str = f"HRR60={interval.hrr60_abs}" if interval.hrr60_abs else "HRR60=?"
        tau_str = f"\u03c4={interval.tau_seconds:.0f}s" if interval.tau_seconds and interval.tau_seconds < 300 else "\u03c4=\u221e"
        frac_str = f"frac={interval.hrr60_frac:.0%}" if interval.hrr60_frac else ""
        onset_str = f"onset={interval.onset_delay_sec}s({interval.onset_confidence[0] if interval.onset_confidence else ''})" if interval.onset_delay_sec else ""
        pre_str = f"pre={interval.effort_avg_hr}" if interval.effort_avg_hr else ""
        
        ax.annotate(f"#{interval.interval_order}\n{hrr60_str}\n{frac_str}\n{tau_str}\n{pre_str}\n{onset_str}", 
                    xy=(mid_min, label_y), fontsize=7, ha='center',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_ylim(min(hr_raw) - 10, max(hr_raw) + 20)
    ax.grid(True, alpha=0.3)
    
    # Summary and legend
    from matplotlib.patches import Patch
    n_rejected = len(all_rejected)
    legend_elements = [
        Patch(facecolor='green', alpha=0.25, label=f'Valid ({len(valid_intervals)})'),
        Patch(facecolor='gray', alpha=0.15, label=f'Rejected ({n_rejected})'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved plot to: {output_path}")
    
    if show:
        plt.show()
    
    plt.close()


def plot_interval_detail(
    samples: List[HRSample],
    interval: RecoveryInterval,
    rhr: int,
    interval_num: int,
    output_path: Optional[str] = None,
    show: bool = True
):
    """
    Detailed plot of a single recovery interval with exponential fit overlay.
    """
    
    if not interval.samples:
        print(f"No samples for interval {interval_num}")
        return
    
    # Prepare data
    t0 = interval.samples[0].timestamp
    times_sec = np.array([(s.timestamp - t0).total_seconds() for s in interval.samples])
    hr_values = np.array([s.hr_value for s in interval.samples])
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot actual HR
    ax.plot(times_sec, hr_values, 'b.-', linewidth=1, markersize=3, label='Measured HR')
    
    # Plot exponential fit if valid
    if interval.tau_seconds and interval.tau_seconds < 300 and interval.tau_fit_r2:
        from hrr_feature_extraction import exponential_decay
        
        t_fit = np.linspace(0, max(times_sec), 100)
        # Reconstruct fit parameters
        a = interval.hr_peak - rhr
        hr_fit = exponential_decay(t_fit, a, interval.tau_seconds, rhr)
        ax.plot(t_fit, hr_fit, 'r--', linewidth=2, 
                label=f'Exp fit (τ={interval.tau_seconds:.1f}s, R²={interval.tau_fit_r2:.3f})')
    
    # Reference lines
    ax.axhline(y=rhr, color='green', linestyle='--', alpha=0.7, label=f'RHR ({rhr})')
    ax.axhline(y=interval.hr_peak, color='red', linestyle=':', alpha=0.5, label=f'Peak ({interval.hr_peak})')
    
    # Mark timepoints
    for t, label in [(30, '30s'), (60, '60s'), (90, '90s'), (120, '120s')]:
        if t <= max(times_sec):
            ax.axvline(x=t, color='gray', linestyle=':', alpha=0.3)
            ax.text(t, ax.get_ylim()[1], label, ha='center', va='bottom', fontsize=8)
    
    # Add metrics box
    metrics_text = f"""Interval #{interval_num}
Duration: {interval.duration_seconds}s
Peak HR: {interval.hr_peak} bpm
Pre-peak avg: {interval.effort_avg_hr or '?'} bpm
Sustained effort: {interval.sustained_effort_sec or '?'}s

HRR30: {interval.hrr30_abs or '?'} bpm ({interval.hrr30_frac:.2f if interval.hrr30_frac else '?'})
HRR60: {interval.hrr60_abs or '?'} bpm ({interval.hrr60_frac:.2f if interval.hrr60_frac else '?'})
Total drop: {interval.total_drop or '?'} bpm
Recovery ratio: {interval.recovery_ratio:.2f if interval.recovery_ratio else '?'}

τ: {interval.tau_seconds:.1f}s (R²={interval.tau_fit_r2:.3f})
""" if interval.tau_seconds else f"""Interval #{interval_num}
Duration: {interval.duration_seconds}s
Peak HR: {interval.hr_peak} bpm
HRR60: {interval.hrr60_abs or '?'} bpm
(Exp fit failed)
"""
    
    ax.text(0.98, 0.98, metrics_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
            family='monospace')
    
    ax.set_xlabel('Time since peak (seconds)')
    ax.set_ylabel('Heart Rate (bpm)')
    ax.set_title(f'Recovery Interval #{interval_num} Detail')
    ax.legend(loc='lower right')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved detail plot to: {output_path}")
    
    if show:
        plt.show()
    
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Visualize HR session with recovery intervals')
    parser.add_argument('--session-id', type=int, required=True, help='Session ID to visualize')
    parser.add_argument('--source', choices=['endurance', 'polar'], default='endurance',
                        help='Session source type')
    parser.add_argument('--output', '-o', type=str, help='Output file path (PNG)')
    parser.add_argument('--detail', type=int, help='Show detailed plot for specific interval number')
    parser.add_argument('--dist', action='store_true', help='Show HRR60 distribution (beeswarm)')
    parser.add_argument('--no-show', action='store_true', help='Do not display plot (just save)')
    
    args = parser.parse_args()
    
    config = HRRConfig()
    conn = get_db_connection()
    
    try:
        # Load samples
        print(f"Loading {args.source} session {args.session_id}...")
        samples = get_hr_samples(conn, args.session_id, args.source)
        if not samples:
            print("No HR samples found")
            return
        
        print(f"Loaded {len(samples)} samples")
        
        # Get RHR
        session_date = samples[0].timestamp
        rhr = get_rhr_for_date(conn, session_date)
        if rhr is None:
            rhr = 60
            print(f"No RHR found, using default {rhr}")
        else:
            print(f"Using RHR={rhr}")
        
        # Detect intervals
        intervals = detect_recovery_intervals(samples, rhr, config)
        print(f"Detected {len(intervals)} raw intervals")
        
        # Compute features
        for interval in intervals:
            compute_features(interval, config)
        
        # Filter by quality
        valid_intervals, noise_intervals, rejected_intervals = filter_quality_intervals(intervals, config)
        print(f"Classification: {len(valid_intervals)} valid, {len(noise_intervals)} noise, {len(rejected_intervals)} rejected")
        
        # Generate title
        duration_min = (samples[-1].timestamp - samples[0].timestamp).total_seconds() / 60
        title = f"{args.source.title()} Session {args.session_id} - {session_date.strftime('%Y-%m-%d')} ({duration_min:.0f} min)"
        
        if args.detail:
            # Show detail for specific interval (from raw list)
            if 1 <= args.detail <= len(intervals):
                interval = intervals[args.detail - 1]
                output_path = args.output or f"interval_{args.detail}_detail.png" if args.no_show else None
                plot_interval_detail(samples, interval, rhr, args.detail, output_path, not args.no_show)
            else:
                print(f"Invalid interval number. Valid range: 1-{len(intervals)}")
        elif args.dist:
            # Show HRR60 distribution
            output_path = args.output if args.output else None
            plot_hrr60_distribution(valid_intervals, title, output_path, not args.no_show)
        else:
            # Show full session with all three categories
            output_path = args.output if args.output else None
            plot_session_with_intervals(samples, valid_intervals, noise_intervals, rejected_intervals, 
                                        rhr, config, title, output_path, not args.no_show)
    
    finally:
        conn.close()


if __name__ == '__main__':
    main()
