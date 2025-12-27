**You're right - I'll output the full STANDARDS_AND_ONTOLOGIES.md here:**

---

# Arnold: Standards & Ontologies Reference

## Purpose

This document catalogs all external standards, ontologies, and scientific references used in Arnold's knowledge graph architecture. It serves as the authoritative source for understanding what we import, why, and how.

---

## Active Standards (Currently Used)

### 1. FMA (Foundational Model of Anatomy)

**Purpose**: Human anatomy reference (muscles, bones, joints)

**Why FMA over UBERON**: 
- FMA is human-specific (UBERON is cross-species - includes fish fins, mouse tails)
- Gold standard for clinical human anatomy
- More detailed musculoskeletal coverage

**Download**:
- Source: http://sig.biostr.washington.edu/projects/fm/
- Direct OWL: http://purl.obolibrary.org/obo/fma.owl
- Format: OWL (Web Ontology Language)
- Size: ~100MB, ~75,000 classes

**License**: Open source, attribution required (CC BY)

**Import Strategy**: **TARGETED IMPORT**
- Extract only muscles referenced in Free-Exercise-DB (~200 muscles)
- Include parent hierarchy (muscle → muscle group → body region)
- Result: ~300-400 anatomy nodes (vs 75,000 bloat)
- Maintains FMA IDs for future medical literature linking

**Status**: ✅ Imported (70 Muscle nodes, 41 BodyPart nodes, 39 hierarchical relationships)

**File Location**: `/ontologies/anatomy/fma.owl`

---

### 2. Free-Exercise-DB

**Purpose**: Canonical exercise library with muscle mappings

**Why Free-Exercise-DB**: 
- CC0 license (public domain, MIT-compatible)
- ~800 exercises with primary/secondary muscle targets
- Includes equipment, difficulty, instructions
- Active community maintenance

**Download**:
- GitHub: https://github.com/yuhonas/free-exercise-db
- Clone: `git clone https://github.com/yuhonas/free-exercise-db.git`
- Format: JSON
- Size: ~2MB

**License**: CC0 1.0 (Public Domain Dedication)

**Import Strategy**: 
- Import all ~800 exercises as canonical nodes
- Link to FMA muscles via TARGETS relationships
- Serve as base for variation hierarchy (Arnold's innovation)

**Status**: ✅ Imported (873 canonical exercises, 2,081 muscle targets)

**File Location**: `/ontologies/exercises/free-exercise-db/`

---

### 3. LOINC (Logical Observation Identifiers Names and Codes)

**Purpose**: Standardized codes for health observations (body weight, heart rate, VO2max)

**Why LOINC**: 
- Universal standard for lab/clinical observations
- Enables interoperability with medical systems
- Required for clinical validation studies

**Download**:
- Source: https://loinc.org/
- **Requires**: Free account registration
- Format: CSV / Access database
- Size: Large (90,000+ codes)

**License**: Free for use, attribution required

**Import Strategy**: **STUB ONLY (Phase 1-4)**
- Created 3 manual ObservationConcept nodes:
  - Body Weight (29463-7)
  - Resting Heart Rate (8867-4)
  - Heart Rate Variability (80404-7)
- Full LOINC import deferred to Phase 6

**Status**: ⏸️ Stub concepts created, full import deferred

**File Location**: N/A (manual nodes in ontology)

---

## Scientific Papers (Cited)

### 1. Boillet et al. (2024) - Sports Performance Digital Twin

**Citation**: Boillet, M., Racinais, S., Maso, F., Coquart, J., & Bowen, M. (2024). "Digital Twin for Sports Performance: Margaria-Morton Energy Model Validation in Elite Cyclists"

**Contribution to Arnold**:
- Three-compartment energy model (Phosphagen, Glycolytic, Oxidative)
- Personalized parameterization from lab tests (VO2max, lactate thresholds)
- Validated predictive performance modeling

**How We Use It**:
- Created 3 EnergySystem reference nodes in ontology
- Athletes link via HAS_CAPACITY relationships with measured parameters
- Forms physiological foundation for workout intensity recommendations

**Status**: ✅ Integrated into proto-human schema (File 2: ontology_definitions.cypher)

---

### 2. Sun et al. (2023) - Musculoskeletal Digital Twin

**Citation**: Sun, W., et al. (2023). "Digital Twin in Healthcare: Recent Updates and Challenges" (Digital Health, Vol 9)

**Contribution to Arnold**:
- Review of digital twin applications in musculoskeletal medicine
- Identified limitations: static biomechanics, lack of real-time personalization
- Called for multi-modal data fusion

**How We Use It**:
- Validates Arnold's LLM-native data fusion approach
- Informs integration strategy for wearable data (Phase 6)
- Guides person-centric modeling (Person → Athlete → Observations)

**Status**: ✅ Conceptual framework adopted

---

### 3. Juliant et al. (2023) - Ontology-Based Exercise Recommender

**Citation**: Juliant, C. L., Baizal, Z. K. A., & Dharayani, R. (2023). "Ontology-Based Physical Exercise Recommender System for Underweight Using Ontology and Semantic Web Rule Language" (Journal of Information System Research, Vol 4, No 4, pp 1308-1315)

**Contribution to Arnold**:
- Demonstrates SWRL rules for BMI calculation and exercise recommendations
- Custom ontology approach (Person, Exercise, WorkoutPlan, MuscleGroup)
- 408 exercises validated by personal trainers (Precision: 0.8, Recall: 1.0, F-score: 0.888)
- Telegram chatbot interface for user interaction

**How We Use It**:
- SWRL rule patterns for BMI and energy system calculations (deferred to post-cleanup)
- Validation approach (human expert review of LLM recommendations)
- MuscleGroup aggregation pattern (hamstrings, forearms, etc.)

**Status**: ⏸️ Cited, SWRL implementation deferred to Phase 5

---

## Rejected/Deferred Standards

### ExerciseDB (RapidAPI)

**Why Rejected**: 
- AGPL-3.0 license (incompatible with Arnold's MIT license)
- Would force all derivatives to be AGPL (copyleft)
- API rate limits (600 req/month free tier)

**Alternative**: Free-Exercise-DB (CC0) + LLM-generated exercises (MIT)

---

### EXMO (Exercise Movement Ontology)

**Source**: https://bioportal.bioontology.org/ontologies/EXMO

**Why Deferred**:
- Last updated 2017 (stale, inactive project)
- Missing modern exercises (kettlebells, functional fitness)
- Limited coverage

**Alternative**: Build our own exercise variation ontology (Arnold's contribution)

---

### OPE (Ontology of Physical Exercise)

**Source**: https://bioportal.bioontology.org/ontologies/OPE

**Why Deferred**:
- Last updated 2016 (stale)
- More complete than EXMO but still outdated
- Missing unconventional training (tire flips, sandbag carries)

**Alternative**: Arnold's custom MovementPattern and ExerciseVariation ontology

---

### KHMO (Kinetic Human Movement Ontology)

**Why Deferred**:
- Cannot find active project or download source
- May be deprecated/renamed
- No viable implementation path

**Alternative**: Arnold's movement pattern classification (Hinge, Squat, Push, Pull, Carry)

---

## Deferred to Phase 6

### SNOMED CT (Medical Terminology)

**Purpose**: Comprehensive clinical terminology for medical conditions, procedures

**Why Deferred**: 
- Requires UMLS license (free for US, complex registration)
- RF2 format requires specialized parsers
- Overkill for Phase 1-5 (only need simple injury/constraint modeling)

**When to Import**: Phase 6 (medical integration, clinical studies)

**License**: Free for US use via UMLS affiliate license

---

### TRAK (Knee Rehabilitation Ontology)

**Purpose**: ACL rehabilitation protocol ontology

**Why Deferred**:
- Primarily conceptual framework, not structured protocol data
- Available as OWL ontology but lacks exercise progression data
- Better suited as terminology reference than workout generator

**When to Import**: Phase 6 (medical protocol formalization)

**Status**: Currently using generic TRAK protocol references in constraints

---

## Arnold's Custom Ontology Contributions

These are our innovations, not imported from external sources:

### 1. Exercise Variation Hierarchy

**Problem**: Free-Exercise-DB treats "Pull-Up" and "Neutral-Grip Pull-Up" as separate exercises

**Solution**: Create VARIATION_OF relationships
```cypher
(neutral_grip_pullup)-[:VARIATION_OF {
  variation_type: "grip",
  emphasis_change: "biceps"
}]->(pullup)
```

**Variation Types**:
- Grip (neutral, wide, narrow, pronated, supinated)
- Equipment (barbell, dumbbell, kettlebell, bodyweight)
- Load (weighted, assisted, bodyweight)
- Stance (conventional, sumo, wide, narrow)
- Tempo (explosive, slow eccentric, pause)
- Surface (rings, bar, rope, TRX)

**Status**: ✅ Schema defined, LLM mapping in progress

---

### 2. Movement Patterns

**Based on**: Functional movement science (not a formal ontology)

**Patterns**:
- Hinge (deadlifts, kettlebell swings)
- Squat (back squat, goblet squat, pistol squat)
- Push (bench press, overhead press, pushups)
- Pull (pullups, rows, face pulls)
- Carry (farmer's walks, suitcase carries)
- Lunge (split squats, walking lunges)
- Rotation (cable chops, Russian twists)

**Status**: ✅ 95.1% of exercises classified (Phase 4)

---

### 3. MuscleGroup Aggregations

**Problem**: FMA has "biceps femoris" but Free-Exercise-DB references "hamstrings"

**Solution**: Create MuscleGroup nodes that aggregate individual muscles
```cypher
(hamstrings:MuscleGroup)-[:INCLUDES]->(biceps_femoris:Muscle)
(hamstrings)-[:INCLUDES]->(semitendinosus:Muscle)
(hamstrings)-[:INCLUDES]->(semimembranosus:Muscle)
```

**Groups Needed**:
- Hamstrings (biceps femoris, semitendinosus, semimembranosus)
- Quadriceps (vastus lateralis, vastus medialis, rectus femoris, vastus intermedius)
- Forearms (flexor carpi, extensor carpi, brachioradialis)
- Abductors (gluteus medius, gluteus minimus, tensor fasciae latae)
- Adductors (adductor longus, adductor brevis, adductor magnus)

**Status**: ⏸️ Pending implementation (cleanup phase)

---

## File Organization

```
/arnold/
├── ontologies/
│   ├── anatomy/
│   │   ├── fma.owl (100MB, FMA ontology)
│   │   └── README.md
│   ├── exercises/
│   │   ├── free-exercise-db/ (git clone)
│   │   └── README.md
│   └── README.md (download instructions)
├── schemas/
│   ├── 01_constraints.cypher (DB constraints)
│   ├── 02_ontology_definitions.cypher (EnergySystem, EquipmentCategory, etc.)
│   └── 03_structure_docs.md (proto-human instantiation pattern)
├── docs/
│   ├── STANDARDS_AND_ONTOLOGIES.md (this file)
│   ├── PROTO_HUMAN_ARCHITECTURE.md
│   └── citations.bib (BibTeX references)
└── scripts/
    └── importers/
        ├── import_fma_targeted.py
        ├── import_exercises.py
        ├── map_custom_exercises_parallel.py
        └── CLAUDE_CODE_INSTRUCTIONS.md
```

---

## License Compatibility Matrix

| Source | License | Compatible with Arnold (MIT)? |
|--------|---------|-------------------------------|
| FMA | CC BY | ✅ Yes (with attribution) |
| Free-Exercise-DB | CC0 | ✅ Yes (public domain) |
| LOINC | Free w/ attribution | ✅ Yes |
| SNOMED CT | UMLS affiliate | ✅ Yes (US use) |
| ExerciseDB | AGPL-3.0 | ❌ No (copyleft) |
| EXMO | Unknown | ⚠️ Check before use |
| OPE | Unknown | ⚠️ Check before use |

---

## Future Ontology Candidates

**For Phase 6+ consideration:**

1. **IHTSDO SNOMED CT** - Full medical terminology (injury classification, comorbidities)
2. **HPO (Human Phenotype Ontology)** - Phenotypic abnormalities (useful for rare conditions)
3. **ChEBI** - Chemical entities (supplement recommendations)
4. **RXNORM** - Medication terminology (drug interactions with exercise)
5. **ICF (International Classification of Functioning)** - Disability and health framework

---

## Validation & Quality Control

**Personal Trainer Review** (from Juliant et al. 2023):
- Precision: 0.8 (80% of recommendations were appropriate)
- Recall: 1.0 (all appropriate exercises were recommended)
- F-score: 0.888

**Arnold's Validation Strategy**:
1. LLM-generated mappings tagged with confidence scores
2. Low-confidence mappings (<0.7) flagged for human review
3. `human_verified: false` property on all LLM inferences
4. Expert review queue for validation

---

## References

1. Boillet, M., et al. (2024). Digital Twin for Sports Performance. *Sports Medicine*.

2. Sun, W., et al. (2023). Digital Twin in Healthcare: Recent Updates and Challenges. *Digital Health*, 9.

3. Juliant, C. L., Baizal, Z. K. A., & Dharayani, R. (2023). Ontology-Based Physical Exercise Recommender System for Underweight Using Ontology and Semantic Web Rule Language. *Journal of Information System Research (JOSH)*, 4(4), 1308-1315. DOI: 10.47065/josh.v4i4.3823

4. Foundational Model of Anatomy Ontology. University of Washington. http://sig.biostr.washington.edu/projects/fm/

5. Free-Exercise-DB. https://github.com/yuhonas/free-exercise-db

6. LOINC - Logical Observation Identifiers Names and Codes. https://loinc.org/

---

**Last Updated**: December 26, 2024  
**Status**: Active development, Phase 4 cleanup in progress
