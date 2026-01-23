# ADR-007: Simplified Workout Schema

**Date:** January 20, 2026  
**Status:** Accepted  
**Supersedes:** ADR-006 (Unified Workout Schema)  
**Deciders:** Brock Webb, Claude

## Context

ADR-006 introduced a segment-based model with sport-specific child tables to handle multi-modal workouts. After implementation, we discovered:

1. **95% of workouts are strength training** — The elaborate sport-discriminator pattern solves a problem we don't have.
2. **"Segment" conflated two concepts** — Sport modality (strength vs running) and training phase (warmup vs main) are orthogonal. Merging them into segment_type lost both meanings.
3. **Deviation capture at logging time = friction** — Forcing users to explain deviations during workout completion interrupted flow.
4. **Child table joins added complexity without benefit** — For a single-sport system, the discriminator pattern is pure overhead.
5. **"v2" naming is technical debt** — Shipping with temporary names (workouts_v2, v2_strength_sets) created confusion.

## Decision

Simplify to three tables with clean naming and nullable columns for different modalities.

### Schema

```
workouts (session)
  └── blocks (container - training phase)
        └── sets (atomic unit - all modalities)
```

**workouts** — Core session record:
- `workout_id`, `start_time`, `end_time`, `duration_minutes`
- `session_rpe`, `sport_type`, `purpose`, `notes`, `source`
- `plan_id` (links to Neo4j PlannedWorkout)
- `extra` JSONB

**blocks** — Training phase containers:
- `block_id`, `workout_id`, `seq`
- `block_type` (warmup | main | accessory | conditioning | cooldown | circuit | emom | skill)
- `modality` (optional override of workout.sport_type)
- `name`, `rounds`, `work_s`, `rest_s`, `notes`
- `extra` JSONB

**sets** — Atomic execution units (unified across modalities):
- `set_id`, `block_id`, `seq`, `exercise_id`, `exercise_name`
- `planned_set_id` (FK to planned_sets for deviation tracking)
- Strength: `reps`, `load`, `load_unit`, `rpe`
- Endurance: `distance`, `distance_unit`, `duration_s`, `pace`, `hr_avg`, `hr_zone`
- Conditioning: `calories`
- `notes`, `extra` JSONB

### Key Design Principles

1. **One sets table** — Nullable columns for different modalities. NULL storage cost is negligible; join complexity is not.

2. **Block type ≠ modality** — These are orthogonal:
   - `block_type` = training phase (warmup, main, accessory)
   - `modality` = sport (strength, running, cycling)
   
3. **Deviation tracking is computed** — Compare executed sets against planned sets via view, not forced at logging time.

4. **Keep extra JSONB** — Escape hatch for truly ad-hoc fields. Quarterly audit promotes frequent keys to real columns.

5. **Clean naming** — No "v2" prefixes. Tables are: `workouts`, `blocks`, `sets`.

## Deviation Tracking

Instead of forcing users to explain deviations during logging:

```sql
CREATE VIEW execution_vs_plan AS
SELECT 
  s.set_id, s.exercise_name,
  s.reps AS actual_reps, s.load AS actual_load,
  ps.prescribed_reps AS planned_reps, ps.prescribed_load_lbs AS planned_load,
  CASE
    WHEN s.reps IS NULL AND ps.prescribed_reps IS NOT NULL THEN 'skipped'
    WHEN s.reps IS NOT NULL AND ps.prescribed_reps IS NULL THEN 'added'
    WHEN ABS(s.reps - ps.prescribed_reps) > 2 THEN 'reps_deviation'
    WHEN ABS(s.load - ps.prescribed_load_lbs) > 10 THEN 'load_deviation'
    ELSE 'as_planned'
  END AS deviation_type
FROM sets s
LEFT JOIN planned_sets ps ON s.planned_set_id = ps.id;
```

Human "why" explanations go to Neo4j relationships when volunteered, not forced at logging.

## Alternatives Considered

### Keep ADR-006 Design
**Rejected:** Over-engineered for actual use case. 95% strength workouts don't need sport discriminators.

### Pure JSONB for Sets
**Rejected:** Claude generates cleaner SQL against relational columns. JSONB requires client-side parsing for analytics.

### Separate Tables Per Modality  
**Rejected:** Already tried in ADR-006. Joins and discriminator logic add complexity without benefit.

## Consequences

### Positive
- **Simpler queries** — No discriminator joins for the 95% case
- **Clean naming** — No "v2" technical debt
- **Reduced friction** — Deviation capture doesn't interrupt logging
- **Maintainable** — Three tables, clear hierarchy
- **Flexible enough** — Nullable columns handle different modalities when needed

### Negative
- **Migration required** — Rename tables, update views and MCPs
- **Sparse columns** — Endurance fields NULL for strength sets (acceptable tradeoff)

### Neutral
- Neo4j still handles planning and relationships
- Analytics views need updating but logic unchanged

## Migration Plan

See `/migrations/SCHEMA_SIMPLIFICATION_INSTRUCTIONS.md` for detailed migration steps.

## Lessons Learned (for Future Reference)

1. **Don't solve problems you don't have.** Build for the 95% case, not hypothetical futures.
2. **Orthogonal concepts need separate axes.** Modality and training phase are different things.
3. **Capture friction kills adoption.** Auto-compute what you can; ask only when necessary.
4. **OOP maps to relational cleanly.** Three objects, three tables. Discriminators add complexity.
5. **Never ship temporary names.** "v2" is not a version strategy.

## References

- **AALL-006:** `/docs/adr/AALL-006-unified-workout-schema.md` — Lessons learned from ADR-006 failure
- ADR-001: Data Layer Separation (Postgres facts, Neo4j relationships)
- ADR-002: Strength Workout Migration (original correct intuition)
- ADR-006: Unified Workout Schema (superseded — explains what went wrong)
- ADR-008: Device Telemetry Layer (separates device data from workout log)
- `/docs/ontology/workout-structure.md` — Canonical data model
