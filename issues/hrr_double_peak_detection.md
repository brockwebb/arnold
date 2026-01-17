# Issue: Double-Peak Detection in HRR Extraction

**Created:** 2026-01-17  
**Priority:** High  
**Component:** `scripts/hrr_feature_extraction.py`

## Problem

The peak detection algorithm can identify two peaks within the same recovery interval, resulting in duplicate/overlapping intervals. 

**Example from session 5:**
- Peak 7: starts 20:13:35, HR=169, duration=233s
- Peak 8: starts 20:13:54, HR=169, duration=214s

These are only 19 seconds apart with identical peak HR and the same end time. Peak 7 is a false detection - peak 8 is the true recovery start.

## Root Cause

Peak detection runs on smoothed HR data and finds local maxima. When HR plateaus at a high value before dropping, multiple samples can qualify as "peaks." The current validation doesn't check if a new peak falls within a previous interval's window.

## Proposed Solution

Add a gate during peak validation:

```python
# After sorting peaks by time
for i, peak in enumerate(peaks[1:], 1):
    prev_peak = peaks[i-1]
    prev_end = prev_peak.start_time + timedelta(seconds=prev_peak.duration)
    
    if peak.start_time < prev_end:
        # This peak falls within previous interval
        # Keep the one with better R² or reject the earlier one
        reject_as_double_peak(prev_peak)
```

## Acceptance Criteria

- [ ] No two intervals from same session have overlapping time windows
- [ ] When double-peak detected, flag with `auto_reject_reason = 'double_peak'`
- [ ] Reprocess existing sessions to catch any missed double-peaks

## Manual Workaround

Use `verify_hrr_interval()` to exclude:
```sql
SELECT verify_hrr_interval(<id>, 'overridden_fail', 'Double peak with interval N', true, 'double_peak');
```
