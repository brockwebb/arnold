# ADR-003: Exercise Hierarchy and Variation Modeling

**Date:** January 8, 2026  
**Status:** Proposed  
**Deciders:** Brock Webb, Claude (Arnold development)  
**GitHub Issue:** [#10](https://github.com/brockwebb/arnold/issues/10)

## Context

The current exercise model is flat — all 4,242 exercises are peers with no hierarchical relationships. This creates several problems:

1. **Name inconsistency**: "Duffle Push Press", "Sandbag Push Press", "Push Press" are all separate exercises with no formal connection
2. **Alias resolution**: User says "duffle push press" but Coach can't resolve to canonical name
3. **Redundant enrichment**: We're enriching variations separately when they share core mechanics
4. **Lost intelligence**: No capture of WHY a variation exists or what it optimizes

However, variations have real value — they work muscles differently, serve different training purposes, and shouldn't be collapsed into parents.

## Problem Dimensions

### 1. Equipment Variations

Same movement, different implement changes the stimulus:

| Base | Variations |
|------|------------|
| Push Press | Sandbag Push Press, Duffle Push Press, KB Push Press |
| Deadlift | Trap Bar Deadlift, Kettlebell Deadlift, Sumo Deadlift |
| Row | Barbell Row, Dumbbell Row, Cable Row, T-Bar Row |

### 2. Movement Modifiers

Tempo/contraction type changes the training effect:

| Modifier | Effect | Example |
|----------|--------|---------|
| **Eccentric** | Slow lowering phase | Time under tension, strength |
| **Isometric** | Static hold | Stability, tendon strength |
| **Explosive/Plyometric** | Maximum velocity | Power, rate of force development |
| **Tempo** | Prescribed timing (e.g., 3-1-2-0) | Hypertrophy, control |
| **Paused** | Dead stop at specific position | Eliminates stretch reflex |

### 3. Compound Exercises

Combinations with emergent properties:

- **Burpee Dumbbell Deadlift** = Burpee + Deadlift (but the combination has unique metabolic/coordination demands)
- **Clean and Press** = Clean + Press (the transition is a skill itself)
- **Turkish Get-Up** = Multiple movement patterns in sequence

These aren't just parent+parent — they're distinct movements that happen to combine elements.

### 4. Stance/Grip/Position Variations

Mechanical changes that shift emphasis:

| Variation Type | Examples |
|----------------|----------|
| Stance | Sumo vs Conventional Deadlift |
| Grip | Wide-Grip vs Neutral-Grip Pull-Up |
| Angle | Incline vs Flat vs Decline Press |
| Unilateral | Single-Leg RDL vs Bilateral RDL |

## Decision

### New Relationships

```cypher
// Equipment/stance/grip variations
(v:Exercise)-[:VARIATION_OF {
  variation_type: 'equipment' | 'stance' | 'grip' | 'position' | 'unilateral',
  differentiator: 'sandbag instability increases core demand',
  optimizes_for: ['core stability', 'grip strength', 'functional transfer']
}]->(base:Exercise)

// Compound exercise composition
(compound:Exercise)-[:COMBINES {
  sequence: 1,
  transition_skill: 'hip drive into press'
}]->(component:Exercise)

// Emergent properties of compounds
(compound:Exercise {
  is_compound: true,
  emergent_properties: ['metabolic demand', 'coordination', 'full-body integration']
})

// Alias resolution
(e:Exercise)-[:KNOWN_AS]->(a:Alias {
  name: 'KB swing',
  source: 'common_shorthand'
})
```

### Variation Intelligence (Properties)

On `VARIATION_OF` relationship or Variation node:

| Property | Purpose | Example |
|----------|---------|---------|
| `differentiator` | What makes this mechanically different | "Trap bar shifts load to quads, reduces lumbar stress" |
| `optimizes_for` | Training goals this variation serves | `['quad emphasis', 'lower back friendly']` |
| `cautions` | When NOT to use | "Avoid with shoulder impingement" |
| `progression_from` | Natural progression path | Goblet Squat → Back Squat |
| `regression_to` | Easier alternative | Pull-Up → Assisted Pull-Up |

### Modifier Handling

**Decision: Modifiers live at SET level, not exercise level.**

Rationale:
- Same exercise can be performed with different modifiers on different sets
- "Eccentric Chin-Up" is how you perform a Chin-Up, not a different exercise
- Keeps exercise ontology clean (exercises are WHAT, modifiers are HOW)

```cypher
// Set-level modifier (in Postgres strength_sets table)
strength_sets.tempo = '3-1-2-0'
strength_sets.modifier = 'eccentric' | 'paused' | 'explosive' | null

// Or as relationship in Neo4j for planned sets
(ps:PlannedSet)-[:WITH_MODIFIER]->(m:Modifier {type: 'eccentric', phase: 'lowering'})
```

**Migration for existing "Eccentric X" exercises:**
- Keep them as-is for historical data integrity
- Create `VARIATION_OF` pointing to base exercise with `variation_type: 'modifier'`
- Going forward, prefer set-level modifier over new exercise creation

### Alias Resolution Layer

```cypher
(:Exercise)-[:KNOWN_AS]->(:Alias)
```

Aliases are just names — no muscle/pattern data. Coach resolves aliases to canonical exercise before planning.

**Common alias sources:**
- Equipment shorthand: "KB" → "Kettlebell", "BB" → "Barbell", "DB" → "Dumbbell"
- Regional names: "Skull Crusher" → "Lying Tricep Extension"
- Abbreviations: "RDL" → "Romanian Deadlift"
- Typos/variations: "Pullup" → "Pull-Up"

## Implementation Approach

### Phase 1: Alias Collection (Low effort, high impact)

1. Mine "related movements" from enrichment batch files
2. Create common abbreviation mappings (KB, BB, DB, RDL, etc.)
3. Create `KNOWN_AS` relationships
4. Update `search_exercises` to check aliases first

**Estimated scope:** ~200 aliases covering 80% of lookup failures

### Phase 2: Variation Relationships (Medium effort)

1. Identify base exercises for common variations
2. Create `VARIATION_OF` relationships with `variation_type`
3. Backfill `differentiator` and `optimizes_for` incrementally
4. Update `find_substitutes` to leverage variation relationships

**Estimated scope:** ~500 variation relationships

### Phase 3: Modifier Modeling (Schema change)

1. Add `modifier` and `tempo` columns to `strength_sets`
2. Update planning tools to capture modifiers
3. Migrate existing "Eccentric X" exercises to variation model
4. Update analytics to group by base exercise when appropriate

### Phase 4: Compound Exercise Connections (Medium effort)

1. Identify compound exercises in current data
2. Create `COMBINES` relationships with sequence
3. Document emergent properties
4. Enable "decompose this compound" queries for substitution

## What This Does NOT Require

- Deleting or merging existing exercises
- Re-enriching exercises (variations keep their own TARGETS)
- Changing historical workout data
- Major schema changes to Postgres (Phase 3 is additive)

## Consequences

### Positive

- Coach can resolve aliases to canonical names
- Programming can leverage variation relationships ("give me a harder push press variation")
- Knowledge graph captures exercise intelligence, not just muscle data
- Cleaner separation: base mechanics vs equipment vs execution style
- Better substitution logic: find variations when equipment unavailable

### Negative

- More relationships to maintain
- Need enrichment process for variation metadata
- Coach needs updated logic for alias resolution
- Some judgment calls on what constitutes "variation" vs "different exercise"

## Open Questions

1. **Inheritance**: Should `VARIATION_OF` inherit TARGETS from parent, or always explicit?
   - Leaning: Always explicit. Variations often shift emphasis.

2. **Threshold**: When is something a variation vs a different exercise?
   - Proposed heuristic: If >70% muscle overlap and same movement pattern = variation

3. **Bidirectional**: Should we track both "is variation of" and "has variation"?
   - Probably not needed — graph traversal works both directions

4. **Modifier granularity**: Just type, or full specification (e.g., "3-second eccentric")?
   - Start with type only, expand if needed

## References

- Current exercise count: 4,242 in Neo4j
- CANONICAL:ARNOLD exercises: 116 (these are most likely to have variations)
- Batch enrichment files contain "related movements" data — untapped resource
- Related issues: #11 (vectordb indexing), #12 (yoga/PT knowledge mining)
