# Arnold: Expert Exercise System
## Cyberdyne Systems Model 101 Fitness Advisor

> "Come with me if you want to lift."

---

## 1. Project Vision

Arnold is a **knowledge-grounded expert exercise system** that combines:
- A physiological knowledge graph (anatomy, muscles, joints, exercises, injuries)
- Personal training history and progression data
- Periodization and programming logic
- An LLM reasoning layer for planning and coaching

The system replaces stateless "paste context into ChatGPT" workflows with a persistent, accumulating knowledge base that gets smarter over time.

### End State
An invisible AI coach that:
1. **Plans** - Generates periodized training plans grounded in exercise science
2. **Tracks** - Logs workouts, deviations, subjective feedback, objective metrics
3. **Analyzes** - Identifies trends, plateaus, imbalances, overtraining signals
4. **Adapts** - Adjusts programming based on accumulated data and goals
5. **Communicates** - Via email (send plans, receive logs via voice dictation)

### Why Graph, Not RAG
The body is an interconnected system. When reasoning about "can I deadlift heavy tomorrow?", the system must traverse:
- Injury (meniscus) → affected joint (knee) → loading patterns → exercise constraints
- Yesterday's workout → fatigued muscles → recovery status
- Current periodization phase → appropriate intensity range
- Historical progression → whether you're due for a PR attempt or deload

This is multi-hop graph reasoning, not document retrieval.

---

## 2. User Context

### Profile
- **Age**: 48, Male
- **Height/Weight**: 5'7.5", 153 lbs
- **Experience**: Experienced fitness athlete
- **Current Status**: 6 weeks post-meniscus surgery, returning to running
- **Training Philosophy**: Functional "farmer strong" strength, ultramarathon endurance, mobility for martial arts

### Current Injuries/Constraints
| Injury | Status | Constraints |
|--------|--------|-------------|
| Right knee meniscus (surgical) | Recovering | Avoid impact, deep flexion, rotational load under weight |
| Left golf elbow | Recovering | Reduce direct elbow stress, prefer neutral grip |
| Mild AC shoulder | Mostly recovered | Monitor overhead pressing volume |

### Goals
**Short-term:**
- Return to running post-surgery
- Maintain functional strength during rebuild
- Improve posture and thoracic mobility

**Long-term:**
- Ultramarathon endurance
- Lifelong running capability
- Martial arts mobility and combat readiness

### Equipment Available
Extensive home gym including:
- Barbells (Olympic, curl, hex trap), plates
- Dumbbells (5-30 lb range)
- Kettlebells (5, 15, 20, 25, 35, 55, 70, 90 lb)
- Sandbags (100, 135, 150, 190 lb)
- Pull-up bar, landmine, plyo box
- Cardio: rowing machine, Airdyne
- Strongman: log (110 lb), chain (60 lb), corny kegs, farmer carry setup
- Striking: Bob dummy, ground-and-pound bag

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PERSONAL TRAINING GRAPH                     │
│  Workouts, Plans, Progress, Deviations, Subjective Signals      │
│  (Your 160+ historical workouts, ongoing logs)                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EXERCISE LAYER                              │
│  ~100-200 exercises mapped to:                                  │
│  - Equipment                                                    │
│  - Movement patterns (push/pull/hinge/squat/carry/rotation)     │
│  - Muscles (target, synergist, stabilizer)                      │
│  - Joint actions                                                │
│  - Injury constraints                                           │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ANATOMY LAYER                               │
│  UBERON/FMA subset - musculoskeletal system:                    │
│  - Muscles (origin, insertion, action)                          │
│  - Joints (articulating bones, ROM, stability structures)       │
│  - Connective tissue (tendons, ligaments)                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     INJURY/REHAB LAYER                          │
│  - TRAK knee rehab protocols                                    │
│  - Injury → structure → constraint mappings                     │
│  - Recovery timelines, phase progressions                       │
└─────────────────────────────────────────────────────────────────┘
```

### Technology Stack
- **Graph Database**: Neo4j (local instance)
- **Ontology Sources**: UBERON, FMA, TRAK, PACO
- **Exercise Data**: free-exercise-db, ExerciseDB
- **Language**: Python for ETL and tooling
- **LLM Interface**: Claude (via API or MCP)
- **Communication**: Gmail MCP (future phase)

---

## 4. Data Sources

### 4.1 Anatomy Ontologies

#### UBERON (Uber Anatomy Ontology)
- **URL**: http://purl.obolibrary.org/obo/uberon/basic.obo
- **Format**: OBO (convertible to OWL/JSON)
- **Content**: 6,500+ anatomical classes with relationships
- **Use**: Filter to musculoskeletal system - muscles, bones, joints, connective tissue
- **Key relationships**: `is_a`, `part_of`, `develops_from`, `attaches_to`

#### FMA (Foundational Model of Anatomy)
- **URL**: http://purl.obolibrary.org/obo/fma.owl
- **Format**: OWL
- **Content**: 85,000+ classes, human-specific, very granular
- **Use**: Supplement UBERON where more detail needed (muscle origins/insertions)
- **Note**: Large file, may need subset extraction

### 4.2 Exercise/Rehab Ontologies

#### TRAK (Taxonomy for Rehabilitation of Knee Conditions)
- **URL**: http://www.cs.cf.ac.uk/trak/ or BioPortal
- **Format**: OBO (convertible to OWL)
- **Content**: 100+ exercises categorized by type (aerobic, balance, stability, flexibility, functional, strength), joint movements, muscle contractions
- **Use**: Knee rehab protocols, exercise categorization structure
- **Directly relevant**: User is post-meniscus surgery

#### PACO (Physical Activity Concept Ontology)
- **URL**: BioPortal - search "PACO"
- **Format**: OWL
- **Content**: Activity types, intensity scales, effects, equipment, programs
- **Use**: Standardized intensity/effort scales, activity classification

### 4.3 Exercise-Muscle Databases

#### free-exercise-db (Primary)
- **URL**: https://github.com/yuhonas/free-exercise-db
- **Format**: JSON files per exercise
- **Content**: 800+ exercises
- **Fields**: `name`, `primaryMuscles`, `secondaryMuscles`, `force`, `level`, `mechanic`, `equipment`, `instructions`, `category`
- **License**: Public domain
- **Use**: Core exercise-muscle mappings

#### ExerciseDB API (Supplement)
- **URL**: https://github.com/ExerciseDB/exercisedb-api
- **Format**: JSON API
- **Content**: 11,000+ exercises
- **Fields**: `name`, `targetMuscles`, `secondaryMuscles`, `bodyParts`, `equipment`, `instructions`
- **Use**: Fill gaps, get variety suggestions

#### ExRx Structure Reference
- **URL**: https://github.com/flaviostutz/exrx-loader (scraper reference)
- **Fields of interest**: `muscles_target`, `muscles_synergists`, `muscles_stabilizers`, `muscles_dynstabilizers`, `muscles_antagonist_stabilizers`
- **Use**: Model for muscle role classification (not just primary/secondary)

### 4.4 Existing User Data

#### Workout Logs
- **Location**: `infinite_exercise_planner/data/infinite_exercise/`
- **Format**: Markdown with YAML frontmatter
- **Count**: ~160 files (Dec 2024 - Nov 2025)
- **Structure**:
```yaml
---
date: 2025-11-10
type: strength
tags: [deadlift, sandbag, shouldering, ...]
sport: strength
goals: [groove_hinge, neural_drive, ...]
periodization_phase: technique_week
equipment_used: [barbell, sandbag_100lb, ...]
injury_considerations: [meniscus_tear_preop, avoid_twist_lateral]
deviations: ["Condensed session; no cooldown"]
---
# Workout Card — Mon, Nov 10
## Warm-Up
- Airdyne × 3:00 (easy)
## Main
### 1) Deadlift (straight bar)
- 135×1, 225×1, 315×2, 275×5, 225×5, 135×5
...
```

#### Profile
- **Location**: `infinite_exercise_planner/data/profile.yaml`
- **Content**: Personal info, goals, injuries, equipment, preferences, periodization settings

#### Schemas
- **Location**: `infinite_exercise_planner/templates/`
- **Files**: `workout_log.schema.json`, `unified_knowledge_schema.json`
- **Use**: Reference for data structure, can be evolved

---

## 5. Neo4j Schema Design

### 5.1 Node Types

```cypher
// === ANATOMY LAYER ===

// Muscles
(:Muscle {
  id: string,           // UBERON ID or custom
  name: string,
  synonyms: [string],
  muscle_group: string, // e.g., "posterior_chain", "quadriceps"
  location: string,     // e.g., "upper_leg", "back"
  action: string        // e.g., "hip_extension", "knee_flexion"
})

// Joints
(:Joint {
  id: string,
  name: string,
  joint_type: string,   // e.g., "hinge", "ball_and_socket"
  primary_movements: [string]  // e.g., ["flexion", "extension"]
})

// Bones (minimal, for joint articulation)
(:Bone {
  id: string,
  name: string
})

// Connective Tissue
(:ConnectiveTissue {
  id: string,
  name: string,
  tissue_type: string   // "tendon", "ligament", "fascia"
})


// === EXERCISE LAYER ===

(:Exercise {
  id: string,
  name: string,
  aliases: [string],
  category: string,         // "strength", "conditioning", "mobility"
  movement_pattern: string, // "hinge", "squat", "push", "pull", "carry", "rotation"
  force_type: string,       // "push", "pull"
  mechanic: string,         // "compound", "isolation"
  difficulty: string,       // "beginner", "intermediate", "advanced"
  instructions: string,
  contraindications: [string]
})

(:Equipment {
  id: string,
  name: string,
  category: string,    // "barbell", "kettlebell", "machine", "bodyweight"
  user_has: boolean    // Whether user owns this
})

(:MovementPattern {
  id: string,
  name: string,        // "hip_hinge", "knee_dominant_squat", "horizontal_push"
  description: string
})


// === INJURY/REHAB LAYER ===

(:Injury {
  id: string,
  name: string,
  status: string,      // "active", "recovering", "resolved"
  onset_date: date,
  notes: string
})

(:Constraint {
  id: string,
  description: string,
  constraint_type: string  // "avoid", "limit", "modify"
})

(:RehabPhase {
  id: string,
  name: string,
  week_range: string,   // e.g., "0-2", "2-6", "6-12"
  goals: [string],
  allowed_activities: [string],
  restrictions: [string]
})


// === PERSONAL TRAINING LAYER ===

(:Workout {
  id: string,           // e.g., "2025-11-10_strength"
  date: date,
  type: string,
  sport: string,
  periodization_phase: string,
  planned_intensity: int,
  perceived_intensity: int,
  duration_minutes: int,
  notes: string,
  deviations: [string]
})

(:ExerciseInstance {
  id: string,
  workout_id: string,
  exercise_id: string,
  sets: int,
  reps: string,         // Can be "5,5,5" or "8-10"
  weight: string,       // Can be "135,185,225" or "bodyweight"
  notes: string
})

(:Goal {
  id: string,
  description: string,
  goal_type: string,    // "strength", "endurance", "body_composition", "skill"
  target_metric: string,
  target_value: string,
  deadline: date,
  status: string        // "active", "achieved", "abandoned"
})

(:PeriodizationPhase {
  id: string,
  name: string,         // "build_week_1", "deload", "peak"
  phase_type: string,   // "accumulation", "intensification", "realization", "deload"
  start_date: date,
  end_date: date
})

(:SubjectiveSignal {
  id: string,
  date: date,
  signal_type: string,  // "soreness", "energy", "pain", "sleep", "stress"
  body_part: string,    // optional, for localized signals
  value: string,        // "high", "low", "3/10", etc.
  notes: string
})
```

### 5.2 Relationships

```cypher
// === ANATOMY RELATIONSHIPS ===

(:Muscle)-[:ORIGIN]->(:Bone)
(:Muscle)-[:INSERTION]->(:Bone)
(:Muscle)-[:CROSSES]->(:Joint)
(:Muscle)-[:ACTION {movement: string}]->(:Joint)  // e.g., "flexion"
(:Muscle)-[:PART_OF]->(:MuscleGroup)
(:Muscle)-[:SYNERGIST_TO]->(:Muscle)
(:Muscle)-[:ANTAGONIST_TO]->(:Muscle)

(:Joint)-[:ARTICULATES]->(:Bone)
(:Joint)-[:STABILIZED_BY]->(:ConnectiveTissue)

(:ConnectiveTissue)-[:CONNECTS]->(:Bone)
(:ConnectiveTissue)-[:ATTACHES]->(:Muscle)


// === EXERCISE RELATIONSHIPS ===

(:Exercise)-[:TARGETS {role: "primary"}]->(:Muscle)
(:Exercise)-[:TARGETS {role: "synergist"}]->(:Muscle)
(:Exercise)-[:TARGETS {role: "stabilizer"}]->(:Muscle)

(:Exercise)-[:LOADS]->(:Joint)
(:Exercise)-[:LOAD_PATTERN {type: string}]->(:Joint)  // "compressive", "shear", "rotational"

(:Exercise)-[:REQUIRES]->(:Equipment)
(:Exercise)-[:MOVEMENT_TYPE]->(:MovementPattern)
(:Exercise)-[:VARIATION_OF]->(:Exercise)
(:Exercise)-[:PROGRESSES_TO]->(:Exercise)
(:Exercise)-[:REGRESSES_TO]->(:Exercise)


// === INJURY RELATIONSHIPS ===

(:Injury)-[:AFFECTS]->(:Joint)
(:Injury)-[:AFFECTS]->(:Muscle)
(:Injury)-[:AFFECTS]->(:ConnectiveTissue)

(:Injury)-[:CREATES]->(:Constraint)
(:Constraint)-[:RESTRICTS]->(:Exercise)
(:Constraint)-[:RESTRICTS]->(:MovementPattern)

(:Injury)-[:FOLLOWS_PROTOCOL]->(:RehabPhase)
(:RehabPhase)-[:NEXT]->(:RehabPhase)


// === PERSONAL TRAINING RELATIONSHIPS ===

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

### 5.3 Example Queries

```cypher
// What exercises should I avoid given my meniscus injury?
MATCH (i:Injury {name: "meniscus_tear"})-[:AFFECTS]->(j:Joint)
MATCH (e:Exercise)-[:LOADS]->(j)
MATCH (e)-[:LOAD_PATTERN {type: "rotational"}]->(j)
RETURN e.name, j.name

// What muscles have I trained this week?
MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e:Exercise)
WHERE w.date >= date() - duration('P7D')
MATCH (e)-[:TARGETS]->(m:Muscle)
RETURN m.name, count(ei) as sets_this_week
ORDER BY sets_this_week DESC

// What posterior chain exercises haven't I done in 3+ weeks?
MATCH (m:Muscle {muscle_group: "posterior_chain"})<-[:TARGETS]-(e:Exercise)
WHERE NOT EXISTS {
  MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e)
  WHERE w.date >= date() - duration('P21D')
}
RETURN e.name

// Am I due for a deload? (volume trend)
MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)
WHERE w.date >= date() - duration('P28D')
WITH w.date as workout_date, count(ei) as volume
RETURN workout_date, volume
ORDER BY workout_date

// What exercises progress from my current deadlift?
MATCH (e:Exercise {name: "conventional_deadlift"})-[:PROGRESSES_TO]->(next:Exercise)
RETURN next.name, next.difficulty
```

---

## 6. Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
**Goal**: Graph exists, populated with anatomy and exercises, queryable

**Deliverables**:
1. Neo4j instance running locally
2. Schema created (all node types and relationships)
3. UBERON musculoskeletal subset imported (~500-1000 relevant nodes)
4. free-exercise-db imported (800 exercises with muscle mappings)
5. User's equipment imported from profile.yaml
6. Basic Cypher queries working (see 5.3)

**Scripts to write**:
- `scripts/setup_neo4j.py` - Initialize database, create constraints/indexes
- `scripts/import_uberon.py` - Parse OBO, filter musculoskeletal, load to Neo4j
- `scripts/import_exercises.py` - Parse free-exercise-db JSON, load to Neo4j
- `scripts/import_user_profile.py` - Parse profile.yaml, load equipment

**Validation**:
- Can query: "What muscles does deadlift target?"
- Can query: "What exercises target the gluteus maximus?"
- Can query: "What equipment do I have for pull exercises?"

### Phase 2: Personal Data (Weeks 2-3)
**Goal**: Historical workout data in graph, queryable for trends

**Deliverables**:
1. Parser for Obsidian workout markdown files
2. All 160 workouts imported as Workout + ExerciseInstance nodes
3. Exercises in logs linked to Exercise nodes in graph
4. Temporal relationships established

**Scripts to write**:
- `scripts/parse_workout_log.py` - Parse markdown + YAML frontmatter
- `scripts/import_workout_history.py` - Batch import all workout files
- `scripts/link_exercises.py` - Fuzzy match logged exercises to Exercise nodes

**Validation**:
- Can query: "How many times have I done trap bar deadlift?"
- Can query: "What's my volume trend over the last 4 weeks?"
- Can query: "When did I last train posterior chain?"

### Phase 3: Injuries & Constraints (Week 3)
**Goal**: Injury knowledge encoded, constraints queryable

**Deliverables**:
1. User's injuries imported with affected structures
2. Constraints created and linked to exercises
3. TRAK rehab phases imported (at least knee-relevant portions)

**Scripts to write**:
- `scripts/import_injuries.py` - Parse injuries from profile, create nodes + relationships
- `scripts/import_trak.py` - Parse TRAK OBO, load relevant exercises and protocols
- `scripts/generate_constraints.py` - Create constraint nodes linking injuries to exercises

**Validation**:
- Can query: "What exercises should I avoid with my meniscus injury?"
- Can query: "What phase of knee rehab am I in at 6 weeks?"
- Can query: "What are safe hip hinge variations for my current constraints?"

### Phase 4: LLM Integration (Weeks 3-4)
**Goal**: Claude can query the graph and generate plans

**Deliverables**:
1. MCP server (or Python tool) exposing graph queries to Claude
2. Prompt templates for plan generation
3. Working plan generation in Claude Desktop

**Components**:
- `src/arnold_mcp/` - MCP server with tools:
  - `query_graph(cypher: str)` - Execute Cypher, return results
  - `get_exercise_suggestions(muscle_group, constraints)` - Higher-level tool
  - `get_training_history(days_back, muscle_group?)` - Summarize recent work
  - `log_workout(workout_data)` - Add workout to graph
  - `get_current_constraints()` - Return active injury constraints

**Validation**:
- Can ask Claude: "Generate a push workout for today avoiding overhead pressing"
- Claude queries graph for push exercises, filters by constraints, checks recent history
- Returns structured plan grounded in graph data

### Phase 5: Email Integration (Weeks 4+)
**Goal**: Invisible interface via email

**Deliverables**:
1. Gmail MCP integration
2. Morning plan email generation
3. Reply parsing (workout log, subjective signals)
4. Scheduled execution (cron or similar)

**Components**:
- Gmail MCP for send/receive
- `scripts/daily_plan.py` - Generate and email daily plan
- `scripts/parse_email_reply.py` - Extract workout data from natural language reply
- `scripts/process_inbox.py` - Scan for Arnold-related emails, process

**Email formats**:
```
Subject: [Arnold] Plan for Tuesday Dec 24
Body: <structured plan with exercises, sets, reps, notes>

---

Reply examples to parse:
"Did the workout as planned except dropped the Bulgarian split squats, knee felt off"
"Ran 5 miles, 45 min, felt good, HR around 140"
"Skipped today, still sore from Monday"
```

---

## 7. Repository Structure

```
arnold/
├── README.md
├── docs/
│   ├── SPEC.md                    # This document
│   ├── cyberdyne-fitness-manual.md # Architecture deep-dive (easter egg)
│   └── schema.md                  # Neo4j schema reference
├── scripts/
│   ├── setup_neo4j.py
│   ├── import_uberon.py
│   ├── import_exercises.py
│   ├── import_trak.py
│   ├── import_user_profile.py
│   ├── import_workout_history.py
│   └── parse_workout_log.py
├── src/
│   ├── arnold/
│   │   ├── __init__.py
│   │   ├── graph.py              # Neo4j connection and query utilities
│   │   ├── parser.py             # Workout log parsing
│   │   └── planner.py            # Plan generation logic
│   └── arnold_mcp/               # MCP server (Phase 4)
│       ├── __init__.py
│       └── server.py
├── data/
│   ├── ontologies/               # Downloaded UBERON, TRAK, etc.
│   ├── exercises/                # free-exercise-db clone
│   ├── user/                     # User profile, workout logs (symlink or copy)
│   └── cache/                    # Processed/intermediate files
├── tests/
│   ├── test_parser.py
│   ├── test_queries.py
│   └── test_constraints.py
├── config/
│   ├── neo4j.yaml
│   └── arnold.yaml               # Main config
├── requirements.txt
└── pyproject.toml
```

---

## 8. Configuration

### Neo4j
```yaml
# config/neo4j.yaml
uri: bolt://localhost:7687
user: neo4j
password: <from env>
database: arnold
```

### Arnold
```yaml
# config/arnold.yaml
user:
  profile_path: data/user/profile.yaml
  workout_logs_path: data/user/workouts/

data_sources:
  uberon:
    url: http://purl.obolibrary.org/obo/uberon/basic.obo
    local_path: data/ontologies/uberon.obo
  trak:
    url: http://www.cs.cf.ac.uk/trak/trak.obo
    local_path: data/ontologies/trak.obo
  exercises:
    repo: https://github.com/yuhonas/free-exercise-db
    local_path: data/exercises/

planning:
  default_periodization_weeks: 4
  deload_week: 4
  min_rest_between_muscle_groups_hours: 48

# Skynet parameters (internal codenames)
skycoach:
  enabled: true
  model: claude-sonnet-4-20250514
  temperature: 0.7
```

---

## 9. Easter Eggs & Personality

Arnold should have personality. Not obnoxious, but present.

### Response Templates
```python
GREETINGS = [
    "Come with me if you want to lift.",
    "I'll be back... with your training plan.",
    "Hasta la vista, weakness.",
]

RECOVERY_RECOMMENDATIONS = [
    "Your muscles need time. I need a vacation.",
    "Rest day. Even machines need maintenance.",
    "You are not a machine. I am. Rest.",
]

OVERTRAINING_WARNINGS = [
    "You are terminated... if you keep this up.",
    "I'm a cybernetic organism. You are not. Recover.",
    "This is not a negotiation. Deload.",
]

SUCCESS_MESSAGES = [
    "Excellent. Your form is... adequate.",
    "Target acquired: gains.",
    "Mission accomplished.",
]
```

### Internal Codenames
- MCP server: `skycoach`
- Email agent: `t-800`
- Graph database: `cyberdyne-core`
- Planning engine: `judgment-day` (as in, judging what workout to do)

---

## 10. Success Criteria

### Phase 1 Complete When:
- [ ] Neo4j running with schema
- [ ] 500+ anatomy nodes (muscles, joints) loaded
- [ ] 800+ exercises loaded with muscle mappings
- [ ] User equipment loaded
- [ ] Can run all example queries from section 5.3

### Phase 2 Complete When:
- [ ] All 160 historical workouts imported
- [ ] 90%+ of logged exercises linked to Exercise nodes
- [ ] Can query volume trends, exercise history, muscle coverage

### Phase 3 Complete When:
- [ ] User injuries encoded with constraints
- [ ] Can query "what to avoid" given current injuries
- [ ] TRAK rehab phases available for knee recovery

### Phase 4 Complete When:
- [ ] MCP server running with graph query tools
- [ ] Claude can generate a workout plan using graph data
- [ ] Plan respects injury constraints and recent history

### Phase 5 Complete When:
- [ ] Daily plan emails sent automatically
- [ ] Email replies parsed and logged to graph
- [ ] System runs unattended via cron

---

## 11. Open Questions

1. **Exercise name matching**: User logs say "Deadlift (straight bar)" but exercise DB says "Conventional Deadlift". Need fuzzy matching or alias system. How aggressive?

2. **Intensity/volume calculation**: How to normalize across exercise types? A set of 5 deadlifts at 315 vs a set of 12 KB swings at 70 lb - how to compare load?

3. **Periodization model**: Currently simple 4-week cycle. Should Arnold learn optimal cycle length from data? Or keep it configurable?

4. **Subjective signal weighting**: How much should "felt tired" override the planned workout? Need a model for when to push vs back off.

5. **Running integration**: Ultramarathon training has its own periodization. How to balance with strength periodization? Separate graphs? Unified?

---

## 12. References

### Ontologies
- UBERON: https://obofoundry.org/ontology/uberon.html
- FMA: https://bioportal.bioontology.org/ontologies/FMA
- TRAK: http://www.cs.cf.ac.uk/trak/
- PACO: https://www.jmir.org/2019/4/e12776/

### Exercise Data
- free-exercise-db: https://github.com/yuhonas/free-exercise-db
- ExerciseDB: https://github.com/ExerciseDB/exercisedb-api

### Papers
- "TRAK ontology: Defining standard care for rehabilitation of knee conditions" (Button et al., 2013)
- "Uberon, an integrative multi-species anatomy ontology" (Mungall et al., 2012)
- "Developing a Physical Activity Ontology" (Kim et al., 2019)

---

*"The future has not been written. There is no fate but what we make for ourselves."*
*— Except for leg day. Leg day is fate.*
