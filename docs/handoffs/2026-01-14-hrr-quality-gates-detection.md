# HRR Quality Gates Handoff: Detection-Based Approach

**Date**: 2026-01-14
**Issue**: [#24 - Add monotonicity gate to reject non-monotonic recovery curves](https://github.com/brockwebb/arnold/issues/24)
**Status**: Exploration complete, key insight discovered, implementation next

---

## Key Insight

**Valley/peak detection must be scoped to the first 60 seconds for HRR60 validation.**

The full dataset analysis revealed that most "valleys" detected are at 50-110 seconds into the interval - these are the *start of the next work bout*, not problems with the recovery measurement. They're irrelevant to HRR60 validity.

Current detection is too aggressive because it checks the entire interval duration (often 60-120s).

---

## What Was Accomplished

### 1. Created Detection-Based Quality Explorer
- **File**: `/Users/brock/Documents/GitHub/arnold/scripts/hrr_quality_explorer.py`
- Uses scipy `find_peaks()` for both peaks and valleys (inverted signal)
- Binary detection: if it fires, it fires - no arbitrary thresholds
- Outputs CSV with all metrics for analysis

### 2. Full Dataset Analysis
- **Output**: `/Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_all_diffs.csv`
- 229 intervals flagged for status change
- Most valleys detected are AFTER 60s (irrelevant to HRR60)
- Peak-in-interval gate catches real violations

### 3. Valleys Within First 60s (The Real Suspects)
From the diffs file, intervals with valleys < 60s:
```
Interval 2:   valley @42s
Interval 5:   valleys @39s, @51s
Interval 21:  valley @35s
Interval 47:  valley @21s
Interval 370: valley @45s  ← Session 71 known bad interval
```

These are the ones worth investigating visually.

---

## Design Decisions Made

1. **No absolute thresholds** - Detection sensitivity via scipy prominence, not pass/fail thresholds
2. **Binary gates** - If scipy detects a valley/peak, it's a signal worth flagging
3. **Context-aware standards**:
   - HRR60 inter-set: Noisy, some jitter expected, be lenient
   - HRR120: Only check if HRR60 passed
   - HRR300 deliberate supine: Should be textbook decay, obvious violations

4. **Future direction**: Empirical noise envelope from "known good" intervals, flag outliers by N sigma

---

## Next Steps

### Immediate: Scope Detection to First 60s
Update `hrr_quality_explorer.py`:
```python
# In detect_valleys() and detect_peaks_in_interval()
# Only analyze hr[:61] for HRR60 validation
# Valleys/peaks after 60s are irrelevant to HRR60 measurement
```

### Then: Re-run Analysis
```bash
python scripts/hrr_quality_explorer.py --output /Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_60s.csv
```

Expect dramatic reduction in false positives.

### Then: Visual Validation
For the remaining flagged intervals (valleys within first 60s):
```bash
python scripts/hrr_qc_viz.py --session-id <id> --age 50 --rhr 55 --details
```

### Finally: Promote to hrr_batch.py
Once gates are tuned, add to production pipeline.

---

## Alternative Approaches Discussed (Not Yet Implemented)

1. **Early-fit extrapolation**: Fit exponential to first 30s, predict where HR should be at 45s/60s. If actual >> prediction, flag it.

2. **Residual sign analysis**: Fit full interval, check if residuals flip sign mid-interval (indicates structural problem vs random noise).

3. **Empirical noise envelope**: Collect residual variance from known-good intervals, flag new intervals that exceed envelope by N sigma.

---

## Files Modified/Created

- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_quality_explorer.py` - Detection-based quality analysis
- `/Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_all_diffs.csv` - Full dataset analysis results

---

## Commands for Next Session

```bash
# Re-run with 60s scoping (after code update)
python scripts/hrr_quality_explorer.py --output /Users/brock/Documents/GitHub/arnold/outputs/hrr_quality_60s.csv

# Visualize specific flagged intervals
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55 --details

# Check the known bad interval (370)
python scripts/hrr_qc_viz.py --session-id 71 --age 50 --rhr 55
```

---

## Context: Session 71 Test Case

- **Interval 370**: R²=0.887, valley @45s, duration 58s
- This is the minute 22-23 interval from the original screenshot
- ~15 bpm upswing mid-recovery that R² alone doesn't catch
- Should be rejected by properly-scoped valley detection
