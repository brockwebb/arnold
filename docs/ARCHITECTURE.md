# Arnold Architecture — Master Document

> **Purpose**: This document is the authoritative reference for Arnold's architecture. It serves as context handoff between conversation threads and the north star for development decisions.

> **Last Updated**: January 1, 2026 (Phase 2 Complete - Analytics Foundation)

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

### Data Sources (Future)

| Source | Data Type | Priority |
|--------|-----------|----------|
| Apple Health | Sleep, HRV, resting HR, steps, activity | High |
| Garmin/Strava | Runs, rides, GPS, training load | High |
| Blood work | Biomarkers, panels, trends | High |
| Medical records | Diagnoses, procedures, medications | Medium |
| Nutrition | Macros, micros, meal timing | Medium |
| Body composition | Weight, body fat, measurements | Medium |
| Subjective | Energy, mood, stress, notes | Medium |
| Genome | 23andMe, ancestry, health risks | Low |
| Wearables | Continuous glucose, Oura, Whoop | Low |

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
│   ├── suunto/                 # .fit files
│   ├── ultrahuman/             # JSON exports
│   ├── apple_health/           # XML exports
│   └── labs/                   # PDF/CSV lab results
├── staging/                    # Parquet, minimal transform
│   ├── workouts.parquet
│   ├── sets.parquet
│   ├── exercises.parquet
│   └── movement_patterns.parquet
├── catalog.json                # ✅ Data intelligence (CREATED)
├── arnold_analytics.duckdb     # Analytics database (pending)
└── exports/                    # Generated reports, charts
```

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
| **arnold-profile-mcp** | Person, equipment, observations, activities | ✅ Operational |
| **arnold-training-mcp** | Planning, exercise selection, workout logging | ✅ Operational |
| **arnold-memory-mcp** | Context management, briefings, observations | ✅ **Operational** |
| **neo4j-mcp** | Direct graph queries | ✅ External |

### To Build (The Team)

| MCP | Persona | Role | Priority |
|-----|---------|------|----------|
| **arnold-analytics-mcp** | Analyst | Metrics, trends, reports, visualizations | 🔴 High |
| **arnold-medical-mcp** | Doc | Health tracking, symptoms, labs, rehab | 🟡 Medium |
| **arnold-checkin-mcp** | Coach | Structured check-ins, progress reviews | 🟡 Medium |
| **arnold-research-mcp** | Researcher | Literature search, protocol recommendations | 🟢 Low |
| **arnold-scribe-mcp** | Scribe | Journaling, reflection, thought capture | 🟢 Low |

### Tool Distribution

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

### Graph Health (as of Dec 30, 2025)

| Node Type | Count |
|-----------|-------|
| Exercise | 4,242 |
| Workout | 163 |
| Set | 2,445 |
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
| Export Neo4j to Parquet | ⏳ | Run script on local machine |
| Create DuckDB database | 📋 | `arnold_analytics.duckdb` |
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
│   ├── arnold-profile-mcp/      # Profile management
│   ├── arnold-training-mcp/     # Training/coaching
│   ├── arnold-memory-mcp/       # Context management + semantic search
│   └── arnold-analytics-mcp/    # (Future) Analytics + reporting
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
