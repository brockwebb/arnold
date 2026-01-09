# Arnold Project - Thread Handoff

> **Last Updated**: January 8, 2026 (Batch 003 template created)
> **Previous Thread**: Batch 002 enrichment + ADR-001 compliance + batch_003.md template
> **Compactions in Previous Thread**: ~3

---

## New Thread Start Here

**Context**: Arnold is an AI-native fitness coaching system with a dual-database architecture. Major exercise migration/enrichment work just completed — 116 CANONICAL:ARNOLD exercises now have proper muscle targeting data.

**Quick Start**:
```
1. Read this file (you're doing it)
2. Call arnold-memory:load_briefing (gets athlete context, goals, current block)
3. Check red flags: arnold-analytics:check_red_flags
4. Check recent journal entries: arnold-journal:get_recent_entries
```

**If you need more context**: Read `/docs/ARCHITECTURE.md` and the ADRs in `/docs/adr/`

---

## Current System State

### Architecture: Dual-Database (ADR-001 + ADR-002)

```
POSTGRES (Left Brain)                NEO4J (Right Brain)
Facts, Measurements, Time-series     Relationships, Semantics, Knowledge
─────────────────────────────────    ─────────────────────────────────
• strength_sessions (165 rows)       • Exercises → MovementPatterns → Muscles
• strength_sets (2,482 rows)         • Goals → Modalities → Blocks
• endurance_sessions                 • PlannedWorkout → PlannedBlock → PlannedSet
• log_entries (journal)              • StrengthWorkout refs (FK to Postgres)
• biometric_readings                 • Injuries → Constraints
• race_history                       • LogEntry → EXPLAINS → Workout
• neo4j_cache_exercise_muscles       • TARGETS relationships (source of truth)
• neo4j_cache_exercise_patterns      • INVOLVES relationships (source of truth)
```

**Key ADR-001 Insight**: Neo4j owns relationships. Postgres caches them for analytics JOINs.

### Exercise Data Quality (Jan 8, 2026)

| Metric | Neo4j | Postgres Cache |
|--------|-------|----------------|
| Total Exercises | 4,223 | — |
| With muscle targeting | 4,162 | 4,169 |
| With movement patterns | 4,100 | 4,100 |
| TARGETS relationships | 11,508 | 11,515 |
| INVOLVES relationships | 4,977 | 4,977 |

**Workout Coverage**:
- Pattern coverage: **97%** (194/200 exercises in workouts)
- Muscle coverage: **78%** (156/200 exercises in workouts)
- 44 exercises still need enrichment (batch_003 candidates)

### Exercise ID Schema (Post-Migration)

| Prefix | Count | Description |
|--------|-------|-------------|
| `CANONICAL:ARNOLD:*` | 116 | Arnold-created, 1,085 sets logged |
| `EXERCISE:*` | 57 | Free Exercise DB, 1,044 sets logged |
| `CANONICAL:FFDB:*` | 27 | Functional Fitness DB, 363 sets logged |
| `CUSTOM:*` | 0 | **All migrated** to CANONICAL:ARNOLD |

---

## Today's Session (January 7-8, 2026)

### Completed ✅

1. **Exercise Migration Cleanup**
   - Migrated 141 CUSTOM exercises to CANONICAL:ARNOLD
   - Merged 6 duplicates, promoted 5 exercises
   - **0 CUSTOM exercises remain**
   - All historical workout data preserved

2. **Batch 002 Enrichment**
   - 50 exercises enriched with Google AI Overview content
   - Muscles extracted and loaded into Neo4j TARGETS relationships
   - Source type: `google_ai_overview`
   - 1,020 new TARGETS relationships (362 primary, 658 secondary)

3. **ADR-001 Compliance Audit** ✅
   - Neo4j is source of truth: Confirmed
   - Postgres cache matches: Confirmed (within 7 rows)
   - Sync is one-way Neo4j→Postgres: Confirmed
   - Full refresh sync pattern: Confirmed

4. **Created Batch 003 Template**
   - `/data/enrichment/batches/batch_003.md` created with 44 exercises
   - Categories: mobility/stretches, warm-ups, compound lifts, specialty exercises
   - Ready for user to fill in Google AI Overview content

### Remaining Work

| Priority | Item | Notes |
|----------|------|-------|
| 1 | **Cleanup Tasks** | See section below - Stick Torso Twist + sync script |
| 2 | **Batch 003 Enrichment** | 44 exercises need muscle targeting (template ready) |
| 3 | Week 1 Planning | Plan remaining sessions for Accumulation block |
| 4 | Daily cron (#2) | Automate sync pipeline |

---

## Cleanup Tasks for Next Thread

### 1. Stick Torso Twist - Fix Audit Fields

The exercise was migrated manually but used wrong field names. Fix to match the established pattern from `migrate_custom_exercises.py`:

```cypher
MATCH (e:Exercise {id: 'CANONICAL:ARNOLD:STICK_TORSO_TWIST'})
SET e.source = 'arnold_promoted',
    e.promoted_from = e.migrated_from,
    e.promoted_at = e.created_at
REMOVE e.migrated_from
```

Optionally add to `data/enrichment/exercise_normalization_review.csv` for documentation:
```
EXERCISE:Stick_Torso_Twist,Stick Torso Twist,1,0,adhoc,,,,,PROMOTE_TO_CANONICAL,Manual migration Jan 8 2026
```

### 2. Sync Script Warning - Already Fixed

The warning about 6 stretches (Cat_Stretch, Childs_Pose, etc.) was because they had TARGETS but no INVOLVES relationships. `Mobility` pattern was added to all 6.

**Action needed**: Run `python scripts/sync_exercise_relationships.py` to update Postgres cache. The warning should disappear and pattern coverage should hit ~100%.

### 3. Batch 003 Ready for Processing

Template created at `/data/enrichment/batches/batch_003.md` with 44 exercises. After user fills in Google AI Overview content:

```bash
# Parse to JSON
python scripts/parse_exercises.py --batch 003

# Ingest to Neo4j
python scripts/ingest_exercise_enrichment.py

# Sync to Postgres cache
python scripts/sync_exercise_relationships.py
```

Query to verify remaining gaps:
```sql
WITH workout_exercises AS (
    SELECT DISTINCT exercise_id 
    FROM strength_sets 
    WHERE exercise_id IS NOT NULL
),
muscle_coverage AS (
    SELECT DISTINCT exercise_id 
    FROM neo4j_cache_exercise_muscles
)
SELECT we.exercise_id
FROM workout_exercises we
LEFT JOIN muscle_coverage mc ON we.exercise_id = mc.exercise_id
WHERE mc.exercise_id IS NULL
ORDER BY we.exercise_id;
```

**Batch 003 Candidates** (44 exercises missing muscle data):
```
Mobility/Stretches:
  Pigeon Pose, Wall Angels, Floor Angels, Thoracic Rotations,
  Thoracic Extensions, Supine Spinal Twist, Child Pose equivalent

Warm-up/Dynamic:
  Hip Hinge, Jumping Jack, Arm Swings, Spiderman Lunges,
  Dynamic Lunges, Active Hang, Single Leg Toe Touches

Compound Lifts:
  Sandbag Clean, Sandbag Zercher Squat, Sandbag Gator Roll,
  Wheelbarrow Carry, Burpee Dumbbell Deadlift, Chain Overhead Press

Specialty:
  Club Swinging, Landmine Anti-Rotation Press, Neural Floss,
  Rope Pulley Pull, Quad Raise, 90-90 Hip Switch
```

---

## Key Scripts & Commands

### Enrichment Pipeline
```bash
# Parse batch markdown → JSON (uses Claude API)
python scripts/parse_exercises.py --batch 003

# Ingest JSON → Neo4j TARGETS relationships
python scripts/ingest_exercise_enrichment.py

# Sync Neo4j → Postgres cache
python scripts/sync_exercise_relationships.py
```

### Import Muscle Data (Alternative)
```bash
# Smart ID resolution (handles CUSTOM→CANONICAL mapping)
python scripts/import_enrichment_muscles.py --dry-run
python scripts/import_enrichment_muscles.py
```

### Sync & Validation
```bash
# Full sync pipeline
python scripts/sync_pipeline.py

# Check muscle coverage
python scripts/import_enrichment_muscles.py --validate

# QC report
python scripts/sync_exercise_relationships.py
```

---

## MCP Roster (All Operational)

| MCP | Status | Purpose |
|-----|--------|---------|
| arnold-training | ✅ | Planning (Neo4j) + Execution/History (Postgres) |
| arnold-journal | ✅ | Subjective data + annotation tools |
| arnold-profile | ✅ | Profile, equipment, activities |
| arnold-memory | ✅ | Context, observations, semantic search |
| arnold-analytics | ✅ | Readiness, training load, red flags |
| neo4j-mcp | ✅ | Direct graph queries |
| postgres-mcp | ✅ | Direct SQL, health checks |
| github | ✅ | Issue tracking, repo management |

---

## ADR-001: Relationship Caching Pattern

```
Neo4j (source of truth)              Postgres (analytics cache)
┌──────────────────────┐            ┌────────────────────────────────┐
│ (Exercise)-[:TARGETS]│            │ neo4j_cache_exercise_muscles   │
│ ->(Muscle)           │───sync────►│ exercise_id, muscle_name, role │
│                      │            │ synced_at                      │
├──────────────────────┤            ├────────────────────────────────┤
│ (Exercise)-[:INVOLVES]            │ neo4j_cache_exercise_patterns  │
│ ->(MovementPattern)  │───sync────►│ exercise_id, pattern_name      │
│                      │            │ synced_at                      │
└──────────────────────┘            └────────────────────────────────┘
```

**Sync Characteristics:**
- One-way: Neo4j → Postgres only
- Full refresh: TRUNCATE + reload (not incremental)
- Triggered by: `sync_exercise_relationships.py`
- Script must run after any Neo4j TARGETS/INVOLVES changes

---

## Enrichment Sources

| Source | Type | Count | Description |
|--------|------|-------|-------------|
| `functional-fitness-db` | Import | 7,961 | Original import |
| `free-exercise-db` | Import | 2,527 | Original import |
| `google_ai_overview` | Enrichment | 1,020 | Batch 001 + 002 |

---

## Athlete Context (Brock)

- **Age**: 50 (turned 50 January 2, 2026)
- **Background**: 35 years martial arts, 18 years ultrarunning
- **Recent**: Knee surgery November 2025, cleared for normal activity
- **Goals**: Deadlift 405x5, Hellgate 100k, 10 ring dips by June 2026
- **Race history**: 114 races including 13 hundred-milers
- **Current Block**: Accumulation (Week 2 of 4, Dec 30 - Jan 26)
- **Philosophy**: Evidence-based, substance over engagement, Digital Twin vision

---

## Critical Notes for Future Claude

1. **ADR-001 + ADR-002 are law** — Postgres stores facts (executed workouts, measurements). Neo4j stores relationships and intentions (plans, goals, exercises). Postgres caches Neo4j relationships for analytics.

2. **CUSTOM exercises are gone** — All migrated to `CANONICAL:ARNOLD:*`. If you see CUSTOM IDs in old enrichment JSON files, they need ID mapping.

3. **Enrichment pipeline**:
   - Source: `data/enrichment/batches/batch_NNN.md` (Google AI Overview content)
   - Parse: `parse_exercises.py` → JSON in `data/enrichment/exercises/`
   - Ingest: `ingest_exercise_enrichment.py` → Neo4j TARGETS
   - Sync: `sync_exercise_relationships.py` → Postgres cache

4. **ID resolution** — `import_enrichment_muscles.py` has smart ID resolution that handles CUSTOM→CANONICAL mapping. Use it if `ingest_exercise_enrichment.py` fails.

5. **Workout coverage priority** — Only enrich exercises that appear in workouts. The 44 missing exercises are higher priority than the ~60 other CANONICAL:ARNOLD exercises without muscles.

6. **Analytics computes, Arnold synthesizes** — `check_red_flags()` returns observations + annotations without suppression. Arnold sees all data and decides what to surface.

7. **Post-surgery monitoring** — Knee surgery Nov 2025. Any knee-related journal entries should link to the injury.

8. **Ultrahuman is primary** for ring biometrics. Apple Health HRV uses different algorithm — not comparable.

---

## File Locations

```
/data/enrichment/
├── batches/
│   ├── batch_001.md          # 50 exercises (completed)
│   ├── batch_002.md          # 50 exercises (completed)
│   └── batch_003.md          # 44 exercises (template ready, needs content)
├── exercises/                 # Parsed JSON files
│   ├── kettlebell_swings.json
│   └── ...
└── schema_reference.json      # Muscle/pattern schema

/scripts/
├── parse_exercises.py         # Markdown → JSON (Claude API)
├── ingest_exercise_enrichment.py  # JSON → Neo4j
├── import_enrichment_muscles.py   # JSON → Neo4j (smart ID resolution)
└── sync_exercise_relationships.py # Neo4j → Postgres cache
```

---

## Open GitHub Issues

| # | Title | Priority |
|---|-------|----------|
| [#2](https://github.com/brockwebb/arnold/issues/2) | Set up daily cron for sync pipeline | Medium |
| [#3](https://github.com/brockwebb/arnold/issues/3) | Apple Health: skip Ultrahuman metrics | Low |
| [#8](https://github.com/brockwebb/arnold/issues/8) | Plan Templates Library | Medium |
| [#9](https://github.com/brockwebb/arnold/issues/9) | Email Integration (Future) | Low |

---

## Reference Documents

```
/docs/
├── ARCHITECTURE.md              # System architecture (ADR-001 details)
├── HANDOFF.md                   # This file
├── adr/
│   ├── 001-data-layer-separation.md   # Postgres vs Neo4j
│   └── 002-strength-workout-migration.md  # Strength to Postgres
└── mcps/

/src/
├── arnold-journal-mcp/
├── arnold-profile-mcp/
├── arnold-training-mcp/
├── arnold-memory-mcp/
└── arnold-analytics-mcp/
```
