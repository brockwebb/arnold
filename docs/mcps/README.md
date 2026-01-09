# Arnold MCP Architecture

> **Last Updated:** January 6, 2026 (Added journal MCP, annotation tools)

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
                             ▼
                    ┌─────────────────┐
                    │     Neo4j       │
                    │ (CYBERDYNE-CORE)│
                    └─────────────────┘
```

## Domain Boundaries

| Domain | MCP | Owns | Does NOT Own |
|--------|-----|------|--------------|
| **Identity & Setup** | arnold-profile | Person, equipment, activities, observations | Workouts, plans, coaching |
| **Journal & Notes** | arnold-journal | Log entries, symptoms, feedback, **data annotations** | Workouts, analytics |
| **Training Ops** | arnold-training | Plans, workouts, execution, exercise selection | Profile data, analytics |
| **Metrics & Insights** | arnold-analytics | Readiness, training load, red flags, sleep | Data writes, coaching decisions |
| **Context & Memory** | arnold-memory | Briefings, observations, block summaries | Profile, workouts |

## MCP Roster

| MCP | Purpose | Tools | Docs |
|-----|---------|-------|------|
| **arnold-profile-mcp** | Athlete identity, equipment, biometrics | 10 | [arnold-profile.md](arnold-profile.md) |
| **arnold-journal-mcp** | Subjective data, notes, **annotations** | 17 | (see HANDOFF) |
| **arnold-training-mcp** | Workout planning and execution | 16 | [arnold-training.md](arnold-training.md) |
| **arnold-analytics-mcp** | Training metrics and coaching insights | 5 | [arnold-analytics.md](arnold-analytics.md) |
| **arnold-memory-mcp** | Conversation context and coaching memory | 5 | [arnold-memory.md](arnold-memory.md) |

## When to Use Which MCP

| Task | Primary MCP | Supporting MCP |
|------|-------------|----------------|
| Create athlete profile | profile | — |
| Log equipment inventory | profile | — |
| Record body weight | profile | — |
| Create workout plan | training | memory (for context) |
| Log completed workout | training | — |
| Check readiness before training | analytics | — |
| Start coaching conversation | memory | analytics (red flags) |
| Find exercise substitutes | training | — |
| Track training load trends | analytics | — |

## Cross-MCP Patterns

### Coaching Conversation Start
```
1. memory:load_briefing         → Full athlete context
2. analytics:check_red_flags    → Any concerns to address
3. training:get_planning_status → Gaps to fill
```

### Workout Completion
```
1. training:complete_as_written OR complete_with_deviations
2. (Analytics auto-updates on next query via DuckDB)
```

### Planning Session
```
1. memory:load_briefing           → Goals, block, constraints
2. training:get_training_context  → Equipment, injuries
3. training:suggest_exercises     → Candidates
4. training:create_workout_plan   → Persist plan
```

## Shared Infrastructure

| Component | Used By | Purpose |
|-----------|---------|---------|
| Neo4j | All MCPs | Graph storage, relationships |
| DuckDB | analytics | Time-series aggregations |
| profile.json | profile, training | Person ID resolution |

## Design Principles

1. **Single Responsibility** — Each MCP owns one domain completely
2. **Atomic Writes** — All write operations use single UNWIND statements (no orphans)
3. **Claude as Orchestrator** — MCPs are "dumb" tools; Claude provides semantic understanding
4. **Graph-First** — Relationships modeled in Neo4j, not inferred at query time

## Adding a New MCP

1. Define domain boundary (what it owns, what it doesn't)
2. Check for overlap with existing MCPs
3. Create MCP with tools following existing patterns
4. Add boundary documentation here
5. Add per-MCP doc in this folder
