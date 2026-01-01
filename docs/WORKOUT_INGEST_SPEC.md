# Arnold Workout Ingest Specification
**Version:** 0.1 (Draft)  
**Status:** Under Development - Revisit after ingest complete  
**Last Updated:** 2025-12-28

---

## Overview

This document defines the rules and patterns for ingesting workout logs into the Arnold Neo4j database. It captures lessons learned from importing 129+ workouts and establishes conventions for consistency.

---

## Schema Reference

```
(Workout)-[:HAS_BLOCK {order}]->(WorkoutBlock)
(WorkoutBlock)-[:USES_PROTOCOL]->(Protocol)
(WorkoutBlock)-[:CONTAINS {order}]->(Set)
(Set)-[:OF_EXERCISE]->(Exercise)
```

---

## 1. Workout Node

### Required Properties
| Property | Type | Description |
|----------|------|-------------|
| id | UUID | Auto-generated unique identifier |
| date | Date | Workout date (Neo4j date type) |
| type | String | One of: strength, conditioning, recovery, endurance, deload, mixed |

### Optional Properties
| Property | Type | Description |
|----------|------|-------------|
| notes | String | Summary/context. NULL if not provided (don't use 'n/a') |
| duration_minutes | Integer | Total session duration if known |
| rpe | Float | Overall session RPE (1-10) if provided |

### Type Definitions
- **strength**: Primary goal is building/maintaining strength (resistance training focus)
- **conditioning**: Primary goal is metabolic/cardiovascular (circuits, combat, HIIT)
- **recovery**: Active recovery, mobility, light movement
- **endurance**: Long runs, sustained aerobic work
- **deload**: Intentionally reduced volume/intensity
- **mixed**: No clear primary goal, or intentional blend

### Rules
1. One workout per date (no duplicates)
2. Type should be inferred from tags/goals in source markdown if not explicit
3. Notes capture the "why" or notable observations, not exercise details

---

## 2. WorkoutBlock Node

### Required Properties
| Property | Type | Description |
|----------|------|-------------|
| id | UUID | Auto-generated unique identifier |
| name | String | Block name (e.g., 'Warm-up', 'Main', 'Finisher') |

### Optional Properties
| Property | Type | Description |
|----------|------|-------------|
| rest_between_rounds_seconds | Integer | Rest after completing each round (circuits) |
| rest_between_exercises_seconds | Integer | Rest between exercises within a round |
| notes | String | Block-specific notes |

### Common Block Names
- Warm-up
- Primer / Microdose / Starter
- Main / Main Work / Main Circuit
- Superset A, Superset B (for labeled supersets)
- Finisher
- Daily Iso / Isometric
- Cooldown
- Accessory

### HAS_BLOCK Relationship
- Must include `order` property (1-indexed)
- Determines display/execution sequence

### Rules
1. Every workout must have at least one block
2. Block names should be consistent (use list above when applicable)
3. Empty blocks are invalid - every block must contain sets

---

## 3. Protocol Node

### Available Protocols
| Name | Description | Set Structure |
|------|-------------|---------------|
| Straight Sets | Traditional sets with rest between | set_number sequential |
| Circuit | Multiple exercises, minimal rest, repeat rounds | round + order |
| Superset | 2-3 exercises paired, rest after pair | round + order |
| EMOM | Every Minute On the Minute | set_number = minute |
| Tabata | 20s work / 10s rest x 8 | set_number or aggregate |
| AMRAP | As Many Rounds As Possible | aggregate or individual |
| Timed | Work for set duration | duration_seconds |
| Fight Gone Bad | Specific CrossFit format | round + order |

### USES_PROTOCOL Relationship
- Optional on WorkoutBlock (many blocks don't need explicit protocol)
- Helps with querying and analysis
- Informs how round/order should be interpreted

### Rules
1. Protocol is optional - don't force it if block structure is simple
2. Circuit and Superset require round/order on sets
3. Tabata/EMOM can be recorded as aggregate (one set, total duration) or individual intervals

---

## 4. Set Node

### Required Properties
| Property | Type | Description |
|----------|------|-------------|
| id | UUID | Auto-generated unique identifier |
| set_number | Integer | Sequential within exercise (1, 2, 3...) |

### Metric Properties (at least one required)
| Property | Type | Description |
|----------|------|-------------|
| reps | Integer | Repetition count |
| duration_seconds | Integer | Timed work (holds, carries by time) |
| distance_miles | Float | Distance work (runs, carries by distance) |

### Optional Properties
| Property | Type | Description |
|----------|------|-------------|
| load_lbs | Float | External load in pounds |
| rpe | Float | Rate of Perceived Exertion (1-10) |
| notes | String | Tempo, cues, deviations, per-side indicators |
| round | Integer | Circuit/superset round number (1-indexed) |
| order | Integer | Position within round (1-indexed) |

### CONTAINS Relationship
- Must include `order` property for sequencing within block
- Order is independent of set_number (order is block position, set_number is per-exercise)

### Rules
1. Every set must have at least one metric (reps, duration_seconds, or distance_miles)
2. load_lbs is NULL for bodyweight exercises (don't use 0)
3. "per side" work: use notes field, reps = total or per-side based on source
4. Weighted vests/belts: record in load_lbs with clarification in notes
5. For circuits: round = which iteration, order = position in that round
6. set_number increments per exercise across the workout (not per block)

### Tempo Notation
Record tempo in notes field as provided (e.g., "3-0-1 tempo", "5s eccentric")

### Failed/Partial Sets
Record as-performed with notes explaining (e.g., "failed at rep 3", "vest removed mid-set")

---

## 5. Exercise Resolution

### Lookup Priority
1. Search existing exercises by name pattern (case-insensitive)
2. Check for CUSTOM: exercises from previous imports
3. Create new CUSTOM: exercise if no match

### ID Convention
| Source | ID Pattern | Example |
|--------|------------|---------|
| free-exercise-db | EXERCISE:{Name} | EXERCISE:Pullups |
| functional-fitness-db | CANONICAL:FFDB:{number} | CANONICAL:FFDB:904 |
| User-created | CUSTOM:{Name} | CUSTOM:Sandbag_Push_Press |

### Naming Rules
1. Use underscores in IDs, spaces in names: `id: 'CUSTOM:Bear_Hug_Carry'`, `name: 'Bear Hug Carry'`
2. Capitalize major words: "Sandbag Push Press" not "sandbag push press"
3. Don't include load/reps in exercise name: "Long Run" not "15-mile Long Run"
4. Don't include equipment variants unless mechanically distinct: "Pull-up" covers bar variations

### Common Custom Exercises Created
Reference list of frequently used custom exercises to check before creating new:
- Sandbag: Push Press, Strict Press, Shouldering, Overhead Hold, Overhead Carry, Ground-to-Shoulder
- Carries: Farmer Carry, Bear Hug Carry, Bear Hug March, Overhead Keg Carry
- Hangs: Dead Hang, Weighted Dead Hang, Arched Hang, One-Arm Hang
- Core: V-Up, Hollow Hold, Hollow Rock, Slide-bag Side Plank, KB Boat Leg Lifts
- Machines: AirDyne, Rower
- Conditioning: Kickboxing, Heavy Bag Work, Jump Rope, Tire Flip

### Exercise Variants
If same movement with different equipment/stance, prefer notes over new exercise:
- "Goblet Squat" with notes "53lb KB" vs creating "Kettlebell Goblet Squat"
- Exception: Mechanically distinct (e.g., "Natural Grip Pull-ups" vs standard)

---

## 6. Aggregate vs Individual Sets

Some workouts describe work in aggregate. Guidelines:

### Record as Aggregate (single set)
- Tabata finishers: one set with duration_seconds: 240, notes describing rotation
- Warm-up flows: one set with duration_seconds and notes listing movements
- Active recovery walks: one set with distance_miles

### Record as Individual Sets
- Circuits with specific loads/reps per exercise per round
- Supersets with distinct exercises
- Any work where per-set progression matters for analysis

### Hybrid Approach
- Combat circuits (5 stations x 5 rounds): one set per station with duration = total time at station
- EMOM: individual sets if load/reps vary, aggregate if uniform

---

## 7. Source File Parsing

### Markdown Structure Expected
```markdown
---
date: 2025-MM-DD
type: "workout"
tags: [strength, posterior_chain, ...]
...
---

## Overview
Brief description

## Warm-Up
| Movement | Prescription | Notes |
...

## Main Work
...

## Finisher
...

## Notes
...
```

### Parsing Rules
1. Date from YAML frontmatter (required)
2. Type from frontmatter or inferred from tags
3. Each ## section becomes a WorkoutBlock candidate
4. Tables contain set data
5. Notes section feeds Workout.notes

### Handling Deviations
Source files often note deviations from plan. Record as-performed:
- "Dropped to 100lb final set" → record 100lb with note
- "Skipped due to grip fatigue" → don't create set
- "Added extra round" → record what was done

---

## 8. Validation Checks

### Pre-Import
1. Date doesn't already exist in database
2. At least one block with sets can be extracted

### Post-Import
Run after each workout:
```cypher
MATCH (w:Workout {date: date('YYYY-MM-DD')})-[:HAS_BLOCK]->(b)-[:CONTAINS]->(s)
RETURN count(DISTINCT b) as blocks, count(s) as sets
```

### Periodic Audit
```cypher
// Orphaned sets
MATCH (s:Set) WHERE NOT (s)<-[:CONTAINS]-(:WorkoutBlock) RETURN count(s)

// Sets without exercise
MATCH (s:Set) WHERE NOT (s)-[:OF_EXERCISE]->(:Exercise) RETURN count(s)

// Duplicate sets (same block, exercise, round, order, set_number)
MATCH (b:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
WITH b, e, s.round as r, s.order as o, s.set_number as n, count(s) as c
WHERE c > 1 RETURN count(*)
```

---

## 9. Open Questions (Revisit Post-Ingest)

1. **Rest Periods**: Block-level properties sufficient? Or need more granular modeling?

2. **Warm-up Detail Level**: Record each warm-up movement as separate set, or aggregate?

3. **Cooldown/Mobility**: Same question - individual stretches or aggregate?

4. **Failed Attempts**: How to record attempts that didn't count (e.g., "2 failed 130lb attempts before")?

5. **Isometric Progressions**: Duration is the metric, but how to track progression (longer holds vs heavier holds)?

6. **Heart Rate / Zone Data**: Worth capturing if provided? New property on Set or Workout?

7. **Exercise Mapping**: When to create SAME_AS relationships between CUSTOM and canonical exercises?

8. **Backward Compatibility**: As schema evolves, migration strategy for existing data?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-12-28 | Initial draft based on 129 workout imports |
