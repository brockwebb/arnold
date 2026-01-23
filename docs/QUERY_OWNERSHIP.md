# Query Ownership Reference

**Purpose:** Single source of truth per metric. MCPs should call the owner or use the same view, not reimplement.

**Last Updated:** 2026-01-22

## Training Metrics

| Metric | Owner MCP | Table/View | Notes |
|--------|-----------|------------|-------|
| Training load (28d volume) | analytics | `workout_summaries` | Both memory & analytics use same view |
| ACWR (volume-based) | analytics | `training_monotony_strain` | |
| ACWR (TRIMP-based) | analytics | `trimp_acwr` | Preferred for cardio intensity |
| Pattern gaps (10d) | analytics | `workout_summaries` (patterns jsonb) | |
| Weekly trends | analytics | `workout_summaries` | |
| Recent workouts (list) | memory | Neo4j `StrengthWorkout` | Reference nodes linked to Person |

## Biometric Metrics

| Metric | Owner MCP | Table/View | Notes |
|--------|-----------|------------|-------|
| HRV (daily/trend) | analytics | `daily_status`, `readiness_daily` | Memory queries same views for briefing |
| Sleep hours/quality | analytics | `daily_status` | **Sync gap:** Ultrahuman not syncing sleep metrics |
| Resting HR | analytics | `daily_status`, `biometric_readings` | |
| HRR trends | analytics | `biometric_readings`, `biometric_trends` | Heart Rate Recovery |

## Recovery/Readiness

| Metric | Owner MCP | Table/View | Notes |
|--------|-----------|------------|-------|
| Readiness snapshot | analytics | `daily_status`, `readiness_daily` | Memory uses analytics client for briefing |
| Red flags/data gaps | analytics | `biometric_readings` | Days since last reading |
| Annotations | analytics | `data_annotations` | Explain unusual data |

## Workout Logging

| Metric | Owner MCP | Table/View | Notes |
|--------|-----------|------------|-------|
| Workout CRUD | training | `workouts`, `blocks`, `sets` | Authoritative for logging |
| Exercise lookup | training | Neo4j Exercise nodes | Via knowledge graph |
| Plan completion | training | Neo4j + Postgres sync | Creates workout from plan |

## Context/Memory

| Metric | Owner MCP | Table/View | Notes |
|--------|-----------|------------|-------|
| Coaching observations | memory | Neo4j `Observation` nodes | Semantic search via embeddings |
| Goals | memory | Neo4j `Goal` nodes | |
| Training levels | memory | Neo4j `TrainingLevel` nodes | |
| Current block | memory | Neo4j `TrainingBlock` nodes | |
| Athlete profile | profile | Neo4j `Person` node | |

## Known Issues

1. **Sleep data not syncing:** `scripts/sync/ultrahuman_to_postgres.py` `METRIC_MAP` missing sleep metrics
2. **HRV sparse:** Ultrahuman not providing daily HRV consistently
3. **Sync automation:** Daily sync stopped running after Jan 14 - check launchd status

## Architecture Principles

1. **Postgres owns facts/measurements** (ADR-001)
2. **Neo4j owns relationships and context**
3. **Analytics MCP owns computed metrics** (ACWR, trends)
4. **Memory MCP aggregates for briefing** - calls analytics views, doesn't recompute
5. **Training MCP owns workout logging** - single source for workout CRUD

## Files Reference

| MCP | Client File | Main Server |
|-----|-------------|-------------|
| memory | `postgres_client.py`, `neo4j_client.py` | `server.py` |
| analytics | (inline in server.py) | `server.py` |
| training | `postgres_client.py`, `neo4j_client.py` | `server.py` |
| profile | `neo4j_client.py` | `server.py` |
