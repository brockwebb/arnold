# Phase 4 Verification: MCP Updates

**Priority:** Execute now  
**Purpose:** Verify all MCPs are using new table/column names and functioning correctly

## Step 1: Find All Remaining Old References

```bash
# Search for ANY remaining references to old table/column names
grep -rn "workouts_v2\|v2_strength\|segments\|segment_id" --include="*.py" src/

# Also check for the old view name
grep -rn "workout_summaries_v2" --include="*.py" src/
```

**Expected:** Zero matches. If any found, update those files.

## Step 2: Verify Table/Column Name Updates

For each MCP, verify these substitutions were made:

| Old | New |
|-----|-----|
| `workouts_v2` | `workouts` |
| `segments` | `blocks` |
| `v2_strength_sets` | `sets` |
| `segment_id` | `block_id` |
| `sport_type` (on blocks) | `modality` |
| `workout_summaries_v2` | `workout_summaries` |

### arnold-training-mcp

**File:** `src/arnold-training-mcp/arnold_training_mcp/postgres_client.py`

Check these functions:
- `log_workout()` — Should INSERT into `workouts`, `blocks`, `sets`
- `get_workout_by_date()` — Should SELECT from `workouts`, `blocks`, `sets`
- `get_recent_workouts()` — Should SELECT from `workouts`
- `complete_as_written()` — Should use new table names

```bash
grep -n "INSERT INTO\|FROM\|JOIN" src/arnold-training-mcp/arnold_training_mcp/postgres_client.py | head -50
```

### arnold-analytics-mcp

**File:** `src/arnold-analytics-mcp/arnold_analytics_mcp/postgres_client.py` (or similar)

Check these functions:
- `get_exercise_history()` — Should query `sets` table
- `get_training_load()` — Should query views or `workouts` table

```bash
grep -n "INSERT INTO\|FROM\|JOIN" src/arnold-analytics-mcp/arnold_analytics_mcp/*.py | head -50
```

### arnold-memory-mcp

**File:** `src/arnold-memory-mcp/arnold_memory_mcp/postgres_client.py` (or similar)

Check:
- `load_briefing()` — Should query `workouts`, `blocks`, `sets` or views

```bash
grep -n "INSERT INTO\|FROM\|JOIN" src/arnold-memory-mcp/arnold_memory_mcp/*.py | head -50
```

## Step 3: Functional Tests

After verifying code, test actual functionality:

### Test 1: Log a Simple Workout

```python
# Via MCP tool call or direct test
workout_data = {
    "date": "2026-01-21",
    "sport_type": "strength",
    "duration_minutes": 45,
    "session_rpe": 7,
    "blocks": [{
        "name": "Test Block",
        "block_type": "main",
        "sets": [{
            "exercise_name": "Test Exercise",
            "reps": 10,
            "load": 100
        }]
    }]
}
# Call log_workout with this data
```

**Verify:**
```sql
SELECT * FROM workouts WHERE start_time::date = '2026-01-21';
SELECT * FROM blocks WHERE workout_id = '<workout_id from above>';
SELECT * FROM sets WHERE block_id = '<block_id from above>';
```

### Test 2: Query Recent Workouts

```python
# Call get_recent_workouts(days=7)
```

**Expected:** Returns workout data without errors

### Test 3: Load Briefing

```python
# Call load_briefing()
```

**Expected:** Returns briefing with recent workout data

### Test 4: Exercise History

```python
# Call get_exercise_history(exercise="Trap Bar Deadlift", days=30)
```

**Expected:** Returns history without errors

## Step 4: Check for Stale Imports/Constants

Sometimes old names are in constants or config:

```bash
# Check for any constants or config with old names
grep -rn "WORKOUTS_V2\|SEGMENTS\|V2_STRENGTH" --include="*.py" src/
grep -rn "workouts_v2\|segments\|v2_strength" --include="*.yaml" --include="*.json" src/ config/
```

## Step 5: Restart MCPs

After any code changes:

```bash
# Restart all MCPs (method depends on your setup)
# If using Claude Desktop, restart the app
# If running manually, kill and restart each MCP process
```

## Verification Checklist

- [ ] `grep` returns zero matches for old table names in Python files
- [ ] `grep` returns zero matches for old table names in config files
- [ ] `log_workout()` successfully creates workout with blocks and sets
- [ ] `get_recent_workouts()` returns data
- [ ] `load_briefing()` returns data with recent workouts
- [ ] `get_exercise_history()` returns data
- [ ] All MCPs restarted after any code changes

## If Old References Found

For each file with old references:

1. Open the file
2. Find/replace:
   - `workouts_v2` → `workouts`
   - `segments` → `blocks`
   - `v2_strength_sets` → `sets`
   - `segment_id` → `block_id`
   - `sport_type` → `modality` (only in block context, not workout)
3. Save and verify syntax
4. Restart MCP

## Report Format

After completing verification, report:

```
MCP Verification Results:
- arnold-training-mcp: [PASS/FAIL] - [notes]
- arnold-analytics-mcp: [PASS/FAIL] - [notes]  
- arnold-memory-mcp: [PASS/FAIL] - [notes]
- arnold-journal-mcp: [PASS/FAIL] - [notes]
- arnold-profile-mcp: [PASS/FAIL] - [notes]

Old references found: [count]
Files updated: [list]
Functional tests: [PASS/FAIL]
```
