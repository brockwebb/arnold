# Arnold Project - Thread Handoff

> **Last Updated**: January 4, 2026 (Polar HR + Apple Health Biometrics Complete)
> **Previous Thread**: Postgres Analytics Layer Phase 2
> **Compactions in Previous Thread**: 1

---

## New Thread Start Here

**Context**: You're continuing development of Arnold, an AI-native fitness coaching system. The analytics layer just got real data (Polar HR + Apple Health biometrics). Next task is migrating arnold-analytics-mcp from DuckDB to Postgres.

**Quick Start**:
```
1. Read this file (you're doing it)
2. Call arnold-memory:load_briefing (gets athlete context, goals, current block)
3. Run the validation checklist below
4. Start on the Phase 3 task list
```

**If you need more context**: Read `/docs/ARCHITECTURE.md` and `/docs/issues/003-postgres-analytics-layer.md`

**If you have questions**: Ask Brock - he prefers direct questions over guessing.

---

## Validation Checklist

Run these before starting work:

```
[ ] Postgres accessible: psql -d arnold_analytics -c "SELECT 1"
[ ] Tables exist: SELECT COUNT(*) FROM workout_summaries;  -- Should be 165
[ ] Views work: SELECT * FROM daily_status LIMIT 1;
[ ] MCP servers running: arnold-training:get_coach_briefing returns data
```

---

## Phase 3 Task List: Migrate arnold-analytics-mcp to Postgres

```
[ ] 1. Read arnold-analytics-mcp source code
      Location: src/arnold-analytics-mcp/arnold_analytics_mcp/server.py
      Understand current DuckDB queries

[ ] 2. Add Postgres connection to arnold-analytics-mcp
      - Add psycopg2 to pyproject.toml
      - Create connection helper (reuse pattern from import scripts)

[ ] 3. Migrate get_readiness_snapshot
      Query: SELECT * FROM daily_status WHERE date = $1
      Return: HRV, RHR, sleep, recent training load, coaching notes

[ ] 4. Migrate get_training_load
      Query: SELECT * FROM trimp_acwr WHERE daily_trimp > 0 ORDER BY session_date DESC
      Return: Workout count, volume trends, pattern distribution, ACWR

[ ] 5. Migrate get_exercise_history
      May need new view joining workout_summaries.exercises JSONB
      Return: PR, working weights, estimated 1RM, distance to goal

[ ] 6. Migrate check_red_flags
      Query daily_status for recovery issues
      Check trimp_acwr for overtraining indicators

[ ] 7. Migrate get_sleep_analysis
      Query: SELECT * FROM readiness_daily WHERE reading_date >= $1

[ ] 8. Validate all tools work
      Compare outputs to DuckDB versions
      Test edge cases (missing data, nulls)

[ ] 9. Remove DuckDB dependency
      Remove from pyproject.toml
      Delete DuckDB-specific code
      Update docs
```

**Verification queries** (run in postgres-mcp to understand the data):

```sql
-- Recent training with full context
SELECT date, workout_type, trimp, hrv_ms, sleep_hours, data_coverage
FROM daily_status WHERE data_coverage != 'readiness_only'
ORDER BY date DESC LIMIT 10;

-- TRIMP-based ACWR trend
SELECT session_date, daily_trimp, acute_load_7d, chronic_load_28d, acwr
FROM trimp_acwr WHERE daily_trimp > 0
ORDER BY session_date DESC LIMIT 10;

-- Readiness metrics
SELECT reading_date, hrv_ms, rhr_bpm, sleep_hours, sleep_quality_pct
FROM readiness_daily ORDER BY reading_date DESC LIMIT 10;
```

### Other Options (if Phase 3 isn't the priority)

- **Plan Week 1 Sessions**: 4 workouts logged (Dec 28, 30, Jan 2, 3). Target: 3-4/week.
- **Issue 002 Phases 2-3**: Intent-based exercise selection, historical context. See `/docs/issues/002-exercise-lookup-efficiency.md`

---

## Reference: Core Documents

```
1. /docs/ARCHITECTURE.md              (System architecture - master reference)
2. /docs/mcps/README.md               (MCP boundaries and patterns) 
3. /docs/PLANNING.md                  (Planning system design)
4. /docs/DATA_DICTIONARY.md           (Data lake reference)
5. /docs/TRAINING_METRICS.md          (Evidence-based metrics)
```

### Active Issues (Check Status)

```
/docs/issues/
├── 001-planning-tool-integrity.md     → RESOLVED (atomic writes)
├── 002-exercise-lookup-efficiency.md  → Phase 1 COMPLETE (batch lookup)
└── 003-postgres-analytics-layer.md    → Phase 2 COMPLETE (Polar + Apple Health loaded)
                                        Phase 3 READY (migrate MCP to Postgres)
```

These track architectural decisions, implementation status, and open questions.

---

## Reference: Session History

### Polar HR Data Ingestion (Issue 003 - Phase 2 COMPLETE)

**Problem**: Analytics infrastructure built but starving for biometric data. `readiness_daily` frame empty.

**Solution**: Ingested Polar HR monitor export data.

**What was built:**

| Table/View | Rows | Purpose |
|------------|------|--------|
| `polar_sessions` | 61 | Raw session data (May 2025 - Jan 2026) |
| `hr_samples` | 167,670 | Second-by-second HR |
| `polar_session_metrics` | (view) | TRIMP, Edwards TRIMP, Intensity Factor |
| `hr_training_load_daily` | (view) | Daily aggregates, zone distribution |
| `trimp_acwr` | (view) | HR-based ACWR (better than volume-based) |
| `combined_training_load` | (view) | Unified volume + HR metrics |
| `readiness_daily` | 188 days | Sleep, HRV, resting HR |
| `daily_status` | (view) | Everything combined |

**Data coverage:**
- Full (training + HR + readiness): 50 days
- Readiness only: 119 days
- Volume only: 95 days
- Training + readiness: 19 days
- Training + HR: 1 day (Jan 3)

**Key metrics now available:**
- **Banister TRIMP**: Duration × HR reserve ratio × exponential intensity factor
- **Edwards TRIMP**: Zone-weighted (Z1×1 + Z2×2 + Z3×3 + Z4×4 + Z5×5)
- **Intensity Factor**: avg_hr / threshold_hr
- **Polarization**: % time in low (Z1-2) vs high (Z4-5) intensity
- **TRIMP-based ACWR**: More meaningful than volume ACWR

**Example query:**
```sql
SELECT * FROM combined_training_load WHERE workout_date = '2026-01-03';
-- Returns: The Fifty - 21,000 lbs volume, TRIMP 91, Edwards TRIMP 204, IF 0.85
```

**Files created:**
- `scripts/migrations/002_polar_sessions.sql` — Tables + views
- `scripts/import_polar_sessions.py` — Idempotent Polar importer
- `scripts/import_apple_health.py` — Apple Health biometrics importer

**Linkage:**
- `workout_summaries.polar_session_id` → FK to `polar_sessions`
- Match confidence: 1.0 (single session, duration match), 0.8 (single session), 0.6-0.7 (multi-session)
- 51 workouts linked, 10 orphaned Polar sessions (runs/walks not logged)

**Import command:**
```bash
python scripts/import_polar_sessions.py data/raw/20260103--polar-user-data-export_b658889b-4ecd-4050-8bab-57e4f187cbca
```

---

### Previous: Exercise Batch Lookup (Issue 002 - Phase 1 Complete)

**Problem**: Building one workout required 10-20 tool calls for exercise ID resolution. Doesn't scale.

**Solution**: Added batch lookup tools to training-mcp:
- `search_exercises(query, limit)` — single exercise fuzzy search
- `resolve_exercises(names[], confidence_threshold)` — batch resolution in one call

**Workflow now**:
```
Claude normalizes: ["KB swing", "RDL"] → ["kettlebell swing", "romanian deadlift"]
Claude calls: resolve_exercises([...])  // ONE tool call
Tool returns: {resolved: {...}, needs_clarification: {...}, not_found: [...]}
```

**Key decisions documented**:
1. Exercise search → training-mcp (moved from profile-mcp)
2. Claude normalizes first, always (semantic layer)
3. Low confidence (<0.5) → ask user, don't "try harder"
4. Historical weight is baseline profile parameter (not derived)

**Files changed**:
- `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` — added search_exercises, resolve_exercises
- `src/arnold-training-mcp/arnold_training_mcp/server.py` — added tool definitions and handlers
- `src/arnold-profile-mcp/arnold_profile_mcp/server.py` — marked search_exercises as DEPRECATED

### Postgres Analytics Layer (Issue 003 - Phase 1 COMPLETE)

**Problem**: DuckDB requires full rebuild on every change. Can't do incremental updates or pre-computed views.

**Solution**: Replace DuckDB with Postgres. Build analytical "frames" (like Census products).

**What was built:**
- Database `arnold_analytics` created and operational
- `workout_summaries` table — 165 workouts synced from Neo4j
- `biometric_readings` table — schema ready for Apple Health/Ultrahuman
- `training_load_daily` frame — ACWR, acute/chronic load, volume (WORKING)
- `readiness_daily` frame — ready for biometric data
- `postgres-mcp` installed (crystaldba/postgres-mcp) — includes index tuning, health checks
- Sync script: `scripts/sync_neo4j_to_postgres.py`

**Python env upgraded:** arnold conda env rebuilt at Python 3.12 (was 3.10, required for postgres-mcp)

**Architecture split**:
- Neo4j: graphs, relationships, structure (workouts, plans, exercises)
- Postgres: time-series bulk data, denormalized summaries, computed frames

**Verified working:**
```sql
SELECT workout_date, daily_volume, acwr FROM training_load_daily ORDER BY workout_date DESC;
```

---

### Previous Session: Exercise Mapping Complete (Jan 3, 2026 - Evening)

Completed systematic mapping of all 63 custom exercises to canonical exercises or marked as unique with descriptions.

**Batches Processed**: 7 batches × ~10 exercises each

**Final Results**:
- Mapped to canonical: 22 exercises
- Unique (no mapping, descriptions added): 41 exercises

**Example Mappings**:
| Custom Exercise | Maps To |
|-----------------|----------|
| Tricep Dips | Bodyweight Dips |
| Two-Handed Pehl Row | Barbell Pendlay Row (misspelling) |
| Strict Press | Standing Military Press |
| Keg Strict Press | Standing Military Press |
| Jumping Jack | Star Jump |
| Pull-Up | Pullups |

**Example Unique Exercises** (with descriptions added):
- Jefferson Curl (spinal mobility)
- Sandbag Gator Roll (NALA roll, functional strength)
- Tucked Hang (core isometric)
- Wood Splitting (literal axe work as conditioning)
- Infinite Rope (conditioning implement)

### The Fifty Workout Logged (Jan 3, 2026)

**Workout Completed**:
- Duration: 70 min (includes setup/breakdown)
- RPE: 8.5
- HR: Peak 159 bpm, Zone 5: 3 min, Zone 4: 20 min, Zone 3: 26 min

**Deviation**: Swapped Sandbag Shouldering → Sandbag Box Squat for all 5 rounds
- Reason: Avoid compounding fatigue on bicep/back/shoulders already taxed
- Effect: Shifted stress to hip hinge ROM and spinal erector bracing

**Workout ID**: `89e05724-d2dc-4a50-8293-88992edc8d84`

### Bug Fix: complete_with_deviations Tool (Jan 3, 2026)

**The Problem**: When logging the workout with deviations, the `complete_with_deviations` tool recorded deviations as metadata but did NOT update the actual exercise link on the Set node. The workout was logged with Sandbag Shouldering even though Box Squats were actually performed.

**Root Cause**: The deviation schema only supported rep/load changes, not exercise substitutions. The code path:
1. `complete_as_written()` creates workout with planned exercises
2. `complete_with_deviations()` only updated reps/load/notes, never changed `OF_EXERCISE` relationship

**The Fix** (in `arnold-training-mcp`):

1. Added `substitute_exercise_id` to deviation schema:
```python
"substitute_exercise_id": {
    "type": "string",
    "description": "If they did a different exercise, the ID of the substitute"
}
```

2. Updated `complete_workout_with_deviations()` to:
   - Separate deviations into substitutions vs rep/load changes
   - For substitutions: DELETE old `OF_EXERCISE`, CREATE new one to substitute exercise
   - Track substitution info in `DEVIATED_FROM` relationship (`substituted_from`, `substituted_to`)

**Files Changed**:
| File | Change |
|------|--------|
| `src/arnold-training-mcp/arnold_training_mcp/server.py` | Added `substitute_exercise_id` to tool schema |
| `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` | Handle exercise substitutions in deviations |

**Requires**: Restart Claude Desktop to pick up MCP changes.

### Bug Fix: Workout.name Not Populated (Jan 3, 2026)

**The Problem**: Executed `Workout` nodes were missing the `name` property. The human-friendly name (e.g., "The Fifty") existed on `PlannedWorkout.goal` but wasn't copied to `Workout.name` during execution.

**Root Cause**: `complete_workout_as_written()` created the Workout node but never copied `pw.goal` → `w.name`.

**The Fix** (in `arnold-training-mcp`):

1. `complete_workout_as_written()` now sets:
   - `w.name = pw.goal` (human-friendly name)
   - `w.source = 'planned'` (provenance tracking)

2. `log_adhoc_workout()` now accepts and sets `w.name` parameter

3. Schema documentation updated to reflect `name` and `source` fields on `Workout`

**Files Changed**:
| File | Change |
|------|--------|
| `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` | Added `name` and `source` to Workout creation |
| `docs/schema.md` | Documented `name` field and population rules |

**Note**: This was first discussed Dec 30, 2025 but the fix was never implemented until now.

---

### Planning Tool Integrity Fix (Issue 001)

**The Problem**: PlannedWorkout nodes had broken ID handling:
- `plan_id` property was never persisted (stored as `id` instead)
- `get_plan_for_date` returned synthetic IDs that didn't match database
- Date validation missing (allowed wrong year like `2025-01-03` instead of `2026-01-03`)
- Orphan draft plans left behind from failed creations

**The Solution**: 
1. Changed property from `id` to `plan_id` in `create_planned_workout`
2. Added date validation (rejects wrong year, warns on distant past)
3. All queries now use `COALESCE(pw.plan_id, pw.id)` for backward compatibility
4. All MATCH clauses use `WHERE pw.plan_id = $plan_id OR pw.id = $plan_id`
5. Refactored to atomic creation using single UNWIND statement (no orphans on failure)

### Files Changed

| File | Change |
|------|--------|
| `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` | Fixed plan_id, date validation, atomic UNWIND for 3 functions |
| `docs/issues/001-planning-tool-integrity.md` | Issue filed and resolved |

### Data Fixed

```cypher
-- Fixed date on The Fifty plan
SET p.date = date('2026-01-03')

-- Migrated existing plans to use plan_id
MATCH (pw:PlannedWorkout)
WHERE pw.plan_id IS NULL AND pw.id IS NOT NULL
SET pw.plan_id = pw.id

-- Deleted 2 orphan drafts
```

### Audit Results

Audited all write functions in `neo4j_client.py` for the same loop-based orphan risk:

| Function | Status |
|----------|--------|
| `create_planned_workout` | ✅ Fixed (atomic UNWIND) |
| `log_adhoc_workout` | ✅ Fixed (atomic UNWIND) |
| `complete_workout_with_deviations` | ✅ Fixed (atomic UNWIND) |
| `complete_workout_as_written` | ✅ Already atomic (single Cypher) |

Read-only functions with multiple queries (efficiency, not correctness):
- `get_training_context` (5 queries → could be 1)
- `get_coach_briefing` (6 queries → could be 1)

These are lower priority — no orphan risk, just latency.

### Read Query Optimization ✅

Consolidated multi-round-trip queries to single queries using `CALL {}` subqueries:

| Function | Before | After |
|----------|--------|-------|
| `get_training_context` | 5 queries | 1 query |
| `get_coach_briefing` | 6 queries | 1 query |
| `get_planning_status` | 3 queries | 1 query |
| `find_substitutes` | 2 queries | 1 query |

### Duplicate Workout Tools Removed ✅

Removed `log_workout` and `get_workout_by_date` from profile-mcp. Training-mcp is now the canonical path for all workout operations.

### Doc Corrections

Fixed `exercise_kb_improvement_plan.md`:
- Relationship name: `HAS_MOVEMENT_PATTERN` → `INVOLVES` (doc was wrong, DB was right)
- Phase 6 marked complete (4,951 INVOLVES relationships exist)
- Updated custom exercise counts (87 mapped, 63 remaining)

### Schema Documentation Added (Jan 3, 2026)

**Problem**: Claude wasted time guessing node labels from ID prefixes. Tried `Plan` when the actual label is `PlannedWorkout`, tried `HAS_PLANNED_SET` when the actual relationship is `CONTAINS_PLANNED`.

**Solution**: Added two quick reference sections to `/docs/schema.md`:

1. **ID Conventions** - Maps ID prefixes to node labels:
   - `PLAN:` → `PlannedWorkout`
   - `PLANBLOCK:` → `PlannedBlock`
   - `PLANSET:` → `PlannedSet`
   - *(no prefix)* → Executed: `Workout`, `WorkoutBlock`, `Set`

2. **Planned vs Executed States** - Quick reference for relationship names:
   - Session → Block: `HAS_PLANNED_BLOCK` (planned) vs `HAS_BLOCK` (executed)
   - Block → Set: `CONTAINS_PLANNED` (planned) vs `CONTAINS` (executed)
   - Set → Exercise: `PRESCRIBES` (planned) vs `OF_EXERCISE` (executed)

**Lesson**: Always call `neo4j-mcp:get-schema` before writing raw Cypher against unfamiliar node types.

### "The Fifty" Plan Corruption Fixed (Jan 3, 2026)

**Problem**: Original plan created with only 2 of 5 circuit exercises (Trap Bar Deadlift + Pullups). The `create_workout_plan` call got truncated mid-write — the bug pattern we fixed earlier.

**Root Cause**: Plan was created before the atomic UNWIND fix. Early conversation quit left partial data.

**Solution**: Deleted corrupted plan, recreated with all 5 exercises:
- Trap Bar Deadlift (195 lb)
- Kettlebell Swings (55 lb)
- Pullups (BW)
- Landmine Shoulder Press (70 lb)
- Sandbag Shouldering (100 lb)

Plus finisher: 50 Pushups + 50 Sit-Ups

**New Plan ID**: `PLAN:18b82903-1d0c-4047-bec1-82f38ea65e34`

### MCP Documentation Created

Created comprehensive documentation for all four MCPs:

| Doc | Purpose |
|-----|--------|
| `docs/mcps/README.md` | MCP roster, boundaries table, cross-MCP patterns |
| `docs/mcps/arnold-training.md` | Training MCP - planning, execution, key decisions |
| `docs/mcps/arnold-profile.md` | Profile MCP - identity, equipment, observations |
| `docs/mcps/arnold-analytics.md` | Analytics MCP - metrics, readiness, red flags |
| `docs/mcps/arnold-memory.md` | Memory MCP - context, observations, semantic search |

Follows ADR pattern: Context → Decision → Consequence. Serves three audiences:
1. Claude (context for future threads)
2. Developer (remember what and why)
3. Contributors (understand the thinking)

---

### Previous Session: Exercise Matching Architecture ✅

**The Problem**: `find_canonical_exercise` used exact string matching (toLower). Failed on common queries:
- "KB swing" → Not found
- "pull up" → Wrong match
- "sit ups" → Missing from DB
- "landmine press" → Missing from DB

**The Solution**: Three-layer architecture

```
┌─────────────────────────────────────────────────────┐
│            SEMANTIC LAYER (Claude)                  │
│  "KB swing" → "Kettlebell Swing"                    │
│  Claude IS the semantic layer                       │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│            RETRIEVAL LAYER (Neo4j)                  │
│  Full-text index + Vector index                     │
│  Returns candidates, Claude picks best              │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│            ENRICHMENT LAYER (Graph)                 │
│  Aliases on Exercise nodes                          │
│  Embeddings added incrementally                     │
└─────────────────────────────────────────────────────┘
```

### Implementation Complete

| Component | Status |
|-----------|--------|
| Full-text index (`exercise_search`) | ✅ Live |
| Vector index (`exercise_embedding_index`) | ✅ Live |
| Initial aliases (51 exercises) | ✅ Complete |
| `search_exercises` tool | ✅ Working |
| Bug fix (parameter conflict) | ✅ Fixed |

### Test Results (All Passing)

| Query | Top Match | Score |
|-------|-----------|-------|
| kettlebell swing | Kettlebell Swings | 7.73 |
| KB swing | Kettlebell Swings | 6.30 |
| sit ups | Sit-Up | 6.74 |
| landmine press | Single Arm Landmine Shoulder Press | 5.99 |
| pull up | Pullups | 4.26 |
| push up | Pushups | 4.04 |
| sandbag ground to shoulder | Sandbag Shouldering | 6.90 |

### Files Changed

| File | Change |
|------|--------|
| `src/arnold-profile-mcp/arnold_profile_mcp/neo4j_client.py` | Added `search_exercises()`, fixed param conflict |
| `src/arnold-profile-mcp/arnold_profile_mcp/server.py` | Added `search_exercises` tool |
| `docs/ARCHITECTURE.md` | Added Exercise Matching Architecture section |
| `docs/exercise_kb_improvement_plan.md` | Added Phase 8, updated status |

### Incremental Improvement Path

The system improves with use:
1. Add aliases as exercises are touched in workouts
2. Add embeddings for semantic search fallback when needed
3. Fill gaps (missing exercises) as discovered

---

## Reference: Current State

### The Fifty Workout (Today - Jan 3)

Plan recreated after corruption fix:
- **Plan ID**: `PLAN:18b82903-1d0c-4047-bec1-82f38ea65e34`
- **Status**: Confirmed
- 5 rounds × 5 exercises × 10 reps = 250 reps
- Finisher: 50 push-ups, 50 sit-ups
- Total: 350 reps, ~60 min

Circuit exercises: Trap Bar Deadlift (195), KB Swings (55), Pullups, Landmine Press (70), Sandbag Shouldering (100)

### Analytics Tools (All Operational)

```
arnold-analytics:check_red_flags      → Flags biometric gaps
arnold-analytics:get_readiness_snapshot → Returns available data
arnold-analytics:get_training_load    → Volume/pattern analysis
arnold-analytics:get_exercise_history → PR tracking, e1RM
arnold-analytics:get_sleep_analysis   → Sleep pattern analysis
```

### MCP Roster

| MCP | Status | Purpose |
|-----|--------|---------|
| arnold-profile-mcp | ✅ | Profile, equipment, activities |
| arnold-training-mcp | ✅ | Planning, logging, execution, exercise search |
| arnold-memory-mcp | ✅ | Context, observations, semantic search |
| arnold-analytics-mcp | ✅ | Readiness, training load, red flags (uses DuckDB, migration pending) |
| neo4j-mcp | ✅ | Direct graph queries |
| postgres-mcp | ✅ NEW | Direct SQL, index tuning, health checks (crystaldba/postgres-mcp) |

---

## Athlete Context (Brock)

- **Age**: 50 (turned 50 January 2, 2026)
- **Background**: 35 years martial arts, 18 years ultrarunning, desk job
- **Recent**: Knee surgery November 2025, cleared for normal activity
- **Goals**: Deadlift 405x5, Hellgate 100k, 10 pain-free ring dips by June 2026
- **Training philosophy**: Evidence-based, prefers substance over engagement

---

## Architecture Summary

```
Neo4j (CYBERDYNE-CORE)         Postgres (T-1000)
├── Relationships               ├── workout_summaries (165, linked to Polar)
├── Exercise graph              ├── polar_sessions (61 sessions)
├── Coaching workflow           ├── hr_samples (167K samples)
└── Memory/observations         ├── biometric_readings (HRV, RHR, sleep)
                                ├── readiness_daily (materialized view)
                                ├── combined_training_load (view)
                                ├── trimp_acwr (view)
                                └── daily_status (view)

Claude Desktop orchestrates via MCP servers:
- arnold-* MCPs for domain logic
- neo4j-mcp for graph queries  
- postgres-mcp for analytics queries
```

---

## Critical Notes for Future Claude

1. **Postgres analytics layer is live** - Database `arnold_analytics` has:
   - 165 workouts in `workout_summaries` (51 linked to Polar sessions)
   - 61 Polar sessions with 167K HR samples
   - Biometrics (HRV, RHR, sleep) in `biometric_readings`
   - Key views: `daily_status`, `combined_training_load`, `trimp_acwr`, `readiness_daily`
   - Use `postgres-mcp:execute_sql` for direct queries

2. **Use `search_exercises` not `find_canonical_exercise`** - The new tool returns multiple candidates with relevance scores. Claude should normalize input, review candidates, and select the best match.

3. **Incremental embedding strategy** - Don't try to embed all 4,242 exercises upfront. Add embeddings as exercises are touched. System gets smarter with use.

4. **Full-text index covers name + aliases** - The `exercise_search` index searches both fields. Add aliases to exercises as you discover common variations.

5. **Parameter naming in Neo4j driver** - Don't use `query` as a parameter name in `session.run()` - it conflicts with the driver's method signature. We fixed this with `search_term`.

6. **Post-surgery ACWR interpretation** - High ACWR is expected during ramp-up. Don't flag as injury risk without context.

7. **Workout ↔ Polar linkage** - `workout_summaries.polar_session_id` is FK to `polar_sessions`. Match confidence in `polar_match_confidence` (1.0 = high, 0.6 = multi-session day). 10 orphaned Polar sessions exist (runs/walks not logged in Arnold).

8. **Postgres connection** - Import scripts use `psycopg2.connect(dbname='arnold_analytics')` relying on local socket auth. May need adjustment for MCP server context.

9. **Materialized view refresh** - `readiness_daily` needs manual refresh after biometric imports: `REFRESH MATERIALIZED VIEW readiness_daily`

10. **JSONB in workout_summaries** - The `exercises` column contains structured data. Use `jsonb_array_elements()` for queries.

11. **Null handling** - Many metrics are nullable (no HR data, no sleep data). Views handle this but tools need null-safe logic.

---

## Frequently Asked Questions

**Q: Why both Neo4j and Postgres?**
A: Neo4j excels at relationships (exercise→muscle→pattern graphs, coaching observations, training plans). Postgres excels at time-series analytics (ACWR calculations, trend analysis, aggregations). Each does what it's best at.

**Q: Why not just use postgres-mcp directly from Claude?**
A: arnold-analytics-mcp wraps domain logic. It knows what "readiness" means, what thresholds matter, how to interpret ACWR. Raw SQL would require Claude to re-derive this each conversation.

**Q: What's the TRIMP formula?**
A: Banister TRIMP = duration_minutes × HR_reserve_ratio × 0.64 × exp(1.92 × HR_reserve_ratio). Edwards TRIMP = Σ(zone_minutes × zone_weight) where Z1=1, Z2=2, Z3=3, Z4=4, Z5=5. Both are in `polar_session_metrics` view.

**Q: Why 51 workouts linked but 61 Polar sessions?**
A: 10 Polar sessions are runs/walks that weren't logged in Arnold (outdoor activities without structured sets). They're orphaned but kept for completeness.

**Q: What if I need to re-run an import?**
A: All import scripts are idempotent. They use ON CONFLICT DO UPDATE or skip existing records. Safe to re-run.

---

## Sync Commands

### Neo4j → Postgres Sync
```bash
# Sync workout summaries from Neo4j to Postgres
python scripts/sync_neo4j_to_postgres.py
```

### Polar HR Data Import
```bash
# Import Polar export (idempotent - skips existing sessions)
python scripts/import_polar_sessions.py data/raw/<polar-export-folder>

# Example:
python scripts/import_polar_sessions.py data/raw/20260103--polar-user-data-export_b658889b-4ecd-4050-8bab-57e4f187cbca
```

### Apple Health Biometrics Import
```bash
# First: Export from iPhone Health app, extract, stage to parquet
# (staging scripts in scripts/export_to_analytics.py)

# Then: Import staged parquet files to Postgres
python scripts/import_apple_health.py

# Refresh the materialized view after import
psql -d arnold_analytics -c "REFRESH MATERIALIZED VIEW readiness_daily"
```

### Workout ↔ Polar Linkage
Linkage is automatic during `sync_neo4j_to_postgres.py`. To re-run linkage manually:
```sql
-- Run the linkage query in postgres-mcp or psql
-- See scripts/migrations/002_polar_sessions.sql for the matching logic
```

### Legacy DuckDB (still used by arnold-analytics-mcp)
```bash
# Old DuckDB rebuild - DEPRECATED, will be removed in Phase 3
python scripts/export_to_analytics.py
python scripts/create_analytics_db.py
```

> **Note**: arnold-analytics-mcp still uses DuckDB. Migration to Postgres is Phase 3 of Issue 003.
