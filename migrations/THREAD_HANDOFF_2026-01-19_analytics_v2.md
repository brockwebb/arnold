# Thread Handoff: V2 Schema Migration Complete → Analytics MCP Update

**Date:** 2026-01-19
**From Thread:** Analytics V2 Migration Bug Investigation & Schema Completion
**Status:** V2 schema migration COMPLETE, analytics MCP update PENDING

---

## Executive Summary

We discovered and fixed a critical data architecture issue. The `arnold-analytics-mcp` tools query legacy tables (`strength_sessions`, `strength_sets`) while new workouts since Jan 11, 2026 are logged only to V2 schema. This created an 8-day blind spot where Coach couldn't see recent training.

**What we did:**
1. Investigated and confirmed V2 already contained all legacy data (not a migration issue)
2. Identified V2 was missing semantic information (block structure, prescribed vs actual)
3. Consulted Gemini for schema design advice
4. Added `set_category` and `target_data` columns to V2
5. Backfilled all 2,597 sets with proper categorization
6. Fixed 23 sets with exercise_name='Unknown'
7. Added NOT NULL constraint on exercise_id

**What remains:**
1. Update analytics MCP to query V2 instead of legacy
2. Begin legacy table deprecation (Scream Test)
3. Fix logging code that caused Unknown bug

---

## Current State (Verified)

### V2 Schema: COMPLETE

```sql
-- v2_strength_sets now has:
set_category text CHECK (warmup/primary/secondary/assistance/finisher/cooldown)
target_data jsonb  -- for prescribed values
exercise_id text NOT NULL  -- constraint added
```

**Verified counts:**
| Metric | Value |
|--------|-------|
| Total sets | 2,597 |
| With set_category | 2,597 (100%) |
| NULL set_category | 0 |
| Unknown exercise_name | 0 |
| NULL exercise_id | 0 |

**Category distribution:**
| Category | Count |
|----------|-------|
| primary | 2,052 |
| finisher | 257 |
| warmup | 191 |
| cooldown | 50 |
| secondary | 47 |

### Legacy vs V2 Data Comparison

| Table | Rows | Date Range |
|-------|------|------------|
| strength_sessions (legacy) | 169 | 2024-04-04 to 2026-01-10 |
| workouts_v2 | 178 | 2024-04-04 to 2026-01-18 |
| strength_sets (legacy) | 2,545 | - |
| v2_strength_sets | 2,597 | - |

**Key finding:** V2 contains ALL legacy data plus 7 new workout dates. The data was already migrated - the problem was analytics tools querying the wrong tables.

---

## Task 1: Update Analytics MCP (PRIMARY)

### File to Modify
`/Users/brock/Documents/GitHub/arnold/src/arnold-analytics-mcp/arnold_analytics/server.py`

### Schema Change Reference

**OLD (Legacy):**
```
strength_sessions (id, session_date, ...)
    └── strength_sets (session_id FK, exercise_id, exercise_name, reps, load_lbs, ...)
```

**NEW (V2):**
```
workouts_v2 (workout_id UUID, start_time timestamptz, ...)
    └── segments (segment_id UUID, workout_id FK, sport_type, ...)
        └── v2_strength_sets (set_id UUID, segment_id FK, exercise_id, exercise_name, 
                              reps, load, set_category, target_data, ...)
```

### Column Mapping

| Legacy | V2 | Notes |
|--------|-----|-------|
| strength_sessions.id | workouts_v2.workout_id | integer → UUID |
| strength_sessions.session_date | workouts_v2.start_time::date | date → timestamptz |
| strength_sets.session_id | v2_strength_sets.segment_id | FK target changed |
| strength_sets.load_lbs | v2_strength_sets.load | column renamed |
| strength_sets.block_type | v2_strength_sets.set_category | values mapped (main→primary, accessory→secondary) |
| strength_sets.reps | v2_strength_sets.reps | same |
| strength_sets.rpe | v2_strength_sets.rpe | same |

### Query Pattern Change

```python
# OLD
query = """
SELECT s.exercise_id, s.exercise_name, s.reps, s.load_lbs, s.rpe,
       ss.session_date
FROM strength_sets s
JOIN strength_sessions ss ON s.session_id = ss.id
WHERE s.exercise_id = %(exercise_id)s
ORDER BY ss.session_date DESC
"""

# NEW
query = """
SELECT v.exercise_id, v.exercise_name, v.reps, v.load, v.rpe,
       w.start_time::date as session_date,
       v.set_category
FROM v2_strength_sets v
JOIN segments seg ON v.segment_id = seg.segment_id
JOIN workouts_v2 w ON seg.workout_id = w.workout_id
WHERE v.exercise_id = %(exercise_id)s
ORDER BY w.start_time DESC
"""
```

### Tools to Audit/Update

From GitHub Issue #40, confirmed affected:
- `get_exercise_history` - definitely uses legacy
- `get_training_load` - likely uses legacy

Need to audit `server.py` for any query referencing:
- `strength_sessions`
- `strength_sets`
- `FROM strength_` pattern

---

## Task 2: Legacy Deprecation (SECONDARY)

Follow 4-step Scream Test pipeline (from Gemini):

### Phase 1: Audit (Start Now)
```sql
-- Check for any reads on legacy tables
SELECT schemaname, relname, seq_scan, idx_scan, last_seq_scan, last_idx_scan
FROM pg_stat_user_tables 
WHERE relname IN ('strength_sessions', 'strength_sets');
```

After analytics MCP is updated, these should show zero new scans.

### Phase 2-4: Future
- Phase 2 (after 2 weeks clean): Rename to `*_deprecated_2026_01`
- Phase 3 (after 30 days): Move to `legacy` schema
- Phase 4 (after 90 days): DROP

---

## Task 3: Fix Unknown Bug (TERTIARY)

23 sets on Jan 14, 2026 were logged with `exercise_name='Unknown'` despite having valid `exercise_id` values. We fixed the data, but the logging code bug remains.

**Likely location:** `arnold-training-mcp` - `complete_as_written` or `log_workout` functions

**Root cause:** Exercise name resolution fails silently, defaults to 'Unknown'

**Fix:** Ensure exercise_name is resolved from Neo4j before insert, fail loudly if not found.

---

## Key Decisions Made

1. **V2 is the canonical schema** - ADR-006 confirms it's the right architecture for multi-sport, multi-user

2. **Block structure restored via set_category** - Not a separate Block table, just a column. Sufficient for coach queries like "show me primary lifts only"

3. **target_data JSONB for prescribed values** - Lightweight bridge until full Neo4j PlannedWorkout integration is complete. Historical data mostly NULL (legacy barely tracked prescribed values - only 46/2545 sets had any)

4. **NOT NULL on exercise_id** - Prevents future Unknown bugs at schema level

---

## Files Created This Thread

| File | Purpose |
|------|---------|
| `/Users/brock/Documents/GitHub/arnold/migrations/v2_completion_migration.sql` | The migration script (EXECUTED) |
| `/Users/brock/Documents/GitHub/arnold/migrations/HANDOFF_v2_completion.md` | Migration documentation |
| This file | Thread transition context |

---

## GitHub Issues

- **Issue #40**: CRITICAL: Analytics tools query legacy schema, blind to v2 workouts since Jan 11
  - Created this thread
  - Schema fix complete
  - Analytics MCP update still pending

---

## Questions the Next Thread Might Have

**Q: Why not just create a view that unions legacy and V2?**
A: We considered this (Option B). Gemini pointed out V2 was missing semantic information that couldn't be recovered via view. Now that V2 has `set_category` and all data, there's no need for a union - V2 is complete.

**Q: What about the `planned_segment_id` column on segments?**
A: Only 5/178 segments have this populated. The Neo4j PlannedWorkout integration is incomplete. The `target_data` JSONB is a bridge. Full plan linking is future work.

**Q: Should set_category be NOT NULL?**
A: Currently allows NULL for flexibility. Could tighten after confirming all logging paths populate it. Current backfill achieved 100% coverage.

**Q: What's the deal with `load` vs `load_lbs`?**
A: V2 uses `load` with a separate `load_unit` column (default 'lb'). More flexible for kg users. Analytics queries should use `load` not `load_lbs`.

---

## Clarification Protocol

**This thread has context window remaining.** If the next thread encounters ambiguity:

1. Check this handoff document first
2. Check `/Users/brock/Documents/GitHub/arnold/migrations/HANDOFF_v2_completion.md`
3. Check ADR-006: `/Users/brock/Documents/GitHub/arnold/docs/adr/006-unified-workout-schema.md`
4. If still unclear, Brock can relay questions back to this thread before it closes

**Minimize drift** - the schema decisions are settled. The next thread's job is implementation, not redesign.

---

## Success Criteria for Next Thread

1. ✓ `get_exercise_history` returns Jan 11+ workout data
2. ✓ `get_training_load` includes recent workouts in calculations
3. ✓ All analytics tools audited and updated
4. ✓ No queries reference `strength_sessions` or `strength_sets`
5. ✓ Verified via test queries that V2 data is being served

---

## One-Liner for Next Thread

> "V2 schema is complete with set_category and target_data columns. Your job: update arnold-analytics-mcp/server.py to query V2 tables instead of legacy. See HANDOFF_v2_completion.md for column mappings."
