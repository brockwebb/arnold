# Memory Architecture

> **Last Updated**: January 8, 2026

---

## The Problem

Every conversation, Claude starts fresh. Without explicit context loading, Claude doesn't know:
- What goals are active
- What block we're in
- Training level per modality
- What happened last workout
- Active injuries or constraints

---

## The Solution: Three-Tier Memory

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHORT-TERM MEMORY                            │
│                   (Context Window)                              │
│                                                                 │
│  Current conversation + loaded briefing + tool results          │
│  ~200k tokens, refreshes each conversation                      │
└─────────────────────────────────┬───────────────────────────────┘
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
└─────────────────────────────────┬───────────────────────────────┘
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

---

## Memory Operations

| Operation | Description |
|-----------|-------------|
| **load_briefing** | Get essential state for conversation start |
| **search_observations** | Semantic retrieval via vector similarity |
| **store_observation** | Persist insight with auto-generated embedding |
| **get_observations** | Tag/type filtered retrieval (non-semantic) |
| **get_block_summary** | Get or generate block summaries |
| **store_block_summary** | Persist block summary with learnings |

---

## Semantic Search

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

## Context Window Management

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
└─────────────────────────────────────────────────────────────────┘
```

---

## Load Briefing Contents

The `load_briefing` tool returns comprehensive coaching context:

- **Athlete identity**: Name, phenotype, total training age
- **Background**: Sports history, preferences
- **Goals**: Active goals with required modalities, target dates, priorities
- **Training levels**: Per-modality level and progression model
- **Current block**: Name, type, week X of Y, intent, targets
- **Medical**: Active injuries with constraints, resolved history
- **Recent workouts**: Last 14 days with patterns trained
- **Coaching observations**: Persistent notes from past conversations
- **Upcoming sessions**: Planned workouts
- **Equipment**: Available equipment

This establishes coaching continuity — Claude knows the full picture from message one.

---

## Observation Types

| Type | Purpose | Example |
|------|---------|---------|
| `pattern` | Recurring behavior noticed | "Fatigue pattern on deadlift set 3+ above 275lbs" |
| `preference` | User preference learned | "Prefers compound movements over isolation" |
| `insight` | Coaching insight | "Responds well to higher rep ranges on accessories" |
| `flag` | Something to watch | "Watch for form breakdown when fatigued" |
| `decision` | Agreed-upon decision | "Prioritize deadlift over squat this block" |

Observations are tagged for retrieval and embedded for semantic search.

---

## Handoff Pattern

When starting a new conversation thread, Claude should:

1. Read `/arnold/docs/HANDOFF.md` for quick context
2. Call `load_briefing` (arnold-memory-mcp) for current state
3. Full context loads automatically

The briefing gives you everything. No more cold starts.
