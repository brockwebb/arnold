# Issue 008: Briefing Data Gaps and Alert Logic

**Created:** 2026-01-13  
**Status:** CLOSED  
**Closed:** 2026-01-13

## Problems Identified

### 1. Annotations not suppressing alerts ✅ FIXED
Data gap alerts were being generated WITHOUT checking if an active annotation explains the gap. This caused repeated "No sleep data for X days" alerts despite the sleep data gap being annotated since Dec 7.

**Root cause:** 
1. `get_red_flags()` generated coaching notes BEFORE loading annotations
2. Annotation query filtered on `annotation_date >= seven_days_ago` which excluded older ongoing annotations

**Fixes applied:**
1. Reordered logic to load annotations first, build set of annotated metrics, then only generate alerts for gaps NOT covered by annotations
2. Simplified date filter: ongoing annotations (date_range_end IS NULL) are always included; bounded annotations included if they ended recently

### 2. Briefing missing recent workouts ✅ FIXED
Briefing query only matched `:Workout` label, but recent workouts use `:StrengthWorkout` / `:EnduranceWorkout` labels.

**Fix applied:** Changed query to `WHERE (w:Workout OR w:StrengthWorkout OR w:EnduranceWorkout)`

Also added `coalesce(w.name, w.type)` to handle workouts that may have name or type populated.

### 3. Jan 10 workout not synced to Neo4j ⚠️ KNOWN ISSUE
Postgres has `strength_sessions.id=175` with `neo4j_id=NULL`. Workout was logged but never synced to graph.

**Status:** Not addressed in this issue. Likely a bug in `complete_as_written` or `log_workout` tools. Needs separate investigation.

### 4. Endurance workout logging bug 🐛 DISCOVERED
`arnold-training:log_workout` routes all workouts to `strength_sessions` table regardless of type. Endurance workouts should go to `endurance_sessions`.

**Workaround:** Manual SQL insert + Neo4j node creation.

**Status:** Not addressed in this issue. Needs fix in training MCP.

## Files Modified

- `/src/arnold-memory-mcp/arnold_memory_mcp/postgres_client.py`:
  - `get_red_flags()` - Annotation-aware alerting, fixed date filter
- `/src/arnold-memory-mcp/arnold_memory_mcp/neo4j_client.py`:
  - `load_briefing()` - Multi-label workout query

## Testing Required

After MCP restart:
1. Call `memory:load_briefing` 
2. Verify NO alert about sleep data gap (annotation should suppress)
3. Verify recent workouts show names and set counts correctly

## Related Issues

- [x] Issue 009: Unified workout logging path (created)
- [x] Issue 010: Neo4j sync gap investigation (created)
