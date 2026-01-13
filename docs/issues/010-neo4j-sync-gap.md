# Issue 010: Neo4j Sync Gap - Silent Failures

**Created:** 2026-01-13  
**Status:** Open  
**Priority:** Medium

## Problem

Workouts logged to Postgres sometimes don't get synced to Neo4j. The Jan 10 workout (`strength_sessions.id=175`) has `neo4j_id=NULL` despite being logged through the normal flow.

```sql
-- Evidence
SELECT id, session_date, name, neo4j_id FROM strength_sessions 
WHERE session_date >= '2026-01-09' ORDER BY session_date;

-- Results:
-- id=170, 2026-01-09, neo4j_id='a0b14a6c-...'  ✓ synced
-- id=175, 2026-01-10, neo4j_id=NULL            ✗ NOT synced
```

## Root Cause (Suspected)

In `complete_as_written` and `complete_with_deviations`, the Neo4j sync happens after Postgres write:

```python
# 4. Create Neo4j reference node
neo4j_ref = neo4j_client.create_strength_workout_ref(...)

# 5. Update Postgres with Neo4j ID
if neo4j_ref:
    postgres_client.update_session_neo4j_id(result['session_id'], neo4j_ref.get('id'))
```

If `create_strength_workout_ref()` returns `None` (fails silently), the sync never happens and there's no error surfaced to the user.

## Investigation Needed

1. Check logs from Jan 10 for errors: `/tmp/arnold-training-mcp.log`
2. Review `create_strength_workout_ref()` - does it catch and swallow exceptions?
3. Determine if this was a one-time failure or systematic issue

## Fixes Required

### 1. Add Error Handling
```python
neo4j_ref = neo4j_client.create_strength_workout_ref(...)
if not neo4j_ref:
    logger.error(f"Failed to create Neo4j ref for session {result['session_id']}")
    # Don't fail the whole operation, but surface warning to user
```

### 2. Add Retry/Recovery
- Periodic job to find Postgres sessions with `neo4j_id=NULL`
- Attempt to create missing Neo4j references
- Or: sync step in `run_sync` pipeline

### 3. Consider Transactional Approach
- Write to both databases in same logical transaction
- If Neo4j fails, rollback Postgres? Or queue for retry?

## Immediate Fix for Jan 10

Manual sync already done in conversation:
```cypher
// Created StrengthWorkout node and linked to Person
// Updated strength_sessions.neo4j_id
```

## Design Question

Should Neo4j sync failure block the workout log? 

**Arguments for blocking:**
- Data integrity - both databases should be consistent
- Graph queries will miss workouts

**Arguments against blocking:**
- Postgres is source of truth for facts (ADR-002)
- Neo4j is for relationships, not critical path
- Better UX to log workout even if graph sync fails

**Recommendation:** Don't block, but surface warning and queue for retry.

## Related

- ADR-002: Plans in Neo4j, Facts in Postgres
- Issue 009: Unified workout logging
