#!/usr/bin/env python3
"""
HRR Sensitivity Analysis

For every scipy-detected peak, calculate R² of exponential fit at:
15s, 30s, 45s, 60s, 90s, 120s

Output to CSV for analysis.
"""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy.ndimage import median_filter
from scipy.signal import find_peaks
from scipy.optimize import curve_fit

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


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


def smooth(hr: np.ndarray, k: int = 5) -> np.ndarray:
    if len(hr) < k:
        return hr.copy()
    med = median_filter(hr, size=k, mode='nearest')
    kernel = np.ones(k) / k
    return np.convolve(med, kernel, mode='same')


def exp_decay(t, hr_final, delta_hr, tau):
    """HR(t) = hr_final + delta_hr * exp(-t/tau)"""
    return hr_final + delta_hr * np.exp(-t / tau)


def fit_exponential(hr_window: np.ndarray) -> Tuple[float, float, str]:
    """
    Fit exponential decay to HR window.
    Returns (r2, tau, error_msg)
    """
    n = len(hr_window)
    if n < 5:
        return 0.0, 0.0, "too_short"
    
    t = np.arange(n)
    hr_peak = hr_window[0]
    hr_final = hr_window[-1]
    
    # Check if there's any descent
    if hr_final >= hr_peak:
        return 0.0, 0.0, "no_descent"
    
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
        tau = popt[2]
        
        return r2, tau, ""
        
    except Exception as e:
        return 0.0, 0.0, str(e)[:30]


def fit_linear(hr_window: np.ndarray) -> Tuple[float, float, float]:
    """
    Fit linear model to HR window.
    Returns (r2, slope, intercept)
    """
    n = len(hr_window)
    if n < 3:
        return 0.0, 0.0, 0.0
    
    t = np.arange(n)
    
    # Linear regression
    slope, intercept = np.polyfit(t, hr_window, 1)
    predicted = slope * t + intercept
    
    ss_res = np.sum((hr_window - predicted) ** 2)
    ss_tot = np.sum((hr_window - np.mean(hr_window)) ** 2)
    
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    return r2, slope, intercept


def test_initial_descent(hr: np.ndarray, peak_idx: int, window_len: int = 15) -> Tuple[bool, float, float]:
    """
    15-second linear fit test for initial descent.
    Same logic as hrr_simple.py.
    
    Requirements:
    - Slope must be negative (descending)
    - R² > 0.5 (decent fit, not noise)
    
    Returns: (passed, slope, r2)
    """
    n = len(hr)
    end = min(peak_idx + window_len, n - 1)
    
    if end - peak_idx < 10:
        return False, 0.0, 0.0
    
    window = hr[peak_idx:end + 1]
    t = np.arange(len(window))
    
    # Linear regression
    slope, intercept = np.polyfit(t, window, 1)
    predicted = slope * t + intercept
    
    ss_res = np.sum((window - predicted) ** 2)
    ss_tot = np.sum((window - np.mean(window)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    # Must be descending with decent fit
    passed = slope < 0 and r2 >= 0.5
    
    return passed, slope, r2


def analyze_peak(hr: np.ndarray, peak_idx: int, windows: list[int]) -> dict:
    """
    Analyze a single peak at multiple window lengths.
    Returns dict with R² values at each window.
    """
    n = len(hr)
    peak_hr = hr[peak_idx]
    
    result = {
        'peak_idx': peak_idx,
        'peak_time_min': peak_idx / 60,
        'peak_hr': peak_hr,
    }
    
    for w in windows:
        end_idx = peak_idx + w
        if end_idx >= n:
            result[f'r2_exp_{w}s'] = None
            result[f'r2_lin_{w}s'] = None
            result[f'tau_{w}s'] = None
            result[f'slope_{w}s'] = None
            result[f'hrr_{w}s'] = None
            result[f'nadir_{w}s'] = None
            continue
        
        window = hr[peak_idx:end_idx + 1]
        
        # Exponential fit
        r2_exp, tau, err = fit_exponential(window)
        result[f'r2_exp_{w}s'] = round(r2_exp, 3) if r2_exp else None
        result[f'tau_{w}s'] = round(tau, 1) if tau else None
        
        # Linear fit
        r2_lin, slope, _ = fit_linear(window)
        result[f'r2_lin_{w}s'] = round(r2_lin, 3)
        result[f'slope_{w}s'] = round(slope, 3)
        
        # HRR value
        result[f'hrr_{w}s'] = round(peak_hr - hr[end_idx], 1)
        
        # Nadir in window
        nadir = np.min(window)
        result[f'nadir_{w}s'] = round(peak_hr - nadir, 1)
    
    return result


def plot_threshold_analysis(df: pd.DataFrame, session_id: int, age: int = None, hide_rejected: bool = False):
    """
    Plot peak_hr vs R² at 60s to find recovery activation threshold.
    
    Only includes peaks with valid R² at 60s (meaning they lasted 60+ seconds).
    
    Research basis: Meaningful parasympathetic-mediated HRR requires exercise
    intensity high enough to substantially suppress vagal tone. This occurs at
    approximately ≥70% HRmax (≈50-60% VO₂max), roughly at/above VT1.
    
    Below this threshold, HR drifts back gently without exponential decay
    because the autonomic system wasn't strongly perturbed.
    
    References:
    - Frontiers in Physiology 2017: https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2017.00301/full
    - PMC8548865: https://pmc.ncbi.nlm.nih.gov/articles/PMC8548865/
    - PubMed 27617566: https://pubmed.ncbi.nlm.nih.gov/27617566/
    """
    import matplotlib.pyplot as plt
    
    # Calculate age-predicted max HR and research-based threshold
    hr_max = None
    hr_threshold_research = None
    if age:
        # Tanaka et al. (2001) - more accurate for active adults
        hr_max = 208 - (0.7 * age)
        # Research-based threshold: ~70% HRmax for meaningful HRR
        hr_threshold_research = 0.70 * hr_max
        print(f"\nAge-predicted max HR (Tanaka): {hr_max:.0f} bpm (age={age})")
        print(f"Research-based HRR threshold (70% max): {hr_threshold_research:.0f} bpm")
        print(f"  Below {hr_threshold_research:.0f}: vagal tone substantial, expect gentle drift")
        print(f"  Above {hr_threshold_research:.0f}: vagal withdrawal, expect exponential decay")
    
    # Filter to peaks with valid R² at 60s (they lasted at least 60s)
    plot_df = df[['peak_hr', 'r2_exp_60s', 'hrr_60s']].dropna()
    
    print(f"\nThreshold analysis: {len(plot_df)} peaks lasted 60+ seconds (of {len(df)} total)")
    
    if len(plot_df) < 3:
        print("Not enough data points for threshold analysis")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Categorize points
    valid = plot_df[(plot_df['r2_exp_60s'] >= 0.7) & (plot_df['hrr_60s'] >= 9)]
    rejected = plot_df[~((plot_df['r2_exp_60s'] >= 0.7) & (plot_df['hrr_60s'] >= 9))]
    
    print(f"  Valid (R²≥0.7 & HRR≥9): {len(valid)}")
    print(f"  Below threshold: {len(rejected)}")
    
    # Plot 1: Peak HR vs R²
    ax1 = axes[0]
    
    # Plot rejected as hollow circles (unless hidden)
    if len(rejected) > 0 and not hide_rejected:
        ax1.scatter(rejected['peak_hr'], rejected['r2_exp_60s'],
                   c='gray', s=80, alpha=0.5, edgecolors='black', linewidth=1,
                   label=f'Below criteria (n={len(rejected)})')
    
    # Plot valid as filled circles colored by HRR
    if len(valid) > 0:
        scatter = ax1.scatter(valid['peak_hr'], valid['r2_exp_60s'], 
                              c=valid['hrr_60s'], cmap='viridis', 
                              s=100, alpha=0.9, edgecolors='black', linewidth=1.5,
                              label=f'Valid (n={len(valid)})')
        cbar = plt.colorbar(scatter, ax=ax1)
        cbar.set_label('HRR60 (bpm)', fontsize=10)
    
    ax1.axhline(y=0.7, color='red', linestyle='--', alpha=0.5, label='R²=0.7')
    ax1.set_xlabel('Peak HR (bpm)', fontsize=12)
    ax1.set_ylabel('R² at 60s (exponential fit)', fontsize=12)
    ax1.set_title('Recovery Signal Quality vs Peak HR', fontsize=14)
    ax1.set_ylim(-0.1, 1.1)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='lower right')
    
    # Plot 2: Peak HR vs HRR60
    ax2 = axes[1]
    
    if len(rejected) > 0 and not hide_rejected:
        ax2.scatter(rejected['peak_hr'], rejected['hrr_60s'],
                   c='gray', s=80, alpha=0.5, edgecolors='black', linewidth=1,
                   label=f'Below criteria')
    
    if len(valid) > 0:
        scatter2 = ax2.scatter(valid['peak_hr'], valid['hrr_60s'],
                               c=valid['r2_exp_60s'], cmap='RdYlGn',
                               s=100, alpha=0.9, edgecolors='black', linewidth=1.5,
                               vmin=0.5, vmax=1, label=f'Valid')
        cbar2 = plt.colorbar(scatter2, ax=ax2)
        cbar2.set_label('R² at 60s', fontsize=10)
    
    ax2.axhline(y=9, color='red', linestyle='--', alpha=0.5, label='HRR60=9')
    ax2.set_xlabel('Peak HR (bpm)', fontsize=12)
    ax2.set_ylabel('HRR60 (bpm)', fontsize=12)
    ax2.set_title('Recovery Magnitude vs Peak HR', fontsize=14)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='lower right')
    
    # Add age-predicted max HR reference lines if available
    if hr_max:
        # Zone boundaries (% of max HR)
        zones = {
            'Z5 (90-100%)': (0.90 * hr_max, 0.90),
            'Z4 (80-90%)': (0.80 * hr_max, 0.80),
            'Z3 (70-80%)': (0.70 * hr_max, 0.70),
            'Z2 (60-70%)': (0.60 * hr_max, 0.60),
        }
        
        for ax in [ax1, ax2]:
            # Max HR line
            ax.axvline(x=hr_max, color='red', linestyle='-', linewidth=1.5, alpha=0.6)
            ax.text(hr_max + 1, ax.get_ylim()[1] * 0.95, f'Max\n{hr_max:.0f}', 
                   fontsize=8, color='red', va='top')
            
            # Research-based threshold (70% HRmax) - prominent
            ax.axvline(x=hr_threshold_research, color='blue', linestyle='-', linewidth=2, alpha=0.7)
            
            # Zone lines (lighter)
            for zone_name, (hr_val, pct) in zones.items():
                if abs(hr_val - hr_threshold_research) > 5:  # Don't overlap with threshold
                    ax.axvline(x=hr_val, color='gray', linestyle='--', linewidth=0.8, alpha=0.4)
        
        # Label threshold on ax1
        ax1.text(hr_threshold_research - 2, 0.5, f'70% HRmax\n{hr_threshold_research:.0f}bpm\n(research)', 
                fontsize=9, color='blue', ha='right', 
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    # Calculate and display empirical threshold estimate
    if len(valid) > 0:
        threshold_empirical = valid['peak_hr'].min()
        
        if hr_max:
            pct_of_max = (threshold_empirical / hr_max) * 100
            
            # Compare empirical to research-based
            diff = threshold_empirical - hr_threshold_research
            if abs(diff) < 5:
                comparison = "matches research prediction"
            elif diff > 0:
                comparison = f"{diff:.0f}bpm above research prediction"
            else:
                comparison = f"{abs(diff):.0f}bpm below research prediction"
            
            print(f"\n*** EMPIRICAL THRESHOLD: {threshold_empirical:.0f} bpm ({pct_of_max:.0f}% of max) ***")
            print(f"    Research prediction: {hr_threshold_research:.0f} bpm (70% of max)")
            print(f"    Comparison: {comparison}")
            
            # Show empirical as green dotted line
            ax1.axvline(x=threshold_empirical, color='green', linestyle=':', linewidth=2, alpha=0.7)
            ax1.text(threshold_empirical + 2, 0.2, f'Empirical\n{threshold_empirical:.0f}bpm\n({pct_of_max:.0f}% max)', 
                    fontsize=9, color='green',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        else:
            print(f"\n*** EMPIRICAL THRESHOLD: {threshold_empirical:.0f} bpm ***")
            print(f"    (Lowest peak HR with R²≥0.7 & HRR≥9)")
            ax1.axvline(x=threshold_empirical, color='green', linestyle=':', linewidth=2, alpha=0.7)
            ax1.text(threshold_empirical + 1, 0.15, f'Empirical\n≈{threshold_empirical:.0f}bpm', 
                    fontsize=10, color='green')
    
    # Build title with age info if available
    if hr_max:
        if hide_rejected:
            title = f'Session {session_id} - Recovery Threshold Analysis (age {age}, max HR {hr_max:.0f})\n({len(valid)} valid intervals shown, {len(rejected)} rejected hidden)'
        else:
            title = f'Session {session_id} - Recovery Threshold Analysis (age {age}, max HR {hr_max:.0f})\n({len(plot_df)} peaks passed descent test AND reached 60s)'
    else:
        title = f'Session {session_id} - Recovery Threshold Analysis\n({len(plot_df)} peaks passed descent test AND reached 60s)'
    
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    output_path = f'/tmp/hrr_threshold_{session_id}.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nSaved threshold plot: {output_path}")
    plt.show()
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='HRR Sensitivity Analysis')
    parser.add_argument('--session-id', type=int, required=True)
    parser.add_argument('--output', type=str, default='/tmp/hrr_sensitivity.csv')
    parser.add_argument('--prominence', type=float, default=5.0)
    parser.add_argument('--distance', type=int, default=10)
    parser.add_argument('--smooth-kernel', type=int, default=5)
    parser.add_argument('--windows', type=str, default='15,30,45,60,90,120',
                       help='Comma-separated window lengths in seconds')
    parser.add_argument('--plot-threshold', action='store_true',
                       help='Generate peak_hr vs R² scatter to find recovery threshold')
    parser.add_argument('--age', type=int, default=50,
                       help='Age for predicted max HR calculation (default: 50)')
    parser.add_argument('--hide-rejected', action='store_true',
                       help='Hide gray rejected points on threshold plot (cleaner for multi-session)')
    
    args = parser.parse_args()
    
    windows = [int(w) for w in args.windows.split(',')]
    
    conn = get_db_connection()
    ts, hr, dts = load_session(conn, args.session_id)
    conn.close()
    
    if hr is None:
        print(f"No data for session {args.session_id}")
        return
    
    print(f"Loaded session {args.session_id}: {len(hr)} samples, {ts[-1]/60:.0f} minutes")
    
    # Smooth
    hr_smooth = smooth(hr, args.smooth_kernel)
    
    # Find peaks
    peaks, props = find_peaks(hr_smooth, prominence=args.prominence, distance=args.distance)
    print(f"Found {len(peaks)} scipy peaks (prominence={args.prominence}, distance={args.distance})")
    
    # Filter peaks through initial descent test
    valid_peaks = []
    for peak_idx in peaks:
        passed, slope, r2_init = test_initial_descent(hr_smooth, peak_idx)
        if passed:
            valid_peaks.append(peak_idx)
    
    print(f"Passed initial descent test: {len(valid_peaks)} peaks (slope<0, R²≥0.5 over 15s)")
    
    # Analyze each validated peak
    results = []
    for peak_idx in valid_peaks:
        result = analyze_peak(hr_smooth, peak_idx, windows)
        results.append(result)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Save to CSV
    df.to_csv(args.output, index=False)
    print(f"\nSaved to {args.output}")
    
    # Print summary
    print(f"\n{'='*80}")
    print("SUMMARY: R² values at each window")
    print('='*80)
    
    # Show first 20 peaks
    cols_to_show = ['peak_time_min', 'peak_hr', 'hrr_60s']
    for w in windows:
        cols_to_show.append(f'r2_exp_{w}s')
    
    available_cols = [c for c in cols_to_show if c in df.columns]
    print(df[available_cols].head(30).to_string())
    
    # Stats on R² at 60s
    if 'r2_exp_60s' in df.columns:
        valid_r2 = df['r2_exp_60s'].dropna()
        print(f"\nR² at 60s: min={valid_r2.min():.2f}, max={valid_r2.max():.2f}, "
              f"mean={valid_r2.mean():.2f}, median={valid_r2.median():.2f}")
    
    # Show peaks with high R² at 60s
    if 'r2_exp_60s' in df.columns and 'hrr_60s' in df.columns:
        good = df[(df['r2_exp_60s'] > 0.7) & (df['hrr_60s'] > 9)]
        print(f"\nPeaks with R²>0.7 AND HRR60>9: {len(good)}")
        if len(good) > 0:
            print(good[available_cols].to_string())
    
    # Generate threshold plot if requested
    if args.plot_threshold:
        plot_threshold_analysis(df, args.session_id, age=args.age, hide_rejected=args.hide_rejected)


if __name__ == '__main__':
    main()
