# HRR Quality Gates Handoff - 2026-01-14

## Context

This thread continued work on HRR (Heart Rate Recovery) quality gating after the previous thread hit max length. The goal was to develop data-driven quality gates rather than hardcoded thresholds.

## Key Findings

### Two Detection Approaches Tested

1. **Peak/Valley Detection** - Detects structural anomalies in the HR trace
2. **Extrapolation Residuals** - Fits exponential to first 30s, compares predicted vs actual at 60s

### Cross-Reference Results (n=197 intervals)

| Method | Flagged |
|--------|---------|
| Extrapolation (|resid_60|>5 OR late_trend>0.1) | 132 |
| Detection (valley OR positive_run>=10s OR peak) | 140 |
| Peak-only | 18 (9.1%) |

**Jaccard overlap: 56%** - Methods catch related but different problems.

### Critical Insight: Peaks vs Valleys

**Peaks during recovery interval = definitive bad data**
- 18 intervals (9.1%) have peaks within the recovery window
- R² < 0.85 is 2.3x more common in peak intervals

**Valleys don't correlate with measurement error**
- High residual intervals are only 1.0x more likely to have valleys
- 70 intervals have valleys but no peaks
- Valley detection is over-flagging

### Extrapolation Statistics (n=301 intervals)

```
Residual at 60s (actual - predicted):
  Mean: -4.0 bpm (actual typically 4 bpm lower than predicted)
  Std:  7.1 bpm
  90th percentile: 4.9 bpm
  95th percentile: 7.7 bpm
  99th percentile: 11.1 bpm

Late residual trend (45-60s):
  Positive (residuals growing): 38.9%
  Strongly positive (>0.1): 27.6%
```

## Files Modified/Created

```
scripts/hrr_extrapolation_analysis.py  # Fixed decimal.Decimal → float, bounds logic
scripts/hrr_cross_reference.py         # New: compares detection vs extrapolation
outputs/hrr_extrapolation_results.csv  # 301 intervals with residual metrics
outputs/hrr_edge_cases_review.csv      # 96 edge cases with empty label column
outputs/hrr_quality_all_diffs.csv      # Quality metrics from detection approach
```

## Recommended Quality Gate Architecture

Based on the analysis:

### Tier 1: Hard Fail (reject interval)
- **Peak detected within recovery interval** (after initial 5s)
- Peak detected within ±10% of measurement point (e.g., 54-66s for HRR60)

### Tier 2: Confidence Adjustment (weight down, don't reject)
- **Residual at 60s > 5 bpm** → confidence × 0.8
- **Residual at 60s > 10 bpm** → confidence × 0.5
- **Late trend > 0.1** (45-60s residuals growing) → confidence × 0.9
- R² < 0.85 → existing penalty

### Tier 3: Informational (log but don't penalize)
- Valley detected (doesn't correlate with measurement error)
- Positive run length (unless associated with peak)

## What Still Needs Doing

1. **Manual labeling** - 96 edge cases in `hrr_edge_cases_review.csv` need human labels (good/bad/uncertain) to validate any gate
2. **Integrate residual metrics** - Add extrapolation residuals to `hr_recovery_intervals` table or compute on-the-fly in analytics
3. **Update confidence scoring** - Incorporate residual-based penalties into existing confidence calculation in `src/arnold/hrr/detect.py`
4. **Visual review tool** - Generate side-by-side plots of flagged intervals for labeling

## The Uncomfortable Truth

Without ground truth labels, we're tuning gates based on assumptions. The cross-reference shows both methods flag ~140 intervals (~70% of data) - that's too aggressive. Either:
- The thresholds are too sensitive
- Most of your training data genuinely has quality issues
- We need to accept more variance in real-world HRR measurements

**Recommendation:** Label 30-50 edge cases manually before further gate tuning. This gives ground truth to measure false positive/negative rates.

## Quick Commands

```bash
# Run extrapolation analysis
python scripts/hrr_extrapolation_analysis.py --output outputs/hrr_extrapolation_results.csv

# Run cross-reference
python scripts/hrr_cross_reference.py

# Visualize specific session
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55 --details

# Run quality explorer
python scripts/hrr_quality_explorer.py --output outputs/hrr_quality_check.csv
```

## Debug Notes

- `hrr_extrapolation_analysis.py` had two bugs fixed this session:
  1. Bounds were hardcoded (e.g., asymptote upper=120) causing 0% fit success
  2. HR values from Postgres came as `decimal.Decimal`, needed explicit `float()` cast
- Debug print statements left in place (can be removed)
