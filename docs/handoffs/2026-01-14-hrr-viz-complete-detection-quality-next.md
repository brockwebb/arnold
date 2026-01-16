# HRR Handoff: Visualization Complete, Detection Quality Next

**Date**: 2026-01-14
**Previous transcript**: `/mnt/transcripts/2026-01-14-17-00-20-hrr-qc-viz-refinement-zones-markers.txt`
**Status**: Phase 2.5 (visualization) complete, Phase 3 (detection quality) identified

---

## What Was Accomplished

### Phase 1: Extended Window Detection (Previous Session)
- Migration 015: Added hr_180s/240s/300s, hrr180/240/300_abs, r2_180/240/300, tau_censored
- hrr_batch.py: Extended window cap 120s→300s, tau upper bound 300s→600s

### Phase 2: Deliberate Test Annotation (Previous Session)
- Migration 016: Added is_deliberate, preceding_activity, notes columns
- hrr_batch.py: Added `--session-id` flag for targeted processing
- Session 71 annotated as first deliberate 5-min supine test

### Phase 2.5: Visualization Overhaul (This Session)
Complete rewrite of `hrr_qc_viz.py`:

**Visual elements:**
| Element | Style |
|---------|-------|
| HR trace | Blue line |
| Karvonen zones (Z1-Z5, Max) | Colored dashed lines, labels on left |
| VT1 (70% HRmax) | Black dashed line, label on left |
| Unused peaks | Gray ▼ (markersize=5, alpha=0.4) |
| Rejected intervals | Red ▼ + gray 60s window |
| HRR60 intervals | Green ▼ + green 60s window |
| HRR120 intervals | Goldenrod ▼ + gold 120s window |
| HRR300 intervals | Purple ▼ + plum window (actual duration) |

**Y-axis scaling:**
- Top: Round up to nearest 10 above HRmax
- Bottom: Round down to nearest 10 below (Z1 - 20)
- Example (age 50, RHR 55): 90-180 bpm

**Removed chart junk (Tufte principles):**
- No legend (colors self-evident, subitizing handles counts)
- No subtitle counts
- No vertical blue peak lines
- Consistent marker sizes

**CLI:**
```bash
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55 --details
python scripts/hrr_qc_viz.py --list
```

---

## Problem Identified: Detection Quality

Session 71, interval around minute 22-23 shows a **5 bpm upward bounce** mid-recovery that passed quality gates (R²=0.89). This is physiologically suspicious - true parasympathetic recovery should be monotonic.

**Current quality gates (hrr_batch.py):**
1. R² ≥ 0.75
2. Peak HR ≥ VT1 (70% HRmax, ~121 bpm for age 50)
3. HRR60 ≥ 9 bpm (for HRR60-only intervals)

**The gap:** R² measures fit quality but doesn't catch non-monotonicity. An exponential can fit "through" bounces while maintaining high R².

---

## Phase 3: Detection Quality Improvements

### Proposed Additional Quality Gates

1. **Max re-elevation threshold**
   - Reject if HR increases > X bpm at any point during window
   - Suggested: 3-4 bpm threshold
   - Catches movement artifacts, re-engagement

2. **Monotonicity score**
   - Count number/magnitude of upward segments
   - Penalize or reject intervals with significant non-monotonic behavior

3. **Residual pattern analysis**
   - Check for systematic vs random deviations from fit
   - Bounces create structured residuals, not random scatter

### Implementation Location
- File: `/Users/brock/Documents/GitHub/arnold/scripts/hrr_batch.py`
- Function: Likely in the interval analysis/quality assessment section
- May need new columns in hr_recovery_intervals for monotonicity metrics

### Test Cases
- Session 71: Has both clean intervals and the problematic bouncy one
- Good for A/B comparison of new gates

---

## Files Modified This Session

1. **`/Users/brock/Documents/GitHub/arnold/scripts/hrr_qc_viz.py`** - Complete visualization overhaul
   - Karvonen zone lines
   - VT1 line (70% HRmax, research threshold)
   - Consistent triangle markers
   - Clean y-axis scaling
   - No legend/counts

---

## Key Terminology Reference

| Term | Definition |
|------|------------|
| VT1 | Ventilatory Threshold 1, ~70% HRmax, minimum intensity for valid HRR research |
| Karvonen | HR zone formula using Heart Rate Reserve: Target = RHR + (HRR × %intensity) |
| HRR (metric) | Heart Rate Recovery - drop in bpm from peak at 60/120/300s |
| HRR (formula) | Heart Rate Reserve = HRmax - RHR (used in Karvonen) |
| R² | Coefficient of determination for exponential fit |
| Monotonicity | Property of continuously decreasing (no bounces) |

---

## Baseline Data (Session 71, Deliberate Test)

First "Tabata burpees → supine 5min" protocol:
- Peak: 171 bpm
- HRR60/120/300: 17/41/56 bpm
- Tau: 342s
- R²: 0.98

---

## Commands for Next Session

```bash
# View the visualization
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55

# Check interval details
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55 --details

# Reprocess after algorithm changes
python scripts/hrr_batch.py --session-id 71 --write-db --clear-existing
```
