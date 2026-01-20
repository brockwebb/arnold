# Testing Guide

<!--
╔══════════════════════════════════════════════════════════════════════════════╗
║                         ⚠️  DO NOT EDIT THIS HEADER  ⚠️                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  WHAT THIS DOCUMENT IS                                                       ║
║  ─────────────────────                                                       ║
║  Master reference for verifying Arnold system behavior. Documents our        ║
║  testing philosophy, verification procedures, known-good test cases,         ║
║  and regression testing approach.                                            ║
║                                                                              ║
║  HOW TO USE THIS DOCUMENT                                                    ║
║  ─────────────────────────                                                   ║
║  1. Before making changes: Find the relevant subsystem section and note      ║
║     the test sessions and verification queries you'll need.                  ║
║  2. After making changes: Run the verification procedures for your           ║
║     subsystem. Check that known-good cases still produce expected output.    ║
║  3. When adding features: Add new test cases to the appropriate section.     ║
║     Include session IDs, expected values, and verification queries.          ║
║                                                                              ║
║  WHEN TO UPDATE THIS DOCUMENT                                                ║
║  ────────────────────────────                                                ║
║  - You discover a new "known-good" or "known-bad" test case                  ║
║  - You add verification queries that others should reuse                     ║
║  - You change thresholds or gates that affect expected outputs               ║
║  - You add a new subsystem that needs verification procedures                ║
║                                                                              ║
║  Last Updated: 2026-01-20 (added FK constraint handling procedure)           ║
║  Register: Listed in docs/DOCUMENTATION_REGISTER.md under Operational Docs   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
-->

---

## Testing Philosophy

Arnold does **not** use a traditional pytest suite. This is intentional:

1. **Rapidly evolving system** — Test fixtures would constantly break during active development
2. **Data-dependent behavior** — Real verification requires real data, not mocks
3. **Human-in-the-loop** — Many quality decisions require visual inspection and judgment
4. **Claude as verifier** — Each thread can run queries and inspect results directly

Instead, we use:
- **Verification queries** — SQL checks against known-good cases
- **Visual inspection** — Matplotlib visualizations for signal processing
- **Regression testing** — Re-run pipelines and compare outputs
- **Documented test cases** — Known sessions with expected behaviors

### When to Add Formal Tests

Consider pytest for:
- Pure functions with stable interfaces (unit tests)
- Critical calculations that must not regress (e.g., TRIMP formula)
- API contracts between MCPs

Continue manual verification for:
- Quality gate tuning (thresholds are empirical)
- Visual signal inspection (peak detection, recovery curves)
- End-to-end pipeline behavior
- Anything requiring human judgment

---

## Quick Reference

| Subsystem | Primary Verification | Key Test Cases |
|-----------|---------------------|----------------|
| HRR Detection | `hrr_qc_viz.py` | S22:I3 (plateau), S51:I3 (peak shift) |
| Workout Logging | Database queries | Check `strength_sessions`, `executed_sets` |
| Sync Pipeline | `run_sync` output | Check for errors, row counts |
| Analytics Views | SQL spot checks | ACWR, TRIMP calculations |
| Exercise Resolution | `resolve_exercises` tool | Fuzzy matching accuracy |

---

## HRR (Heart Rate Recovery)

### Verification Commands

```bash
# Visualize specific session (PRIMARY VERIFICATION)
python scripts/hrr_qc_viz.py --session-id <N>

# Reprocess single session
python scripts/hrr_feature_extraction.py --session-id <N>

# Reprocess all sessions (FULL REGRESSION)
python scripts/hrr_feature_extraction.py --all
```

### Known Test Cases

| Session | Interval | Pattern | Expected Behavior | Notes |
|---------|----------|---------|-------------------|-------|
| 22 | 1 | Delayed plateau | r2_15_45 trigger, +141s shift | Forward reanchoring test (rejected at 45s) |
| 22 | 3 | Gradual deceleration | -24s backward shift, HRR60 ~21 | Backward peak search test case (Issue #43) |
| 51 | 3 | False peak | Peak shift +54s corrects it | Has `peak_adjustments` record |
| 5 | 10 | Plateau anchor | Peak shift +120s corrects it | Has `peak_adjustments` record |
| 70 | — | Clean session | 11 pass, 0 flagged, 1 rejected | Good regression baseline |

> **Note (2026-01-20)**: Session 22 is the primary test case for Issue #43 enhancements:
> - **I1**: Tests r2_15_45 trigger for forward reanchoring (correctly rejected after shift due to 45s duration)
> - **I3**: Tests backward peak search (-24s shift corrects gradual deceleration pattern)

### Querying Existing QC Data

Before modifying detection logic, check what manual corrections exist:

```sql
-- View all peak adjustments (manual peak shifts)
SELECT 
    pa.polar_session_id,
    ps.start_time::date as session_date,
    pa.interval_order,
    pa.shift_seconds,
    pa.reason
FROM peak_adjustments pa
JOIN polar_sessions ps ON pa.polar_session_id = ps.id
ORDER BY pa.polar_session_id;

-- View all quality overrides (force-pass/force-reject)
SELECT * FROM hrr_quality_overrides;

-- View interval reviews (flag clearing, verification)
SELECT * FROM hrr_review_status;
```

**Full documentation**: `/docs/hrr_quality_gates.md` → "Querying Existing QC Data" section

### Verification Queries

```sql
-- Check specific interval metrics
SELECT 
    interval_order, peak_hr, hrr60, hrr120,
    r2_0_30, r2_30_60, r2_0_60,
    tau_seconds, quality_status, auto_reject_reason
FROM hr_recovery_intervals
WHERE polar_session_id = <N>
ORDER BY interval_order;

-- Summary by session (regression check)
SELECT 
    polar_session_id,
    COUNT(*) as total,
    SUM(CASE WHEN quality_status = 'pass' THEN 1 ELSE 0 END) as pass,
    SUM(CASE WHEN quality_status = 'flagged' THEN 1 ELSE 0 END) as flagged,
    SUM(CASE WHEN quality_status = 'rejected' THEN 1 ELSE 0 END) as rejected
FROM hr_recovery_intervals
GROUP BY polar_session_id
ORDER BY polar_session_id;

-- Find intervals that might have plateau issues
SELECT polar_session_id, interval_order, peak_hr, hrr60, r2_0_30
FROM hr_recovery_intervals
WHERE r2_0_30 < 0.65 
   OR (hrr60 IS NOT NULL AND hrr60 < 10)
ORDER BY polar_session_id, interval_order;

-- Check quality gate rejection distribution
SELECT auto_reject_reason, COUNT(*) 
FROM hr_recovery_intervals 
WHERE quality_status = 'rejected'
GROUP BY auto_reject_reason
ORDER BY COUNT(*) DESC;
```

### Quality Gate Thresholds

Current thresholds (verify these haven't drifted):

| Gate | Metric | Threshold | Reject Reason |
|------|--------|-----------|---------------|
| 0 | r2_0_60 | None | insufficient_duration_Xs |
| 1 | slope_90_120 | > 0.1 bpm/sec | activity_resumed |
| 3 | best_r2 | < 0.75 | poor_fit_quality |
| 4 | r2_30_60 | < 0.75 | r2_30_60_below_0.75 |
| 5 | r2_0_30 | < 0.5 | double_peak |
| 6 | tau_seconds | >= 299 | tau_clipped |

> **Note (2026-01-20)**: Gates 0 and 2 now include duration in rejection reason
> (e.g., `insufficient_duration_45s`, `no_valid_r2_windows_52s`) for easier debugging.

**Reference**: `/docs/hrr_quality_gates.md`

### Regression Testing Procedure

1. Note current pass/flagged/rejected counts per session
2. Make code changes
3. Run `--all` extraction
4. Compare counts — significant shifts need investigation
5. Spot-check 2-3 sessions visually with `hrr_qc_viz.py`

---

## Workout Logging

### Verification Commands

```bash
# Check MCP is responding
# Use arnold-training:get_recent_workouts tool
```

### Verification Queries

```sql
-- Recent logged workouts
SELECT id, workout_date, name, session_rpe, duration_minutes
FROM strength_sessions
ORDER BY workout_date DESC
LIMIT 10;

-- Check sets were logged
SELECT 
    ss.workout_date, 
    e.name as exercise,
    es.set_number, es.reps, es.load_lbs, es.rpe
FROM executed_sets es
JOIN strength_sessions ss ON es.session_id = ss.id
JOIN exercises e ON es.exercise_id = e.id
WHERE ss.workout_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY ss.workout_date DESC, es.id;

-- Verify plan → execution linking
SELECT 
    pw.plan_date,
    pw.goal,
    ss.workout_date,
    ss.name
FROM planned_workouts pw
LEFT JOIN strength_sessions ss ON ss.from_plan_id = pw.plan_id
WHERE pw.plan_date >= CURRENT_DATE - INTERVAL '14 days'
ORDER BY pw.plan_date;
```

### Known Issues to Watch

- **Issue #41**: `exercise_name` not resolved during logging
- **Issue #40**: Analytics tools query legacy schema
- **Issue #25**: Constraint errors on completion

---

## Sync Pipeline

### Verification Commands

```bash
# Run full sync
# Use arnold-analytics:run_sync tool

# Check sync history
# Use arnold-analytics:get_sync_history tool
```

### Expected Outputs

A successful sync shows:
- No errors in output
- Row counts for each step (polar, ultrahuman, fit, etc.)
- Timestamps for data freshness

### Verification Queries

```sql
-- Check data freshness
SELECT 
    'polar_sessions' as source,
    MAX(start_time) as latest
FROM polar_sessions
UNION ALL
SELECT 
    'ultrahuman_daily',
    MAX(date)::timestamp
FROM ultrahuman_daily
UNION ALL
SELECT
    'hr_samples',
    MAX(timestamp)
FROM hr_samples;

-- Check for sync gaps (missing dates)
SELECT date_trunc('day', d)::date as missing_date
FROM generate_series(
    (SELECT MIN(date) FROM ultrahuman_daily),
    CURRENT_DATE - 1,
    '1 day'
) d
WHERE d::date NOT IN (SELECT date FROM ultrahuman_daily);
```

---

## Analytics Views

### Key Views to Spot-Check

```sql
-- ACWR calculation
SELECT * FROM training_load_acwr 
ORDER BY activity_date DESC 
LIMIT 7;

-- Verify ACWR is in expected range (0.8-1.3 normal, >1.5 risk)
SELECT 
    activity_date,
    acwr,
    CASE 
        WHEN acwr < 0.8 THEN 'undertrained'
        WHEN acwr > 1.5 THEN 'injury_risk'
        ELSE 'optimal'
    END as zone
FROM training_load_acwr
WHERE activity_date >= CURRENT_DATE - INTERVAL '14 days';

-- HRV trend check
SELECT 
    recorded_date,
    hrv_rmssd,
    hrv_7d_avg,
    hrv_30d_avg
FROM daily_readiness
WHERE recorded_date >= CURRENT_DATE - INTERVAL '14 days'
ORDER BY recorded_date DESC;
```

---

## Exercise Resolution

### Verification Procedure

Test fuzzy matching with known cases:

```
Input: "KB swing" → Expected: "Kettlebell Swing"
Input: "RDL" → Expected: "Romanian Deadlift"
Input: "pullup" → Expected: "Pull-up" or "Chin-up" (should ask)
Input: "bench" → Expected: clarification needed (multiple matches)
```

### Verification Query

```sql
-- Check alias coverage
SELECT 
    e.name,
    array_agg(a.alias) as aliases
FROM exercises e
LEFT JOIN exercise_aliases a ON e.id = a.exercise_id
WHERE e.name ILIKE '%deadlift%'
GROUP BY e.id, e.name;
```

---

## Neo4j Graph Verification

### Basic Connectivity

```cypher
// Check node counts
MATCH (n) RETURN labels(n)[0] as label, count(*) as count
ORDER BY count DESC;

// Check relationship counts
MATCH ()-[r]->() RETURN type(r) as type, count(*) as count
ORDER BY count DESC;
```

### Exercise Graph Integrity

```cypher
// Exercises with muscle targets
MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
RETURN e.name, collect(m.name) as muscles
LIMIT 10;

// Orphan exercises (no relationships)
MATCH (e:Exercise)
WHERE NOT (e)--()
RETURN e.name;
```

---

## Adding New Test Cases

When you discover a useful test case:

1. **Document it** in the appropriate section above
2. **Include**:
   - Session/record ID
   - What pattern it demonstrates
   - Expected behavior/values
   - Any relevant context
3. **Add verification query** if not already covered

### Template

```markdown
| Session | Interval | Pattern | Expected Behavior | Notes |
|---------|----------|---------|-------------------|-------|
| XX | Y | Description | Expected output | Context |
```

---

## Regression Testing Checklist

Before merging significant changes:

- [ ] HRR: Run `--all`, compare pass/flagged/rejected counts
- [ ] HRR: Visualize 2-3 sessions, verify curves look correct
- [ ] Workout: Log a test workout, verify it appears in queries
- [ ] Sync: Run sync, verify no errors
- [ ] Analytics: Spot-check ACWR and readiness views
- [ ] Neo4j: Verify node/relationship counts stable

---

## HRR Re-extraction with FK Constraints

The `hrr_qc_judgments` table has a foreign key (`interval_id`) referencing `hr_recovery_intervals(id)`. This creates a chicken-and-egg problem: re-extraction deletes and recreates intervals with new IDs, breaking the FK relationship.

### Why FK Constraints Matter Here

Foreign keys (FKs) enforce referential integrity—they prevent orphaned records (judgments pointing to non-existent intervals). The problem: `interval_id` is a **surrogate key** (auto-increment), so it changes every time we re-extract. The human judgments reference the old IDs.

**Future fix**: Change FK to use natural key `(polar_session_id, interval_order)` which is stable across re-extractions. For now, we use this unlock/relock procedure.

### Complete Re-extraction Procedure

#### 1. Create Backup

```bash
# Create backup schema with timestamp
psql -d arnold_analytics <<'SQL'
CREATE SCHEMA IF NOT EXISTS backup_YYYYMMDD;

CREATE TABLE backup_YYYYMMDD.hr_recovery_intervals AS 
SELECT * FROM hr_recovery_intervals;

CREATE TABLE backup_YYYYMMDD.hrr_qc_judgments AS 
SELECT * FROM hrr_qc_judgments;

CREATE TABLE backup_YYYYMMDD.hrr_quality_overrides AS 
SELECT * FROM hrr_quality_overrides;
SQL

# Verify backup
psql -d arnold_analytics -c "SELECT count(*) FROM backup_YYYYMMDD.hr_recovery_intervals;"
```

#### 2. Drop FK Constraint (Unlock)

```bash
# Drop the FK constraint
psql -d arnold_analytics -c "
ALTER TABLE hrr_qc_judgments 
DROP CONSTRAINT hrr_qc_judgments_interval_id_fkey;
"

# Verify constraint is gone
psql -d arnold_analytics -c "
SELECT constraint_name FROM information_schema.table_constraints 
WHERE table_name = 'hrr_qc_judgments' AND constraint_type = 'FOREIGN KEY';
"
```

#### 3. Run Re-extraction

```bash
# Re-extract all sessions
python scripts/hrr_feature_extraction.py --all --reprocess

# Or single session for testing
python scripts/hrr_feature_extraction.py --session-id <N>
```

#### 4. Validate with Test Harness

The test harness compares current state to baseline using natural keys:

```sql
-- Create/refresh comparison view (if not exists)
CREATE OR REPLACE VIEW hrr_algo_comparison AS
SELECT 
    COALESCE(c.polar_session_id, b.polar_session_id) as polar_session_id,
    COALESCE(c.interval_order, b.interval_order) as interval_order,
    b.human_judgment as baseline_human,
    b.algo_judgment as baseline_algo,
    c.quality_status as current_algo,
    CASE 
        WHEN b.id IS NULL THEN 'new'
        WHEN c.id IS NULL THEN 'deleted'
        WHEN b.human_judgment = 'pass' AND b.algo_judgment != 'pass' AND c.quality_status = 'pass' THEN 'fixed'
        WHEN b.human_judgment = 'pass' AND b.algo_judgment = 'pass' AND c.quality_status != 'pass' THEN 'REGRESSION'
        WHEN b.algo_judgment = c.quality_status THEN 'unchanged'
        ELSE 'changed'
    END as change_type
FROM hr_recovery_intervals c
FULL OUTER JOIN hrr_algo_baseline_intervals b 
    ON c.polar_session_id = b.polar_session_id 
    AND c.interval_order = b.interval_order;

-- Check for regressions (MUST BE ZERO)
SELECT * FROM hrr_algo_comparison WHERE change_type = 'REGRESSION';

-- Summary of changes
SELECT change_type, count(*) 
FROM hrr_algo_comparison 
GROUP BY change_type 
ORDER BY count(*) DESC;
```

**Critical**: If regressions exist, fix them before proceeding. Options:
- Revert code changes
- Add quality overrides for edge cases
- Update baseline if human judgment was wrong

#### 5. Apply Corrections (if needed)

```sql
-- Add quality override for specific intervals
INSERT INTO hrr_quality_overrides (polar_session_id, interval_order, override_action, reason)
VALUES 
    (4, 12, 'force_reject', 'tau_clipped_300'),
    (25, 14, 'force_reject', 'tau_clipped_300');

-- Update baseline if human judgment was incorrect
UPDATE hrr_algo_baseline_intervals 
SET human_judgment = 'pass'
WHERE (polar_session_id, interval_order) IN ((47,5), (55,15));
```

#### 6. Remap Judgments to New IDs

```bash
# Update judgment interval_ids using natural key lookup
psql -d arnold_analytics -c "
UPDATE hrr_qc_judgments j
SET interval_id = i.id
FROM hr_recovery_intervals i
WHERE j.polar_session_id = i.polar_session_id
  AND j.interval_order = i.interval_order;
"

# Verify no orphans
psql -d arnold_analytics -c "SELECT count(*) FROM hrr_qc_judgments WHERE interval_id IS NULL;"
```

#### 7. Restore FK Constraint (Relock)

```bash
# Re-add FK constraint
psql -d arnold_analytics -c "
ALTER TABLE hrr_qc_judgments 
ADD CONSTRAINT hrr_qc_judgments_interval_id_fkey 
FOREIGN KEY (interval_id) REFERENCES hr_recovery_intervals(id);
"

# Verify constraint exists
psql -d arnold_analytics -c "
SELECT constraint_name FROM information_schema.table_constraints 
WHERE table_name = 'hrr_qc_judgments' AND constraint_type = 'FOREIGN KEY';
"
```

#### 8. Final Validation

```sql
-- Verify counts match
SELECT 
    (SELECT count(*) FROM hr_recovery_intervals) as intervals,
    (SELECT count(*) FROM hrr_qc_judgments) as judgments,
    (SELECT count(*) FROM hrr_qc_judgments WHERE interval_id IS NULL) as orphaned;

-- Verify no regressions
SELECT change_type, count(*) 
FROM hrr_algo_comparison 
GROUP BY change_type;
```

#### 9. Cleanup

```bash
# Only after confident everything is correct
psql -d arnold_analytics -c "DROP SCHEMA backup_YYYYMMDD CASCADE;"
```

### Quick Reference: Unlock/Relock Commands

```bash
# UNLOCK (drop FK)
psql -d arnold_analytics -c "ALTER TABLE hrr_qc_judgments DROP CONSTRAINT hrr_qc_judgments_interval_id_fkey;"

# ... do work ...

# REMAP IDs
psql -d arnold_analytics -c "UPDATE hrr_qc_judgments j SET interval_id = i.id FROM hr_recovery_intervals i WHERE j.polar_session_id = i.polar_session_id AND j.interval_order = i.interval_order;"

# RELOCK (add FK)
psql -d arnold_analytics -c "ALTER TABLE hrr_qc_judgments ADD CONSTRAINT hrr_qc_judgments_interval_id_fkey FOREIGN KEY (interval_id) REFERENCES hr_recovery_intervals(id);"
```

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| FK constraint violation on add | Orphaned judgments | Run remap query first |
| NULL interval_ids after remap | Natural key mismatch | Check if intervals were deleted |
| Constraint already exists | Double-add attempt | Drop first, then add |
| Regressions in test harness | Algorithm change broke cases | Fix code or add overrides |

---

## Related Documentation

- `/docs/hrr_quality_gates.md` — HRR gate details and QC workflow
- `/docs/handoffs/2026-01-17-hrr-qc-review-workflow.md` — HRR QC procedures
- `/docs/DATA_DICTIONARY.md` — Schema reference for queries
- `/docs/adr/005-hrr-pipeline-architecture.md` — HRR architecture decisions
