# Exercise Knowledge Base Improvement Plan

**Created:** 2024-12-29  
**Updated:** 2026-01-02 (Phase 8 Infrastructure Complete)
**Status:** Phase 5 In Progress, Phase 8 ✅ Complete  
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

## Phase 8: Exercise Matching Architecture

**Created:** January 2, 2026  
**Updated:** January 2, 2026  
**Status:** Core Infrastructure Complete, Incremental Enrichment Ongoing

### The Problem

Current `find_canonical_exercise` uses exact string matching (toLower). This fails on:

| User Says | DB Has | Result |
|-----------|--------|--------|
| "KB swing" | "Kettlebell Swing" | ❌ Not found |
| "pull up" | "Pullups" | ❌ Wrong match |
| "push up" | "Push_Up_to_Side_Plank" | ❌ Wrong exercise |
| "landmine press" | — | ❌ Missing from DB |
| "sit ups" | — | ❌ Missing from DB |

**Root causes:**
1. Brittle string matching (spaces, underscores, plurals)
2. Missing common exercises from source databases
3. No alias/synonym support
4. Asking the database to do semantic matching (it can't)

### The Solution: Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEMANTIC LAYER (Claude)                      │
│  "KB swing" → "Kettlebell Swing"                                │
│  Normalization, synonym resolution, context understanding       │
│  Claude IS the semantic layer — stop outsourcing this to DB     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL LAYER (Neo4j)                      │
│  Full-text index + Vector index                                 │
│  Returns candidates, Claude picks best match                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ENRICHMENT LAYER (Graph)                     │
│  Aliases, common_names, descriptions on Exercise nodes          │
│  Rich metadata enables better retrieval                         │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Components

#### 1. Exercise Node Enrichment

Add properties to Exercise nodes:

```cypher
(:Exercise {
  id: string,
  name: string,                    // Canonical name
  aliases: [string],               // ["KB swing", "Russian swing", "hip hinge swing"]
  common_names: [string],          // ["Kettlebell Swing", "Two-Hand KB Swing"]
  description: string,             // For vector embedding
  equipment_required: [string],    // ["kettlebell"]
  embedding: [float]               // 1536-dim vector (added incrementally)
})
```

#### 2. Full-Text Index

```cypher
// Create full-text index across name, aliases, common_names
CREATE FULLTEXT INDEX exercise_search IF NOT EXISTS
FOR (e:Exercise)
ON EACH [e.name, e.aliases, e.common_names]
```

Query pattern:
```cypher
CALL db.index.fulltext.queryNodes('exercise_search', 'kettlebell swing~')
YIELD node, score
RETURN node.id, node.name, score
ORDER BY score DESC
LIMIT 5
```

#### 3. Vector Index (Neo4j Native)

Neo4j 5.x has native vector search. Same pattern as observations:

```cypher
// Create vector index
CREATE VECTOR INDEX exercise_embedding_index IF NOT EXISTS
FOR (e:Exercise)
ON e.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}}
```

Query pattern:
```cypher
CALL db.index.vector.queryNodes(
  'exercise_embedding_index',
  5,                              // top k
  $query_embedding                // user query embedded
) YIELD node, score
RETURN node.id, node.name, score
```

#### 4. Incremental Embedding Strategy

**Don't embed everything upfront.** Add embeddings as exercises are touched:

1. **On exercise use** — When an exercise is logged or planned, if it lacks an embedding, generate one
2. **On alias addition** — When aliases are added, regenerate embedding from enriched text
3. **Batch backfill** — Low-priority background job for remaining exercises

Embedding input text:
```python
embedding_text = f"{exercise.name}. {exercise.description or ''}. Also known as: {', '.join(exercise.aliases or [])}."
```

#### 5. Tool Redesign

**Before (wrong approach):**
```python
def find_canonical_exercise(name: str) -> str:
    # DB does matching — fails on synonyms
    query = "MATCH (e:Exercise) WHERE toLower(e.name) = toLower($name)"
```

**After (correct approach):**
```python
def search_exercises(query: str, limit: int = 5) -> list:
    """
    Search exercises using full-text + vector fallback.
    Returns candidates for Claude to select from.
    """
    # 1. Try full-text first (fast, handles typos)
    results = fulltext_search(query)
    
    # 2. If sparse results, try vector search (semantic)
    if len(results) < 2:
        results += vector_search(query)
    
    return results  # Claude picks the right one
```

Claude's role:
- Normalize user input before searching ("KB" → "Kettlebell")
- Evaluate candidates and pick best match
- Create custom exercise if nothing matches

### Workflow: Exercise Resolution

```
User: "I did 3x10 KB swings"
        │
        ▼
Claude normalizes: "kettlebell swing"
        │
        ▼
Tool: search_exercises("kettlebell swing")
        │
        ▼
┌─────────────────────────────────────────┐
│ Candidates:                              │
│ 1. Kettlebell Swing (score: 0.95)       │
│ 2. One-Arm Kettlebell Swing (0.82)      │
│ 3. Kettlebell Snatch (0.71)             │
└─────────────────────────────────────────┘
        │
        ▼
Claude selects: "Kettlebell Swing" (two-hand, standard)
        │
        ▼
If not found: Create custom exercise with MAPS_TO to closest canonical
```

### Gap Filling: Missing Exercises

Many common exercises are missing from source databases. Create as needed:

| Missing | Category | Action |
|---------|----------|--------|
| Sit-Ups | Core | Create with targeting |
| Landmine Press | Pressing | Create with targeting |
| Two-Hand KB Swing | Hip Hinge | Create OR add alias to existing |
| Sandbag Ground-to-Shoulder | Strongman | Create with targeting |
| Cat-Cow | Mobility | Create with targeting |
| Jefferson Curl | Mobility/Hinge | Create with targeting |

### Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Full-text index | ✅ | ✅ |
| Vector index | ✅ | ✅ |
| Exercises with aliases | 51 | 500+ common exercises |
| Exercises with embeddings | 0 | Add incrementally |
| Match rate on common names | ~85% | >95% |

**Initial aliases added:**
- Pushups (push-up, push up, etc.)
- Pullups (pull-up, pull up, chin-up, etc.)
- Sit-Up (sit up, situp, etc.)
- Single Arm Landmine Shoulder Press (landmine press, etc.)
- Kettlebell Swings (kb swing, russian swing, etc.)
- Trap Bar Deadlift (hex bar deadlift, etc.)

### Implementation Priority

1. **Now:** Create full-text index, test with current data
2. **Now:** Fill critical gaps (sit-ups, landmine press, etc.)
3. **Now:** Create vector index infrastructure
4. **Ongoing:** Add aliases as exercises are used
5. **Ongoing:** Generate embeddings incrementally

---

## Key Files

- Plan: `/arnold/docs/exercise_kb_improvement_plan.md`
- Muscle ontology source: Wikipedia (cited in creation)
- FFDB: `/arnold/ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx`
- Free-Exercise-DB: `/arnold/ontologies/exercises/free-exercise-db/dist/exercises.json`
