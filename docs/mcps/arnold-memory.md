# arnold-memory-mcp

> **Purpose:** Coaching context, persistent observations, and conversation continuity
> **Updated:** January 13, 2026 - Consolidated briefing architecture

## What This MCP Owns

- **Coaching briefings** (consolidated context at conversation start)
- **Observations** (patterns, preferences, insights, flags, decisions)
- **Block summaries** (what happened and what was learned)
- **Semantic search** over coaching memory

## Boundaries

| This MCP Does | This MCP Does NOT |
|---------------|-------------------|
| Load comprehensive context (Neo4j + Postgres) | Execute workouts |
| Store coaching observations | Calculate raw metrics |
| Summarize training blocks | Manage profile |
| Search past insights | Create plans |

## Tools

| Tool | Purpose |
|------|---------|
| `load_briefing` | **THE** briefing - full context from both databases |
| `store_observation` | Persist insight for future reference |
| `get_observations` | Retrieve observations by type/tags |
| `search_observations` | Semantic search over coaching memory |
| `get_block_summary` | Retrieve or request block summary |
| `store_block_summary` | Save block summary with learnings |
| `debrief_session` | End-of-session knowledge capture |

## Key Decisions

### Consolidated Briefing (Jan 2026)

**Context:** Architecture had drifted to 3 separate calls at conversation start:
- `memory:load_briefing` (Neo4j only)
- `analytics:check_red_flags` (Postgres)
- `training:get_planning_status` (mixed)

This violated the original design intent of "one call gets everything."

**Decision:** Consolidate into single `load_briefing` that queries both databases:

```
┌─────────────────────────────────────────────────────────────────┐
│                    load_briefing                                 │
│                                                                  │
│  ┌──────────────────────┐    ┌──────────────────────┐          │
│  │       Neo4j          │    │      Postgres         │          │
│  │  - Goals, Block      │    │  - HRV, Sleep, RHR    │          │
│  │  - Injuries          │    │  - ACWR, Load         │          │
│  │  - Observations      │    │  - HRR Trends         │          │
│  │  - Equipment         │    │  - Annotations        │          │
│  │  - Recent Workouts   │    │  - Pattern Gaps       │          │
│  └──────────────────────┘    └──────────────────────┘          │
│                                                                  │
│                    → Single formatted response                   │
└─────────────────────────────────────────────────────────────────┘
```

**Consequence:** One tool call establishes full coaching context. Deprecated `training:get_coach_briefing`.

### Three-Tier Memory Architecture

**Context:** Claude starts each conversation without memory. Need to restore context without overwhelming the context window.

**Decision:** Three tiers:
1. **Short-term** — Current context window
2. **Mid-term** — Summaries + embeddings for RAG retrieval
3. **Long-term** — Complete graph in Neo4j

**Consequence:** `load_briefing` provides essential context. `search_observations` retrieves relevant details on demand.

### Observation Types

**Context:** Different kinds of insights need different handling.

**Decision:** Five observation types:
- `pattern` — Recurring behavior ("Fatigue on deadlift set 3+ above 275lbs")
- `preference` — Athlete likes/dislikes ("Prefers compounds over isolation")
- `insight` — General learning ("Responds well to higher rep accessories")
- `flag` — Watch item ("Monitor form when fatigued")
- `decision` — Agreed action ("Prioritize deadlift over squat this block")

**Consequence:** Can filter by type when retrieving. Flags get special attention.

### Semantic Search with Embeddings

**Context:** Keyword search misses conceptually related observations.

**Decision:** Store 1536-dimension embeddings (OpenAI) for each observation. Use vector index for semantic search.

**Consequence:** Query "why does my deadlift break down?" finds fatigue patterns even without exact keyword match.

## load_briefing Response Structure

The consolidated briefing returns:

```
# COACHING CONTEXT: [Name]

## Today's Status
- HRV: [value] ([trend])
- Sleep: [hours] ([quality])
- ACWR: [value] ([zone])
- HRR: [per-stratum summary]
- 28d Volume: [workouts], [sets]
- Pattern Gaps: [list]

## Athletic Background
[martial arts, running, etc.]

## Active Goals
[goals with modalities and training levels]

## Training Levels by Modality
[per-modality: level, years, progression model]

## Current Block
[name, type, week X of Y, intent, volume/intensity]

## Medical / Constraints
[active injuries with constraints]

## Recent Workouts
[last 7 with patterns trained]

## Athlete-Specific Coaching Notes
[observations organized by category]

## Upcoming Sessions
[planned workouts]

## Equipment Available
[list]

## ⚡ Coaching Alerts
[pre-computed insights requiring attention]

## Active Annotations
[context for unusual data]
```

## Data Sources

| Section | Source | Purpose |
|---------|--------|---------|
| Today's Status | Postgres | Current biometrics, load |
| Goals, Block | Neo4j | Training structure |
| Injuries | Neo4j | Constraints |
| Recent Workouts | Neo4j | Training history |
| Observations | Neo4j | Coaching memory |
| HRR Trends | Postgres | Recovery tracking |
| Annotations | Postgres | Data context |

## Dependencies

- **Neo4j** — Observation storage, vector index, relationships
- **Postgres** — Analytics, biometrics, time-series
- **OpenAI API** — Embedding generation
- **profile.json** — Person ID resolution

## Typical Usage Pattern

### Conversation Start
```python
briefing = load_briefing()  # ONE call gets everything
# Claude now knows goals, block, injuries, readiness, HRR, recent history
```

### During Coaching
```python
# Store insight discovered during conversation
store_observation(
    content="Responds better to RPE-based loading than percentage-based",
    observation_type="preference",
    tags=["programming", "load-selection"]
)
```

### Finding Relevant Context
```python
# Semantic search when topic comes up
results = search_observations(
    query="shoulder mobility issues",
    threshold=0.7
)
```

## Migration Notes

**Deprecated tools:**
- `training:get_coach_briefing` — Use `memory:load_briefing` instead

**Old pattern (DON'T DO THIS):**
```
1. memory:load_briefing
2. analytics:check_red_flags  
3. training:get_planning_status
```

**New pattern:**
```
1. memory:load_briefing  # That's it
```

## Known Issues / Tech Debt

1. **Embedding generation** — Currently requires OpenAI API key. Should have fallback or batch processing.

2. **Briefing size** — As history grows, briefing may exceed ideal size. May need pagination or summarization.
