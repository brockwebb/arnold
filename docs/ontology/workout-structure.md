# Workout Structure Ontology

**Last Updated:** 2026-01-20  
**Status:** Active  
**Supersedes:** ADR-006 (Unified Workout Schema)

## Overview

This document defines the canonical data model for workout tracking in the Arnold system. The design prioritizes simplicity over flexibility—we built for the 95% case (strength training) rather than hypothetical future modalities.

## Hierarchy

```
WORKOUT (session)
├── Properties: date, duration, rpe, sport_type, purpose, notes, source
└── Contains: 1..N BLOCKS

BLOCK (container)
├── Properties: type, modality, name, seq, rounds, work_s, rest_s, notes
├── type: warmup | main | accessory | conditioning | cooldown | circuit | emom | skill
├── modality: strength | running | cycling | swimming | mixed
│   (optional - defaults to workout.sport_type)
└── Contains: 1..N SETS

SET (atomic unit)
├── Properties: exercise_id, exercise_name, seq, notes, planned_set_id
├── Strength: reps, load, load_unit, rpe
├── Endurance: distance, distance_unit, duration_s, pace, hr_avg, hr_zone
├── Conditioning: calories, rounds (for result tracking)
└── All fields nullable - use what applies
```

## Design Principles

### 1. One Sets Table

All set data lives in a single `sets` table with nullable columns for different modalities. We rejected the discriminator/child-table pattern (e.g., `strength_sets`, `running_intervals`) because:

- 95% of our workouts are strength training
- Joins across child tables add complexity without benefit
- NULL columns have negligible storage cost in Postgres

### 2. Block is General-Purpose

A block is simply a container with properties. It groups sets that share context (warmup, main work, finisher). We do not subtype blocks—the `block_type` property carries the semantic meaning.

**Valid block_type values:**
| Type | Purpose |
|------|---------|
| `warmup` | Preparation exercises |
| `main` | Primary training focus |
| `accessory` | Supporting exercises |
| `conditioning` | Cardio/metabolic work |
| `cooldown` | Recovery exercises |
| `circuit` | Multiple exercises in rotation |
| `emom` | Every-minute-on-the-minute format |
| `skill` | Technique practice |

### 3. Modality vs Block Type (Orthogonal Concepts)

**Modality** = What sport/activity (strength, running, cycling)  
**Block Type** = Training phase (warmup, main, accessory)

These are independent axes. A running workout can have warmup blocks. A strength workout can have conditioning blocks. The previous schema conflated these into "segment type" and lost both meanings.

### 4. Deviation Tracking is Computed

We do not force users to explain deviations at logging time. Instead:

1. Log what actually happened (executed sets)
2. Compare against plan automatically via `execution_vs_plan` view
3. Store "why" explanations in Neo4j relationships when volunteered

This reduces friction while preserving analytical capability.

### 5. Extra JSONB for Escape Hatch

Each table retains an `extra` JSONB column for truly ad-hoc fields. If a key appears frequently (>10 occurrences in quarterly audit), promote it to a real column.

## Table Definitions

### workouts

| Column | Type | Description |
|--------|------|-------------|
| workout_id | UUID | Primary key |
| start_time | TIMESTAMPTZ | When workout began |
| end_time | TIMESTAMPTZ | When workout ended |
| duration_minutes | INT | Total duration |
| session_rpe | INT | Overall perceived exertion (1-10) |
| sport_type | TEXT | Primary modality |
| purpose | TEXT | Training goal |
| notes | TEXT | Free-form notes |
| source | TEXT | Data origin (manual, polar, fit_file) |
| plan_id | TEXT | Link to Neo4j PlannedWorkout |
| extra | JSONB | Ad-hoc fields |

### blocks

| Column | Type | Description |
|--------|------|-------------|
| block_id | UUID | Primary key |
| workout_id | UUID | FK to workouts |
| block_type | TEXT | Training phase (warmup, main, etc.) |
| modality | TEXT | Sport type (optional override) |
| name | TEXT | Display name |
| seq | INT | Order within workout |
| rounds | INT | For circuits/EMOMs |
| work_s | INT | Work interval (seconds) |
| rest_s | INT | Rest interval (seconds) |
| notes | TEXT | Block-specific notes |
| extra | JSONB | Ad-hoc fields |

### sets

| Column | Type | Description |
|--------|------|-------------|
| set_id | UUID | Primary key |
| block_id | UUID | FK to blocks |
| exercise_id | TEXT | FK to exercise knowledge graph |
| exercise_name | TEXT | Denormalized for convenience |
| seq | INT | Order within block |
| planned_set_id | UUID | FK to planned_sets (for deviation tracking) |
| notes | TEXT | Set-specific notes |
| **Strength** | | |
| reps | INT | Repetitions completed |
| load | NUMERIC | Weight used |
| load_unit | TEXT | lbs, kg |
| rpe | INT | Perceived exertion (1-10) |
| **Endurance** | | |
| distance | NUMERIC | Distance covered |
| distance_unit | TEXT | mi, km, m |
| duration_s | INT | Time in seconds |
| pace | TEXT | e.g., "8:30/mi" |
| hr_avg | INT | Average heart rate |
| hr_zone | TEXT | HR zone label |
| **Conditioning** | | |
| calories | NUMERIC | Energy expenditure |
| extra | JSONB | Ad-hoc fields |

## Relationship to Neo4j

Neo4j stores the planning side:

- `PlannedWorkout` → `PlannedBlock` → `PlannedSet`
- `(:StrengthWorkout)` references Postgres `workout_id`
- Goals, injuries, and coaching observations link to workouts

Postgres stores the execution side (facts/measurements). The `plan_id` column on `workouts` links execution to plan.

## Migration History

| Date | Change |
|------|--------|
| 2026-01-20 | Simplified from v2 schema (segments → blocks, discriminator pattern removed) |
| 2025-12 | v2 schema introduced (over-engineered, superseded) |
| 2025-11 | Original workout tables |

## See Also

- ADR-001: Data Layer Separation (graph vs analytics)
- ADR-002: Strength Workout Migration (original correct design)
- ADR-006: Unified Workout Schema (superseded - explains what went wrong)
- ADR-007: Simplified Workout Schema (current)
