# Handoff: Schema Migration Phase 7c - Production Readiness

**Date:** 2026-01-22
**Status:** 🟡 Workout logging fixed, briefing queries need audit
**Previous:** `HANDOFF_2026-01-22_PHASE7b.md`

## Session Summary

### ✅ Completed

| Task | Notes |
|------|-------|
| Fix ACWR query in analytics MCP | `training_load_daily` → `training_monotony_strain` |
| Fix zero set counts in briefing | Use `w.total_sets` property |
| Backfill missing Neo4j workout refs | Created `backfill_neo4j_workout_refs.py` |
| Add error logging to training MCP | Neo4j failures now visible |
| Fix `planned_block_id` → `planned_segment_id` | Column name mismatch |
| **Fix log_workout to support blocks** | New `log_workout_session()` per ADR-007 |
| **Fix complete_as_written** | Preserves block structure |
| **Fix complete_with_deviations** | Preserves block structure |

### ✅ Verified Working

- `log_workout` with blocks structure → 8 blocks, 33 sets logged correctly
- `get_training_load()` → Returns 20 workouts, 244 sets, ACWR 0.89
- Recent workouts in briefing → Shows today's workout with set count
- Block structure preserved per ADR-007 (warmup/main/finisher separate)

### ❌ Still Broken

| Issue | Root Cause | CC Task |
|-------|------------|---------|
| Briefing "28d Volume: 0" | Parallel query path in memory MCP | `CC_TASK_AUDIT_BRIEFING_SOURCES.md` |
| HRV/Sleep: No data | Sync not running or wrong tables | Same task |
| Stale coaching observations | No lifecycle/expiry mechanism | Same task |

## CC Tasks Queued

1. **`CC_TASK_AUDIT_BRIEFING_SOURCES.md`** - Fix briefing to use single source of truth
   - Trace 28d volume query, make it match analytics
   - Trace HRV/Sleep queries
   - Add observation lifecycle (resolved_at or expiry)
   - Set up sync automation (cron/launchd)

## Files Modified This Session

| File | Change |
|------|--------|
| `/src/arnold-analytics-mcp/arnold_analytics/server.py` | ACWR query fix |
| `/src/arnold-memory-mcp/arnold_memory_mcp/neo4j_client.py` | Use `w.total_sets` |
| `/src/arnold-training-mcp/arnold_training_mcp/server.py` | All three handlers updated, Neo4j error logging |
| `/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py` | New `log_workout_session()`, column fix |
| `/scripts/backfill_neo4j_workout_refs.py` | NEW |
| `/scripts/sync_exercise_patterns.py` | NEW (from Phase 7) |

## Test Workout (Jan 22, 2026)

Successfully logged with proper block structure:

```
workout_id: 348c1dca-fe31-45b6-9532-adc5b2148fc4

seq | block_type | block_name                        | sets
----|------------|-----------------------------------|-----
  1 | warmup     | Warmup                            |    6
  2 | main       | KB Swings Warmup                  |    1
  3 | main       | KB Swing + Goblet Squat Supersets |    8
  4 | main       | Pullover + Ball Slam Supersets    |    6
  5 | main       | Sandbag Rows                      |    3
  6 | main       | Sandbag Press + March Supersets   |    6
  7 | main       | Heavy Attempt                     |    1
  8 | finisher   | Core Finisher                     |    2
```

## Architecture Reference

**ADR-007 Schema:**
```
workouts (session: sport_type, rpe, notes)
  └── blocks (container: block_type, modality override)
        └── sets (atomic: exercise, reps, load, etc.)
```

**Key distinction:**
- `block_type` = training phase (warmup, main, accessory, finisher)
- `modality` = sport (strength, running, cycling)

These are orthogonal. A warmup block can have strength modality.

## Quick Verification Commands

```sql
-- Check today's workout structure
SELECT b.seq, b.block_type, b.extra->>'name', COUNT(s.set_id)
FROM workouts w
JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
WHERE w.start_time::date = '2026-01-22'
GROUP BY b.block_id ORDER BY b.seq;

-- Check analytics 28d summary
SELECT COUNT(DISTINCT workout_date) as workouts, 
       SUM(daily_sets) as sets,
       SUM(daily_volume) as volume
FROM training_monotony_strain
WHERE workout_date >= CURRENT_DATE - 28;
```

## Next Session

1. Have CC run `CC_TASK_AUDIT_BRIEFING_SOURCES.md`
2. Verify briefing matches analytics output
3. Set up sync automation
4. Clean up stale observations
