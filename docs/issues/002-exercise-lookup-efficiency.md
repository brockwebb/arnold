# Issue 002: Exercise Lookup Efficiency

> **Status**: Phase 1 Complete
> **Priority**: High  
> **Created**: January 3, 2026
> **Updated**: January 3, 2026
> **Related**: Exercise Matching Architecture (ARCHITECTURE.md)

---

## Problem Statement

Building a single workout plan requires 10-20 tool calls due to exercise ID resolution. This pattern doesn't scale.

### Current Flow (Broken)

```
Claude wants to create Thursday's plan with 5 exercises:
1. Guess ID: "EXERCISE:Kettlebell_Swings" → ❌ Fails (doesn't exist)
2. Search: search_exercises("kettlebell swing") → Returns candidates
3. Select: CUSTOM:Kettlebell_Swings
4. Repeat for next exercise...
5. Repeat...
6. Finally call create_workout_plan with all IDs
7. ❌ Fails on one bad ID, start over
```

**Result**: 15+ round trips for one workout. A 12-week plan would require 500+ tool calls.

### Observed Failure (Jan 3, 2026)

Building a 7-day plan crashed mid-creation because Claude used `EXERCISE:Kettlebell_Swings` instead of `CUSTOM:Kettlebell_Swings`. The APOC validation correctly rejected the invalid ID, but the workflow wasted 10 tool calls before failing.

---

## Root Causes

### 1. ID Namespace Confusion

Multiple ID formats exist:
- `EXERCISE:Name` — Free-Exercise-DB imports
- `CANONICAL:FFDB:###` — Functional Fitness DB with numeric IDs
- `CUSTOM:Name` — User-created from workout history

Claude doesn't know which namespace an exercise lives in without searching first.

### 2. No Batch Operations

Each exercise requires a separate `search_exercises` call. No way to say "resolve these 10 exercise names to IDs."

### 3. Name-First Instead of Intent-First

Current approach: "I need kettlebell swings" → search by name → get ID

Graph-native approach: "I need a hip hinge warmup" → query by pattern → get candidates

The graph already has 4,951 `INVOLVES` relationships connecting exercises to movement patterns. We're not using them.

### 4. Ignoring Historical Context

The athlete has 163 workouts with 2,445 sets. The question "what hip hinge warmup exercises has Brock actually used?" is answerable but we never ask it.

### 5. Canonical Gaps

FFDB doesn't have basic "Kettlebell Swing" (only Double/Single-arm variants). User's `CUSTOM:Kettlebell_Swings` exists because historical workouts created it. This is correct behavior but surprising.

---

## Proposed Solutions

### Solution A: Batch Exercise Lookup

New tool: `resolve_exercises(names: list[str]) -> dict[str, ExerciseMatch]`

```python
# Input
["kettlebell swing", "trap bar deadlift", "RDL", "ab rollout"]

# Output
{
  "kettlebell swing": {
    "id": "CUSTOM:Kettlebell_Swings",
    "name": "Kettlebell Swings",
    "confidence": 0.95,
    "alternatives": ["CANONICAL:FFDB:575"]  # Double KB Swing
  },
  "trap bar deadlift": {
    "id": "EXERCISE:Trap_Bar_Deadlift",
    "name": "Trap Bar Deadlift", 
    "confidence": 1.0,
    "alternatives": []
  },
  ...
}
```

**Pro**: Direct replacement for current workflow, minimal changes
**Con**: Still name-first, doesn't leverage graph structure

### Solution B: Intent-Based Exercise Selection

New tool: `get_exercises_for_intent(intent: ExerciseIntent) -> list[Exercise]`

```python
# Input
{
  "block_type": "warmup",
  "patterns": ["Hip Hinge"],
  "count": 2,
  "prefer_historical": true,
  "equipment_available": ["kettlebell", "barbell"]
}

# Output
[
  {"id": "CUSTOM:Kettlebell_Swings", "name": "Kettlebell Swings", "times_used": 47},
  {"id": "CUSTOM:Jefferson_Curl", "name": "Jefferson Curl", "times_used": 12}
]
```

**Pro**: Graph-native, leverages relationships and history
**Con**: More complex, requires Claude to express intent rather than names

### Solution C: Smart Plan Builder

Push exercise resolution INTO `create_workout_plan`. Accept fuzzy exercise names, resolve internally.

```python
# Input to create_workout_plan
{
  "date": "2026-01-08",
  "blocks": [{
    "name": "Warm-Up",
    "sets": [
      {"exercise": "KB swings", "reps": 15},  # Fuzzy name, not ID
      {"exercise": "jefferson curl", "reps": 8}
    ]
  }]
}

# Tool resolves internally, returns plan or structured errors
```

**Pro**: Single tool call, all resolution hidden
**Con**: Black box, harder to debug, Claude loses visibility

### Solution D: Hybrid — Batch + Intent

Combine A and B:

1. `resolve_exercises` for when Claude knows what it wants
2. `suggest_exercises_for_intent` for when building from scratch

Both return the same `Exercise` shape, both can be used as inputs to `create_workout_plan`.

---

## Recommendation

**Start with Solution D (Hybrid)** but implement in phases:

### Phase 1: Batch Lookup (Immediate)

Add `resolve_exercises` tool to `arnold-profile-mcp`:
- Takes list of exercise names (fuzzy)
- Returns map of name → best match with confidence
- Uses existing full-text index
- Single round trip for all exercises in a plan

This unblocks current workflow immediately.

### Phase 2: Intent-Based Selection (Next)

Add `suggest_exercises_for_intent` tool:
- Takes pattern, muscle targets, block type, equipment
- Queries graph for matching exercises
- Ranks by historical usage (prefer what athlete has done)
- Returns candidates for Claude to select

This enables smarter exercise selection for new plans.

### Phase 3: Historical Context (Later)

Enhance intent-based selection with:
- "Exercises used in similar blocks"
- "Exercises used for this goal"
- "Exercises not used in last N days" (for variety)

---

## Implementation Notes

### Batch Lookup Query

```cypher
UNWIND $names AS name
CALL db.index.fulltext.queryNodes('exercise_search', name) YIELD node, score
WITH name, node, score
ORDER BY name, score DESC
WITH name, COLLECT({id: node.id, name: node.name, score: score})[0..3] AS matches
RETURN name, matches
```

### Intent-Based Query

```cypher
// Get hip hinge exercises I've actually used, ranked by frequency
MATCH (e:Exercise)-[:INVOLVES]->(:MovementPattern {name: $pattern})
OPTIONAL MATCH (e)<-[:OF_EXERCISE]-(s:Set)
WITH e, COUNT(s) AS times_used
WHERE times_used > 0 OR $include_unused
RETURN e.id, e.name, times_used
ORDER BY times_used DESC
LIMIT $count
```

### KB Swing Canonical Gap

Should we create a canonical "Kettlebell Swing" and map the CUSTOM to it?

```cypher
// Create canonical exercise
CREATE (e:Exercise {
  id: 'CANONICAL:FFDB:KB_SWING_2H',
  name: 'Kettlebell Swing',
  aliases: ['KB swing', 'Russian swing', 'two-hand swing'],
  description: 'Two-handed kettlebell swing, hip hinge dominant'
})

// Map existing custom
MATCH (c:Exercise {id: 'CUSTOM:Kettlebell_Swings'})
MATCH (can:Exercise {id: 'CANONICAL:FFDB:KB_SWING_2H'})
MERGE (c)-[:MAPS_TO]->(can)
```

This preserves history on CUSTOM while creating a proper canonical reference.

---

## Success Criteria

1. **Single workout plan**: ≤3 tool calls (down from 15+)
2. **Week plan**: ≤10 tool calls (down from 50+)
3. **12-week mesocycle**: Feasible without crashing
4. **Exercise not found**: Returns "not found" with suggestions, doesn't crash plan creation

---

## Decisions (Jan 3, 2026 Discussion)

1. **Where does batch lookup live?** → **training-mcp**
   - Move `search_exercises` from profile-mcp to training-mcp
   - Training owns all exercise operations (search, suggest, substitute, safety check)
   - Neo4j MCP stays generic DB operations, not specialized
   - Other MCPs query Neo4j directly if needed

2. **Should create_workout_plan accept fuzzy names?** → **No, require resolved IDs**
   - Explicit is better than implicit
   - Claude normalizes first (semantic layer), then batch resolves IDs
   - Keep create_workout_plan strict — garbage in, error out

3. **How to handle low-confidence matches?** → **Reject and ask**
   - If <0.5 confidence after Claude's normalization, something is wrong
   - Don't "try harder" with automated fallbacks — leads to confabulation
   - Surface uncertainty, discuss with user
   - System improves over time as gaps are filled

4. **Historical preference weighting?** → **Baseline parameter in profile**
   - Store `novelty_preference` as profile field (e.g., 0.8 = conservative)
   - Context can adjust (deload → more familiar, "try something new" → override)
   - Save these deltas to tune the loop over time
   - Don't over-engineer derivation — start simple, learn from adjustments

---

## Implementation Status

### Phase 1: Batch Lookup — COMPLETE (Jan 3, 2026)

**Added to training-mcp:**
- `search_exercises(query, limit)` — single exercise fuzzy search
- `resolve_exercises(names[], confidence_threshold)` — batch resolution

**Files changed:**
- `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` — added search_exercises, resolve_exercises methods
- `src/arnold-training-mcp/arnold_training_mcp/server.py` — added tool definitions and handlers
- `src/arnold-profile-mcp/arnold_profile_mcp/server.py` — marked search_exercises as DEPRECATED

**Workflow now:**
```
Claude normalizes: ["KB swing", "RDL", "ab wheel"] → ["kettlebell swing", "romanian deadlift", "ab wheel rollout"]
Claude calls: resolve_exercises(["kettlebell swing", "romanian deadlift", "ab wheel rollout"])
Tool returns: {resolved: {...}, needs_clarification: {...}, not_found: [...]}
Claude builds plan with IDs or discusses problems with user
```

**Result:** Single tool call for all exercises instead of N calls.

### Phase 2: Intent-Based Selection — TODO

### Phase 3: Historical Context — TODO

---

## Related Files

- `src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py` — search_exercises, resolve_exercises, create_workout_plan
- `src/arnold-profile-mcp/arnold_profile_mcp/neo4j_client.py` — search_exercises (deprecated)
- `docs/ARCHITECTURE.md` — Exercise Matching Architecture section
- `docs/exercise_kb_improvement_plan.md` — Phase 8 matching work

---

## Notes from Discussion (Jan 3, 2026)

Brock raised several key points:

1. **Why is KB swing CUSTOM?** — FFDB gap, not system error. Should create canonical and map.

2. **Use vector search properly** — Claude should normalize first, then search. Not searching blindly.

3. **Pattern-first thinking** — Query by intent (hip hinge warmup) not just by name. Leverage graph structure.

4. **Historical workouts as training data** — 163 workouts tell us what Brock actually does. Use that.

5. **Scaling concern** — 12-week plan would kill current approach. Need fundamentally different architecture (block templates, lazy instantiation, constraint optimization).

6. **Agent/API architecture** — Consider pushing more logic out of LLM context into background services. MCP as thin API, real work happens elsewhere.
