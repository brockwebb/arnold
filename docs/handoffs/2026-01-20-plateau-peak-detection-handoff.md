# Plateau Peak Detection Handoff

**Date**: 2026-01-20
**Purpose**: Context for fixing plateau-induced bad HRR60 measurements
**Status**: Problem identified, solution approach proposed

---

## The Problem

Peak detection anchors on the wrong point when athletes decelerate gradually (plateaus). Current manual "peak shift" overrides produce terrible HRR60 values (0, 2, 8 bpm) because the shifted peak still isn't at the true maximum.

### Root Cause

When an athlete slows down gradually over 30+ seconds instead of stopping suddenly:
1. scipy `find_peaks()` detects a local maximum at the **end** of the plateau (not the true peak)
2. Current plateau detection only looks **forward** from detected peak
3. The true peak is **backwards** in time, sometimes 30-50+ seconds earlier

### Example (Session 22, Interval 3)

```
Time    HR      Pattern
-50s    134     ← TRUE PEAK (missed!)
-50→-25 134→132 Very slow initial decline  
-25→-17 132→126 Gradual deceleration
-17→0   126     Plateau
0s      126     ← DETECTED "peak" (wrong!)
0→60    126→113 "Recovery" from wrong baseline
```

**Result**: HRR60 measures 13 bpm (126→113) instead of 21 bpm (134→113). An 8 bpm error.

---

## Relevant GitHub Issues

| Issue | Title | Relevance |
|-------|-------|-----------|
| **#36** | Backward peak search for gradual deceleration | **Primary** - describes the exact solution |
| #38 | Missing obvious peaks (large gaps) | Related detection problem |
| #34 | Peak shift recomputation | Manual correction workflow |
| #24 | Monotonicity gate | Could help flag these patterns |

### Issue #36 Details (key content)

**Proposed Solution**: Search backwards from detected peak to find true maximum:

```python
def search_backward_for_true_peak(
    samples: List[HRSample],
    detected_peak_idx: int,
    config: HRRConfig,
    lookback_sec: int = 60  # You suggested 30, 60 is in the issue
) -> Tuple[int, str]:
    """
    Search backward from detected peak to find true maximum.
    
    Triggers when:
    - HR at detected peak is flat or declining for N seconds before
    - There's a higher HR value within lookback window
    """
    start_idx = max(0, detected_peak_idx - lookback_sec)
    lookback_hr = [s.hr_value for s in samples[start_idx:detected_peak_idx + 1]]
    
    detected_hr = samples[detected_peak_idx].hr_value
    max_hr = max(lookback_hr)
    
    # If there's a higher peak in the lookback window
    if max_hr > detected_hr + 3:  # At least 3 bpm higher
        max_indices = [i for i, hr in enumerate(lookback_hr) if hr == max_hr]
        true_peak_relative = max_indices[-1]  # LAST occurrence (end of plateau at true peak)
        true_peak_idx = start_idx + true_peak_relative
        return true_peak_idx, 'high'
    
    return detected_peak_idx, 'no_change'
```

**When to trigger backward search:**
1. HR at detected peak is within 5 bpm of HR 10 seconds before (flat approach)
2. HR slope in 10s before detected peak is negative (declining into "peak")
3. `r2_0_30` is poor despite no obvious forward plateau

---

## Current Codebase State

### Key Files

```
scripts/hrr/
├── detection.py      # Peak detection logic (scipy find_peaks)
├── reanchoring.py    # Plateau detection - FORWARD only currently
├── metrics.py        # R² and quality gates
├── types.py          # HRRConfig with parameters
└── cli.py            # Main extraction entry point
```

### Current Reanchoring (scripts/hrr/reanchoring.py)

Only looks **forward**:
- `find_peak_by_slope()` - finds where sustained negative slope begins
- `find_peak_by_geometry()` - binary search for inflection point
- `attempt_plateau_reanchor()` - orchestrates forward search

Missing: Any backward search capability.

### Quality Gates That Catch This (scripts/hrr/metrics.py)

- **Gate 5**: `r2_0_30 < 0.5` triggers `double_peak` rejection
  - Catches when first 30s doesn't fit exponential (plateau/rise pattern)
- But: If plateau is subtle, r2_0_30 might pass while HRR60 is still garbage

---

## Proposed Solution

### Option A: Simple Backward Search (Brock's Suggestion)

Add to `detection.py` or `reanchoring.py`:

```python
def search_backward_for_true_peak(
    samples: List[HRSample],
    detected_peak_idx: int,
    lookback_sec: int = 30
) -> int:
    """Find highest HR in lookback window before detected peak."""
    start_idx = max(0, detected_peak_idx - lookback_sec)
    
    # Get HR values in lookback window
    lookback_samples = samples[start_idx:detected_peak_idx + 1]
    if not lookback_samples:
        return detected_peak_idx
    
    # Find the maximum HR
    max_hr = max(s.hr_value for s in lookback_samples)
    detected_hr = samples[detected_peak_idx].hr_value
    
    # Only shift if significantly higher peak exists
    if max_hr > detected_hr + 3:
        # Find LAST index of max (handles plateaus at peak)
        for i in range(len(lookback_samples) - 1, -1, -1):
            if lookback_samples[i].hr_value == max_hr:
                return start_idx + i
    
    return detected_peak_idx
```

**Integration point**: Call after `find_peaks()` in `detection.py`:

```python
for peak_idx in valid_peaks:
    # NEW: Check for gradual deceleration pattern
    true_peak_idx = search_backward_for_true_peak(samples, peak_idx, lookback_sec=30)
    if true_peak_idx != peak_idx:
        logger.info(f"Backward search: peak shifted from {peak_idx} to {true_peak_idx}")
        peak_idx = true_peak_idx
    
    # Continue with existing logic...
    end_idx = find_recovery_end(samples, peak_idx, config)
```

### Option B: Conditional Triggering

Only search backward when indicators suggest a plateau:
- HR slope in 10s before detected peak is ≤ 0 (flat or declining)
- `r2_0_30` < 0.65 (not quite failing, but questionable)

This avoids shifting peaks that are correctly detected.

---

## Testing Strategy

### Existing QC Data

Before testing, check what manual corrections already exist:

```sql
-- View all peak adjustments
SELECT * FROM peak_adjustments;
```

**Current adjustments:**
| Session | Interval | Shift | Reason |
|---------|----------|-------|--------|
| 5 | 10 | +120s | Plateau anchor |
| 51 | 3 | +54s | False peak |

**Full QC query reference**: `/docs/hrr_quality_gates.md` → "Querying Existing QC Data" section

### Target Sessions

From QC review, these had plateau issues:
- **Session 22, Interval 3** - the documented example
- Check other rejected intervals with `auto_reject_reason = 'double_peak'`

### Verification Query

```sql
-- Find intervals that might benefit from backward search
SELECT 
    polar_session_id, 
    interval_order,
    peak_hr,
    hrr60,
    r2_0_30,
    quality_status,
    auto_reject_reason
FROM hr_recovery_intervals
WHERE r2_0_30 < 0.65
   OR auto_reject_reason = 'double_peak'
   OR (hrr60 IS NOT NULL AND hrr60 < 10)
ORDER BY polar_session_id, interval_order;
```

### Expected Outcomes

After backward search implementation:
1. S22:I3 peak shifts from sec 0 (126 bpm) to sec -50 (134 bpm)
2. HRR60 changes from 13 bpm to ~21 bpm
3. R² values should improve (measuring from true peak)
4. Some previously rejected intervals should pass

---

## Acceptance Criteria

- [ ] Backward search finds higher peaks within lookback window
- [ ] Only shifts when delta > threshold (3 bpm suggested)
- [ ] Existing valid peaks not affected (regression test)
- [ ] Session 22 Interval 3 produces HRR60 ~21 bpm (not 13)
- [ ] Logging shows when shifts occur for audit

---

## Limitations to Accept

Even with backward search:
- Very gradual declines (30+ bpm over 2+ minutes) may still be tricky
- Running data with continuous HR modulation may have many false plateaus
- This is a heuristic improvement, not a perfect solution

The goal is **better**, not perfect. Accept that some intervals will remain problematic.

---

## Files to Modify

1. `scripts/hrr/detection.py` - add backward search function
2. `scripts/hrr/detection.py` - integrate into peak processing loop
3. `scripts/hrr/types.py` - add config parameter `backward_lookback_sec`
4. Possibly `scripts/hrr/reanchoring.py` - if integrating with existing plateau logic
