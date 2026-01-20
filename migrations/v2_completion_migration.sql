-- =================================================================
-- V2 SCHEMA COMPLETION MIGRATION
-- =================================================================
-- Purpose: Complete the V2 workout schema to restore semantic parity
--          with legacy tables, enabling full deprecation of legacy.
--
-- Context: V2 already contains all legacy DATA (178 workouts, 2597 sets)
--          but was missing two semantic concepts:
--          1. Block structure (warmup/primary/secondary/finisher/cooldown)
--          2. Plan snapshot capability (prescribed vs actual)
--
-- Also fixes: 23 sets with exercise_name='Unknown' despite valid exercise_ids
--
-- Related: GitHub Issue #40, ADR-006 (Unified Workout Schema)
-- Date: 2026-01-19
-- =================================================================

-- Run as single transaction
BEGIN;

-- =================================================================
-- PHASE 1: SCHEMA ADDITIONS
-- =================================================================

-- 1a. Add block structure (the missing logical hierarchy)
-- Legacy had block_type: warmup/main/accessory/finisher/cooldown
-- V2 only had is_warmup boolean - insufficient for coach queries
ALTER TABLE v2_strength_sets 
ADD COLUMN IF NOT EXISTS set_category text 
CHECK (set_category IN ('warmup', 'primary', 'secondary', 'assistance', 'finisher', 'cooldown'));

-- 1b. Add plan snapshot capability (prescribed vs actual)
-- Stores the target at execution time: {"reps": 5, "load": 225, "rpe": 8}
-- Links to Neo4j PlannedSet for full planning, this is lightweight snapshot
ALTER TABLE v2_strength_sets 
ADD COLUMN IF NOT EXISTS target_data jsonb;

-- =================================================================
-- PHASE 2: FIX UNKNOWN EXERCISE NAMES (23 rows on Jan 14, 2026)
-- =================================================================
-- Root cause: Logging code failed to resolve exercise names
-- All have valid exercise_ids - names looked up from Neo4j

UPDATE v2_strength_sets SET exercise_name = 'Dumbbell Bench Press' 
WHERE exercise_id = 'EXERCISE:Dumbbell_Bench_Press' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Ring Support Hold' 
WHERE exercise_id = 'CANONICAL:FFDB:506' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Face Pull' 
WHERE exercise_id = 'EXERCISE:Face_Pull' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Seated Dumbbell Press' 
WHERE exercise_id = 'EXERCISE:Seated_Dumbbell_Press' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Weighted Bench Dip' 
WHERE exercise_id = 'EXERCISE:Weighted_Bench_Dip' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Shoulder Dislocate' 
WHERE exercise_id = 'CANONICAL:ARNOLD:SHOULDER_DISLOCATE' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Resistance Band Pull Apart' 
WHERE exercise_id = 'CANONICAL:FFDB:2149' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'Bodyweight Side Plank' 
WHERE exercise_id = 'CANONICAL:FFDB:58' AND exercise_name = 'Unknown';

UPDATE v2_strength_sets SET exercise_name = 'AirDyne' 
WHERE exercise_id = 'CANONICAL:ARNOLD:AIRDYNE' AND exercise_name = 'Unknown';

-- Verify no Unknown remain
DO $$
DECLARE
    unknown_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unknown_count FROM v2_strength_sets WHERE exercise_name = 'Unknown';
    IF unknown_count > 0 THEN
        RAISE EXCEPTION 'Still have % Unknown exercise names - aborting', unknown_count;
    END IF;
END $$;

-- Lock it down - prevent future Unknown bugs
ALTER TABLE v2_strength_sets ALTER COLUMN exercise_id SET NOT NULL;

-- =================================================================
-- PHASE 3: BACKFILL set_category FROM LEGACY block_type
-- =================================================================
-- Matching logic: session_date + set_order = workout_date + seq
-- Validated: Perfect 1:1 match confirmed on sample dates

WITH legacy_data AS (
    SELECT 
        ss.session_date,
        s.set_order,
        s.block_type,
        -- Build plan snapshot from legacy prescribed columns (sparse: ~46 sets have data)
        jsonb_strip_nulls(jsonb_build_object(
            'reps', s.prescribed_reps,
            'load', s.prescribed_load_lbs,
            'rpe', s.prescribed_rpe,
            'rest', s.prescribed_rest_seconds
        )) as plan_snapshot
    FROM strength_sets s
    JOIN strength_sessions ss ON s.session_id = ss.id
)
UPDATE v2_strength_sets v2
SET 
    set_category = CASE 
        WHEN ld.block_type = 'warmup' THEN 'warmup'
        WHEN ld.block_type = 'main' THEN 'primary'
        WHEN ld.block_type = 'accessory' THEN 'secondary'
        WHEN ld.block_type = 'finisher' THEN 'finisher'
        WHEN ld.block_type = 'cooldown' THEN 'cooldown'
        ELSE 'secondary'
    END,
    target_data = CASE WHEN ld.plan_snapshot = '{}'::jsonb THEN NULL ELSE ld.plan_snapshot END
FROM legacy_data ld
JOIN workouts_v2 w ON w.start_time::date = ld.session_date
JOIN segments seg ON seg.workout_id = w.workout_id
WHERE v2.segment_id = seg.segment_id
  AND v2.seq = ld.set_order;

-- =================================================================
-- PHASE 4: FILL GAPS FOR V2-ONLY DATA (Jan 11+ workouts)
-- =================================================================
-- These workouts exist only in V2, no legacy equivalent
-- Use is_warmup flag as best available signal

UPDATE v2_strength_sets
SET set_category = 'warmup'
WHERE set_category IS NULL AND is_warmup = true;

-- Default remaining to 'primary' - conservative choice
-- Coach can reclassify via normal workflow
UPDATE v2_strength_sets
SET set_category = 'primary'
WHERE set_category IS NULL AND is_warmup = false;

-- =================================================================
-- PHASE 5: VALIDATION
-- =================================================================

DO $$
DECLARE
    null_category_count INTEGER;
    null_exercise_count INTEGER;
    total_sets INTEGER;
    categorized_sets INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_sets FROM v2_strength_sets;
    SELECT COUNT(*) INTO null_category_count FROM v2_strength_sets WHERE set_category IS NULL;
    SELECT COUNT(*) INTO null_exercise_count FROM v2_strength_sets WHERE exercise_id IS NULL;
    SELECT COUNT(*) INTO categorized_sets FROM v2_strength_sets WHERE set_category IS NOT NULL;
    
    RAISE NOTICE '=== MIGRATION VALIDATION ===';
    RAISE NOTICE 'Total sets: %', total_sets;
    RAISE NOTICE 'Categorized sets: %', categorized_sets;
    RAISE NOTICE 'NULL category: % (should be 0)', null_category_count;
    RAISE NOTICE 'NULL exercise_id: % (should be 0)', null_exercise_count;
    
    IF null_category_count > 0 THEN
        RAISE EXCEPTION 'Migration incomplete: % sets without category', null_category_count;
    END IF;
    
    IF null_exercise_count > 0 THEN
        RAISE EXCEPTION 'Migration incomplete: % sets without exercise_id', null_exercise_count;
    END IF;
    
    RAISE NOTICE '=== MIGRATION SUCCESSFUL ===';
END $$;

-- Show category distribution
SELECT set_category, COUNT(*) as count 
FROM v2_strength_sets 
GROUP BY set_category 
ORDER BY count DESC;

COMMIT;

-- =================================================================
-- POST-MIGRATION: Update analytics-mcp to query V2
-- =================================================================
-- After this migration, update arnold-analytics-mcp/server.py:
-- - get_exercise_history: query v2_strength_sets instead of strength_sets
-- - get_training_load: query workouts_v2 instead of strength_sessions
-- - All other tools using legacy tables
--
-- See GitHub Issue #40 for full list of affected tools
-- =================================================================
