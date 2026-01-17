# Handoff: HRR Issue #015 Complete - Onset Adjustment & Overlap Detection

**Date:** 2026-01-17  
**Session:** Issue #015 implementation and resolution  
**Status:** Complete

## Summary

Fixed double-peak detection bug in HRR extraction. Recovery intervals now correctly identify the true max HR at the end of plateaus, and overlapping intervals are rejected.

## What Was Done

### 1. YAML Config System
Created `/config/hrr_extraction.yaml` with configurable:
- Peak detection parameters
- Recovery interval settings
- Quality gates with thresholds
- Flag enable/disable and review triggers
- Athlete defaults (fallback only - profile is authoritative)

### 2. Last-Occurrence Max HR Detection
Changed `detect_onset_maxhr()` to find the **last** occurrence of max HR:
```python
max_hr = max(hr_values)
max_indices = [i for i, hr in enumerate(hr_values) if hr == max_hr]
max_hr_idx = max_indices[-1] if max_indices else 0
```
This catches the end of plateaus where HR is flat at max before declining.

### 3. Onset-Adjusted R² Computation
In `extract_features()`, R² is now computed from the onset-adjusted start point:
```python
onset_offset = interval.onset_delay_sec or 0
adjusted_start_idx = peak_idx + onset_offset
interval_samples = samples[adjusted_start_idx:end_idx + 1]
```

### 4. Overlap Detection Gate
After all intervals are built, reject any interval whose adjusted start overlaps the next:
```python
if curr.start_time >= next_int.start_time:
    curr.quality_status = 'rejected'
    curr.auto_reject_reason = 'overlap_duplicate'
```

### 5. ONSET_ADJUSTED Flag Threshold
Only flag intervals with onset adjustment > 15 seconds (small adjustments are normal).

## Results

**Before fix:** 70% rejection rate (r2_0_30 gate catching plateaus as "double peaks")

**After fix:**
- 60% pass
- 37% reject  
- 2% flagged

**Rejection breakdown:**
| Reason | Count |
|--------|-------|
| r2_30_60_below_0.75 | 95 |
| r2_30_90_below_0.75 | 62 |
| double_peak | 51 |
| overlap_duplicate | 32 |
| poor_fit_quality | 23 |
| no_valid_r2_windows | 20 |

## Files Changed

- `scripts/hrr_feature_extraction.py` - onset detection, R² computation, overlap gate, YAML loading
- `config/hrr_extraction.yaml` - new config file (created)
- `docs/issues/015-hrr-double-peak-detection.md` - closed

## New Issues Created

### Issue #020: Plateau Detection for Sustained Efforts
Scipy's `find_peaks` requires prominence (spike above surroundings). When HR is sustained at high level then gradually rolls off (common in running), no peak is detected. Need complementary detection method for plateau-to-decline patterns.

### Issue #021: QC Viz Shows Flagged Intervals as Rejected
The QC visualization shows intervals with `quality_status = 'flagged'` as if they were rejected. Table output is correct, visual rendering is wrong.

## Commands

```bash
# Reprocess all sessions
python scripts/hrr_feature_extraction.py --all --reprocess --quiet

# Check single session
python scripts/hrr_feature_extraction.py --session-id 5 --dry-run

# QC visualization
python scripts/hrr_qc_viz.py --session-id 5

# Check rejection stats
psql arnold_analytics -c "
SELECT auto_reject_reason, count(*)
FROM hr_recovery_intervals 
WHERE quality_status = 'rejected'
GROUP BY auto_reject_reason
ORDER BY count DESC
"

# Check pass/flag/reject distribution
psql arnold_analytics -c "
SELECT quality_status, count(*), 
       round(100.0 * count(*) / sum(count(*)) over(), 1) as pct
FROM hr_recovery_intervals 
GROUP BY quality_status
"
```

## Key Files

- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_feature_extraction.py`
- `/Users/brock/Documents/GitHub/arnold/config/hrr_extraction.yaml`
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_qc_viz.py`
- `/Users/brock/Documents/GitHub/arnold/docs/issues/015-hrr-double-peak-detection.md`
- `/Users/brock/Documents/GitHub/arnold/docs/issues/020-plateau-detection-sustained-efforts.md`
- `/Users/brock/Documents/GitHub/arnold/docs/issues/021-qc-viz-status-display.md`

## Next Steps

1. **Issue #020** - Implement plateau detection for running data (sustained HR → gradual decline)
2. **Issue #021** - Fix QC viz status display (low priority)
3. Consider lowering `peak_prominence` from 10 to 5 as quick partial fix for #020
