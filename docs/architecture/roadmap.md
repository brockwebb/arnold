# Development Roadmap

> **Last Updated**: January 8, 2026

---

## Completed (Dec 30-31, 2025)

1. ✅ Create Modality nodes (14 modalities)
2. ✅ Create PeriodizationModel library (Linear, Undulating, Block)
3. ✅ Create Goal nodes (4 goals with [:REQUIRES]->Modality)
4. ✅ Create TrainingLevel per modality (6 levels)
5. ✅ Update get_coach_briefing for new model
6. ✅ Delete Athlete nodes, Person direct to Workout
7. ✅ Delete TrainingPlan, Blocks direct to Person
8. ✅ Update MCP neo4j_client.py for new schema
9. ✅ **arnold-memory-mcp built and operational** - load_briefing working
10. ✅ Ring Dips goal + Shoulder Mobility protocol created
11. ✅ MobilityLimitation tracking for shoulder
12. ✅ **arnold-memory-mcp Phase 2: Semantic Search** - Neo4j vector index + OpenAI embeddings
13. ✅ **Training Metrics Specification** - TRAINING_METRICS.md with full citations

---

## Completed (Jan 4-5, 2026)

14. ✅ **ADR-001 Data Layer Separation** - Postgres (facts) / Neo4j (relationships)
15. ✅ **Migration 008: Endurance Sessions** - FIT imports to Postgres
16. ✅ **Migration 009: Journal System** - 17 MCP tools, dual-storage
17. ✅ **ADR-002: Strength Workout Migration** - 165 sessions, 2,482 sets migrated
    - Created `strength_sessions` and `strength_sets` tables
    - Created `postgres_client.py` for Postgres operations  
    - Refactored `server.py` for hybrid Neo4j/Postgres routing
    - 100% bidirectional links between Postgres and Neo4j refs

---

## Phase 1: Core Coaching Loop (Current)

| Task | Status | Notes |
|------|--------|-------|
| Weekly planning workflow | ⏳ | Plan Week 1 sessions |
| Live fire test | ⏳ | Plan → Execute → Reconcile end-to-end |
| Start logging observations | ⏳ | Build coaching memory over time |

---

## Phase 2: Analytics ("The Analyst")

| Task | Status | Notes |
|------|--------|-------|
| Data Lake Architecture | ✅ | Raw → Staging → Analytics design complete |
| Data catalog/registry | ✅ | `/data/catalog.json` with schema, fitness for use |
| Directory structure | ✅ | `/data/raw/`, `/data/staging/`, `/data/exports/` |
| Export script | ✅ | `/scripts/export_to_analytics.py` ready to run |
| Training Metrics Spec | ✅ | TRAINING_METRICS.md - ACWR, TSS, volume targets w/ citations |
| Export Neo4j to Parquet | ⏳ | Run script on local machine |
| Create DuckDB database | 📋 | `arnold_analytics.duckdb` |
| Tier 1 metrics | 📋 | ACWR, monotony, strain, pattern frequency |
| arnold-analytics-mcp | 📋 | Query interface, report generation |
| Core views | 📋 | daily_volume, weekly_summary, exercise_progression |
| Goal progress tracking | 📋 | Deadlift trajectory, distance to target |
| Hot reports | 📋 | On-demand pattern detection, anomalies |
| Visual artifacts | 📋 | React charts for exploration |

---

## Phase 3: Medical Support ("Doc")

| Task | Status | Notes |
|------|--------|-------|
| arnold-medical-mcp | 📋 | Health tracking, constraints |
| Symptom logging | 📋 | Pain, fatigue, illness tracking |
| Medication tracking | 📋 | What you're taking, interactions |
| Lab work import | 📋 | Blood panels, trends over time |
| Rehab protocol management | 📋 | Post-injury/surgery progression |
| Clearance logic | 📋 | "Safe to return to X" decisions |
| Research agent integration | 📋 | Latest literature on conditions |

---

## Phase 4: Data Integration

| Task | Status | Notes |
|------|--------|-------|
| Apple Health import | 📋 | Sleep, HRV, resting HR, steps |
| Garmin/Strava sync | 📋 | Run/ride data, GPS, training load |
| Body composition logging | 📋 | Weight, measurements, photos |
| Nutrition tracking | 📋 | Macros, meal timing |
| Subjective logging | 📋 | Energy, mood, stress, sleep quality |

---

## Phase 5: Digital Twin Foundation

| Task | Status | Notes |
|------|--------|-------|
| Unified Person schema | 📋 | All data sources → one graph |
| Cross-domain correlation | 📋 | Sleep ↔ performance, HRV ↔ readiness |
| Longitudinal views | 📋 | Years of data, trend analysis |
| Research agent ("Researcher") | 📋 | Literature search, protocol recommendations |
| Journaling/reflection ("Scribe") | 📋 | Thought capture, semantic search over notes |

---

## Phase 6: Delivery & Interface

| Task | Status | Notes |
|------|--------|-------|
| Email delivery | 📋 | Daily/weekly plans to inbox |
| Calendar integration | 📋 | Workouts as calendar events |
| Mobile-friendly output | 📋 | Phone-readable formats |
| Check-in system | 📋 | Structured conversations at cadence |

---

## Migration Notes

### From Old Schema

| Old | New | Action |
|-----|-----|--------|
| TrainingPlan | Deprecated | Extract goals, delete node |
| TrainingBlock | Block | Rename, re-link to Person |
| Goal (string on plan) | Goal (node) | Create nodes with [:REQUIRES]->Modality |
| Implicit training level | TrainingLevel | Create per person-modality |
| Obsidian workout files | Deprecated | Historical data imported, no longer maintained |

### Data Preservation

- Historical workouts (163) remain unchanged
- Exercise graph (4,242) remains unchanged
- MovementPattern (28) now links to Modality via [:EXPRESSED_BY]
- Obsidian markdown files no longer needed — Arnold is the system of record

---

## References

### Training Load & Workload Management

For complete training metrics citations, see **[TRAINING_METRICS.md](../TRAINING_METRICS.md)**.

Key sources:
- Gabbett, T.J. (2016). The training—injury prevention paradox. *BJSM*, 50(5), 273-280.
- Murray, N.B. et al. (2017). EWMA provides more sensitive injury indicator. *BJSM*, 51(9), 749-754.
- Schoenfeld, B.J. et al. (2017). Dose-response for training volume and hypertrophy. *J Sports Sci*, 35(11), 1073-1082.
- Foster, C. (1998). Monitoring training with overtraining syndrome. *MSSE*, 30(7), 1164-1168.
- Banister, E.W. (1975). Systems model of training for athletic performance. *Aust J Sports Med*, 7, 57-61.

### Periodization Science

- Issurin, V. (2010). New Horizons for the Methodology and Physiology of Training Periodization. Sports Medicine.
- Lorenz, D. (2015). Current Concepts in Periodization of Strength and Conditioning for the Sports Physical Therapist. IJSPT.
- Rønnestad, B. (2014). Block periodization in elite cyclists.
- Api, G. & Arruda, D. (2022). Comparison of Periodization Models: A Critical Review with Practical Applications.

### Fitness-Fatigue Model

- Banister, E.W. (1975). A systems model of training for athletic performance. Australian Journal of Sports Medicine.
- Clarke, D.C. & Skiba, P.F. (2013). Rationale and Resources for Teaching the Mathematical Modeling of Athletic Training and Performance.

### Concurrent Training

- Coffey, V.G. & Hawley, J.A. (2017). Concurrent training: From molecules to the finish line.
- Effects of Running-Specific Strength Training (2022). ATR periodization for recreational endurance athletes.
