# Handoff: HRR300 Early Termination Bug

**Date:** 2026-01-18
**Status:** Ready for next session
**Priority:** HIGH - affects data quality for long recovery analysis

## Problem
Session 71 interval 13 has 298s duration but no HRR300 value extracted. The interval is cut off 2 seconds early, preventing HRR300 calculation.

```
 13    39:11  171  298     2    hig     pass
 13      5     19      42      53      55       -    110  0.98
```

HRR values through HRR240 (55 bpm) but HRR300 is `-` despite:
- R² values excellent: 0.94, 0.98, 0.89, 1.00, 0.96, 0.98, 0.98
- Clean exponential decay (tau=110)
- This was a deliberate 5min supine protocol

## Root Cause Hypothesis
`find_recovery_end()` in `scripts/hrr/detection.py` terminates on late-stage HR flutter/rise. At t>240s, HR naturally oscillates more as it approaches resting baseline. The termination logic treats this as "recovery ended" when it's just physiological noise.

## Relevant Code
```bash
grep -n "find_recovery_end\|recovery_end\|termination" scripts/hrr/detection.py
```

Key function: `find_recovery_end()` - determines when recovery interval stops.

## Proposed Fix
Add softer termination threshold for t>240s when early R² (0-60s, 0-120s) is clean:

```python
# Pseudo-logic
if t > 240 and r2_0_60 > 0.85:
    # Late-stage flutter tolerance - don't terminate on small rises
    termination_threshold = config.late_flutter_tolerance  # e.g., 5 bpm rise vs normal 3 bpm
```

Or simpler: if we have 300s of data and R² metrics are excellent, just take the full 300s regardless of late flutter.

## Config Values to Check
In `config/hrr_extraction.yaml`:
- `max_recovery_duration` - should be 300
- Any termination thresholds for HR rise detection

## Verification
```bash
python scripts/hrr_feature_extraction.py --session-id 71 --dry-run
```

After fix, interval 13 should show:
- Duration: 300 (not 298)
- HRR300: ~55-57 bpm (extrapolated from curve)

## Files Modified This Session
- `scripts/hrr/metrics.py` - Removed line 259 (quality_flags reset), added INFORMATIONAL_FLAGS
- `scripts/hrr/reanchoring.py` - Already had PLATEAU_RESOLVED flag (working)

## Related Issues
- GitHub #27: HRR module refactor (completed this session)
- GitHub #28: Protocol annotation (new - for distinguishing deliberate vs incidental recoveries)

## Context
Session 71 was a burpee tabata followed by deliberate 5min supine recovery. User wants to:
1. Get full 300s HRR data from controlled protocols
2. Annotate which intervals were deliberate vs incidental
3. Compare recovery patterns between protocol types

The 298s cutoff defeats the purpose of the deliberate protocol.
