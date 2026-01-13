# Exercise Resolution Diagnostic Handoff

**Date:** 2026-01-08
**Status:** NEW - Diagnostic needed
**Priority:** HIGH - Blocks workout logging
**Previous Related:** `2026-01-07-exercise-normalization-handoff.md` (migration completed)

---

## Problem Statement

Exercise resolution fails on common inputs ("KB swing", "RDL", etc.), blocking workout logging. The migration work (Jan 7) is complete — CUSTOM exercises are gone, canonical exercises exist. But the **search/resolution step** still fails to find them.

## Current Architecture

```
User Input          Claude              MCP Tool              Neo4j
"KB swing"    →    (normalize?)    →   search_exercises   →   FTS Index
                   "kettlebell           query: ???           Exercises
                    swing" ???                                 (4,242)
```

### What We Have
- **Neo4j**: 4,242 exercises with FTS index
- **Tool**: `search_exercises` in arnold-training-mcp (uses FTS, NOT vector search)
- **Tool**: `resolve_exercises` (batch resolution with confidence scoring)
- **Design intent**: Claude normalizes abbreviations BEFORE calling tool

### What We DON'T Have
- Vector/semantic search for exercises (only for observations in memory-mcp)
- Populated embeddings on Exercise nodes (field exists, empty)
- KNOWN_AS alias relationships (ADR-003 proposes this)

## Key Question

**Where is resolution failing?**

| Failure Point | Symptom | Fix |
|---------------|---------|-----|
| Claude not normalizing | "KB swing" reaches tool as "KB swing" | Prompt/instruction fix |
| Exercise name mismatch | Canonical name is "Swing, Kettlebell" not "Kettlebell Swing" | Data/alias fix |
| FTS scoring too strict | Near-matches scored below threshold | Config tuning |
| FTS index config | Wrong fields indexed, bad tokenization | Index rebuild |

## Diagnostic Steps for Next Thread

### Step 1: Capture a Failing Case
Ask: "Log a workout with KB swings, RDLs, and chin-ups"
Observe: Which exercises fail? What error message?

### Step 2: Check What Reaches the Tool
Look at `resolve_exercises` input — is Claude normalizing?
- If input is "KB swing" → Claude not normalizing
- If input is "kettlebell swing" → Tool/data issue

### Step 3: Check Canonical Names in Neo4j
```cypher
MATCH (e:Exercise)
WHERE e.name =~ '(?i).*swing.*' OR e.name =~ '(?i).*kettlebell.*'
RETURN e.id, e.name, e.aliases
LIMIT 20;
```

What's the actual canonical name? Is it:
- "Kettlebell Swing"
- "KB Swing"  
- "Swing, Kettlebell"
- Something else?

### Step 4: Test FTS Directly
```cypher
CALL db.index.fulltext.queryNodes('exercise_search', 'kettlebell swing')
YIELD node, score
RETURN node.id, node.name, score
LIMIT 10;
```

Does it find the exercise? What score?

### Step 5: Check Tool Implementation
File: `/src/arnold-training-mcp/src/tools/exercises.ts`

What threshold is used? How is the query constructed?

## Key Files

| File | Purpose |
|------|---------|
| `/src/arnold-training-mcp/src/tools/exercises.ts` | search_exercises, resolve_exercises implementation |
| `/src/arnold-training-mcp/src/index.ts` | Tool registration, may have context |
| `/docs/adr/003-exercise-hierarchy.md` | Proposes KNOWN_AS aliases (not implemented) |

## Possible Fixes (In Order of Preference)

### 1. Prompt Fix (Minutes)
If Claude isn't normalizing, add explicit instruction in tool description or system prompt.

### 2. FTS Tuning (Hours)
Adjust scoring threshold, add fuzzy matching, tune tokenization.

### 3. Add Aliases to Data (Hours)
Create common abbreviations as properties on Exercise nodes:
```cypher
MATCH (e:Exercise) WHERE e.name = 'Kettlebell Swing'
SET e.aliases = ['KB swing', 'KB swings', 'kettlebell swings', 'Russian swing']
```
Update FTS index to include aliases field.

### 4. KNOWN_AS Relationships (ADR-003 Phase 1) (Day)
Full alias system with separate nodes and relationships.

### 5. Vector Search (Days)
Add embeddings to exercises, semantic search. Heavier lift but solves the problem properly.

## Architecture Reference

From ADR-003:
> "Claude should NORMALIZE the query first (semantic layer). Example: 'KB swing' → 'kettlebell swing' BEFORE calling this tool. The tool handles string matching variations (swing vs swings)."

From arnold-training-mcp tool description:
> "IMPORTANT: Claude should NORMALIZE all names first (semantic layer). Example: ['KB swing', 'RDL'] → ['kettlebell swing', 'romanian deadlift']"

**The design relies on Claude normalizing.** If that's not happening, that's the root cause.

## Questions for Brock Before Starting

1. **Do you have a specific failing case?** (e.g., "Yesterday I tried to log X and it failed")

2. **What error did you see?** 
   - "Not found"
   - "Low confidence" 
   - "Wrong exercise matched"
   - Something else?

3. **Is this happening with specific exercises or all exercises?**
   - If specific: which ones?
   - If all: likely systemic (FTS index, threshold)

4. **Have you noticed if Claude's normalization is working?**
   - Do you see "kettlebell swing" in the tool call, or "KB swing"?

---

## Session Completed Today (Jan 8)

For context, this thread completed:

1. **Architecture doc split** — ARCHITECTURE.md → modular `/docs/architecture/` with 11 files
2. **ADR-003 formalized** — Exercise Hierarchy and Variation Modeling (from Issue #10)
3. **ADR-004 drafted** — Decision Trace System (new Issue #13)
4. **System diagrams created** — SV-0, SV-1, data flow, intelligence stack in `/docs/architecture/diagrams/`

The exercise resolution diagnostic was identified as next priority because it blocks daily coaching workflow.

---

## Start the Next Thread With

```
Let's diagnose exercise resolution failures. 

First, I'll try to log a workout with common abbreviations to see what fails:
"Log: 3x10 KB swings, 3x8 RDLs, 3x5 chin-ups"

Then we'll trace through where it breaks.
```

