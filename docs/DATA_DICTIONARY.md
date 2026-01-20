# Arnold Data Dictionary

> **Purpose**: Comprehensive reference for the Arnold analytics data lake. Describes all data sources, schemas, relationships, and fitness for use.
> **Last Updated**: January 19, 2026 (Migration 023: r2_15_45, r2_30_90 gate fix)
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
| **Strength Workouts** | **2** | **2,647** | **Apr 2024 → Jan 2026** | **✅ NEW: ADR-002** |
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

### strength_sessions (ADR-002)
**Executed strength training sessions - PRIMARY SOURCE OF TRUTH**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment ID |
| session_date | DATE NOT NULL | Workout date |
| session_time | TIME | Start time if known |
| name | VARCHAR(255) | Workout name (e.g., "The Fifty") |
| block_id | VARCHAR(100) | FK to Neo4j Block (training phase) |
| plan_id | VARCHAR(100) | FK to Neo4j PlannedWorkout (if from plan) |
| duration_minutes | INT | Session duration |
| total_volume_lbs | DECIMAL | Sum of load × reps |
| total_sets | INT | Number of sets |
| total_reps | INT | Total repetitions |
| session_rpe | DECIMAL | Overall session RPE (1-10) |
| avg_rpe | DECIMAL | Average RPE across sets |
| max_rpe | DECIMAL | Highest RPE in session |
| notes | TEXT | Session notes |
| tags | JSONB | Tags for categorization |
| status | VARCHAR(20) | completed, partial, skipped |
| source | VARCHAR(50) | migrated, logged, planned |
| neo4j_id | VARCHAR(100) | FK to Neo4j StrengthWorkout ref |

- **Rows**: 165
- **Date Range**: April 2024 → January 2026
- **Migrated**: January 5, 2026 (ADR-002)

---

### strength_sets (ADR-002)
**Individual sets within strength sessions - FULL DETAIL**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment ID |
| session_id | INT FK | References strength_sessions.id |
| set_order | INT | Order within session (1-indexed) |
| block_name | VARCHAR(100) | Workout block (Warm-Up, Main, Finisher) |
| block_type | VARCHAR(50) | warmup, main, accessory, finisher, cooldown |
| exercise_id | VARCHAR(100) | Exercise ID (EXERCISE:, CANONICAL:, CUSTOM:) |
| exercise_name | VARCHAR(255) | Human-readable name |
| reps | INT | Actual reps performed |
| load_lbs | DECIMAL | Load in pounds |
| rpe | DECIMAL | Rate of Perceived Exertion (1-10) |
| volume_lbs | DECIMAL | Computed: reps × load |
| prescribed_reps | INT | Planned reps (if from plan) |
| prescribed_load_lbs | DECIMAL | Planned load (if from plan) |
| prescribed_rpe | DECIMAL | Target RPE (if from plan) |
| is_deviation | BOOLEAN | Did this deviate from plan? |
| deviation_reason | VARCHAR(50) | fatigue, pain, equipment, time, technique |
| set_type | VARCHAR(20) | working, warmup, backoff, amrap, drop, cluster, rest_pause, timed, isometric |
| notes | TEXT | Set-specific notes |

- **Rows**: 2,482
- **Migrated**: January 5, 2026 (ADR-002)

**Helper Functions:**
```sql
-- Exercise progression history
SELECT * FROM exercise_history('EXERCISE:Barbell_Deadlift', 365);

-- Personal records
SELECT * FROM exercise_pr('EXERCISE:Barbell_Deadlift');

-- Weekly volume aggregates
SELECT * FROM weekly_strength_volume;
```

---

### workout_summaries (DEPRECATED)
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
| hrr_qc_status | VARCHAR(20) | QC status: pending, reviewed, needs_reprocess |
| hrr_qc_reviewed_at | TIMESTAMPTZ | When QC review was completed |

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

## peak_adjustments
**Manual overrides for HRR peak detection when auto-detection fails**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| polar_session_id | INT FK | Reference to polar_sessions |
| interval_order | SMALLINT | Which detected peak (1-indexed) |
| shift_seconds | SMALLINT | Seconds to shift peak (positive = later) |
| reason | TEXT | Documentation of why adjustment needed |
| created_at | TIMESTAMPTZ | When adjustment was created |
| applied_at | TIMESTAMPTZ | When extraction used this adjustment |

- **Unique Constraint**: (polar_session_id, interval_order)
- **Use Case**: False peak detection where scipy anchors on plateau instead of true max HR
- **Workflow**: See [hrr_quality_gates.md](./hrr_quality_gates.md#manual-peak-adjustments)

**Example:**
```sql
-- Add adjustment for session 51, peak 3: shift 54 seconds later
INSERT INTO peak_adjustments (polar_session_id, interval_order, shift_seconds, reason)
VALUES (51, 3, 54, 'False peak - real recovery starts ~54s later');

-- Reprocess: python scripts/hrr_feature_extraction.py --session-id 51
```

**Quality Flag**: Intervals with manual adjustments get `MANUAL_ADJUSTED` in `quality_flags`.

---

## hrr_quality_overrides
**Human overrides for automated quality decisions - survives re-extraction**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| polar_session_id | INT FK | Reference to polar_sessions (PK with interval_order) |
| endurance_session_id | INT FK | Reference to endurance_sessions (alternative PK) |
| interval_order | SMALLINT | Which interval (1-indexed, PK) |
| override_action | VARCHAR(20) | `force_pass` or `force_reject` |
| original_status | VARCHAR(20) | Status before override (for audit) |
| original_reason | TEXT | Rejection reason before override |
| reason | TEXT | Human explanation for override |
| created_at | TIMESTAMPTZ | When override was created |
| applied_at | TIMESTAMPTZ | When extraction used this override |

- **Unique Constraint**: (polar_session_id, interval_order) OR (endurance_session_id, interval_order)
- **Stable Keys**: Uses session_id + interval_order, not interval PK (survives re-extraction)
- **Workflow**: See [hrr_quality_gates.md](./hrr_quality_gates.md#quality-overrides)

**Override Actions:**
- `force_pass`: Override rejection → pass (clears auto_reject_reason, sets review_priority=3)
- `force_reject`: Override pass/flagged → rejected (sets auto_reject_reason='human_override: {reason}')

**Example:**
```sql
-- Force-pass an interval with valid recovery despite segment R² flag
INSERT INTO hrr_quality_overrides 
    (polar_session_id, interval_order, override_action, original_status, original_reason, reason)
VALUES 
    (70, 1, 'force_pass', 'rejected', 'r2_30_60_below_0.75', 
     'Human reviewed: mid-peak plateau in middle of steady drop. Valid recovery curve.');

-- Reprocess: python scripts/hrr_feature_extraction.py --session-id 70
```

**Quality Flag**: Intervals with overrides get `HUMAN_OVERRIDE` in `quality_flags`.

**Architecture Note**: Unlike `hrr_interval_reviews` (which records reviews but doesn't change data), quality overrides actively modify extraction results. The stable key design ensures overrides persist across re-extraction runs.

---

## hr_recovery_intervals
**Heart rate recovery intervals extracted from HR time-series - PRIMARY HRR SOURCE**

Heart rate recovery (HRR) intervals are extracted from Polar/endurance sessions and contain both raw measurements and computed quality metrics. Each interval represents a recovery period following a peak heart rate event.

### Core Identification

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| polar_session_id | INT FK | Reference to polar_sessions (NULL for endurance) |
| endurance_session_id | INT FK | Reference to endurance_sessions (NULL for Polar) |
| interval_order | SMALLINT | Interval sequence within session (1-indexed) |
| peak_label | TEXT | Human-readable label (e.g., "S71:p13") |
| start_time | TIMESTAMPTZ NOT NULL | Interval start timestamp |
| end_time | TIMESTAMPTZ NOT NULL | Interval end timestamp |
| duration_seconds | INT NOT NULL | Recovery window length |

### Heart Rate Measurements

| Column | Type | Description |
|--------|------|-------------|
| hr_peak | SMALLINT NOT NULL | Peak heart rate at interval start (bpm) |
| hr_30s | SMALLINT | Heart rate at 30 seconds post-peak |
| hr_60s | SMALLINT | Heart rate at 60 seconds post-peak |
| hr_90s | SMALLINT | Heart rate at 90 seconds post-peak |
| hr_120s | SMALLINT | Heart rate at 120 seconds post-peak |
| hr_180s | SMALLINT | Heart rate at 180 seconds post-peak |
| hr_240s | SMALLINT | Heart rate at 240 seconds post-peak |
| hr_300s | SMALLINT | Heart rate at 300 seconds post-peak |
| hr_nadir | SMALLINT | Lowest HR reached during recovery |
| rhr_baseline | SMALLINT | Resting HR used as baseline |
| local_baseline_hr | SMALLINT | Local baseline HR (session context) |

### HRR Absolute Drops (bpm)

| Column | Type | Description |
|--------|------|-------------|
| hrr30_abs | SMALLINT | HRR at 30s: peak - hr_30s |
| hrr60_abs | SMALLINT | HRR at 60s: peak - hr_60s |
| hrr90_abs | SMALLINT | HRR at 90s: peak - hr_90s |
| hrr120_abs | SMALLINT | HRR at 120s: peak - hr_120s |
| hrr180_abs | SMALLINT | HRR at 180s: peak - hr_180s |
| hrr240_abs | SMALLINT | HRR at 240s: peak - hr_240s |
| hrr300_abs | SMALLINT | HRR at 300s: peak - hr_300s |
| total_drop | SMALLINT | Peak - nadir (max observed drop) |
| peak_minus_local | SMALLINT | Peak - local_baseline_hr |
| hr_reserve | SMALLINT | Peak - RHR baseline |
| recovery_ratio | NUMERIC(5,4) | Total drop / HR reserve |

### Exponential Fit Parameters

| Column | Type | Description |
|--------|------|-------------|
| tau_seconds | NUMERIC(6,2) | Time constant (seconds to 63% recovery) |
| tau_fit_r2 | NUMERIC(5,4) | R² of exponential fit |
| tau_censored | BOOLEAN | True if tau was capped at max (300s) |
| fit_amplitude | DOUBLE | Fitted amplitude parameter |
| fit_asymptote | DOUBLE | Fitted asymptote (recovery target) |
| decline_slope_30s | NUMERIC(6,4) | Slope of 0-30s decline (bpm/sec) |
| decline_slope_60s | NUMERIC(6,4) | Slope of 0-60s decline (bpm/sec) |
| early_slope | NUMERIC | Early phase slope |

### Segment R² Values (Quality Metrics)

Segment R² values measure how well HR decay fits an exponential model within specific time windows. Used for quality gating and validity assessment.

**Quality Gate Logic (as of Migration 023):**
- `r2_0_30 < 0.5` → Hard reject (double-peak detection)
- `r2_30_60 < 0.75` → Hard reject (validates HRR60)
- `r2_30_90 < 0.75` → **Diagnostic only** (validates HRR120, does NOT reject interval)
- `best_r2 < 0.75` → Hard reject (no valid windows)

| Column | Type | Description |
|--------|------|-------------|
| r2_0_30 | DOUBLE | R² for 0-30s window. <0.5 triggers double_peak rejection |
| r2_15_45 | REAL | R² for 15-45s centered window. Diagnostic for edge artifacts |
| r2_30_60 | DOUBLE | R² for 30-60s window. <0.75 triggers hard reject |
| r2_0_60 | REAL | R² for 0-60s window. Validates HRR60 measurement |
| r2_0_90 | REAL | R² for 0-90s window |
| r2_30_90 | REAL | R² for 30-90s window. Diagnostic for HRR120 validity (NOT a reject gate) |
| r2_0_120 | REAL | R² for 0-120s window |
| r2_0_180 | REAL | R² for 0-180s window |
| r2_0_240 | REAL | R² for 0-240s window |
| r2_0_300 | REAL | R² for 0-300s window |
| r2_180 | NUMERIC | Legacy R² at 180s |
| r2_240 | NUMERIC | Legacy R² at 240s |
| r2_300 | NUMERIC | Legacy R² at 300s |
| r2_delta | DOUBLE | R² 30-60 - R² 0-30 (plateau indicator) |
| slope_90_120 | DOUBLE | Slope in 90-120s window (bpm/sec) |
| slope_90_120_r2 | DOUBLE | R² of 90-120s slope fit |

### Extrapolation Quality

| Column | Type | Description |
|--------|------|-------------|
| extrap_residual_60 | DOUBLE | Extrapolation residual at 60s |
| extrap_accumulated_error | DOUBLE | Cumulative extrapolation error |
| extrap_late_trend | DOUBLE | Late-phase trend indicator |

### Detection Metadata

| Column | Type | Description |
|--------|------|-------------|
| peak_detected | BOOLEAN | True if peak found by scipy |
| valley_detected | BOOLEAN | True if valley-based detection |
| peak_count | INT | Number of candidate peaks |
| valley_count | INT | Number of candidate valleys |
| peak_sample_idx | INT | Sample index of peak |
| onset_delay_sec | SMALLINT | Delay before recovery starts |
| onset_confidence | VARCHAR | 'high', 'medium', 'low' |
| nadir_time_sec | INT | Time to reach nadir (seconds) |
| time_to_50pct_sec | SMALLINT | Time to 50% recovery |

### Session Context

| Column | Type | Description |
|--------|------|-------------|
| session_type | VARCHAR(20) | Workout type |
| session_elapsed_min | SMALLINT | Minutes into session |
| sustained_effort_sec | SMALLINT | Duration of preceding effort |
| effort_avg_hr | SMALLINT | Average HR during effort |
| peak_pct_max | NUMERIC(5,4) | Peak as % of max HR |
| stratum | VARCHAR | Intensity stratum |
| preceding_activity | VARCHAR | Activity before peak |
| protocol_type | VARCHAR | Recovery protocol |
| recovery_posture | VARCHAR | Posture during recovery |

### Sample Quality

| Column | Type | Description |
|--------|------|-------------|
| sample_count | INT | Actual HR samples in interval |
| expected_sample_count | INT | Expected samples (1/sec) |
| sample_completeness | NUMERIC | sample_count / expected |
| is_clean | BOOLEAN | No quality issues (default: true) |
| is_low_signal | BOOLEAN | Low signal quality (default: false) |
| is_deliberate | BOOLEAN | Deliberate recovery protocol |

### Quality Assessment

| Column | Type | Description |
|--------|------|-------------|
| quality_status | TEXT | 'pass', 'flagged', 'rejected', 'pending' |
| quality_flags | TEXT[] | Array of flag codes (e.g., 'MANUAL_ADJUSTED', 'HUMAN_OVERRIDE') |
| quality_score | DOUBLE | Composite quality score |
| auto_reject_reason | TEXT | Reason for auto-rejection |
| confidence | NUMERIC | Overall confidence score |
| weighted_hrr60 | NUMERIC | Confidence-weighted HRR60 |
| actionable | BOOLEAN | Usable for trend analysis (default: true) |
| needs_review | BOOLEAN | Flagged for human review (default: true) |
| review_priority | INT | 1=urgent, 2=normal, 3=low (default: 3) |

### Human Review

| Column | Type | Description |
|--------|------|-------------|
| human_verified | BOOLEAN | Has been manually reviewed (default: false) |
| verified_at | TIMESTAMPTZ | When verified |
| verified_status | TEXT | Human's status decision |
| verification_notes | TEXT | Reviewer notes |
| excluded | BOOLEAN | Excluded from analysis (default: false) |
| exclusion_reason | TEXT | Why excluded |
| notes | TEXT | General notes |

### Derived Metrics

| Column | Type | Description |
|--------|------|-------------|
| auc_60s | NUMERIC(10,2) | Area under curve (first 60s) |
| predicted_rpe | NUMERIC | ML-predicted RPE |
| anomaly_score | NUMERIC | Anomaly detection score |
| recovery_cluster | VARCHAR | Cluster assignment |
| created_at | TIMESTAMPTZ | Record creation (default: now()) |

**Table Statistics:**
- **Rows**: ~1,500+ (grows with each session)
- **Sessions**: 61+ Polar sessions, endurance sessions
- **Quality Distribution**: ~60% pass, ~40% rejected
- **Migration**: 021_hrr_extended_columns_fix.sql added hr_180s, hr_240s, hr_300s, hrr180-300 columns

**Key Queries:**
```sql
-- Get HRR60 trends for passed intervals
SELECT start_time::date, AVG(hrr60_abs) as avg_hrr60
FROM hr_recovery_intervals
WHERE quality_status = 'pass' AND hrr60_abs IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- Find long recovery intervals (5+ min)
SELECT polar_session_id, interval_order, duration_seconds,
       hrr60_abs, hrr120_abs, hrr180_abs, hrr240_abs, hrr300_abs
FROM hr_recovery_intervals
WHERE duration_seconds >= 300 AND quality_status = 'pass';

-- Session summary
SELECT polar_session_id,
       COUNT(*) as intervals,
       COUNT(*) FILTER (WHERE quality_status = 'pass') as passed,
       AVG(hrr60_abs) FILTER (WHERE quality_status = 'pass') as avg_hrr60
FROM hr_recovery_intervals
GROUP BY 1;
```

**Extraction Script**: `python scripts/hrr_feature_extraction.py --session-id <ID>`

**⚠️ WARNING**: Do NOT use `hrr_batch.py` - it is DEPRECATED and contains divergent detection logic. Always use `hrr_feature_extraction.py`.

**Quality Documentation**: See [hrr_quality_gates.md](./hrr_quality_gates.md)

---

## hrr_interval_reviews
**Human review decisions at interval level**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| interval_id | INT FK | Reference to hr_recovery_intervals.id |
| review_action | VARCHAR(30) | Action type (see below) |
| original_flags | TEXT[] | Snapshot of quality_flags at review time |
| notes | TEXT | Reviewer notes |
| reviewed_at | TIMESTAMPTZ | When reviewed |

- **Unique Constraint**: (interval_id, review_action)
- **Review Actions**:
  - `flags_cleared` - Informational flags acknowledged as OK
  - `peak_shift_verified` - Manual peak adjustment confirmed correct
  - `accepted` - Interval marked as good data
  - `rejected_override` - Force reject otherwise passing interval

**Helper View**: `hrr_review_status` joins intervals with reviews.

---

# HRR Quality Control (QC) System

The HRR QC system supports algorithm validation and human oversight of heart rate recovery interval detection. See also: [hrr_quality_gates.md](./hrr_quality_gates.md)

## QC Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    HRR QC DATA MODEL                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  DETECTION OUTPUT (regenerated on re-extraction)                │
│  ├── hr_recovery_intervals  ← Algorithm detects these           │
│  └── polar_sessions.hrr_qc_status  ← Review tracking            │
│                                                                 │
│  HUMAN CURATION (persists across re-extraction)                 │
│  ├── peak_adjustments       ← Shift peak locations              │
│  ├── hrr_quality_overrides  ← Force pass/reject decisions       │
│  ├── hrr_qc_judgments       ← TP/FP/TN/FN for validation        │
│  ├── hrr_missed_peaks       ← Peaks algorithm didn't detect     │
│  └── hrr_interval_reviews   ← General review notes              │
│                                                                 │
│  ANALYTICS VIEWS                                                │
│  ├── hrr_qc_stats           ← Precision/recall metrics          │
│  └── hrr_session_qc_queue   ← Review queue status               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Principle**: Human curation tables use stable keys (`session_id` + `interval_order`) rather than volatile `interval_id` foreign keys, so corrections persist when intervals are re-extracted.

---

## hrr_qc_judgments
**Algorithm validation judgments for precision/recall calculation**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| polar_session_id | INT FK | Reference to polar_sessions (PK with interval_order) |
| endurance_session_id | INT FK | Reference to endurance_sessions (alternative PK) |
| interval_order | SMALLINT | Which interval (1-indexed, stable key) |
| judgment | VARCHAR(20) | Validation classification (see below) |
| algo_status | VARCHAR(20) | Algorithm's decision (pass/flagged/rejected) snapshot |
| algo_reject_reason | TEXT | Algorithm's rejection reason snapshot |
| peak_correct | VARCHAR(10) | Peak location accuracy: yes, no, shifted |
| peak_shift_sec | SMALLINT | If shifted, by how many seconds |
| notes | TEXT | Human explanation |
| judged_at | TIMESTAMPTZ | When judgment was made |

- **Unique Constraint**: (polar_session_id, interval_order) or (endurance_session_id, interval_order)
- **Migration**: 022_hrr_qc_validation.sql

**Judgment Values:**

| Code | Meaning | When to Use |
|------|---------|-------------|
| `TP` | True Positive | Algorithm correctly found a real recovery peak |
| `FP` | False Positive | Algorithm detected something that isn't a real recovery |
| `TN` | True Negative | Algorithm correctly rejected a non-recovery |
| `FN_REJECTED` | False Negative (Rejected) | Real peak but algorithm rejected it |
| `FN_MISSED` | False Negative (Missed) | Algorithm didn't detect the peak at all |
| `SKIP` | Skip | Cannot determine / not enough information |

**Usage:**
```sql
-- Add a judgment
INSERT INTO hrr_qc_judgments 
    (polar_session_id, interval_order, judgment, algo_status, notes)
VALUES (71, 3, 'FP', 'pass', 'Movement artifact, not real recovery');

-- View all judgments for a session
SELECT * FROM hrr_qc_judgments WHERE polar_session_id = 71;
```

---

## hrr_missed_peaks
**Peaks the algorithm failed to detect entirely (FN_MISSED cases)**

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment |
| polar_session_id | INT FK | Reference to polar_sessions |
| endurance_session_id | INT FK | Reference to endurance_sessions |
| peak_time_elapsed_sec | INT NOT NULL | Seconds from session start where peak should be |
| hr_peak_approx | SMALLINT | Approximate peak HR value |
| notes | TEXT | Description of missed peak |
| created_at | TIMESTAMPTZ | When recorded |

- **Use Case**: Document peaks the algorithm completely missed for improving detection
- **Migration**: 022_hrr_qc_validation.sql

---

## hrr_qc_stats (View)
**Algorithm validation metrics calculated from judgments**

| Column | Type | Description |
|--------|------|-------------|
| tp | INT | True positive count |
| fp | INT | False positive count |
| tn | INT | True negative count |
| fn_rejected | INT | False negatives (rejected) count |
| fn_missed | INT | False negatives (missed) count |
| total | INT | Total judgments |
| precision | NUMERIC | TP / (TP + FP) - of passes, how many real? |
| recall | NUMERIC | TP / (TP + FN) - of real peaks, how many pass? |
| f1 | NUMERIC | Harmonic mean of precision and recall |
| detection_recall | NUMERIC | (TP + FN_REJECTED) / (TP + FN) - did we find the peak at all? |
| rejection_accuracy | NUMERIC | TN / (TN + FN_REJECTED) - of rejected, how many should be? |

**Usage:**
```sql
SELECT * FROM hrr_qc_stats;
-- Returns current precision/recall metrics
```

---

## hrr_session_qc_queue (View)
**Review queue showing all sessions and their QC status**

| Column | Type | Description |
|--------|------|-------------|
| source | TEXT | 'polar' or 'endurance' |
| session_id | INT | Session ID |
| session_date | DATE | Session date |
| sport_type | VARCHAR | Sport type |
| hrr_qc_status | VARCHAR | pending, in_progress, reviewed |
| hrr_qc_reviewed_at | TIMESTAMPTZ | When review completed |
| total_intervals | INT | Total detected intervals |
| pass_ct | INT | Intervals that passed |
| flagged_ct | INT | Intervals flagged for review |
| rejected_ct | INT | Intervals auto-rejected |
| judged_ct | INT | Intervals with human judgments |

**Usage:**
```sql
-- See review queue
SELECT * FROM hrr_session_qc_queue WHERE hrr_qc_status = 'pending';
```

---

## QC Workflow

### Interactive Review (Recommended)

```bash
# ONE COMMAND - walks you through everything
python scripts/hrr_qc.py
```

This interactive script:
1. Shows queue of sessions needing review
2. Opens visualization for selected session
3. Prompts for judgment on each interval
4. Stores judgments in database
5. Shows precision/recall stats

### Manual Review

```bash
# 1. Visualize a session
python scripts/hrr_qc_viz.py --session-id 71

# 2. Add judgments via SQL
INSERT INTO hrr_qc_judgments 
    (polar_session_id, interval_order, judgment, algo_status, notes)
VALUES 
    (71, 1, 'TP', 'pass', NULL),
    (71, 2, 'FP', 'pass', 'Artifact'),
    (71, 3, 'TN', 'rejected', NULL);

# 3. Mark session reviewed
UPDATE polar_sessions SET hrr_qc_status = 'reviewed' WHERE id = 71;

# 4. Check stats
SELECT * FROM hrr_qc_stats;
```

---

## Neo4j Relationship Cache Tables (ADR-001)

Neo4j relationships synced to Postgres for analytics JOINs. **Neo4j is source of truth.**

### neo4j_cache_exercise_patterns
**Caches (Exercise)-[:INVOLVES]->(MovementPattern) relationships**

| Column | Type | Description |
|--------|------|-------------|
| exercise_id | TEXT | Exercise ID (PK with pattern_name) |
| exercise_name | TEXT | Human-readable name |
| pattern_name | TEXT | MovementPattern name (PK with exercise_id) |
| confidence | FLOAT | Relationship confidence score |
| synced_at | TIMESTAMPTZ | Last sync timestamp |

- **Rows**: 4,952
- **Unique Exercises**: 4,136
- **Unique Patterns**: 30
- **Sync**: `sync_pipeline.py --step relationships`

---

### neo4j_cache_exercise_muscles
**Caches (Exercise)-[:TARGETS]->(Muscle|MuscleGroup) relationships**

| Column | Type | Description |
|--------|------|-------------|
| exercise_id | TEXT | Exercise ID (PK with muscle_name, role) |
| exercise_name | TEXT | Human-readable name |
| muscle_name | TEXT | Target muscle name |
| muscle_type | TEXT | 'Muscle' or 'MuscleGroup' |
| role | TEXT | 'primary', 'secondary', or 'unknown' |
| confidence | FLOAT | Relationship confidence score |
| synced_at | TIMESTAMPTZ | Last sync timestamp |

- **Rows**: 13,430
- **Unique Exercises**: 4,240
- **Unique Muscles**: 45
- **Primary targets**: 5,741 | **Secondary targets**: 7,684
- **Sync**: `sync_pipeline.py --step relationships`

---

### Views Built on Cache

| View | Purpose | Query |
|------|---------|-------|
| `pattern_last_trained` | Days since each movement pattern | `SELECT * FROM pattern_last_trained` |
| `muscle_volume_weekly` | Sets/reps/volume per muscle per week | `SELECT * FROM muscle_volume_weekly WHERE role = 'primary'` |

**Sync Script**: `scripts/sync_exercise_relationships.py`

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
