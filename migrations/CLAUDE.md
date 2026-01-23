# Claude Code Migration Context

**Project:** Arnold (AI Fitness Coaching System)  
**Task:** Schema Simplification Migration  
**Date:** 2026-01-20

## Scope (READ FIRST)

This migration is **ONLY** about the workout log layer:

✅ Rename: `workouts_v2` → `workouts`, `segments` → `blocks`, `v2_strength_sets` → `sets`  
✅ Rename column: `segment_id` → `block_id`  
✅ Rename column: `sport_type` → `modality` (on blocks)  
✅ Update views that reference old names  
✅ Update MCPs to use new names  
✅ Clean up duplicate data  

❌ **DO NOT** touch `endurance_sessions`  
❌ **DO NOT** build device telemetry infrastructure  
❌ **DO NOT** drop tables — rename unused to `_deprecated_*`  

## Pre-flight Complete

4 views will break:

| View | Action |
|------|--------|
| `srpe_training_load` | UPDATE (new table/column names) |
| `training_load_daily` | UPDATE |
| `workout_summaries_v2` | UPDATE + RENAME to `workout_summaries` |
| `v_all_activity_events` | DROP (unused) |

## Files to Reference

1. **Migration Instructions:** `/migrations/SCHEMA_SIMPLIFICATION_INSTRUCTIONS.md` — Execute this
2. **Ontology:** `/docs/ontology/workout-structure.md` — Data model (Phase 1 done)
3. **ADR-007:** `/docs/adr/007-simplified-workout-schema.md` — Decision record
4. **ADR-006:** `/docs/adr/006-unified-workout-schema.md` — What went wrong (context)

## Database Credentials

```bash
# Postgres
psql -h localhost -U brock -d arnold_analytics

# Backup (already taken)
pg_dump -h localhost -U brock -d arnold_analytics -f ~/pre_migration_backup_YYYYMMDD.sql
```

## Execution Order

1. **Phase 2 Step 1:** Deprecate unused tables (rename to `_deprecated_*`)
2. **Phase 2 Step 2:** Drop views that will break
3. **Phase 2 Step 3:** Rename core tables
4. **Phase 2 Step 4:** Rename `segment_id` → `block_id`
5. **Phase 2 Steps 5-9:** Add columns, backfill, audit
6. **Phase 3:** Recreate views with new names
7. **Phase 4:** Update MCPs
8. **Phase 5:** Create deviation view
9. **Phase 6:** Clean up duplicate data

## Known Bugs to Fix During Migration

1. **Duplicate workouts Jan 15-19** — Double-insert bug, need to dedupe
2. **Exercise name typo Jan 20** — "Trap Bar Romanian Deadlift" → "Trap Bar Deadlift"
3. **postgres_id kwarg error** — Neo4j client signature mismatch (Phase 8)

## MCP Locations

```bash
src/arnold-training-mcp/    # Workout logging
src/arnold-analytics-mcp/   # Metrics queries  
src/arnold-memory-mcp/      # load_briefing
```

Find all references:
```bash
grep -r "workouts_v2\|v2_strength\|segments\|segment_id" --include="*.py" src/
```

## Verification After Each Phase

```sql
-- Tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name IN ('workouts', 'blocks', 'sets');

-- Old names gone
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name IN ('workouts_v2', 'segments', 'v2_strength_sets');

-- No stale references in views
SELECT viewname FROM pg_views 
WHERE schemaname = 'public'
  AND (definition LIKE '%workouts_v2%' 
    OR definition LIKE '%v2_strength%' 
    OR definition LIKE '%segments%');
```

## After Phase 6: Execute Phase 6b

**IMPORTANT:** The deviation view created in Phase 5 used JSONB `extra` fields instead of proper FK relationships. This needs fixing.

Read `/migrations/PHASE_6B_DEVIATION_FIX.md` and execute:

1. Create `planned_sets` table in Postgres
2. Add FK constraint to `sets.planned_set_id`
3. Replace `execution_vs_plan` view with proper FK join version
4. Update MCP plan creation to mirror planned sets to Postgres
5. Update MCP workout completion to link executed sets to planned sets

## After Phase 6b: Execute Phase 6c

**CRITICAL:** Several implementation choices violated the sport-agnostic design. 

Read `/migrations/PHASE_6C_ARCHITECTURE_CORRECTIONS.md` and execute:

1. Remove hardcoded `WHERE modality = 'strength'` filters from views
2. DROP `v_all_activity_events` entirely (not "simplify to strength")
3. RESTORE endurance tables (we deprecated tables that consumers still use)
4. Update `execution_vs_plan` to handle unlinked sets gracefully (2626 historical sets have no plan)
5. Add table comments documenting sport-agnostic design intent

**Key principle:** Sport is a PROPERTY, not a FILTER. "95% strength" meant don't over-engineer separate tables, NOT "only support strength."

## NOW: Execute Phase 7 (MCP Verification)

**Status:** Phase 6c complete. Now verify MCPs.

Read `/migrations/PHASE_4_MCP_VERIFICATION.md` and execute:

1. `grep` for any remaining old table/column names in `src/`
2. Update any files still using old names
3. Run functional tests (log workout, query workout, load briefing)
4. Restart MCPs after any code changes
5. Report results

**Expected outcome:** All MCPs use new table names, functional tests pass.

This aligns with ADR-007/008: Postgres for facts, Neo4j for relationships.

## After Migration

Test these work:
- Log a workout via MCP
- `load_briefing` returns recent workouts
- Analytics queries return data

## DO NOT DO (Out of Scope)

- Device telemetry tables (ADR-008, future)
- FIT file ingestion
- Modifying endurance_sessions
- Athlete calibration parameters
- TRIMP/TSS computation

Stay focused on the table renames and view updates.
