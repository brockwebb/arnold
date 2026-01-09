# Coach Workflows

> **Last Updated**: January 8, 2026

---

## Before Any Planning

The coach must answer:
1. **What are the goals?** (Goal nodes)
2. **What modalities do they require?** (Goal → Modality)
3. **What's the training level per modality?** (TrainingLevel)
4. **What block are we in?** (Active Block)
5. **What should today accomplish?** (Session intent from block)

---

## Session Generation Flow

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

---

## Check-in Cadence

| When | Purpose |
|------|---------|
| Block start | What's the intent, what are we doing |
| Block end | What happened, what did we learn |
| Weekly brief | Here's the week, any issues? |
| After deviation | Life happened, let's recalibrate |
| On request | Athlete has questions/concerns |

---

## What the Coach Explains

1. **The Plan** — "This block is 4 weeks of accumulation. We're building work capacity."

2. **The Why** — "You're 12 months from Hellgate. This base phase supports the volume you'll need in fall. Your deadlift is progressing linearly because you're new to it."

3. **The Tradeoffs** — "Running volume will be moderate because we're also building strength. When we shift to race-specific prep, strength becomes maintenance only."

4. **The Data** — "Your deadlift went from 225x5 to 315x5 in 8 weeks. That's novice gains."

5. **The Ask** — "How are you feeling? Anything I should know?"

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

## Exercise Matching Architecture

### The Problem

Exercise matching was failing because we asked the database to do semantic work:

| User Says | DB Has | Result |
|-----------|--------|--------|
| "KB swing" | "Kettlebell Swing" | ❌ Not found |
| "pull up" | "Pullups" | ❌ Wrong match |

### The Solution: Layered Responsibility

**Core insight: Claude IS the semantic layer. The database is the retrieval layer.**

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEMANTIC LAYER (Claude)                      │
│  "KB swing" → "Kettlebell Swing"                                │
│  Normalization, synonym resolution, context understanding       │
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

### Tool Pattern

Replace exact match with candidate retrieval:

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

---

## System Architecture Overview

```
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
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         ┌─────────┐  ┌─────────┐  ┌─────────┐
         │ Neo4j   │  │Postgres │  │ Journal │
         │(graphs) │  │ (facts) │  │  MCP    │
         └─────────┘  └─────────┘  └─────────┘
```

**Key Insight: Claude IS the Orchestrator**

There is no separate "orchestrator MCP." Claude Desktop performs orchestration by:
1. Understanding the user's intent
2. Deciding which tools to call
3. Synthesizing results into coherent responses
4. Maintaining conversation context

MCPs are **specialist tool collections**, not autonomous agents.
