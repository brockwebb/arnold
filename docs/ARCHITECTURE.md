# Arnold Architecture — Master Document

> **Purpose**: This document is the authoritative reference for Arnold's architecture. It serves as context handoff between conversation threads and the north star for development decisions.

> **Last Updated**: January 5, 2026 (Journal System Complete)

---

## Executive Summary

Arnold is an AI-native fitness coaching system built on Neo4j. The architecture uses Claude Desktop as the reasoning/orchestration layer, with specialist MCP servers providing domain tools. The critical insight: **Claude IS the orchestrator** — MCPs are tools, not agents.

Arnold is designed as a **proto-human system**: it learns and grows with the user, adapting to their goals, experience level, and life context. It is not a bespoke solution for one athlete, but a foundation for any human pursuing fitness.

---

## North Star: The Digital Twin

Arnold is the first implementation of a broader vision: **personal health sovereignty through data ownership and AI-augmented analysis.**

### The Problem

Everyday people get 15 minutes with a doctor, twice a year. Doctors are specialists with discipline-specific training, knowledge gaps, and anchoring bias from what they learned in school and residency. No single human can see the complete picture of another human's health across all domains and time.

Meanwhile, individuals generate vast amounts of health data—workouts, sleep, heart rate, nutrition, lab work, symptoms, medications—scattered across apps, devices, and medical records they don't control.

### The Vision

A **Digital Twin** is a comprehensive, longitudinal model of a person that:

1. **Aggregates all personal health data** — training, biometrics, medical records, lab work, nutrition, sleep, symptoms, even thoughts and reflections
2. **Owns the data** — privacy-first, user-controlled, portable
3. **Enables pattern detection** — AI agents find correlations humans miss across time and domains
4. **Stays current with research** — deep research agents crawl latest literature, not anchored to outdated training
5. **Augments (not replaces) professionals** — better informed conversations with doctors, coaches, therapists

### The Team Model

Claude orchestrates specialist agents, each with domain expertise:

| Agent | Domain | Role |
|-------|--------|------|
| **Coach** | Fitness/Training | Programming, periodization, exercise selection |
| **Doc** | Medical/Health | Symptom tracking, medication interactions, lab interpretation, rehab protocols |
| **Analyst** | Data Science | Trends, correlations, reports, visualizations |
| **Researcher** | Literature | Latest evidence, protocol recommendations, myth-busting |
| **Scribe** | Documentation | Logging, journaling, reflection capture |

Arnold (Coach) is the first specialist. Others follow the same pattern: MCP tools + Neo4j storage + Claude reasoning.

### Data Sources (Current)

| Source | Data Type | Method | Status |
|--------|-----------|--------|--------|
| Ultrahuman API | Sleep, HRV, resting HR, temp, recovery | Automated daily | ✅ Live |
| Polar Export | HR sessions, TRIMP, zones | Manual weekly | ✅ Live |
| Apple Health | Medical records, labs, BP, meds | Manual monthly | ✅ Live |
| Race History | Historical performance (114 races, 2005-2023) | One-time import | ✅ Done |
| Neo4j Workouts | Training structure, exercises | Automated sync | ✅ Live |

### Why This Matters

This isn't about replacing doctors. It's about:
- **Better conversations** — arrive informed, ask better questions
- **Pattern detection** — "Your HRV drops 3 days before you get sick"
- **Longitudinal insight** — trends over years, not snapshots
- **Privacy** — your data, your control, your choice who sees it
- **Democratization** — elite-level analysis for everyone

Arnold proves the model works. The Digital Twin is where it's going.

### Core Architectural Principles

1. **Modality as Hub** — Training domains (Hip Hinge Strength, Ultra Endurance, etc.) are the central organizing concept. Everything connects through modality.

2. **Block as Fundamental Unit** — Time is organized into blocks (typically 3-4 weeks). Blocks serve goals, contain sessions, and follow periodization models.

3. **Training Level Per Modality** — An athlete can be novice at deadlift and advanced at ultrarunning simultaneously. Progression models are selected per modality.

4. **Science-Grounded** — Periodization models, progression schemes, and coaching logic are grounded in peer-reviewed exercise science.

5. **Graph-First Thinking** — Everything is relationships. Start at any node, traverse to what you need.

---

## Coaching Philosophy

### The Athlete is Here to Be Coached

Arnold is not a Q&A system. The athlete shows up; Arnold assesses, plans, and coaches. The athlete participates but doesn't drive.

**Wrong mental model:**
- Athlete asks question → Claude queries data → Claude answers

**Correct mental model:**
- Athlete shows up → Arnold assesses situation → Arnold coaches proactively

The athlete shouldn't need to know what to ask. Arnold should proactively check relevant data based on context. When an athlete says "I'm feeling tired," Arnold doesn't wait for them to ask about their HRV—he checks it himself and synthesizes.

### Coaching Intensity Scales with Athlete Level

Noobs need more guidance. Experts need synthesis.

| Athlete Level | Coaching Behavior |
|---------------|-------------------|
| **Novice** | Tell them what to do. Prompt for information they don't know to volunteer. Explain the why in simple terms. High touch. |
| **Intermediate** | Offer options with recommendations. Explain tradeoffs. Ask better questions. |
| **Advanced** | Synthesize macro trends. Surface patterns they can't see. Challenge assumptions. Low touch unless requested. |

**Critical insight:** Level is per-modality, not global. Brock is a novice deadlifter but an advanced endurance athlete. He needs hand-holding on hip hinge progression but only macro synthesis on running.

### Transfer Effects and Athletic Background

A "novice" in one modality isn't necessarily a novice athlete. Someone with 35 years of martial arts and 18 years of ultrarunning has:

- **Motor learning capacity** — picks up new movements faster
- **Body awareness / proprioception** — knows what "right" feels like
- **Mental training** — understands progressive overload, deload, periodization concepts
- **Aerobic engine** — work capacity that transfers across domains
- **Recovery patterns** — lifelong athletes recover differently than gen pop

This means their "novice" progression in deadlift will be atypical. They start higher (better foundation) and may progress differently (transfer effects). The TrainingLevel node captures this with `historical_foundation` and `foundation_period` fields.

### Adaptive Feedback Loops

The system should know what information to request based on what it knows about the athlete:

**Noob context:**
- "How did that workout feel?" → Simple scale (Easy / Moderate / Hard / Crushed)
- "Any pain or discomfort?" → Binary with location prompt if yes
- "Did you complete as written?" → Yes/No with deviation capture if no

**Expert context:**
- "Anything notable?" → Open-ended, trust them to surface what matters
- Deviations captured by exception, not interrogation

### RPE Capture (User Experience, Not Logging Problem)

RPE (Rate of Perceived Exertion) is consistently NULL in the data. This isn't a data quality issue—it's a coaching UX gap.

The athlete doesn't know what to report. Arnold should:
1. **Ask post-workout**: "How did that feel?" with anchored options
2. **Correlate with objective data**: If HR monitor shows max effort but athlete says "easy," something's off
3. **Learn their calibration**: Some athletes underreport, some overreport

**Simple scale for capture:**
| Rating | Description | Technical RPE |
|--------|-------------|---------------|
| Easy | Could do much more | 5-6 |
| Moderate | Challenging but manageable | 7 |
| Hard | Few reps left in tank | 8-9 |
| Crushed | Nothing left | 10 |

### Graceful Degradation

Arnold works with what he has. Data gaps are expected (ring left on charger, sensor failed, life happened).

**When data is missing:**
- Don't pretend to know what you don't
- Fall back to simpler heuristics
- Ask the athlete directly
- Note uncertainty in recommendations

**When data is sparse:**
- Use population priors
- Widen confidence intervals
- Be more conservative in recommendations

**When data is rich:**
- Use individual patterns
- Tighten confidence intervals
- Make bolder, personalized recommendations

The `data_completeness` field in daily_metrics (0-4) signals how much Arnold knows about any given day.

### Data Annotation System

Data gaps and anomalies need context. The annotation system provides explanations that:
1. **Reduce false positives** — Don't alarm on explained gaps
2. **Preserve institutional knowledge** — "Why does the data look like this?"
3. **Enable graph relationships** — Link explanations to actual workouts, injuries, plans

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                         NEO4J                                │
│                   (Source of Truth)                          │
│                                                              │
│  (Person)──[:HAS_ANNOTATION]──>(Annotation)                 │
│                                      │                       │
│                              [:EXPLAINS]                     │
│                                      │                       │
│                    ┌─────────────────┼─────────────────┐    │
│                    ▼                 ▼                 ▼    │
│               (Workout)         (Injury)        (PlannedWorkout)│
└─────────────────────────────────────────────────────────────┘
                          │
                    sync_annotations.py
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       POSTGRES                               │
│                   (Analytics Layer)                          │
│                                                              │
│  data_annotations table                                      │
│  ├── annotations_for_date() function                        │
│  ├── active_data_issues view                                │
│  └── Coach Brief report integration                         │
└─────────────────────────────────────────────────────────────┘
```

**Neo4j Annotation Schema:**
```cypher
(:Annotation {
    id: STRING,                    // 'ann-' + uuid
    annotation_date: DATE,
    date_range_end: DATE | null,   // null = ongoing
    target_type: STRING,           // 'biometric', 'workout', 'training', 'general'
    target_metric: STRING,         // 'hrv', 'sleep', 'all', etc.
    reason_code: STRING,           // device_issue, surgery, expected, etc.
    explanation: STRING,
    tags: [STRING],
    is_active: BOOLEAN
})

// Relationships
(Person)-[:HAS_ANNOTATION]->(Annotation)
(Annotation)-[:EXPLAINS {relationship_type}]->(Workout|Injury|PlannedWorkout)
```

**Reason Codes:**
- `device_issue` — Sensor malfunction, app not syncing
- `surgery` — Medical procedure, post-op recovery  
- `injury` — Active injury affecting training
- `expected` — Normal variation (e.g., HRV drop after hard workout)
- `data_quality` — Known data issue, source confusion
- `travel`, `illness`, `deload`, `life` — Other common reasons

**Usage:**
```sql
-- Get annotations for today
SELECT * FROM annotations_for_date(CURRENT_DATE);

-- Active issues for coach brief
SELECT * FROM active_data_issues;
```

See **[DATA_DICTIONARY.md](./DATA_DICTIONARY.md)** for full schema details.

### The Coach Proactively Assesses

Before any planning or response, Arnold should internally:

1. **Load context** — `load_briefing()` for goals, block, recent training
2. **Check readiness** — HRV, sleep, recovery score, recent load
3. **Identify constraints** — injuries, equipment, time available
4. **Surface concerns** — anything trending wrong?

Then synthesize into coaching behavior:

```
Athlete: "What's today's workout?"

Arnold thinks:
- Plan says heavy deadlifts
- But: HRV down 15%, sleep 5.2 hrs, high volume yesterday
- Adjust: "Plan says deadlifts, but your body says otherwise.
  Let's go light technique work today, push heavy to Saturday."
```

The athlete didn't ask about their HRV. Arnold checked anyway. That's coaching.

### What Arnold Explains (And Doesn't)

**Always explain:**
- The plan (what we're doing)
- The why (at appropriate level for athlete)
- The tradeoffs (when relevant)

**Don't over-explain:**
- The data machinery
- The statistical methods
- The confidence intervals (unless asked)

**On request, go deep:**
- "Why?" → reasoning layer
- "Show me the data" → full derivation
- "How confident are you?" → uncertainty quantification

---

## System Architecture

### Data Layer Separation: The Right Brain / Left Brain Model

> **Key Insight (ADR-001):** Neo4j stores *relationships and meaning*. Postgres stores *measurements and facts*.

Arnold uses a hybrid database architecture where each system handles what it does best:

```
┌─────────────────────────────────────────────────────────────┐
│                    POSTGRES (Left Brain)                     │
│              Measurements, Facts, Time-Series                │
│                                                              │
│  biometric_readings    - HRV, RHR, sleep, temp              │
│  endurance_sessions    - FIT imports (runs, rides)          │
│  endurance_laps        - Per-lap splits                     │
│  hr_samples            - Beat-by-beat (optional)            │
│  lab_results           - Blood panels, clinical data        │
│  medications           - Current and historical             │
│  race_history          - Competition results                │
│  log_entries           - Journal/subjective data            │
│  data_annotations      - Time-series context                │
│                                                              │
│  SQL, aggregations, materialized views, analytics           │
└─────────────────────────────┬───────────────────────────────┘
                              │
                         FK references
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     NEO4J (Right Brain)                      │
│              Relationships, Semantics, Knowledge             │
│                                                              │
│  Person, Goal, Modality, Block    - Training structure      │
│  Exercise, MovementPattern, Muscle - Knowledge base         │
│  Injury, Constraint, Protocol      - Medical context        │
│  Annotation (relationships)        - Explanatory links      │
│  WorkoutRef, EnduranceWorkoutRef   - FK to Postgres         │
│                                                              │
│  Graph traversals, pattern matching, "why" queries          │
└─────────────────────────────────────────────────────────────┘
```

**Query Pattern Examples:**

| Question | Database | Why |
|----------|----------|-----|
| "Average HRV last 30 days?" | Postgres | Time-series aggregation |
| "What modalities does this goal require?" | Neo4j | Relationship traversal |
| "All workouts affected by knee injury?" | Neo4j → Postgres | Graph query, then fetch details |
| "TSS trend by week?" | Postgres | Analytical rollup |
| "Why did my performance drop Jan 3?" | Neo4j | Annotation → Workout explanation |

**The Bridge Pattern:**

When data needs to exist in both systems, Postgres holds the detail and Neo4j holds a lightweight reference:

```
Postgres                              Neo4j
┌──────────────────────┐            ┌──────────────────────┐
│ endurance_sessions   │            │ (:EnduranceWorkout)  │
│ id: 12345            │◄──── FK ───►│ postgres_id: 12345   │
│ date, distance, tss  │            │ date (for queries)   │
│ duration, hr, pace   │            │ [:PERFORMED]->Person │
│ ALL the detail       │            │ [:EXPLAINS]<-Annot   │
└──────────────────────┘            └──────────────────────┘
```

See **[ADR-001: Data Layer Separation](./adr/001-data-layer-separation.md)** for full rationale.

---

## Journal System (Subjective Data Capture)

The journal captures **what sensors can't measure** — the subjective experience that completes the Digital Twin.

### What It Captures

| Category | Examples |
|----------|----------|
| Recovery | Fatigue levels, soreness, energy |
| Physical | Symptoms, pain, stiffness, numbness |
| Mental | Mood, stress, motivation |
| Nutrition | Food, hydration, caffeine |
| Medical | Supplements, medications, side effects |
| Training | Workout feedback, form issues, RPE |

### Architecture (ADR-001 Compliant)

```
User: "My right knee feels stiff from yesterday's run"
                    │
                    ▼
            Claude extracts:
            • symptom: stiffness
            • location: right knee
            • cause: running
            • severity: notable
                    │
    ┌───────────────┴───────────────┐
    ▼                               ▼
POSTGRES (facts)              NEO4J (relationships)
log_entries                   (:LogEntry)
  id: 2                         │
  raw_text: "..."           ─[:EXPLAINS]─▶ (:EnduranceWorkout)
  extracted: {...}          ─[:RELATED_TO]─▶ (:Injury {right_knee_meniscus})
  severity: notable
```

**Key Insight**: The graph *knows* about the knee surgery. When the user mentions "right knee" + "stiffness", the relationship to the injury is automatic — no rules, no keywords, just graph traversal.

### Relationship Types

| Relationship | Direction | Meaning |
|--------------|-----------|--------|
| `EXPLAINS` | LogEntry → Workout | Entry explains workout performance |
| `AFFECTS` | LogEntry → PlannedWorkout | Entry should influence future plan |
| `RELATED_TO` | LogEntry → Injury | Entry relates to injury |
| `INFORMS` | LogEntry → Goal | Entry provides goal insight |
| `DOCUMENTS` | LogEntry → Symptom | Entry documents symptom pattern |
| `MENTIONS` | LogEntry → Supplement | Entry mentions supplement |

### MCP Tools (arnold-journal-mcp)

**Entry Creation**:
- `log_entry` — Create entry with Claude-extracted structured data

**Relationship Creation**:
- `link_to_workout` — EXPLAINS a past workout
- `link_to_plan` — AFFECTS a future plan  
- `link_to_injury` — RELATED_TO an injury
- `link_to_goal` — INFORMS a goal

**Retrieval (Postgres)**:
- `get_recent_entries` — Last N days
- `get_unreviewed_entries` — For coach/doc briefings
- `get_entries_by_severity` — Notable/concerning/urgent
- `search_entries` — Filter by tags, type, category

**Retrieval (Neo4j)**:
- `get_entries_for_workout` — All entries explaining a workout
- `get_entries_for_injury` — All entries related to an injury
- `get_entries_with_relationships` — Entries with all their links

**Discovery**:
- `find_workouts_for_date` — Find workouts to link
- `get_active_injuries` — Find injuries to link
- `get_active_goals` — Find goals to link

### Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `info` | Routine observation | Log only |
| `notable` | Worth tracking | Include in briefings |
| `concerning` | Needs attention | Flag for review |
| `urgent` | Immediate action | Alert |

### Usage Flow

1. User shares observation naturally: *"Legs are toast from yesterday's run"*
2. Claude extracts structured data (fatigue level, body part, cause)
3. `log_entry` creates Postgres record + Neo4j node
4. Claude finds related entities (yesterday's workout, any injuries)
5. `link_to_*` tools create graph relationships
6. Entry appears in future briefings with full context

See `/src/arnold-journal-mcp/README.md` for full documentation.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONTEXT WINDOW                             │
│                   (Claude's Working Memory)                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ System Prompt                                              │ │
│  │ + Coach Briefing (loaded from memory layer)                │ │
│  │ + Retrieved relevant context (RAG)                         │ │
│  │ + Current conversation                                     │ │
│  │ + Tool results                                             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  If it's not in this window, Claude doesn't know it.           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLAUDE DESKTOP (LLM)                         │
│               ═══════════════════════════════                   │
│                                                                 │
│  • Reasoning engine                                             │
│  • Orchestration decisions (which tools to call)                │
│  • Natural language understanding                               │
│  • Persona: Coach, with access to specialists                   │
│                                                                 │
└───────────────┬─────────────┬─────────────┬─────────────────────┘
                │             │             │
                ▼             ▼             ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐
         │ Profile  │  │ Training │  │  Memory  │
         │   MCP    │  │   MCP    │  │   MCP    │
         └────┬─────┘  └────┬─────┘  └────┬─────┘
              │             │             │
              └─────────────┴─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │   NEO4J     │
                     │  (Storage)  │
                     └─────────────┘
```

### Key Insight: Claude IS the Orchestrator

There is no separate "orchestrator MCP." Claude Desktop performs orchestration by:
1. Understanding the user's intent
2. Deciding which tools to call
3. Synthesizing results into coherent responses
4. Maintaining conversation context

MCPs are **specialist tool collections**, not autonomous agents. They don't reason, decide, or call each other.

---

## Core Data Model

### The Graph Structure

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

### Node Types

#### Modality (The Hub)

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

Extensible — add modalities as needed for new training domains.

#### Goal

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

#### TrainingLevel (Per Person-Modality)

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

#### PeriodizationModel (Library)

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

#### Block (The Fundamental Time Unit)

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

The coach uses seasonal language naturally ("This spring we're transitioning to race prep") but the underlying data is just blocks with dates.

#### Session Structure (Unchanged)

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

// Execution
(:Workout)-[:EXECUTED_FROM]->(:PlannedWorkout)
(:Set)-[:DEVIATED_FROM]->(:PlannedSet)
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

## Memory Architecture

### The Problem

Every conversation, Claude starts fresh. Without explicit context loading, Claude doesn't know:
- What goals are active
- What block we're in
- Training level per modality
- What happened last workout
- Active injuries or constraints

### The Solution: Three-Tier Memory

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHORT-TERM MEMORY                            │
│                   (Context Window)                              │
│                                                                 │
│  Current conversation + loaded briefing + tool results          │
│  ~200k tokens, refreshes each conversation                      │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              │ load/store
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MID-TERM MEMORY                              │
│               (Summaries + Embeddings)                          │
│                                                                 │
│  • Block summaries: "Accumulation complete, 16 sessions..."     │
│  • Week summaries: "Week 3: volume peaked, technique solid"     │
│  • Coaching observations: "Fatigue pattern on deadlift set 3"   │
│  • Vector embeddings for semantic search                        │
│                                                                 │
│  Stored as Summary nodes in Neo4j with embeddings               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              │ compress/retrieve
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LONG-TERM MEMORY                             │
│                  (Complete Graph)                               │
│                                                                 │
│  Every workout, every set, every rep                            │
│  All relationships, all history                                 │
│  Full fidelity, queryable but not loaded wholesale              │
│                                                                 │
│  This is Neo4j — the "disk"                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Memory Operations

| Operation | Description |
|-----------|-------------|
| **load_briefing** | Get essential state for conversation start |
| **search_observations** | Semantic retrieval via vector similarity (Phase 2) |
| **store_observation** | Persist insight with auto-generated embedding |
| **get_observations** | Tag/type filtered retrieval (non-semantic) |
| **get_block_summary** | Get or generate block summaries |
| **store_block_summary** | Persist block summary with learnings |

### Semantic Search (Phase 2 - Implemented)

Observations are embedded using OpenAI's `text-embedding-3-small` model (1536 dimensions) and indexed in Neo4j's native vector index (`obs_embedding_index`) for cosine similarity search.

```
search_observations("why does my deadlift break down?")
        │
        ▼
┌─────────────────┐
│ Embed Query     │ → [0.018, -0.142, 0.095, ...] (1536 floats)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  db.index.vector.queryNodes('obs_embedding_index', ...)         │
│  Returns: "Fatigue pattern emerges..." (0.87 similarity)        │
└─────────────────────────────────────────────────────────────────┘
```

This enables natural language queries over coaching memory without exact keyword matching.

---

## Exercise Matching Architecture

### The Problem

Exercise matching was failing because we asked the database to do semantic work:

| User Says | DB Has | Result |
|-----------|--------|--------|
| "KB swing" | "Kettlebell Swing" | ❌ Not found |
| "pull up" | "Pullups" | ❌ Wrong match |
| "landmine press" | — | ❌ Missing from DB |

### The Solution: Layered Responsibility

**Core insight: Claude IS the semantic layer. The database is the retrieval layer.**

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEMANTIC LAYER (Claude)                      │
│  "KB swing" → "Kettlebell Swing"                                │
│  Normalization, synonym resolution, context understanding       │
│  Stop outsourcing this to DB — Claude does it naturally         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL LAYER (Neo4j)                       │
│  Full-text index: Fast fuzzy matching on name + aliases         │
│  Vector index: Semantic similarity for long tail                │
│  Returns candidates → Claude picks best match                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ENRICHMENT LAYER (Graph)                      │
│  Exercise nodes with: aliases, common_names, descriptions       │
│  Embeddings added incrementally as exercises are touched        │
└─────────────────────────────────────────────────────────────────┘
```

### Exercise Node Enrichment

```cypher
(:Exercise {
  id: string,
  name: string,                    // Canonical name
  aliases: [string],               // ["KB swing", "Russian swing"]
  common_names: [string],          // ["Kettlebell Swing", "Two-Hand KB Swing"]
  description: string,             // For vector embedding
  equipment_required: [string],    // ["kettlebell"]
  embedding: [float]               // 1536-dim (added incrementally)
})
```

### Indexes

**Full-text index** for fast fuzzy matching:
```cypher
CREATE FULLTEXT INDEX exercise_search IF NOT EXISTS
FOR (e:Exercise)
ON EACH [e.name, e.aliases, e.common_names]
```

**Vector index** for semantic search:
```cypher
CREATE VECTOR INDEX exercise_embedding_index IF NOT EXISTS
FOR (e:Exercise)
ON e.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}}
```

### Incremental Embedding Strategy

**Don't embed 4,242 exercises upfront.** Add embeddings incrementally:

1. **On exercise use** — When logged/planned, if no embedding, generate one
2. **On alias addition** — Regenerate embedding from enriched text
3. **Batch backfill** — Low-priority background job

The system gets smarter with use. Ship incrementally, improve continuously.

### Tool Redesign

Replace `find_canonical_exercise` (exact match) with `search_exercises` (returns candidates):

```python
def search_exercises(query: str, limit: int = 5) -> list:
    # 1. Full-text first (fast, handles typos)
    results = fulltext_search(query)
    
    # 2. If sparse, fall back to vector search
    if len(results) < 2:
        results += vector_search(query)
    
    return results  # Claude picks the right one
```

Claude's role:
- Normalize input before searching ("KB" → "Kettlebell")
- Evaluate candidates and select best match
- Create custom exercise with MAPS_TO if nothing fits

### Implementation Status

See **[exercise_kb_improvement_plan.md](./exercise_kb_improvement_plan.md)** Phase 8 for full details.

| Component | Status |
|-----------|--------|
| Full-text index (`exercise_search`) | ✅ Live |
| Vector index (`exercise_embedding_index`) | ✅ Live |
| Exercise node enrichment schema | ✅ Designed |
| Initial aliases (51 exercises) | ✅ Complete |
| Incremental embedding pipeline | 📝 Add as used |
| Gap filling (missing exercises) | ✅ Core gaps filled |

---

## Analytics Architecture ("The Analyst")

### Design Philosophy: Data Lake, Not Data Warehouse

Key insight: **Solve problems you can observe, not problems you imagine.**

Rather than prematurely optimizing with star schemas and dimensional models, Arnold uses a data lake approach:

1. **Raw stays raw** — Never destroy source fidelity
2. **Staging is dumb** — Just flattened Parquet, easy to rebuild
3. **Intelligence is external** — Catalog describes, doesn't prescribe
4. **Transform at runtime OR pre-build** — Your choice per use case

### The OLTP/OLAP Split

Neo4j excels at relationships and graph traversal (coaching workflows). Analytics wants denormalized tables with SQL. Arnold uses both:

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                │
│  Apple Health │ Suunto │ Ultrahuman │ Labs │ Manual Entry        │
└─────────────────────────────────┬───────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAW (Native Format)                          │
│  /arnold/data/raw/{source}/ — Untouched source files           │
│  .fit, .json, .xml, .csv — never lose fidelity                 │
└─────────────────────────────────┬───────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGING (Parquet)                            │
│  /arnold/data/staging/*.parquet — Flattened, minimal transform │
│  Just columnar conversion, no joins, no aggregation             │
└─────────────────────────────────┬───────────────────────────────┘
                                            │
              ┌─────────────────────────┼─────────────────────────┐
              │                           │                         │
              ▼                           ▼                         ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────┐
│       Neo4j           │   │       DuckDB          │   │  Data Catalog │
│   (Relationships)     │   │    (Analytics)        │   │   (Registry)  │
│                       │   │                       │   │               │
│ • Coaching workflow   │   │ • Time-series queries │   │ • What exists │
│ • Graph traversal     │   │ • Aggregations        │   │ • Freshness   │
│ • Exercise selection  │   │ • Pre-computed views  │   │ • Schema info │
│ • Plan → Execute flow │   │ • Dashboard feeds     │   │ • Fitness for │
│ • Semantic search     │   │ • Custom SQL          │   │   use         │
└───────────────────────┘   └───────────────────────┘   └───────────────┘
```

### Why DuckDB

| Feature | Benefit |
|---------|---------|  
| Embedded | No server, just a file (`arnold_analytics.duckdb`) |
| Columnar | Blazing fast aggregations and time-series |
| Parquet-native | Reads staging files directly |
| Full SQL | Claude generates queries naturally |
| Python/pandas | Easy integration with notebooks, exports |

### Data Flow: Scalable Ingestion

New data sources follow the same pattern:

```
1. IMPORT    →  Raw data lands in /staging/{source}/
2. CATALOG   →  Register in data catalog (schema, grain, freshness)
3. TRANSFORM →  Clean, normalize, load to DuckDB
4. SYNC      →  If graph relationships needed, sync to Neo4j
5. VIEW      →  Create/update pre-computed views
```

**Example: Adding Apple Health**

```
/data/staging/apple_health/
  ├── sleep_2024.parquet
  ├── sleep_2025.parquet
  ├── hrv_2024.parquet
  ├── resting_hr_2025.parquet
  └── _manifest.json          # Schema, last_import, row_counts
```

### Data Catalog (Registry)

The catalog lets Claude (and tools) answer: "What data do we have? Is this query answerable?"

```python
# /data/catalog.json
{
  "tables": {
    "workouts": {
      "source": "neo4j_export",
      "location": "duckdb:workouts",
      "grain": "workout_id",
      "freshness": "daily",
      "row_count": 163,
      "date_range": ["2024-04-01", "2025-12-31"],
      "columns": {
        "date": {"type": "date", "nullable": false},
        "type": {"type": "string", "values": ["strength", "conditioning", "mobility"]},
        "duration_min": {"type": "int", "nullable": true},
        "total_sets": {"type": "int"},
        "total_reps": {"type": "int"}
      }
    },
    "sets": {
      "source": "neo4j_export",
      "grain": "set_id",
      "row_count": 2445,
      "columns": {...}
    },
    "apple_health_sleep": {
      "source": "apple_health_export",
      "grain": "date",
      "freshness": "weekly",
      "columns": {...}
    }
  }
}
```

### Pre-Computed Views

| View | Grain | Refresh | Use Case |
|------|-------|---------|----------|
| `daily_training_volume` | date | Daily | Training load dashboard |
| `weekly_summary` | year-week | Weekly | Week-over-week trends |
| `exercise_progression` | date × exercise | Daily | Track lifts over time |
| `goal_progress` | date × goal | Daily | Distance to target |
| `body_metrics` | date | Daily | Weight, HRV, resting HR |
| `movement_pattern_freq` | week × pattern | Weekly | Balance across patterns |
| `block_summary` | block_id | On block close | Block retrospectives |

### Output Modes

**1. Dashboard (Pre-Computed)**

Standardized views refreshed on schedule. Always ready, no query latency.

```sql
-- Weekly training volume (pre-computed)
SELECT week, total_sets, total_reps, session_count
FROM weekly_summary
ORDER BY week DESC
LIMIT 12;
```

**2. Hot Reports (On-Demand Intelligence)**

Ad-hoc analysis that surfaces patterns and anomalies. Claude generates these in response to questions or proactively.

```
🔥 HOT REPORT: Week 52 Analysis

Volume: 47 sets (+12% vs 4-week avg)
Intensity: 72% of sets @RPE 7+ (normal)
Pattern Gap: No horizontal pull in 10 days ⚠️

Notable:
• Deadlift trending up: 275→295→315 over 3 sessions
• Sleep avg 6.2 hrs (down from 7.1 last month)
• HRV elevated post-surgery, stabilizing

Suggestion: Add rowing or face pulls to Thursday
```

**3. Exploratory (Custom SQL)**

When the data intelligence layer knows what exists, Claude can write custom queries:

```sql
-- "How does my deadlift correlate with sleep?"
SELECT 
  s.date,
  s.load_lbs,
  b.sleep_hours,
  b.hrv_ms
FROM sets s
JOIN body_metrics b ON s.date = b.date
WHERE s.exercise_name ILIKE '%deadlift%'
ORDER BY s.date;
```

**4. Visual Artifacts (React)**

Interactive charts for exploration:
- Progress toward goals (line chart)
- Volume distribution by pattern (stacked bar)
- Training calendar heatmap
- Correlation matrices

### File Structure

```
/arnold/data/
├── raw/                        # Native format, untouched
│   ├── neo4j_snapshots/        # JSON exports from graph
│   ├── ultrahuman/             # API syncs + manual exports
│   ├── apple_health/           # XML exports (aggregates all sources)
│   ├── garmin/                 # Historical .FIT files
│   ├── race_logs/              # Manual historical data
│   └── labs/                   # PDF/CSV lab results
├── staging/                    # Parquet, minimal transform
│   ├── workouts.parquet
│   ├── sets.parquet
│   ├── ultrahuman_daily.parquet
│   └── apple_health_*.parquet
├── catalog.json                # ✅ Data intelligence (CREATED)
├── sources.json                # Source registry (APIs, exports, schemas)
├── arnold_analytics.duckdb     # Analytics database (pending)
└── exports/                    # Generated reports, charts
```

### Data Sync Scripts

```
/arnold/scripts/sync/
├── sync_ultrahuman.py          # API sync (requires .env credentials)
├── stage_ultrahuman.py         # CSV/JSON → Parquet
├── import_apple_health.py      # XML → Parquet (streaming parser)
└── import_garmin_fit.py        # .FIT → Parquet
```

---

## Analytics Intelligence Framework

Arnold's analytics layer is not a static dashboard—it's a **closed-loop control system** that learns and adapts to the individual.

### Control Systems Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENSORS (Measurement)                        │
│  Wearables, labs, manual entry, workouts                        │
│  Each with known error bounds and confidence                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OBSERVER (State Estimation)                  │
│  What's the current state? What patterns exist?                 │
│  Bayesian updating, uncertainty quantification                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROLLER (Decision Logic)                  │
│  Given state + goals + constraints → recommendations            │
│  Risk-neutral, dampened response to noise                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ACTUATOR (Interventions)                     │
│  Training plan, rest day, intensity adjustment                  │
│  Coach makes recommendation, human decides                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PLANT (The Individual)                       │
│  Biological system with unique response characteristics         │
│  The thing we're trying to optimize                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ (response)
                            ▼
                    Back to SENSORS
```

### System Lifecycle

| Phase | What Happens | Uncertainty |
|-------|--------------|-------------|
| **Startup** | Initial data collection, baseline estimation | High — wide credible intervals |
| **Calibration** | Learning individual response curves, tuning priors | Medium — intervals narrowing |
| **Loop Tuning** | Adjusting dampening, identifying lag structures | Medium-Low — patterns stabilizing |
| **Optimization** | Exploiting learned patterns, fine-tuning | Low — confident interventions |

The system **never stops learning**. Even in optimization phase, beliefs update, drift is detected, new patterns emerge.

### Bayesian Evidence Framework

**Why not p-values?** P < 0.05 is a binary gate that:
- Treats p=0.049 and p=0.051 completely differently
- Answers the wrong question ("probability of data given null" ≠ "probability effect is real")
- Ignores prior knowledge
- Doesn't account for multiple testing

**Instead, we use:**

```python
class PatternEvidence:
    """Represents belief about a discovered pattern."""
    
    # Effect
    effect_size: float              # Point estimate
    credible_interval: tuple        # (low, high) - 95% HDI
    effect_direction: str           # "positive", "negative", "unclear"
    
    # Confidence
    prior_plausibility: float       # 0-1, based on domain knowledge
    posterior_probability: float    # 0-1, P(real | data)
    bayes_factor: float             # Strength of evidence vs null
    
    # Stability
    temporal_consistency: float     # Does it hold across time windows?
    sample_size: int
    
    # Actionability
    effect_meaningful: bool         # Is effect size large enough to matter?
    intervention_available: bool    # Can we do anything about it?
    
    def evidence_grade(self) -> str:
        """
        Returns: 'strong', 'moderate', 'suggestive', 'weak', 'insufficient'
        
        NOT a binary gate. A communication tool.
        Underlying numbers always available.
        """
```

### Prior Sources (Confidence-Weighted)

| Source | Confidence | Use |
|--------|------------|-----|
| Peer-reviewed literature | High | Population-level priors |
| Exercise science consensus | High | Physiological plausibility |
| Your historical data | Very High | Individual response patterns |
| Single studies | Medium | Hypothesis generation |
| Expert opinion | Medium | Where data sparse |
| Pseudoscience measurements | Low | Trend-only, cross-validate |

### Dampening and Noise Handling

**Risk-neutral approach:** Don't chase noise, but don't ignore persistent signals.

```python
class SignalProcessor:
    def process_observation(self, new_data, pattern):
        # 1. Update estimate with dampening (learned per-pattern)
        alpha = self.get_dampening_factor(pattern)
        smoothed = alpha * new_data + (1 - alpha) * self.current_estimate
        
        # 2. Track persistence
        if signal_direction_consistent(new_data, window=7):
            pattern.persistence_count += 1
        else:
            pattern.persistence_count = max(0, pattern.persistence_count - 1)
        
        # 3. Escalate attention if persistent
        if pattern.persistence_count > threshold:
            flag_for_investigation(pattern)
            # "This keeps showing up. Let's look closer."
        
        # 4. Update uncertainty bounds
        pattern.credible_interval = update_interval(
            prior=pattern.credible_interval,
            new_evidence=new_data
        )
```

### Transparency Architecture

**Three layers of explanation, available on demand:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER-FACING OUTPUT                           │
│  "Your HRV is down. Consider a lighter session today."          │
│  Simple. Actionable. No jargon.                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │ [Why?]
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    REASONING LAYER                              │
│  "HRV is 18% below your 7-day average. Based on 180 days of     │
│  your data, this predicts elevated RPE (+1.2 on average).       │
│  Confidence: moderate (CI: 0.8-1.6 RPE points)."                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ [Show me the math]
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FULL DERIVATION                              │
│  Model: Bayesian linear regression                              │
│  Prior: N(0.5, 0.3) based on literature + Q1-Q2 data            │
│  Likelihood: N(1.2, 0.4) from current data                      │
│  Posterior: N(1.05, 0.25)                                       │
│  Credible interval: [0.56, 1.54] 95% HDI                        │
│  Bayes factor vs null: 4.2 (moderate evidence)                  │
│  Raw data: [attached], Code: [link to computation]              │
└─────────────────────────────────────────────────────────────────┘
```

**Every recommendation is traceable to source data and explicit assumptions.**

### Individualization as First Principle

Population studies tell us: "On average, sleep affects recovery."

Your data tells us: "For YOU, sleep 2 nights ago matters more than last night, the effect is ~0.8 RPE points per SD of sleep score, and this holds except during deload weeks."

```python
# Population prior (from literature)
population_effect = Normal(mean=0.5, std=0.3)

# Your data updates the prior
your_posterior = update(
    prior=population_effect,
    likelihood=your_data_likelihood
)

# With enough data, your posterior dominates
# With sparse data, fall back toward population
# Automatic regularization via Bayesian updating
```

**What's important for you ≠ what's important for everyone.** The system learns YOUR transfer functions, YOUR lag structures, YOUR response curves.

### Value Extraction Pipeline

```
RAW MEASUREMENTS (Parquet)
    │
    ▼
FEATURE ENGINEERING (DuckDB + Python)
    Rolling averages, deltas, lag features, z-scores
    │
    ▼
PATTERN DETECTION (Statistical + ML)
    Correlation, regression, clustering, anomaly detection
    │
    ▼
DISCOVERED KNOWLEDGE (Neo4j)
    Patterns become graph nodes with relationships
    │
    ▼
COACHING DECISIONS (Claude)
    Knowledge informs recommendations
```

**Raw time-series stays tabular. Discovered patterns become graph relationships.**

### Training Metrics Specification

For evidence-based training metrics with full citations, see **[TRAINING_METRICS.md](./TRAINING_METRICS.md)**.

Key metrics by tier:

**Tier 1 (From Logged Workouts)**:
- Volume Load (tonnage)
- ACWR (Acute:Chronic Workload Ratio) using EWMA
- Training Monotony & Strain
- Sets per muscle group per week
- Movement pattern frequency
- Exercise progression (estimated 1RM)

**Tier 2 (Requires Biometric Data)**:
- Readiness Score (HRV + sleep + RHR)
- hrTSS (heart rate-based Training Stress Score)
- ATL/CTL/TSB (Acute/Chronic Training Load, Training Stress Balance)

**Tier 3 (Requires External Platform Export)**:
- Suunto TSS (not available via Apple Health sync)
- rTSS (pace-based running TSS)

All formulas and thresholds are cited to peer-reviewed sports science literature.

### Visualization Dashboards (Streamlit)

Standalone Streamlit apps provide interactive visualization without requiring MCP integration:

**Muscle Heatmap Dashboard** (`src/muscle_heatmap.py`)

Visualizes training load distribution across muscle groups.

| Component | Description |
|-----------|-------------|
| Stack | Streamlit + DuckDB (reads Parquet directly) |
| Math | Weber-Fechner logarithmic normalization |
| Input | `sets.parquet`, `muscle_targeting.csv` |
| Features | Date range picker, rolling window, role weighting |

**Why log normalization?** Legs handle 300lb squats while biceps work with 25lb curls. Linear scaling would wash out small muscles. Weber-Fechner law: human perception of intensity is logarithmic.

**Per-muscle log_factor:** Each muscle has a sensitivity multiplier stored in `muscle_svg_mapping.json`. Quads get compressed (0.6), rear delts get amplified (1.8). This normalizes "effort" across muscle sizes.

Run: `streamlit run src/muscle_heatmap.py`

Future: SVG body diagram overlay once appropriate licensed assets are sourced.

---

## Coach Workflow

### Before Any Planning

The coach must answer:
1. **What are the goals?** (Goal nodes)
2. **What modalities do they require?** (Goal → Modality)
3. **What's the training level per modality?** (TrainingLevel)
4. **What block are we in?** (Active Block)
5. **What should today accomplish?** (Session intent from block)

### Session Generation Flow

```
1. Load briefing (memory)
2. Check constraints (injuries, equipment)
3. Identify modalities to train (from block focus)
4. Check training levels for those modalities
5. Apply appropriate progression model per modality
6. Select exercises (graph query)
7. Structure session (blocks, sets, loads)
8. Present plan (compact, phone-readable)
9. Confirm or adjust
10. Execute
11. Reconcile (deviations, observations)
12. Update memory (summarize if needed)
```

### Check-in Cadence

| When | Purpose |
|------|---------|
| Block start | What's the intent, what are we doing |
| Block end | What happened, what did we learn |
| Weekly brief | Here's the week, any issues? |
| After deviation | Life happened, let's recalibrate |
| On request | Athlete has questions/concerns |

### What the Coach Explains

1. **The Plan** — "This block is 4 weeks of accumulation. We're building work capacity."

2. **The Why** — "You're 12 months from Hellgate. This base phase supports the volume you'll need in fall. Your deadlift is progressing linearly because you're new to it."

3. **The Tradeoffs** — "Running volume will be moderate because we're also building strength. When we shift to race-specific prep, strength becomes maintenance only."

4. **The Data** — "Your deadlift went from 225x5 to 315x5 in 8 weeks. That's novice gains."

5. **The Ask** — "How are you feeling? Anything I should know?"

---

## MCP Roster

### Currently Implemented

| MCP | Role | Status |
|-----|------|--------|
| **arnold-journal-mcp** | Subjective data capture, relationship linking | ✅ Operational |
| **arnold-profile-mcp** | Person, equipment, observations, activities | ✅ Operational |
| **arnold-training-mcp** | Planning, exercise selection, workout logging | ✅ Operational |
| **arnold-memory-mcp** | Context management, briefings, observations | ✅ Operational |
| **arnold-analytics-mcp** | Metrics, trends, readiness, red flags | ✅ Operational |
| **neo4j-mcp** | Direct graph queries | ✅ External |
| **postgres-mcp** | Analytics queries, index tuning | ✅ External |

### To Build (The Team)

| MCP | Persona | Role | Priority |
|-----|---------|------|----------|
| **arnold-medical-mcp** | Doc | Health tracking, symptoms, labs, rehab | 🟡 Medium |
| **arnold-checkin-mcp** | Coach | Structured check-ins, progress reviews | 🟡 Medium |
| **arnold-research-mcp** | Researcher | Literature search, protocol recommendations | 🟢 Low |
| **arnold-scribe-mcp** | Scribe | Journaling, reflection, thought capture | 🟢 Low |

### Tool Distribution

**arnold-journal-mcp**
```
// Entry Creation
log_entry

// Relationship Creation  
link_to_workout, link_to_plan, link_to_injury, link_to_goal

// Retrieval (Postgres - Facts)
get_recent_entries, get_unreviewed_entries, get_entries_by_severity
get_entries_for_date, search_entries

// Retrieval (Neo4j - Relationships)
get_entries_for_workout, get_entries_for_injury, get_entries_with_relationships

// Discovery
find_workouts_for_date, get_active_injuries, get_active_goals

// Management
update_entry, mark_reviewed
```

**arnold-profile-mcp**
```
intake_profile, complete_intake, create_profile, get_profile, update_profile
setup_equipment_inventory, list_equipment
add_activity, list_activities
record_observation
find_canonical_exercise
```

**arnold-training-mcp**
```
// Context
get_coach_briefing, get_training_context, get_active_constraints

// Exercise Selection
suggest_exercises, check_exercise_safety, find_substitutes

// Planning
create_workout_plan, get_plan_for_date, get_planned_workout, confirm_plan

// Execution
complete_as_written, complete_with_deviations, skip_workout, log_workout

// History
get_workout_by_date, get_recent_workouts
```

**arnold-memory-mcp**
```
load_briefing         # Comprehensive context for conversation start
store_observation     # Persist coaching insights (auto-embeds)
search_observations   # Semantic search via vector similarity (NEW)
get_observations      # Retrieve past observations (tag/type filter)
get_block_summary     # Get/generate block summaries
store_block_summary   # Store block summary
```

**arnold-checkin-mcp** (To Build)
```
conduct_checkin      # Generate and run a check-in conversation
schedule_checkin     # Set up future check-in
get_checkin_history  # What we discussed, decisions made
```

---

## Data Model Summary

### Graph Health (as of Jan 4, 2026)

| Node Type | Count |
|-----------|-------|
| Exercise | 4,242 |
| Workout | 165 |
| Set | 2,500+ |
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
| **Annotation** | **4** |
| Person | 1 |

### Key Relationships

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

---

## Output Formats

### Compact Session (Phone-Readable)

```
TUE DEC 30 - VERTICAL PULL/PUSH (~50 min)

WARM-UP
• Chin-Up 1×5 @5
• Ring Dips 1×8 @5

MAIN
• Chin-Up 4×6 @8 (add weight if easy)
• KB Push Press 4×5/arm 55lb @7

ACCESSORY
• Ring Dips 3×10 @7 (3s negative)

FINISHER
• Ab Rollout 2×10 @7
```

### Weekly Preview

```
WEEK 1 OF 4 — ACCUMULATION
Dec 30 - Jan 5

Tue 30: Vertical Pull/Push ✓
        Chin-Up, KB Press, Ring Dips

Wed 31: [not planned]

Thu  2: [not planned]
...
```

### Seasonal View

```
WINTER 2025-26 (Dec - Feb)
Theme: Rebuild base post-surgery

Block 1: ACCUMULATION ◀── CURRENT (Week 1 of 4)
         Focus: Work capacity, movement patterns

Block 2: TRANSMUTATION (Jan 27)
         Focus: Strength emphasis

Block 3: DELOAD (Feb 17)
         Focus: Recovery, consolidation
```

---

## Development Roadmap

### Completed (Dec 30-31, 2025)
1. ✅ Create Modality nodes (14 modalities)
2. ✅ Create PeriodizationModel library (Linear, Undulating, Block)
3. ✅ Create Goal nodes (4 goals with [:REQUIRES]->Modality)
4. ✅ Create TrainingLevel per modality (6 levels)
5. ✅ Update get_coach_briefing for new model
6. ✅ Delete Athlete nodes, Person direct to Workout
7. ✅ Delete TrainingPlan, Blocks direct to Person
8. ✅ Update MCP neo4j_client.py for new schema
9. ✅ **arnold-memory-mcp built and operational** - load_briefing working
10. ✅ Ring Dips goal + Shoulder Mobility protocol created
11. ✅ MobilityLimitation tracking for shoulder
12. ✅ **arnold-memory-mcp Phase 2: Semantic Search** - Neo4j vector index + OpenAI embeddings
13. ✅ **Training Metrics Specification** - TRAINING_METRICS.md with full citations

### Phase 1: Core Coaching Loop (Current)

| Task | Status | Notes |
|------|--------|-------|
| Weekly planning workflow | ⏳ | Plan Week 1 sessions |
| Live fire test | ⏳ | Plan → Execute → Reconcile end-to-end |
| Start logging observations | ⏳ | Build coaching memory over time |

### Phase 2: Analytics ("The Analyst")

| Task | Status | Notes |
|------|--------|-------|
| Data Lake Architecture | ✅ | Raw → Staging → Analytics design complete |
| Data catalog/registry | ✅ | `/data/catalog.json` with schema, fitness for use |
| Directory structure | ✅ | `/data/raw/`, `/data/staging/`, `/data/exports/` |
| Export script | ✅ | `/scripts/export_to_analytics.py` ready to run |
| Training Metrics Spec | ✅ | TRAINING_METRICS.md - ACWR, TSS, volume targets w/ citations |
| Export Neo4j to Parquet | ⏳ | Run script on local machine |
| Create DuckDB database | 📋 | `arnold_analytics.duckdb` |
| Tier 1 metrics | 📋 | ACWR, monotony, strain, pattern frequency |
| arnold-analytics-mcp | 📋 | Query interface, report generation |
| Core views | 📋 | daily_volume, weekly_summary, exercise_progression |
| Goal progress tracking | 📋 | Deadlift trajectory, distance to target |
| Hot reports | 📋 | On-demand pattern detection, anomalies |
| Visual artifacts | 📋 | React charts for exploration |

### Phase 3: Medical Support ("Doc")

| Task | Status | Notes |
|------|--------|-------|
| arnold-medical-mcp | 📋 | Health tracking, constraints |
| Symptom logging | 📋 | Pain, fatigue, illness tracking |
| Medication tracking | 📋 | What you're taking, interactions |
| Lab work import | 📋 | Blood panels, trends over time |
| Rehab protocol management | 📋 | Post-injury/surgery progression |
| Clearance logic | 📋 | "Safe to return to X" decisions |
| Research agent integration | 📋 | Latest literature on conditions |

### Phase 4: Data Integration

| Task | Status | Notes |
|------|--------|-------|
| Apple Health import | 📋 | Sleep, HRV, resting HR, steps |
| Garmin/Strava sync | 📋 | Run/ride data, GPS, training load |
| Body composition logging | 📋 | Weight, measurements, photos |
| Nutrition tracking | 📋 | Macros, meal timing |
| Subjective logging | 📋 | Energy, mood, stress, sleep quality |

### Phase 5: Digital Twin Foundation

| Task | Status | Notes |
|------|--------|-------|
| Unified Person schema | 📋 | All data sources → one graph |
| Cross-domain correlation | 📋 | Sleep ↔ performance, HRV ↔ readiness |
| Longitudinal views | 📋 | Years of data, trend analysis |
| Research agent ("Researcher") | 📋 | Literature search, protocol recommendations |
| Journaling/reflection ("Scribe") | 📋 | Thought capture, semantic search over notes |

### Phase 6: Delivery & Interface

| Task | Status | Notes |
|------|--------|-------|
| Email delivery | 📋 | Daily/weekly plans to inbox |
| Calendar integration | 📋 | Workouts as calendar events |
| Mobile-friendly output | 📋 | Phone-readable formats |
| Check-in system | 📋 | Structured conversations at cadence |

---

## Migration Notes

### From Old Schema

| Old | New | Action |
|-----|-----|--------|
| TrainingPlan | Deprecated | Extract goals, delete node |
| TrainingBlock | Block | Rename, re-link to Person |
| Goal (string on plan) | Goal (node) | Create nodes with [:REQUIRES]->Modality |
| Implicit training level | TrainingLevel | Create per person-modality |
| Obsidian workout files | Deprecated | Historical data imported, no longer maintained |

### Data Preservation

- Historical workouts (163) remain unchanged
- Exercise graph (4,242) remains unchanged
- MovementPattern (28) now links to Modality via [:EXPRESSED_BY]
- Obsidian markdown files no longer needed — Arnold is the system of record

---

## Principles

### Graph-First
Everything is relationships. Start at any node, traverse to what you need. The journey, the history, the patterns — all live in Neo4j.

### Modality as Hub
Training domains are the central organizing concept. "What are we training?" is the fundamental question.

### LLM-Native
Use Claude's reasoning for decisions, not rigid rule engines. MCPs provide data; Claude provides intelligence.

### Science-Grounded
Periodization models, progression schemes, and coaching logic are grounded in peer-reviewed exercise science. Evidence level is tracked. Citations required.

### Data Sovereignty
Your data, your control. All personal health data lives in your own Neo4j instance. Portable, queryable, private. No vendor lock-in.

### Minimal State
MCPs query fresh data, don't cache. Context is managed explicitly through memory layer.

### Compact Output
Phone-readable. The athlete is in the gym, not at a desk.

### Human in the Loop
The system advises; the human decides. Coach makes recommendations, athlete has final say.

---

## Codenames (Internal Only)

| Codename | Component |
|----------|-----------|
| CYBERDYNE-CORE | Neo4j database |
| SKYNET-READER | Data import pipelines |
| JUDGMENT-DAY | Workout planning logic |
| T-800 | Exercise knowledge graph |
| SARAH-CONNOR | User profile/digital twin |
| T-1000 | Analyst (analytics-mcp) |
| MILES-DYSON | Doc (medical-mcp) |
| JOHN-CONNOR | Researcher (research-mcp) |

---

## File Locations

```
/arnold
├── docs/
│   ├── ARCHITECTURE.md          # This file (master reference)
│   ├── HANDOFF.md               # Thread handoff document
│   ├── schema.md                # Detailed Neo4j schema
│   └── ...
├── src/
│   ├── arnold-journal-mcp/      # Subjective data capture + relationships
│   ├── arnold-profile-mcp/      # Profile management
│   ├── arnold-training-mcp/     # Training/coaching
│   ├── arnold-memory-mcp/       # Context management + semantic search
│   └── arnold-analytics-mcp/    # Analytics + reporting
├── data/                        # .gitignored, PII
│   ├── staging/                 # Raw imports (Parquet)
│   │   ├── neo4j_export/
│   │   ├── apple_health/
│   │   ├── garmin/
│   │   └── labs/
│   ├── arnold_analytics.duckdb  # Analytics database
│   ├── catalog.json             # Data registry
│   ├── profile.json             # Person profile
│   └── exports/                 # Generated reports
└── kernel/                      # Shareable ontology
```

---

## Handoff Checklist

When starting a new conversation thread, Claude should:

1. Read `/arnold/docs/HANDOFF.md` for quick context
2. Call `load_briefing` (arnold-memory-mcp) for current state
3. Full context loads automatically - goals, modalities, training levels, current block, injuries, recent workouts

The briefing gives you everything. No more cold starts.

---

## References

### Training Load & Workload Management

For complete training metrics citations, see **[TRAINING_METRICS.md](./TRAINING_METRICS.md)**.

Key sources:
- Gabbett, T.J. (2016). The training—injury prevention paradox. *BJSM*, 50(5), 273-280.
- Murray, N.B. et al. (2017). EWMA provides more sensitive injury indicator. *BJSM*, 51(9), 749-754.
- Schoenfeld, B.J. et al. (2017). Dose-response for training volume and hypertrophy. *J Sports Sci*, 35(11), 1073-1082.
- Foster, C. (1998). Monitoring training with overtraining syndrome. *MSSE*, 30(7), 1164-1168.
- Banister, E.W. (1975). Systems model of training for athletic performance. *Aust J Sports Med*, 7, 57-61.

### Periodization Science

- Issurin, V. (2010). New Horizons for the Methodology and Physiology of Training Periodization. Sports Medicine.
- Lorenz, D. (2015). Current Concepts in Periodization of Strength and Conditioning for the Sports Physical Therapist. IJSPT.
- Rønnestad, B. (2014). Block periodization in elite cyclists. (Referenced in TrainingPeaks masters athlete research)
- Api, G. & Arruda, D. (2022). Comparison of Periodization Models: A Critical Review with Practical Applications.

### Fitness-Fatigue Model

- Banister, E.W. (1975). A systems model of training for athletic performance. Australian Journal of Sports Medicine.
- Clarke, D.C. & Skiba, P.F. (2013). Rationale and Resources for Teaching the Mathematical Modeling of Athletic Training and Performance.

### Concurrent Training

- Coffey, V.G. & Hawley, J.A. (2017). Concurrent training: From molecules to the finish line. (Separating sessions by 9-24 hours)
- Effects of Running-Specific Strength Training (2022). ATR periodization for recreational endurance athletes.
