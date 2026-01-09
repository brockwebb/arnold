# Exercise Normalization & Enrichment Handoff

**Date:** 2026-01-07
**Status:** IN PROGRESS - Needs migration script execution
**Priority:** HIGH - Data quality blocker

---

## Context

This session discovered and addressed a fundamental architecture violation: CUSTOM exercises were being created during workout logging instead of resolving to canonical exercises. This violates the design in ARCHITECTURE.md which specifies ONE canonical exercise with aliases for search.

## The Problem

When workouts were logged, exercises like "Kettlebell Swings" created `CUSTOM:Kettlebell_Swings` nodes instead of resolving to `CANONICAL:ARNOLD:KB_SWING_2H`. This caused:
- Duplicate exercises (141 CUSTOM nodes)
- Muscle targeting data not inherited
- Search returning multiple entries for same exercise
- Pattern frequency calculations fragmented

## Decisions Made (DO NOT RE-ASK)

### Exercise-Specific Decisions

| Exercise | Decision | Rationale |
|----------|----------|-----------|
| Box Step-Up vs Step-up | KEEP SEPARATE | Box specifies equipment |
| Elbow/Forearm Plank vs Plank | KEEP SEPARATE | Different exercises (forearm vs straight arm) |
| Elevated Push-up vs Decline Push-Up | KEEP SEPARATE | Different exercises |
| Shoulder Dislocate | KEEP as equipment-agnostic | Not tied to resistance band |
| Tabata Drill | NOT AN EXERCISE | It's a protocol (see below) |

### Protocols Are NOT Exercises

**THIS HAS BEEN DECIDED BEFORE AND KEEPS GETTING LOST:**

The following are PROTOCOLS, not exercises. They should NOT be in the exercise graph:
- **Tabata** - 20s work / 10s rest × 8 rounds
- **EMOM** - Every Minute On the Minute
- **AMRAP** - As Many Rounds As Possible
- **FGB** - Fight Gone Bad (CrossFit benchmark)

These define HOW exercises are performed, not WHAT is performed. The workout structure should capture the protocol, and the sets reference the actual exercises performed within that protocol.

**Action needed:** Remove protocol "exercises" from strength_sets, model protocols differently.

### Muscle Data Quality

When merging CUSTOM → Canonical:
- **Keep CUSTOM muscle data if source is `google_ai_overview`** — it's typically richer (11-19 muscles vs 1-5)
- Canonical data from `free-exercise-db` and `functional-fitness-db` is often sparse
- Human-verified Google AI Overview data is higher quality

## Files Created

### Review CSV
`/data/enrichment/exercise_normalization_review.csv`

Contains 141 CUSTOM exercises with **FINALIZED** actions (all REVIEWs resolved):
- **MERGE_TO_CANONICAL** (35) — Has exact/near-exact match, update refs + add alias
- **PROMOTE_TO_CANONICAL** (99) — No equivalent exists, becomes `CANONICAL:ARNOLD:X`
- **KEEP_SEPARATE** (5) — Different exercises despite similar names (Box Step-Up, Elbow Plank, Elevated Push-up, Jefferson Curl, Hollow Rock)
- **MERGE_TO_KICKBOXING** (1) — Kickboxing - Heavy Bag merges to Kickboxing
- **PROTOCOL_NOT_EXERCISE** (1) — Tabata Drill (needs protocol modeling)

### Batch Enrichment Workflow (From Earlier Session)

Created batch processing system for Google AI Overview → Claude API → Neo4j:

```
/data/enrichment/
├── batches/
│   ├── batch_001.md     # 50 exercises PROCESSED
│   └── batch_002.md     # 50 exercises READY for input
├── exercises/           # JSON output (50 files from batch 001)
├── schema_reference.json
└── exercises_needing_enrichment.md
```

**Scripts:**
- `scripts/parse_exercises.py` — Markdown → Claude API → JSON
- `scripts/ingest_exercise_enrichment.py` — JSON → Neo4j (MERGE)
- `scripts/sync_exercise_relationships.py` — Neo4j → Postgres cache

**Usage:**
```bash
# After filling batch_002.md with Google AI Overview data:
python scripts/parse_exercises.py --batch 002
python scripts/ingest_exercise_enrichment.py
python scripts/sync_exercise_relationships.py
```

## Migration Script Needed

Create `scripts/migrate_custom_exercises.py` that:

1. **Reads** the review CSV
2. **For MERGE_TO_CANONICAL rows:**
   - Updates `strength_sets.exercise_id` from CUSTOM to canonical
   - Adds CUSTOM name as alias on canonical Exercise node
   - If CUSTOM has better muscle data, transfers it to canonical
   - Deletes CUSTOM node
3. **For PROMOTE_TO_CANONICAL rows:**
   - Changes ID from `CUSTOM:X` to `CANONICAL:ARNOLD:X`
   - Updates `strength_sets.exercise_id`
4. **For KEEP_SEPARATE rows:**
   - Promotes to `CANONICAL:ARNOLD:X` (they're legitimate new exercises)
5. **Handles protocols:**
   - Logs Tabata/EMOM/AMRAP/FGB occurrences
   - Does NOT migrate them (needs separate protocol modeling)

**Transaction safety:** Wrap in transaction, verify counts match before commit.

## Current State

### Neo4j
- 4,242 Exercise nodes total
- 141 CUSTOM: prefixed (the problem)
- Vector index exists but NO embeddings populated
- Aliases field exists but empty arrays

### Postgres
- `strength_sets` references CUSTOM IDs (needs update)
- Cache tables synced but reflecting bad IDs

### Coverage After Batch 001
- 104/208 workout exercises have muscle data (50%)
- 50 exercises enriched with Google AI Overview data

## Next Steps

1. **Create migration script** (see spec above)
2. **Run with --dry-run first** to verify
3. **Execute migration** 
4. **Sync caches:** `python scripts/sync_exercise_relationships.py`
5. **Continue batch enrichment:** Fill batch_002.md, process remaining exercises
6. **Populate embeddings** for semantic search
7. **Model protocols properly** (separate issue)

## Architecture Reference

From ARCHITECTURE.md - Exercise Node schema:
```cypher
(:Exercise {
  id: string,
  name: string,                    // Canonical name
  aliases: [string],               // ["KB swing", "Russian swing"]
  common_names: [string],          // ["Kettlebell Swing", "Two-Hand KB Swing"]
  description: string,             // For vector embedding
  equipment_required: [string],    // ["kettlebell"]
  embedding: [float]               // 1536-dim (added incrementally)
})
```

The design intent: ONE node per exercise, aliases for search, workouts reference canonical ID.

---

## Compaction Notes

This is the 3rd compaction in this thread. Key context that kept getting lost:
1. Protocols (Tabata/EMOM/AMRAP/FGB) are NOT exercises
2. Equipment-specific variants (Box Step-Up) are separate from generic (Step-up)
3. Plank variants (elbow vs straight) are separate exercises
4. CUSTOM muscle data is often BETTER than canonical when source is google_ai_overview

**Read this handoff before asking questions that are answered here.**
