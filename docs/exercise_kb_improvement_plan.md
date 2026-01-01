# Exercise Knowledge Base Improvement Plan

**Created:** 2024-12-29  
**Updated:** 2024-12-29 (Phase 1-4 Complete)
**Status:** Phase 5 In Progress  
**Priority:** Critical for coaching intelligence

---

## Current State (Post Phase 1-4)

| Metric | Count |
|--------|-------|
| Exercises with muscle targeting | 4,082 |
| TARGETS relationships | 10,534 |
| Muscles (active) | 47 |
| MovementPatterns | 26 |
| ACTIVATES (pattern→muscle) | 116 |
| Custom workout exercises | 144 |
| Custom with canonical mappings | 31 |
| Custom needing work | 113 |

---

## Graph Query Patterns

### Core Principle: Traverse, Don't Duplicate

Custom workout exercises link to canonical exercises via `MAPS_TO` or `VARIATION_OF`. 
Muscle targeting lives on canonical exercises. Queries traverse the chain.

**Pattern 1: Get muscles for any exercise (including custom)**

```cypher
// Direct targeting OR inherited via mapping
MATCH (e:Exercise {id: $exerciseId})
OPTIONAL MATCH (e)-[:TARGETS]->(directMuscle:Muscle)
OPTIONAL MATCH (e)-[:MAPS_TO|VARIATION_OF]->(canonical:Exercise)-[:TARGETS]->(inheritedMuscle:Muscle)
WITH e, collect(DISTINCT directMuscle) + collect(DISTINCT inheritedMuscle) as muscles
UNWIND muscles as m
RETURN DISTINCT m.name as muscle, m.region
```

**Pattern 2: Get all muscles worked in a workout**

```cypher
MATCH (w:Workout {date: $date})-[:HAS_BLOCK]->()-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
OPTIONAL MATCH (e)-[:TARGETS]->(m1:Muscle)
OPTIONAL MATCH (e)-[:MAPS_TO|VARIATION_OF]->()-[:TARGETS]->(m2:Muscle)
WITH s, coalesce(m1, m2) as muscle
WHERE muscle IS NOT NULL
RETURN muscle.name, muscle.region, sum(s.reps) as totalReps
ORDER BY totalReps DESC
```

**Pattern 3: Find exercises targeting a specific muscle**

```cypher
// Returns both canonical exercises AND custom exercises that map to them
MATCH (m:Muscle {name: $muscleName})<-[:TARGETS]-(e:Exercise)
OPTIONAL MATCH (custom:Exercise)-[:MAPS_TO|VARIATION_OF]->(e)
WHERE custom.source = 'user_workout_log'
RETURN e.name as canonicalExercise, collect(custom.name) as yourVariants
```

**Pattern 4: Movement pattern inference for custom exercises**

```cypher
// Custom exercise → canonical → movement pattern → muscles
MATCH (custom:Exercise {source: 'user_workout_log'})
OPTIONAL MATCH (custom)-[:MAPS_TO|VARIATION_OF]->(canonical:Exercise)-[:HAS_MOVEMENT_PATTERN]->(mp:MovementPattern)
OPTIONAL MATCH (mp)-[:ACTIVATES]->(m:Muscle)
RETURN custom.name, mp.name as pattern, collect(m.name) as inferredMuscles
```

---

## Completed Phases

### ✅ Phase 1: Muscle Ontology (Complete)

- 47 muscles with Wikipedia-grounded definitions
- Trapezius split into Upper/Mid/Lower
- Individual hamstrings added (Biceps Femoris, Semimembranosus, Semitendinosus)
- Quadriceps components added (Rectus Femoris, Vastus Lateralis/Medialis/Intermedius)
- Rotator cuff muscles explicit (Supraspinatus, Infraspinatus, Teres Minor, Subscapularis)
- Region property on all muscles

### ✅ Phase 2: Movement Patterns (Complete)

26 movement patterns with 116 muscle activations:
- Push patterns: Horizontal Push, Vertical Push, Incline Push
- Pull patterns: Horizontal Pull, Vertical Pull  
- Lower body: Hip Hinge, Squat, Lunge, Split Squat
- Core: Anti-Extension, Anti-Rotation, Anti-Lateral Flexion, Trunk Flexion, Trunk Rotation
- Carries: Loaded Carry, Overhead Carry
- Power: Hip Extension Power, Upper Body Power
- Isolation: Knee Extension, Knee Flexion, Hip Flexion, Hip Abduction, Hip Adduction
- Specialty: Scapular, Grip, Rotator Cuff

### ✅ Phase 3: FFDB → Muscle Targeting (Complete)

- 3,216 FFDB exercises linked to muscles
- 7,969 TARGETS relationships created
- Used Prime Mover, Secondary, Tertiary from source
- role property: 'primary', 'secondary', 'tertiary'

### ✅ Phase 4: Free-Exercise-DB → Muscle Targeting (Complete)

- 866 exercises linked to muscles  
- 2,565 TARGETS relationships created
- Merged with existing FFDB relationships

---

## Current Work: Phase 5

### 5A: Validate Chain Traversal (Complete)
31 custom exercises with existing MAPS_TO relationships work via chain traversal.

### 5B: Match Unmapped → Canonical (In Progress)
113 custom exercises need MAPS_TO relationships to canonical exercises.

**Categories identified:**
- Easy canonical matches (Pallof Press, Kettlebell Swings, Box Step-Up)
- Equipment variants (Chain Overhead Press, Sandbag variations)
- Combo movements (Burpee Dumbbell Deadlift, Trap Bar Deadlift RDL Combo)
- Mobility/yoga (Cat-Cow, Pigeon Pose, Thread-the-Needle)
- Specialized (Jefferson Curl, Helms Row, Viking Press)
- Activities (Boxing, Kickboxing, Wood Splitting)

**Approach:** LLM-powered matching against 4,000+ canonical exercises.

### 5C: Direct Targeting for Unique Exercises
Exercises with no canonical equivalent get direct TARGETS relationships.
Examples: Wood Splitting, specific mobility drills.

---

## Remaining Phases

### Phase 6: Link Exercises to MovementPatterns

Currently 0 `HAS_MOVEMENT_PATTERN` relationships.
4,082 exercises need pattern classification.

### Phase 7: Validation Queries

- Coverage metrics
- Orphan detection
- Relationship consistency checks

---

## Architecture Notes

### Why Traverse Instead of Copy

Custom exercises should NOT have their own TARGETS relationships copied from canonical exercises.

**Reasons:**
1. Single source of truth - if canonical targeting is updated, custom inherits automatically
2. Cleaner graph semantics - MAPS_TO means "is a variant of"
3. Avoids data duplication and sync issues
4. Query patterns handle traversal cleanly

**Exception:** Truly unique exercises (no canonical equivalent) get direct TARGETS.

### MCP Instruction Layer

Query helpers should be documented in MCP function descriptions so coaching queries "just work" without requiring callers to understand the graph structure.

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Exercises → specific Muscle | 4,082 | All active |
| Custom exercises with targeting path | 31 | 144 |
| Movement Patterns defined | 26 | 26 ✓ |
| ACTIVATES relationships | 116 | 116 ✓ |
| HAS_MOVEMENT_PATTERN | 0 | 4,082 |

---

## Key Files

- Plan: `/arnold/docs/exercise_kb_improvement_plan.md`
- Muscle ontology source: Wikipedia (cited in creation)
- FFDB: `/arnold/ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx`
- Free-Exercise-DB: `/arnold/ontologies/exercises/free-exercise-db/dist/exercises.json`
