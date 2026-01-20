# HRR Quality Gates

## Overview

Quality gates filter recovery intervals to ensure only physiologically valid data enters analytics. Gates run in sequence; first failure triggers rejection.

## Querying Existing QC Data

Before making changes to HRR detection, check what manual corrections already exist:

### Peak Adjustments

Manual corrections for false peak detection:

```sql
-- View all peak adjustments
SELECT 
    pa.polar_session_id,
    ps.start_time::date as session_date,
    ps.sport_type,
    pa.interval_order,
    pa.shift_seconds,
    pa.reason,
    pa.applied_at
FROM peak_adjustments pa
JOIN polar_sessions ps ON pa.polar_session_id = ps.id
ORDER BY pa.polar_session_id, pa.interval_order;
```

**Current known adjustments:**

| Session | Date | Interval | Shift | Reason |
|---------|------|----------|-------|--------|
| 5 | 2025-06-17 | 10 | +120s | Plateau anchor |
| 51 | 2025-07-27 | 3 | +54s | False peak |

### Quality Overrides

Human decisions to force-pass or force-reject intervals:

```sql
-- View all quality overrides
SELECT 
    qo.polar_session_id,
    ps.start_time::date as session_date,
    qo.interval_order,
    qo.override_action,
    qo.original_status,
    qo.original_reason,
    qo.reason as override_reason,
    qo.applied_at
FROM hrr_quality_overrides qo
JOIN polar_sessions ps ON qo.polar_session_id = ps.id
ORDER BY qo.polar_session_id, qo.interval_order;
```

### Interval Reviews

Granular review decisions (flag clearing, verification):

```sql
-- View all interval reviews with context
SELECT 
    i.polar_session_id,
    i.interval_order,
    r.review_action,
    r.original_flags,
    r.notes,
    r.reviewed_at
FROM hrr_interval_reviews r
JOIN hr_recovery_intervals i ON r.interval_id = i.id
ORDER BY i.polar_session_id, i.interval_order;

-- Or use the convenience view
SELECT * FROM hrr_review_status WHERE polar_session_id = 5;
```

### Session QC Status

```sql
-- Sessions with QC review status
SELECT 
    id,
    start_time::date as session_date,
    sport_type,
    hrr_qc_status,
    hrr_qc_reviewed_at
FROM polar_sessions
WHERE id IN (SELECT DISTINCT polar_session_id FROM hr_recovery_intervals)
ORDER BY start_time DESC;
```

### How Extraction Uses This Data

During extraction, the pipeline loads adjustments and overrides from Postgres:

- **Peak adjustments**: `scripts/hrr/persistence.py::load_peak_adjustments(session_id)` returns `{interval_order: shift_seconds}`
- **Quality overrides**: Applied after quality gates run, overriding the computed status
- Both use `(session_id, interval_order)` as stable keys that survive re-extraction

---

## Hard Reject Criteria

| Gate | Metric | Threshold | Reject Reason | Rationale |
|------|--------|-----------|---------------|-----------|
| 0 | `r2_0_60` | None | `insufficient_duration_Xs` | Too short for HRR60 |
| 1 | `slope_90_120` | > 0.1 bpm/sec | `activity_resumed` | HR rising = athlete moved |
| 2 | `best_r2` (0-60 through 0-300) | None | `no_valid_r2_windows_Xs` | Too short for validation |
| 3 | `best_r2` | < 0.75 | `poor_fit_quality` | Exponential decay doesn't fit |
| 4 | `r2_30_60` | < 0.75 | `r2_30_60_below_0.75` | HRR60 unreliable (mid-recovery disruption) |
| 5 | `r2_0_30` | < 0.5 | `double_peak` | Plateau/rise in first 30s = false start |
| 6 | `tau_seconds` | >= 299 | `tau_clipped` | Fit hit ceiling, recovery shape invalid |

> **Note (2026-01-20)**: Rejection reasons for gates 0 and 2 now include duration context
> (e.g., `insufficient_duration_45s`, `no_valid_r2_windows_52s`) for easier debugging.

> **Note (Migration 024)**: `r2_30_90 < 0.75` was previously Gate 5 but is now **diagnostic only**.
> It validates HRR120 quality but does NOT reject the interval. Valid HRR60 intervals were being
> incorrectly rejected when only HRR120 was invalid.

### Gate 6: tau_clipped

**What is tau (τ)?** The time constant in exponential decay fitting. It measures how fast HR drops:
- **Small tau (30-60s)** = fast recovery, HR drops quickly toward baseline
- **Large tau (100-150s)** = slower recovery, HR drops gradually
- **tau = 300** = fit hit the ceiling constraint (max bound), algorithm gave up

**Why reject tau = 300?** When the exponential fit returns exactly 300s (the configured max), it means:
1. Recovery was impossibly slow (doesn't match exponential decay physiology)
2. Data contains plateau, interruption, or irregular pattern that broke the model
3. The interval may be a pause/flutter rather than a true recovery attempt

Even if R² values look acceptable, tau=300 indicates the **shape** of recovery doesn't match expected physiology. The HRR60 measurement may be numerically present but is not trustworthy for longitudinal trend analysis.

**Observations from QC review:**
- tau=300 intervals often have low peak HR (zone 1-2 effort)
- Frequently show flat/plateau patterns rather than exponential decay
- Sometimes followed immediately by a "real" recovery with normal tau
- Correlated with lower r2_15_45 values (avg 0.65 vs 0.85 for normal tau)

**Monitoring:** Track tau_clipped rejection rate as a baseline. Potential signals:
- Sudden increase may indicate sensor fit issues (chest strap contact)
- Sustained elevation could indicate training pattern changes
- Or could be early sign of autonomic changes worth investigating

**Added**: January 2026 (Migration TBD)

## Peak Detection Enhancements

### Backward Peak Search (Issue #43)

When scipy's `find_peaks()` detects a peak, it may anchor on the end of a gradual deceleration plateau rather than the true maximum HR. The backward search looks backward from the detected peak to find the true maximum.

**Configuration** (`config/hrr_extraction.yaml`):
- `backward_lookback_sec`: Maximum seconds to search backward (default: 60)
- `backward_threshold_bpm`: Minimum HR increase to consider (default: 3)

> **Note (2026-01-20)**: Lookback increased from 30s to 60s after regression testing showed
> gradual deceleration patterns where the true peak can be 40-60s before scipy detection.
> Session 22, Interval 3 demonstrated a true peak ~50s back from the detected point.

**Behavior**:
1. From detected peak, search backward up to `backward_lookback_sec`
2. If a point ≥ `backward_threshold_bpm` higher is found, shift to that point
3. Intervals with backward shift get `BACKWARD_SHIFTED` flag

**Test case**: Session 22, Interval 3 — demonstrates backward shift correcting a gradual deceleration detection.

### Forward Re-anchoring (Plateau Detection)

When the first 30-45 seconds don't fit exponential decay, the interval likely started on a plateau before the true peak. Forward re-anchoring searches ahead for the actual recovery start.

**Trigger conditions** (either triggers re-anchor attempt):
- `r2_0_30 < 0.5` — Immediate plateau in first 30 seconds
- `r2_15_45 < 0.5` — Delayed plateau pattern (Issue #43)

**Method conflict resolution**: When slope and geometry methods disagree significantly (>10s difference), the slope method is trusted. Geometry uses inflection point detection which fails on long declining plateaus.

**Result**:
- Success: Interval shifted forward, `PLATEAU_RESOLVED` flag added
- Failure: Original interval kept, may be rejected by quality gates

**Test case**: Session 22, Interval 1 — demonstrates r2_15_45 trigger with +141s shift (correctly rejected at 45s duration).

## Flag Criteria (Review, Not Reject)

| Flag | Condition | Meaning |
|------|-----------|---------|
| `LATE_RISE` | 0 < slope_90_120 ≤ 0.1 | Minor fidgeting, probably OK |
| `ONSET_DISAGREEMENT` | onset_confidence == 'low' | Detection methods disagree on start |
| `LOW_SIGNAL` | hr_reserve < 25 bpm | Floor effect - small signal |

## Segment R² Windows

| Window | Validates | Notes |
|--------|-----------|-------|
| r2_0_30 | Early phase | <0.5 triggers re-anchor attempt and double_peak rejection |
| r2_15_45 | Centered window | <0.5 triggers re-anchor attempt (Issue #43) |
| r2_30_60 | HRR60 | <0.75 triggers hard reject |
| r2_0_60 | Overall decay | First phase gate |
| r2_30_90 | HRR120 | **Diagnostic only** - does NOT reject (Mig 024) |
| r2_0_120+ | Longer HRR | Extended windows |

## Implementation Notes

- `r2_0_30 < 0.5` OR `r2_15_45 < 0.5` triggers forward re-anchor attempt (Issue #43)
- If re-anchor fails and `r2_0_30 < 0.5`, `double_peak` rejection is applied
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
