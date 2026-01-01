# Arnold Neo4j Schema Reference

> **Last Updated:** December 31, 2025

This document describes the complete graph schema for the Arnold knowledge graph.

---

## Core Architecture (Dec 2025)

### The Central Insight: Modality as Hub

Modality is the central organizing concept. Everything connects through modality:

```
Goal -[:REQUIRES]-> Modality <-[:FOR_MODALITY]- TrainingLevel
                       |
              [:EXPRESSED_BY]
                       |
                       v
              MovementPattern <-[:INVOLVES]- Exercise
```

### Modality

Answers "What are we training?"

```cypher
(:Modality {
  id: string,              // "MOD:hip-hinge-strength"
  name: string,            // "Hip Hinge Strength"
  adaptation_type: string, // strength | power | endurance | conditioning | mobility | stability
  context_type: string,    // movement_pattern | activity
  description: string
})
```

**Current Modalities (13):**
- Hip Hinge Strength, Squat Strength, Vertical Pull/Push Strength, Horizontal Pull/Push Strength
- Loaded Carry, Core Stability, Power/Explosive, Mobility
- Ultra Endurance, Aerobic Base, Anaerobic Capacity

**Relationships:**
```cypher
(:Modality)-[:EXPRESSED_BY]->(:MovementPattern)  // For strength modalities
(:Modality)-[:EXPRESSED_BY]->(:Activity)         // For endurance modalities
```

### Goal

First-class entity representing training objectives.

```cypher
(:Goal {
  id: string,              // "GOAL:deadlift-405x5-2026"
  name: string,            // "Deadlift 405x5"
  type: string,            // performance | body_comp | health | skill | rehabilitation
  target_value: number,    // 405
  target_unit: string,     // "lbs"
  target_reps: number,     // 5
  target_date: date,       // date("2026-12-31")
  priority: string,        // high | medium | low | meta
  status: string           // active | achieved | abandoned | paused
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_GOAL]->(:Goal)
(:Goal)-[:REQUIRES {priority: "primary"|"supporting"}]->(:Modality)
(:Goal)-[:CONFLICTS_WITH {reason: string}]->(:Goal)
(:Goal)-[:SYNERGIZES_WITH {reason: string}]->(:Goal)
(:Block)-[:SERVES]->(:Goal)
```

### TrainingLevel

Per-person, per-modality training experience and progression model.

```cypher
(:TrainingLevel {
  id: string,                    // "TL:brock:hip-hinge-strength"
  current_level: string,         // novice | intermediate | advanced
  training_age_years: float,     // 0.5
  training_age_assessed: date,
  historical_foundation: boolean, // true if had prior experience
  foundation_period: string,      // "1990-1997"
  foundation_notes: string,
  evidence_notes: string,
  known_gaps: [string],          // ["anti-lateral flexion"]
  strong_planes: [string]        // ["sagittal", "transverse"]
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_LEVEL]->(:TrainingLevel)
(:TrainingLevel)-[:FOR_MODALITY]->(:Modality)
(:TrainingLevel)-[:USES_MODEL]->(:PeriodizationModel)
```

### PeriodizationModel

Library of progression models with scientific grounding.

```cypher
(:PeriodizationModel {
  id: string,                          // "PMODEL:linear"
  name: string,                        // "Linear Periodization"
  description: string,
  recommended_for: [string],           // ["novice", "returning"]
  contraindicated_for: [string],       // ["advanced_concurrent"]
  typical_block_duration_weeks_min: int,
  typical_block_duration_weeks_max: int,
  volume_trend: string,                // decreasing | increasing | variable | block_dependent
  intensity_trend: string,
  deload_frequency: string,            // "every_4_weeks"
  loading_paradigm: string,            // "3:1"
  citations: [string],                 // ["Matveyev 1981", "Stone 2007"]
  evidence_level: string               // strong | moderate | emerging
})
```

**Current Models (3):**
- Linear Periodization (novices)
- Non-Linear/Undulating Periodization (intermediate, lifestyle athletes)
- Block Periodization (advanced, masters, concurrent goals)

### Block

The fundamental time unit for training organization. Replaces TrainingPlan.

```cypher
(:Block {
  id: string,              // "BLOCK:2025-Q1-1-accumulation"
  name: string,            // "Accumulation"
  block_type: string,      // accumulation | transmutation | realization | deload | recovery
  start_date: date,
  end_date: date,
  week_count: int,
  status: string,          // planned | active | completed | skipped
  intent: string,          // Plain language coaching intent
  volume_target: string,   // "moderate-high"
  intensity_target: string,
  loading_pattern: string, // "3:1"
  focus: [string]          // ["hypertrophy", "work_capacity"]
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_BLOCK]->(:Block)
(:Block)-[:SERVES]->(:Goal)
(:Block)-[:HAS_SESSION]->(:PlannedWorkout)
```

### Activity

Sports and activities (for endurance modalities).

```cypher
(:Activity {
  id: string,           // "ACT:trail-running"
  name: string,         // "Trail Running"
  type: string,         // endurance | combat | skill
  description: string,
  uses_for: [string]    // ["primary sport", "conditioning"]
})
```

**Relationships:**
```cypher
(:Modality)-[:EXPRESSED_BY]->(:Activity)
(:Person)-[:PRACTICES {years, current_role, frequency}]->(:Activity)
```

---

## Person & Training Data

### Person

```cypher
(:Person {
  id: string,
  name: string,
  birth_date: date,
  sex: string,
  
  // Athletic profile
  athlete_phenotype: string,       // "lifelong"
  athlete_phenotype_notes: string,
  training_age_total_years: int,
  
  // Background
  martial_arts_years: int,
  martial_arts_notes: string,
  triathlon_history: string,
  cycling_history: string,
  running_preference: string
})
```

**Key Relationships:**
```cypher
(:Person)-[:HAS_GOAL]->(:Goal)
(:Person)-[:HAS_LEVEL]->(:TrainingLevel)
(:Person)-[:HAS_BLOCK]->(:Block)
(:Person)-[:PERFORMED]->(:Workout)           // Direct, no Athlete intermediary
(:Person)-[:HAS_PLANNED_WORKOUT]->(:PlannedWorkout)
(:Person)-[:HAS_INJURY]->(:Injury)           // Direct, no Athlete intermediary
(:Person)-[:HAS_ACCESS_TO]->(:EquipmentInventory)
(:Person)-[:PRACTICES]->(:Activity)
```

### Workout (Executed)

```cypher
(:Workout {
  id: string,
  date: date,
  type: string,              // strength | conditioning | mobility
  duration_minutes: int,
  notes: string,
  source: string,            // "obsidian" | "adhoc" | "planned"
  imported_at: datetime
})
```

**Relationships:**
```cypher
(:Person)-[:PERFORMED]->(:Workout)
(:Workout)-[:HAS_BLOCK]->(:WorkoutBlock)
(:Workout)-[:EXECUTED_FROM]->(:PlannedWorkout)  // If from plan
```

### WorkoutBlock

```cypher
(:WorkoutBlock {
  id: string,
  name: string,      // "Warm-Up", "Main Work", "Finisher"
  phase: string,     // warmup | main | accessory | finisher | cooldown
  order: int
})
```

### Set

```cypher
(:Set {
  id: string,
  order: int,
  set_number: int,
  reps: int,
  load_lbs: float,
  duration_seconds: int,
  distance_miles: float,
  rpe: float,
  notes: string
})
```

**Relationships:**
```cypher
(:WorkoutBlock)-[:CONTAINS {order}]->(:Set)
(:Set)-[:OF_EXERCISE]->(:Exercise)
(:Set)-[:DEVIATED_FROM]->(:PlannedSet)  // If deviated from plan
```

---

## Planning Layer

### PlannedWorkout

```cypher
(:PlannedWorkout {
  id: string,
  date: date,
  status: string,              // draft | confirmed | completed | skipped
  goal: string,
  focus: [string],
  estimated_duration_minutes: int,
  notes: string,
  created_at: datetime,
  confirmed_at: datetime,
  completed_at: datetime,
  skipped_at: datetime,
  skip_reason: string
})
```

### PlannedBlock

```cypher
(:PlannedBlock {
  id: string,
  name: string,
  block_type: string,
  order: int,
  protocol_notes: string,
  notes: string
})
```

### PlannedSet

```cypher
(:PlannedSet {
  id: string,
  order: int,
  round: int,
  prescribed_reps: int,
  prescribed_load_lbs: float,
  prescribed_rpe: float,
  prescribed_duration_seconds: int,
  prescribed_distance_miles: float,
  intensity_zone: string,       // light | moderate | heavy | max
  notes: string
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_PLANNED_WORKOUT]->(:PlannedWorkout)
(:PlannedWorkout)-[:HAS_PLANNED_BLOCK {order}]->(:PlannedBlock)
(:PlannedBlock)-[:CONTAINS_PLANNED {order, round}]->(:PlannedSet)
(:PlannedSet)-[:PRESCRIBES]->(:Exercise)
```

---

## Example Queries

### Modality-Based Queries

```cypher
// What's my training level for hip hinge?
MATCH (p:Person {name: "Brock Webb"})-[:HAS_LEVEL]->(tl:TrainingLevel)-[:FOR_MODALITY]->(m:Modality {name: "Hip Hinge Strength"})
OPTIONAL MATCH (tl)-[:USES_MODEL]->(pm:PeriodizationModel)
RETURN tl.current_level, tl.training_age_years, pm.name

// What modalities does a goal require?
MATCH (g:Goal {name: "Deadlift 405x5"})-[:REQUIRES]->(m:Modality)
RETURN g.name, collect(m.name) as required_modalities

// Traverse Goal → Modality → MovementPattern → Exercise
MATCH (g:Goal)-[:REQUIRES]->(m:Modality)-[:EXPRESSED_BY]->(mp:MovementPattern)<-[:INVOLVES]-(e:Exercise)
RETURN g.name, m.name, mp.name, e.name LIMIT 20

// What goals does the current block serve?
MATCH (b:Block {status: 'active'})-[:SERVES]->(g:Goal)
RETURN b.name, collect(g.name) as serves
```

### Exercise Selection

```cypher
// What exercises target the gluteus maximus?
MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
WHERE toLower(m.name) CONTAINS 'glute'
RETURN DISTINCT e.name

// What hip hinge exercises exist?
MATCH (e:Exercise)-[:INVOLVES]->(mp:MovementPattern {name: "Hip Hinge"})
RETURN e.name, e.source
```

### Injury & Constraints

```cypher
// What active injuries exist?
MATCH (p:Person)-[:HAS_INJURY]->(i:Injury)
WHERE i.status IN ['active', 'recovering']
RETURN i.name, i.status, i.body_part, i.diagnosis

// What constraints come from injuries?
MATCH (p:Person)-[:HAS_INJURY]->(i:Injury)-[:CREATES]->(c:Constraint)
WHERE i.status IN ['active', 'recovering']
RETURN i.name, c.description, c.constraint_type
```

### Training History

```cypher
// Recent workouts (Person direct)
MATCH (p:Person)-[:PERFORMED]->(w:Workout)
WHERE w.date >= date() - duration('P7D')
RETURN w.date, w.type ORDER BY w.date DESC

// What muscles have I trained this week?
MATCH (p:Person)-[:PERFORMED]->(w:Workout)-[:HAS_BLOCK]->(:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
WHERE w.date >= date() - duration('P7D')
MATCH (e)-[:TARGETS]->(m:Muscle)
RETURN m.name, count(s) as sets_this_week
ORDER BY sets_this_week DESC

// What movement patterns haven't I trained in 2+ weeks?
MATCH (mp:MovementPattern)<-[:INVOLVES]-(e:Exercise)
WHERE NOT EXISTS {
  MATCH (p:Person)-[:PERFORMED]->(w:Workout)-[:HAS_BLOCK]->(:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e)
  WHERE w.date >= date() - duration('P14D')
}
RETURN DISTINCT mp.name
```

---

## Exercise Knowledge Graph

### Exercise

```cypher
(:Exercise {
  id: string,               // "EXERCISE:deadlift" or source-specific
  name: string,
  aliases: [string],
  category: string,         // strength | conditioning | mobility
  force_type: string,       // push | pull
  mechanic: string,         // compound | isolation
  difficulty: string,       // beginner | intermediate | advanced
  instructions: string,
  source: string            // free-exercise-db | functional-fitness-db
})
```

**Relationships:**
```cypher
(:Exercise)-[:INVOLVES]->(:MovementPattern)
(:Exercise)-[:TARGETS {role: "primary"|"synergist"|"stabilizer"}]->(:Muscle)
(:Exercise)-[:REQUIRES]->(:Equipment)
(:Exercise)-[:VARIATION_OF]->(:Exercise)
(:Exercise)-[:SIMILAR_TO]->(:Exercise)
(:Exercise)-[:SUBSTITUTES_FOR]->(:Exercise)
```

### MovementPattern

```cypher
(:MovementPattern {
  id: string,
  name: string,     // "Hip Hinge", "Squat", "Vertical Pull", etc.
  description: string
})
```

**Current Patterns (28):** Hip Hinge, Squat, Vertical Pull, Vertical Push, Horizontal Pull, Horizontal Push, Loaded Carry, Anti-Extension, Anti-Rotation, Anti-Lateral Flexion, Knee Extension, Hip Adduction, Hip Abduction, etc.

### Muscle & MuscleGroup

```cypher
(:Muscle {
  id: string,           // UBERON:... or CUSTOM:...
  name: string,
  wikipedia_url: string,  // Citation requirement
  synonyms: [string]
})

(:MuscleGroup {
  id: string,
  name: string          // "Quadriceps", "Posterior Chain"
})
```

**Relationships:**
```cypher
(:Muscle)-[:PART_OF]->(:MuscleGroup)
(:Muscle)-[:SYNERGIST_TO]->(:Muscle)
(:Muscle)-[:ANTAGONIST_TO]->(:Muscle)
```

---

## Injury Layer

### Injury

```cypher
(:Injury {
  id: string,              // "INJ:knee-surgery-2025"
  name: string,
  body_part: string,
  side: string,            // left | right | bilateral
  injury_date: date,
  surgery_date: date,
  surgery_type: string,
  diagnosis: string,
  status: string,          // active | recovering | resolved
  recovery_notes: string,
  rehab_insights: string,
  weeks_post_surgery: int,
  outcome: string          // For resolved injuries
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_INJURY]->(:Injury)
(:Injury)-[:CREATES]->(:Constraint)
(:Injury)-[:AFFECTS]->(:Joint)
(:Injury)-[:AFFECTS]->(:Muscle)
```

### Constraint

```cypher
(:Constraint {
  id: string,
  description: string,
  constraint_type: string  // avoid | limit | modify | monitor
})
```

**Relationships:**
```cypher
(:Constraint)-[:RESTRICTS]->(:Exercise)
(:Constraint)-[:RESTRICTS]->(:MovementPattern)
```

---

## Equipment Layer

### EquipmentInventory

```cypher
(:EquipmentInventory {
  id: string,
  name: string,       // "Home Gym"
  location: string
})
```

### EquipmentCategory

```cypher
(:EquipmentCategory {
  id: string,
  name: string,       // "Kettlebell", "Barbell"
  type: string
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_ACCESS_TO]->(:EquipmentInventory)
(:EquipmentInventory)-[:CONTAINS {weight_lbs, adjustable}]->(:EquipmentCategory)
(:Exercise)-[:REQUIRES]->(:EquipmentCategory)
```

---

## Indexes and Constraints

```cypher
// Uniqueness Constraints
CREATE CONSTRAINT exercise_id FOR (e:Exercise) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT person_id FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT goal_id FOR (g:Goal) REQUIRE g.id IS UNIQUE;
CREATE CONSTRAINT modality_id FOR (m:Modality) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT training_level_id FOR (tl:TrainingLevel) REQUIRE tl.id IS UNIQUE;
CREATE CONSTRAINT block_id FOR (b:Block) REQUIRE b.id IS UNIQUE;
CREATE CONSTRAINT workout_id FOR (w:Workout) REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT injury_id FOR (i:Injury) REQUIRE i.id IS UNIQUE;

// Indexes
CREATE INDEX exercise_name FOR (e:Exercise) ON (e.name);
CREATE INDEX workout_date FOR (w:Workout) ON (w.date);
CREATE INDEX block_status FOR (b:Block) ON (b.status);
CREATE INDEX goal_status FOR (g:Goal) ON (g.status);
```

---

## Deprecated (Removed Dec 2025)

| Node/Relationship | Replaced By |
|-------------------|-------------|
| Athlete | Person (direct relationships) |
| Person-[:HAS_ROLE]->Athlete | Removed |
| TrainingPlan | Block + Goal |
| Person-[:HAS_TRAINING_PLAN]->TrainingPlan | Person-[:HAS_BLOCK]->Block |
| Athlete-[:PERFORMED]->Workout | Person-[:PERFORMED]->Workout |
| Athlete-[:HAS_INJURY]->Injury | Person-[:HAS_INJURY]->Injury |
