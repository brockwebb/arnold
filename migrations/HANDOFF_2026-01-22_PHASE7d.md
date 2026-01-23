# Handoff: Schema Migration Phase 7d - Memory MCP Debug

**Date:** 2026-01-22
**Status:** 🟡 Workout logging working, briefing Postgres query failing silently
**Transcript:** `/mnt/transcripts/2026-01-23-03-06-30-schema-migration-phase7-mcp-fixes.txt`

## Session Summary

Continued from Phase 7c. Verified `log_workout` with blocks works (tested with 8-block, 33-set workout). Diagnosed why briefing still shows "28d Volume: 0 workouts, 0 sets".

## Current Status

### ✅ Working

| Component | Evidence |
|-----------|----------|
| `log_workout` with blocks | 348c1dca: 8 blocks, 33 sets, structure preserved |
| `get_training_load()` (analytics MCP) | Returns 20 workouts, 244 sets correctly |
| `workout_summaries` view | Has correct data |
| Recent workouts in briefing | Shows Jan 22 workout with 33 sets |
| Neo4j refs synced | 7 missing refs backfilled |

### ❌ Broken

| Component | Symptom | Root Cause |
|-----------|---------|------------|
| 28d Volume in briefing | Shows "0 workouts, 0 sets" | Silent exception in `get_training_load_summary()` |
| HRV/Sleep | "No data" | Ultrahuman sync missing metrics |
| Stale coaching flags | Shows fixed bugs | Need to resolve observations |

## Key Finding

The `workout_summaries` view has correct data:
```sql
SELECT workout_date, set_count FROM workout_summaries LIMIT 3;
-- Jan 22: 33, Jan 20: 12, Jan 19: 22
```

But `postgres_client.get_training_load_summary()` returns 0. Exception is being caught silently:
```python
except Exception as e:
    logger.error(f"Error getting training load: {e}")
```

## CC Tasks Queued

1. **`CC_TASK_DEBUG_MEMORY_POSTGRES.md`** - Find and fix the silent failure
   - Check `/tmp/arnold-memory-mcp.log`
   - Add debug logging
   - Test connection
   - Verify view visibility

2. **`CC_TASK_AUDIT_BRIEFING_SOURCES.md`** - Partially done
   - ✅ Config updated
   - ✅ resolve_observation tool added
   - ❌ Connection still failing
   - ❌ Sleep metrics still missing from Ultrahuman sync

## Files Modified This Session

From transcript context:
- `/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py` - `log_workout_session()`
- `/src/arnold-training-mcp/arnold_training_mcp/server.py` - All handlers use new method
- `/src/arnold-memory-mcp/arnold_memory_mcp/neo4j_client.py` - resolve_observation
- `/src/arnold-memory-mcp/arnold_memory_mcp/server.py` - resolve_observation tool
- `/Library/Application Support/Claude/claude_desktop_config.json` - DATABASE_URI added

## Test Workout (Verified)

```sql
SELECT b.seq, b.block_type, b.extra->>'name', COUNT(s.set_id)
FROM workouts w
JOIN blocks b ON w.workout_id = b.workout_id
LEFT JOIN sets s ON b.block_id = s.block_id
WHERE w.workout_id = '348c1dca-fe31-45b6-9532-adc5b2148fc4'
GROUP BY b.block_id ORDER BY b.seq;

-- Returns 8 blocks: warmup(6), main(1,8,6,3,6,1), finisher(2)
```

## Quick Debug Command

```bash
tail -100 /tmp/arnold-memory-mcp.log | grep -i "training\|error\|postgres"
```

## Next Steps

1. CC debugs Postgres connection in memory MCP
2. Fix silent failure
3. Restart Claude Desktop
4. Verify briefing shows correct 28d volume
5. Clean up stale observations using new `resolve_observation` tool
