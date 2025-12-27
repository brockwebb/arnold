# Arnold Knowledge Graph - Claude Code Guide

> **For Claude Code AI Assistant**
> This file provides context about the Arnold project for AI-assisted development.

## Project Overview

**Arnold** is a Neo4j-based fitness knowledge graph that combines exercise science ontologies, anatomical models, and workout tracking. It provides a foundation for intelligent workout planning, exercise recommendations, and training analysis.

**Name Origin:** Named after Arnold Schwarzenegger, the knowledge graph aims to be a comprehensive fitness intelligence system.

## Current Status: ✅ Phase 1 Complete

**Version:** 1.0
**Last Updated:** 2025-12-26
**Status:** Kernel export complete, 100% custom exercise mapping achieved

### Completed Milestones

1. ✅ **FMA Anatomy Import** - 29 muscles, 41 body parts, hierarchical relationships
2. ✅ **Dual-Source Exercise Import** - 4,997 canonical exercises from two sources
3. ✅ **Graph Relationship Layer** - Pure relationship approach (zero data deletion)
4. ✅ **Custom Exercise Mapping** - 100% coverage (842/842) using GPT-5.2 + Claude Sonnet 4.5
5. ✅ **Kernel Export** - Version-controlled shared knowledge layer

## Technology Stack

- **Database:** Neo4j 5.x (graph database)
- **Python:** 3.11+ with neo4j-driver
- **Ontologies:** FMA (anatomy), LOINC (observations)
- **LLMs:** GPT-5.2 (OpenAI), Claude Sonnet 4.5 (Anthropic)
- **Data Sources:** Free-Exercise-DB (CC0), Functional Fitness DB (v2.9)

## Repository Structure

```
arnold/
├── src/
│   └── arnold/
│       ├── graph.py          # Neo4j connection wrapper
│       ├── models.py          # Data models
│       └── utils.py           # Helper functions
│
├── scripts/
│   ├── importers/             # Data import scripts
│   │   ├── import_fma.py                    # FMA anatomy import
│   │   ├── import_free_exercise_db.py       # Free-Exercise-DB import
│   │   ├── import_functional_fitness_db.py  # FFDB import
│   │   ├── create_graph_relationships.py    # Relationship layer builder
│   │   ├── map_customs_final_gpt52.py       # Custom mapping (GPT-5.2)
│   │   └── map_failures_sonnet45.py         # Failure recovery (Sonnet 4.5)
│   │
│   └── export/
│       └── export_kernel.py   # Export shared knowledge to .cypher files
│
├── kernel/                    # Importable shared knowledge (Cypher files)
│   ├── README.md
│   ├── 01_constraints.cypher
│   ├── 02_reference_nodes.cypher
│   ├── 03_anatomy.cypher
│   ├── 04_exercise_sources.cypher
│   ├── 05_canonical_exercises.cypher
│   └── 06_exercise_relationships.cypher
│
├── ontologies/                # Source ontology files (NOT in git, too large)
│   ├── anatomy/
│   │   └── fma.owl            # Foundational Model of Anatomy (266 MB)
│   ├── uberon/
│   │   ├── uberon-basic.obo   # Body part ontology (11 MB)
│   │   └── uberon-basic.json  # UBERON JSON (24 MB)
│   └── exercises/
│       ├── free-exercise-db/  # Git submodule (95 MB)
│       └── Functional+Fitness+Exercise+Database+(version+2.9).xlsx
│
├── docs/                      # Documentation
│   ├── GRAPH_RELATIONSHIP_LAYER_COMPLETE.md
│   └── DUAL_SOURCE_IMPORT_STATUS.md
│
├── .env                       # Credentials (NOT in git)
├── .gitignore                 # Excludes large ontology files
└── claude.md                  # This file
```

## Graph Schema

### Node Types

| Label | Count | Description | Unique Key |
|-------|-------|-------------|------------|
| `Exercise` | 5,839 | Exercises (4,997 canonical + 842 custom) | `id` |
| `ExerciseSource` | 2 | Exercise database sources | `id` |
| `Muscle` | 29 | Individual muscles (FMA) | `fma_id` |
| `MuscleGroup` | 19 | Functional muscle groupings | `id` |
| `BodyPart` | 41 | Anatomical body parts (FMA) | `uberon_id` |
| `EnergySystem` | 3 | Metabolic pathways | `type` |
| `ObservationConcept` | 3 | Measurement types (LOINC) | `loinc_code` |
| `EquipmentCategory` | 17 | Exercise equipment types | `id` |
| `Athlete` | 1 | User profile (Brock) | `id` |
| `Workout` | 200+ | Training sessions | `id` |
| `WorkoutSet` | 5000+ | Individual exercise sets | `id` |

### Relationship Types

| Type | Count | Description |
|------|-------|-------------|
| `SOURCED_FROM` | 4,124 | Exercise → ExerciseSource (provenance) |
| `TARGETS` | 9,444+ | Exercise → Muscle/MuscleGroup (activation) |
| `SAME_AS` | 907 | Exercise ↔ Exercise (duplicates, bidirectional) |
| `HIGHER_QUALITY_THAN` | 890 | Exercise → Exercise (quality preference) |
| `MAPS_TO` | 353 | Custom → Canonical exercise mapping |
| `IS_A` | 100+ | Anatomy hierarchy (e.g., Muscle → BodyPart) |
| `INCLUDES` | 50+ | MuscleGroup → Muscle containment |
| `PERFORMED` | 200+ | Athlete → Workout |
| `INCLUDES_SET` | 5000+ | Workout → WorkoutSet |
| `EXERCISES_WITH` | 5000+ | WorkoutSet → Exercise |

## Key Design Patterns

### 1. Pure Relationship Layer

Arnold uses a **relationship-based approach** to handle duplicate data without deletion:

```cypher
// Good: Original exercises preserved
MATCH (ex1:Exercise {source: "free-exercise-db", name: "Barbell Squat"})
MATCH (ex2:Exercise {source: "functional-fitness-db", name: "Barbell Squat"})
MERGE (ex1)-[:SAME_AS]->(ex2)
MERGE (ex1)-[:HIGHER_QUALITY_THAN {confidence: 0.85}]->(ex2)

// Bad: Don't delete data
// DELETE ex2  ❌
```

**Benefits:**
- Full audit trail
- Queryable quality comparisons
- Reversible decisions
- No data loss

### 2. Provenance Tracking

Every canonical exercise has source attribution:

```cypher
MATCH (ex:Exercise)-[:SOURCED_FROM]->(src:ExerciseSource)
RETURN ex.name, src.name, ex.imported_at
```

### 3. Quality-Aware Queries

Get unique canonical exercises (quality winners only):

```cypher
MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
OPTIONAL MATCH (winner:Exercise)-[:HIGHER_QUALITY_THAN]->(ex)
WHERE winner IS NULL
RETURN ex
```

### 4. Dual-Model LLM Strategy

Custom exercise mapping uses two LLMs for optimal coverage:

1. **GPT-5.2** (OpenAI): Fast, cost-effective, handles 87.9% of exercises
2. **Claude Sonnet 4.5** (Anthropic): Handles edge cases, achieves 100% recovery

**Results:**
- 353 exercises mapped to canonical
- 489 exercises assigned muscles via LLM knowledge
- 842/842 total coverage (100%)

## Common Operations

### Finding Exercises

```cypher
// Find exercises for a muscle
MATCH (m:Muscle {name: "pectoralis major"})<-[:TARGETS]-(ex:Exercise)
WHERE ex.is_canonical = true
RETURN ex.name, ex.category, ex.difficulty
LIMIT 10;

// Find exercise alternatives
MATCH (ex:Exercise {name: "Barbell Bench Press"})-[:TARGETS]->(m:Muscle)
MATCH (alt:Exercise)-[:TARGETS]->(m)
WHERE alt <> ex AND alt.is_canonical = true
RETURN DISTINCT alt.name, count(m) as shared_muscles
ORDER BY shared_muscles DESC
LIMIT 10;

// Find exercises by equipment
MATCH (eq:EquipmentCategory {name: "Dumbbell"})<-[:REQUIRES_EQUIPMENT]-(ex:Exercise)
RETURN ex.name
LIMIT 20;
```

### Workout Analysis

```cypher
// Find athlete's recent workouts
MATCH (a:Athlete {id: "ATHLETE:brock"})-[:PERFORMED]->(w:Workout)
RETURN w.date, w.duration_minutes, w.total_volume
ORDER BY w.date DESC
LIMIT 10;

// Analyze muscle group coverage
MATCH (a:Athlete)-[:PERFORMED]->(w:Workout)
MATCH (w)-[:INCLUDES_SET]->(ws:WorkoutSet)
MATCH (ws)-[:EXERCISES_WITH]->(ex:Exercise)
MATCH (ex)-[:TARGETS]->(mg:MuscleGroup)
WHERE w.date >= date() - duration({days: 7})
RETURN mg.common_name, count(ws) as sets
ORDER BY sets DESC;
```

### Custom Exercise Management

```cypher
// Find unmapped custom exercises
MATCH (ex:Exercise)
WHERE ex.id STARTS WITH 'CUSTOM:'
  AND NOT EXISTS {MATCH (ex)-[:MAPS_TO]->()}
  AND (ex.llm_assigned_muscles IS NULL OR ex.llm_assigned_muscles = false)
RETURN ex.name;

// Check mapping coverage
MATCH (ex:Exercise)
WHERE ex.id STARTS WITH 'CUSTOM:'
WITH count(ex) as total
MATCH (mapped:Exercise)
WHERE mapped.id STARTS WITH 'CUSTOM:'
  AND (EXISTS {MATCH (mapped)-[:MAPS_TO]->()}
       OR mapped.llm_assigned_muscles = true)
RETURN total, count(mapped) as mapped,
       100.0 * count(mapped) / total as coverage_pct;
```

## Environment Setup

### Required Environment Variables

Create `.env` file in project root:

```bash
# Neo4j Connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=arnold

# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Python Environment

```bash
# Create conda environment
conda create -n arnold python=3.11
conda activate arnold

# Install dependencies
pip install neo4j python-dotenv openai anthropic tqdm pandas openpyxl
```

### Neo4j Setup

1. Install Neo4j Desktop or use Neo4j Aura
2. Create database named "arnold"
3. Import kernel files (see `kernel/README.md`)
4. Verify import with queries in kernel documentation

## Import Workflow

### Fresh Database Setup

```bash
# 1. Import kernel (shared knowledge)
cd /path/to/arnold
# Follow instructions in kernel/README.md

# 2. Import personal workout data (if available)
python scripts/importers/import_workout_logs.py

# 3. Map custom exercises to canonical
python scripts/importers/map_customs_final_gpt52.py
python scripts/importers/map_failures_sonnet45.py  # if needed
```

### Re-export Kernel

```bash
# After making changes to canonical exercises/relationships
python scripts/export/export_kernel.py

# Commit updated kernel files
git add kernel/
git commit -m "Update kernel export"
```

## Code Style & Patterns

### Neo4j Queries

**DO:**
```python
# Use ArnoldGraph wrapper
from arnold.graph import ArnoldGraph

graph = ArnoldGraph()
result = graph.execute_query("""
    MATCH (ex:Exercise)-[:TARGETS]->(m:Muscle)
    RETURN ex.name, m.name
    LIMIT 10
""")
graph.close()
```

**DON'T:**
```python
# Don't use raw neo4j driver directly
from neo4j import GraphDatabase
driver = GraphDatabase.driver(...)  # ❌ Use ArnoldGraph wrapper
```

### LLM Integration

**DO:**
```python
# Use concurrent workers for bulk operations
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=6) as executor:
    futures = {executor.submit(process_exercise, ex): ex for ex in exercises}
    for future in as_completed(futures):
        result = future.result()
```

**DON'T:**
```python
# Don't process exercises sequentially
for ex in exercises:  # ❌ Too slow
    result = process_exercise(ex)
```

### Property Naming

**DO:**
- Use snake_case: `is_canonical`, `llm_assigned`, `created_at`
- Add provenance: `source`, `imported_at`, `model_version`
- Include confidence: `confidence`, `human_verified`

**DON'T:**
- Use camelCase: `isCanonical` ❌
- Omit timestamps: Missing `created_at` ❌
- Skip provenance: Unknown data source ❌

## Testing & Validation

### Verification Queries

```cypher
// Check node counts
MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count DESC;

// Verify canonical exercise count
MATCH (ex:Exercise)-[:SOURCED_FROM]->()
OPTIONAL MATCH (winner)-[:HIGHER_QUALITY_THAN]->(ex)
WHERE winner IS NULL
RETURN count(ex);  // Should be 4,107

// Check custom exercise mapping
MATCH (ex:Exercise)
WHERE ex.id STARTS WITH 'CUSTOM:'
RETURN
  count(ex) as total,
  sum(CASE WHEN EXISTS {(ex)-[:MAPS_TO]->()} THEN 1 ELSE 0 END) as mapped_canonical,
  sum(CASE WHEN ex.llm_assigned_muscles = true THEN 1 ELSE 0 END) as mapped_llm;
// Should be: total=842, sum=842
```

### Database Health Checks

Run these regularly:

```cypher
// Find orphaned exercises (no muscle targets)
MATCH (ex:Exercise)
WHERE NOT EXISTS {MATCH (ex)-[:TARGETS]->()}
  AND ex.is_canonical = true
RETURN count(ex);  // Should be 0

// Find exercises with no source
MATCH (ex:Exercise)
WHERE ex.is_canonical = true
  AND NOT EXISTS {MATCH (ex)-[:SOURCED_FROM]->()}
RETURN count(ex);  // Should be 0

// Check for duplicate IDs
MATCH (ex:Exercise)
WITH ex.id as id, count(ex) as cnt
WHERE cnt > 1
RETURN id, cnt;  // Should be empty
```

## Development Guidelines

### When Adding New Features

1. **Check existing patterns** - Review similar scripts in `scripts/importers/`
2. **Use ArnoldGraph wrapper** - Don't use raw neo4j driver
3. **Add provenance** - Always tag where data came from
4. **Include timestamps** - Use `imported_at`, `created_at`, `updated_at`
5. **Document relationships** - Update this file with new relationship types
6. **Update kernel export** - If changing canonical data, re-export kernel

### When Modifying Canonical Data

1. **Never delete canonical exercises** - Use HIGHER_QUALITY_THAN instead
2. **Always maintain SOURCED_FROM** - Provenance is critical
3. **Re-export kernel** - Run `export_kernel.py` after changes
4. **Document changes** - Update relevant docs in `docs/`

### When Adding New Scripts

1. **Follow naming convention** - `import_*.py`, `map_*.py`, `export_*.py`
2. **Add docstring** - Explain what the script does
3. **Use tqdm for progress** - Show progress bars for long operations
4. **Handle errors gracefully** - Don't crash on single failures
5. **Print summary stats** - Show counts at completion

## Known Issues & Limitations

### Current Limitations

1. **No semantic duplicate detection** - Only exact name matching for duplicates
2. **No exercise video/images** - Text metadata only
3. **Limited equipment taxonomy** - Only 17 categories
4. **Static muscle mappings** - No dynamic muscle activation based on form/variation

### Future Enhancements

1. **Semantic search** - Embedding-based exercise similarity
2. **Program templates** - Pre-built training programs
3. **Exercise progression** - Difficulty progression paths
4. **Form analysis** - Video/image analysis integration
5. **Nutrition integration** - Meal planning and macros
6. **Recovery tracking** - Sleep, HRV, readiness scores

## Troubleshooting

### Common Issues

**Problem:** `ModuleNotFoundError: No module named 'neo4j'`
```bash
# Solution: Install in correct conda environment
conda activate arnold
pip install neo4j
```

**Problem:** `AuthError: The client is unauthorized`
```bash
# Solution: Check .env file has correct credentials
cat .env | grep NEO4J_PASSWORD
```

**Problem:** LLM API rate limits
```python
# Solution: Reduce NUM_WORKERS in script
NUM_WORKERS = 3  # Reduce from 6
```

**Problem:** Kernel import fails
```bash
# Solution: Check Neo4j database is empty
# In Neo4j Browser:
MATCH (n) RETURN count(n);  // Should be 0 before import
```

## Resources

### Documentation
- `kernel/README.md` - Kernel import guide
- `docs/GRAPH_RELATIONSHIP_LAYER_COMPLETE.md` - Relationship layer details
- `docs/DUAL_SOURCE_IMPORT_STATUS.md` - Import history

### External Resources
- Neo4j Cypher Manual: https://neo4j.com/docs/cypher-manual/
- FMA Ontology: http://si.washington.edu/projects/fma
- Free-Exercise-DB: https://github.com/yuhonas/free-exercise-db

### Contact
- GitHub: https://github.com/brock/arnold
- Issues: https://github.com/brock/arnold/issues

---

**Last Updated:** 2025-12-26
**Maintained by:** Brock
**For:** Claude Code AI Assistant
