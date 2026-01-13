# Apple Health Data Pipeline - Handoff Document

## Session Summary
Investigated and fixed Apple Health data pipeline gap. XML parsing worked but no Postgres loader existed. Added gait metrics and created the missing loader.

## Problem Discovered
- `import_apple_health.py` successfully parses XML → staging parquets
- **No script existed** to load staging parquets → Postgres `biometric_readings` table
- Result: Steps, gait data stuck in parquet files, never reaching analytics layer

## Changes Made

### 1. `scripts/sync/import_apple_health.py`
Added 5 gait record types to `RECORD_TYPES`:
```python
"HKQuantityTypeIdentifierWalkingAsymmetryPercentage": "walking_asymmetry",
"HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": "walking_double_support",
"HKQuantityTypeIdentifierWalkingStepLength": "walking_step_length",
"HKQuantityTypeIdentifierWalkingSpeed": "walking_speed",
"HKQuantityTypeIdentifierAppleWalkingSteadiness": "walking_steadiness",
```

Added `process_gait_records()` function for daily aggregation.

Updated `main()` to process all gait metrics and save to staging.

### 2. `scripts/sync/apple_health_to_postgres.py` (NEW)
Created loader script that:
- Reads staging parquets
- Aggregates by date (sum for steps, mean for gait metrics)
- Upserts to `biometric_readings` with proper conflict handling
- Handles multiple `source_name` values per day (Hexagon, Ultrahuman, etc.)

Key fix: Original version failed with `CardinalityViolation` because multiple source_names collapsed to single `source='apple_health'`. Fixed by pre-aggregating per date before insert.

### 3. `scripts/sync_pipeline.py`
Updated `step_apple()` to run both scripts in sequence:
1. Parse XML → staging parquet
2. Load staging → Postgres

## To Complete Initial Load

```bash
cd ~/Documents/GitHub/arnold

# 1. Parse XML with --full to bypass cutoff (required for first run)
python scripts/sync/import_apple_health.py --full --verbose

# 2. Load to Postgres
python scripts/sync/apple_health_to_postgres.py --verbose
```

The `--full` flag is needed because existing Apple HRV data (97 rows) sets a cutoff date that would skip historical gait/steps data.

## Expected Results in Postgres

| metric_type | source | approx rows | notes |
|-------------|--------|-------------|-------|
| steps | apple_health | ~1,400 | Daily totals (summed across sources) |
| walking_asymmetry_pct | apple_health | ~500 | L/R leg imbalance % |
| walking_double_support_pct | apple_health | ~500 | Balance indicator |
| walking_step_length | apple_health | ~500 | Stride length |
| walking_speed | apple_health | ~500 | Walking pace |
| walking_steadiness | apple_health | ~50 | Fall risk (less frequent) |

## Sensor Hierarchy (FR-002)
- **Steps**: Apple Health (1) > Ultrahuman (2) > Suunto (3)
- **Gait/Balance**: Apple Health only source
- Rationale: Phone carried more consistently than ring

## Open Items

1. **Cutoff logic improvement**: Currently source-wide (`WHERE source ILIKE '%apple%'`). Should be metric-specific so new metric types don't get skipped on incremental imports.

2. **Ultrahuman steps deduplication**: Now have both sources in `biometric_readings`. Analytics queries should filter by source or implement hierarchy logic per FR-002.

## Resolved

- **Apple HRV excluded**: Per FR-002, Apple HRV uses SDNN algorithm incompatible with Ultrahuman RMSSD baseline. Import disabled, existing 97 rows deleted from `biometric_readings`. Ultrahuman is sole HRV source.

## File Locations
- Parser: `/scripts/sync/import_apple_health.py`
- Loader: `/scripts/sync/apple_health_to_postgres.py`
- Pipeline: `/scripts/sync_pipeline.py`
- Staging: `/data/staging/apple_health_*.parquet`
- Raw: `/data/raw/apple_health_export/export.xml` (240MB)
