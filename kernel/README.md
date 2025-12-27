# Arnold Knowledge Graph Kernel

This directory contains the **shared knowledge** layer of the Arnold fitness knowledge graph. These Cypher files can be imported into any fresh Neo4j instance to bootstrap the system with exercise science ontologies, anatomy, and canonical exercise data.

## What is the Kernel?

The kernel is the **version-controlled foundation** of Arnold, containing:
- Scientific ontologies (FMA anatomy, energy systems)
- Canonical exercise databases (4,997 exercises from two sources)
- Exercise-to-muscle mappings
- Exercise source provenance and quality relationships

**Excluded:** Personal data (workouts, custom exercises, athlete profiles)

## Files Overview

Import these files **in order**:

### 1. `01_constraints.cypher` (1.1 KB)
Database constraints and unique indexes. Run this **first** on a fresh Neo4j instance.

**Contents:**
- Unique constraints for all node types
- Ensures data integrity

### 2. `02_reference_nodes.cypher` (3.0 KB)
Scientific reference data and standards.

**Contents:**
- 3 EnergySystem nodes (Margaria-Morton model: phosphagen, glycolytic, oxidative)
- 3 ObservationConcept nodes (LOINC codes for weight, heart rate, RPE)
- 17 EquipmentCategory nodes (barbell, dumbbell, kettlebell, etc.)

### 3. `03_anatomy.cypher` (13 KB)
FMA-based anatomy ontology.

**Contents:**
- 29 Muscle nodes (e.g., pectoralis major, biceps brachii)
- 19 MuscleGroup nodes (chest, back, legs, etc.)
- 41 BodyPart nodes (upper limb, thorax, etc.)
- Anatomy hierarchies (IS_A, INCLUDES relationships)

### 4. `04_exercise_sources.cypher` (669 B)
Exercise database provenance.

**Contents:**
- `SOURCE:free-exercise-db` - Open source (CC0 license)
- `SOURCE:functional-fitness-db` - Comprehensive (v2.9)

### 5. `05_canonical_exercises.cypher` (1.3 MB)
4,997 canonical exercises from two authoritative sources.

**Contents:**
- 873 exercises from Free-Exercise-DB
- 3,251 exercises from Functional Fitness Database
- Metadata: category, difficulty, body region, mechanics, force type

**Warning:** Large file (~5000 exercises, may take 30-60 seconds to import)

### 6. `06_exercise_relationships.cypher` (2.5 MB)
Exercise relationships and muscle mappings.

**Contents:**
- 4,124 SOURCED_FROM relationships (exercise → source provenance)
- 9,444 TARGETS relationships (exercise → muscle/muscle group)
- 907 SAME_AS relationships (cross-source duplicates marked)
- 890 HIGHER_QUALITY_THAN relationships (LLM quality assessment)

**Warning:** Large file, may take 60-120 seconds to import)

## Import Instructions

### Method 1: Neo4j Browser

1. Open Neo4j Browser
2. For each file in order:
   ```cypher
   :source /path/to/arnold/kernel/01_constraints.cypher
   :source /path/to/arnold/kernel/02_reference_nodes.cypher
   :source /path/to/arnold/kernel/03_anatomy.cypher
   :source /path/to/arnold/kernel/04_exercise_sources.cypher
   :source /path/to/arnold/kernel/05_canonical_exercises.cypher
   :source /path/to/arnold/kernel/06_exercise_relationships.cypher
   ```

### Method 2: cypher-shell (CLI)

```bash
cd /path/to/arnold/kernel

cat 01_constraints.cypher | cypher-shell -u neo4j -p password --format plain
cat 02_reference_nodes.cypher | cypher-shell -u neo4j -p password --format plain
cat 03_anatomy.cypher | cypher-shell -u neo4j -p password --format plain
cat 04_exercise_sources.cypher | cypher-shell -u neo4j -p password --format plain
cat 05_canonical_exercises.cypher | cypher-shell -u neo4j -p password --format plain
cat 06_exercise_relationships.cypher | cypher-shell -u neo4j -p password --format plain
```

### Method 3: Python Script

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

files = [
    "01_constraints.cypher",
    "02_reference_nodes.cypher",
    "03_anatomy.cypher",
    "04_exercise_sources.cypher",
    "05_canonical_exercises.cypher",
    "06_exercise_relationships.cypher"
]

with driver.session() as session:
    for filename in files:
        print(f"Importing {filename}...")
        with open(f"kernel/{filename}", 'r') as f:
            cypher = f.read()
            # Split on semicolons and execute each statement
            for statement in cypher.split(';'):
                if statement.strip():
                    session.run(statement)
        print(f"  ✓ Done")

driver.close()
```

## Expected Import Time

- **Small files (1-4):** <5 seconds each
- **Canonical exercises (5):** 30-60 seconds
- **Relationships (6):** 60-120 seconds
- **Total:** ~2-3 minutes

## Verification Queries

After import, verify the kernel loaded correctly:

```cypher
// Check node counts
MATCH (n) RETURN labels(n)[0] as label, count(n) as count ORDER BY count DESC;

// Expected results:
// Exercise: 4997
// Muscle: 29
// MuscleGroup: 19
// BodyPart: 41
// ExerciseSource: 2
// EnergySystem: 3
// ObservationConcept: 3
// EquipmentCategory: 17

// Check canonical exercises
MATCH (ex:Exercise)-[:SOURCED_FROM]->(src:ExerciseSource)
RETURN src.name, count(ex) as exercises
ORDER BY exercises DESC;

// Expected:
// Functional Fitness Database: 3251
// Free Exercise DB: 1746 (873 unique + 873 duplicates)

// Check unique canonical exercises (quality winners only)
MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
OPTIONAL MATCH (winner:Exercise)-[:HIGHER_QUALITY_THAN]->(ex)
WHERE winner IS NULL
RETURN count(ex) as unique_canonicals;

// Expected: 4107
```

## Architecture

```
Arnold Knowledge Graph Kernel
│
├── Scientific Foundation
│   ├── EnergySystem (3) - Metabolic pathways
│   ├── ObservationConcept (3) - LOINC measurement standards
│   └── EquipmentCategory (17) - Exercise equipment taxonomy
│
├── Anatomy Ontology (FMA)
│   ├── Muscle (29) - Individual muscles
│   ├── MuscleGroup (19) - Functional groupings
│   └── BodyPart (41) - Anatomical hierarchy
│
├── Exercise Sources (2)
│   ├── Free-Exercise-DB (CC0 license, 873 exercises)
│   └── Functional Fitness DB (v2.9, 3,251 exercises)
│
└── Canonical Exercises (4,107 unique)
    ├── SOURCED_FROM → ExerciseSource (provenance)
    ├── TARGETS → Muscle/MuscleGroup (muscle activation)
    ├── SAME_AS ↔ Exercise (duplicate detection)
    └── HIGHER_QUALITY_THAN → Exercise (quality preference)
```

## Data Provenance

### Free-Exercise-DB
- **License:** CC0 (Public Domain)
- **Source:** https://github.com/yuhonas/free-exercise-db
- **Exercises:** 873 (traditional gym exercises)
- **Strengths:** Good muscle mappings, difficulty ratings

### Functional Fitness Database
- **Version:** 2.9
- **Exercises:** 3,251 (functional training emphasis)
- **Strengths:** Body region, mechanics, force type metadata
- **Coverage:** Unconventional equipment (clubbells, macebells, gymnastic rings)

### Anatomy (FMA)
- **Source:** Foundational Model of Anatomy
- **Coverage:** 29 muscles, 41 body parts
- **Standard:** Biomedical ontology (UBERON-compatible)

## Dual-Source Strategy

Arnold uses a **pure relationship layer** to combine two exercise databases without data deletion:

1. **Provenance Tracking:** Every exercise tagged with source via SOURCED_FROM
2. **Duplicate Detection:** 17 cross-source duplicates found via exact name matching
3. **Quality Assessment:** LLM (Claude Sonnet 4.5) judges best version when duplicates exist
4. **Zero Data Loss:** All exercises preserved; duplicates marked with SAME_AS relationships

**Result:** 4,107 unique high-quality canonical exercises

## Kernel Updates

To regenerate the kernel from a running Neo4j instance:

```bash
cd /path/to/arnold/scripts/export
python export_kernel.py
```

This creates fresh `.cypher` files in the `kernel/` directory.

## Version History

- **v1.0** (2025-12-26): Initial kernel export
  - Dual-source exercise import complete
  - 4,107 unique canonical exercises
  - LLM-based quality assessment
  - FMA anatomy ontology

## Next Steps After Import

After importing the kernel, you can:

1. **Add Personal Data:**
   - Create Athlete nodes for users
   - Import workout logs
   - Map custom exercises using `scripts/importers/map_customs_final_gpt52.py`

2. **Explore the Graph:**
   ```cypher
   // Find exercises for a muscle
   MATCH (m:Muscle {name: "pectoralis major"})<-[:TARGETS]-(ex:Exercise)
   RETURN ex.name LIMIT 10;

   // Find exercise alternatives (same muscle targets)
   MATCH (ex:Exercise {name: "Barbell Bench Press"})-[:TARGETS]->(m:Muscle)
   MATCH (alt:Exercise)-[:TARGETS]->(m)
   WHERE alt <> ex
   RETURN DISTINCT alt.name, count(m) as shared_muscles
   ORDER BY shared_muscles DESC
   LIMIT 10;
   ```

3. **Build Applications:**
   - Workout planning
   - Exercise recommendations
   - Muscle group analysis
   - Training program generation

## License

The kernel contains data from multiple sources:

- **Free-Exercise-DB:** CC0 (Public Domain)
- **Functional Fitness DB:** Proprietary (v2.9)
- **FMA Anatomy:** Academic use
- **Arnold Scripts:** MIT License (see LICENSE file)

Refer to individual source licenses before redistribution.

## Support

For issues or questions:
- GitHub Issues: https://github.com/brock/arnold/issues
- Documentation: See `docs/` directory
- Scripts: See `scripts/` directory

---

**Generated:** 2025-12-26
**Arnold Version:** 1.0
**Neo4j Version:** 5.x compatible
