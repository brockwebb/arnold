# Issue 004: Apple Health Import Deduplication

> **Created**: January 7, 2026
> **Status**: Backlog
> **Priority**: High (data integrity)

## Problem

Apple Health exports contain HRV data that can conflict with native device data:

1. **Apple Health HRV (RMSSD)**: ~90-120ms range, algorithm applied to Apple Watch PPG
2. **Ultrahuman Ring HRV**: ~20-50ms range, native ring algorithm

When importing Apple Health data, we previously conflated these sources, labeling Apple HRV as `hrv_morning` with source `ultrahuman`. This corrupted the Ring-native HRV baseline.

**Cleanup performed Jan 7, 2026**: Deleted 83 mislabeled records where `hrv_morning` values >50ms were actually Apple passthrough duplicates.

## Required Fix

The Apple Health import script (`scripts/import_apple_health.py`) must:

1. **Label source correctly**: Apple Health data must use `source = 'apple_health'`, never `ultrahuman`
2. **Use distinct metric types**:
   - Apple Watch HRV → `hrv_apple_rmssd`
   - Ring HRV → `hrv_morning` (only from Ultrahuman API)
3. **Deduplicate on import**: Skip records that already exist for (date, metric_type, source)
4. **Never overwrite device-native data**: Ring-native values are authoritative for `hrv_morning`

## Implementation

```python
# In import_apple_health.py
HRV_METRIC_TYPE = 'hrv_apple_rmssd'  # NOT 'hrv_morning'
SOURCE = 'apple_health'              # NOT 'ultrahuman'

# Dedup check before insert
INSERT INTO biometric_readings (reading_date, metric_type, value, source)
VALUES ($1, $2, $3, $4)
ON CONFLICT (reading_date, metric_type, source) DO NOTHING;
```

## Validation

After import, verify no cross-contamination:
```sql
-- Should return 0 rows
SELECT * FROM biometric_readings 
WHERE source = 'ultrahuman' AND metric_type = 'hrv_morning' AND value > 50;

-- Apple HRV should be separate
SELECT COUNT(*), AVG(value) FROM biometric_readings 
WHERE metric_type = 'hrv_apple_rmssd';
```

## Related

- See data annotation #4 in `data_annotations` table
- ADR-001: Data Layer Separation
- Issue 003: Postgres Analytics Layer
