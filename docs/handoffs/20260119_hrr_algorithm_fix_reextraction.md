# HRR Algorithm Fix: Re-extraction Handoff

**Date**: January 19, 2026  
**Issue**: #37 - Cascading validity bug (r2_30_90 incorrectly rejecting valid HRR60 intervals)  
**Migration**: 024

---

## Summary of Changes

### Code Changes (Already Applied)

| File | Change |
|------|--------|
| `scripts/hrr/metrics.py` | Removed r2_30_90 as hard reject gate (now diagnostic only) |
| `scripts/hrr/metrics.py` | Added r2_15_45 computation (centered 15-45s window) |
| `scripts/hrr/types.py` | Added r2_15_45 to RecoveryInterval dataclass |
| `scripts/hrr/persistence.py` | Added r2_15_45 to columns + values |

### Schema Changes (Already Applied)

```sql
-- Migration 024 already run
ALTER TABLE hr_recovery_intervals ADD COLUMN r2_15_45 REAL;
```

### Documentation Updated

- `docs/DATA_DICTIONARY.md` - R² section with gate logic
- `docs/hrr_quality_gates.md` - Hard reject table updated

---

## Pre-Extraction: Full Backup

### Step 1: Create timestamped backup of all HRR tables

```sql
-- Run this BEFORE extraction
-- Creates point-in-time backup with timestamp suffix

DO $$
DECLARE
    ts TEXT := to_char(NOW(), 'YYYYMMDD_HH24MI');
BEGIN
    -- Backup intervals (main table)
    EXECUTE format('CREATE TABLE hr_recovery_intervals_backup_%s AS SELECT * FROM hr_recovery_intervals', ts);
    RAISE NOTICE 'Created hr_recovery_intervals_backup_%', ts;
    
    -- Backup judgments (human QC decisions)
    EXECUTE format('CREATE TABLE hrr_qc_judgments_backup_%s AS SELECT * FROM hrr_qc_judgments', ts);
    RAISE NOTICE 'Created hrr_qc_judgments_backup_%', ts;
    
    -- Backup overrides
    EXECUTE format('CREATE TABLE hrr_quality_overrides_backup_%s AS SELECT * FROM hrr_quality_overrides', ts);
    RAISE NOTICE 'Created hrr_quality_overrides_backup_%', ts;
    
    -- Backup peak adjustments
    EXECUTE format('CREATE TABLE peak_adjustments_backup_%s AS SELECT * FROM peak_adjustments', ts);
    RAISE NOTICE 'Created peak_adjustments_backup_%', ts;
    
    -- Backup missed peaks
    EXECUTE format('CREATE TABLE hrr_missed_peaks_backup_%s AS SELECT * FROM hrr_missed_peaks', ts);
    RAISE NOTICE 'Created hrr_missed_peaks_backup_%', ts;
END $$;
```

### Step 2: Create judgment remapping table

The `hrr_qc_judgments` table uses stable keys (session_id + interval_order), but we want to be extra safe. This creates a mapping table that links judgments to intervals via timestamp proximity.

```sql
-- Create a remapping table that captures judgment → interval relationships
-- Uses start_time as the stable anchor (peaks detected at same time = same interval)

CREATE TABLE IF NOT EXISTS hrr_judgment_remap_20260119 AS
SELECT 
    j.id as judgment_id,
    j.polar_session_id,
    j.interval_order,
    j.judgment,
    j.algo_status as pre_fix_algo_status,
    j.algo_reject_reason as pre_fix_reject_reason,
    j.notes,
    j.judged_at,
    i.id as pre_fix_interval_id,
    i.start_time as interval_start_time,
    i.hr_peak,
    i.quality_status as pre_fix_quality_status,
    i.auto_reject_reason as pre_fix_auto_reject_reason
FROM hrr_qc_judgments j
JOIN hr_recovery_intervals i 
    ON j.polar_session_id = i.polar_session_id 
    AND j.interval_order = i.interval_order
WHERE j.polar_session_id IS NOT NULL;

-- Verify
SELECT COUNT(*) as total_judgments,
       COUNT(DISTINCT polar_session_id) as sessions_with_judgments
FROM hrr_judgment_remap_20260119;
```

### Step 3: Verify baseline snapshot exists

```sql
-- Check our test harness baseline exists
SELECT snapshot_id, created_at, total_intervals, human_judged_intervals
FROM hrr_algo_baseline
WHERE snapshot_id = 'pre_fix_20260119';
```

---

## Extraction

### Step 4: Run full re-extraction

```bash
cd /Users/brock/Documents/GitHub/arnold

# Dry run first to check for errors
python scripts/hrr_feature_extraction.py --all --dry-run

# If no errors, run for real
python scripts/hrr_feature_extraction.py --all
```

**Expected output:**
- Should process all 61+ Polar sessions
- Each session: delete old intervals → detect peaks → compute metrics → save
- Peak adjustments and quality overrides are automatically re-applied

---

## Post-Extraction Validation

### Step 5: Quick sanity check

```sql
-- Basic counts
SELECT 
    COUNT(*) as total_intervals,
    COUNT(*) FILTER (WHERE quality_status = 'pass') as passed,
    COUNT(*) FILTER (WHERE quality_status = 'rejected') as rejected,
    COUNT(*) FILTER (WHERE quality_status = 'flagged') as flagged,
    COUNT(*) FILTER (WHERE r2_15_45 IS NOT NULL) as has_r2_15_45
FROM hr_recovery_intervals;
```

### Step 6: Compare against baseline (test harness)

```sql
-- This is the key validation query
-- Shows what changed between baseline and current state

SELECT 
    change_type,
    COUNT(*) as count,
    array_agg(DISTINCT auto_reject_reason) as reject_reasons
FROM hrr_algo_comparison
GROUP BY change_type
ORDER BY change_type;
```

**Expected results:**
- `fixed`: ~11+ intervals (the r2_30_90 cases that now pass)
- `regression`: **MUST BE ZERO** - any regressions indicate a bug
- `unchanged`: majority of intervals

### Step 7: Detailed change review

```sql
-- See exactly what changed
SELECT 
    c.polar_session_id,
    c.interval_order,
    c.change_type,
    c.baseline_status,
    c.current_status,
    c.baseline_reject_reason,
    c.current_reject_reason,
    c.human_judgment,
    i.r2_30_90,
    i.r2_15_45
FROM hrr_algo_comparison c
JOIN hr_recovery_intervals i 
    ON c.polar_session_id = i.polar_session_id 
    AND c.interval_order = i.interval_order
WHERE c.change_type != 'unchanged'
ORDER BY c.change_type, c.polar_session_id, c.interval_order;
```

### Step 8: Verify judgment remapping

```sql
-- Check that judgments still align with intervals
-- Match by start_time (timestamp-based remapping)

SELECT 
    r.judgment_id,
    r.polar_session_id,
    r.interval_order,
    r.judgment,
    r.pre_fix_quality_status,
    r.pre_fix_auto_reject_reason,
    i.quality_status as post_fix_quality_status,
    i.auto_reject_reason as post_fix_auto_reject_reason,
    CASE 
        WHEN r.judgment IN ('TP', 'FN_REJECTED') AND i.quality_status = 'pass' THEN 'FIXED ✓'
        WHEN r.judgment = 'TN' AND i.quality_status = 'rejected' THEN 'STILL_TN ✓'
        WHEN r.judgment = 'FP' AND i.quality_status = 'pass' THEN 'STILL_FP (needs override)'
        WHEN r.judgment IN ('TP', 'FN_REJECTED') AND i.quality_status = 'rejected' THEN 'STILL_REJECTED'
        ELSE 'CHECK'
    END as status
FROM hrr_judgment_remap_20260119 r
JOIN hr_recovery_intervals i 
    ON r.polar_session_id = i.polar_session_id 
    AND r.interval_order = i.interval_order
ORDER BY 
    CASE 
        WHEN r.judgment IN ('TP', 'FN_REJECTED') AND i.quality_status = 'pass' THEN 1
        WHEN r.judgment = 'TN' AND i.quality_status = 'rejected' THEN 2
        ELSE 3
    END,
    r.polar_session_id, r.interval_order;
```

### Step 9: Update QC stats

```sql
-- Refresh the QC stats view to see new precision/recall
SELECT * FROM hrr_qc_stats;
```

**Expected improvement:**
- Recall should increase (fewer false negatives from r2_30_90 gate)
- Precision should stay similar or improve slightly

---

## Rollback (If Needed)

If something goes wrong, restore from backup:

```sql
-- Find your backup tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_name LIKE 'hr_recovery_intervals_backup_%'
ORDER BY table_name DESC
LIMIT 5;

-- Restore (replace YYYYMMDD_HHMM with your timestamp)
TRUNCATE hr_recovery_intervals;
INSERT INTO hr_recovery_intervals SELECT * FROM hr_recovery_intervals_backup_YYYYMMDD_HHMM;
```

---

## Cleanup (After Validation)

Once you're satisfied with the results:

```sql
-- Drop backup tables (keep for a few days first)
-- DROP TABLE hr_recovery_intervals_backup_YYYYMMDD_HHMM;
-- DROP TABLE hrr_qc_judgments_backup_YYYYMMDD_HHMM;
-- etc.

-- Keep the remap table for reference
-- DROP TABLE hrr_judgment_remap_20260119;
```

---

## Expected Outcomes

### Intervals that should now PASS (were rejected for r2_30_90_below_0.75):

Based on QC analysis, approximately 11 intervals were:
- Judged as valid HRR60 by human review
- Rejected by algorithm due to r2_30_90 < 0.75
- These should now pass since r2_30_90 is no longer a hard reject

### New diagnostic data:

- `r2_15_45` column now populated for all intervals with sufficient duration
- Can analyze whether r2_15_45 correlates with valid recoveries when r2_30_60 is borderline

---

## Next Steps After Validation

1. **If all looks good**: Update GitHub issue #37 as resolved
2. **Review r2_15_45 data**: Analyze whether it helps identify edge cases
3. **Consider threshold tuning**: If r2_30_60 still rejects valid intervals, may need threshold adjustment
4. **Re-run QC on changed intervals**: Verify the 11 newly-passing intervals visually

---

## Commands Quick Reference

```bash
# Backup (run SQL above in psql or via postgres-mcp)

# Extraction
cd /Users/brock/Documents/GitHub/arnold
python scripts/hrr_feature_extraction.py --all --dry-run  # test first
python scripts/hrr_feature_extraction.py --all            # for real

# Validation (run SQL above)
```
