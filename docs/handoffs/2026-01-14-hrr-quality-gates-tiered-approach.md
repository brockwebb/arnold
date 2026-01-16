# HRR Handoff: Detection-Based Quality Gates - Tiered Approach

**Date**: 2026-01-14
**Issue**: [#24 - HRR detection: Add monotonicity gate to reject non-monotonic recovery curves](https://github.com/brockwebb/arnold/issues/24)
**Status**: Exploration complete, tiered solution designed, ready for implementation

---

## Context

Session 71 minute 22-23 interval showed R²=0.89 but had a clear mid-interval bounce (~15 bpm upswing). R² alone is insufficient - it measures fit quality but doesn't penalize non-monotonic behavior.

## Key Insight from Data Exploration

Ran `hrr_quality_explorer.py` on full dataset. **Critical finding:**

Most valleys detected are at 50-110 seconds - **after** the HRR60 measurement window. These are the start of the next work bout, not problems with the recovery measurement itself.

Valleys that actually matter (within first 60s):
- Interval 2: @42s
- Interval 5: @39s, @51s
- Interval 21: @35s
- Interval 47: @21s
- Interval 370: @45s ← **The known bad one from Session 71**

## Design Decision: Detection-Based, Not Threshold-Based

**Rejected approaches:**
- Absolute thresholds (e.g., ">8 bpm drawup") - too arbitrary, doesn't scale
- Percentage thresholds (e.g., ">10% drawup") - broken for small total drops where noise dominates

**Adopted approach:**
- Use scipy `find_peaks()` detectability as the signal
- If the algorithm detects a valley/peak, that's the flag
- Prominence parameter controls detection sensitivity, not pass/fail threshold

## Proposed Tiered Validation

### Tier 1: HRR60 Validation
- **Scope**: 0-60 seconds only
- **Valley check**: `find_peaks(-hr[0:60], prominence=5)` - if ANY valley detected, fail
- **Peak check**: `find_peaks(hr[5:60], prominence=5)` - if ANY peak detected after initial, fail
- **Binary**: pass/fail

### Tier 2: HRR120 Validation  
- **Prerequisite**: HRR60 must pass
- **Scope**: Check 60-120s window behavior
- **Method**: Late-window slope check, not valley detection (too strict for messy tail)
- **Logic**: Fit line to last 30s (90-120s), if slope > 0, flag it
- **Simple version**: `is hr[120] > hr[90]?` - net uptick in tail = bad
- **Tolerance**: Flat slope (≈0) is fine - that's asymptotic behavior

### Tier 3: HRR300 Deliberate Tests
- **Context**: Supine recovery, should be textbook exponential
- **Stricter validation**: Valley detection appropriate for full window
- **Alternative**: Check any 30s window after 60s for positive slope

## Files Created/Modified

### Created: `scripts/hrr_quality_explorer.py`
Detection-based quality gate exploration tool.

Current version computes:
- Valley detection (scipy find_peaks on inverted signal)
- Peak-in-interval detection
- Sustained positive run (informational)

**Needs updating** to implement tiered scoping (0-60s for HRR60, slope check for HRR120).

### Output files generated:
- `/Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_all.csv` - all intervals with metrics
- `/Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_all_diffs.csv` - intervals that would flip status

## Implementation Plan for Next Thread

### Step 1: Update `hrr_quality_explorer.py`
```python
# HRR60 validation: scope to 0-60s
def validate_hrr60(hr):
    hr_60 = hr[:61]  # First 60 seconds
    valleys, _ = find_peaks(-hr_60, prominence=5)
    peaks, _ = find_peaks(hr_60[5:], prominence=5)  # Skip initial peak
    return len(valleys) == 0 and len(peaks) == 0

# HRR120 validation: late slope check
def validate_hrr120(hr):
    if len(hr) < 121:
        return True  # Can't validate, pass by default
    late_slope = (hr[120] - hr[90]) / 30  # bpm/sec
    return late_slope <= 0  # Must be flat or declining
```

### Step 2: Re-run on full dataset
Verify:
- Known bad interval 370 fails HRR60 validation
- Most intervals that were failing due to late valleys now pass
- Detection rate is reasonable (not rejecting 75% of data)

### Step 3: Promote to `hrr_batch.py`
Once thresholds are validated:
- Add validation functions to hrr_batch.py
- Add new columns to hr_recovery_intervals if needed (e.g., `hrr60_valid`, `hrr120_valid`)
- Migration for schema changes

### Step 4: Update visualization
- `hrr_qc_viz.py` could show rejected intervals differently
- Maybe red shading for failed windows vs green for passed

## Test Commands

```bash
# Run explorer on specific session
python scripts/hrr_quality_explorer.py --session-id 71

# Run on full dataset
python scripts/hrr_quality_explorer.py --output /Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_all.csv

# Visualize specific session
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55 --details

# Reprocess after algorithm changes
python scripts/hrr_batch.py --session-id 71 --write-db --clear-existing
```

## Key Principles Established

1. **Detection-based, not threshold-based** - scipy's detectability IS the signal
2. **Tiered by measurement window** - HRR60 strict (0-60s), HRR120 lenient (slope check)
3. **Let data define normal** - collect good intervals, compute variance envelope, flag outliers
4. **Context matters** - inter-set recovery is noisy, deliberate 5-min supine should be clean

## Related Files

- `scripts/hrr_batch.py` - main batch processor, will receive validated gates
- `scripts/hrr_qc_viz.py` - visualization tool for manual review
- `config/hrr_defaults.json` - configuration values
- `docs/handoffs/2026-01-14-hrr-viz-complete-detection-quality-next.md` - previous handoff

---

## Summary for Next Thread

**Where we are:** Exploration complete. We know the pattern - valleys after 60s are next-bout starts, not recovery problems. Tiered validation approach designed.

**What's next:** 
1. Update explorer to scope HRR60 check to 0-60s
2. Add late-slope check for HRR120
3. Re-run on full dataset to validate approach
4. Promote to hrr_batch.py once confirmed

**The key test case:** Interval 370 (Session 71, valley @45s, R²=0.887) should fail HRR60 validation. Most other intervals should pass since their valleys are >60s.
