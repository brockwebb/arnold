# ADR-006: Unified Workout Schema — Segments + Sport-Specific Child Tables

**Date:** January 13, 2026  
**Status:** Accepted  
**Deciders:** Brock Webb, Claude, ChatGPT Health, Gemini 2.5 Pro

## Context

The current workout storage uses two tables:
- `strength_sessions` — sets, reps, load, RPE
- `endurance_sessions` — distance, pace, HR zones, TSS

This design is already showing strain:
1. **Doesn't scale** — What about rowing (strokes, 500m splits, drag factor), cycling (power, NP, IF), swimming (SWOLF, stroke count), climbing, martial arts, CrossFit?
2. **Can't represent multi-modal sessions** — A CrossFit WOD with rowing intervals, barbell work, and gymnastics is ONE workout, not three.
3. **N-tables problem** — Creating a new table per sport is brittle and requires migrations for every new activity.

The athlete (Brock) has 35 years of martial arts, 18 years of ultrarunning, and is rebuilding strength post-knee surgery. The system must handle diverse modalities over decades.

## Decision

Adopt a **segment-based model with sport-specific child tables** and a generic fallback.

### Architecture

```
workouts (core session record)
  └── segments (ordered modality blocks within a workout)
        ├── strength_sets (when sport_type = 'strength')
        ├── rowing_intervals (when sport_type = 'rowing')
        ├── running_intervals (when sport_type = 'running')
        ├── swimming_laps (when sport_type = 'swimming')
        ├── cycling_intervals (when sport_type = 'cycling')
        └── segment_events_generic (fallback for unmapped sports)
```

### Key Design Principles

1. **Segments solve multi-modal** — A workout is a sequence of ordered segments, each with its own sport_type. A brick workout (bike → run) is one workout with two segments.

2. **Sport-specific child tables for common modalities** — Strong typing, constraints, efficient indexing. Claude generates cleaner SQL against relational columns than JSONB paths.

3. **Generic fallback for unknown sports** — `segment_events_generic` uses (metric_name, metric_value, unit) pattern. Never blocked on a migration for a rare sport.

4. **Metric catalog for Claude navigation** — `metric_catalog` table maps metric names → tables → sport types. Claude reads this to know where to query.

5. **Promotion policy** — When a sport in generic table hits repeated use (X sessions or high query volume), promote to a dedicated table.

### Schema Highlights

**workouts** (core record):
- `workout_id`, `user_id`, `start_time`, `duration_seconds`
- `rpe`, `notes`, `source`, `source_fidelity`

**segments** (modality blocks):
- `segment_id`, `workout_id`, `seq` (order within workout)
- `sport_type` (discriminator)
- `duration_seconds`, `transition_seconds` (gap from previous segment)
- `planned_segment_id` (links to Neo4j plan for intent vs outcome)
- `extra` JSONB (rare/ad-hoc fields)

**strength_sets** (child of segment):
- `set_id`, `segment_id`, `seq`
- `exercise_id` (links to Neo4j exercise catalog)
- `reps`, `load`, `load_unit`, `rpe`
- `time_started`, `time_ended`, `rest_seconds`
- `failed`, `pain_scale` (rehab context)
- `is_warmup`, `tempo_code`
- `extra` JSONB

**segment_events_generic** (fallback):
- `segment_id`, `seq`, `metric_name`, `metric_value`, `metric_unit`
- `extra` JSONB

**metric_catalog** (Claude's navigation map):
- `metric_name`, `table_name`, `unit`, `sport_types[]`, `description`

### Query Patterns

| Query Type | Approach |
|------------|----------|
| "What did I do Tuesday?" | Query `workouts` + `segments` |
| "Show deadlift progression" | Query `strength_sets` joined to `segments` |
| "Weekly volume across all sports" | Query `v_all_activity_events` unified view |
| "HRR by sport type" | Query `segment_metrics` filtered by sport |
| "Log unknown sport" | Insert to `segment_events_generic` |

### Claude's Role

- **Reads `metric_catalog`** to know which metrics live in which tables
- **Generates SQL** against sport-specific tables for precision queries
- **Uses unified views** for cross-modal aggregations
- **Routes new sports** to generic table without blocking on migrations

## Alternatives Considered

### Option 1: Single Table + JSONB
```sql
workout_sessions (
  id, date, workout_type,
  sport_data JSONB  -- everything in a blob
)
```
**Rejected:** JSONB is opaque to SQL analytics. Every aggregation becomes client-side JSON parsing. Claude generates cleaner SQL against relational columns.

### Option 2: Pure Star Schema (EAV)
```sql
workouts (id, date)
workout_metrics (workout_id, metric_name, value, unit)
```
**Rejected:** Too many joins for simple queries. Loses type safety. Query complexity not worth the flexibility when sport-specific tables handle 95% of cases.

### Option 3: One Generic Child Table
```sql
segment_events (
  segment_id, event_type, seq,
  reps, load, distance, pace, strokes...  -- sparse columns
)
```
**Rejected:** Many NULLs, weak typing, poor indexing. Harder to enforce constraints. Messy over decades.

### Current State (Two Tables)
**Rejected:** Doesn't scale. Already failing with just strength + endurance.

## Consequences

### Positive
- **Multi-modal workouts** represented cleanly as segments
- **Type safety** for common sports via dedicated tables
- **Never blocked** on migrations for rare sports (generic fallback)
- **Claude-friendly** — relational columns over JSONB, catalog for navigation
- **Analytics-ready** — efficient indexing, materialized views for common queries
- **Decades-scale** — adding new sport = one DDL migration when justified

### Negative
- **More tables** to document and maintain
- **Joins required** for complete workout picture
- **Migration needed** to move from current two-table schema
- **Catalog discipline** required (metric names, units, versioning)

### Neutral
- Query complexity becomes Claude's problem, not user's
- Views solve fragmentation for cross-modal queries

## Implementation Plan

See Issue 013 for implementation details and migration plan.

## References

- ADR-001: Data Layer Separation (Postgres for facts, Neo4j for relationships)
- ADR-002: Strength Workout Migration (current schema)
- Consultation with ChatGPT Health and Gemini 2.5 Pro (January 2026)
- Open mHealth schemas, UCUM unit standards
