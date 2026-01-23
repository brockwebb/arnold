# Handoff: Schema Migration Phase 7b - MCP Bug Fix

**Date:** 2026-01-22
**Status:** 🔴 BLOCKED - `log_workout` fails despite code fix
**Previous:** `HANDOFF_2026-01-22_PHASE7.md`

## Completed This Session

| Task | Status | Notes |
|------|--------|-------|
| Fix ACWR query in analytics MCP | ✅ | Changed `training_load_daily` → `training_monotony_strain` |
| Fix zero set counts in briefing | ✅ | Use `w.total_sets` property instead of relationship traversal |
| Backfill missing Neo4j workout refs | ✅ | Created `backfill_neo4j_workout_refs.py` |
| Add error logging to training MCP | ✅ | Neo4j failures now visible + logged |
| Fix `planned_block_id` column name | ❌ | Code fixed but error persists |

## Current Blocking Issue

**Error:** `column "planned_block_id" of relation "blocks" does not exist`

**What we know:**
- `postgres_client.py` line ~150 shows correct column name `planned_segment_id`
- MCP was restarted
- Error still references `planned_block_id`

**Suspected causes:**
1. Python bytecode cache (`.pyc` files)
2. MCP installed as pip package elsewhere
3. Multiple copies of the file

**Debug steps:**
```bash
# Clear Python cache
find /Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp -name "*.pyc" -delete
find /Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# Verify fix is in file
grep -n "planned_block_id\|planned_segment_id" /Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py

# Check for pip-installed version
pip show arnold-training-mcp 2>/dev/null || echo "Not installed"

# Check all copies
find /Users/brock -name "postgres_client.py" -path "*/arnold*" 2>/dev/null
```

After clearing cache, restart Claude Desktop and test.

## Test Workout Data

Once `log_workout` works, use this payload to test:

```json
{
  "date": "2026-01-22",
  "name": "KB/Sandbag Strength - Self-Programmed",
  "sport_type": "strength",
  "notes": "Plan was garbage, made my own. Good variety session. Failed 200lb sandbag shoulder at 90%.",
  "blocks": [
    {
      "name": "Warmup",
      "block_type": "warmup",
      "sets": [
        {"exercise_id": "CANONICAL:ARNOLD:BOXING", "duration_seconds": 300, "notes": "5 min boxing"},
        {"exercise_id": "CANONICAL:ARNOLD:STICK_TORSO_TWIST", "reps": 15, "notes": "Stick dislocates"},
        {"exercise_id": "EXERCISE:Band_Pull-Apart", "reps": 15},
        {"exercise_id": "CUSTOM:Banded_Sidesteps", "reps": 10, "notes": "Set 1"},
        {"exercise_id": "CUSTOM:Banded_Sidesteps", "reps": 10, "notes": "Set 2"},
        {"exercise_id": "CUSTOM:Banded_Sidesteps", "reps": 10, "notes": "Set 3"}
      ]
    },
    {
      "name": "KB Swings Warmup",
      "block_type": "main",
      "sets": [
        {"exercise_id": "CANONICAL:ARNOLD:KB_SWING_2H", "reps": 15, "load_lbs": 35}
      ]
    },
    {
      "name": "KB Swing + Goblet Squat Supersets",
      "block_type": "main",
      "sets": [
        {"exercise_id": "CANONICAL:ARNOLD:KB_SWING_2H", "reps": 10, "load_lbs": 60},
        {"exercise_id": "EXERCISE:Goblet_Squat", "reps": 10, "load_lbs": 60},
        {"exercise_id": "CANONICAL:ARNOLD:KB_SWING_2H", "reps": 10, "load_lbs": 60},
        {"exercise_id": "EXERCISE:Goblet_Squat", "reps": 10, "load_lbs": 60},
        {"exercise_id": "CANONICAL:ARNOLD:KB_SWING_2H", "reps": 8, "load_lbs": 40},
        {"exercise_id": "EXERCISE:Goblet_Squat", "reps": 8, "load_lbs": 40},
        {"exercise_id": "CANONICAL:ARNOLD:KB_SWING_2H", "reps": 8, "load_lbs": 40},
        {"exercise_id": "EXERCISE:Goblet_Squat", "reps": 8, "load_lbs": 40}
      ]
    },
    {
      "name": "Pullover + Ball Slam Supersets",
      "block_type": "main",
      "sets": [
        {"exercise_id": "EXERCISE:Straight-Arm_Dumbbell_Pullover", "reps": 10, "load_lbs": 25},
        {"exercise_id": "CANONICAL:FFDB:3118", "reps": 10, "load_lbs": 30},
        {"exercise_id": "EXERCISE:Straight-Arm_Dumbbell_Pullover", "reps": 8, "load_lbs": 35},
        {"exercise_id": "CANONICAL:FFDB:3118", "reps": 10, "load_lbs": 30},
        {"exercise_id": "EXERCISE:Straight-Arm_Dumbbell_Pullover", "reps": 8, "load_lbs": 45},
        {"exercise_id": "CANONICAL:FFDB:3118", "reps": 10, "load_lbs": 30}
      ]
    },
    {
      "name": "Sandbag Rows",
      "block_type": "main",
      "sets": [
        {"exercise_id": "EXERCISE:Bent_Over_Barbell_Row", "reps": 8, "load_lbs": 100, "notes": "Sandbag"},
        {"exercise_id": "EXERCISE:Bent_Over_Barbell_Row", "reps": 8, "load_lbs": 100, "notes": "Sandbag"},
        {"exercise_id": "EXERCISE:Bent_Over_Barbell_Row", "reps": 8, "load_lbs": 100, "notes": "Sandbag"}
      ]
    },
    {
      "name": "Sandbag Press + March Supersets",
      "block_type": "main",
      "sets": [
        {"exercise_id": "CANONICAL:ARNOLD:SANDBAG_STRICT_PRESS", "reps": 3, "load_lbs": 100},
        {"exercise_id": "CANONICAL:FFDB:2638", "reps": 30, "load_lbs": 100, "notes": "30 steps"},
        {"exercise_id": "CANONICAL:ARNOLD:SANDBAG_STRICT_PRESS", "reps": 3, "load_lbs": 100},
        {"exercise_id": "CANONICAL:FFDB:2638", "reps": 30, "load_lbs": 100, "notes": "30 steps"},
        {"exercise_id": "CANONICAL:ARNOLD:SANDBAG_STRICT_PRESS", "reps": 3, "load_lbs": 100},
        {"exercise_id": "CANONICAL:FFDB:2638", "reps": 30, "load_lbs": 100, "notes": "30 steps"}
      ]
    },
    {
      "name": "Heavy Attempt",
      "block_type": "main",
      "sets": [
        {"exercise_id": "EXERCISE:SANDBAG_SHOULDERING", "reps": 0, "load_lbs": 200, "rpe": 10, "notes": "Failed at 90% - lost it at top"}
      ]
    },
    {
      "name": "Core Finisher",
      "block_type": "finisher",
      "sets": [
        {"exercise_id": "CANONICAL:FFDB:1381", "reps": 10, "notes": "Knee to shoulder crunches"},
        {"exercise_id": "EXERCISE:Plank", "duration_seconds": 69, "notes": "Straight plank hold"}
      ]
    }
  ]
}
```

## Files Modified This Session

| File | Change |
|------|--------|
| `/src/arnold-analytics-mcp/arnold_analytics/server.py` | ACWR query fix (lines 347, 546) |
| `/src/arnold-memory-mcp/arnold_memory_mcp/neo4j_client.py` | Use `w.total_sets` property |
| `/src/arnold-training-mcp/arnold_training_mcp/server.py` | Added Neo4j error logging |
| `/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py` | `planned_block_id` → `planned_segment_id` |
| `/scripts/backfill_neo4j_workout_refs.py` | NEW - sync missing refs |

## Other Issues Noted (Not Blocking)

1. **Stick dislocate** resolved to "Stick Torso Twist" - wrong exercise. Need to add proper shoulder dislocate exercise.

2. **28d Volume shows 0** in briefing despite workouts existing - analytics query still broken somewhere.

3. **Stale coaching flags** - Observations mention "legacy schema" issues that were supposedly fixed. Need cleanup.

4. **Ultrahuman sync** - No HRV/sleep data flowing.

## Quick Test After Fix

```bash
# From Claude Desktop, call:
arnold-training:log_workout with the JSON above

# Verify in Postgres:
psql -c "SELECT workout_id, start_time::date, notes FROM workouts WHERE start_time::date = '2026-01-22';" arnold_analytics
```
