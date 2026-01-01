# Arnold Architecture — Master Document

> **Purpose**: This document is the authoritative reference for Arnold's architecture. It serves as context handoff between conversation threads and the north star for development decisions.

> **Last Updated**: December 31, 2025 (Phase 2 - Semantic Search)

---

## Executive Summary

Arnold is an AI-native fitness coaching system built on Neo4j. The architecture uses Claude Desktop as the reasoning/orchestration layer, with specialist MCP servers providing domain tools. The critical insight: **Claude IS the orchestrator** — MCPs are tools, not agents.

Arnold is designed as a **proto-human system**: it learns and grows with the user, adapting to their goals, experience level, and life context. It is not a bespoke solution for one athlete, but a foundation for any human pursuing fitness.

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

### To Build

| MCP | Role | Priority |
|-----|------|----------|
| **arnold-checkin-mcp** | Structured check-ins, progress reviews | 🟡 Medium |
| **arnold-analytics-mcp** | Metrics, trends, visualizations | 🟢 Low |

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

## Development Priorities

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

### Immediate
1. ⏳ Weekly planning workflow - plan Week 1 sessions
2. ⏳ Live fire test: plan → execute → reconcile

### Next
4. arnold-checkin-mcp - structured check-ins
5. arnold-analytics-mcp - metrics, visualization

### Future
- arnold-checkin-mcp
- arnold-medical-mcp (injuries, constraints)
- arnold-analytics-mcp (metrics, visualization)
- Email/calendar integration for plan delivery
- Wearable data integration

---

## Migration Notes

### From Old Schema

| Old | New | Action |
|-----|-----|--------|
| TrainingPlan | Deprecated | Extract goals, delete node |
| TrainingBlock | Block | Rename, re-link to Person |
| Goal (string on plan) | Goal (node) | Create nodes with [:REQUIRES]->Modality |
| Implicit training level | TrainingLevel | Create per person-modality |

### Data Preservation

- Historical workouts (163) remain unchanged
- Exercise graph (4,242) remains unchanged
- MovementPattern (28) now links to Modality via [:EXPRESSED_BY]

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
│   └── arnold-memory-mcp/       # Context management + semantic search
├── data/                        # .gitignored, PII
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
