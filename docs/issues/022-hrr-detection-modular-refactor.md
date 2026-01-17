# Issue #022: Refactor HRR Detection into Modular Components

**Created:** 2026-01-17  
**Priority:** Low  
**Status:** Open  
**Component:** `scripts/hrr_feature_extraction.py`

## Problem

`hrr_feature_extraction.py` is ~900 lines with detection logic tangled with feature extraction. Adding valley-based detection increases complexity. Token-heavy to read/modify.

## Proposed Structure

```
scripts/
  hrr_feature_extraction.py     # orchestrator + feature computation
  hrr_peak_detector.py          # scipy peak detection (extract existing)
  hrr_valley_detector.py        # valley-based peak discovery
```

Main function becomes:
```python
peak_indices = detect_peaks(samples, config)
valley_peaks = detect_valley_peaks(samples, config)
all_candidates = merge_candidates(peak_indices, valley_peaks, existing_intervals)
# ... existing feature extraction on all_candidates
```

## Acceptance Criteria

- [ ] Peak detection in separate module
- [ ] Valley detection in separate module  
- [ ] Merge logic enforces measurement window constraint
- [ ] Main orchestrator under 300 lines
- [ ] No behavior change from current integrated version

## Notes

Deferred to ship working valley detection first. Refactor when code is stable and validated.
