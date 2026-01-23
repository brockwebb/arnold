# Phase 7: URGENT MCP Fixes

**Status:** Migration broke MCPs. Fix now.

## Issue 1: Analytics MCP - Wrong Column Names

The analytics MCP queries use old column names that don't exist in the new schema.

**Find and fix these:**

```bash
# Find files with old column names
grep -rn "duration_min\|workout_date\|patterns" --include="*.py" src/arnold-analytics-mcp/
grep -rn "duration_min\|workout_date\|patterns" --include="*.py" src/arnold-memory-mcp/
```

**Column mappings:**

| Old | New | Table |
|-----|-----|-------|
| `duration_min` | `duration_minutes` | workouts |
| `workout_date` | `start_time::date` | workouts |
| `patterns` | Check if this exists - may be view/computed | varies |

**Common fix patterns:**

```python
# Old
"SELECT duration_min FROM workouts"
# New
"SELECT duration_minutes FROM workouts"

# Old  
"SELECT workout_date FROM workouts"
# New
"SELECT start_time::date AS workout_date FROM workouts"
```

## Issue 2: Neo4j Client - postgres_id Argument Mismatch

The workout logging fails because the Neo4j client function signature doesn't match callers.

```bash
# Find the mismatch
grep -rn "postgres_id" --include="*.py" src/arnold-training-mcp/
grep -rn "create_strength_workout_ref\|create_workout_reference" --include="*.py" src/arnold-training-mcp/
```

**Likely fix:** Either:
- Add `postgres_id` parameter to function definition
- Or remove it from the caller
- Or rename to match (e.g., `workout_id` vs `postgres_id`)

Check the function definition vs call site and align them.

## Issue 3: Jan 14 Data - exercise_name = 'Unknown'

24 sets have `exercise_name = 'Unknown'`. This is a data quality issue.

**First, identify the workout:**

```sql
SELECT w.workout_id, w.start_time, s.set_id, s.exercise_name
FROM workouts w
JOIN blocks b ON w.workout_id = b.workout_id
JOIN sets s ON b.block_id = s.block_id
WHERE s.exercise_name = 'Unknown'
ORDER BY w.start_time;
```

**Option A: Delete and re-log**
If you can reconstruct what the workout was, delete and re-log.

**Option B: Manual backfill**
If you know what exercises those sets were, update directly:

```sql
-- Example (adjust based on actual data)
UPDATE sets 
SET exercise_name = 'Actual Exercise Name'
WHERE set_id IN (SELECT set_id FROM ... WHERE exercise_name = 'Unknown' AND ...);
```

**Option C: Mark as unknown and move on**
Leave as-is, acknowledge data gap.

## Verification After Fixes

```bash
# 1. No old column references
grep -rn "duration_min\|workout_date" --include="*.py" src/
# Should return nothing

# 2. Restart MCPs
# (restart method depends on setup)

# 3. Test load_briefing
# Should not throw schema errors

# 4. Test complete_as_written  
# Should not throw postgres_id error

# 5. Check analytics tools
# get_readiness_snapshot, get_training_load should work
```

## Report Format

After fixes, report:

```
Issue 1 (Column names): [FIXED/PARTIAL] - [files changed]
Issue 2 (postgres_id): [FIXED/PARTIAL] - [changes made]
Issue 3 (Unknown exercises): [FIXED/DEFERRED] - [action taken]

All tools tested:
- load_briefing: [PASS/FAIL]
- get_readiness_snapshot: [PASS/FAIL]
- get_training_load: [PASS/FAIL]
- complete_as_written: [PASS/FAIL]
```
