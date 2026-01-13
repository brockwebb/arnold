# Session Protocols

> **Status**: Active  
> **Implements**: Issue #20

This document defines the session protocols for consistent Coach behavior across conversation threads.

---

## Overview

Claude Desktop doesn't support mandatory startup hooks—there's no way to force context loading before Claude responds. These protocols accept that constraint and optimize within it through convention-based rituals.

**Key insight**: We're building a knowledge layer (graph + analytics), not updating the LLM. Claude is the intelligence that uses the knowledge. As LLMs improve, they use the knowledge better. Investment is in the knowledge, not the model.

---

## Startup Protocol

### Trigger Phrases

- "Coach, ready to train"
- "Coach, let's check in"
- "Hey Coach" (as greeting)

### What Happens

1. Claude calls `load_briefing()` from arnold-memory-mcp
2. Briefing returns comprehensive context:
   - Athlete identity, background, goals
   - Current training block and week
   - Active injuries and constraints
   - Recent workouts (last 14 days)
   - **Athlete-Specific Coaching Notes** (assembled from observations)
   - Upcoming planned sessions
   - Pattern gaps and muscle volume
3. Coach acknowledges context loaded
4. Proceeds with consistent personality informed by the coaching notes

### Project Instructions

```
When user initiates a coaching session (phrases like "ready to train", 
"let's check in", "Coach" as greeting), ALWAYS call load_briefing() 
before responding. Your personality and approach should reflect the 
coaching notes returned in the briefing.
```

---

## End-of-Session Protocol (Debrief)

### Trigger Phrases

- "Coach, let's debrief"
- "Let's wrap up"
- "Save what we learned"

### The Collaborative Flow

1. **Claude reviews the session** and proposes observations to capture
2. **User confirms, corrects, or adds** ("don't forget X")
3. **Claude calls `debrief_session`** with the agreed observations
4. **Tool stores observations** and creates graph relationships
5. **Claude confirms** what was captured

### What to Look For (Guidelines, Not Checklist)

| Category | What to Capture |
|----------|-----------------|
| **Emergent preferences** | Athlete keeps adding warmups? That's a preference. |
| **Deviations from plan** | Changed exercises, adjusted loads, skipped sets—and WHY |
| **Patterns noticed** | HRV correlations, fatigue signatures, time-of-day effects |
| **Feedback received** | How athlete responded to coaching cues or suggestions |
| **Medical/symptoms** | Pain, discomfort, or recovery notes not captured elsewhere |
| **What worked** | Cues that clicked, progressions that felt right |
| **What didn't** | Approaches to avoid next time |

**Use judgment.** Not everything needs capturing—focus on what will inform future coaching. Quality over quantity.

### Example Debrief

```
User: "Coach, let's debrief"

Coach: "Here's what I think is worth capturing from this session:

- [preference] You added an active warmup again—seems like a standing preference
- [pattern] Ring support holds fatigued you faster than expected at the 20-sec mark
- [insight] The cue 'squeeze the rings like you're wringing out a towel' clicked

Anything I missed?"

User: "Add that I want cooldowns included too"

Coach: [calls debrief_session with 4 observations]
"Captured 4 observations. These will inform future sessions via load_briefing()."
```

### Graph Relationships Created

The debrief tool can create relationship links:

| Link Type | Relationship | Use Case |
|-----------|--------------|----------|
| `link_to_workout` | `(:Observation)-[:ABOUT_WORKOUT]->(:Workout)` | "This observation is about today's workout" |
| `link_to_goal` | `(:Observation)-[:INFORMS]->(:Goal)` | "This observation relates to the deadlift goal" |
| `link_to_injury` | `(:Observation)-[:RELATED_TO]->(:Injury)` | "This observation is about knee recovery" |

These links enable future queries like "what have we learned about deadlift sessions?" to traverse the graph.

---

## How the System Learns

```
Session N: User prefers active warmup
    ↓ debrief_session stores preference
    ↓
Session N+1: load_briefing returns "athlete prefers active warmup"
    ↓ Coach includes warmup without being asked
    ↓
Session N+1: User confirms, no correction needed
    = System learned
```

The graph doesn't forget, doesn't have token limits, and gets more queryable as it grows.

---

## Tools Reference

### `load_briefing()` (arnold-memory-mcp)

**Purpose**: Load comprehensive coaching context at session start

**Returns**:
- Athlete identity and background
- Active goals with modality requirements
- Training levels by modality
- Current block (name, type, week X of Y, intent)
- Medical/injuries with constraints
- Recent workouts (last 14 days)
- **Athlete-Specific Coaching Notes** (categorized observations)
- Upcoming planned sessions
- Pattern gaps and muscle volume
- Available equipment

### `debrief_session()` (arnold-memory-mcp)

**Purpose**: End-of-session knowledge capture

**Parameters**:
```python
debrief_session(
    observations: [
        {
            content: str,              # The observation
            observation_type: str,     # pattern/preference/insight/flag/decision
            tags: [str],               # Keywords for retrieval
            link_to_workout: str,      # Optional: workout date (YYYY-MM-DD)
            link_to_goal: str,         # Optional: goal name to link
            link_to_injury: str        # Optional: injury name to link
        }
    ],
    session_summary: str               # Optional: brief narrative
)
```

**Returns**: Summary of stored observations and created links

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SESSION START                             │
│                                                              │
│  "Coach, ready to train"                                     │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────┐                                        │
│  │ load_briefing() │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────┐            │
│  │ Returns:                                     │            │
│  │ - Context (goals, block, injuries)          │            │
│  │ - Coaching Notes (from past observations)   │            │
│  └─────────────────────────────────────────────┘            │
│           │                                                  │
│           ▼                                                  │
│  Coach behaves with consistent personality                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    SESSION END                               │
│                                                              │
│  "Coach, let's debrief"                                      │
│         │                                                    │
│         ▼                                                    │
│  Claude proposes observations                                │
│         │                                                    │
│         ▼                                                    │
│  User confirms/adds                                          │
│         │                                                    │
│         ▼                                                    │
│  ┌───────────────────┐                                      │
│  │ debrief_session() │                                      │
│  └─────────┬─────────┘                                      │
│            │                                                 │
│            ▼                                                 │
│  ┌─────────────────────────────────────────────┐            │
│  │ Neo4j Knowledge Graph                        │            │
│  │                                              │            │
│  │ (:Person)-[:HAS_OBSERVATION]->(:Observation) │            │
│  │ (:Observation)-[:ABOUT_WORKOUT]->(:Workout)  │            │
│  │ (:Observation)-[:INFORMS]->(:Goal)           │            │
│  │ (:Observation)-[:RELATED_TO]->(:Injury)      │            │
│  └─────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

---

## Related

- Issue #20: Session protocols and data-driven personality
- `config/personalities/coach.md`: Base personality config
- `docs/handoffs/2026-01-10-issue-20-phase-a.md`: Phase A implementation details
