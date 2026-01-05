# Arnold Data Dictionary

> **Purpose**: Comprehensive reference for the Arnold analytics data lake. Describes all data sources, schemas, relationships, and fitness for use.
> **Last Updated**: January 4, 2026 (ADR-001: Data Layer Separation)
> **Location**: `/arnold/data/`

---

## Overview

Arnold's analytics layer uses a **hybrid architecture** per **ADR-001: Data Layer Separation**:

- **Postgres (Left Brain)**: Measurements, facts, time-series data
- **Neo4j (Right Brain)**: Relationships, semantics, knowledge graph

See `/docs/adr/001-data-layer-separation.md` for full rationale.

```
/data/
├── raw/                    # Native format, untouched
│   ├── apple_health_export/   # 217MB XML + clinical FHIR JSON
│   ├── ultrahuman/            # Manual CSV exports
│   ├── polar_exports/         # Polar Flow JSON exports
│   ├── neo4j_snapshots/       # Graph exports
│   └── old_race_info/         # Historical race data
├── staging/                # Parquet files (query-ready)
├── catalog.json            # Data registry
└── arnold_analytics.duckdb # Legacy analytics (being replaced)

Postgres: arnold_analytics   # Primary analytics database
├── workout_summaries        # Neo4j workout sync
├── polar_sessions           # HR monitor sessions
├── hr_samples               # Second-by-second HR
├── biometric_readings       # HRV, RHR, sleep
└── Views: daily_status, combined_training_load, trimp_acwr, readiness_daily
```

**Design Principle**: Raw stays raw. Staging is minimally transformed. Postgres holds computed frames.

---

## Data Sources Summary

| Source | Tables | Rows | Date Range | Status |
|--------|--------|------|------------|--------|
| FIT Files (Suunto/Garmin) | 2 | TBD | Jan 2026 → | ✅ NEW: Postgres-first |
| Apple Health | 8 | 20,227 | May 2025 → Dec 2025 | ✅ Staged + Postgres |
| Polar HR | 2 | 167,731 | May 2025 → Jan 2026 | ✅ Postgres |
| Clinical (FHIR) | 4 | 584 | Various | ✅ Staged |
| Ultrahuman | 1 | 234 | May 2025 → Jan 2026 | ✅ Staged |
| Neo4j Export | 4 | 6,886 | Apr 2024 → Jan 2026 | ✅ Staged + Postgres |
| Race History | 1 | 95 | Nov 2005 → Mar 2023 | ✅ Staged |

---

## Postgres Analytics Layer

The primary analytics database. Connect via `postgres-mcp` or `psql -d arnold_analytics`.

### workout_summaries
**Denormalized workout data synced from Neo4j**

| Column | Type | Description |
|--------|------|-------------|
| neo4j_id | VARCHAR(50) PK | Workout UUID from Neo4j |
| workout_date | DATE | Workout date |
| workout_name | VARCHAR | Named workouts (e.g., "The Fifty") |
| workout_type | VARCHAR | strength, conditioning, endurance, recovery |
| duration_minutes | INT | Workout duration |
| set_count | INT | Total sets |
| total_volume_lbs | DECIMAL | Sum of load × reps |
| patterns | JSONB | Movement patterns used |
| exercises | JSONB | Exercises with set details |
| tss | DECIMAL | Training stress score |
| source | VARCHAR | planned, adhoc, imported |
| polar_session_id | INT FK | Link to polar_sessions |
| polar_match_confidence | DECIMAL | Match confidence (0.6-1.0) |
| polar_match_method | VARCHAR | date_single, date_duration_best |

- **Rows**: 165
- **Linked to Polar**: 51
- **Sync**: `python scripts/sync_neo4j_to_postgres.py`

---

### polar_sessions
**HR monitor training sessions from Polar exports**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment ID |
| polar_session_id | VARCHAR UNIQUE | Polar's session UUID |
| start_time | TIMESTAMPTZ | Session start |
| stop_time | TIMESTAMPTZ | Session end |
| duration_seconds | INT | Total duration |
| sport_type | VARCHAR | CROSS_FIT, STRENGTH_TRAINING, RUNNING, etc. |
| avg_hr | INT | Average heart rate |
| max_hr | INT | Maximum heart rate |
| min_hr | INT | Minimum heart rate |
| calories | INT | Calories burned |
| zone_1-5_seconds | INT | Time in each HR zone |
| zone_1-5_lower/higher_limit | INT | Zone boundaries |
| resting_hr | INT | Physical snapshot: resting HR |
| max_hr_setting | INT | Physical snapshot: max HR |
| vo2max | DECIMAL | Physical snapshot: VO2max |
| ftp | INT | Functional threshold power |
| weight_kg | DECIMAL | Body weight at session |
| feeling | DECIMAL | Post-workout RPE (0-1) |
| timezone_offset | INT | UTC offset in seconds |
| note | TEXT | Session notes |

- **Rows**: 61
- **Date Range**: May 21, 2025 → Jan 3, 2026
- **Sport Distribution**: CrossFit (36), Strength (14), Running (6), Other (5)
- **Import**: `python scripts/import_polar_sessions.py <export-folder>`

---

### hr_samples
**Second-by-second heart rate data**

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL PK | Auto-increment |
| session_id | INT FK | Reference to polar_sessions |
| sample_time | TIMESTAMPTZ | Exact timestamp |
| hr_value | INT | Heart rate (bpm) |

- **Rows**: 167,670
- **Use Cases**: TRIMP calculation, cardiac drift detection, recovery curves
- **Note**: Some samples may be missing during HR dropouts (sensor lost contact)

---

### biometric_readings
**Daily biometric metrics from Apple Health / Ultrahuman**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| reading_date | DATE | Measurement date |
| metric_type | VARCHAR | hrv_morning, resting_hr, sleep_total_min, sleep_deep_min, sleep_rem_min |
| value | DECIMAL | Metric value |
| source | VARCHAR | Ultrahuman, Apple Health |
| imported_at | TIMESTAMP | Import timestamp |

- **Unique Constraint**: (reading_date, metric_type, source)
- **Rows by Metric**:
  - hrv_morning: 97 (May-Dec 2025)
  - resting_hr: 158 (May-Dec 2025)
  - sleep_total_min: 188 (May-Dec 2025)
  - sleep_deep_min: 181
  - sleep_rem_min: 176
- **Import**: `python scripts/import_apple_health.py`

---

### endurance_sessions
**Source of truth for FIT file imports (Suunto, Garmin, Wahoo) per ADR-001**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| session_date | DATE | Workout date |
| session_time | TIME | Start time of day |
| name | VARCHAR | "Long Run - Odenton Loop" |
| sport | VARCHAR | 'running', 'cycling', 'swimming' |
| source | VARCHAR | 'suunto', 'garmin', 'polar', 'wahoo' |
| source_file | VARCHAR | Original filename |
| distance_miles | DECIMAL | Total distance |
| duration_seconds | INT | Total time |
| duration_minutes | DECIMAL | Generated column |
| avg_pace | VARCHAR | "11:13/mi" |
| avg_hr / max_hr / min_hr | INT | Heart rate metrics |
| elevation_gain_m | INT | Elevation gain |
| tss | DECIMAL | Training Stress Score |
| training_effect | DECIMAL | Aerobic training effect |
| recovery_time_hours | DECIMAL | Suggested recovery |
| rpe | INT | Subjective effort (1-10) |
| notes | TEXT | Rich notes from athlete |
| tags | TEXT[] | ['long_run', 'post_surgery'] |
| neo4j_id | VARCHAR | Cross-ref to Neo4j EnduranceWorkout |

- **Import**: `python scripts/import_fit_workouts.py`
- **Architecture**: Postgres = source of truth, Neo4j = lightweight reference
- **Migration**: `scripts/migrations/008_endurance_sessions.sql`

---

### endurance_laps
**Per-lap splits from endurance sessions**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| session_id | INT FK | Reference to endurance_sessions |
| lap_number | INT | Lap sequence |
| distance_miles | DECIMAL | Lap distance |
| duration_seconds | INT | Lap time |
| pace | VARCHAR | "10:32/mi" |
| avg_hr / max_hr | INT | Lap HR |

- **Use Cases**: Split analysis, pacing strategy, HR drift

---

### Postgres Views

| View | Type | Description |
|------|------|-------------|
| `polar_session_metrics` | View | Session-level TRIMP, Edwards TRIMP, Intensity Factor |
| `hr_training_load_daily` | View | Daily HR aggregates, zone distribution, polarization |
| `trimp_acwr` | View | TRIMP-based Acute:Chronic Workload Ratio |
| `combined_training_load` | View | Unified volume + HR metrics per workout |
| `readiness_daily` | Materialized | Daily HRV, RHR, sleep metrics |
| `daily_status` | View | Comprehensive daily view (training + readiness) |

**Key Queries:**
```sql
-- Full daily status
SELECT * FROM daily_status WHERE date = '2026-01-03';

-- Training load with HR metrics
SELECT * FROM combined_training_load WHERE data_coverage = 'linked';

-- TRIMP-based ACWR
SELECT * FROM trimp_acwr WHERE daily_trimp > 0 ORDER BY session_date DESC;

-- Refresh readiness after biometric import
REFRESH MATERIALIZED VIEW readiness_daily;
```

---

## Apple Health Sources (Parquet Staging)

### apple_health_hr
**Hourly heart rate aggregates from wearables**

| Column | Type | Description |
|--------|------|-------------|
| hour | datetime | Hour bucket (timezone-aware) |
| source_name | string | Device/app (Ultrahuman, Polar Flow, Bluetooth Device) |
| hr_avg | float | Average HR for hour |
| hr_min | float | Minimum HR |
| hr_max | float | Maximum HR |
| hr_count | int | Number of samples in hour |
| date | date | Date for joining |

- **Grain**: Hour × Source
- **Rows**: 3,892
- **Date Range**: 2025-05-15 → 2025-12-31

---

### apple_health_hrv
**Heart rate variability measurements (SDNN)**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Measurement date |
| measured_at | datetime | Exact timestamp |
| hrv_ms | float | SDNN in milliseconds |
| source_name | string | Device (usually Ultrahuman) |

- **Rows**: 9,912
- **Date Range**: 2025-05-15 → 2025-12-06
- **Statistics**: min=1ms, max=255ms, mean=76.8ms

---

### apple_health_sleep
**Sleep session segments by stage**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Wake date (attribution) |
| duration_minutes | float | Segment duration |
| sleep_stage | string | inbed, asleep, asleepcore, asleepdeep, asleeprem, awake |

- **Rows**: 4,281
- **Note**: Multiple segments per night. Aggregate by date for totals.

---

### apple_health_resting_hr
**Resting heart rate measurements**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Date |
| resting_hr | float | Resting HR (bpm) |

- **Rows**: 168

---

## Clinical Sources (FHIR)

### clinical_labs
**Lab test results from MyChart/Epic**

- **Rows**: 494
- **Unique Tests**: 179
- **Tests with LOINC**: 394 (80%)
- **Fitness for Use**: HIGH - standard FHIR format, LOINC coded

### clinical_conditions, clinical_medications, clinical_immunizations
Standard FHIR resources. See staging parquet files for schema details.

---

## Neo4j Export Sources (Parquet Staging)

### workouts
- **Rows**: 163
- **Date Range**: 2024-04-04 → 2025-12-30

### sets
- **Rows**: 2,453

### exercises
- **Rows**: 4,242

### movement_patterns
- **Rows**: 30

---

## Race History

### race_history
- **Rows**: 95
- **Date Range**: 2005-11-24 → 2023-03-11
- **Running Races**: 90
- **Triathlon Races**: 5

---

## Known Data Quality Issues

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Sparse weight data (3 rows) | Can't track body composition | Add regular weigh-ins |
| Sparse BP data (2 rows) | No BP trend analysis | Add regular measurements |
| HRV ends Dec 6, 2025 | Recent HRV missing | Re-export Apple Health |
| Some labs missing LOINC | 20% can't be standardized | Manual mapping if needed |

---

## Refresh Patterns

| Source | Target | Script | Frequency |
|--------|--------|--------|-----------|
| FIT files | Postgres + Neo4j ref | `python scripts/import_fit_workouts.py` | After runs/rides |
| Neo4j workouts | Postgres | `python scripts/sync_neo4j_to_postgres.py` | After workouts |
| Polar HR | Postgres | `python scripts/import_polar_sessions.py <folder>` | Weekly |
| Apple Health biometrics | Postgres | `python scripts/import_apple_health.py` | Weekly/Monthly |
| Apple Health | Parquet staging | `python scripts/export_to_analytics.py` | Weekly/Monthly |
| Ultrahuman | Parquet staging | `python scripts/stage_ultrahuman.py` | Weekly |
| Materialized views | Postgres | `REFRESH MATERIALIZED VIEW readiness_daily` | After biometric import |

---

## File Locations

```
/arnold/
├── data/
│   ├── raw/
│   │   ├── apple_health_export/
│   │   │   ├── export.xml              # 217MB main health data
│   │   │   └── clinical-records/       # ~900 FHIR JSON files
│   │   ├── ultrahuman/
│   │   │   └── manual_export_*.csv
│   │   ├── polar_exports/              # Polar Flow JSON exports
│   │   │   └── 20260103--polar-user-data-export_*/
│   │   └── old_race_info/
│   ├── staging/
│   │   ├── apple_health_*.parquet
│   │   ├── clinical_*.parquet
│   │   ├── ultrahuman_daily.parquet
│   │   ├── workouts.parquet
│   │   ├── sets.parquet
│   │   └── exercises.parquet
│   └── arnold_analytics.duckdb         # Legacy (being replaced)
├── scripts/
│   ├── sync_neo4j_to_postgres.py       # Neo4j → Postgres sync
│   ├── import_polar_sessions.py        # Polar HR import
│   ├── import_apple_health.py          # Apple Health → Postgres biometrics
│   ├── export_to_analytics.py          # Neo4j → Parquet staging
│   └── migrations/
│       ├── 001_initial_schema.sql      # Postgres base schema
│       └── 002_polar_sessions.sql      # Polar tables + views
```

---

## Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `import_fit_workouts.py` | Import FIT files (Postgres-first) | `python scripts/import_fit_workouts.py` |
| `sync_neo4j_to_postgres.py` | Sync workouts from Neo4j to Postgres | `python scripts/sync_neo4j_to_postgres.py` |
| `import_polar_sessions.py` | Import Polar HR data to Postgres | `python scripts/import_polar_sessions.py data/raw/<polar-folder>` |
| `import_apple_health.py` | Import biometrics (HRV, sleep, RHR) to Postgres | `python scripts/import_apple_health.py` |
| `export_to_analytics.py` | Export Neo4j to Parquet staging | `python scripts/export_to_analytics.py` |
| `stage_ultrahuman.py` | Stage Ultrahuman CSV to Parquet | `python scripts/stage_ultrahuman.py` |
| `create_analytics_db.py` | Build DuckDB from staging (legacy) | `python scripts/create_analytics_db.py` |

---

## data_annotations
**Context and explanations for data gaps, outliers, and anomalies**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| annotation_date | DATE | Start date of annotation |
| date_range_end | DATE | End date (NULL = ongoing or single day) |
| target_type | VARCHAR(50) | 'biometric', 'workout', 'training', 'general' |
| target_metric | VARCHAR(50) | 'hrv', 'sleep', 'rhr', 'volume', 'all', etc. |
| target_id | VARCHAR(100) | Optional: specific record ID (e.g., 'Workout:uuid') |
| reason_code | VARCHAR(50) | Categorization (see below) |
| explanation | TEXT | Human-readable context |
| tags | TEXT[] | For retrieval: ['ring', 'sleep', 'gap'] |
| created_at | TIMESTAMP | When annotation was created |
| created_by | VARCHAR(50) | 'user', 'neo4j', 'postgres_only' |
| is_active | BOOLEAN | Soft delete flag |

**Reason Codes:**
- `device_issue` - Sensor malfunction, app not syncing, battery dead
- `travel` - Away from home, different timezone, equipment unavailable
- `illness` - Sick, recovery from illness
- `surgery` - Medical procedure, post-op recovery
- `injury` - Active injury affecting training
- `event` - Race, competition, special occasion
- `expected` - Normal/expected variation (e.g., HRV drop after hard workout)
- `data_quality` - Known data issue, source confusion, cleanup note
- `deload` - Planned recovery week
- `life` - Work stress, family, schedule disruption

**Architecture:**
- **Neo4j = Source of Truth** - Rich relationships to Workout, Injury, PlannedWorkout nodes
- **Postgres = Analytics Layer** - Time-series queries, materialized views
- **Sync**: `python scripts/sync_annotations.py` (runs in pipeline)

**Helper Functions:**
```sql
-- Get annotations for a specific date
SELECT * FROM annotations_for_date('2026-01-04');

-- Get active issues (ongoing or current)
SELECT * FROM active_data_issues;
```

**Current Annotations:**
| Date | Metric | Reason | Status |
|------|--------|--------|--------|
| Jan 3-5, 2026 | hrv | expected | bounded (The Fifty workout) |
| Dec 7, 2025 → | sleep | device_issue | **ongoing** (ring app closed) |
| Nov 8-21, 2025 | all | surgery | bounded (knee surgery) |
| May 14 - Dec 6, 2025 | hrv | data_quality | bounded (source cleanup) |

---

## Training Metrics

For evidence-based training metrics (ACWR, TSS, volume targets, etc.), see:

**[TRAINING_METRICS.md](./TRAINING_METRICS.md)** — Complete specification with:
- Tier 1: Metrics calculable from logged workouts (Volume Load, ACWR, Monotony, Strain)
- Tier 2: Metrics requiring biometric data (hrTSS, Readiness, ATL/CTL/TSB)
- Tier 3: Metrics requiring external platform export (Suunto TSS, rTSS)
- Full citations for all formulas and thresholds

---

## Next Steps

1. ~~**Create DuckDB database**~~ ✅ Complete
2. ~~**Build unified views**~~ ✅ Complete
3. ~~**Implement arnold-analytics-mcp**~~ ✅ Complete (DuckDB backend)
4. ~~**Polar HR integration**~~ ✅ Complete - 61 sessions, 167K samples
5. ~~**Apple Health biometrics**~~ ✅ Complete - HRV, RHR, sleep in Postgres
6. **Phase 3: Migrate arnold-analytics-mcp to Postgres** ← Next
7. **Pattern detection** - HRV ↔ performance correlations
8. **Tier 2 metrics** - Full readiness scoring
