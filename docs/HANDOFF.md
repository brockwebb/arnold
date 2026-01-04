# Arnold Project - Thread Handoff

> **Last Updated**: January 3, 2026 (Exercise Batch Lookup + Postgres Analytics Planning)
> **Previous Thread**: Exercise Mapping + The Fifty + Bug Fixes
> **Compactions in Previous Thread**: 2

## For New Claude Instance

You're picking up development of **Arnold**, an AI-native fitness coaching system built on Neo4j + Postgres. The exercise matching architecture was just completed, fixing the brittle string matching that was breaking workout logging.

---

## Step 1: Read the Core Documents

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
└── 003-postgres-analytics-layer.md    → PLANNING (DuckDB → Postgres)
```

These track architectural decisions, implementation status, and open questions.

---

## Step 2: What Was Accomplished This Session

### Exercise Batch Lookup (Issue 002 - Phase 1 Complete)

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

### Postgres Analytics Layer (Issue 003 - Planning)

**Problem**: DuckDB requires full rebuild on every change. Can't do incremental updates or pre-computed views.

**Solution**: Replace DuckDB with Postgres. Build analytical "frames" (like Census products):
- `readiness_daily` — morning check-in
- `training_load_weekly` — ACWR, monotony, strain  
- `progression_by_modality` — goal tracking
- `biometric_series` — long-term trends

**Architecture split**:
- Neo4j: graphs, relationships, structure (workouts, plans, exercises)
- Postgres: time-series bulk data (292K biometrics), denormalized summaries, computed frames

**Status**: Schema drafted, implementation plan documented. Not yet built.

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

## Step 3: Current State

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
| arnold-profile-mcp | ✅ | Profile, equipment, exercise search |
| arnold-training-mcp | ✅ | Planning, logging, execution |
| arnold-memory-mcp | ✅ | Context, observations, semantic search |
| arnold-analytics-mcp | ✅ | Readiness, training load, red flags |
| neo4j-mcp | ✅ | Direct graph queries |

---

## Step 4: Immediate Next Steps

### Option A: Plan Week 1 Remaining Sessions
- Current: 3 workouts logged (Dec 28, Dec 30, Jan 3)
- Block target: 3-4 sessions/week × 4 weeks
- Identify gaps and schedule remaining Week 1 sessions

### Option B: Bayesian Pattern Detection
- Next Phase 2 item from roadmap
- Replace threshold-based alerts with evidence accumulation
- Handles sparse data gracefully (common in biometrics)

### Option C: Update Documentation / Roadmap
- Mark exercise mapping complete in exercise_kb_improvement_plan.md
- Update roadmap with Phase 2 progress
- Review any stale documentation

---

## Step 5: Quick Start for New Thread

```
1. Read /Users/brock/Documents/GitHub/arnold/docs/HANDOFF.md (this file)
2. Call arnold-memory:load_briefing
3. Optionally: Call arnold-analytics:check_red_flags
```

---

## Step 6: Load Context (Expanded)

Call `arnold-memory:load_briefing` to get:
- Active goals (Deadlift 405x5, Hellgate 100k, Ring Dips 10, Stay Healthy)
- Current block (Week 1 of 4, Accumulation)
- Training levels per modality
- Active injuries (knee surgery recovery - cleared for normal activity)
- Recent workouts
- Equipment inventory

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
Neo4j (CYBERDYNE-CORE)     Postgres (T-1000) [Planned]
├── Relationships          ├── Time-series biometrics
├── Exercise graph         ├── Workout summaries  
├── Coaching workflow      ├── Analytical frames
└── Memory/observations    └── Pre-computed reports

Claude Desktop orchestrates both via MCP servers
```

---

## Critical Notes for Future Claude

1. **Use `search_exercises` not `find_canonical_exercise`** - The new tool returns multiple candidates with relevance scores. Claude should normalize input, review candidates, and select the best match.

2. **Incremental embedding strategy** - Don't try to embed all 4,242 exercises upfront. Add embeddings as exercises are touched. System gets smarter with use.

3. **Full-text index covers name + aliases** - The `exercise_search` index searches both fields. Add aliases to exercises as you discover common variations.

4. **Parameter naming in Neo4j driver** - Don't use `query` as a parameter name in `session.run()` - it conflicts with the driver's method signature. We fixed this with `search_term`.

5. **Post-surgery ACWR interpretation** - High ACWR is expected during ramp-up. Don't flag as injury risk without context.

---

## Rebuild Commands (Current - DuckDB)

> **Note**: Postgres migration planned but not yet implemented. See Issue 003.

```bash
# If Neo4j data changes:
python scripts/export_to_analytics.py

# Always after export:
python scripts/create_analytics_db.py
```
