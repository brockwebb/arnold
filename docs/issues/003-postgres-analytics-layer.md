# Issue 003: Analytics Layer — DuckDB → Postgres

> **Status**: Phase 4 Complete (Unified Sync Pipeline Operational)
> **Priority**: Maintenance mode
> **Created**: January 3, 2026
> **Last Updated**: January 4, 2026

---

## Problem Statement

Original problem (RESOLVED): DuckDB was file-based, requiring full rebuild on every change. Couldn't do incremental updates or pre-computed views.

---

## Implementation Status

### Phase 1: Postgres Setup ✅ COMPLETE (Jan 3)
- Database `arnold_analytics` created
- Core tables: `workout_summaries`, `biometric_readings`
- Materialized views: `training_load_daily`, `readiness_daily`
- `postgres-mcp` installed

### Phase 2: Data Load ✅ COMPLETE (Jan 4)
- Polar HR sessions: 61 sessions, 167K samples
- Apple Health biometrics: HRV, RHR, sleep data
- Ultrahuman CSV import: 8 months of ring data
- Workout ↔ Polar linkage established

### Phase 3: MCP Migration ✅ COMPLETE (Jan 4)
- All 5 arnold-analytics-mcp tools migrated to Postgres
- DuckDB dependency removed from active code path
- Flag overrides system implemented

### Phase 4: Unified Pipeline ✅ COMPLETE (Jan 4)
- Single orchestration script: `sync_pipeline.py`
- Ultrahuman API connector: `sync_ultrahuman.py`
- Sensor error detection: `clean_biometrics.py`
- Source deduplication: Ultrahuman API is canonical for ring data

---

## Current Architecture

```
┌──────────────────────────────────────────────────────┐
│                  DATA SOURCES                        │
├──────────────────────────────────────────────────────┤
│ Ultrahuman API │ Polar Export │ Apple Health        │
│    (daily)     │   (weekly)   │   (monthly)         │
└───────┬────────┴──────┬───────┴──────┬──────────────┘
        │               │              │
        └───────────────┼──────────────┘
                        │
            ┌───────────▼───────────┐
            │   sync_pipeline.py    │
            │   ┌───────────────┐   │
            │   │ 1. polar      │   │
            │   │ 2. ultrahuman │   │
            │   │ 3. apple      │   │
            │   │ 4. neo4j      │   │
            │   │ 5. clean      │   │
            │   │ 6. refresh    │   │
            │   └───────────────┘   │
            └───────────┬───────────┘
                        │
            ┌───────────▼───────────┐
            │  Postgres Analytics   │
            │  ├── biometric_readings│
            │  ├── workout_summaries │
            │  ├── polar_sessions    │
            │  ├── hr_samples        │
            │  ├── flag_overrides    │
            │  └── (materialized views)│
            └───────────────────────┘
```

---

## Data Quality Infrastructure

### Sensor Error Detection
Uses physiological bounds (not statistical outliers):
- HRV: 15-250 ms
- Resting HR: 35-100 bpm
- Temperature: 28-40°C

Preserves original value, stores cleaned value separately.

### Flag Overrides
Suppress expected warnings:
```sql
INSERT INTO flag_overrides (flag_type, context, reason, expires_at)
VALUES ('acwr', 'post_surgery_ramp', 'Expected during rebuild', '2026-03-01');
```

### Source Priority
1. Ultrahuman API (primary for ring data)
2. Polar (primary for workout HR)
3. Apple Health (secondary, medical/other data)

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/sync_pipeline.py` | Orchestrates all data sync |
| `scripts/sync_ultrahuman.py` | Ultrahuman API connector |
| `scripts/import_polar_sessions.py` | Polar export parser |
| `scripts/import_apple_health.py` | Apple Health parser |
| `scripts/import_ultrahuman_csv.py` | Ultrahuman CSV parser |
| `scripts/clean_biometrics.py` | Sensor error detection |
| `scripts/sync_neo4j_to_postgres.py` | Workout sync |
| `scripts/migrations/002_polar_sessions.sql` | Polar schema |

---

## Ongoing Maintenance

### Daily
```bash
python scripts/sync_pipeline.py  # Or set up cron
```

### Weekly
- Export new Polar data (manual)
- Review any new sensor errors

### Monthly
- Apple Health export for medical data
- Review flag_overrides expirations

---

## Resolved Questions

1. **Sync direction?** → Neo4j → Postgres (one-way). Writes hit Neo4j, sync copies.

2. **What goes where?** 
   - Neo4j: structure, relationships, plans, observations
   - Postgres: time-series, biometrics, summaries, analytics

3. **Source priority?** → Ultrahuman API > Apple Health for ring data.

4. **Outlier detection?** → Physiological bounds, not statistical. High variance is normal.

---

## Success Criteria ✅

1. ✅ **Fresh data**: Workout completed → queryable in < 5 minutes
2. ✅ **Fast queries**: Readiness check < 100ms
3. ✅ **No rebuilds**: Incremental updates via UPSERT
4. ✅ **Frame coverage**: All standard coaching queries have pre-built views
5. ✅ **Automated sync**: Single command for all sources
6. ✅ **Data quality**: Sensor errors flagged, originals preserved
