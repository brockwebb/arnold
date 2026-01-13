# Arnold MCP Architecture

> **Last Updated:** January 13, 2026 (Consolidated briefing architecture)

## Overview

Arnold uses four MCP servers, each owning a distinct domain. Claude Desktop orchestrates all four, calling the right tools for the task.

```
┌─────────────────────────────────────────────────────────────────┐
│                      Claude Desktop                              │
│                    (Orchestration Layer)                         │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   Profile   │ │  Training   │ │  Analytics  │ │   Memory    │
│     MCP     │ │     MCP     │ │     MCP     │ │     MCP     │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │              │              │              │
       └──────────────┴──────┬───────┴──────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌─────────┐  ┌─────────┐  ┌─────────┐
         │ Neo4j   │  │Postgres │  │ Journal │
         │(graphs) │  │ (facts) │  │  MCP    │
         └─────────┘  └─────────┘  └─────────┘
```

## Domain Boundaries

| Domain | MCP | Owns | Does NOT Own |
|--------|-----|------|--------------|
| **Identity & Setup** | arnold-profile | Person, equipment, activities, observations | Workouts, plans, coaching |
| **Journal & Notes** | arnold-journal | Log entries, symptoms, feedback, **data annotations** | Workouts, analytics |
| **Training Ops** | arnold-training | Plans, workouts, execution, exercise selection | Profile data, analytics |
| **Metrics & Insights** | arnold-analytics | Readiness, training load, red flags, sleep, HRR | Data writes, coaching decisions |
| **Context & Memory** | arnold-memory | **Consolidated briefings**, observations, block summaries | Profile, workouts |

## MCP Roster

| MCP | Purpose | Tools | Docs |
|-----|---------|-------|------|
| **arnold-profile-mcp** | Athlete identity, equipment, biometrics | 10 | [arnold-profile.md](arnold-profile.md) |
| **arnold-journal-mcp** | Subjective data, notes, **annotations** | 17 | (see HANDOFF) |
| **arnold-training-mcp** | Workout planning and execution | 16 | [arnold-training.md](arnold-training.md) |
| **arnold-analytics-mcp** | Training metrics and coaching insights | 8 | [arnold-analytics.md](arnold-analytics.md) |
| **arnold-memory-mcp** | **Consolidated context** and coaching memory | 7 | [arnold-memory.md](arnold-memory.md) |

## When to Use Which MCP

| Task | Primary MCP | Supporting MCP |
|------|-------------|----------------|
| **Start coaching conversation** | **memory** (`load_briefing`) | — |
| Create athlete profile | profile | — |
| Log equipment inventory | profile | — |
| Record body weight | profile | — |
| Create workout plan | training | — |
| Log completed workout | training | — |
| Check readiness (detailed) | analytics | — |
| Find exercise substitutes | training | — |
| Track training load trends | analytics | — |
| Deep dive on HRR | analytics | — |

## Cross-MCP Patterns

### Coaching Conversation Start (SIMPLIFIED)

```
1. memory:load_briefing  ← ONE CALL gets everything
```

The consolidated `load_briefing` returns:
- Neo4j: Goals, block, injuries, observations, equipment
- Postgres: HRV, sleep, ACWR, HRR trends, pattern gaps, annotations

**DO NOT use the old 3-call pattern.**

### Workout Completion
```
1. training:complete_as_written OR complete_with_deviations
2. (Analytics auto-updates on next query via views)
```

### Planning Session
```
1. memory:load_briefing           → Full context
2. training:get_training_context  → Equipment, injuries (if needed)
3. training:suggest_exercises     → Candidates
4. training:create_workout_plan   → Persist plan
```

### Deep Analytics (when needed)
```
# Only call these for detailed investigation, not routine briefing
analytics:get_readiness_snapshot  → Detailed biometrics
analytics:get_hrr_trend           → Full HRR analysis with EWMA/CUSUM
analytics:get_training_load       → Volume trends, pattern distribution
analytics:get_exercise_history    → Progression for specific lift
```

## Database Access Architecture

There are TWO ways Arnold MCPs access Postgres:

### 1. postgres-mcp (Generic Tool)
- External MCP from crystaldba
- Exposes raw SQL execution to Claude
- Used for ad-hoc queries, debugging, schema exploration
- Claude calls it directly when needed

### 2. Internal Postgres Clients (Private Helpers)
- `PostgresAnalyticsClient` inside arnold-memory-mcp
- `PostgresTrainingClient` inside arnold-training-mcp
- NOT exposed as MCP tools
- Encapsulate domain-specific queries
- Return structured data, not raw rows

**Why both?**

```
┌─────────────────────────────────────────────────────────────┐
│  Claude calls: memory:load_briefing                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  server.py (arnold-memory-mcp)                               │
│    ├── Neo4jMemoryClient.load_briefing()   → Neo4j          │
│    └── PostgresAnalyticsClient.get_analytics_for_briefing() │
│                                             → Postgres       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
              Single formatted response to Claude
```

The internal clients are implementation details. Claude doesn't need to know the schema or write SQL - it just calls the MCP tool and gets structured coaching context.

**postgres-mcp** is still available for Claude to use when it needs raw database access (debugging, exploration, one-off queries).

## Shared Infrastructure

| Component | Used By | Purpose |
|-----------|---------|---------|
| Neo4j | All MCPs | Graph storage, relationships |
| Postgres | analytics, memory, training | Time-series, facts |
| profile.json | profile, training, memory | Person ID resolution |

## Design Principles

1. **Single Responsibility** — Each MCP owns one domain completely
2. **Atomic Writes** — All write operations use single UNWIND statements (no orphans)
3. **Claude as Orchestrator** — MCPs are "dumb" tools; Claude provides semantic understanding
4. **Graph-First** — Relationships modeled in Neo4j, not inferred at query time
5. **One Briefing** — Conversation start requires exactly ONE tool call

## Deprecated Patterns

### ❌ Old Pattern (DON'T DO THIS)
```
1. memory:load_briefing         → Neo4j only
2. analytics:check_red_flags    → Postgres
3. training:get_planning_status → Mixed
```

### ✅ New Pattern
```
1. memory:load_briefing  → Everything
```

### Deprecated Tools
- `training:get_coach_briefing` — Redundant, use `memory:load_briefing`

## Adding a New MCP

1. Define domain boundary (what it owns, what it doesn't)
2. Check for overlap with existing MCPs
3. Create MCP with tools following existing patterns
4. Add boundary documentation here
5. Add per-MCP doc in this folder
