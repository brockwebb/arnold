# Claude Code Handoff: V2 Schema Completion Migration

## Context

We discovered a critical analytics bug: `arnold-analytics-mcp` tools query legacy tables (`strength_sessions`, `strength_sets`) while new workouts since Jan 11, 2026 are logged only to V2 (`workouts_v2` → `segments` → `v2_strength_sets`). This creates an 8-day data gap where Coach is "flying blind."

Investigation revealed:
1. **V2 already has all legacy data** - 178 workouts vs 169 in legacy, perfect set-count match
2. **But V2 dropped semantic information** - block structure (warmup/main/accessory) and prescribed vs actual tracking
3. **23 sets have exercise_name='Unknown'** - bug in logging code, all have valid exercise_ids

After consulting Gemini, we determined V2 is the correct architecture (supports multi-sport, multi-user, extensible) but needs two columns added to restore semantic parity.

## The Migration

**Location:** `/Users/brock/Documents/GitHub/arnold/migrations/v2_completion_migration.sql`

**What it does:**
1. Adds `set_category` column (warmup/primary/secondary/assistance/finisher/cooldown)
2. Adds `target_data` JSONB column (for prescribed values)
3. Fixes 23 Unknown exercise names
4. Adds NOT NULL constraint on exercise_id
5. Backfills set_category from legacy block_type
6. Fills gaps for V2-only data (Jan 11+) using is_warmup flag
7. Validates completeness

**Pre-validated:**
- seq/set_order mapping: confirmed 1:1 match
- Block types in legacy: main (1986), finisher (257), warmup (191), cooldown (56), accessory (55)
- Unknown exercise IDs: all 9 resolve to valid names in Neo4j

## Execution Instructions

```bash
# Connect to arnold database
psql -d arnold -f /Users/brock/Documents/GitHub/arnold/migrations/v2_completion_migration.sql
```

Or if using environment variables:
```bash
psql "$ARNOLD_DATABASE_URL" -f /Users/brock/Documents/GitHub/arnold/migrations/v2_completion_migration.sql
```

The script runs as a single transaction - if any phase fails, everything rolls back.

## Expected Output

```
NOTICE:  === MIGRATION VALIDATION ===
NOTICE:  Total sets: 2597
NOTICE:  Categorized sets: 2597
NOTICE:  NULL category: 0 (should be 0)
NOTICE:  NULL exercise_id: 0 (should be 0)
NOTICE:  === MIGRATION SUCCESSFUL ===

 set_category | count
--------------+-------
 primary      | ~2000
 finisher     |  ~260
 warmup       |  ~200
 cooldown     |   ~60
 secondary    |   ~55
```

## Post-Migration Verification

```sql
-- 1. Confirm no Unknown exercises remain
SELECT COUNT(*) FROM v2_strength_sets WHERE exercise_name = 'Unknown';
-- Expected: 0

-- 2. Confirm all sets have category
SELECT COUNT(*) FROM v2_strength_sets WHERE set_category IS NULL;
-- Expected: 0

-- 3. Confirm NOT NULL constraint exists
\d v2_strength_sets
-- exercise_id should show "not null"

-- 4. Spot check category distribution
SELECT set_category, COUNT(*) FROM v2_strength_sets GROUP BY set_category ORDER BY count DESC;
```

## Next Steps (After Migration)

### 1. Update analytics-mcp to query V2

**File:** `/Users/brock/Documents/GitHub/arnold/src/arnold-analytics-mcp/arnold_analytics/server.py`

All tools currently querying `strength_sessions`/`strength_sets` need to query V2:
- `get_exercise_history` 
- `get_training_load`
- Others (audit the file)

Example change:
```python
# OLD
query = """
SELECT ... FROM strength_sets s
JOIN strength_sessions ss ON s.session_id = ss.id
"""

# NEW
query = """
SELECT ... FROM v2_strength_sets v
JOIN segments seg ON v.segment_id = seg.segment_id
JOIN workouts_v2 w ON seg.workout_id = w.workout_id
"""
```

### 2. Begin legacy deprecation (Scream Test)

Per Gemini's 4-step pipeline:
1. Monitor `pg_stat_user_tables` for zero reads on legacy tables
2. After 2 weeks clean, rename to `strength_sessions_deprecated_2026_01`
3. After 30 days, move to `legacy` schema
4. After 90 days, drop

### 3. Fix logging code

The Unknown bug came from workout logging. Find where `exercise_name='Unknown'` gets set and ensure it resolves from Neo4j before insert.

**Likely location:** `arnold-training-mcp` complete_as_written or log_workout functions.

## Related Issues

- **GitHub Issue #40**: CRITICAL: Analytics tools query legacy schema, blind to v2 workouts since Jan 11
- **ADR-006**: Unified Workout Schema (explains V2 architecture rationale)

## Rollback

If something goes wrong:
```sql
-- Remove added columns
ALTER TABLE v2_strength_sets DROP COLUMN IF EXISTS set_category;
ALTER TABLE v2_strength_sets DROP COLUMN IF EXISTS target_data;
ALTER TABLE v2_strength_sets ALTER COLUMN exercise_id DROP NOT NULL;
```

Note: The Unknown exercise name fixes cannot be easily rolled back (no harm in keeping them).
