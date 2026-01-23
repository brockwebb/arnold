# Phase 7: MCP Verification and Updates

**Priority:** Execute after Phase 6c  
**Goal:** Ensure all MCPs use new table/column names and function correctly

## Step 1: Find All Old References

Run these greps to identify any remaining old table/column references:

```bash
# Old table names
grep -rn "workouts_v2\|v2_strength_sets" --include="*.py" src/

# Old table name: segments
grep -rn "segments" --include="*.py" src/ | grep -v "# segment" | grep -v "line segment"

# Old column name
grep -rn "segment_id" --include="*.py" src/

# Old column name (in blocks context)
grep -rn "sport_type" --include="*.py" src/ | grep -v "workout"
```

Document all files that need updates.

## Step 2: MCP-Specific Checks

### arnold-training-mcp

**Location:** `src/arnold-training-mcp/`

Check these files:
- `arnold_training_mcp/server.py`
- `arnold_training_mcp/postgres_client.py`
- `arnold_training_mcp/neo4j_client.py`

**Functions to verify:**

| Function | Check For |
|----------|-----------|
| `log_workout` | Uses `workouts`, `blocks`, `sets` (not v2 names) |
| `complete_as_written` | Uses new table names, writes `planned_set_id` |
| `get_workout_by_date` | Queries `workouts`, `blocks`, `sets` |
| `get_recent_workouts` | Queries new table names |
| `create_workout_plan` | Writes to `planned_sets` table in Postgres |

**Test after updates:**
```bash
# Restart MCP
# Then test via Claude Desktop or direct call:
# - Log a simple workout
# - Retrieve today's workout
# - Check planned_sets table has data after plan creation
```

### arnold-analytics-mcp

**Location:** `src/arnold-analytics-mcp/`

Check these files:
- `arnold_analytics_mcp/server.py`
- `arnold_analytics_mcp/postgres_client.py`

**Functions to verify:**

| Function | Check For |
|----------|-----------|
| `get_exercise_history` | Queries `sets` (not `v2_strength_sets`) |
| `get_training_load` | Uses updated views or new table names |
| `get_readiness_snapshot` | Uses updated views |
| `check_red_flags` | Uses updated views |

### arnold-memory-mcp

**Location:** `src/arnold-memory-mcp/`

Check these files:
- `arnold_memory_mcp/server.py`
- `arnold_memory_mcp/postgres_client.py`

**Functions to verify:**

| Function | Check For |
|----------|-----------|
| `load_briefing` | Queries new table names for recent workouts |

### arnold-journal-mcp

**Location:** `src/arnold-journal-mcp/`

**Functions to verify:**

| Function | Check For |
|----------|-----------|
| `link_to_workout` | Uses correct workout table reference |
| `find_workouts_for_date` | Queries `workouts` table |

## Step 3: Update Pattern

For each file with old references, apply these replacements:

| Old | New |
|-----|-----|
| `workouts_v2` | `workouts` |
| `segments` | `blocks` |
| `v2_strength_sets` | `sets` |
| `segment_id` | `block_id` |
| `seg.sport_type` or `segments.sport_type` | `b.modality` or `blocks.modality` |

**Important:** Don't blindly replace. Check context:
- `sport_type` on `workouts` table stays as `sport_type`
- `sport_type` on `blocks` table becomes `modality`

## Step 4: Verify planned_sets Integration

The `planned_sets` table was created in Phase 6b. Verify MCPs use it:

```sql
-- Check table exists with correct structure
\d planned_sets

-- After creating a plan via MCP, verify data appears
SELECT COUNT(*) FROM planned_sets;
```

**If `create_workout_plan` doesn't write to `planned_sets`:**

Update the function to mirror Neo4j PlannedSets to Postgres. See `/migrations/PHASE_6B_DEVIATION_FIX.md` for the pattern.

## Step 5: Verify Neo4j Client

Check for the `postgres_id` kwarg error mentioned in Phase 8:

```bash
grep -rn "postgres_id\|create_strength_workout_ref" --include="*.py" src/
```

Fix any signature mismatches between caller and function definition.

## Step 6: End-to-End Test

After all updates, restart MCPs and test:

1. **Create a plan:**
   ```
   "Create a workout plan for tomorrow: 3x5 trap bar deadlift at 275, 3x8 Bulgarian split squats"
   ```
   Verify: `planned_sets` table has new rows

2. **Log a workout:**
   ```
   "I just did my workout as planned"
   ```
   Verify: `workouts`, `blocks`, `sets` have new rows

3. **Query workout:**
   ```
   "What did I do today?"
   ```
   Verify: Returns the logged workout

4. **Check analytics:**
   ```
   "What's my training load this week?"
   ```
   Verify: No SQL errors, returns data

5. **Check briefing:**
   ```
   "Load my coaching briefing"
   ```
   Verify: Recent workouts appear, no errors

## Verification Checklist

- [ ] No grep hits for old table names in src/
- [ ] No grep hits for `segment_id` in src/
- [ ] `arnold-training-mcp` uses new names
- [ ] `arnold-analytics-mcp` uses new names
- [ ] `arnold-memory-mcp` uses new names
- [ ] `arnold-journal-mcp` uses new names
- [ ] `create_workout_plan` writes to `planned_sets`
- [ ] `complete_as_written` sets `planned_set_id` FK
- [ ] Neo4j `postgres_id` kwarg error fixed
- [ ] End-to-end test passes (plan → log → query → analytics)

## Files Changed Log

Document each file updated:

| File | Changes Made |
|------|--------------|
| | |
| | |
| | |

After completing this phase, the migration is functionally complete.
