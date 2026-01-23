# CC Task: Fix Workout Logging to Match ADR-007 Schema

**Priority:** HIGH - Current implementation violates schema design
**Reference:** `/docs/adr/007-simplified-workout-schema.md`
**Files:** 
- `/src/arnold-training-mcp/arnold_training_mcp/server.py`
- `/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py`

## ADR-007 Schema (Source of Truth)

```
workouts (session)
  └── blocks (container - training phase)
        └── sets (atomic unit - all modalities)
```

**Key principle from ADR-007:**
> Block type ≠ modality — These are orthogonal:
> - `block_type` = training phase (warmup, main, accessory)
> - `modality` = sport (strength, running, cycling)

## Current Problems

1. **Function naming:** `log_strength_session()` implies strength-only, but schema is modality-agnostic

2. **Single block creation:** All callers create ONE block regardless of input structure:
   - `complete_as_written` - flattens plan's blocks to single block
   - `complete_with_deviations` - same
   - `log_workout` - same
   
3. **Block structure lost:** Warmup/main/accessory/finisher info discarded

4. **Both paths broken:**
   - Plan completion: Neo4j plan HAS blocks → flattened to one
   - Ad-hoc logging: Input CAN have blocks → ignored, only reads `exercises`

## Required Changes

### 1. Rename in postgres_client.py

| Current | New |
|---------|-----|
| `log_strength_session()` | `log_workout_session()` |
| `log_endurance_session()` | MERGE into `log_workout_session()` |

Single function handles all modalities via nullable columns per ADR-007:
> "One sets table — Nullable columns for different modalities. NULL storage cost is negligible; join complexity is not."

### 2. New `log_workout_session()` Signature

```python
def log_workout_session(
    self,
    session_date: str,
    name: str,
    blocks: List[Dict[str, Any]],  # REQUIRED - always block structure
    sport_type: str = 'strength',   # workout-level modality
    duration_minutes: int = None,
    notes: str = None,
    session_rpe: int = None,
    source: str = 'logged',
    plan_id: str = None,
    user_id: str = None
) -> Dict[str, Any]:
```

### 3. Block Structure (Input)

```python
blocks = [
    {
        "name": "Warmup",
        "block_type": "warmup",      # training phase
        "modality": None,            # inherits from workout.sport_type
        "sets": [
            {"exercise_id": "...", "reps": 15},
            {"exercise_id": "...", "duration_seconds": 300}
        ]
    },
    {
        "name": "Main Work", 
        "block_type": "main",
        "sets": [...]
    },
    {
        "name": "Conditioning Finisher",
        "block_type": "conditioning",
        "modality": "rowing",        # override for this block only
        "sets": [
            {"exercise_id": "...", "distance": 500, "distance_unit": "m"}
        ]
    }
]
```

### 4. Database Writes

**Workout:**
```sql
INSERT INTO workouts (
    user_id, start_time, duration_seconds, rpe, notes,
    sport_type, source, source_fidelity
) VALUES (...) RETURNING workout_id
```

**Per block:**
```sql
INSERT INTO blocks (
    workout_id, seq, block_type, modality, extra
) VALUES (
    %(workout_id)s, 
    %(seq)s,           -- 1, 2, 3...
    %(block_type)s,    -- 'warmup', 'main', 'finisher'
    %(modality)s,      -- NULL = inherit from workout, or override
    %(extra)s          -- {"name": "Block Name"}
) RETURNING block_id
```

**Sets (unified per ADR-007):**
```sql
INSERT INTO sets (
    block_id, seq, exercise_id, exercise_name,
    -- Strength columns (nullable)
    reps, load, load_unit, rpe,
    -- Endurance columns (nullable)  
    distance, distance_unit, duration_s, pace, hr_avg, hr_zone,
    -- Common
    notes, extra, planned_set_id
) VALUES (...)
```

### 5. Update All Callers in server.py

**`log_workout` handler (~line 1430):**
- Accept `blocks` array (preferred) OR `exercises` array (legacy)
- If `exercises` provided, wrap in single "Main" block for backward compat
- Call `postgres_client.log_workout_session()`

**`complete_as_written` handler (~line 1090):**
- Plan already has blocks structure from Neo4j
- Pass blocks directly, don't flatten
- Remove the flattening loop

**`complete_with_deviations` handler (~line 1180):**
- Same - preserve block structure from plan

### 6. Backward Compatibility

If caller provides `exercises` array instead of `blocks`:
```python
if workout_data.get('exercises') and not workout_data.get('blocks'):
    # Legacy format - wrap in single block
    blocks = [{
        'name': 'Main',
        'block_type': 'main',
        'sets': []
    }]
    for exercise in workout_data['exercises']:
        for s in exercise.get('sets', []):
            s['exercise_id'] = exercise.get('exercise_id')
            s['exercise_name'] = exercise.get('name') or exercise.get('exercise_name')
            blocks[0]['sets'].append(s)
```

## Implementation Order

1. Add `log_workout_session()` to postgres_client.py (new function)
2. Update `log_workout` handler to use new function with blocks
3. Update `complete_as_written` to preserve block structure
4. Update `complete_with_deviations` to preserve block structure  
5. Deprecate/remove `log_strength_session()` and `log_endurance_session()`
6. Test all three paths

## Verification

```sql
-- After logging a workout with warmup/main/finisher blocks:
SELECT 
    b.seq,
    b.block_type,
    b.modality,
    b.extra->>'name' as block_name,
    COUNT(s.set_id) as sets
FROM workouts w
JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
WHERE w.start_time::date = '2026-01-22'
GROUP BY b.block_id
ORDER BY b.seq;
```

Expected:
```
seq | block_type | modality | block_name | sets
----+------------+----------+------------+------
  1 | warmup     | NULL     | Warmup     |    6
  2 | main       | NULL     | Main Work  |   20
  3 | finisher   | NULL     | Core       |    2
```

## Cleanup Bad Data

After fix verified, delete today's incorrectly structured workout:

```sql
DELETE FROM sets WHERE block_id IN (
    SELECT block_id FROM blocks WHERE workout_id = '0e5db880-6a86-4b72-9f59-fbaca9305973'
);
DELETE FROM blocks WHERE workout_id = '0e5db880-6a86-4b72-9f59-fbaca9305973';
DELETE FROM workouts WHERE workout_id = '0e5db880-6a86-4b72-9f59-fbaca9305973';
```

Neo4j cleanup:
```cypher
MATCH (w:StrengthWorkout {postgres_id: '0e5db880-6a86-4b72-9f59-fbaca9305973'}) DETACH DELETE w
```

Then re-log using the blocks payload from `/migrations/HANDOFF_2026-01-22_PHASE7b.md`.

## Test Payloads

See `/migrations/HANDOFF_2026-01-22_PHASE7b.md` for the complete workout JSON with proper blocks structure.
