# Handoff: Briefing Bugs and Deduplication Fix

**Date:** 2026-01-13
**From:** Claude (briefing bugs session)
**Status:** Complete - verified working after restart

## What Was Done

### Problems Fixed

1. **Annotation date filter bug** - Ongoing annotations weren't suppressing alerts because the query filtered on `annotation_date >= seven_days_ago`, excluding older but still-active annotations.

2. **Workout deduplication** - Briefing showed duplicate entries per date because query returned BOTH `:Workout` nodes (full structure) AND `:StrengthWorkout`/`:EnduranceWorkout` reference nodes for the same date.

3. **Workout name display** - Showed "None (0 sets)" because code used `w.get('type', 'workout')` but reference nodes have `type=null`.

4. **run_sync Python path** - Used bare `python` which doesn't exist in MCP PATH. Fixed to `/opt/anaconda3/envs/arnold/bin/python`.

### Files Modified

**`/src/arnold-memory-mcp/arnold_memory_mcp/server.py`**
- Line ~677: Changed workout name extraction to `w.get('name') or w.get('type') or 'workout'`

**`/src/arnold-memory-mcp/arnold_memory_mcp/neo4j_client.py`**
- Lines 260-290: Added deduplication query using Cypher `reduce()` to pick workout with most sets per date

**`/src/arnold-analytics-mcp/arnold_analytics/server.py`**
- `run_sync()`: Changed `cmd = ["python", ...]` to `cmd = ["/opt/anaconda3/envs/arnold/bin/python", ...]`

### Root Cause Analysis

The workout deduplication issue stems from ADR-002's dual architecture:
- `:Workout` nodes have full structure (blocks, sets) from planned workouts
- `:StrengthWorkout`/`:EnduranceWorkout` are lightweight reference nodes linking Postgres facts to Neo4j

Both get created for executed workouts. The deduplication query now uses `reduce()` to prefer whichever node has more sets (i.e., the structured `:Workout` node).

## Issues Created

| Issue | Title | Priority |
|-------|-------|----------|
| 009 | Unified Workout Logging Path | High |
| 010 | Neo4j Sync Gap - Silent Failures | Medium |
| 011 | Ultrahuman HRV Sync LaunchAgent | High |
| 012 | Sync Script Directory Convention | Low |

## Issues Closed

- **008**: Briefing Data Gaps (all root causes fixed)

## Annotations Created

- HRV `device_issue` annotation (2026-01-10) - suppresses HRV alert until plist fixed

## What's Verified Working

After Claude Desktop restart:
- ✅ Workout names display correctly (not "None")
- ✅ One entry per date (no duplicates)
- ✅ Sleep alert suppressed by annotation
- ✅ HRV alert suppressed by annotation

## What's Next

### High Priority
1. **Issue 011** - Fix LaunchAgent plist for automated Ultrahuman/HRV sync
2. **Issue 009** - Unify workout logging (single path, Claude determines type)

### Medium Priority
3. **Issue 010** - Investigate silent Neo4j sync failures (some workouts have `neo4j_id=NULL`)

## Key Technical Details

**Deduplication Query Pattern:**
```cypher
WITH workout_date, 
     reduce(best = workouts[0], w IN workouts | 
         CASE WHEN w.sets > best.sets THEN w ELSE best END) as best
```

**Annotation Filter Logic:**
```python
# Include if: ongoing (no end date) OR ended recently
annotation_date <= today AND (date_range_end IS NULL OR date_range_end >= seven_days_ago)
```

## Transcript

Full session: `/mnt/transcripts/2026-01-13-12-14-31-briefing-bugs-deduplication-fix.txt`
