#!/usr/bin/env python3
"""
Cross-reference extrapolation residuals with peak/valley detection
to see if both approaches catch the same problems.
"""

import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Load both datasets
extrap = pd.read_csv(PROJECT_ROOT / 'outputs/hrr_extrapolation_results.csv')
quality = pd.read_csv(PROJECT_ROOT / 'outputs/hrr_quality_all_diffs.csv')

print("=" * 70)
print("CROSS-REFERENCE: Extrapolation Residuals vs Peak/Valley Detection")
print("=" * 70)

# Rename to match
quality = quality.rename(columns={'id': 'interval_id'})

# Merge on interval_id
merged = extrap.merge(quality, on='interval_id', how='inner', suffixes=('_ext', '_qual'))
print(f"\nMerged: {len(merged)} intervals (extrap: {len(extrap)}, quality: {len(quality)})")

# Debug: show columns
print(f"\nColumns from quality CSV: {[c for c in merged.columns if 'valley' in c.lower() or 'run' in c.lower() or 'r2' in c.lower()]}")

# Key metrics from each approach
# Extrapolation: resid_60, late_residual_trend, accumulated_error
# Quality: valley_detected, valley_positions, max_positive_run_sec

# Use the actual column names from the quality CSV
# valley_detected is already boolean
# valley_positions contains the position(s)

# Parse first valley position for analysis
def get_first_valley_pos(pos_str):
    if pd.isna(pos_str) or pos_str == '':
        return None
    try:
        return int(float(str(pos_str).split(',')[0]))
    except:
        return None

merged['first_valley_pos'] = merged['valley_positions'].apply(get_first_valley_pos)
merged['valley_in_60s'] = merged['first_valley_pos'].apply(
    lambda x: x is not None and x <= 60
)

# Peak detection - this is the real signal
merged['has_peak_in_interval'] = merged['peak_in_interval'].fillna(False).astype(bool)
merged['has_peak_near_end'] = merged['peak_near_end'].fillna(False).astype(bool)

# Significant positive run as proxy for rise detection
merged['significant_positive_run'] = merged['max_positive_run_sec'] >= 10

print("\n" + "=" * 70)
print("CORRELATION ANALYSIS")
print("=" * 70)

# Group 1: High residual intervals (|resid_60| > 5)
high_resid = merged[merged['resid_60'].abs() > 5]
normal_resid = merged[merged['resid_60'].abs() <= 5]

print(f"\nHigh residual (|resid_60| > 5): {len(high_resid)} intervals")
print(f"Normal residual (|resid_60| <= 5): {len(normal_resid)} intervals")

print(f"\n{'Metric':<35} {'High Resid':>12} {'Normal':>12} {'Ratio':>8}")
print("-" * 70)

for metric, col in [
    ('Valley detected (pos <= 60)', 'valley_in_60s'),
    ('PEAK in interval', 'has_peak_in_interval'),
    ('Peak near end (57-63s)', 'has_peak_near_end'),
    ('Significant positive run (>=10s)', 'significant_positive_run'),
    ('R² < 0.85', lambda df: df['r2_60'] < 0.85),
]:
    if callable(col):
        hr_rate = col(high_resid).mean() * 100
        nr_rate = col(normal_resid).mean() * 100
    else:
        hr_rate = high_resid[col].mean() * 100
        nr_rate = normal_resid[col].mean() * 100
    
    ratio = hr_rate / nr_rate if nr_rate > 0 else float('inf')
    print(f"{metric:<35} {hr_rate:>10.1f}% {nr_rate:>10.1f}% {ratio:>7.1f}x")

# Group 2: Late trend analysis
print(f"\n{'Late residual trend > 0.1 (getting worse):':<45}")
late_trend_bad = merged[merged['late_residual_trend'] > 0.1]
late_trend_ok = merged[merged['late_residual_trend'] <= 0.1]

print(f"  Bad trend: {len(late_trend_bad)} intervals")
print(f"  OK trend: {len(late_trend_ok)} intervals")

print(f"\n{'Metric':<35} {'Bad Trend':>12} {'OK Trend':>12} {'Ratio':>8}")
print("-" * 70)

for metric, col in [
    ('Valley detected (pos <= 60)', 'valley_in_60s'),
    ('PEAK in interval', 'has_peak_in_interval'),
    ('Peak near end (57-63s)', 'has_peak_near_end'),
    ('Significant positive run (>=10s)', 'significant_positive_run'),
    ('R² < 0.85', lambda df: df['r2_60'] < 0.85),
]:
    if callable(col):
        bt_rate = col(late_trend_bad).mean() * 100
        ot_rate = col(late_trend_ok).mean() * 100
    else:
        bt_rate = late_trend_bad[col].mean() * 100
        ot_rate = late_trend_ok[col].mean() * 100
    
    ratio = bt_rate / ot_rate if ot_rate > 0 else float('inf')
    print(f"{metric:<35} {bt_rate:>10.1f}% {ot_rate:>10.1f}% {ratio:>7.1f}x")

print("\n" + "=" * 70)
print("OVERLAP ANALYSIS: Do both methods catch the same problems?")
print("=" * 70)

# Define "flagged" by each method
merged['flagged_by_extrap'] = (merged['resid_60'].abs() > 5) | (merged['late_residual_trend'] > 0.1)
merged['flagged_by_detection'] = merged['valley_in_60s'] | merged['significant_positive_run'] | merged['has_peak_in_interval']

# Separate peak-specific analysis
merged['flagged_by_peak'] = merged['has_peak_in_interval'] | merged['has_peak_near_end']

both = merged[merged['flagged_by_extrap'] & merged['flagged_by_detection']]
extrap_only = merged[merged['flagged_by_extrap'] & ~merged['flagged_by_detection']]
detection_only = merged[~merged['flagged_by_extrap'] & merged['flagged_by_detection']]
neither = merged[~merged['flagged_by_extrap'] & ~merged['flagged_by_detection']]

print(f"\n  Flagged by BOTH methods:        {len(both):>4} ({len(both)/len(merged)*100:.1f}%)")
print(f"  Flagged by EXTRAPOLATION only:  {len(extrap_only):>4} ({len(extrap_only)/len(merged)*100:.1f}%)")
print(f"  Flagged by DETECTION only:      {len(detection_only):>4} ({len(detection_only)/len(merged)*100:.1f}%)")
print(f"  Flagged by NEITHER:             {len(neither):>4} ({len(neither)/len(merged)*100:.1f}%)")

# Jaccard similarity
union = len(both) + len(extrap_only) + len(detection_only)
jaccard = len(both) / union if union > 0 else 0
print(f"\n  Jaccard similarity: {jaccard:.2f} (0=no overlap, 1=perfect overlap)")

# PEAK-SPECIFIC ANALYSIS
print("\n" + "=" * 70)
print("PEAK-SPECIFIC ANALYSIS (peaks are stronger signal than valleys)")
print("=" * 70)

has_peak = merged[merged['has_peak_in_interval'] == True]
no_peak = merged[merged['has_peak_in_interval'] == False]

print(f"\nIntervals with PEAK in interval: {len(has_peak)} ({len(has_peak)/len(merged)*100:.1f}%)")
print(f"Intervals without peak: {len(no_peak)} ({len(no_peak)/len(merged)*100:.1f}%)")

if len(has_peak) > 0:
    print(f"\n{'Metric':<35} {'Has Peak':>12} {'No Peak':>12} {'Ratio':>8}")
    print("-" * 70)
    
    # Residual analysis for peaks
    for metric, fn in [
        ('|Residual @ 60s| > 5 bpm', lambda df: (df['resid_60'].abs() > 5).mean() * 100),
        ('|Residual @ 60s| > 10 bpm', lambda df: (df['resid_60'].abs() > 10).mean() * 100),
        ('Late trend > 0.1', lambda df: (df['late_residual_trend'] > 0.1).mean() * 100),
        ('R² < 0.85', lambda df: (df['r2_60'] < 0.85).mean() * 100),
    ]:
        hp_rate = fn(has_peak)
        np_rate = fn(no_peak)
        ratio = hp_rate / np_rate if np_rate > 0 else float('inf')
        print(f"{metric:<35} {hp_rate:>10.1f}% {np_rate:>10.1f}% {ratio:>7.1f}x")
    
    print(f"\nMean |residual @ 60s|: has_peak={has_peak['resid_60'].abs().mean():.1f} bpm, no_peak={no_peak['resid_60'].abs().mean():.1f} bpm")
    
    # Show the peak intervals
    print(f"\n{'ID':>4} {'Sess':>4} {'HRR60':>6} {'R²':>6} {'Resid60':>8} {'LateTrend':>10} {'PkPos':>8}")
    print("-" * 60)
    for _, r in has_peak.head(10).iterrows():
        pk_pos = r.get('peak_positions', '-')
        hrr60 = int(r['hrr60_recorded']) if pd.notna(r['hrr60_recorded']) else 0
        print(f"{int(r['interval_id']):>4} {int(r['session_id_ext']):>4} {hrr60:>6} "
              f"{r['r2_60']:.3f} {r['resid_60']:>8.1f} {r['late_residual_trend']:>10.3f} "
              f"{str(pk_pos):>8}")

print("\n" + "=" * 70)
print("EXTRAPOLATION-ONLY FLAGS (Detection missed these)")
print("=" * 70)

if len(extrap_only) > 0:
    print(f"\n{'ID':>4} {'Sess':>4} {'HRR60':>6} {'R²':>6} {'Resid60':>8} {'LateTrend':>10} {'VPos':>6} {'Peak':>5} {'RunLen':>7}")
    print("-" * 75)
    for _, r in extrap_only.head(15).iterrows():
        vpos = f"{r['first_valley_pos']:.0f}" if pd.notna(r['first_valley_pos']) else "-"
        hrr60 = int(r['hrr60_recorded']) if pd.notna(r['hrr60_recorded']) else 0
        has_pk = "Y" if r['has_peak_in_interval'] else "-"
        print(f"{int(r['interval_id']):>4} {int(r['session_id_ext']):>4} {hrr60:>6} "
              f"{r['r2_60']:.3f} {r['resid_60']:>8.1f} {r['late_residual_trend']:>10.3f} "
              f"{vpos:>6} {has_pk:>5} {int(r['max_positive_run_sec']):>7}")

print("\n" + "=" * 70)
print("DETECTION-ONLY FLAGS (Extrapolation missed these)")
print("=" * 70)

if len(detection_only) > 0:
    print(f"\n{'ID':>4} {'Sess':>4} {'HRR60':>6} {'R²':>6} {'Resid60':>8} {'LateTrend':>10} {'VPos':>6} {'Peak':>5} {'RunLen':>7}")
    print("-" * 75)
    for _, r in detection_only.head(15).iterrows():
        vpos = f"{r['first_valley_pos']:.0f}" if pd.notna(r['first_valley_pos']) else "-"
        hrr60 = int(r['hrr60_recorded']) if pd.notna(r['hrr60_recorded']) else 0
        has_pk = "Y" if r['has_peak_in_interval'] else "-"
        print(f"{int(r['interval_id']):>4} {int(r['session_id_ext']):>4} {hrr60:>6} "
              f"{r['r2_60']:.3f} {r['resid_60']:>8.1f} {r['late_residual_trend']:>10.3f} "
              f"{vpos:>6} {has_pk:>5} {int(r['max_positive_run_sec']):>7}")

print("\n" + "=" * 70)
print("R² CORRELATION")
print("=" * 70)

# Does low R² correlate with high residuals?
# r2_60 exists directly in quality CSV
corr_cols = ['r2_60', 'resid_60', 'accumulated_error', 'late_residual_trend']
available_cols = [c for c in corr_cols if c in merged.columns]
if len(available_cols) >= 2:
    corr = merged[available_cols].corr()
    print("\nCorrelation matrix:")
    print(corr.round(3).to_string())
else:
    print(f"\nInsufficient columns for correlation. Available: {available_cols}")

# Summary recommendation
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Calculate peak impact
peak_count = merged['has_peak_in_interval'].sum()
peak_pct = peak_count / len(merged) * 100 if len(merged) > 0 else 0

print(f"""
Methods flagging:
- Extrapolation (|resid_60|>5 OR late_trend>0.1): {merged['flagged_by_extrap'].sum()} intervals
- Detection (valley OR positive_run>=10s OR peak): {merged['flagged_by_detection'].sum()} intervals
- Peak-only: {peak_count} intervals ({peak_pct:.1f}%)

Overlap: {jaccard:.0%} - {'complementary (use both)' if jaccard < 0.5 else 'moderate overlap'}

Key insight:
- Valleys without peaks: {merged['valley_in_60s'].sum() - merged[merged['valley_in_60s'] & merged['has_peak_in_interval']].shape[0]} intervals
- Peaks (hard fail): {peak_count} intervals
- PEAK is the strongest quality signal - a peak during recovery = definitive problem
""")
