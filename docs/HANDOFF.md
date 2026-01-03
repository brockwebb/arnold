# Arnold Project - Thread Handoff

> **Last Updated**: January 2, 2026 (Exercise Matching Architecture Complete)
> **Previous Thread**: Analytics MCP Operational + Data Quality Fixes
> **Compactions in Previous Thread**: 1

## For New Claude Instance

You're picking up development of **Arnold**, an AI-native fitness coaching system built on Neo4j + DuckDB. The exercise matching architecture was just completed, fixing the brittle string matching that was breaking workout logging.

---

## Step 1: Read the Core Documents

```
1. /Users/brock/Documents/GitHub/arnold/docs/ARCHITECTURE.md  (System architecture - includes Exercise Matching section)
2. /Users/brock/Documents/GitHub/arnold/docs/PLANNING.md  (Planning system design)
3. /Users/brock/Documents/GitHub/arnold/docs/exercise_kb_improvement_plan.md  (Phase 8 = matching architecture)
4. /Users/brock/Documents/GitHub/arnold/docs/DATA_DICTIONARY.md  (Data lake reference)
5. /Users/brock/Documents/GitHub/arnold/docs/TRAINING_METRICS.md  (Evidence-based metrics)
```

---

## Step 2: What Was Accomplished This Session

### Major Deliverable: Exercise Matching Architecture ✅

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

### The Fifty Workout (Tomorrow)

Plan created for January 3rd:
- **Plan ID**: `PLAN:d805010d-a9df-49c6-9392-1daba60e2f5a`
- **Status**: Confirmed
- 5 rounds × 5 exercises × 10 reps = 250 reps
- Finisher: 50 push-ups, 50 sit-ups
- Total: 350 reps, ~60 min

Exercises: Trap Bar Deadlift, Sandbag Shouldering, Chin-Ups, Push-Ups, Kettlebell Swings

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

### Option A: Execute The Fifty
- Tomorrow (Jan 3) is the workout
- Use `complete_as_written` or `complete_with_deviations` to log

### Option B: Coaching Loop
- Plan remaining Week 1 sessions
- Test full workflow with new exercise matching

### Option C: Continue Enrichment
- Add more aliases to commonly-used exercises
- Batch backfill embeddings for semantic search

---

## Step 5: Load Context

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
Neo4j (CYBERDYNE-CORE)     DuckDB (T-1000)
├── Relationships          ├── Time-series
├── Exercise graph         ├── Aggregations  
├── Coaching workflow      ├── Metrics
└── Memory/observations    └── Reports

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

## Rebuild Commands (If Needed)

```bash
# If Neo4j data changes:
python scripts/export_to_analytics.py

# Always after export:
python scripts/create_analytics_db.py
```
