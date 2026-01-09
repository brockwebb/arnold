# Graph Data Model

> **Last Updated**: January 8, 2026

---

## The Graph Structure

```
                                        ┌──────────────┐
                                        │    GOAL      │
                                        │ Deadlift 405 │
                                        └───────┬──────┘
                                                │
                                          [:REQUIRES]
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           ▼                           │
                    │                   ┌──────────────┐                    │
                    │                   │   MODALITY   │                    │
                    │         ┌─────────│  Hip Hinge   │─────────┐          │
                    │         │         │   Strength   │         │          │
                    │         │         └──────────────┘         │          │
                    │         │                │                 │          │
                    │   [:EXPRESSED_BY]        │           [:HAS_LEVEL]     │
                    │         │                │                 │          │
                    │         ▼                │                 ▼          │
                    │  ┌──────────────┐        │         ┌──────────────┐   │
                    │  │   MOVEMENT   │        │         │  TRAINING    │   │
                    │  │   PATTERN    │        │         │    LEVEL     │   │
                    │  │  Hip Hinge   │        │         │   novice     │   │
                    │  └───────┬──────┘        │         │   linear     │   │
                    │          │               │         └───────┬──────┘   │
                    │    [:INVOLVES]           │                 │          │
                    │          │               │           [:FOR_PERSON]    │
                    │          ▼               │                 │          │
                    │  ┌──────────────┐        │                 ▼          │
                    │  │   EXERCISE   │        │         ┌──────────────┐   │
                    │  │   Deadlift   │        │         │    PERSON    │   │
                    │  └───────┬──────┘        │         │              │   │
                    │          │               │         └──────────────┘   │
                    │    [:PRESCRIBES]         │                 ▲          │
                    │          │               │                 │          │
                    │          ▼               │           [:HAS_BLOCK]     │
                    │  ┌──────────────┐        │                 │          │
                    │  │     SET      │        │         ┌───────┴──────┐   │
                    │  │   315x5      │        └────────►│    BLOCK     │   │
                    │  └───────┬──────┘         [:SERVES]│ Winter Base  │   │
                    │          │                        └───────┬──────┘   │
                    │    [:CONTAINS]                            │          │
                    │          │                          [:HAS_SESSION]   │
                    │          ▼                                │          │
                    │  ┌──────────────┐                         ▼          │
                    └─►│   SESSION    │◄────────────────────────┘          │
                       │   Monday     │                                    │
                       └──────────────┘
```

**Every path leads somewhere useful. Start anywhere.**

---

## Node Types

### Modality (The Hub)

Modality is the central organizing concept — it answers "What are we training?"

```cypher
(:Modality {
  id: "MOD:hip-hinge-strength",
  name: "Hip Hinge Strength",
  adaptation_type: "strength",      // strength | power | endurance | conditioning | mobility | skill
  context_type: "movement_pattern", // movement_pattern | activity
  description: "Maximal force production in hip-dominant pulling movements"
})
```

**Core Modalities:**

| Modality | Adaptation Type | Context Type | Expressed By |
|----------|----------------|--------------|--------------|
| Hip Hinge Strength | strength | movement_pattern | Hip Hinge |
| Squat Strength | strength | movement_pattern | Squat |
| Vertical Pull Strength | strength | movement_pattern | Vertical Pull |
| Vertical Push Strength | strength | movement_pattern | Vertical Push |
| Horizontal Pull Strength | strength | movement_pattern | Horizontal Pull |
| Horizontal Push Strength | strength | movement_pattern | Horizontal Push |
| Ultra Endurance | endurance | activity | Ultra Running |
| Aerobic Base | endurance | activity | Easy Running/Cycling |
| Anaerobic Capacity | conditioning | activity | Intervals/Sprints |
| Core Stability | stability | movement_pattern | Anti-Extension, Anti-Rotation |
| Mobility | mobility | movement_pattern | various |

### Goal

```cypher
(:Goal {
  id: "GOAL:deadlift-405x5-2026",
  name: "Deadlift 405x5",
  type: "performance",        // performance | body_comp | health | skill | rehabilitation
  target_value: 405,
  target_unit: "lbs",
  target_reps: 5,
  target_date: date("2026-12-31"),
  priority: "high",           // high | medium | low | meta
  status: "active"            // active | achieved | abandoned | paused
})

// Meta-goals have no target date
(:Goal {
  id: "GOAL:stay-healthy",
  name: "Stay healthy, minimize injury",
  type: "health",
  priority: "meta",
  status: "active"
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_GOAL]->(Goal)
(:Goal)-[:REQUIRES]->(Modality)
(:Goal)-[:CONFLICTS_WITH {reason: "competing energy systems"}]->(Goal)
(:Goal)-[:SYNERGIZES_WITH {reason: "core stability supports both"}]->(Goal)
```

### TrainingLevel (Per Person-Modality)

```cypher
(:TrainingLevel {
  current_level: "novice",           // novice | intermediate | advanced
  training_age_years: 0.5,
  training_age_assessed: date("2025-12-30"),
  historical_foundation: true,        // had prior experience, now returning
  foundation_period: "1990-1997",
  recommended_model: "linear",        // determined by level
  evidence_notes: "Weekly PRs still occurring"
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_LEVEL]->(TrainingLevel)-[:FOR_MODALITY]->(Modality)
(:TrainingLevel)-[:USES_MODEL]->(PeriodizationModel)
```

### PeriodizationModel (Library)

```cypher
(:PeriodizationModel {
  id: "PMODEL:linear",
  name: "Linear Periodization",
  description: "Progressive overload with gradual volume reduction and intensity increase",
  
  // Selection criteria
  recommended_for: ["novice", "returning"],
  contraindicated_for: ["advanced_concurrent"],
  
  // Structure parameters
  typical_block_duration_weeks: [4, 6],
  volume_trend: "decreasing",
  intensity_trend: "increasing",
  deload_frequency: "every_4_weeks",
  loading_paradigm: "3:1",
  
  // Scientific grounding
  citations: ["Matveyev 1981", "Stone 2007"],
  evidence_level: "strong"
})
```

**Core Models:**

| Model | Best For | Key Characteristics |
|-------|----------|---------------------|
| Linear | Novices, single focus | Volume ↓, Intensity ↑ over time |
| Non-linear/Undulating | Intermediate, lifestyle athletes | Daily/weekly variation, flexible |
| Block | Advanced, masters, concurrent | Concentrated loading, multiple peaks |

### Block (The Fundamental Time Unit)

```cypher
(:Block {
  id: "BLOCK:2025-Q1-1-accumulation",
  name: "Winter Base Building",
  block_type: "accumulation",    // accumulation | transmutation | realization | deload | recovery | technique
  start_date: date("2025-12-30"),
  end_date: date("2026-01-26"),
  week_count: 4,
  status: "active",              // planned | active | completed | skipped
  
  // Intent (plain language for coach and athlete)
  intent: "Build work capacity, establish movement patterns, progressive volume increase",
  
  // Targets
  volume_target: "moderate-high",
  intensity_target: "moderate",
  loading_pattern: "3:1",        // 3 weeks build, 1 week deload
  
  // Focus areas
  focus: ["hypertrophy", "work_capacity"]
})
```

**Relationships:**
```cypher
(:Person)-[:HAS_BLOCK]->(Block)
(:Block)-[:SERVES]->(Goal)
(:Block)-[:HAS_SESSION]->(PlannedWorkout)
```

**Season is a Query, Not a Node:**

Seasons (Winter, Spring, Summer, Fall) are for human orientation. They're computed from block dates, not stored.

```cypher
// Get "Winter 2025-26" view
MATCH (p:Person {id: $person_id})-[:HAS_BLOCK]->(b:Block)
WHERE b.start_date >= date("2025-12-01") AND b.start_date < date("2026-03-01")
RETURN b ORDER BY b.start_date
```

### Session Structure

```cypher
(:PlannedWorkout {
  id: UUID,
  display_name: "Tuesday, December 30, 2025 - Vertical Pull/Push",
  date: date,
  status: "draft" | "confirmed" | "completed" | "skipped",
  goal: string,
  estimated_duration_minutes: int
})

(:PlannedWorkout)-[:HAS_PLANNED_BLOCK]->(:PlannedBlock)
(:PlannedBlock)-[:CONTAINS_PLANNED]->(:PlannedSet)
(:PlannedSet)-[:PRESCRIBES]->(:Exercise)

// Execution (refs to Postgres)
(:StrengthWorkout)-[:EXECUTED_FROM]->(:PlannedWorkout)
```

---

## Modality-Driven Queries

The power of modality as hub — start anywhere, traverse to what you need:

```cypher
// "Show me all hip hinge work in the last 4 weeks"
MATCH (m:Modality {name: "Hip Hinge Strength"})-[:EXPRESSED_BY]->(mp:MovementPattern)<-[:INVOLVES]-(e:Exercise)<-[:PRESCRIBES]-(s:Set)
MATCH (s)<-[:CONTAINS]-(sess:PlannedWorkout)-[:IN_BLOCK]->(b:Block)
WHERE b.start_date >= date() - duration('P4W')
RETURN sess.date, e.name, s.reps, s.load_lbs
ORDER BY sess.date

// "What modalities does this block touch?"
MATCH (b:Block {id: $block_id})-[:HAS_SESSION]->(sess)-[:CONTAINS]->(s)-[:PRESCRIBES]->(e)-[:INVOLVES]->(mp:MovementPattern)<-[:EXPRESSED_BY]-(m:Modality)
RETURN DISTINCT m.name

// "What's my training level for hip hinge?"
MATCH (p:Person {id: $person_id})-[:HAS_LEVEL]->(tl:TrainingLevel)-[:FOR_MODALITY]->(m:Modality {name: "Hip Hinge Strength"})
RETURN tl.current_level, tl.training_age_years, tl.recommended_model

// "What goals require ultra endurance?"
MATCH (g:Goal)-[:REQUIRES]->(m:Modality {name: "Ultra Endurance"})
RETURN g.name, g.target_date
```

---

## Graph Health (as of Jan 2026)

| Node Type | Count | Notes |
|-----------|-------|-------|
| Exercise | 4,242 | Knowledge base |
| StrengthWorkout | 165 | **Refs to Postgres (ADR-002)** |
| EnduranceWorkout | 1 | Refs to Postgres |
| MovementPattern | 28 |
| Modality | 14 |
| Goal | 4 |
| TrainingLevel | 6 |
| PeriodizationModel | 3 |
| Block | 4 |
| Activity | 19 |
| PlannedWorkout | 1 |
| Injury | 2 |
| MobilityLimitation | 1 |
| Protocol | 10 |
| Annotation | 4 |
| Person | 1 |

---

## Key Relationships

| Relationship | Description |
|--------------|-------------|
| (Exercise)-[:INVOLVES]->(MovementPattern) | Exercise uses movement pattern |
| (Modality)-[:EXPRESSED_BY]->(MovementPattern) | Modality manifests through pattern |
| (Modality)-[:EXPRESSED_BY]->(Activity) | Modality manifests through activity |
| (Goal)-[:REQUIRES]->(Modality) | Goal needs modality |
| (Person)-[:HAS_GOAL]->(Goal) | Person's goals |
| (Person)-[:HAS_LEVEL]->(TrainingLevel) | Person's level per modality |
| (TrainingLevel)-[:FOR_MODALITY]->(Modality) | What modality this level is for |
| (TrainingLevel)-[:USES_MODEL]->(PeriodizationModel) | Progression model for this level |
| (Person)-[:HAS_BLOCK]->(Block) | Person's training blocks |
| (Block)-[:SERVES]->(Goal) | Block serves goal(s) |
| (Block)-[:HAS_SESSION]->(PlannedWorkout) | Sessions in block |
| (Person)-[:HAS_ANNOTATION]->(Annotation) | Data context/explanations |
| (Annotation)-[:EXPLAINS]->(Workout\|Injury) | What the annotation documents |
