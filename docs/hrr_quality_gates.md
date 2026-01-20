# HRR Quality Gates

## Overview

Quality gates filter recovery intervals to ensure only physiologically valid data enters analytics. Gates run in sequence; first failure triggers rejection.

## Hard Reject Criteria

| Gate | Metric | Threshold | Reject Reason | Rationale |
|------|--------|-----------|---------------|-----------|
| 0 | `r2_0_60` | None | `insufficient_duration` | Too short for HRR60 |
| 1 | `slope_90_120` | > 0.1 bpm/sec | `activity_resumed` | HR rising = athlete moved |
| 2 | `best_r2` (0-60 through 0-300) | None | `no_valid_r2_windows` | Too short for validation |
| 3 | `best_r2` | < 0.75 | `poor_fit_quality` | Exponential decay doesn't fit |
| 4 | `r2_30_60` | < 0.75 | `r2_30_60_below_0.75` | HRR60 unreliable (mid-recovery disruption) |
| 5 | `r2_0_30` | < 0.5 | `double_peak` | Plateau/rise in first 30s = false start |

> **Note (Migration 024)**: `r2_30_90 < 0.75` was previously Gate 5 but is now **diagnostic only**.
> It validates HRR120 quality but does NOT reject the interval. Valid HRR60 intervals were being
> incorrectly rejected when only HRR120 was invalid.

## Flag Criteria (Review, Not Reject)

| Flag | Condition | Meaning |
|------|-----------|---------|
| `LATE_RISE` | 0 < slope_90_120 ≤ 0.1 | Minor fidgeting, probably OK |
| `ONSET_DISAGREEMENT` | onset_confidence == 'low' | Detection methods disagree on start |
| `LOW_SIGNAL` | hr_reserve < 25 bpm | Floor effect - small signal |

## Segment R² Windows

| Window | Validates | Notes |
|--------|-----------|-------|
| r2_0_30 | Early phase | <0.5 triggers double_peak rejection |
| r2_15_45 | Centered window | Diagnostic for edge artifacts (new in Mig 024) |
| r2_30_60 | HRR60 | <0.75 triggers hard reject |
| r2_0_60 | Overall decay | First phase gate |
| r2_30_90 | HRR120 | **Diagnostic only** - does NOT reject (Mig 024) |
| r2_0_120+ | Longer HRR | Extended windows |

## Implementation Notes

- `r2_0_30 < 0.5` triggers `double_peak` rejection (catches plateau/rise before real recovery)
- `r2_15_45` is diagnostic only - helps identify edge artifacts affecting r2_30_60
- `r2_30_90` is diagnostic only - validates HRR120 but does NOT reject interval (Mig 024)
- `best_r2` uses r2_0_60 through r2_0_300 only (excludes r2_0_30)
- Fit failures return `None` (no data) or very low R² (triggers rejection)
- Rejected intervals stored with `auto_reject_reason` for audit trail
- Intervals < 60s rejected as `insufficient_duration` (no HRR60 possible)

## Database Fields
```sql
quality_status: 'pass' | 'rejected' | 'flagged'
quality_flags: TEXT[]  -- e.g., {'LATE_RISE', 'LOW_SIGNAL'}
auto_reject_reason: TEXT  -- e.g., 'r2_30_60_below_0.75'
```

## Manual Peak Adjustments

Sometimes the automatic peak detection anchors on a false peak (plateau before actual max HR). When QC visualization shows a rejected interval with good-looking recovery data offset from the detected peak, manual adjustment can recover the interval.

### When to Use

- Interval rejected with `r2_30_60_below_0.75` but visual inspection shows clean decay starting later
- Double-peak pattern where scipy detected the first (false) peak
- Plateau-to-decline pattern not caught by automatic re-anchoring

### Workflow

1. **Identify the problem** via QC viz:
   ```bash
   python scripts/hrr_qc_viz.py --session-id 51
   ```
   Look for gray (rejected) intervals where the recovery curve looks valid but offset.

2. **Estimate the shift** in seconds from the viz. Positive = shift peak later (right).

3. **Insert adjustment**:
   ```sql
   INSERT INTO peak_adjustments (polar_session_id, interval_order, shift_seconds, reason)
   VALUES (51, 3, 54, 'False peak - real recovery starts ~54s later');
   ```

4. **Reprocess the session**:
   ```bash
   python scripts/hrr_feature_extraction.py --session-id 51
   ```

5. **Verify** with QC viz again. Adjust `shift_seconds` if needed:
   ```sql
   UPDATE peak_adjustments SET shift_seconds = 60 
   WHERE polar_session_id = 51 AND interval_order = 3;
   ```

### Database Schema

```sql
CREATE TABLE peak_adjustments (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    interval_order SMALLINT NOT NULL,  -- which detected peak (1-indexed)
    shift_seconds SMALLINT NOT NULL,   -- positive = shift later
    reason TEXT,                        -- documentation
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,             -- set when extraction uses it
    UNIQUE(polar_session_id, interval_order)
);
```

### Quality Flag

Intervals with manual adjustments get `MANUAL_ADJUSTED` in `quality_flags` for audit trail.

### Philosophy

Manual adjustments are surgical fixes for edge cases, not a substitute for improving detection. If you find yourself making many adjustments for similar patterns, that's a signal to improve the automatic detection logic.

## Quality Overrides

When QC visualization shows a rejected interval with legitimately good recovery data (not a peak detection issue), quality overrides let you force-pass or force-reject intervals. Unlike peak adjustments (which shift detection), overrides change the final status after all quality gates have run.

### When to Use (vs Peak Adjustments)

| Situation | Tool |
|-----------|------|
| Peak detected in wrong place, good recovery data offset | **Peak Adjustment** |
| Peak detected correctly, but R² gate triggered by benign plateau | **Quality Override** |
| Want to reject a passing interval (bad visual despite metrics) | **Quality Override** |
| Double-peak pattern | Try **Peak Adjustment** first |

### Workflow

1. **Identify the candidate** via QC viz:
   ```bash
   python scripts/hrr_qc_viz.py --session-id 70
   ```
   Look for rejected intervals where the decay curve looks physiologically valid.

2. **Verify peak location is correct** - if peak is offset, use peak adjustment instead.

3. **Examine the rejection reason** in the summary table:
   - `r2_30_60_below_0.75` - often a mid-recovery plateau that doesn't invalidate HRR60
   - `poor_fit_quality` - check if exponential just doesn't fit (legitimate reject) vs noise

4. **Insert override** (force_pass example):
   ```sql
   INSERT INTO hrr_quality_overrides 
       (polar_session_id, interval_order, override_action, original_status, original_reason, reason)
   VALUES 
       (70, 1, 'force_pass', 'rejected', 'r2_30_60_below_0.75', 
        'Human reviewed: mid-peak plateau in steady drop. Valid recovery curve despite segment R² flag.');
   ```

5. **Reprocess the session**:
   ```bash
   python scripts/hrr_feature_extraction.py --session-id 70
   ```

6. **Verify** - interval should now show `pass` with `HUMAN_OVERRIDE` flag.

### Database Schema

```sql
CREATE TABLE hrr_quality_overrides (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    endurance_session_id INTEGER REFERENCES endurance_sessions(id),
    interval_order SMALLINT NOT NULL,
    override_action VARCHAR(20) NOT NULL,  -- 'force_pass' or 'force_reject'
    original_status VARCHAR(20),           -- for audit trail
    original_reason TEXT,                  -- rejection reason being overridden
    reason TEXT NOT NULL,                  -- human explanation (required)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,                -- set when extraction uses it
    UNIQUE(polar_session_id, interval_order),
    UNIQUE(endurance_session_id, interval_order),
    CHECK (override_action IN ('force_pass', 'force_reject'))
);
```

### Override Actions

**force_pass**: Override rejected → pass
- Clears `auto_reject_reason`
- Sets `review_priority = 3` (low)
- Adds `HUMAN_OVERRIDE` to `quality_flags`

**force_reject**: Override pass/flagged → rejected  
- Sets `auto_reject_reason = 'human_override: {reason}'`
- Sets `review_priority = 0`
- Adds `HUMAN_OVERRIDE` to `quality_flags`

### Key Design: Stable Keys

Overrides use `(session_id, interval_order)` as key, NOT the interval PK. This means:
- Overrides survive re-extraction (interval PKs change, order doesn't)
- No need to re-enter overrides after pipeline improvements
- `applied_at` timestamp tracks when override was used

### Philosophy

Quality overrides are for the "R² gate is being too strict" case where human judgment says the data is valid. They should be rare - if you're overriding many intervals for the same reason, consider adjusting gate thresholds in `config/hrr_extraction.yaml`.

## Session QC Tracking

Track which sessions have been reviewed via columns on `polar_sessions`:

| Column | Type | Values |
|--------|------|--------|
| `hrr_qc_status` | VARCHAR(20) | `pending`, `reviewed`, `needs_reprocess` |
| `hrr_qc_reviewed_at` | TIMESTAMPTZ | When review completed |

**Mark session as reviewed:**
```sql
UPDATE polar_sessions 
SET hrr_qc_status = 'reviewed', hrr_qc_reviewed_at = NOW() 
WHERE id = 51;
```

**Find sessions needing review:**
```sql
SELECT id, start_time::date, sport_type, hrr_qc_status
FROM polar_sessions
WHERE id IN (SELECT DISTINCT polar_session_id FROM hr_recovery_intervals)
  AND (hrr_qc_status = 'pending' OR hrr_qc_status IS NULL)
ORDER BY start_time;
```

## Interval-Level Reviews

For granular review decisions (clearing flags, verifying peak shifts), use `hrr_interval_reviews`:

| Column | Type | Description |
|--------|------|-------------|
| `interval_id` | INT FK | Reference to hr_recovery_intervals.id |
| `review_action` | VARCHAR(30) | `flags_cleared`, `peak_shift_verified`, `accepted`, `rejected_override` |
| `original_flags` | TEXT[] | Snapshot of flags at review time |
| `notes` | TEXT | Reviewer notes |
| `reviewed_at` | TIMESTAMPTZ | When reviewed |

**Clear informational flags:**
```sql
INSERT INTO hrr_interval_reviews (interval_id, review_action, original_flags, notes)
SELECT id, 'flags_cleared', quality_flags, 'ONSET flags OK - R² excellent'
FROM hr_recovery_intervals
WHERE polar_session_id = 5 AND interval_order IN (6, 8);
```

**Verify peak shift:**
```sql
INSERT INTO hrr_interval_reviews (interval_id, review_action, original_flags, notes)
SELECT id, 'peak_shift_verified', quality_flags, 'Shifted 120s - corrected'
FROM hr_recovery_intervals
WHERE polar_session_id = 5 AND interval_order = 10;
```

**View review status:**
```sql
SELECT * FROM hrr_review_status WHERE polar_session_id = 5;
```
