# Handoff: HRR300 Early Termination Bug - RESOLVED

**Date:** 2026-01-18
**Status:** ✅ COMPLETE - Ready for code push
**Related:** GitHub #27 (HRR refactor), #28 (protocol annotation)

## Problem (Resolved)

Session 71 interval 13 had 298s duration but no HRR300 value extracted. The interval was cut off 2 seconds early due to a bug in onset adjustment logic.

## Root Cause

**Bug in onset adjustment logic:** `find_recovery_end()` caps at `peak_idx + 300`, but onset adjustment shifts the effective start forward without extending the end.

```
peak_idx = 2349
end_idx = 2649 (peak + 300)
onset_delay = 2s
adjusted_start_idx = 2351
Effective samples = 2351 to 2649 = 299 samples = 298s duration
```

**Initial hypothesis was wrong:** We initially suspected late-stage HR flutter was triggering early termination. Investigation showed HR was flat at t=290-300 (114 bpm), not oscillating.

## Solution Implemented

### Primary Fix: Extended Window Compensation

In `scripts/hrr/detection.py` `extract_features()` (lines 523-533):

```python
# Compensate for onset adjustment - extend end to maintain full measurement window
onset_offset = adjusted_start_idx - start_idx
extended_end_idx = end_idx + onset_offset
if extended_end_idx >= len(samples):
    extended_end_idx = len(samples) - 1
interval_samples = samples[adjusted_start_idx:extended_end_idx + 1]
```

Also updated overlap tracker (line 574):
```python
last_interval_end = extended_end_idx
```

### Secondary Fix: Late-Stage Flutter Tolerance

Added to `find_recovery_end()` (lines 191-230) - uses 6 bpm tolerance after 240s vs normal 3 bpm. Not the root cause for session 71, but still valuable for genuine premature termination cases.

## Files Modified

| File | Changes |
|------|---------|
| `scripts/hrr/detection.py` | Extended window compensation in `extract_features()`, late-stage flutter tolerance in `find_recovery_end()` |
| `scripts/hrr/types.py` | Added `late_stage_sec: int = 240`, `late_stage_tolerance_bpm: int = 6` to HRRConfig |
| `config/hrr_extraction.yaml` | Added `late_stage_sec: 240`, `late_stage_tolerance_bpm: 6` under `recovery_interval` |

## Verification

After fix, session 71 interval 13 shows:
- **HRR300** = 56 bpm ✓ (was `-`)
- **Duration** = 300s ✓ (was 298s)
- **r2_0_300** computes correctly ✓

```bash
python scripts/hrr_feature_extraction.py --session-id 71 --dry-run 2>&1 | grep "^ 13"
```

## Context

Session 71 was a burpee tabata followed by deliberate 5min supine recovery. The fix enables:
1. Full 300s HRR data from controlled protocols
2. Proper long recovery analysis (HRR240, HRR300)
3. Accurate R² computation for extended windows

## Related Issues

- **GitHub #27**: HRR module refactor (this fix is part of that work)
- **GitHub #28**: Protocol annotation (still open - for distinguishing deliberate vs incidental recoveries)

## Debugging Journey

1. **Initial hypothesis:** Late-stage HR flutter triggering early termination
2. **Added flutter tolerance:** Implemented, but didn't fix the issue
3. **Investigated actual data:** HR was flat at 114 bpm, not oscillating
4. **Found real bug:** Onset adjustment eating into measurement window
5. **Implemented fix:** Extended `end_idx` to compensate for onset offset
6. **Verified:** HRR300 now extracts correctly

## Transcript

Full session details: `/mnt/transcripts/2026-01-18-16-50-02-hrr300-early-termination-fix.txt`
