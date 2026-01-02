# Arnold Data Dictionary

> **Purpose**: Comprehensive reference for the Arnold analytics data lake. Describes all data sources, schemas, relationships, and fitness for use.
> **Last Updated**: January 1, 2026
> **Location**: `/arnold/data/`

---

## Overview

Arnold's analytics layer uses a **data lake architecture**:

```
/data/
├── raw/                    # Native format, untouched
│   ├── apple_health_export/   # 217MB XML + clinical FHIR JSON
│   ├── ultrahuman/            # Manual CSV exports
│   ├── neo4j_snapshots/       # Graph exports
│   ├── old_race_info/         # Historical race data
│   └── ...
├── staging/                # Parquet files (query-ready)
├── catalog.json            # Data registry (this doc's source of truth)
└── arnold_analytics.duckdb # Analytics database (pending)
```

**Design Principle**: Raw stays raw. Staging is minimally transformed. Intelligence lives in the catalog.

---

## Data Sources Summary

| Source | Tables | Rows | Date Range | Status |
|--------|--------|------|------------|--------|
| Apple Health | 8 | 20,227 | May 2025 → Dec 2025 | ✅ Staged |
| Clinical (FHIR) | 4 | 584 | Various | ✅ Staged |
| Ultrahuman | 1 | 234 | May 2025 → Jan 2026 | ✅ Staged |
| Neo4j Export | 4 | 6,886 | Apr 2024 → Dec 2025 | ✅ Staged |
| Race History | 1 | 95 | Nov 2005 → Mar 2023 | ✅ Staged |

---

## Apple Health Sources

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
- **Join Keys**: date, hour
- **Note**: Aggregated from ~5-minute samples. Use for daily/hourly trends.

---

### apple_health_hrv
**Heart rate variability measurements (SDNN)**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Measurement date |
| measured_at | datetime | Exact timestamp |
| hrv_ms | float | SDNN in milliseconds |
| unit | string | Always "ms" |
| source_name | string | Device (usually Ultrahuman) |

- **Grain**: Individual measurement
- **Rows**: 9,912
- **Date Range**: 2025-05-15 → 2025-12-06
- **Join Keys**: date
- **Statistics**: min=1ms, max=255ms, mean=76.8ms
- **Note**: High granularity. Aggregate to daily for most analyses.

---

### apple_health_sleep
**Sleep session segments by stage**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Wake date (attribution) |
| start_ts | datetime | Segment start |
| end_ts | datetime | Segment end |
| duration_minutes | float | Segment duration |
| sleep_stage | string | inbed, asleep, asleepcore, asleepdeep, asleeprem, awake |
| source_name | string | Device |

- **Grain**: Sleep segment
- **Rows**: 4,281
- **Join Keys**: date
- **Note**: Multiple segments per night. Aggregate by date for total sleep, by stage for composition.

```sql
-- Example: Daily sleep totals
SELECT date, 
       SUM(duration_minutes) as total_sleep,
       SUM(CASE WHEN sleep_stage = 'asleepdeep' THEN duration_minutes END) as deep_sleep
FROM apple_health_sleep
GROUP BY date
```

---

### apple_health_workouts
**Workout sessions from Suunto, Polar, Ultrahuman**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Workout date |
| start_ts | datetime | Start time |
| end_ts | datetime | End time |
| activity | string | Walking, Running, HIIT, TraditionalStrengthTraining, etc. |
| duration_min | float | Duration in minutes |
| distance | float | Distance (nullable) |
| total_distance_unit | string | Unit (mi, km) |
| calories | float | Energy burned (nullable) |
| source_name | string | Suunto, Ultrahuman, Polar Flow |

- **Grain**: Workout session
- **Rows**: 197
- **Date Range**: 2024-04-15 → 2025-09-02
- **Activity Distribution**: Walking (91), Running (43), HIIT (31), Strength (15), Rowing (5)
- **Note**: May overlap with Neo4j workouts. Use time matching for deduplication.

---

### apple_health_steps
**Daily step counts by source**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Date |
| source_name | string | Device/app |
| steps | int | Total steps |

- **Grain**: Date × Source
- **Rows**: 1,672
- **Join Keys**: date
- **Note**: Multiple sources may report for same day. Sum or pick preferred source.

---

### apple_health_resting_hr
**Resting heart rate measurements**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Date |
| measured_at | datetime | Measurement time |
| resting_hr | float | Resting HR (bpm) |
| unit | string | Always "count/min" |
| source_name | string | Device |

- **Grain**: Measurement
- **Rows**: 168
- **Join Keys**: date
- **Note**: Usually one measurement per day from Ultrahuman.

---

### apple_health_weight
**Body mass measurements**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Date |
| measured_at | datetime | Measurement time |
| weight_lbs | float | Weight in pounds |
| unit | string | lb |
| source_name | string | Usually manual entry |

- **Grain**: Measurement
- **Rows**: 3
- **Fitness for Use**: LOW - sparse manual entries only
- **Action Needed**: Regular weigh-ins recommended

---

### apple_health_bp
**Blood pressure measurements**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Date |
| timestamp | datetime | Measurement time |
| systolic | float | Systolic (mmHg) |
| diastolic | float | Diastolic (mmHg) |
| source_name | string | Device |

- **Grain**: Measurement
- **Rows**: 2
- **Fitness for Use**: LOW - sparse data

---

## Clinical Sources (FHIR)

### clinical_labs
**Lab test results from MyChart/Epic**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Test date |
| test_name | string | Human-readable test name |
| loinc_code | string | LOINC code (nullable) |
| value | float | Result value |
| unit | string | Unit of measure |
| ref_range_low | float | Reference range low (nullable) |
| ref_range_high | float | Reference range high (nullable) |
| ref_range_text | string | Text description of range |
| encounter_type | string | Visit type |
| status | string | final, preliminary, etc. |
| source_file | string | Original FHIR JSON filename |

- **Grain**: Test result
- **Rows**: 494
- **Unique Tests**: 179
- **Tests with LOINC**: 394 (80%)
- **Common Tests**: Albumin (10), Globulin (10), Total Protein (10), Chloride (9), Potassium (9)
- **Fitness for Use**: HIGH - standard FHIR format, LOINC coded

```sql
-- Example: Track a biomarker over time
SELECT date, value, unit, ref_range_low, ref_range_high
FROM clinical_labs
WHERE loinc_code = '3094-0'  -- BUN
ORDER BY date
```

---

### clinical_conditions
**Diagnoses from medical records**

| Column | Type | Description |
|--------|------|-------------|
| condition_name | string | Diagnosis name |
| icd_code | string | ICD-10 code (nullable) |
| snomed_code | string | SNOMED-CT code (nullable) |
| onset_date | date | When condition started (nullable) |
| abatement_date | date | When resolved (nullable) |
| clinical_status | string | active, resolved, etc. |
| source_file | string | Original FHIR JSON |

- **Grain**: Condition
- **Rows**: 12
- **Note**: Historical conditions, includes resolved

---

### clinical_medications
**Prescription history**

| Column | Type | Description |
|--------|------|-------------|
| medication_name | string | Drug name |
| rxnorm_code | string | RxNorm code (nullable) |
| dosage | string | Dosage instructions |
| authored_date | date | Prescription date |
| status | string | active, completed, cancelled |
| source_file | string | Original FHIR JSON |

- **Grain**: Medication record
- **Rows**: 58
- **Note**: Historical, includes completed/cancelled prescriptions

---

### clinical_immunizations
**Vaccination records**

| Column | Type | Description |
|--------|------|-------------|
| vaccine_name | string | Vaccine name |
| cvx_code | string | CVX code (nullable) |
| date | date | Immunization date |
| lot_number | string | Vaccine lot (nullable) |
| status | string | completed, etc. |
| source_file | string | Original FHIR JSON |

- **Grain**: Immunization
- **Rows**: 20

---

## Ultrahuman Source

### ultrahuman_daily
**Daily wellness metrics from Ultrahuman ring**

| Column | Type | Description |
|--------|------|-------------|
| date | date | Date |
| sleep_score | float | Overall sleep quality (0-100) |
| recovery_score | float | Recovery readiness (0-100) |
| movement_score | float | Activity score (0-100) |
| steps | int | Daily steps |
| calories | int | Calories burned |
| sleep_minutes | int | Total sleep duration |
| sleep_awake_minutes | int | Time awake during sleep |
| deep_sleep_minutes | int | Deep sleep duration |
| rem_sleep_minutes | int | REM sleep duration |
| light_sleep_minutes | int | Light sleep duration |
| sleep_efficiency | float | Sleep efficiency % |
| perceived_recovery | float | Self-reported recovery (nullable) |
| skin_temp_c | float | Skin temperature |
| resting_hr | float | Resting heart rate |
| hrv_ms | float | HRV (SDNN) |
| activity_minutes | int | Active minutes |
| _source | string | Always "ultrahuman" |
| _source_file | string | Source CSV filename |

- **Grain**: Date
- **Rows**: 234
- **Date Range**: 2025-05-13 → 2026-01-01
- **Join Keys**: date
- **Fitness for Use**: HIGH - complete daily metrics

**Relationship to Apple Health**: Ultrahuman writes granular data to Apple Health. This table has daily aggregates from Ultrahuman's own export. Use this for scores; use Apple Health for granular HR/HRV.

---

## Neo4j Export Sources

### workouts
**Training sessions from Neo4j graph**

| Column | Type | Description |
|--------|------|-------------|
| workout_id | string | UUID primary key |
| date | date | Workout date |
| type | string | strength, conditioning, endurance, recovery, deload, mobility, mixed |
| duration_min | int | Duration (nullable) |
| notes | string | Session notes (nullable) |

- **Grain**: Workout session
- **Rows**: 163
- **Date Range**: 2024-04-04 → 2025-12-30
- **Join Keys**: workout_id, date
- **Fitness for Use**: HIGH - authoritative training log

---

### sets
**Individual exercise sets from Neo4j**

| Column | Type | Description |
|--------|------|-------------|
| set_id | string | UUID primary key |
| workout_id | string | FK to workouts |
| date | date | Via workout |
| set_number | int | Order within exercise |
| reps | int | Repetitions (nullable) |
| load_lbs | float | Weight in pounds (nullable) |
| rpe | float | Rate of perceived exertion 1-10 (nullable) |
| duration_sec | int | For timed sets (nullable) |
| distance_miles | float | For distance sets (nullable) |
| notes | string | Set notes (nullable) |
| exercise_id | string | FK to exercises |
| exercise_name | string | Denormalized for convenience |
| patterns | string | Movement patterns (comma-separated) |

- **Grain**: Set
- **Rows**: 2,453
- **Join Keys**: set_id, workout_id, exercise_id, date

---

### exercises
**Canonical exercise library from Neo4j**

| Column | Type | Description |
|--------|------|-------------|
| exercise_id | string | UUID primary key |
| name | string | Exercise name |
| source | string | ffdb, free-exercise-db, custom |
| movement_patterns | string | Comma-separated patterns |

- **Grain**: Exercise
- **Rows**: 4,242
- **Note**: Includes aliases for custom exercise names

---

### movement_patterns
**Movement pattern taxonomy**

| Column | Type | Description |
|--------|------|-------------|
| pattern_id | string | UUID |
| name | string | Pattern name |
| category | string | push, pull, hinge, squat, carry, etc. |

- **Grain**: Pattern
- **Rows**: 28
- **Examples**: Hip Hinge, Squat, Vertical Pull, Horizontal Push, Anti-Extension, Rotation

---

## Race History

### race_history
**Consolidated running and triathlon race results**

| Column | Type | Description |
|--------|------|-------------|
| event_date | date | Race date |
| event_year | int | Year |
| event_name | string | Race name |
| distance_label | string | 5K, Marathon, 50 Miler, Half Ironman, etc. |
| distance_miles | float | Distance in miles |
| location_city | string | City (nullable) |
| location_state | string | State (nullable) |
| finish_time | string | HH:MM:SS format |
| finish_seconds | float | Total seconds |
| overall_place | float | Overall finish position (nullable) |
| overall_field | float | Total finishers (nullable) |
| division_place | float | Age group position (nullable) |
| division_field | float | Age group size (nullable) |
| age_at_race | float | Age when raced (nullable) |
| rank_percent | float | Percentile finish (nullable) |
| sport | string | running, triathlon |
| race_type | string | 5K, 10K, Half Marathon, Marathon, 50K, 50 Miler, 100K, 100 Miler, Half Ironman, Olympic, Xterra |
| source | string | Data source file |
| swim_time | string | Tri swim split (nullable) |
| bike_time | string | Tri bike split (nullable) |
| run_time | string | Tri run split (nullable) |
| weather | string | Conditions (nullable) |

- **Grain**: Race result
- **Rows**: 95
- **Date Range**: 2005-11-24 → 2023-03-11
- **Running Races**: 90
- **Triathlon Races**: 5

**Distribution by Distance:**
| Type | Count |
|------|-------|
| 5K | 10 |
| 10K | 6 |
| Half Marathon | 7 |
| 20 Miler | 6 |
| Marathon | 12 |
| 50K | 9 |
| 50 Miler | 15 |
| 100K | 14 |
| 100 Miler | 7 |
| Half Ironman | 2 |
| Olympic Tri | 2 |
| Xterra | 1 |

---

## Join Strategies

### Date-Based Joins

Most tables join on `date`. Example unified daily view:

```sql
SELECT 
    w.date,
    w.workout_id,
    u.sleep_score,
    u.recovery_score,
    u.hrv_ms as ultrahuman_hrv,
    AVG(h.hrv_ms) as apple_hrv_avg,
    AVG(hr.hr_avg) as avg_hr
FROM workouts w
LEFT JOIN ultrahuman_daily u ON w.date = u.date
LEFT JOIN apple_health_hrv h ON w.date = h.date
LEFT JOIN apple_health_hr hr ON w.date = hr.date
GROUP BY w.date, w.workout_id, u.sleep_score, u.recovery_score, u.hrv_ms
```

### Workout Deduplication

Apple Health workouts may overlap with Neo4j workouts. Match by:
1. Same date
2. Similar start time (within 30 minutes)
3. Similar duration

---

## Known Data Quality Issues

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Sparse weight data (3 rows) | Can't track body composition trends | Add regular weigh-ins |
| Sparse BP data (2 rows) | No BP trend analysis | Add regular measurements |
| Apple Health workouts end Sep 2025 | Gap in workout HR data | Continue manual logging |
| HRV ends Dec 6 | Recent HRV missing | Re-export Apple Health |
| Some labs missing LOINC | 20% can't be standardized | Manual mapping if needed |

---

## Refresh Patterns

| Source | Refresh Method | Frequency |
|--------|---------------|-----------|
| Apple Health | Export XML from iPhone, run `import_apple_health.py` | Weekly/Monthly |
| Ultrahuman | Manual CSV export, run `stage_ultrahuman.py` | Weekly |
| Neo4j | Run `export_to_analytics.py` | After workouts |
| Clinical | Automatic via Apple Health export | With health export |
| Race History | Manual update | As needed |

---

## File Locations

```
/arnold/data/
├── raw/
│   ├── apple_health_export/
│   │   ├── export.xml              # 217MB main health data
│   │   ├── export_cda.xml          # Clinical documents
│   │   └── clinical-records/       # ~900 FHIR JSON files
│   ├── ultrahuman/
│   │   └── manual_export_*.csv
│   ├── old_race_info/
│   │   ├── brock_webb_race_history.csv
│   │   └── Webb-Race-Resume*.csv
│   └── neo4j_snapshots/
├── staging/
│   ├── apple_health_*.parquet      # 8 files
│   ├── clinical_*.parquet          # 4 files
│   ├── ultrahuman_daily.parquet
│   ├── race_history.parquet
│   ├── workouts.parquet
│   ├── sets.parquet
│   ├── exercises.parquet
│   └── movement_patterns.parquet
├── catalog.json                    # This doc's source of truth
└── arnold_analytics.duckdb         # Pending creation
```

---

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/sync/import_apple_health.py` | Parse Apple Health XML | `python import_apple_health.py --verbose` |
| `scripts/sync/stage_ultrahuman.py` | Stage Ultrahuman CSV | `python stage_ultrahuman.py` |
| `scripts/export_to_analytics.py` | Export Neo4j to Parquet | `python export_to_analytics.py` |

---

## Training Metrics

For evidence-based training metrics (ACWR, TSS, volume targets, etc.), see:

**[TRAINING_METRICS.md](./TRAINING_METRICS.md)** — Complete specification with:
- Tier 1: Metrics calculable from logged workouts (Volume Load, ACWR, Monotony, Strain)
- Tier 2: Metrics requiring biometric data (hrTSS, Readiness, ATL/CTL/TSB)
- Tier 3: Metrics requiring external platform export (Suunto TSS, rTSS)
- Full citations for all formulas and thresholds
- Coaching decision matrix

---

## Next Steps

1. **Create DuckDB database** - Load all Parquet files
2. **Build unified views** - Daily/weekly rollups joining all sources
3. **Implement arnold-analytics-mcp** - Query interface for Claude
4. **Implement Tier 1 metrics** - ACWR, monotony, strain from workout data
5. **Pattern detection** - HRV ↔ performance, sleep ↔ recovery correlations
