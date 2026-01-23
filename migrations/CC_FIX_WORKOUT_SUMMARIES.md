# CC Task: Proper Fix for workout_summaries View

## Goal
Rebuild `workout_summaries` view with `patterns` and `exercises` JSONB columns by mirroring Neo4j exercise-pattern relationships to Postgres.

## Step 1: Create exercise_patterns mirror table

```sql
-- Mirror of Neo4j (:Exercise)-[:INVOLVES]->(:MovementPattern) relationships
CREATE TABLE IF NOT EXISTS exercise_patterns (
    exercise_id TEXT PRIMARY KEY,
    exercise_name TEXT NOT NULL,
    patterns TEXT[] NOT NULL DEFAULT '{}',
    primary_muscles TEXT[] DEFAULT '{}',
    source TEXT DEFAULT 'neo4j_sync',
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_exercise_patterns_name ON exercise_patterns(exercise_name);

COMMENT ON TABLE exercise_patterns IS 'Mirror of Neo4j exercise-pattern relationships for analytics joins. Source of truth is Neo4j.';
```

## Step 2: Populate from Neo4j

Query Neo4j and insert into Postgres:

```python
# Pseudo-code for sync script
from neo4j import GraphDatabase
import psycopg2

# Query Neo4j
neo4j_query = """
MATCH (e:Exercise)
OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
OPTIONAL MATCH (e)-[:TARGETS {role: 'primary'}]->(m:Muscle)
RETURN 
    e.id AS exercise_id,
    e.name AS exercise_name,
    collect(DISTINCT mp.name) AS patterns,
    collect(DISTINCT m.name) AS primary_muscles
"""

# Insert into Postgres
pg_query = """
INSERT INTO exercise_patterns (exercise_id, exercise_name, patterns, primary_muscles, synced_at)
VALUES (%s, %s, %s, %s, NOW())
ON CONFLICT (exercise_id) DO UPDATE SET
    exercise_name = EXCLUDED.exercise_name,
    patterns = EXCLUDED.patterns,
    primary_muscles = EXCLUDED.primary_muscles,
    synced_at = NOW()
"""
```

Create this as `/scripts/sync_exercise_patterns.py`.

## Step 3: Rebuild workout_summaries view

```sql
DROP VIEW IF EXISTS workout_summaries CASCADE;

CREATE VIEW workout_summaries AS
WITH set_details AS (
    -- Aggregate set details per exercise per workout
    SELECT 
        b.workout_id,
        s.exercise_name,
        s.exercise_id,
        COUNT(*) AS sets,
        SUM(s.reps) AS total_reps,
        MAX(s.load) AS max_load,
        jsonb_agg(
            jsonb_build_object(
                'reps', s.reps,
                'load_lbs', s.load,
                'rpe', s.rpe
            ) ORDER BY s.seq
        ) AS set_details
    FROM blocks b
    JOIN sets s ON b.block_id = s.block_id
    WHERE s.exercise_name IS NOT NULL
    GROUP BY b.workout_id, s.exercise_name, s.exercise_id
),
exercise_agg AS (
    -- Build exercises JSONB array per workout
    SELECT 
        sd.workout_id,
        jsonb_agg(
            jsonb_build_object(
                'name', sd.exercise_name,
                'exercise_id', sd.exercise_id,
                'sets', sd.sets,
                'total_reps', sd.total_reps,
                'max_load', sd.max_load,
                'set_details', sd.set_details
            )
        ) AS exercises
    FROM set_details sd
    GROUP BY sd.workout_id
),
pattern_agg AS (
    -- Aggregate unique patterns per workout via exercise_patterns lookup
    SELECT 
        b.workout_id,
        jsonb_agg(DISTINCT pattern) FILTER (WHERE pattern IS NOT NULL) AS patterns
    FROM blocks b
    JOIN sets s ON b.block_id = s.block_id
    LEFT JOIN exercise_patterns ep ON s.exercise_id = ep.exercise_id 
        OR LOWER(s.exercise_name) = LOWER(ep.exercise_name)
    CROSS JOIN LATERAL unnest(ep.patterns) AS pattern
    GROUP BY b.workout_id
)
SELECT
    w.workout_id,
    w.start_time::date AS workout_date,
    w.start_time,
    w.end_time,
    (w.duration_seconds / 60.0)::numeric(10,2) AS duration_minutes,
    w.rpe AS session_rpe,
    COALESCE(w.sport_type, 'strength') AS workout_type,
    COALESCE(w.purpose, w.notes, 'Workout') AS workout_name,
    w.purpose,
    w.notes,
    w.source,
    COALESCE(ea.exercises, '[]'::jsonb) AS exercises,
    COALESCE(pa.patterns, '[]'::jsonb) AS patterns,
    COUNT(DISTINCT b.block_id) AS block_count,
    COUNT(DISTINCT s.set_id) AS set_count,
    COUNT(DISTINCT s.exercise_name) AS exercise_count,
    SUM(s.reps) AS total_reps,
    SUM(COALESCE(s.reps, 0) * COALESCE(s.load, 0)) AS total_volume_lbs,
    SUM(s.distance) AS total_distance,
    MAX(s.hr_avg) AS max_hr_avg
FROM workouts w
LEFT JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
LEFT JOIN exercise_agg ea ON w.workout_id = ea.workout_id
LEFT JOIN pattern_agg pa ON w.workout_id = pa.workout_id
GROUP BY w.workout_id, w.start_time, w.end_time, w.duration_seconds,
         w.rpe, w.sport_type, w.purpose, w.notes, w.source,
         ea.exercises, pa.patterns;

COMMENT ON VIEW workout_summaries IS 'Workout summary with JSONB exercises and patterns. Patterns sourced from exercise_patterns mirror table.';
```

## Step 4: Rebuild cascaded views

After recreating workout_summaries, rebuild any views that depend on it:

```sql
-- Check for dependencies first
SELECT dependent.relname
FROM pg_depend d
JOIN pg_rewrite r ON d.objid = r.oid
JOIN pg_class dependent ON r.ev_class = dependent.oid
JOIN pg_class source ON d.refobjid = source.oid
WHERE source.relname = 'workout_summaries';
```

Recreate any dependent views.

## Step 5: Verify

```sql
-- Check view has expected columns
\d workout_summaries

-- Test query
SELECT workout_id, workout_date, workout_name, patterns, exercises
FROM workout_summaries
ORDER BY workout_date DESC
LIMIT 3;

-- Verify pattern aggregation works
SELECT workout_date, jsonb_array_length(patterns) as pattern_count
FROM workout_summaries
WHERE patterns != '[]'::jsonb
LIMIT 5;
```

## Step 6: Add to sync pipeline

Add `sync_exercise_patterns.py` call to the sync pipeline so patterns stay current when exercises are added/updated in Neo4j.

## Deliverables

1. `exercise_patterns` table created and populated
2. `workout_summaries` view recreated with all columns
3. `/scripts/sync_exercise_patterns.py` created
4. Verification queries pass
5. Update handoff with completion status

## Do NOT
- Modify the analytics MCP code
- Change table names
- Drop any data
