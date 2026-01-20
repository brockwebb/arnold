# HRR Peak Adjustment Candidates

Intervals where the detected peak is NOT the true peak. These are candidates for Issue #36 (backward peak search).

## Pattern: Gradual Deceleration

Athlete slows down over 20-60 seconds instead of stopping suddenly. Scipy finds a local max at the END of the deceleration, missing the true peak further back.

## Tracking Table

| Session | Interval | Detected Peak (bpm) | True Peak (bpm) | Shift (sec) | Current Status | Notes |
|---------|----------|---------------------|-----------------|-------------|----------------|-------|
| 22 | 3 | 126 @ sec 0 | 134 @ sec -50 | -50 | PASS (bad) | r2_0_60=0.70 slipped through |
| 33 | 11 | 134 @ sec 0 | 139 @ sec -30 | -30 | rejected | r2_30_60=0.70 caught it |

## How to Add Entries

When reviewing QC and you see a backward peak candidate:

```sql
-- 1. Get interval metrics
SELECT polar_session_id, interval_order, hr_peak, onset_delay_sec,
       r2_0_30, r2_30_60, r2_0_60, quality_status, auto_reject_reason
FROM hr_recovery_intervals
WHERE polar_session_id = ? AND interval_order = ?;

-- 2. Look at HR trace before detected peak
WITH interval_window AS (
    SELECT start_time
    FROM hr_recovery_intervals
    WHERE polar_session_id = ? AND interval_order = ?
)
SELECT 
    (EXTRACT(EPOCH FROM (hs.sample_time - iw.start_time)))::int as sec,
    hs.hr_value as hr
FROM hr_samples hs
CROSS JOIN interval_window iw
WHERE hs.session_id = ?
  AND hs.sample_time >= iw.start_time - interval '60 seconds'
  AND hs.sample_time <= iw.start_time + interval '10 seconds'
ORDER BY hs.sample_time;
```

Then add a row to the table above with:
- Session/Interval identifiers
- Detected peak HR and position (always sec 0 relative to interval start)
- True peak HR and position (negative seconds = before detected)
- Shift needed (negative = move backward)
- Current quality status
- Brief notes on why it was caught or missed

## Verification After Fix

Once Issue #36 is implemented, reprocess these sessions and verify:
1. Peak shifts to true position
2. HRR values recalculated correctly
3. Quality status improves (rejected → pass, or pass with better metrics)

## Related

- [Issue #35](https://github.com/brockwebb/arnold/issues/35): r2_0_60 gate (catches some of these via rejection)
- [Issue #36](https://github.com/brockwebb/arnold/issues/36): Backward peak search (the fix)
- `docs/examples/hrr-use-case-activity-resumed.md`: Different pattern (activity resumed mid-recovery)
