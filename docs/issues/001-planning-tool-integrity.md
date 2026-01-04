# Issue #001: Planning Tool Data Integrity

**Filed**: 2026-01-03  
**Status**: ✅ Resolved  
**Priority**: High  
**Component**: arnold-training-mcp

## Problem Statement

The `create_workout_plan` tool has multiple data integrity issues that resulted in an unqueryable workout plan. Manual intervention was required to fix data before the planned workout could be executed.

## Bugs Identified

### 1. `plan_id` Never Persisted

**Symptom**: All `PlannedWorkout` nodes have `plan_id: null`

**Root Cause**: The `create_workout_plan` tool either doesn't generate a `plan_id` or doesn't include it in the Cypher `CREATE` statement.

**Impact**: 
- Plans cannot be reliably referenced by ID
- Completion tools that take `plan_id` as input will fail
- No stable identifier for plan lifecycle tracking

**Fix Required**:
```python
# In create_workout_plan handler
plan_id = f"PLAN:{uuid.uuid4()}"
# Include in CREATE statement
```

### 2. `get_plan_for_date` Returns Synthetic ID

**Symptom**: Tool returned `PLAN:d805010d-a9df-49c6-9392-1daba60e2f5a` when database contained `PLAN:76997914-556f-441d-951f-bbf90afca69d`

**Root Cause**: The tool's Cypher query constructs a fake ID (likely from `elementId()` or similar) instead of reading `p.plan_id`

**Impact**: Returned ID doesn't match actual database record; using it with other tools will fail

**Fix Required**: Change query to return actual `p.plan_id` property

### 3. Date Stored in Wrong Year

**Symptom**: Plan created for "January 3" was stored as `2025-01-03` instead of `2026-01-03`

**Root Cause**: Either:
- User input ambiguity ("January 3" without year)
- Claude reasoning error  
- No validation that date is in the future

**Impact**: Plan not queryable by intended date

**Fix Required**: 
- Validate date is not in the past (warning if >7 days ago)
- If year not specified and month/day has passed, assume next year
- Or require explicit year in all date inputs

### 4. Orphan Plans Not Cleaned Up

**Symptom**: Two draft plans left behind from failed/abandoned creation attempts

**Root Cause**: No cleanup on failed creation, no mechanism to prune old drafts

**Impact**: Data pollution, confusion when querying plans

**Fix Required**:
- Transaction rollback on creation failure
- Consider auto-cleanup of drafts older than N days
- Or explicit "discard draft" command

## Data Fixed (2026-01-03)

```cypher
// Fixed date and added plan_id
MATCH (p:PlannedWorkout)
WHERE p.goal = 'The Fifty - Birthday Strength Circuit' AND p.status = 'confirmed'
SET p.date = date('2026-01-03'),
    p.plan_id = 'PLAN:' + randomUUID()

// Deleted orphan drafts  
MATCH (p:PlannedWorkout)
WHERE p.goal CONTAINS 'The Fifty' AND p.status = 'draft'
DETACH DELETE p
// Removed 2 orphans
```

## Files to Modify

| File | Changes Needed |
|------|----------------|
| `src/arnold-training-mcp/arnold_training_mcp/server.py` | `create_workout_plan`: generate and persist `plan_id`, add date validation |
| `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` | Fix queries to return actual `plan_id` property |

## Acceptance Criteria

- [x] New plans have non-null `plan_id` with format `PLAN:{uuid}`
- [x] `get_plan_for_date` returns the actual `plan_id` from database
- [x] Date validation warns if date appears to be in wrong year
- [x] Failed plan creation doesn't leave orphan nodes
- [x] All plan lifecycle tools (`complete_as_written`, `skip_workout`, etc.) work with persisted `plan_id`

## Resolution (2026-01-03)

Fixed in `neo4j_client.py`:

1. **Property naming**: Changed from `id` to `plan_id` in `create_planned_workout`
2. **Date validation**: Added checks for wrong year and distant past dates
3. **Query updates**: All queries now use `COALESCE(pw.plan_id, pw.id)` for backward compatibility
4. **Match clauses**: Changed from `{id: $plan_id}` to `WHERE pw.plan_id = $plan_id OR pw.id = $plan_id`
5. **Atomic creation**: Refactored `create_planned_workout` to use single UNWIND statement

### Atomic Plan Creation

The old approach used multiple `session.run()` calls that each auto-committed:
```python
# Old: Multiple commits = orphans on failure
session.run("CREATE PlannedWorkout")  # committed
for block in blocks:
    session.run("CREATE PlannedBlock")  # committed
    for set in sets:
        session.run("CREATE PlannedSet")  # fails here = orphans
```

New approach validates all exercises exist first, then creates everything in one statement:
```python
# New: Single commit = all or nothing
# 1. Pre-validate: check all exercise_ids exist
# 2. Single Cypher with UNWIND creates workout + blocks + sets
# 3. If MATCH (e:Exercise) fails, entire statement rolls back
```

Migrated existing data:
```cypher
MATCH (pw:PlannedWorkout)
WHERE pw.plan_id IS NULL AND pw.id IS NOT NULL
SET pw.plan_id = pw.id
```

## Related

- `docs/PLANNING.md` — Planning system design
- `docs/ARCHITECTURE.md` — System architecture

---

## Audit: Other Functions (2026-01-03)

During the fix, audited other functions for same pattern.

### Fixed (Atomic UNWIND)

| Function | Before | After |
|----------|--------|-------|
| `create_planned_workout` | Loop per block/set | Single UNWIND |
| `log_adhoc_workout` | Loop per exercise/set | Single UNWIND |
| `complete_workout_with_deviations` | Loop per deviation | Single UNWIND |

### ✅ Read Query Optimization (Jan 3, 2026)

Consolidated multi-query functions to single queries using `CALL {}` subqueries:

| Function | Before | After |
|----------|--------|-------|
| `get_training_context` | 5 queries | 1 query |
| `get_coach_briefing` | 6 queries | 1 query |
| `get_planning_status` | 3 queries | 1 query |
| `find_substitutes` | 2 queries | 1 query |

Total round-trips eliminated: 12 per combined call sequence.

### ✅ Duplicate Workout Logging (Resolved Jan 3, 2026)

Removed duplicate workout tools from profile-mcp:
- **arnold-training-mcp** → `log_adhoc_workout()` ✅ Canonical path (atomic UNWIND)
- **arnold-profile-mcp** → `log_workout` and `create_workout_node()` ✅ Removed

Profile-mcp now focuses on profile/equipment/observations only.
