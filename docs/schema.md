# Arnold Neo4j Schema Reference

This document describes the complete graph schema for the Arnold knowledge graph.

## Node Types

### Anatomy Layer

#### Muscle
```cypher
(:Muscle {
  id: string,           // UBERON:... or CUSTOM:...
  name: string,
  synonyms: [string],
  muscle_group: string, // e.g., "posterior_chain", "quadriceps"
  location: string,     // e.g., "upper_leg", "back"
  action: string,       // e.g., "hip_extension", "knee_flexion"
  source: string        // "UBERON" or "free-exercise-db"
})
```

#### Joint
```cypher
(:Joint {
  id: string,
  name: string,
  joint_type: string,         // e.g., "hinge", "ball_and_socket"
  primary_movements: [string], // e.g., ["flexion", "extension"]
  source: string
})
```

#### Bone
```cypher
(:Bone {
  id: string,
  name: string,
  source: string
})
```

#### ConnectiveTissue
```cypher
(:ConnectiveTissue {
  id: string,
  name: string,
  tissue_type: string   // "tendon", "ligament", "fascia"
})
```

### Exercise Layer

#### Exercise
```cypher
(:Exercise {
  id: string,               // EXERCISE:...
  name: string,
  aliases: [string],
  category: string,         // "strength", "conditioning", "mobility"
  movement_pattern: string, // "hinge", "squat", "push", "pull", "carry"
  force_type: string,       // "push", "pull"
  mechanic: string,         // "compound", "isolation"
  difficulty: string,       // "beginner", "intermediate", "advanced"
  instructions: string,
  contraindications: [string],
  source: string            // "free-exercise-db"
})
```

#### Equipment
```cypher
(:Equipment {
  id: string,              // EQUIPMENT:...
  name: string,
  category: string,        // "barbell", "kettlebell", "machine", "bodyweight"
  user_has: boolean,       // Whether user owns this equipment
  weights_available: [int] // For adjustable equipment (KB, DB, etc.)
})
```

#### MovementPattern
```cypher
(:MovementPattern {
  id: string,
  name: string,           // "hip_hinge", "knee_dominant_squat", "horizontal_push"
  description: string
})
```

### Injury/Rehab Layer

#### Injury
```cypher
(:Injury {
  id: string,            // INJURY:...
  name: string,
  status: string,        // "active", "recovering", "resolved"
  onset_date: date,
  surgery_date: date,    // optional
  notes: string
})
```

#### Constraint
```cypher
(:Constraint {
  id: string,              // CONSTRAINT:...
  description: string,
  constraint_type: string  // "avoid", "limit", "modify", "monitor"
})
```

#### RehabPhase
```cypher
(:RehabPhase {
  id: string,
  name: string,
  week_range: string,      // e.g., "0-2", "2-6", "6-12"
  goals: [string],
  allowed_activities: [string],
  restrictions: [string]
})
```

### Personal Training Layer

#### Workout
```cypher
(:Workout {
  id: string,              // e.g., "2025-11-10_strength"
  date: date,
  type: string,            // "strength", "conditioning", "mobility"
  sport: string,
  periodization_phase: string,
  planned_intensity: int,
  perceived_intensity: int,
  duration_minutes: int,
  notes: string,
  deviations: [string]
})
```

#### ExerciseInstance
```cypher
(:ExerciseInstance {
  id: string,
  workout_id: string,
  exercise_id: string,
  sets: int,
  reps: string,           // Can be "5,5,5" or "8-10"
  weight: string,         // Can be "135,185,225" or "bodyweight"
  notes: string
})
```

#### Goal
```cypher
(:Goal {
  id: string,            // GOAL:...
  description: string,
  goal_type: string,     // "strength", "endurance", "body_composition", "skill"
  target_metric: string,
  target_value: string,
  deadline: date,
  status: string         // "active", "achieved", "abandoned"
})
```

#### PeriodizationPhase
```cypher
(:PeriodizationPhase {
  id: string,
  name: string,          // "build_week_1", "deload", "peak"
  phase_type: string,    // "accumulation", "intensification", "realization", "deload"
  start_date: date,
  end_date: date
})
```

#### SubjectiveSignal
```cypher
(:SubjectiveSignal {
  id: string,
  date: date,
  signal_type: string,   // "soreness", "energy", "pain", "sleep", "stress"
  body_part: string,     // optional, for localized signals
  value: string,         // "high", "low", "3/10", etc.
  notes: string
})
```

## Relationships

### Anatomy Relationships

```cypher
(:Muscle)-[:ORIGIN]->(:Bone)
(:Muscle)-[:INSERTION]->(:Bone)
(:Muscle)-[:CROSSES]->(:Joint)
(:Muscle)-[:ACTION {movement: string}]->(:Joint)
(:Muscle)-[:PART_OF]->(:MuscleGroup)
(:Muscle)-[:SYNERGIST_TO]->(:Muscle)
(:Muscle)-[:ANTAGONIST_TO]->(:Muscle)

(:Joint)-[:ARTICULATES]->(:Bone)
(:Joint)-[:STABILIZED_BY]->(:ConnectiveTissue)

(:ConnectiveTissue)-[:CONNECTS]->(:Bone)
(:ConnectiveTissue)-[:ATTACHES]->(:Muscle)
```

### Exercise Relationships

```cypher
(:Exercise)-[:TARGETS {role: "primary"}]->(:Muscle)
(:Exercise)-[:TARGETS {role: "synergist"}]->(:Muscle)
(:Exercise)-[:TARGETS {role: "stabilizer"}]->(:Muscle)

(:Exercise)-[:LOADS]->(:Joint)
(:Exercise)-[:LOAD_PATTERN {type: string}]->(:Joint)

(:Exercise)-[:REQUIRES]->(:Equipment)
(:Exercise)-[:MOVEMENT_TYPE]->(:MovementPattern)
(:Exercise)-[:VARIATION_OF]->(:Exercise)
(:Exercise)-[:PROGRESSES_TO]->(:Exercise)
(:Exercise)-[:REGRESSES_TO]->(:Exercise)
```

### Injury Relationships

```cypher
(:Injury)-[:AFFECTS]->(:Joint)
(:Injury)-[:AFFECTS]->(:Muscle)
(:Injury)-[:AFFECTS]->(:ConnectiveTissue)

(:Injury)-[:CREATES]->(:Constraint)
(:Constraint)-[:RESTRICTS]->(:Exercise)
(:Constraint)-[:RESTRICTS]->(:MovementPattern)

(:Injury)-[:FOLLOWS_PROTOCOL]->(:RehabPhase)
(:RehabPhase)-[:NEXT]->(:RehabPhase)
```

### Personal Training Relationships

```cypher
(:Workout)-[:CONTAINS]->(:ExerciseInstance)
(:ExerciseInstance)-[:INSTANCE_OF]->(:Exercise)
(:ExerciseInstance)-[:USED]->(:Equipment)

(:Workout)-[:IN_PHASE]->(:PeriodizationPhase)
(:Workout)-[:TOWARD_GOAL]->(:Goal)
(:Workout)-[:HAD_SIGNAL]->(:SubjectiveSignal)

(:Goal)-[:REQUIRES_PROGRESSION]->(:Exercise)

// Temporal
(:Workout)-[:PREVIOUS]->(:Workout)
(:PeriodizationPhase)-[:NEXT]->(:PeriodizationPhase)
```

## Example Queries

### What exercises should I avoid given my meniscus injury?

```cypher
MATCH (i:Injury {name: "right_knee_meniscus"})-[:CREATES]->(c:Constraint)
WHERE c.constraint_type = 'avoid'
RETURN c.description
```

### What muscles does deadlift target?

```cypher
MATCH (e:Exercise)-[r:TARGETS]->(m:Muscle)
WHERE toLower(e.name) CONTAINS 'deadlift'
RETURN e.name, r.role, m.name
ORDER BY r.role
```

### What exercises target the gluteus maximus?

```cypher
MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
WHERE toLower(m.name) CONTAINS 'glute'
RETURN DISTINCT e.name
```

### What equipment do I have for pull exercises?

```cypher
MATCH (e:Exercise)-[:REQUIRES]->(eq:Equipment)
WHERE eq.user_has = true
  AND e.force_type = 'pull'
RETURN DISTINCT e.name, eq.name
```

### What muscles have I trained this week?

```cypher
MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e:Exercise)
WHERE w.date >= date() - duration('P7D')
MATCH (e)-[:TARGETS]->(m:Muscle)
RETURN m.name, count(ei) as sets_this_week
ORDER BY sets_this_week DESC
```

### What posterior chain exercises haven't I done in 3+ weeks?

```cypher
MATCH (m:Muscle {muscle_group: "posterior_chain"})<-[:TARGETS]-(e:Exercise)
WHERE NOT EXISTS {
  MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e)
  WHERE w.date >= date() - duration('P21D')
}
RETURN e.name
```

### Am I due for a deload? (volume trend)

```cypher
MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)
WHERE w.date >= date() - duration('P28D')
WITH w.date as workout_date, count(ei) as volume
RETURN workout_date, volume
ORDER BY workout_date
```

## Indexes and Constraints

### Uniqueness Constraints

```cypher
// Anatomy
CREATE CONSTRAINT muscle_id FOR (m:Muscle) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT joint_id FOR (j:Joint) REQUIRE j.id IS UNIQUE;
CREATE CONSTRAINT bone_id FOR (b:Bone) REQUIRE b.id IS UNIQUE;

// Exercise
CREATE CONSTRAINT exercise_id FOR (e:Exercise) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT equipment_id FOR (eq:Equipment) REQUIRE eq.id IS UNIQUE;

// Injury
CREATE CONSTRAINT injury_id FOR (i:Injury) REQUIRE i.id IS UNIQUE;
CREATE CONSTRAINT constraint_id FOR (c:Constraint) REQUIRE c.id IS UNIQUE;

// Training
CREATE CONSTRAINT workout_id FOR (w:Workout) REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT instance_id FOR (ei:ExerciseInstance) REQUIRE ei.id IS UNIQUE;
CREATE CONSTRAINT goal_id FOR (g:Goal) REQUIRE g.id IS UNIQUE;
```

### Indexes

```cypher
CREATE INDEX muscle_name FOR (m:Muscle) ON (m.name);
CREATE INDEX exercise_name FOR (e:Exercise) ON (e.name);
CREATE INDEX workout_date FOR (w:Workout) ON (w.date);
```
