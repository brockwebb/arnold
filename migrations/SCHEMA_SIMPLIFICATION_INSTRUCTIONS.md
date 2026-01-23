# Schema Simplification Migration - Claude Code Instructions

**Date:** 2026-01-20 (Updated)  
**Purpose:** Migrate from `workouts_v2 → segments → v2_strength_sets` to simplified `workouts → blocks → sets`

## Scope (READ THIS FIRST)

**This migration is ONLY about the workout log layer.** 

- ✅ Rename tables: `workouts_v2` → `workouts`, `segments` → `blocks`, `v2_strength_sets` → `sets`
- ✅ Update views that reference old table names
- ✅ Update MCPs to use new table names
- ✅ Clean up duplicate data from bugs
- ❌ **DO NOT** touch `endurance_sessions` — different schema, keep separate
- ❌ **DO NOT** build device telemetry infrastructure — that's ADR-008 (future)
- ❌ **DO NOT** drop tables — rename unused tables to `_deprecated_*` for safety

**Why the scope limit:** Device data (Polar, Suunto, Garmin) needs its own architecture with provenance, versioning, and athlete calibration. That's a separate project. This migration just cleans up the human-authored workout log.

---

## Context

We over-engineered the workout schema with sport-discriminator patterns that added complexity without benefit. This migration simplifies to three clean tables with proper naming.

### Key Lessons (for ADR appendix)
1. Don't solve problems you don't have (95% strength workouts)
2. "Segment" conflated sport modality and training phase - they're orthogonal
3. Deviation capture at logging time = friction - auto-compute instead
4. Block is general-purpose - don't over-type it
5. OOP maps to relational cleanly - discriminator/child-table pattern added complexity
6. "v2" naming is technical debt

---

## Pre-flight Results (Already Completed)

**4 views will break when tables are renamed:**

| View | References | Action |
|------|------------|--------|
| `srpe_training_load` | workouts_v2, segments, v2_strength_sets | UPDATE |
| `training_load_daily` | workouts_v2, segments, v2_strength_sets | UPDATE |
| `workout_summaries_v2` | workouts_v2, segments, v2_strength_sets | UPDATE + RENAME to `workout_summaries` |
| `v_all_activity_events` | segments, v2_strength_sets, v2_running_intervals, v2_rowing_intervals, v2_cycling_intervals, v2_swimming_laps | DROP (unused multi-modal abstraction) |

**Column renames needed in views:**
- `segment_id` → `block_id`
- `seg.sport_type` → `b.modality`
- `WHERE seg.sport_type = 'strength'` → `WHERE b.modality = 'strength'`

---

## Execution Phases

Execute in order. Run verification gate after each phase before proceeding.

---

## Phase 1: Document Corrected Ontology ✅ COMPLETE

File created: `docs/ontology/workout-structure.md`

---

## Phase 2: Schema Migration (Postgres)

### Step 1: Deprecate Unused Tables (BEFORE renaming core tables)

```sql
-- Rename empty/unused sport-specific tables to deprecated (don't drop - cheap insurance)
ALTER TABLE IF EXISTS v2_running_intervals RENAME TO _deprecated_v2_running_intervals;
ALTER TABLE IF EXISTS v2_rowing_intervals RENAME TO _deprecated_v2_rowing_intervals;
ALTER TABLE IF EXISTS v2_cycling_intervals RENAME TO _deprecated_v2_cycling_intervals;
ALTER TABLE IF EXISTS v2_swimming_laps RENAME TO _deprecated_v2_swimming_laps;
ALTER TABLE IF EXISTS segment_events_generic RENAME TO _deprecated_segment_events_generic;
```

### Step 2: Drop Views That Will Break

```sql
-- Drop views BEFORE renaming tables (they'll fail anyway)
DROP VIEW IF EXISTS v_all_activity_events;  -- unused multi-modal abstraction
DROP VIEW IF EXISTS srpe_training_load;
DROP VIEW IF EXISTS training_load_daily;
DROP VIEW IF EXISTS workout_summaries_v2;
```

### Step 3: Rename Core Tables

```sql
-- Rename core tables
ALTER TABLE workouts_v2 RENAME TO workouts;
ALTER TABLE segments RENAME TO blocks;
ALTER TABLE v2_strength_sets RENAME TO sets;
```

### Step 4: Rename Foreign Key Columns

```sql
-- Rename segment_id to block_id in sets table
ALTER TABLE sets RENAME COLUMN segment_id TO block_id;
```

### Step 5: Add Block Columns

```sql
-- Add block_type for training phase
ALTER TABLE blocks ADD COLUMN IF NOT EXISTS block_type TEXT;

-- Rename sport_type to modality (check if column exists first)
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'blocks' AND column_name = 'sport_type';
ALTER TABLE blocks RENAME COLUMN sport_type TO modality;
```

### Step 6: Add Workout Columns

```sql
-- Add if missing
ALTER TABLE workouts ADD COLUMN IF NOT EXISTS sport_type TEXT;
ALTER TABLE workouts ADD COLUMN IF NOT EXISTS purpose TEXT;
```

### Step 7: Add Set Columns for Future Endurance Support

```sql
-- Nullable columns for endurance data in unified sets table (future use)
ALTER TABLE sets ADD COLUMN IF NOT EXISTS distance NUMERIC;
ALTER TABLE sets ADD COLUMN IF NOT EXISTS distance_unit TEXT;
ALTER TABLE sets ADD COLUMN IF NOT EXISTS duration_s INT;
ALTER TABLE sets ADD COLUMN IF NOT EXISTS pace TEXT;
ALTER TABLE sets ADD COLUMN IF NOT EXISTS hr_avg INT;
ALTER TABLE sets ADD COLUMN IF NOT EXISTS hr_zone TEXT;
ALTER TABLE sets ADD COLUMN IF NOT EXISTS calories NUMERIC;

-- Plan linkage for deviation tracking
ALTER TABLE sets ADD COLUMN IF NOT EXISTS planned_set_id UUID;
-- Note: Only add FK constraint if planned_sets table exists
-- ALTER TABLE sets ADD CONSTRAINT sets_planned_set_id_fkey 
--   FOREIGN KEY (planned_set_id) REFERENCES planned_sets(id);
```

### Step 8: Backfill block_type from JSONB

```sql
-- Backfill from extra JSONB where available
UPDATE blocks SET block_type = extra->>'block_type' WHERE extra->>'block_type' IS NOT NULL;

-- Default remaining to 'main'
UPDATE blocks SET block_type = 'main' WHERE block_type IS NULL;
```

### Step 9: Audit JSONB Before Deciding on Drop

```sql
-- What keys exist in blocks.extra?
SELECT DISTINCT jsonb_object_keys(extra) AS key, COUNT(*) 
FROM blocks 
WHERE extra IS NOT NULL 
GROUP BY key;

-- What keys exist in sets.extra?
SELECT DISTINCT jsonb_object_keys(extra) AS key, COUNT(*) 
FROM sets 
WHERE extra IS NOT NULL 
GROUP BY key;

-- Verify no orphaned data
SELECT COUNT(*) AS orphaned_block_type
FROM blocks 
WHERE block_type IS NULL AND extra->>'block_type' IS NOT NULL;
-- Should be 0
```

**Decision:** Keep `extra` JSONB as escape hatch for truly ad-hoc fields.

### Verification Gate

```sql
-- Tables exist with new names
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name IN ('workouts', 'blocks', 'sets');
-- Should return 3 rows

-- Old names gone (renamed to core tables)
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name IN ('workouts_v2', 'segments', 'v2_strength_sets');
-- Should return 0 rows

-- Deprecated tables exist (safety net)
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '_deprecated_%';
-- Should return the renamed unused tables

-- New columns exist
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'blocks' AND column_name IN ('block_type', 'modality');

SELECT column_name FROM information_schema.columns 
WHERE table_name = 'sets' AND column_name = 'block_id';
```

---

## Phase 3: Recreate Views

### srpe_training_load

```sql
CREATE OR REPLACE VIEW srpe_training_load AS
SELECT 
  w.workout_id,
  w.start_time::date AS workout_date,
  w.duration_minutes,
  w.session_rpe,
  (w.duration_minutes * w.session_rpe) AS srpe_load,
  COUNT(DISTINCT s.set_id) AS total_sets,
  SUM(s.reps) AS total_reps,
  SUM(s.reps * s.load) AS total_volume_lbs
FROM workouts w
JOIN blocks b ON w.workout_id = b.workout_id
JOIN sets s ON b.block_id = s.block_id
WHERE b.modality = 'strength'
GROUP BY w.workout_id, w.start_time, w.duration_minutes, w.session_rpe;
```

### training_load_daily

```sql
CREATE OR REPLACE VIEW training_load_daily AS
SELECT 
  w.start_time::date AS workout_date,
  SUM(w.duration_minutes * w.session_rpe) AS daily_srpe_load,
  SUM(w.duration_minutes) AS daily_duration,
  COUNT(DISTINCT w.workout_id) AS workout_count
FROM workouts w
JOIN blocks b ON w.workout_id = b.workout_id
WHERE b.modality = 'strength'
GROUP BY w.start_time::date;
```

### workout_summaries (renamed from workout_summaries_v2)

```sql
CREATE OR REPLACE VIEW workout_summaries AS
SELECT 
  w.workout_id,
  w.start_time,
  w.end_time,
  w.duration_minutes,
  w.session_rpe,
  w.sport_type,
  w.purpose,
  w.notes,
  w.source,
  COUNT(DISTINCT b.block_id) AS block_count,
  COUNT(DISTINCT s.set_id) AS set_count,
  COUNT(DISTINCT s.exercise_name) AS exercise_count,
  SUM(s.reps) AS total_reps,
  SUM(s.reps * s.load) AS total_volume_lbs
FROM workouts w
LEFT JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
GROUP BY w.workout_id, w.start_time, w.end_time, w.duration_minutes, 
         w.session_rpe, w.sport_type, w.purpose, w.notes, w.source;
```

### Verification

```sql
-- No views reference old names
SELECT viewname FROM pg_views 
WHERE schemaname = 'public'
  AND (definition LIKE '%workouts_v2%' 
    OR definition LIKE '%v2_strength%' 
    OR definition LIKE '%segments%'
    OR definition LIKE '%segment_id%');
-- Should return 0 rows

-- Views work
SELECT * FROM srpe_training_load LIMIT 3;
SELECT * FROM training_load_daily LIMIT 3;
SELECT * FROM workout_summaries LIMIT 3;
```

---

## Phase 4: MCP Updates

### Find all references first

```bash
grep -r "workouts_v2\|v2_strength\|segments\|segment_id" --include="*.py" src/
```

### arnold-training-mcp

| Function | Action |
|----------|--------|
| `complete_with_deviations` | DELETE entirely |
| `complete_as_written` | Simplify - logs final plan state |
| `log_workout` | Update: `segments` → `blocks`, `v2_strength_sets` → `sets`, `segment_id` → `block_id` |
| `get_workout_by_date` | Update table names |
| `get_recent_workouts` | Update table names |
| `create_workout_plan` | Keep (Neo4j) |

### arnold-analytics-mcp

| Function | Action |
|----------|--------|
| `get_exercise_history` | Update table refs |
| `get_training_load` | Update table refs |
| All others | Audit for old table names |

### arnold-memory-mcp

| Function | Action |
|----------|--------|
| `load_briefing` | Update queries to use new table names |

### Verification

After updating, restart all MCPs and test:
```bash
# Test workout logging works
# Test load_briefing returns recent workouts
# Test analytics queries work
```

---

## Phase 5: Deviation View

```sql
CREATE OR REPLACE VIEW execution_vs_plan AS
SELECT 
  s.set_id,
  s.block_id,
  s.exercise_name,
  s.reps AS actual_reps,
  s.load AS actual_load,
  ps.prescribed_reps AS planned_reps,
  ps.prescribed_load_lbs AS planned_load,
  CASE
    WHEN s.reps IS NULL AND ps.prescribed_reps IS NOT NULL THEN 'skipped'
    WHEN s.reps IS NOT NULL AND ps.prescribed_reps IS NULL THEN 'added'
    WHEN ABS(s.reps - ps.prescribed_reps) > 2 THEN 'reps_deviation'
    WHEN ABS(s.load - ps.prescribed_load_lbs) > 10 THEN 'load_deviation'
    ELSE 'as_planned'
  END AS deviation_type,
  (s.reps - ps.prescribed_reps) AS reps_delta,
  (s.load - ps.prescribed_load_lbs) AS load_delta
FROM sets s
JOIN blocks b ON s.block_id = b.block_id
JOIN workouts w ON b.workout_id = w.workout_id
LEFT JOIN planned_sets ps ON s.planned_set_id = ps.id
WHERE w.plan_id IS NOT NULL;
```

**Note:** This view may return empty until workouts are logged with `planned_set_id` populated.

---

## Phase 6: Data Cleanup

### Find Duplicates

```sql
-- Duplicate workouts from double-insert bug (Jan 15-19)
SELECT start_time::date AS workout_date, COUNT(*), array_agg(workout_id) AS ids
FROM workouts 
WHERE start_time >= '2026-01-15'
GROUP BY start_time::date 
HAVING COUNT(*) > 1;
```

### Fix Exercise Name (Jan 20 workout)

```sql
-- "Trap Bar Romanian Deadlift" should be "Trap Bar Deadlift"
UPDATE sets 
SET exercise_name = 'Trap Bar Deadlift'
WHERE block_id IN (
  SELECT block_id FROM blocks 
  WHERE workout_id = 'f80d974d-9323-460d-85f6-e2caf63b48f7'
)
AND exercise_name = 'Trap Bar Romanian Deadlift';
```

### Delete Duplicates (MANUAL REVIEW FIRST)

```sql
-- Show duplicates for review
SELECT w.workout_id, w.start_time, w.duration_minutes, w.session_rpe,
       COUNT(s.set_id) AS set_count
FROM workouts w
LEFT JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
WHERE w.start_time::date IN (
  SELECT start_time::date FROM workouts 
  WHERE start_time >= '2026-01-15'
  GROUP BY start_time::date HAVING COUNT(*) > 1
)
GROUP BY w.workout_id, w.start_time, w.duration_minutes, w.session_rpe
ORDER BY w.start_time;

-- AFTER MANUAL REVIEW: Delete duplicate workout (keep the one with more data)
-- DELETE FROM sets WHERE block_id IN (SELECT block_id FROM blocks WHERE workout_id = 'DUPLICATE_ID');
-- DELETE FROM blocks WHERE workout_id = 'DUPLICATE_ID';
-- DELETE FROM workouts WHERE workout_id = 'DUPLICATE_ID';
```

---

## Phase 7: ADR Updates ✅ COMPLETE

- ADR-006: Marked Superseded, added "Why It Failed" section
- ADR-007: Created - documents simplified design

---

## Phase 8: Neo4j Alignment

### Fix postgres_id kwarg error

The `create_strength_workout_ref` function has a signature mismatch. Locate and fix:

```bash
grep -r "create_strength_workout_ref\|postgres_id" --include="*.py" src/
```

### Terminology alignment

- Ensure Neo4j client uses `block` not `segment` in any new code
- `PlannedBlock` naming is already correct

---

## Master Verification Checklist

After all phases:

- [ ] Core tables renamed: workouts, blocks, sets
- [ ] Old tables deprecated (not dropped): `_deprecated_*`
- [ ] Views recreated and working
- [ ] No "v2" or "segment" references in active code (`grep` returns nothing)
- [ ] No "v2" or "segment" references in views
- [ ] MCPs updated and restarted
- [ ] Can log a workout end-to-end
- [ ] `load_briefing` returns recent workouts
- [ ] Analytics queries work
- [ ] `extra` JSONB audited - all keys accounted for
- [ ] Duplicate workouts cleaned up
- [ ] Exercise name typo fixed
- [ ] Neo4j client fixed (postgres_id kwarg)

---

## Rollback Plan

If something breaks badly:

```sql
-- Rename back (only works if no new data written to new names)
ALTER TABLE workouts RENAME TO workouts_v2;
ALTER TABLE blocks RENAME TO segments;
ALTER TABLE sets RENAME TO v2_strength_sets;
ALTER TABLE sets RENAME COLUMN block_id TO segment_id;

-- Restore deprecated tables
ALTER TABLE _deprecated_v2_running_intervals RENAME TO v2_running_intervals;
-- etc.
```

Better: You already took a pg_dump backup before starting.

---

## Out of Scope (DO NOT DO)

These are future work (ADR-008: Device Telemetry Layer):

- ❌ Device-specific tables (polar_sessions, suunto_sessions, etc.)
- ❌ FIT file ingestion infrastructure
- ❌ Workout-to-device-session matching
- ❌ Athlete calibration parameters (HRmax, HRrest, FTP)
- ❌ Canonical metric computation (TRIMP, TSS)
- ❌ Modifying `endurance_sessions` table

The workout log layer should stay dumb and universal. Device telemetry is a separate concern with its own provenance and versioning requirements.

---

## Quarterly JSONB Audit (Add to Maintenance)

```sql
-- Promotion candidates: keys appearing frequently in extra
SELECT 
  'blocks' AS table_name,
  jsonb_object_keys(extra) AS key, 
  COUNT(*) AS occurrences
FROM blocks 
WHERE extra IS NOT NULL 
GROUP BY key
HAVING COUNT(*) > 10

UNION ALL

SELECT 
  'sets' AS table_name,
  jsonb_object_keys(extra) AS key, 
  COUNT(*) AS occurrences
FROM sets 
WHERE extra IS NOT NULL 
GROUP BY key
HAVING COUNT(*) > 10
ORDER BY occurrences DESC;
```

If a key hits threshold (>10), promote to real column.
