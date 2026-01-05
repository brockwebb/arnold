# ADR-002: Migrate Strength Workouts to Postgres-First Architecture

**Date:** January 5, 2026  
**Status:** ✅ Implemented  
**Deciders:** Brock Webb, Claude (Arnold development)  
**Depends On:** ADR-001 (Data Layer Separation)

## Implementation Summary (January 5, 2026)

Migration completed with:
- **165 sessions** migrated to `strength_sessions`
- **2,482 sets** migrated to `strength_sets`
- **165 StrengthWorkout** reference nodes created in Neo4j
- **arnold-training-mcp** refactored to read/write Postgres for executed workouts
- Neo4j retained for plans, exercises, and relationship queries

## Context

ADR-001 established the principle: **Postgres for measurements, Neo4j for relationships.**

Currently, strength workouts violate this principle:
- Full workout structure lives in Neo4j: `(Workout)-[:HAS_BLOCK]->(WorkoutBlock)-[:CONTAINS]->(Set)-[:OF_EXERCISE]->(Exercise)`
- A lossy `workout_summaries` materialized view syncs to Postgres for analytics
- Sets are embedded in a graph structure when they're fundamentally tabular measurements

This creates friction:
1. **Lossy denormalization** — exercises stored as JSONB blob in `workout_summaries`
2. **Query limitations** — can't easily ask "all sets where RPE > 8" or "deadlift volume by week"
3. **Sync maintenance** — neo4j→postgres sync script must be maintained
4. **Inconsistency** — endurance workouts are Postgres-first (per ADR-001), strength workouts are not

## Decision

**Migrate strength workouts to follow the same Postgres-first pattern as endurance workouts.**

### Postgres Schema (Source of Truth)

```sql
-- Strength training sessions
CREATE TABLE strength_sessions (
    id SERIAL PRIMARY KEY,
    session_date DATE NOT NULL,
    session_time TIME,
    name VARCHAR(255),                        -- "Lower Body - Deadlift Focus"
    
    -- Training context
    block_id VARCHAR(100),                    -- FK to Neo4j Block (training phase)
    plan_id VARCHAR(100),                     -- FK to Neo4j PlannedWorkout (if from plan)
    
    -- Session metrics
    duration_minutes INT,
    total_volume_lbs DECIMAL(10,1),          -- Calculated: SUM(reps * weight)
    total_sets INT,
    avg_rpe DECIMAL(3,1),
    
    -- Subjective
    rpe_session INT CHECK (rpe_session BETWEEN 1 AND 10),
    notes TEXT,
    tags TEXT[],
    
    -- Execution tracking
    status VARCHAR(20) DEFAULT 'completed',   -- 'completed', 'partial', 'skipped'
    deviation_notes TEXT,                     -- If deviated from plan
    
    -- Metadata
    source VARCHAR(50) DEFAULT 'logged',      -- 'logged', 'from_plan', 'imported'
    neo4j_id VARCHAR(100),                    -- Reference to Neo4j node
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Individual sets (the actual measurements)
CREATE TABLE strength_sets (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES strength_sessions(id) ON DELETE CASCADE,
    
    -- Position in workout
    block_name VARCHAR(100),                  -- "Warm-Up", "Main Work", "Accessory"
    block_type VARCHAR(50),                   -- 'warmup', 'main', 'accessory', 'finisher'
    set_order INT NOT NULL,                   -- Order within session
    
    -- Exercise reference (FK to Neo4j Exercise node)
    exercise_id VARCHAR(100) NOT NULL,        -- Neo4j Exercise.id
    exercise_name VARCHAR(255) NOT NULL,      -- Denormalized for query convenience
    
    -- Prescription (if from plan)
    prescribed_reps INT,
    prescribed_load_lbs DECIMAL(6,1),
    prescribed_rpe INT,
    
    -- Actual execution
    actual_reps INT,
    actual_load_lbs DECIMAL(6,1),
    actual_rpe INT,
    
    -- Convenience (use actual if present, else prescribed)
    reps INT GENERATED ALWAYS AS (COALESCE(actual_reps, prescribed_reps)) STORED,
    load_lbs DECIMAL(6,1) GENERATED ALWAYS AS (COALESCE(actual_load_lbs, prescribed_load_lbs)) STORED,
    rpe INT GENERATED ALWAYS AS (COALESCE(actual_rpe, prescribed_rpe)) STORED,
    
    -- Set metadata
    set_type VARCHAR(50),                     -- 'working', 'warmup', 'backoff', 'amrap'
    tempo VARCHAR(20),                        -- "3-1-2-0" (eccentric-pause-concentric-pause)
    rest_seconds INT,
    
    -- Deviation tracking
    deviation_reason VARCHAR(50),             -- 'fatigue', 'pain', 'equipment', 'time'
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_strength_sessions_date ON strength_sessions(session_date);
CREATE INDEX idx_strength_sets_session ON strength_sets(session_id);
CREATE INDEX idx_strength_sets_exercise ON strength_sets(exercise_id);
CREATE INDEX idx_strength_sets_exercise_name ON strength_sets(exercise_name);
```

### Neo4j Structure (Relationships Only)

```cypher
// Lightweight reference node
(:StrengthWorkout {
    id: "uuid",
    postgres_id: 123,                 // FK to Postgres
    date: date("2026-01-03"),
    name: "Lower Body - Deadlift Focus"
})

// Relationships preserved
(p:Person)-[:PERFORMED]->(sw:StrengthWorkout)
(sw:StrengthWorkout)-[:IN_BLOCK]->(b:Block)
(sw:StrengthWorkout)-[:TOWARD]->(g:Goal)
(a:Annotation)-[:EXPLAINS]->(sw:StrengthWorkout)
(sw:StrengthWorkout)-[:AFFECTED_BY]->(i:Injury)

// Exercise ontology unchanged
(:Exercise)-[:HAS_PATTERN]->(:MovementPattern)
(:Exercise)-[:TARGETS]->(:Muscle)

// Plans remain in Neo4j (they're prescriptive, not measurements)
(:PlannedWorkout)-[:HAS_BLOCK]->(:PlannedBlock)-[:PRESCRIBES]->(:PlannedSet)
```

### What Stays in Neo4j

| Entity | Reason |
|--------|--------|
| Exercise ontology | Knowledge graph (patterns, muscles, constraints) |
| Goals, Modalities | Relationships define training structure |
| Blocks (training phases) | Relationships to goals, periodization context |
| Injuries, Constraints | Affect exercise selection (graph queries) |
| PlannedWorkouts | Prescriptions, not measurements (debatable — could migrate) |
| Annotations | Explain relationships between entities |
| Lightweight workout refs | Bridge to Postgres detail |

### What Moves to Postgres

| Entity | Reason |
|--------|--------|
| Executed sessions | Tabular: date, duration, volume |
| Executed sets | Tabular: reps, weight, RPE measurements |
| Deviation tracking | Facts about what happened |

## Consequences

### Positive

- **Consistent architecture** — all workout types follow same pattern
- **Better analytics** — direct SQL for progression, volume, trends
- **Eliminate sync script** — no more neo4j→workout_summaries pipeline
- **Richer queries** — "sets where actual_rpe > prescribed_rpe + 1"
- **Single source of truth** — no denormalization drift

### Negative

- **MCP refactor required** — `arnold-training-mcp` tools need updating
- **Migration complexity** — 165 existing workouts need migration
- **Cross-DB joins** — exercise details require Neo4j lookup (but exercise_name denormalized)

### Migration Scope

1. **Schema migration** — Create `strength_sessions` and `strength_sets` tables
2. **Data migration** — Export Neo4j workouts → import to Postgres
3. **MCP refactor** — Update these tools in `arnold-training-mcp`:
   - `create_workout_plan` — keep in Neo4j (prescriptions) or migrate?
   - `confirm_plan` — creates execution record in Postgres
   - `complete_as_written` — writes to Postgres
   - `complete_with_deviations` — writes to Postgres with deviation tracking
   - `log_workout` — writes to Postgres
   - `get_workout_by_date` — reads from Postgres
   - `get_recent_workouts` — reads from Postgres
4. **Create Neo4j references** — lightweight StrengthWorkout nodes with postgres_id
5. **Deprecate sync** — remove workout_summaries materialized view (or keep as backup)
6. **Update analytics** — queries now hit strength_sets directly

## Implementation Order

1. ✅ ADR-001: Data Layer Separation (complete)
2. ✅ Migration 008: endurance_sessions (complete)
3. 🔲 Journal System (#7) — Postgres-first from start
4. 🔲 **ADR-002: This migration**
5. 🔲 Deprecate workout_summaries

## Design Decisions

### PlannedWorkouts Stay in Neo4j (Resolved)

The prescriptive/descriptive split is the key insight:

| Concept | Nature | Home |
|---------|--------|------|
| Plan | Prescriptive — what *should* happen | Neo4j |
| Execution | Descriptive — what *did* happen | Postgres |

Plans are semantic structures:
- "Do 5x5 back squat at 80% 1RM" — prescription, not measurement
- Rich relationships: `(Plan)-[:SERVES]->(Goal)`, `(Plan)-[:PART_OF]->(Block)`
- "What plans target hip hinge this week?" — graph traversal
- Templates, progressions, periodization logic — knowledge domain

The clean flow:
```
NEO4J                                 POSTGRES
┌─────────────────────┐              ┌─────────────────────┐
│ (:PlannedWorkout)   │              │                     │
│   prescribed_sets   │──execute───► │ strength_sessions   │
│   -[:SERVES]->Goal  │              │ strength_sets       │
│   -[:PART_OF]->Block│              │   actual reps/weight│
│                     │              │   deviations        │
│ (intention)         │◄──reference──│   neo4j_plan_id     │
└─────────────────────┘              └─────────────────────┘
```

Prescribed sets within a plan stay embedded in Neo4j (JSONB or child nodes) because:
1. They're part of the template, not measurements
2. They change together with the plan (atomic)
3. Low volume (dozens, not thousands)
4. Avoids cross-database joins during planning

**Summary: Plans are intentions. Executions are facts. Different databases.**

## Open Questions

1. **Keep workout_summaries as backup?** During transition, could maintain both. Drop once confident.

2. **Exercise name denormalization** — storing `exercise_name` in sets avoids Neo4j lookup for basic queries. Acceptable redundancy?

## References

- [ADR-001: Data Layer Separation](001-data-layer-separation.md)
- [GitHub Issue #7: Journal System](https://github.com/brockwebb/arnold/issues/7)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
