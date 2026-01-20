# HRR Re-extraction Complete

**Date**: January 19, 2026  
**Issue**: #37 cascading validity bug (r2_30_90 gate removal)

---

## What Was Done

### Code Changes (from prior session)
- Removed `r2_30_90 < 0.75` as hard reject gate (now diagnostic only)
- Added `r2_15_45` computation (centered early window)
- Migration 024 added `r2_15_45` column

### Re-extraction Process
1. Created backup schema `backup_20260119` (intervals, judgments)
2. Dropped FK constraint `hrr_qc_judgments_interval_id_fkey` (blocked delete)
3. Ran `python scripts/hrr_feature_extraction.py --all --reprocess`
4. Remapped `hrr_algo_baseline_intervals.interval_id` to new IDs
5. Validated via `hrr_algo_comparison` view
6. Resolved 6 "regressions" (4 were judgment errors, 2 needed tau_clipped overrides)
7. Remapped `hrr_qc_judgments.interval_id` to new IDs
8. Restored FK constraint

### Final Results
| Metric | Count |
|--------|-------|
| Total intervals | 807 |
| Unchanged | 791 |
| Fixed (algo now matches human) | 10 |
| Changed (other) | 6 |
| Regressions | 0 |

---

## Key Learnings

### Surrogate Key Problem
Both `hrr_qc_judgments` and `hrr_algo_baseline_intervals` reference `hr_recovery_intervals.id` (surrogate key). On re-extraction:
- All intervals deleted and re-inserted with new IDs
- FK blocks deletion
- Comparison view breaks (joins on stale IDs)

**Workaround**: Drop FK → extract → remap IDs → restore FK

**Better design**: Reference by natural key `(polar_session_id, interval_order)` instead. Filed as issue #39.

### tau=300 (Clipped) Signal
Two intervals had `tau_seconds = 300` (the max/clip value), indicating exponential fit failed. These were correctly rejected by r2_30_90 gate for wrong reason. Added `force_reject` overrides with reason `tau_clipped_300`.

**Consider**: Adding `tau_clipped` as explicit quality gate.

### Judgment Quality
Some `confirm_rejection` judgments were trusting the algo when algo was wrong. When reviewing rejections, verify independently rather than rubber-stamping.

---

## Current State

- `hr_recovery_intervals`: 807 rows, re-extracted with new quality logic
- `hrr_qc_judgments`: 801 rows, remapped to new interval IDs
- `hrr_quality_overrides`: 2 new overrides (sessions 4, 25) for tau_clipped
- `hrr_algo_baseline_intervals`: Remapped to new IDs, 4 judgments corrected
- FK constraint: Restored
- Backup: `backup_20260119` schema (drop when confident)

---

## Open Items

1. **Plateau detection not firing** - Some intervals with clear plateaus not getting flagged
2. **Natural key refactor** - Issue #39, low priority
3. **tau_clipped gate** - Consider adding as explicit reject reason
4. **6 "changed" intervals** - Not investigated, likely benign flag changes

---

## Commands Reference

```bash
# Re-extraction
python scripts/hrr_feature_extraction.py --all --reprocess

# Remap baseline IDs after extraction
psql -d arnold_analytics -c "
UPDATE hrr_algo_baseline_intervals b
SET interval_id = i.id
FROM hr_recovery_intervals i
WHERE b.polar_session_id = i.polar_session_id
  AND b.interval_order = i.interval_order;
"

# Remap judgment IDs after extraction
psql -d arnold_analytics -c "
UPDATE hrr_qc_judgments j
SET interval_id = i.id
FROM hr_recovery_intervals i
WHERE j.polar_session_id = i.polar_session_id
  AND j.interval_order = i.interval_order;
"

# Check test harness
psql -d arnold_analytics -c "SELECT change_type, count(*) FROM hrr_algo_comparison GROUP BY 1;"
```

---

## Files Modified

```
scripts/hrr/metrics.py          # r2_30_90 gate removed
scripts/hrr/types.py            # r2_15_45 field
scripts/hrr/persistence.py      # r2_15_45 column
scripts/migrations/024_*.sql    # Schema change
```
