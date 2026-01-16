# Issue 013 Handoff: Unified Workout Schema Complete

**Date:** 2026-01-14  
**Issue:** 013-unified-workout-schema  
**Status:** CLOSED  

## What Was Done

Implemented segment-based unified workout schema per ADR-006. The old two-table design (`strength_sessions`, `endurance_sessions`) couldn't handle multi-sport workouts or new modalities. The new schema supports any sport type through a hierarchical structure.

### Schema Architecture

```
workouts_v2 (session envelope)
  └── segments (sport_type discriminator, ordered blocks)
        ├── v2_strength_sets
        ├── v2_running_intervals  
        ├── v2_rowing_intervals
        ├── v2_cycling_intervals
        ├── v2_swimming_laps
        └── v2_segment_events_generic (fallback)
```

### Phases Completed

| Phase | Description | Key Deliverables |
|-------|-------------|------------------|
| 1-3 | DDL + indexes + metric catalog | 9 new tables, unified activity view |
| 4 | Data migration | 173 workouts, 2545 strength sets, 4 endurance sessions migrated |
| 5 | MCP client rewrite | `postgres_client.py` routes to v2 schema |
| 6 | Neo4j references | 170 workout nodes updated with `workout_id` UUID |

### Data Counts (Post-Migration)

- `workouts_v2`: 174 (173 migrated + 1 new)
- `segments`: 174
- `v2_strength_sets`: 2,561 (2,545 migrated + 16 new)
- `v2_running_intervals`: 3
- `v2_rowing_intervals`: 1

### Bug Fix Applied

Fixed `postgres_client.py` line ~195 - exercise_name extraction now handles None:
```python
# Before (bug): 
s.get('exercise_name', 'Unknown')  # Returns None if key exists with None value

# After (fixed):
s.get('exercise_name') or s.get('name') or 'Unknown'
```

MCP server was restarted to pick up fix.

## What's Still There (Backward Compatibility)

Old tables remain for rollback:
- `strength_sessions` - 169 records (one deleted during cleanup)
- `strength_sets` - 2,529 records  
- `endurance_sessions` - 5 records

These can be dropped after 30-day verification period.

## Key Files Changed

| File | Change |
|------|--------|
| `src/arnold-training-mcp/arnold_training_mcp/postgres_client.py` | Complete rewrite for v2 schema |
| `docs/issues/013-unified-workout-schema.md` | Closed |
| `docs/adr/006-unified-workout-schema.md` | Reference architecture |

## Neo4j Reference Pattern

Workout nodes now have both:
- `postgres_id` (old integer, retained for backward compat)
- `workout_id` (new UUID pointing to `workouts_v2.workout_id`)

## How New Workouts Flow

1. Claude calls `log_strength_session()` or `log_endurance_session()` 
2. MCP inserts → `workouts_v2` → `segments` → sport-specific child table
3. Returns `workout_id` (UUID) and `session_id` (same UUID, for compat)
4. Neo4j ref creation uses UUID

## Transcripts

All work documented in:
- `/mnt/transcripts/2026-01-13-23-45-14-issue-013-phase1-3-ddl-complete.txt`
- `/mnt/transcripts/2026-01-14-00-01-56-issue-013-phase4-strength-complete.txt`
- `/mnt/transcripts/2026-01-14-00-17-20-issue-013-phase4-migration-complete.txt`
- `/mnt/transcripts/2026-01-14-00-21-01-issue-013-phase5-mcp-v2-schema.txt`

## Next Thread Should Know

1. **V2 schema is live** - all new workouts go to v2 tables
2. **Old tables are read-only** - don't write to them
3. **MCP server must be restarted** after any `postgres_client.py` changes
4. **Multi-modal workouts now possible** - can have strength + cardio in same session via multiple segments
5. **Jan 13, 2026 workout** was first real workout through v2 (after cleanup)

## Suggested Next Work

- Issue 010: Neo4j sync gap fixes (some workout refs may be stale)
- Deprecation cleanup: Schedule old table drops after verification period
- Multi-modal test: Log a brick workout (run + lift) to verify segment handling
