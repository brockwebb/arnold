# Exercise Relationship Matching System

**Graph-Native Exercise Mapping with LLM Intelligence**

## Overview

This system builds knowledge graph relationships between user exercises and canonical exercises, enabling:
- Automatic muscle group inheritance
- Exercise variation tracking
- Substitute recommendations
- Progressive overload tracking across variations

## Architecture

```
User Exercise: "Sandbag Shoulder (Alternating)"
         ↓
    [LLM Analysis]
         ↓
   VARIATION_OF (confidence: 0.85)
         ↓
Canonical: "Sandbag Clean and Press"
         ↓
    [Inherit TARGETS]
         ↓
MuscleGroup: Shoulders, Core, Legs
```

## Relationship Types

**EXACT_MATCH** (confidence > 0.9)
- Same exercise, different name
- Example: "Bench Press" = "Barbell Bench Press"
- Inherits: ALL muscle mappings

**VARIATION_OF** (confidence > 0.7)
- Modified version (incline/decline/tempo/pause)
- Example: "Incline Bench Press" variation of "Bench Press"
- Inherits: ALL muscle mappings

**SIMILAR_TO** (confidence > 0.6)
- Similar movement, different equipment
- Example: "Dumbbell Press" similar to "Barbell Press"
- Inherits: Muscle mappings (conditional)

**SUBSTITUTES_FOR** (confidence > 0.6)
- Can replace in programming
- Example: "Push-up" substitutes "Bench Press"
- Inherits: NO automatic inheritance

## Files

**exercise_matcher.py**
- Core matching engine
- LLM-powered relationship analysis
- Neo4j graph construction

**map_exercises.py**
- Integration script
- Maps unmapped exercises
- Batch processing

**run_exercise_mapping.py**
- Quick script for Dec 26 workout
- Pre-configured with exercise IDs

## Usage

### Quick Start (Map Dec 26 Workout)

```bash
cd ~/Documents/GitHub/arnold/src
export OPENAI_API_KEY="your-key-here"
python run_exercise_mapping.py
```

### Manual Mapping

```bash
# Map all unmapped exercises
python map_exercises.py

# Map specific exercises by ID
python map_exercises.py --ids "ex-id-1" "ex-id-2"
```

### Programmatic

```python
from exercise_matcher import ExerciseMatcher

matcher = ExerciseMatcher()
result = matcher.match_exercise(
    user_exercise_name="Sandbag Shoulder (Alternating)",
    user_exercise_id="abc-123"
)

print(result)
# {
#   'matched': True,
#   'canonical_exercise': 'Sandbag Clean and Press',
#   'relationship_type': 'VARIATION_OF',
#   'confidence': 0.85,
#   'muscle_groups_inherited': True
# }
```

## Knowledge Graph Queries

**Find all bench press variations:**
```cypher
MATCH (ex:Exercise {name: "Barbell Bench Press"})-[:HAS_VARIATION*1..2]->(variant)
RETURN variant.name
```

**Find exercises targeting same muscles:**
```cypher
MATCH (ex1:Exercise {name: "Barbell Bench Press"})-[:TARGETS]->(mg:MuscleGroup)
MATCH (ex2:Exercise)-[:TARGETS]->(mg)
WHERE ex1 <> ex2
RETURN ex2.name, mg.name
```

**Find substitutes for an exercise:**
```cypher
MATCH (ex1:Exercise)-[:SUBSTITUTES_FOR]->(ex2:Exercise {name: "Barbell Bench Press"})
RETURN ex1.name
```

**Exercise progression chains:**
```cypher
MATCH path = (easier:Exercise)-[:PROGRESSION*]->(harder:Exercise)
WHERE easier.name = "Push-up"
RETURN path
```

## LLM Prompt Design

The system uses OpenAI gpt-5o-mini with 6 parallel workers for fast, cost-effective matching:

```
USER EXERCISE: "Seated Quad Extension"
CANONICAL EXERCISE: "Leg Extension"
MUSCLE GROUPS: Legs, Quadriceps

Determine relationship...
```

Response enforces JSON schema with confidence scores.

## Integration Points

**1. Workout Logging**
- neo4j_client.create_workout_node() returns exercises_needing_mapping
- server.py suggests running mapper

**2. Exercise Search**
- find_canonical_exercise tool enhanced with relationship traversal
- Searches EXACT_MATCH, VARIATION_OF, SIMILAR_TO

**3. Programming**
- Find substitutes for equipment limitations
- Track volume across variations
- Progressive overload through relationship chains

## Requirements

```bash
pip install openai neo4j python-dotenv tqdm
```

**Environment:**
```bash
export OPENAI_API_KEY="sk-..."
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"
export NEO4J_DATABASE="arnold"
```

## Examples

**Yesterday's Workout Mapping:**

```
🔍 Matching: Sandbag Shoulder (Alternating)
  Found 12 candidates:
    - Sandbag Clean and Press
    - Sandbag Shouldering
    - Sandbag Power Clean
  
  Analyzing: Sandbag Clean and Press
    Type: VARIATION_OF
    Confidence: 0.85
    Reasoning: Alternating variation of the clean and press movement
  
  ✅ Created VARIATION_OF relationship
     → Sandbag Clean and Press
     → Inherited muscle mappings: Shoulders, Core, Legs
```

## Graph Evolution

As exercises are logged:
1. User exercise created (source='user')
2. Matcher finds canonical matches
3. LLM analyzes relationships
4. Graph relationships created
5. Muscle groups inherited
6. Future queries leverage relationships

**Result:** Rich, interconnected exercise knowledge graph that gets smarter over time.

## Muscle Taxonomy

The system uses a two-layer muscle architecture:

**Layer 1: MuscleGroups (FFDB - practical tracking)**
- 9 muscle groups with 3,400+ exercise mappings
- Source: FFDB (open-source fitness database)
- Wikipedia citations for anatomical grounding
- Used for: Volume/frequency analysis, workout programming

**Layer 2: Muscles (Wikipedia - anatomical detail)**
- 31 detailed muscles with full anatomical info
- Linked TO muscle groups via PART_OF relationships
- Used for: Rehab planning, mobility work, injury prevention

Example:
```
MuscleGroup: "Chest" (49 exercises) → https://en.wikipedia.org/wiki/Pectoralis_major
  ├─ Muscle: "Pectoralis Major" (Pecs)
  ├─ Muscle: "Pectoralis Minor" (Pec Minor)
  └─ Muscle: "Serratus Anterior" (Serratus)
```

All muscle data is traceable to authoritative sources (Wikipedia, FFDB).
