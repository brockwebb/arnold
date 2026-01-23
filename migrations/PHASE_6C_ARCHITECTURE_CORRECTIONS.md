# Phase 6c: Architecture Corrections

**Priority:** Execute after Phase 6b  
**Issue:** Several implementation choices violated the sport-agnostic design we agreed on

## Problem Summary

| Issue | What We Designed | What Got Implemented |
|-------|------------------|---------------------|
| Views hardcode sport | Sport is a property, not filter | `WHERE modality = 'strength'` everywhere |
| v_all_activity_events | DROP entirely | "Simplified to strength only" |
| Endurance logging | Don't touch `endurance_sessions` | Deprecated tables it depends on |
| Unlinked sets | Graceful handling | No null-safety in deviation view |

## Correction 1: Remove Hardcoded Sport Filters

The "95% strength" lesson meant "don't over-engineer separate tables per sport."  
It did NOT mean "only support strength."

**Fix these views to be sport-agnostic:**

```sql
-- srpe_training_load: Remove modality filter
-- All workouts with RPE and duration contribute to training load, regardless of sport
DROP VIEW IF EXISTS srpe_training_load CASCADE;

CREATE VIEW srpe_training_load AS
SELECT 
  w.workout_id,
  w.start_time::date AS workout_date,
  w.duration_minutes,
  w.session_rpe,
  w.sport_type,  -- Include sport as OUTPUT column, not filter
  (w.duration_minutes * COALESCE(w.session_rpe, 5)) AS srpe_load,  -- Default RPE 5 if missing
  COUNT(DISTINCT s.set_id) AS total_sets,
  SUM(s.reps) AS total_reps,
  SUM(COALESCE(s.reps, 0) * COALESCE(s.load, 0)) AS total_volume_lbs
FROM workouts w
LEFT JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
GROUP BY w.workout_id, w.start_time, w.duration_minutes, w.session_rpe, w.sport_type;

COMMENT ON VIEW srpe_training_load IS 
'Training load for ALL workout types. Filter by sport_type in your query if needed.';
```

```sql
-- training_load_daily: Remove modality filter
DROP VIEW IF EXISTS training_load_daily CASCADE;

CREATE VIEW training_load_daily AS
SELECT 
  w.start_time::date AS workout_date,
  SUM(w.duration_minutes * COALESCE(w.session_rpe, 5)) AS daily_srpe_load,
  SUM(w.duration_minutes) AS daily_duration,
  COUNT(DISTINCT w.workout_id) AS workout_count,
  array_agg(DISTINCT w.sport_type) AS sport_types  -- Show what sports, don't filter
FROM workouts w
GROUP BY w.start_time::date;

COMMENT ON VIEW training_load_daily IS 
'Daily training load aggregated across ALL sports. Use sport_types column to see breakdown.';
```

```sql
-- workout_summaries: Remove modality filter
DROP VIEW IF EXISTS workout_summaries CASCADE;

CREATE VIEW workout_summaries AS
SELECT 
  w.workout_id,
  w.start_time,
  w.end_time,
  w.duration_minutes,
  w.session_rpe,
  w.sport_type,  -- Include as column
  w.purpose,
  w.notes,
  w.source,
  w.plan_id,
  COUNT(DISTINCT b.block_id) AS block_count,
  COUNT(DISTINCT s.set_id) AS set_count,
  COUNT(DISTINCT s.exercise_name) AS exercise_count,
  SUM(s.reps) AS total_reps,
  SUM(COALESCE(s.reps, 0) * COALESCE(s.load, 0)) AS total_volume_lbs,
  -- Endurance metrics (nullable, populated when relevant)
  SUM(s.distance) AS total_distance,
  MAX(s.hr_avg) AS max_hr_avg
FROM workouts w
LEFT JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
GROUP BY w.workout_id, w.start_time, w.end_time, w.duration_minutes, 
         w.session_rpe, w.sport_type, w.purpose, w.notes, w.source, w.plan_id;

COMMENT ON VIEW workout_summaries IS 
'Summary of ALL workouts regardless of sport. Includes both strength (reps/volume) and endurance (distance/hr) metrics.';
```

## Correction 2: Drop v_all_activity_events Entirely

This view was an artifact of the failed ADR-006 multi-table design. It should not exist in any form.

```sql
DROP VIEW IF EXISTS v_all_activity_events CASCADE;

-- Do NOT recreate. This abstraction is dead.
-- If you need cross-sport queries, use workout_summaries.
```

## Correction 3: Restore Endurance Tables (Temporary)

We deprecated tables that `log_endurance_session()` depends on. Until we update the function to use the unified `sets` table, restore them:

```sql
-- Restore endurance tables (they were renamed, not dropped)
ALTER TABLE IF EXISTS _deprecated_v2_running_intervals RENAME TO v2_running_intervals;
ALTER TABLE IF EXISTS _deprecated_v2_rowing_intervals RENAME TO v2_rowing_intervals;
ALTER TABLE IF EXISTS _deprecated_v2_cycling_intervals RENAME TO v2_cycling_intervals;
ALTER TABLE IF EXISTS _deprecated_v2_swimming_laps RENAME TO v2_swimming_laps;
ALTER TABLE IF EXISTS _deprecated_segment_events_generic RENAME TO segment_events_generic;
```

**TODO (Future):** Update `log_endurance_session()` to write to unified `sets` table with endurance columns (distance, duration_s, pace, hr_avg, hr_zone). Then these tables can be truly deprecated.

## Correction 4: Handle Unlinked Sets Gracefully

2,626 existing sets have no `planned_set_id`. The deviation view must handle this gracefully.

```sql
-- Update execution_vs_plan to handle unlinked sets
DROP VIEW IF EXISTS execution_vs_plan;

CREATE VIEW execution_vs_plan AS
SELECT 
  s.set_id,
  s.block_id,
  b.workout_id,
  w.start_time::date AS workout_date,
  
  -- Exercise
  s.exercise_name,
  
  -- Actual execution
  s.reps AS actual_reps,
  s.load AS actual_load,
  s.rpe AS actual_rpe,
  
  -- Planned prescription (NULL for unlinked sets)
  ps.prescribed_reps AS planned_reps,
  ps.prescribed_load_lbs AS planned_load,
  ps.prescribed_rpe AS planned_rpe,
  
  -- Block context
  b.name AS block_name,
  b.block_type,
  
  -- Plan linkage status
  s.planned_set_id,
  CASE 
    WHEN s.planned_set_id IS NULL THEN FALSE 
    ELSE TRUE 
  END AS is_linked_to_plan,
  
  -- Deviation classification (only meaningful for linked sets)
  CASE
    WHEN s.planned_set_id IS NULL THEN 'unlinked'  -- Not an error, just no plan
    WHEN ps.id IS NULL THEN 'orphaned'  -- FK exists but target missing (data issue)
    WHEN s.reps IS NULL AND ps.prescribed_reps IS NOT NULL THEN 'skipped'
    WHEN s.reps IS NOT NULL AND ps.prescribed_reps IS NULL THEN 'added'
    WHEN ABS(COALESCE(s.reps, 0) - COALESCE(ps.prescribed_reps, 0)) > 2 THEN 'reps_deviation'
    WHEN ABS(COALESCE(s.load, 0) - COALESCE(ps.prescribed_load_lbs, 0)) > 10 THEN 'load_deviation'
    ELSE 'as_planned'
  END AS deviation_type,
  
  -- Deviation magnitude (NULL for unlinked)
  CASE WHEN s.planned_set_id IS NOT NULL THEN (s.reps - ps.prescribed_reps) END AS reps_delta,
  CASE WHEN s.planned_set_id IS NOT NULL THEN (s.load - ps.prescribed_load_lbs) END AS load_delta
  
FROM sets s
JOIN blocks b ON s.block_id = b.block_id
JOIN workouts w ON b.workout_id = w.workout_id
LEFT JOIN planned_sets ps ON s.planned_set_id = ps.id;

COMMENT ON VIEW execution_vs_plan IS 
'Compares executed sets against planned prescriptions.
- is_linked_to_plan: FALSE for ad-hoc/historical sets (this is normal, not an error)
- deviation_type "unlinked": Set was logged without a plan (valid state)
- deviation_type "orphaned": FK exists but planned_set missing (data issue, investigate)
Most historical data will be unlinked. Only sets from confirmed plans will have linkage.';
```

## Correction 5: Update Cascaded Views

Any view that depends on the corrected views needs rebuilding. Check these:

```sql
-- List views that might need updating
SELECT viewname 
FROM pg_views 
WHERE schemaname = 'public'
  AND definition LIKE '%training_load_daily%'
  OR definition LIKE '%srpe_training_load%'
  OR definition LIKE '%workout_summaries%';
```

Rebuild them after the base views are corrected. The CASCADE in DROP VIEW should handle dependencies, but verify they're recreated correctly.

## Correction 6: Document the Design Intent

Add comments to core tables reinforcing sport-agnostic design:

```sql
COMMENT ON TABLE workouts IS 
'Core workout session record. Sport-agnostic - sport_type is a property, not a discriminator.
All workout types (strength, running, cycling, etc.) use this same table.';

COMMENT ON TABLE blocks IS 
'Training phase container within a workout. Sport-agnostic.
block_type = training phase (warmup, main, accessory, conditioning, cooldown, circuit, emom, skill)
modality = sport type (optional override of workout.sport_type)';

COMMENT ON TABLE sets IS 
'Atomic execution unit. Sport-agnostic with nullable columns for different modalities.
Strength: reps, load, load_unit, rpe
Endurance: distance, distance_unit, duration_s, pace, hr_avg, hr_zone
Use whichever columns apply. NULLs are normal.';
```

## Verification

```sql
-- Views have no hardcoded modality filters
SELECT viewname, 
       CASE WHEN definition LIKE '%modality%=%strength%' THEN 'FAIL: hardcoded' ELSE 'OK' END AS status
FROM pg_views 
WHERE schemaname = 'public'
  AND viewname IN ('srpe_training_load', 'training_load_daily', 'workout_summaries');
-- All should show 'OK'

-- v_all_activity_events is gone
SELECT COUNT(*) FROM pg_views WHERE viewname = 'v_all_activity_events';
-- Should be 0

-- Endurance tables restored (temporary)
SELECT table_name FROM information_schema.tables 
WHERE table_name IN ('v2_running_intervals', 'v2_rowing_intervals');
-- Should return rows

-- Unlinked sets handled gracefully
SELECT deviation_type, COUNT(*) 
FROM execution_vs_plan 
GROUP BY deviation_type;
-- 'unlinked' should appear with count ~2626
```

## Summary of Changes

| Item | Action | Rationale |
|------|--------|-----------|
| Sport filters in views | REMOVE | Sport is property, not discriminator |
| v_all_activity_events | DROP | Dead abstraction from failed ADR-006 |
| Endurance tables | RESTORE (temp) | Don't break consumers until we migrate them |
| Unlinked sets | Handle gracefully | 2626 historical sets have no plan - this is normal |
| Table comments | ADD | Document design intent to prevent future drift |

## Future Work (Not This Migration)

1. **Migrate `log_endurance_session()`** to use unified `sets` table
2. **Then deprecate** the v2_*_intervals tables for real
3. **Add sport-specific views** only if needed (e.g., `running_workout_summaries`) that filter on sport_type
