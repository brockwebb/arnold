# FR-005: Exercise Alias System

## Metadata
- **Priority**: High
- **Status**: Proposed
- **Created**: 2026-01-09
- **Dependencies**: ADR-003 (Exercise Hierarchy)

## Description

Implement a robust exercise alias system that enables natural language exercise references to resolve to canonical exercise IDs. The system must handle:

1. **Abbreviations**: "KB swing" → Kettlebell Swing
2. **Pluralization**: "chin-ups" → Chin-Up
3. **Regional variants**: "press-ups" → Push-Up
4. **Common misspellings**: "deadlfit" → Deadlift
5. **Partial matches**: "bench" → Barbell Bench Press (with clarification)

## Problem Statement

Current exercise resolution fails on common inputs:

| Input | Expected | Actual Result |
|-------|----------|---------------|
| "KB swing" | Kettlebell Swing | ✅ Works (alias exists) |
| "RDL" | Romanian Deadlift | ⚠️ Needs clarification (no alias) |
| "chin-ups" | Chin-Up | ⚠️ Low confidence (1.88 score) |
| "bench press" | Barbell Bench Press | ❌ Returns Incline variant |

**Root Cause**: 
- Some exercises have aliases populated, many don't
- FTS index may not include aliases field
- Confidence threshold may be too strict
- Abbreviation handling is inconsistent

## Current State

### Alias Storage
Aliases currently stored as array property on Exercise nodes:
```cypher
(:Exercise {
    id: 'CANONICAL:ARNOLD:KB_SWING_2H',
    name: 'Kettlebell Swing',
    aliases: ['KB swing', 'Russian swing', 'two-hand swing', 'kettlebell swings']
})
```

**Problem**: ~90% of exercises have empty or null aliases.

### FTS Index
```cypher
CREATE FULLTEXT INDEX exercise_search FOR (e:Exercise) ON EACH [e.name, e.description]
```

**Problem**: Does NOT include `aliases` field.

## Target State

### Enhanced Alias Coverage

Every exercise used in workouts should have:
1. Common abbreviations
2. Plural forms
3. Equipment-qualified name (if ambiguous)

### FTS Index Update
```cypher
DROP INDEX exercise_search;
CREATE FULLTEXT INDEX exercise_search FOR (e:Exercise) ON EACH [e.name, e.description, e.aliases_text];
```

Where `aliases_text` is aliases joined as a searchable string.

### Resolution Flow

```
User Input: "RDL"
     │
     ▼
┌─────────────────────────────────────────┐
│ Step 1: Check exact alias match         │
│ MATCH (e:Exercise) WHERE 'RDL' IN e.aliases │
│ → Found? Return immediately (high confidence) │
└─────────────────────────────────────────┘
     │ Not found
     ▼
┌─────────────────────────────────────────┐
│ Step 2: FTS search with fuzzy matching  │
│ Query: 'RDL~' (fuzzy) + 'RDL' (exact)  │
│ → Multiple results? Rank by score      │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ Step 3: Confidence check                │
│ Score > 0.8? → Return top match        │
│ Score 0.5-0.8? → Return with clarification │
│ Score < 0.5? → "Not found, did you mean..." │
└─────────────────────────────────────────┘
```

## Alias Sources

### 1. Batch Enrichment Files
`/data/enrichment/batches/batch_00X.md` contain:
- Alternative names
- Related exercises
- Common abbreviations

**Action**: Parse and extract aliases during enrichment.

### 2. User Corrections
When user manually specifies an exercise after failed resolution:
```
User: "Log 3x5 RDL"
System: "Did you mean Romanian Deadlift or Barbell Romanian Deadlift?"
User: "Romanian Deadlift"
```
**Action**: Auto-add "RDL" as alias to selected exercise.

### 3. Common Abbreviations (Seed Data)

| Abbreviation | Full Name |
|--------------|-----------|
| KB | Kettlebell |
| DB | Dumbbell |
| BB | Barbell |
| RDL | Romanian Deadlift |
| SLDL | Stiff-Leg Deadlift |
| OHP | Overhead Press |
| BP | Bench Press |
| BW | Bodyweight |
| SL | Single Leg |
| SA | Single Arm |

## Data Model Options

### Option A: Property Array (Current)
```cypher
(:Exercise {aliases: ['KB swing', 'Russian swing']})
```
✅ Simple
❌ FTS can't search arrays directly (need `aliases_text` workaround)

### Option B: KNOWN_AS Relationships (ADR-003)
```cypher
(:Alias {name: 'KB swing'})-[:KNOWN_AS]->(:Exercise {name: 'Kettlebell Swing'})
```
✅ Graph-native
✅ Can add metadata (source, confidence)
❌ More complex queries

### Recommendation: Hybrid
- Keep `aliases` array for simple cases
- Add `aliases_text` computed property for FTS
- Reserve KNOWN_AS relationships for complex mappings (e.g., "burpee" → multiple exercises)

## Acceptance Criteria

- [ ] `aliases_text` property added to all Exercise nodes
- [ ] FTS index rebuilt to include `aliases_text`
- [ ] Resolution tool uses two-phase search (exact alias → FTS)
- [ ] Common abbreviations seeded for top 50 exercises
- [ ] User corrections auto-populate aliases
- [ ] "chin-ups" → Chin-Up resolves with high confidence
- [ ] "RDL" → Romanian Deadlift resolves (or offers clear disambiguation)
- [ ] "bench press" → Barbell Bench Press (not Incline)

## MCP Interface Changes

```typescript
// Enhanced search with alias priority
search_exercises(query: string, options?: { include_aliases: boolean, fuzzy: boolean })
  → [
      { id: '...', name: 'Romanian Deadlift', match_type: 'alias', alias_matched: 'RDL', score: 1.0 },
      { id: '...', name: 'Barbell Romanian Deadlift', match_type: 'fts', score: 0.85 }
    ]

// Add alias after user clarification
add_exercise_alias(exercise_id: string, alias: string, source: 'user' | 'batch' | 'seed')
  → { status: 'added', exercise_id: '...', new_alias: 'RDL' }
```

## Technical Notes

### FTS Alias Text Generation
```cypher
// One-time migration
MATCH (e:Exercise)
WHERE e.aliases IS NOT NULL AND size(e.aliases) > 0
SET e.aliases_text = reduce(s = '', a IN e.aliases | s + ' ' + a)
```

### Abbreviation Expansion
Before FTS query, expand known abbreviations:
```python
def expand_abbreviations(query: str) -> str:
    expansions = {
        'kb': 'kettlebell',
        'db': 'dumbbell',
        'bb': 'barbell',
        'rdl': 'romanian deadlift',
        'bw': 'bodyweight',
        'sl': 'single leg',
        'sa': 'single arm',
    }
    tokens = query.lower().split()
    expanded = [expansions.get(t, t) for t in tokens]
    return ' '.join(expanded)
```

**Note**: This should happen in the tool, not rely on Claude to normalize.

## Open Questions

- [ ] Should alias matching be case-insensitive? (Probably yes)
- [ ] How to handle ambiguous abbreviations? (e.g., "press" = bench press? OHP? Leg press?)
- [ ] Should we track alias usage frequency to improve ranking?
- [ ] What's the confidence threshold for auto-accept vs clarification?
