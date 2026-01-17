# Issue #022: Refactor HRR Detection into Modular Components

**Created:** 2026-01-17  
**Priority:** Low  
**Status:** Open  
**Component:** `scripts/hrr_feature_extraction.py`

## Problem

`hrr_feature_extraction.py` is ~900 lines with detection logic tangled with feature extraction. Adding valley-based detection increased coupling. Token-heavy to read/modify.

## Proposed Structure

```
scripts/
  hrr_feature_extraction.py   # Orchestrator + feature computation
  hrr_peak_detector.py        # scipy peak detection (extract existing)
  hrr_valley_detector.py      # Valley-based peak discovery
```

Main function becomes:
```python
from hrr_peak_detector import detect_peaks
from hrr_valley_detector import detect_valley_peaks

peak_indices = detect_peaks(samples, config)
valley_peaks = detect_valley_peaks(samples, config)
all_candidates = merge_candidates(peak_indices, valley_peaks, existing_intervals)
# ... feature extraction on all_candidates
```

## Benefits

- Easier to test detectors independently
- Smaller files, fewer tokens to read/write
- Can swap detection strategies without touching feature extraction
- Clear separation: detection → candidates → features → quality gates

## Acceptance Criteria

- [ ] Peak detection in separate module
- [ ] Valley detection in separate module  
- [ ] Main script orchestrates and computes features
- [ ] No behavior change (same outputs)
- [ ] Tests pass

## Notes

Not urgent - current code works. Do when touching detection logic next.
