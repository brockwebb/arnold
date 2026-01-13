# Arnold Knowledge Graph

> A Neo4j-based fitness knowledge graph combining exercise science ontologies, anatomical models, and workout tracking.

**Named after Arnold Schwarzenegger** - A comprehensive fitness intelligence system for workout planning, exercise recommendations, and training analysis.

---

## 🎯 Project Status

**Version:** 1.0 (2025-12-26)
**Status:** ✅ Phase 1 Complete - Kernel Export Ready

### Quick Stats

- 📚 **4,997 canonical exercises** from two authoritative sources
- 💪 **29 FMA muscles** with anatomical hierarchies
- 🎯 **100% custom exercise mapping** (842/842)
- 🔬 **Zero data deletion** through pure relationship layer
- 📦 **Exportable kernel** for fresh database imports

---

## What is Arnold?

Arnold is a **Neo4j graph database** that models:
- Exercise science ontologies (FMA anatomy, LOINC observations)
- Canonical exercise databases (Free-Exercise-DB + Functional Fitness DB)
- Workout tracking and analysis
- Custom exercise-to-canonical mappings using LLMs

### Key Features

✅ **Dual-Source Exercise Database**
- 873 exercises from Free-Exercise-DB (CC0 license)
- 3,251 exercises from Functional Fitness Database (v2.9)
- 4,107 unique high-quality exercises after deduplication

✅ **LLM-Powered Custom Exercise Mapping**
- GPT-5.2 for bulk mapping (87.9% coverage)
- Claude Sonnet 4.5 for edge case recovery (100% recovery)
- 842/842 custom exercises successfully mapped

✅ **Scientific Foundation**
- 29 muscles from Foundational Model of Anatomy (FMA)
- 19 functional muscle groups
- 41 anatomical body parts with hierarchies
- Margaria-Morton energy system model

✅ **Pure Relationship Layer**
- Zero data deletion
- Full provenance tracking
- LLM quality assessment preserved
- Queryable duplicate detection

---

## Quick Start

### Prerequisites

- **Neo4j 5.x** (Desktop or Aura)
- **Python 3.11+**
- **Conda** (recommended) or pip/venv

### 1. Clone Repository

```bash
git clone https://github.com/brock/arnold.git
cd arnold
```

### 2. Setup Environment

```bash
# Create conda environment
conda create -n arnold python=3.11
conda activate arnold

# Install dependencies
pip install neo4j python-dotenv openai anthropic tqdm pandas openpyxl
```

### 3. Configure Neo4j

Create `.env` file:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=arnold

# Optional: For custom exercise mapping
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Import Kernel (Shared Knowledge)

```bash
# Option 1: Neo4j Browser
# In Neo4j Browser, run each file in order:
:source /path/to/arnold/kernel/01_constraints.cypher
:source /path/to/arnold/kernel/02_reference_nodes.cypher
:source /path/to/arnold/kernel/03_anatomy.cypher
:source /path/to/arnold/kernel/04_exercise_sources.cypher
:source /path/to/arnold/kernel/05_canonical_exercises.cypher
:source /path/to/arnold/kernel/06_exercise_relationships.cypher

# Option 2: cypher-shell (CLI)
cd kernel
for file in *.cypher; do
  cat $file | cypher-shell -u neo4j -p password --format plain
done
```

**See [kernel/README.md](kernel/README.md) for detailed import instructions.**

### 5. Verify Import

```cypher
// In Neo4j Browser
MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count DESC;

// Expected:
// Exercise: 4997
// Muscle: 29
// MuscleGroup: 19
// ...
```

### 6. Start Exploring

```cypher
// Find exercises for chest
MATCH (m:Muscle {name: "pectoralis major"})<-[:TARGETS]-(ex:Exercise)
RETURN ex.name, ex.category, ex.difficulty
LIMIT 10;

// Find exercise alternatives
MATCH (ex:Exercise {name: "Barbell Bench Press"})-[:TARGETS]->(m:Muscle)
MATCH (alt:Exercise)-[:TARGETS]->(m)
WHERE alt <> ex
RETURN DISTINCT alt.name, count(m) as shared_muscles
ORDER BY shared_muscles DESC
LIMIT 10;
```

---

## Repository Structure

```
arnold/
├── src/arnold/              # Python library
│   ├── graph.py             # Neo4j wrapper
│   ├── models.py            # Data models
│   └── utils.py             # Utilities
│
├── scripts/
│   ├── importers/           # Data import scripts
│   │   ├── import_fma.py
│   │   ├── import_free_exercise_db.py
│   │   ├── import_functional_fitness_db.py
│   │   ├── create_graph_relationships.py
│   │   ├── map_customs_final_gpt52.py
│   │   └── map_failures_sonnet45.py
│   │
│   └── export/
│       └── export_kernel.py # Export kernel to .cypher files
│
├── kernel/                  # Importable shared knowledge ✅
│   ├── README.md
│   ├── 01_constraints.cypher
│   ├── 02_reference_nodes.cypher
│   ├── 03_anatomy.cypher
│   ├── 04_exercise_sources.cypher
│   ├── 05_canonical_exercises.cypher (1.3 MB)
│   └── 06_exercise_relationships.cypher (2.5 MB)
│
├── ontologies/              # Source files (NOT in git, too large)
│   ├── anatomy/fma.owl      # 266 MB
│   ├── uberon/*.obo         # 11 MB
│   └── exercises/           # Free-Exercise-DB + FFDB
│
├── docs/                    # Documentation
│   ├── GRAPH_RELATIONSHIP_LAYER_COMPLETE.md
│   └── DUAL_SOURCE_IMPORT_STATUS.md
│
├── README.md                # This file
├── claude.md                # Claude Code AI guide
├── PROJECT_STATUS.md        # Current status & roadmap
└── .env                     # Credentials (create this)
```

---

## Documentation

### For Developers

- **[claude.md](claude.md)** - Comprehensive guide for Claude Code AI assistant
- **[PROJECT_STATUS.md](PROJECT_STATUS.md)** - Current status, metrics, and roadmap
- **[kernel/README.md](kernel/README.md)** - Kernel import and structure guide

### For Users

- **[GRAPH_RELATIONSHIP_LAYER_COMPLETE.md](GRAPH_RELATIONSHIP_LAYER_COMPLETE.md)** - Relationship layer architecture
- **[DUAL_SOURCE_IMPORT_STATUS.md](DUAL_SOURCE_IMPORT_STATUS.md)** - Dual-source import history

---

## Graph Schema

### Core Node Types

| Label | Count | Description |
|-------|-------|-------------|
| `Exercise` | 5,839 | Canonical + custom exercises |
| `Muscle` | 29 | FMA individual muscles |
| `MuscleGroup` | 19 | Functional groupings |
| `ExerciseSource` | 2 | Free-Exercise-DB + Functional Fitness DB |
| `BodyPart` | 41 | Anatomical hierarchy |
| `EnergySystem` | 3 | Margaria-Morton metabolic model |

### Core Relationships

| Type | Purpose |
|------|---------|
| `SOURCED_FROM` | Exercise → ExerciseSource provenance |
| `TARGETS` | Exercise → Muscle/MuscleGroup activation |
| `SAME_AS` | Exercise ↔ Exercise duplicates |
| `HIGHER_QUALITY_THAN` | Exercise → Exercise quality preference |
| `MAPS_TO` | Custom → Canonical exercise mapping |
| `IS_A` | Anatomical hierarchy |
| `INCLUDES` | MuscleGroup → Muscle containment |

**See [claude.md](claude.md) for complete schema and query examples.**

---

## Example Queries

### Find Exercises by Muscle

```cypher
// Chest exercises
MATCH (m:Muscle {name: "pectoralis major"})<-[:TARGETS]-(ex:Exercise)
WHERE ex.is_canonical = true
RETURN ex.name, ex.category, ex.difficulty
ORDER BY ex.difficulty
LIMIT 10;
```

### Find Exercise Alternatives

```cypher
// Alternatives to Barbell Squat
MATCH (ex:Exercise {name: "Barbell Squat"})-[:TARGETS]->(m:Muscle)
MATCH (alt:Exercise)-[:TARGETS]->(m)
WHERE alt <> ex AND alt.is_canonical = true
RETURN DISTINCT alt.name, count(m) as shared_muscles
ORDER BY shared_muscles DESC
LIMIT 10;
```

### Analyze Workout History

```cypher
// Muscle group coverage last 7 days
MATCH (a:Athlete)-[:PERFORMED]->(w:Workout)
MATCH (w)-[:INCLUDES_SET]->(ws:WorkoutSet)
MATCH (ws)-[:EXERCISES_WITH]->(ex:Exercise)
MATCH (ex)-[:TARGETS]->(mg:MuscleGroup)
WHERE w.date >= date() - duration({days: 7})
RETURN mg.common_name, count(ws) as sets
ORDER BY sets DESC;
```

---

## Key Features Explained

### Dual-Source Exercise Import

Arnold combines two exercise databases:

1. **Free-Exercise-DB** (873 exercises)
   - License: CC0 (Public Domain)
   - Focus: Traditional gym exercises
   - Strengths: Good muscle mappings, difficulty ratings

2. **Functional Fitness Database** (3,251 exercises)
   - Version: 2.9
   - Focus: Functional training, unconventional equipment
   - Strengths: Body region, mechanics, force type metadata

**Result:** 4,107 unique exercises after LLM-based deduplication

### Pure Relationship Layer

Instead of deleting duplicate data, Arnold uses relationships:

```cypher
// Duplicates marked, not deleted
(ex1:Exercise)-[:SAME_AS]->(ex2:Exercise)
(ex1)-[:HIGHER_QUALITY_THAN {confidence: 0.85}]->(ex2)

// Query quality winners only
MATCH (ex:Exercise)-[:SOURCED_FROM]->()
WHERE NOT EXISTS {()-[:HIGHER_QUALITY_THAN]->(ex)}
RETURN ex
```

**Benefits:**
- Full audit trail
- Reversible decisions
- Queryable quality comparisons
- Zero data loss

### LLM-Powered Custom Exercise Mapping

Custom exercises from workout logs are mapped using two LLMs:

1. **GPT-5.2** (OpenAI): Bulk processing, 87.9% coverage
2. **Claude Sonnet 4.5** (Anthropic): Edge case recovery, 100% final coverage

**Results:**
- 353 exercises mapped to canonical
- 489 exercises assigned muscles via LLM knowledge
- 842/842 total (100% coverage)

---

## Development

### Running Scripts

```bash
# Activate environment
conda activate arnold

# Import FMA anatomy
python scripts/importers/import_fma.py

# Import canonical exercises
python scripts/importers/import_free_exercise_db.py
python scripts/importers/import_functional_fitness_db.py

# Build relationship layer
python scripts/importers/create_graph_relationships.py

# Map custom exercises (requires OpenAI/Anthropic API keys)
python scripts/importers/map_customs_final_gpt52.py
python scripts/importers/map_failures_sonnet45.py

# Export kernel
python scripts/export/export_kernel.py
```

### Testing

```bash
# Verify node counts
python -c "
from arnold.graph import ArnoldGraph
g = ArnoldGraph()
result = g.execute_query('MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count DESC')
for r in result: print(f'{r[\"label\"]}: {r[\"count\"]}')
g.close()
"
```

---

## Roadmap

### ✅ Phase 1 Complete (Q4 2024)
- FMA anatomy import
- Dual-source exercise import
- Custom exercise mapping (100% coverage)
- Kernel export

### 🔄 Phase 2 (Q1 2025)
- Program templates
- Exercise recommendations
- Workout analytics dashboard

### 📋 Phase 3 (Q2 2025)
- Semantic exercise search
- Form analysis integration
- Multi-user support

### ✅ HRR Pipeline (Q1 2025)
- Heart Rate Recovery extraction from Polar sessions
- Gap-aware EWMA/CUSUM trend detection
- Per-stratum SDD thresholds

### 🚀 Future
- Nutrition integration
- AI workout generation

**See [PROJECT_STATUS.md](PROJECT_STATUS.md) for detailed roadmap.**

---

## Heart Rate Recovery (HRR) Pipeline

This pipeline extracts robust in-session HRR intervals (HRR30/60, HRR_frac, early slope, AUC₀₋₆₀) using a local pre-peak baseline, flags truncated windows and τ censoring, and computes a per-interval confidence score (R², accel quietness, window length, normalized magnitude). Intervals are weighted by confidence into a `weighted_value` stream and monitored with gap-aware EWMA (λ=0.2) and one-sided CUSUM detectors; alert thresholds are tied to per-stratum SDD (data-driven) rather than hard bpm cutoffs. τ is retained only as a descriptive metric for uncensored windows (do not use censored τ for alerts). Defaults: include events ≥5 bpm above local baseline, single-event actionable ≈13 bpm, and practical alerting when EWMA/CUSUM exceed SDD (recommended alert ~12 bpm for this dataset). This setup prioritizes reliable longitudinal signals from messy field data while minimizing false alarms.

**Usage:**
```bash
# Extract intervals with stratified visualization
python scripts/hrr_batch.py --output outputs/hrr_all.csv --plot-beeswarm --stratified

# Test EWMA/CUSUM detectors
python src/arnold/hrr/detect.py
```

**See [docs/hrr-data-quality-checklist.md](docs/hrr-data-quality-checklist.md) for implementation details.**

---

## Performance

### Import Times
- Kernel import: ~2-3 minutes (5,000+ exercises)
- Custom mapping: ~8 minutes (842 exercises with dual-LLM)

### Database Size
- Kernel (shared): ~50 MB
- Personal data: ~20 MB
- Total: ~70 MB

---

## Contributing

### Guidelines

1. **Never delete canonical data** - Use HIGHER_QUALITY_THAN relationships
2. **Always maintain provenance** - Tag source, timestamp, confidence
3. **Document relationships** - Update claude.md with new types
4. **Re-export kernel** - Run `export_kernel.py` after changes
5. **Follow existing patterns** - Review scripts/importers/ for style

### Pull Requests

- Include tests/verification queries
- Update relevant documentation
- Keep commits focused and atomic
- Follow existing code style

---

## License

- **Arnold Scripts:** MIT License
- **Free-Exercise-DB:** CC0 (Public Domain)
- **Functional Fitness DB:** Proprietary (v2.9)
- **FMA Anatomy:** Academic use

Refer to individual source licenses before redistribution.

---

## Acknowledgments

### Data Sources
- [Free-Exercise-DB](https://github.com/yuhonas/free-exercise-db) by yuhonas
- Functional Fitness Database v2.9
- [Foundational Model of Anatomy (FMA)](http://si.washington.edu/projects/fma)
- [UBERON Anatomy Ontology](http://uberon.github.io/)

### Technology
- [Neo4j](https://neo4j.com/) - Graph database platform
- [OpenAI](https://openai.com/) - GPT-5.2 API
- [Anthropic](https://anthropic.com/) - Claude Sonnet 4.5 API

### Inspiration
- **Arnold Schwarzenegger** - Namesake and fitness icon
- **Margaria & Morton** - Energy systems research

---

## Contact

- **GitHub Issues:** https://github.com/brock/arnold/issues
- **Documentation:** See `docs/` and `claude.md`
- **Maintainer:** Brock

---

**Built with 💪 by Brock**
**Last Updated:** 2025-12-26
