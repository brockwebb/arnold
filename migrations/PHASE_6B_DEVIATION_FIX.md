# Phase 6b: Fix Deviation Tracking Architecture

**Priority:** Execute after Phase 6 data cleanup  
**Issue:** Deviation view uses JSONB `extra` field instead of proper FK relationships

## Problem

The current `execution_vs_plan` view pulls planned values from `sets.extra` JSONB:
```sql
extra->>'planned_reps', extra->>'planned_load'
```

This works for basic comparison but:
1. Loses plan-to-execution traceability (can't query "all executions of this planned set")
2. Keeps "why" explanations in Postgres instead of Neo4j relationships
3. Doesn't use the `planned_set_id` column we added

## Target Architecture

```
Neo4j (Plans - Source of Truth)
┌─────────────────────────────────────────┐
│ PlannedWorkout → PlannedBlock → PlannedSet │
│ (intentions, relationships, "why")      │
└─────────────────────────────────────────┘
            │
            │ sync on plan confirm
            ▼
Postgres (Plans - Mirror for Joins)
┌─────────────────────────────────────────┐
│ planned_sets (id, exercise, reps, load) │
└─────────────────────────────────────────┘
            │
            │ FK: sets.planned_set_id
            ▼
Postgres (Execution - Facts)
┌─────────────────────────────────────────┐
│ sets (actual reps, load, planned_set_id)│
└─────────────────────────────────────────┘
            │
            │ computed view
            ▼
┌─────────────────────────────────────────┐
│ execution_vs_plan (deviations)          │
└─────────────────────────────────────────┘
```

## Step 1: Create planned_sets Table in Postgres

```sql
CREATE TABLE IF NOT EXISTS planned_sets (
  id UUID PRIMARY KEY,  -- Same ID as Neo4j PlannedSet node
  plan_id TEXT NOT NULL,  -- Neo4j PlannedWorkout ID
  block_seq INT NOT NULL,
  set_seq INT NOT NULL,
  
  -- Prescription
  exercise_id TEXT,
  exercise_name TEXT NOT NULL,
  prescribed_reps INT,
  prescribed_load_lbs NUMERIC,
  prescribed_rpe INT,
  intensity_zone TEXT,  -- light, moderate, heavy, max
  
  -- Context
  block_name TEXT,
  block_type TEXT,
  notes TEXT,
  
  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(plan_id, block_seq, set_seq)
);

CREATE INDEX idx_planned_sets_plan ON planned_sets(plan_id);
CREATE INDEX idx_planned_sets_exercise ON planned_sets(exercise_name);
```

## Step 2: Add FK Constraint to sets Table

```sql
-- Add FK constraint (column already exists from Phase 2)
ALTER TABLE sets 
ADD CONSTRAINT sets_planned_set_fk 
FOREIGN KEY (planned_set_id) REFERENCES planned_sets(id);
```

## Step 3: Update execution_vs_plan View

Replace the JSONB-based view with proper FK join:

```sql
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
  
  -- Planned prescription (from FK join)
  ps.prescribed_reps AS planned_reps,
  ps.prescribed_load_lbs AS planned_load,
  ps.prescribed_rpe AS planned_rpe,
  ps.intensity_zone,
  
  -- Block context
  b.name AS block_name,
  b.block_type,
  
  -- Plan linkage
  s.planned_set_id,
  ps.plan_id,
  
  -- Deviation classification
  CASE
    WHEN s.planned_set_id IS NULL THEN 'unlinked'
    WHEN s.reps IS NULL AND ps.prescribed_reps IS NOT NULL THEN 'skipped'
    WHEN s.reps IS NOT NULL AND ps.prescribed_reps IS NULL THEN 'added'
    WHEN ABS(COALESCE(s.reps, 0) - COALESCE(ps.prescribed_reps, 0)) > 2 THEN 'reps_deviation'
    WHEN ABS(COALESCE(s.load, 0) - COALESCE(ps.prescribed_load_lbs, 0)) > 10 THEN 'load_deviation'
    ELSE 'as_planned'
  END AS deviation_type,
  
  -- Deviation magnitude
  (s.reps - ps.prescribed_reps) AS reps_delta,
  (s.load - ps.prescribed_load_lbs) AS load_delta
  
FROM sets s
JOIN blocks b ON s.block_id = b.block_id
JOIN workouts w ON b.workout_id = w.workout_id
LEFT JOIN planned_sets ps ON s.planned_set_id = ps.id;

COMMENT ON VIEW execution_vs_plan IS 
'Compares executed sets against planned prescriptions via proper FK relationship.
Deviation types: as_planned, skipped, added, reps_deviation, load_deviation, unlinked.
For "why" explanations, see Neo4j relationships on the PlannedSet node.';
```

## Step 4: Update MCP - Plan Creation

In `arnold-training-mcp`, update `create_workout_plan` to also write to Postgres:

**File:** `src/arnold-training-mcp/arnold_training_mcp/server.py` (or wherever plan creation lives)

After creating PlannedSets in Neo4j, also insert into Postgres:

```python
async def create_workout_plan(self, plan_data: dict) -> dict:
    # ... existing Neo4j creation code ...
    
    # NEW: Mirror planned sets to Postgres for FK joins
    planned_sets_rows = []
    for block_idx, block in enumerate(plan_data.get('blocks', [])):
        for set_idx, set_data in enumerate(block.get('sets', [])):
            planned_sets_rows.append({
                'id': set_data['id'],  # Use same UUID as Neo4j
                'plan_id': plan_id,
                'block_seq': block_idx + 1,
                'set_seq': set_idx + 1,
                'exercise_id': set_data.get('exercise_id'),
                'exercise_name': set_data.get('exercise_name'),
                'prescribed_reps': set_data.get('prescribed_reps'),
                'prescribed_load_lbs': set_data.get('prescribed_load_lbs'),
                'prescribed_rpe': set_data.get('prescribed_rpe'),
                'intensity_zone': set_data.get('intensity_zone'),
                'block_name': block.get('name'),
                'block_type': block.get('block_type'),
                'notes': set_data.get('notes')
            })
    
    # Bulk insert to Postgres
    await self.postgres_client.insert_planned_sets(planned_sets_rows)
```

## Step 5: Update MCP - Workout Completion

In `complete_as_written`, link executed sets to planned sets:

```python
async def complete_as_written(self, plan_id: str, session_rpe: int, ...) -> dict:
    # Get planned sets for this plan
    planned_sets = await self.postgres_client.get_planned_sets_for_plan(plan_id)
    
    # Match executed sets to planned sets by (block_seq, set_seq, exercise_name)
    # Set the planned_set_id FK on each executed set
    
    # ... rest of completion logic ...
```

## Step 6: Backfill Existing Data (Optional)

If you want to link historical executed sets to plans:

```sql
-- Find sets that have planned values in JSONB but no planned_set_id
SELECT 
  s.set_id,
  s.exercise_name,
  s.extra->>'planned_reps' AS planned_reps,
  w.plan_id
FROM sets s
JOIN blocks b ON s.block_id = b.block_id
JOIN workouts w ON b.workout_id = w.workout_id
WHERE s.planned_set_id IS NULL
  AND s.extra->>'planned_reps' IS NOT NULL
  AND w.plan_id IS NOT NULL;

-- Manual backfill would require matching by exercise + sequence
-- Low priority - focus on new data going forward
```

## Step 7: "Why" Explanations in Neo4j

The Postgres view handles "what deviated" (auto-computed). 

For "why it deviated", use the journal system (arnold-journal-mcp):

```python
# When user volunteers explanation:
# "Had to drop weight because knee was bothering me"

# 1. Log journal entry
entry = await journal.log_entry(
    entry_type='feedback',
    category='training',
    raw_text="Had to drop weight because knee was bothering me",
    severity='notable'
)

# 2. Link to workout
await journal.link_to_workout(entry['id'], workout_id, relationship='EXPLAINS')

# 3. Link to injury (if relevant)
await journal.link_to_injury(entry['id'], knee_injury_id)
```

This creates Neo4j relationships:
```
(:LogEntry)-[:EXPLAINS]->(:StrengthWorkout)
(:LogEntry)-[:RELATED_TO]->(:Injury {name: "Knee"})
```

## Verification

```sql
-- planned_sets table exists and has data
SELECT COUNT(*) FROM planned_sets;

-- FK constraint works
SELECT 
  s.set_id,
  s.planned_set_id,
  ps.exercise_name AS planned_exercise,
  ps.prescribed_reps
FROM sets s
LEFT JOIN planned_sets ps ON s.planned_set_id = ps.id
LIMIT 5;

-- View works with proper joins
SELECT * FROM execution_vs_plan 
WHERE deviation_type != 'as_planned'
LIMIT 10;
```

## Summary

| Component | Before | After |
|-----------|--------|-------|
| Planned values | JSONB `extra` field | FK to `planned_sets` table |
| Deviation detection | Same | Same (auto-computed) |
| Plan traceability | None | `planned_set_id` FK |
| "Why" storage | JSONB `deviation_reason` | Neo4j via journal system |
| Cross-plan analysis | Not possible | Query `planned_sets` table |

This aligns with ADR-007/008 design: Postgres for facts, Neo4j for relationships, auto-compute what we can, capture "why" only when volunteered.
