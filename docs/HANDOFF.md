# Arnold Project - Thread Handoff

> **Last Updated**: January 4, 2026 (Journal System Complete)
> **Previous Thread**: ADR-001 Data Layer Separation + Journal System
> **Compactions in Previous Thread**: 0

---

## New Thread Start Here

**Context**: Arnold is an AI-native fitness coaching system with a dual-database architecture. The **Journal System** was just completed, enabling subjective data capture with automatic graph-based relationship linking.

**Quick Start**:
```
1. Read this file (you're doing it)
2. Call arnold-memory:load_briefing (gets athlete context, goals, current block)
3. Check recent journal entries: arnold-journal:get_recent_entries
4. Check red flags: arnold-analytics:check_red_flags
```

**If you need more context**: Read `/docs/ARCHITECTURE.md` and the ADRs in `/docs/adr/`

---

## Current System State

### Architecture: Dual-Database (ADR-001)

```
POSTGRES (Left Brain)                NEO4J (Right Brain)
Facts, Measurements, Time-series     Relationships, Semantics, Knowledge
─────────────────────────────────    ─────────────────────────────────
• biometric_readings                 • Exercises → MovementPatterns → Muscles
• endurance_sessions                 • Goals → Modalities → Blocks
• log_entries (journal)              • Injuries → Constraints
• strength_sets (future ADR-002)     • LogEntry → EXPLAINS → Workout
• race_history                       • LogEntry → RELATED_TO → Injury
```

**Key Insight**: Plans are intentions (Neo4j). Executions are facts (Postgres).

### MCP Roster (All Operational)

| MCP | Status | Purpose |
|-----|--------|---------|
| **arnold-journal** | ✅ NEW | Subjective data capture + relationship linking |
| arnold-profile | ✅ | Profile, equipment, activities |
| arnold-training | ✅ | Planning, logging, execution |
| arnold-memory | ✅ | Context, observations, semantic search |
| arnold-analytics | ✅ | Readiness, training load, red flags |
| neo4j-mcp | ✅ | Direct graph queries |
| postgres-mcp | ✅ | Direct SQL, health checks |
| github | ✅ | Issue tracking, repo management |

### Database Inventory

**Postgres (`arnold_analytics`)**:
| Table | Rows | Description |
|-------|------|-------------|
| `log_entries` | 2 | **NEW: Journal entries (facts)** |
| `endurance_sessions` | 1 | FIT imports (runs, rides) |
| `endurance_laps` | 10 | Per-lap splits |
| `biometric_readings` | 2,885 | HRV, RHR, sleep, temp |
| `workout_summaries` | 165 | Denormalized strength workouts |
| `race_history` | 114 | 18 years of races |
| `hr_samples` | 167,670 | Beat-by-beat HR |
| `data_annotations` | 4 | Context for data gaps |

**Neo4j (`arnold`)**:
- 4,242 exercises with movement patterns
- 165+ workouts with block/set structure  
- LogEntry nodes with relationship links
- Training plans, goals, injuries, constraints

---

## Today's Session (January 4-5, 2026)

### Completed ✅

1. **ADR-001: Data Layer Separation**
   - Postgres = measurements, facts, time-series (LEFT BRAIN)
   - Neo4j = relationships, semantics, knowledge (RIGHT BRAIN)
   - See `/docs/adr/001-data-layer-separation.md`

2. **ADR-002: Strength Workout Migration** (documented, pending implementation)
   - Plans stay in Neo4j (prescriptive)
   - Executed sets move to Postgres (descriptive)
   - See `/docs/adr/002-strength-workout-migration.md`

3. **Migration 008: Endurance Sessions**
   - `endurance_sessions` and `endurance_laps` tables
   - FIT importer refactored to Postgres-first
   - Lightweight `EnduranceWorkout` reference nodes in Neo4j

4. **Migration 009: Journal System** 🎉
   - `log_entries` table in Postgres (facts)
   - `LogEntry` nodes in Neo4j (relationships)
   - 17 MCP tools for full CRUD + relationship management
   - **Automatic linking**: Mention "right knee" → links to knee surgery injury

5. **Logged 10.01mi run** (2026-01-04)
   - Postgres: `endurance_sessions.id = 1`
   - Neo4j: `EnduranceWorkout` with postgres_id reference

6. **First journal entries**
   - Entry #1: Leg soreness (DOMS) → EXPLAINS workout
   - Entry #2: Right knee stiffness → EXPLAINS workout + RELATED_TO injury

### Key Files Created This Session

| File | Purpose |
|------|---------|
| `docs/adr/001-data-layer-separation.md` | Postgres vs Neo4j responsibilities |
| `docs/adr/002-strength-workout-migration.md` | Planned migration for strength data |
| `scripts/migrations/008_endurance_sessions.sql` | Endurance tables |
| `scripts/migrations/009_journal_system.sql` | Journal tables |
| `src/arnold-journal-mcp/` | Complete MCP with 17 tools |

---

## Journal System Overview

The journal captures **subjective data that sensors can't measure**:
- Fatigue, soreness, energy levels
- Symptoms (pain, dizziness, numbness)
- Nutrition, hydration, caffeine
- Supplements, medications
- Workout feedback
- Mood, stress, mental state

### Architecture

```
User: "My right knee feels stiff from yesterday's run"
                    ↓
            Claude extracts:
            - symptom: stiffness
            - location: right knee  
            - cause: running
            - severity: notable
                    ↓
    ┌───────────────┴───────────────┐
    ↓                               ↓
POSTGRES (facts)              NEO4J (relationships)
log_entries                   (:LogEntry)
  id: 2                         ↓
  raw_text: "..."           -[:EXPLAINS]→ (:EnduranceWorkout)
  extracted: {...}          -[:RELATED_TO]→ (:Injury {name: "right_knee_meniscus"})
  severity: notable
```

### Key Tools

| Tool | Purpose |
|------|---------|
| `log_entry` | Create entry (Postgres + Neo4j) |
| `link_to_workout` | Entry EXPLAINS a workout |
| `link_to_injury` | Entry RELATED_TO an injury |
| `link_to_plan` | Entry AFFECTS a future plan |
| `link_to_goal` | Entry INFORMS a goal |
| `get_recent_entries` | Last N days of entries |
| `get_entries_for_workout` | All entries explaining a workout |

---

## Next Priorities

| Priority | Item | Notes |
|----------|------|-------|
| 1 | **ADR-002 Implementation** | Migrate strength sets to Postgres |
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
- #7 ✅ **Journal System** (just completed!)

---

## Athlete Context (Brock)

- **Age**: 50 (turned 50 January 2, 2026)
- **Background**: 35 years martial arts, 18 years ultrarunning
- **Recent**: Knee surgery November 2025, cleared for normal activity
- **Goals**: Deadlift 405x5, Hellgate 100k, 10 ring dips by June 2026
- **Race history**: 114 races including 13 hundred-milers
- **Philosophy**: Evidence-based, substance over engagement, Digital Twin vision

---

## Critical Notes for Future Claude

1. **ADR-001 is law** - Postgres stores facts, Neo4j stores relationships. Read the ADR before architectural decisions.

2. **Journal entries are dual-stored** - Facts in Postgres (`log_entries`), relationships in Neo4j (`LogEntry` nodes). Always create both.

3. **Graph linking is automatic** - When user mentions body parts, symptoms, or workouts, check for existing entities to link.

4. **Plans vs Executions** - Plans are prescriptive (Neo4j), executions are descriptive (Postgres). Different databases.

5. **Post-surgery monitoring** - Knee surgery Nov 2025. Any knee-related journal entries should link to the injury.

6. **Ultrahuman is primary** for ring biometrics. Apple Health HRV uses different algorithm — not comparable.

7. **Sync pipeline** - Use `python scripts/sync_pipeline.py`, not individual scripts.

---

## Common Commands

```bash
# Daily sync
python scripts/sync_pipeline.py

# Journal queries
psql arnold_analytics -c "SELECT * FROM recent_log_entries(7);"
psql arnold_analytics -c "SELECT * FROM unreviewed_entries();"
psql arnold_analytics -c "SELECT * FROM entries_by_severity('notable');"

# Endurance queries  
psql arnold_analytics -c "SELECT * FROM recent_endurance_sessions(14);"

# Import FIT files
python scripts/import_fit_workouts.py

# Generate coach brief
python scripts/reports/generate_coach_brief.py

# Check system health
psql arnold_analytics -c "SELECT * FROM daily_status ORDER BY date DESC LIMIT 5;"
```

---

## Reference Documents

```
/docs/
├── ARCHITECTURE.md              # System architecture (update pending)
├── HANDOFF.md                   # This file
├── adr/
│   ├── 001-data-layer-separation.md   # Postgres vs Neo4j
│   └── 002-strength-workout-migration.md  # Planned migration
├── issues/
│   └── 003-postgres-analytics-layer.md
└── mcps/

/src/
├── arnold-journal-mcp/          # NEW: Journal system
├── arnold-profile-mcp/
├── arnold-training-mcp/
├── arnold-memory-mcp/
└── arnold-analytics-mcp/
```
