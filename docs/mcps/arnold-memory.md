# arnold-memory-mcp

> **Purpose:** Coaching context, persistent observations, and conversation continuity

## What This MCP Owns

- **Coaching briefings** (load full context at conversation start)
- **Observations** (patterns, preferences, insights, flags, decisions)
- **Block summaries** (what happened and what was learned)
- **Semantic search** over coaching memory

## Boundaries

| This MCP Does | This MCP Does NOT |
|---------------|-------------------|
| Load comprehensive context | Execute workouts |
| Store coaching observations | Calculate metrics |
| Summarize training blocks | Manage profile |
| Search past insights | Create plans |

## Tools

| Tool | Purpose |
|------|---------|
| `load_briefing` | Full coaching context for conversation start |
| `store_observation` | Persist insight for future reference |
| `get_observations` | Retrieve observations by type/tags |
| `search_observations` | Semantic search over coaching memory |
| `get_block_summary` | Retrieve or request block summary |
| `store_block_summary` | Save block summary with learnings |

## Key Decisions

### Three-Tier Memory Architecture

**Context:** Claude starts each conversation without memory. Need to restore context without overwhelming the context window.

**Decision:** Three tiers:
1. **Short-term** — Current context window
2. **Mid-term** — Summaries + embeddings for RAG retrieval
3. **Long-term** — Complete graph in Neo4j

**Consequence:** `load_briefing` provides essential context. `search_observations` retrieves relevant details on demand.

### load_briefing as First Call

**Context:** Coaching quality depends on knowing the athlete's current state, goals, constraints.

**Decision:** `load_briefing` returns comprehensive context in one call:
- Athlete identity and background
- Active goals with modalities
- Current block (type, week N of M, intent)
- Recent workouts (last 14 days)
- Active injuries
- Coaching observations
- Upcoming plans

**Consequence:** Single tool call establishes full coaching context. No need for multiple queries.

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

```cypher
// Vector index for semantic search
CREATE VECTOR INDEX observation_embedding IF NOT EXISTS
FOR (o:CoachingObservation) ON (o.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
```

### Block Summaries as Learning Capture

**Context:** Blocks contain valuable lessons that shouldn't be lost.

**Decision:** At block end, store summary with:
- Narrative content
- Key metrics (volume, PRs, compliance)
- Key learnings (list of insights)

**Consequence:** Future blocks can reference what worked/didn't work in past blocks.

## Data Model

```
(Person)-[:HAS_OBSERVATION]->(CoachingObservation)
(CoachingObservation {
  type: 'pattern'|'preference'|'insight'|'flag'|'decision',
  content: String,
  tags: [String],
  embedding: [Float],
  created_at: DateTime
})

(Block)-[:HAS_SUMMARY]->(BlockSummary)
(BlockSummary {
  content: String,
  key_metrics: Map,
  key_learnings: [String]
})
```

## Dependencies

- **Neo4j** — Observation storage, vector index
- **OpenAI API** — Embedding generation
- **profile.json** — Person ID resolution

## Typical Usage Pattern

### Conversation Start
```python
briefing = load_briefing()  # Full context
# Claude now knows goals, block, injuries, recent history
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

## Known Issues / Tech Debt

1. **Embedding generation** — Currently requires OpenAI API key. Should have fallback or batch processing.

2. **Briefing size** — As history grows, briefing may exceed ideal size. May need pagination or summarization.
