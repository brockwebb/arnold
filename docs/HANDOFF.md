# Arnold Project - Thread Handoff

> **Last Updated**: January 5, 2026 (ADR-002 Strength Migration Complete)
> **Previous Thread**: Journal System + ADR-002 Migration
> **Compactions in Previous Thread**: 1

---

## New Thread Start Here

**Context**: Arnold is an AI-native fitness coaching system with a dual-database architecture. **ADR-002 Strength Workout Migration** was just completed — executed workouts now live in Postgres while plans stay in Neo4j.

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
```

**Key Insight**: Plans are intentions (Neo4j). Executions are facts (Postgres).

### MCP Roster (All Operational)

| MCP | Status | Purpose |
|-----|--------|---------|
| arnold-training | ✅ **UPDATED** | Planning (Neo4j) + Execution/History (Postgres) |
| arnold-journal | ✅ | Subjective data capture + relationship linking |
| arnold-profile | ✅ | Profile, equipment, activities |
| arnold-memory | ✅ | Context, observations, semantic search |
| arnold-analytics | ✅ | Readiness, training load, red flags |
| neo4j-mcp | ✅ | Direct graph queries |
| postgres-mcp | ✅ | Direct SQL, health checks |
| github | ✅ | Issue tracking, repo management |

### Database Inventory

**Postgres (`arnold_analytics`)**:
| Table | Rows | Description |
|-------|------|-------------|
| `strength_sessions` | 165 | **ADR-002: Executed strength workouts** |
| `strength_sets` | 2,482 | **ADR-002: Individual sets with load/reps** |
| `log_entries` | 2+ | Journal entries (facts) |
| `endurance_sessions` | 1 | FIT imports (runs, rides) |
| `endurance_laps` | 10 | Per-lap splits |
| `biometric_readings` | 2,885 | HRV, RHR, sleep, temp |
| `race_history` | 114 | 18 years of races |
| `hr_samples` | 167,670 | Beat-by-beat HR |
| `data_annotations` | 4 | Context for data gaps |

**Neo4j (`arnold`)**:
- 4,242 exercises with movement patterns
- 165 StrengthWorkout reference nodes (FK to Postgres)
- PlannedWorkout nodes with PlannedBlock/PlannedSet structure
- Training plans, goals, injuries, constraints
- LogEntry nodes with relationship links

---

## Today's Session (January 5, 2026)

### Completed ✅

1. **ADR-002: Strength Workout Migration** 🎉
   - Created migration 010 schema (`strength_sessions`, `strength_sets`)
   - Migrated 165 sessions, 2,482 sets from Neo4j to Postgres
   - Created `StrengthWorkout` reference nodes in Neo4j (100% bidirectional links)
   - Built `postgres_client.py` with full CRUD operations
   - Refactored `server.py` — history reads from Postgres, execution writes to Postgres
   - Verified end-to-end: `get_recent_workouts` and `get_workout_by_date` now use Postgres
   - `get_coach_briefing` is hybrid: goals/block from Neo4j, workouts from Postgres

2. **Previous Session (Jan 4-5)**:
   - ADR-001: Data Layer Separation (documented)
   - Migration 008: Endurance Sessions
   - Migration 009: Journal System (17 MCP tools)
   - Logged 10.01mi run + first journal entries

### Key Files Created/Modified This Session

| File | Purpose |
|------|---------|
| `scripts/migrations/010_strength_workouts.sql` | Strength tables + helper functions |
| `scripts/migrate_strength_workouts.py` | Data migration script |
| `src/arnold-training-mcp/.../postgres_client.py` | **NEW**: Postgres operations |
| `src/arnold-training-mcp/.../server.py` | **UPDATED**: ADR-002 compliant |

---

## ADR-002 Architecture

### The Split

```
PLANNING (Neo4j)                    EXECUTION (Postgres)
────────────────                    ──────────────────
PlannedWorkout                      strength_sessions
  └─ PlannedBlock                     └─ strength_sets
       └─ PlannedSet                       (exercise_id, reps, load, RPE)
            └─ [:PRESCRIBES]→Exercise

When completed:
  PlannedWorkout.status = 'completed'
  StrengthWorkout ref created → postgres_id
  strength_sessions row created with all sets
```

### Tool Routing

| Tool | Database | Operation |
|------|----------|-----------|
| `create_workout_plan` | Neo4j | Create PlannedWorkout |
| `get_plan_for_date` | Neo4j | Read PlannedWorkout |
| `complete_as_written` | Both | Read Neo4j plan → Write Postgres session |
| `complete_with_deviations` | Both | Read Neo4j plan → Write Postgres with deviations |
| `log_workout` | Both | Write Postgres → Create Neo4j ref |
| `get_recent_workouts` | **Postgres** | Read strength_sessions |
| `get_workout_by_date` | **Postgres** | Read strength_sessions + sets |
| `get_coach_briefing` | **Both** | Neo4j context + Postgres workouts |

### Helper Functions (Postgres)

```sql
-- Get exercise progression with estimated 1RM
SELECT * FROM exercise_history('EXERCISE:Barbell_Deadlift', 365);

-- Get personal records
SELECT * FROM exercise_pr('EXERCISE:Barbell_Deadlift');

-- Weekly volume aggregates
SELECT * FROM weekly_strength_volume;
```

---

## Next Priorities

| Priority | Item | Notes |
|----------|------|-------|
| 1 | **Week 1 Planning** | Plan remaining sessions for Accumulation block |
| 2 | Daily cron (#2) | Automate sync pipeline |
| 3 | Plan Templates (#8) | Library of workout templates |
| 4 | Email Integration (#9) | Journal entries via email |

---

## Open GitHub Issues

| # | Title | Priority |
|---|-------|----------|
| [#2](https://github.com/brockwebb/arnold/issues/2) | Set up daily cron for sync pipeline | Medium |
| [#3](https://github.com/brockwebb/arnold/issues/3) | Apple Health: skip Ultrahuman metrics | Low |
| [#8](https://github.com/brockwebb/arnold/issues/8) | Plan Templates Library | Medium |
| [#9](https://github.com/brockwebb/arnold/issues/9) | Email Integration (Future) | Low |

**Recently Closed:**
- #4 ✅ HRV algorithm discrepancy
- #5 ✅ Coach Brief Report System
- #6 ✅ Data Annotation System
- #7 ✅ Journal System

---

## Athlete Context (Brock)

- **Age**: 50 (turned 50 January 2, 2026)
- **Background**: 35 years martial arts, 18 years ultrarunning
- **Recent**: Knee surgery November 2025, cleared for normal activity
- **Goals**: Deadlift 405x5, Hellgate 100k, 10 ring dips by June 2026
- **Race history**: 114 races including 13 hundred-milers
- **Current Block**: Accumulation (Week 1 of 4, Dec 30 - Jan 26)
- **Philosophy**: Evidence-based, substance over engagement, Digital Twin vision

---

## Critical Notes for Future Claude

1. **ADR-001 + ADR-002 are law** — Postgres stores facts (executed workouts, measurements). Neo4j stores relationships and intentions (plans, goals, exercises). Read the ADRs before architectural decisions.

2. **Strength workouts are in Postgres** — Don't query Neo4j for workout history. Use `get_recent_workouts` or `get_workout_by_date` which read from `strength_sessions`.

3. **StrengthWorkout refs in Neo4j** — Lightweight reference nodes exist for graph traversal (linking journal entries, injuries). They contain `postgres_id` FK, not the actual data.

4. **Plans stay in Neo4j** — PlannedWorkout, PlannedBlock, PlannedSet are prescriptive. They don't move to Postgres until executed.

5. **Journal entries are dual-stored** — Facts in Postgres (`log_entries`), relationships in Neo4j (`LogEntry` nodes). Always create both.

6. **Post-surgery monitoring** — Knee surgery Nov 2025. Any knee-related journal entries should link to the injury.

7. **Ultrahuman is primary** for ring biometrics. Apple Health HRV uses different algorithm — not comparable.

8. **Sync pipeline** — Use `python scripts/sync_pipeline.py`, not individual scripts.

---

## Common Commands

```bash
# Daily sync
python scripts/sync_pipeline.py

# Strength workout queries (Postgres)
psql arnold_analytics -c "SELECT * FROM strength_sessions ORDER BY session_date DESC LIMIT 5;"
psql arnold_analytics -c "SELECT * FROM exercise_history('EXERCISE:Barbell_Deadlift', 365);"
psql arnold_analytics -c "SELECT * FROM weekly_strength_volume;"

# Journal queries
psql arnold_analytics -c "SELECT * FROM recent_log_entries(7);"
psql arnold_analytics -c "SELECT * FROM unreviewed_entries();"

# Endurance queries  
psql arnold_analytics -c "SELECT * FROM recent_endurance_sessions(14);"

# Import FIT files
python scripts/import_fit_workouts.py

# Check system health
psql arnold_analytics -c "SELECT * FROM daily_status ORDER BY date DESC LIMIT 5;"
```

---

## Reference Documents

```
/docs/
├── ARCHITECTURE.md              # System architecture
├── HANDOFF.md                   # This file
├── adr/
│   ├── 001-data-layer-separation.md   # Postgres vs Neo4j
│   └── 002-strength-workout-migration.md  # Strength to Postgres
├── issues/
│   └── 003-postgres-analytics-layer.md
└── mcps/

/src/
├── arnold-journal-mcp/          # Journal system
├── arnold-profile-mcp/
├── arnold-training-mcp/         # UPDATED for ADR-002
│   └── arnold_training_mcp/
│       ├── server.py            # Tool handlers
│       ├── neo4j_client.py      # Graph operations
│       └── postgres_client.py   # NEW: Postgres operations
├── arnold-memory-mcp/
└── arnold-analytics-mcp/

/scripts/
├── migrations/
│   ├── 008_endurance_sessions.sql
│   ├── 009_journal_system.sql
│   └── 010_strength_workouts.sql  # NEW
└── migrate_strength_workouts.py   # NEW
```
