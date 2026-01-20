# HRR Re-extraction Handoff: Migration 024

**Date**: January 19, 2026  
**Issue**: #37 cascading validity bug  
**Changes**: r2_30_90 gate removed, r2_15_45 added

---

## Summary of Code Changes (Already Applied)

| File | Change |
|------|--------|
| `scripts/hrr/metrics.py` | Removed r2_30_90 as hard reject gate (now diagnostic only) |
| `scripts/hrr/metrics.py` | Added r2_15_45 computation (centered 15-45s window) |
| `scripts/hrr/types.py` | Added r2_15_45 to RecoveryInterval dataclass |
| `scripts/hrr/persistence.py` | Added r2_15_45 to columns + values |
| Postgres | Migration 024: Added r2_15_45 column |

---

## The Problem with Re-extraction

The `hrr_qc_judgments` table currently references intervals by `interval_id` (the primary key of `hr_recovery_intervals`). When we re-extract:

1. All intervals are **deleted** and **re-inserted** with new IDs
2. Interval order might shift if detection logic changes peak locations
3. Judgments become orphaned or mismatched

**Solution**: Back up judgments with timestamp-based keys, then remap after re-extraction.

---

## Pre-Extraction Steps

### Step 1: Create Full Backup

```sql
-- Create backup schema if not exists
CREATE SCHEMA IF NOT EXISTS backup_20260119;

-- Back up intervals with all data
CREATE TABLE backup_20260119.hr_recovery_intervals AS 
SELECT * FROM hr_recovery_intervals;

-- Back up judgments
CREATE TABLE backup_20260119.hrr_qc_judgments AS 
SELECT * FROM hrr_qc_judgments;

-- Back up overrides (should survive, but belt+suspenders)
CREATE TABLE backup_20260119.hrr_quality_overrides AS 
SELECT * FROM hrr_quality_overrides;

-- Back up peak adjustments
CREATE TABLE backup_20260119.peak_adjustments AS 
SELECT * FROM peak_adjustments;

-- Verify counts
SELECT 'intervals' as tbl, count(*) FROM backup_20260119.hr_recovery_intervals
UNION ALL
SELECT 'judgments', count(*) FROM backup_20260119.hrr_qc_judgments
UNION ALL
SELECT 'overrides', count(*) FROM backup_20260119.hrr_quality_overrides
UNION ALL
SELECT 'adjustments', count(*) FROM backup_20260119.peak_adjustments;
```

### Step 2: Create Timestamp-Based Judgment Mapping Table

```sql
-- Create mapping table that joins judgments to interval timestamps
-- This survives re-extraction because it uses start_time, not interval_id
CREATE TABLE backup_20260119.judgment_mapping AS
SELECT 
    j.id as judgment_id,
    j.polar_session_id,
    j.endurance_session_id,
    j.interval_order as original_interval_order,
    i.id as original_interval_id,
    i.start_time,  -- KEY: timestamp is stable
    i.end_time,
    i.hr_peak,     -- Secondary match criteria
    i.duration_seconds,
    j.judgment,
    j.algo_status as original_algo_status,
    j.algo_reject_reason as original_algo_reject_reason,
    j.peak_correct,
    j.peak_shift_sec,
    j.notes,
    j.judged_at
FROM hrr_qc_judgments j
JOIN hr_recovery_intervals i ON (
    (j.polar_session_id = i.polar_session_id AND j.interval_order = i.interval_order)
    OR 
    (j.endurance_session_id = i.endurance_session_id AND j.interval_order = i.interval_order)
);

-- Verify mapping captured all judgments
SELECT 
    (SELECT count(*) FROM hrr_qc_judgments) as total_judgments,
    (SELECT count(*) FROM backup_20260119.judgment_mapping) as mapped_judgments;
```

### Step 3: Verify Test Harness Baseline Exists

```sql
-- Confirm baseline snapshot exists
SELECT snapshot_name, created_at, total_intervals, human_judged_count
FROM hrr_algo_baseline
WHERE snapshot_name = 'pre_fix_20260119';
```

If missing, create it:
```sql
-- See earlier session for full baseline creation SQL
-- Or run: SELECT * FROM hrr_algo_baseline_intervals LIMIT 1;
```

---

## Extraction

### Step 4: Run Re-extraction

```bash
cd /Users/brock/Documents/GitHub/arnold

# Dry run first to check for errors
python scripts/hrr_feature_extraction.py --all --dry-run

# If clean, run for real
python scripts/hrr_feature_extraction.py --all
```

**Expected output**: 
- ~800 intervals across 61 sessions
- No Python errors
- Quality overrides and peak adjustments should be applied automatically

---

## Post-Extraction Steps

### Step 5: Remap Judgments to New Interval IDs

```sql
-- Find new intervals that match old intervals by timestamp
-- Allow 2-second tolerance for timestamp matching (rare edge cases)
CREATE TEMP TABLE judgment_remap AS
SELECT 
    m.judgment_id,
    m.polar_session_id,
    m.endurance_session_id,
    m.original_interval_order,
    m.original_interval_id,
    i.id as new_interval_id,
    i.interval_order as new_interval_order,
    m.start_time as original_start_time,
    i.start_time as new_start_time,
    m.judgment,
    m.original_algo_status,
    m.original_algo_reject_reason,
    i.quality_status as new_algo_status,
    i.auto_reject_reason as new_algo_reject_reason,
    m.peak_correct,
    m.peak_shift_sec,
    m.notes,
    m.judged_at,
    -- Match quality indicators
    CASE 
        WHEN m.start_time = i.start_time THEN 'exact'
        WHEN ABS(EXTRACT(EPOCH FROM (m.start_time - i.start_time))) <= 2 THEN 'fuzzy'
        ELSE 'no_match'
    END as match_quality
FROM backup_20260119.judgment_mapping m
LEFT JOIN hr_recovery_intervals i ON (
    -- Match by session + timestamp (primary key for matching)
    (m.polar_session_id = i.polar_session_id OR m.endurance_session_id = i.endurance_session_id)
    AND ABS(EXTRACT(EPOCH FROM (m.start_time - i.start_time))) <= 2
    AND m.hr_peak = i.hr_peak  -- Secondary validation
);

-- Check match quality
SELECT match_quality, count(*) 
FROM judgment_remap 
GROUP BY 1;

-- Review any that didn't match
SELECT * FROM judgment_remap WHERE match_quality = 'no_match';
```

### Step 6: Update Judgments with New Interval Orders

```sql
-- Update judgments to point to new interval_order values
-- (The table uses session_id + interval_order as the key, not interval_id)
UPDATE hrr_qc_judgments j
SET 
    interval_order = r.new_interval_order,
    algo_status = r.new_algo_status,
    algo_reject_reason = r.new_algo_reject_reason
FROM judgment_remap r
WHERE j.id = r.judgment_id
  AND r.match_quality IN ('exact', 'fuzzy')
  AND r.new_interval_id IS NOT NULL;

-- Verify update
SELECT 
    (SELECT count(*) FROM hrr_qc_judgments) as total_judgments,
    (SELECT count(*) FROM judgment_remap WHERE match_quality IN ('exact', 'fuzzy')) as remapped;
```

### Step 7: Validate Against Baseline

```sql
-- Compare to pre-fix baseline
SELECT 
    change_type,
    count(*) as intervals,
    array_agg(DISTINCT auto_reject_reason) as reject_reasons
FROM hrr_algo_comparison
GROUP BY 1
ORDER BY 1;

-- Detailed view of fixes
SELECT 
    polar_session_id,
    interval_order,
    baseline_status,
    baseline_reject_reason,
    current_status,
    current_reject_reason,
    human_judgment,
    change_type
FROM hrr_algo_comparison
WHERE change_type = 'fixed'
ORDER BY polar_session_id, interval_order;

-- CRITICAL: Check for regressions
SELECT * FROM hrr_algo_comparison
WHERE change_type = 'regression';
-- This should return 0 rows!
```

### Step 8: Recalculate QC Stats

```sql
-- Updated precision/recall with new algo results
SELECT * FROM hrr_qc_stats;
```

**Expected improvement**:
- Recall should increase (fewer false negatives from r2_30_90 gate)
- Precision should stay similar (we didn't change what makes a "real" peak)

---

## Validation Checklist

- [ ] Backup tables exist in `backup_20260119` schema
- [ ] All 801 judgments remapped successfully
- [ ] Zero regressions in `hrr_algo_comparison`
- [ ] `r2_15_45` column populated for all intervals with duration >= 45s
- [ ] Intervals previously rejected for `r2_30_90_below_0.75` now pass (if HRR60 valid)
- [ ] QC stats show improved recall

---

## Rollback Procedure (If Needed)

```sql
-- Restore intervals
TRUNCATE hr_recovery_intervals;
INSERT INTO hr_recovery_intervals SELECT * FROM backup_20260119.hr_recovery_intervals;

-- Restore judgments
TRUNCATE hrr_qc_judgments;
INSERT INTO hrr_qc_judgments SELECT * FROM backup_20260119.hrr_qc_judgments;

-- Restore overrides
TRUNCATE hrr_quality_overrides;
INSERT INTO hrr_quality_overrides SELECT * FROM backup_20260119.hrr_quality_overrides;

-- Restore peak adjustments
TRUNCATE peak_adjustments;
INSERT INTO peak_adjustments SELECT * FROM backup_20260119.peak_adjustments;
```

---

## Post-Migration Cleanup (After Validation)

Once validated, you can optionally:

```sql
-- Keep backups for 30 days, then drop
-- DROP SCHEMA backup_20260119 CASCADE;
```

---

## Files Modified in This Session

```
scripts/hrr/metrics.py          # r2_30_90 gate removed, r2_15_45 added
scripts/hrr/types.py            # r2_15_45 field added
scripts/hrr/persistence.py      # r2_15_45 in columns/values
scripts/migrations/024_r2_15_45_and_gate_fix.sql  # New migration
docs/DATA_DICTIONARY.md         # Updated R² documentation
docs/hrr_quality_gates.md       # Updated gate table
```

---

## Expected Outcomes

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Total intervals | ~807 | ~807 (unchanged) |
| Pass rate | ~65% | ~68-70% |
| r2_30_90 rejects | 11 | 0 |
| New r2_15_45 data | 0 | ~750+ |
| Regressions | N/A | 0 |

---

## Contact

Session context in: `/mnt/transcripts/2026-01-19-18-53-15-hrr-algorithm-test-harness-and-cascading-fix.txt`
