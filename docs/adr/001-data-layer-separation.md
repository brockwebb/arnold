# ADR-001: Data Layer Separation — Postgres for Measurements, Neo4j for Relationships

**Date:** January 4, 2026  
**Status:** Accepted  
**Deciders:** Brock Webb, Claude (Arnold development)

## Context

Arnold ingests data from multiple sources:
- **Sensor data**: HRV, RHR, sleep stages, temperature (Ultrahuman Ring, Apple Health)
- **Session data**: Endurance workouts from FIT files (Suunto, Garmin, Wahoo)
- **Training data**: Strength workouts with exercises, sets, reps, loads
- **Medical data**: Lab results, medications, blood pressure, clinical records (FHIR)
- **Subjective data**: Journal entries, observations, annotations
- **Race history**: Historical competition results

Initially, we attempted to route FIT file imports through Neo4j first, then sync to Postgres. This felt wrong — we were forcing tabular time-series data into a graph structure.

## Decision

**Establish clear separation of concerns between the two databases:**

| Database | Responsibility | Data Characteristics |
|----------|---------------|---------------------|
| **Postgres** | Measurements, facts, time-series | Tabular, high-volume, analytical queries |
| **Neo4j** | Relationships, semantics, knowledge | Graph traversals, meaning, connections |

### Postgres is Source of Truth for:
- Biometric readings (HRV, RHR, sleep, temp, etc.)
- Endurance sessions and laps (FIT imports)
- HR samples (beat-by-beat if needed)
- Lab results and medical records
- Medications and supplements
- Race history
- Journal/log entries
- Annotations (for time-series queries)
- Potentially: strength sets (reps, weight, RPE) — TBD

### Neo4j is Source of Truth for:
- Person, Goals, Modalities, Blocks — training structure
- Exercises, MovementPatterns, Muscles — knowledge base
- Injuries, Constraints, Protocols — medical context
- Annotations (for relationship queries) — *dual storage*
- Lightweight workout references with FK to Postgres
- Any data where *relationships are the primary value*

### The Bridge Pattern

When data needs to exist in both systems:

```
Postgres (measurements)              Neo4j (relationships)
┌──────────────────────┐            ┌──────────────────────┐
│ endurance_sessions   │            │ (:EnduranceWorkout)  │
│ id: 12345            │◄──────────►│ postgres_id: 12345   │
│ date, distance, tss  │    FK      │ date (for queries)   │
│ duration, hr, pace   │            │ [:PERFORMED]->Person │
│ laps (full detail)   │            │ [:EXPLAINS]<-Annot   │
└──────────────────────┘            └──────────────────────┘
```

Neo4j holds enough to support graph queries and relationships. Postgres holds the full measurement detail.

## Rationale

### Why This Split?

1. **Play to each database's strengths**
   - Postgres: Columnar queries, aggregations, time-series, SQL analytics
   - Neo4j: Traversals, pattern matching, semantic relationships

2. **Data volume realities**
   - A single run can have 10,000+ HR samples
   - 18 years of race history = 114 flat records
   - Lab results, medications, journal entries = all tabular
   - Forcing this through Neo4j adds complexity with no benefit

3. **Query patterns differ**
   - "What was my average HRV last 30 days?" → Postgres
   - "What modalities does this goal require?" → Neo4j
   - "Show me all workouts affected by my knee injury" → Neo4j with FK to Postgres detail

4. **Apple Health XML is a red herring**
   - Looks hierarchical, actually just tabular records with XML syntax
   - Don't let the export format dictate the data model

### The "Right Brain / Left Brain" Analogy

- **Postgres (Left Brain)**: Facts, measurements, numbers, time, sequence
- **Neo4j (Right Brain)**: Meaning, connections, context, relationships

Both are essential. Neither can do the other's job well.

## Consequences

### Positive
- Cleaner architecture aligned with data characteristics
- Better performance for analytical queries (Postgres)
- Better performance for relationship queries (Neo4j)
- Simpler import pipelines (data goes to natural home)
- Easier to reason about where data lives

### Negative
- Some data needs FK references across systems
- Dual storage for some entities (annotations, workout refs)
- Need to maintain sync for cross-system references

### Migration Required
- Refactor FIT importer to go Postgres-first
- Create `endurance_sessions` and `endurance_laps` tables
- Create lightweight `(:EnduranceWorkout)` reference nodes in Neo4j
- Update sync pipeline accordingly
- Consider migrating strength workout sets to Postgres (future)

## Implementation

### New Postgres Tables

```sql
-- Endurance sessions (source of truth)
CREATE TABLE endurance_sessions (
    id SERIAL PRIMARY KEY,
    session_date DATE NOT NULL,
    sport VARCHAR(50),
    source VARCHAR(50),           -- 'suunto', 'garmin', 'polar'
    source_file VARCHAR(255),
    
    -- Core metrics
    distance_miles DECIMAL(6,2),
    duration_seconds INT,
    avg_pace VARCHAR(20),
    
    -- Heart rate
    avg_hr INT,
    max_hr INT,
    min_hr INT,
    
    -- Elevation
    elevation_gain_m INT,
    elevation_loss_m INT,
    
    -- Training load
    tss DECIMAL(5,1),
    training_effect DECIMAL(3,1),
    recovery_time_hours DECIMAL(4,1),
    
    -- Other
    calories INT,
    avg_cadence INT,
    
    -- Metadata
    imported_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(session_date, distance_miles, duration_seconds)
);

-- Lap splits
CREATE TABLE endurance_laps (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES endurance_sessions(id),
    lap_number INT,
    distance_miles DECIMAL(5,2),
    duration_seconds INT,
    pace VARCHAR(20),
    avg_hr INT,
    max_hr INT,
    avg_cadence INT,
    elevation_gain_m INT
);

CREATE INDEX idx_sessions_date ON endurance_sessions(session_date);
CREATE INDEX idx_laps_session ON endurance_laps(session_id);
```

### Neo4j Reference Node

```cypher
(:EnduranceWorkout {
    id: "uuid",
    postgres_id: 12345,           // FK to Postgres
    date: date("2026-01-04"),
    sport: "running",
    distance_miles: 10.01,        // Denormalized for graph queries
    tss: 140.3
})

// Relationships
(p:Person)-[:PERFORMED]->(ew:EnduranceWorkout)
(a:Annotation)-[:EXPLAINS]->(ew:EnduranceWorkout)
(ew:EnduranceWorkout)-[:AFFECTED_BY]->(i:Injury)
```

### Sync Direction

```
FIT files
    ↓
Postgres (endurance_sessions, endurance_laps)
    ↓
Neo4j (lightweight EnduranceWorkout reference)
```

## Related Decisions

- ADR-002 (future): Migrate strength workout sets to Postgres?
- ADR-003 (future): Journal/Log system architecture

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Master architecture document
- [DATA_DICTIONARY.md](../DATA_DICTIONARY.md) — Data source reference
