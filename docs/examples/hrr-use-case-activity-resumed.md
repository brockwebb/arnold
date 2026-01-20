# HRR Use Case: Activity Resumed Mid-Recovery

**Date**: 2026-01-18  
**Session**: Polar session 23, Interval 9  
**Status**: Correctly REJECTED  
**Reject Reason**: `r2_30_60_below_0.75`

## Summary

This use case documents a scenario where the HRR quality gates correctly rejected an interval that initially appeared to have good recovery characteristics but where the athlete resumed activity mid-recovery.

## The Data

Raw HR trace from session 23, interval 9:

| Seconds | HR (bpm) | Phase |
|---------|----------|-------|
| 0 | 172 | Peak (detected) |
| 0-38 | 172→152 | **Clean decline** (-20 bpm in 38s) |
| 38-44 | 150-152 | Flutter/nadir plateau |
| 44-60 | 150→154 | **HR RISING** - activity resumed |
| 60-90 | 154→162 | Continues rising (+8 bpm) |
| 90+ | 162→164 | Still climbing |

## What the Algorithm Did

1. **Peak Detection**: Detected peak at sec 0 (172 bpm)
2. **Initial R² Check**: `r2_0_30` was poor, triggered plateau detection
3. **Plateau Reanchoring**: Shifted measurement window start by 38 seconds
4. **Feature Extraction**:
   - `onset_delay_sec`: 38
   - `r2_0_30`: 0.95 (excellent - fits early slow decline)
   - `r2_30_60`: 0.66 (poor - HR is rising, exponential decay can't fit)
   - `r2_0_60`: 0.93
5. **Quality Gate**: Rejected for `r2_30_60_below_0.75`

## Why r2_30_60 Failed

After the 38-second onset adjustment, the measurement windows are:
- **r2_0_30**: Covers adjusted sec 0-30 → original sec 38-68
- **r2_30_60**: Covers adjusted sec 30-60 → original sec 68-98

In the 68-98 second range, HR goes from 157→162 bpm. This is a **rising** signal. An exponential decay model cannot fit rising data, resulting in R² = 0.66.

## Why This is Correct Rejection

This interval represents a **truncated recovery** followed by **activity resumption**:

1. Athlete worked hard (peak 172 bpm)
2. Recovery began (clean drop to ~150 bpm)
3. **Activity resumed around sec 44** (movement, next set prep, etc.)
4. HR started climbing again

The initial 38-second drop (172→152 = 20 bpm) could be analyzed as HRR30, but:
- We cannot trust HRR60 because the 30-60s window contains rising HR
- The segment R² gates exist precisely to catch this pattern

## Alternative Outcomes

**Could `find_recovery_end()` have terminated earlier?**

The termination logic looks for 5 consecutive seconds of HR rising above tolerance. The flutter in sec 44-60 (bouncing 150-154) didn't trigger a clear termination signal. The gradual rise was slow enough to evade the consecutive-rise detector.

**Is this a problem?**

No. The quality gates serve as a safety net for exactly this scenario. The pipeline correctly:
1. Attempted to salvage the interval via plateau reanchoring
2. Recomputed R² on the adjusted window
3. Detected the poor fit in the 30-60s segment
4. Rejected the interval

## Key Insight

**R² measures different things in different segments:**
- `r2_0_30`: Captures initial recovery slope (fast parasympathetic response)
- `r2_30_60`: Captures sustained recovery behavior

An interval can have excellent `r2_0_30` but poor `r2_30_60` when:
- Activity resumes mid-recovery (this case)
- Movement artifact occurs
- Athlete stands up from supine position
- Any event that reverses the decline

## Flags Present

```
quality_flags: ['PLATEAU_RESOLVED', 'ONSET_ADJUSTED']
```

- `PLATEAU_RESOLVED`: Plateau detection successfully shifted the measurement window
- `ONSET_ADJUSTED`: Onset delay was applied (38 seconds)

Both flags are informational. The rejection is due to `r2_30_60_below_0.75`, not the flags.

## Verification

```bash
# View this interval
python scripts/hrr_qc_viz.py --session-id 23

# Query the interval
SELECT interval_order, duration_seconds, onset_delay_sec, 
       r2_0_30, r2_30_60, quality_status, auto_reject_reason
FROM hr_recovery_intervals
WHERE polar_session_id = 23 AND interval_order = 9;
```

## Related

- Issue #33: NULL R² bypass bug (now fixed with -1 sentinel)
- Issue #24: Monotonicity gate (would also catch this pattern)
- `docs/hrr_quality_gates.md`: Quality gate documentation
