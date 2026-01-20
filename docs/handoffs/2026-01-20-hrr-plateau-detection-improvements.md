# HRR Plateau Detection Improvements Handoff

**Date**: 2026-01-20  
**Thread**: Backward peak search and forward reanchoring enhancements  
**Status**: Code complete, pending regression testing and commit

---

## Summary

Implemented two complementary fixes for HRR peak detection failures:

1. **Backward peak search** - Catches gradual deceleration patterns where scipy detects the END of a plateau instead of the true peak
2. **Enhanced forward reanchoring trigger** - Now also triggers on `r2_15_45 < 0.5` to catch delayed plateau patterns that pass r2_0_30

Both validated with dry-run on Session 22. Ready for regression testing.

---

## GitHub Issues

| Issue | Title | Status | Action |
|-------|-------|--------|--------|
| #43 | Backward peak search for gradual deceleration patterns | Ready to close | Close after regression passes |
| #36 | Referenced in code comments (original issue for this pattern) | Verify if duplicate | May be duplicate of #43 |

---

## Files Modified

### `scripts/hrr/detection.py`

**1. Added `search_backward_for_true_peak()` function (lines ~22-65)**

Searches backward from scipy-detected peak to find true maximum HR:
- Lookback window: `config.backward_lookback_sec` (default 30s)
- Threshold: `config.backward_threshold_bpm` (default 3 bpm)
- Uses LAST occurrence of max (finds end of plateau, right before true decline)
- Adds `BACKWARD_SHIFTED` quality flag when triggered

**2. Enhanced forward reanchoring trigger (lines ~607-613)**

Now triggers on EITHER condition:
```python
r2_0_30_bad = interval.r2_0_30 is not None and interval.r2_0_30 < config.gate_r2_0_30_threshold
r2_15_45_bad = interval.r2_15_45 is not None and interval.r2_15_45 < config.gate_r2_0_30_threshold
if r2_0_30_bad or r2_15_45_bad:
```

- `r2_0_30 < 0.5` catches immediate plateau at interval start
- `r2_15_45 < 0.5` catches delayed plateau (starts OK, then stalls)

### `scripts/hrr/reanchoring.py`

**Changed method conflict resolution (lines ~115-125)**

When slope and geometry methods disagree significantly:
- **Before**: Averaged them (caused bad results when one method failed)
- **After**: Trust slope method (geometry's inflection point detection fails on long declining plateaus)

```python
else:
    # Large disagreement - trust slope method
    # Geometry uses inflection point detection which fails on long declining plateaus
    return offset_slope, 'medium', debug_info
```

### `scripts/hrr/cli.py`

**Added r2_15_45 to segment R² output table (lines ~90-114)**

- Widened table from 95 to 103 characters
- Added `15-45` column between `0-30` and `30-60`

### `scripts/hrr/metrics.py`

**Enhanced rejection reasons to include duration context**

- `insufficient_duration` → `insufficient_duration_45s`
- `no_valid_r2_windows` → `no_valid_r2_windows_45s`

Greatly improves debuggability when reviewing rejected intervals.

### `scripts/hrr/types.py`

**Added backward search config params**

```python
# Backward peak search (Issue #036 - gradual deceleration)
backward_lookback_sec: int = 30  # How far back to search for true peak
backward_threshold_bpm: int = 3  # Only shift if higher peak exceeds this delta
```

---

## Validation Results (Dry-Run)

### Session 22

**Interval 3 - Backward Search**
```
Backward search: peak 3 shifted from idx 1104 (HR=126) to idx 1080 (HR=133), delta=-24s
```
- Correctly identified true peak was 24s earlier
- Still rejected (r2_30_60 = 0.73, legitimate quality issue from 2bpm mid-recovery bump)
- ✅ Algorithm working, rejection is valid

**Interval 1 - Forward Reanchoring**
```
Interval 1: r2_15_45=0.133 < 0.5, attempting re-anchor
Interval 1: plateau detection - offset=141s, confidence=medium, slope=141s/slope_found, geom=0s/geometry_found
Interval 1: resolved: r2_0_30 0.845 -> 0.949, shifted +141s
```
- r2_15_45 trigger fired (r2_0_30 was 0.845, would have missed it)
- Slope method found 141s, geometry found 0s → trusting slope worked
- After shift: only 45s of clean recovery before activity resumed
- Rejected as `no_valid_r2_windows_45s` - correct, insufficient data for HRR60
- ✅ Algorithm working, rejection is valid

---

## Regression Testing Procedure

Per `/docs/testing.md` "HRR Re-extraction with FK Constraints" section:

### 1. Create Backup
```sql
CREATE SCHEMA backup_20260120;
CREATE TABLE backup_20260120.hr_recovery_intervals AS 
SELECT * FROM hr_recovery_intervals;
CREATE TABLE backup_20260120.hrr_qc_judgments AS 
SELECT * FROM hrr_qc_judgments;
```

### 2. Record Baseline Counts
```sql
SELECT 
    quality_status, 
    COUNT(*) 
FROM hr_recovery_intervals 
GROUP BY quality_status;
```

### 3. Unlock FK Constraint
```bash
psql -d arnold_analytics -c "
ALTER TABLE hrr_qc_judgments 
DROP CONSTRAINT hrr_qc_judgments_interval_id_fkey;"
```

### 4. Run Full Extraction
```bash
python scripts/hrr_feature_extraction.py --all --reprocess
```

### 5. Compare Counts
```sql
-- Summary comparison
SELECT 
    quality_status, 
    COUNT(*) 
FROM hr_recovery_intervals 
GROUP BY quality_status;

-- Check for regressions (human-verified intervals that changed)
SELECT 
    h.polar_session_id,
    h.interval_order,
    b.quality_status as old_status,
    h.quality_status as new_status,
    h.auto_reject_reason
FROM hr_recovery_intervals h
JOIN backup_20260120.hr_recovery_intervals b 
    ON h.polar_session_id = b.polar_session_id 
    AND h.interval_order = b.interval_order
WHERE h.quality_status != b.quality_status;
```

### 6. Verify Key Test Sessions

```bash
# Session 22 - both fixes validated
python scripts/hrr_qc_viz.py --session-id 22

# Sessions with human peak adjustments - verify not broken
python scripts/hrr_qc_viz.py --session-id 5   # +120s adjustment
python scripts/hrr_qc_viz.py --session-id 51  # +54s adjustment  
python scripts/hrr_qc_viz.py --session-id 70  # +60s adjustment
```

### 7. Remap Judgment IDs
```bash
psql -d arnold_analytics -c "
UPDATE hrr_qc_judgments j
SET interval_id = i.id
FROM hr_recovery_intervals i
WHERE j.polar_session_id = i.polar_session_id
  AND j.interval_order = i.interval_order;"
```

### 8. Relock FK Constraint
```bash
psql -d arnold_analytics -c "
ALTER TABLE hrr_qc_judgments 
ADD CONSTRAINT hrr_qc_judgments_interval_id_fkey 
FOREIGN KEY (interval_id) REFERENCES hr_recovery_intervals(id);"
```

### 9. Final Validation
```sql
SELECT 
    (SELECT count(*) FROM hr_recovery_intervals) as intervals,
    (SELECT count(*) FROM hrr_qc_judgments) as judgments,
    (SELECT count(*) FROM hrr_qc_judgments WHERE interval_id IS NULL) as orphaned;
```

### 10. Cleanup (only after confident)
```sql
DROP SCHEMA backup_20260120 CASCADE;
```

---

## Expected Outcomes

**Pass/Flagged/Rejected counts**: May shift slightly as:
- Some previously-rejected intervals might pass (better peak detection)
- Some edge cases might now be rejected (stricter with enhanced detection)

**Key validation**: Sessions with human peak adjustments (S5, S51, S70) should not regress.

---

## Commit Checklist

After regression passes:

- [ ] `git add scripts/hrr/detection.py scripts/hrr/reanchoring.py scripts/hrr/cli.py scripts/hrr/metrics.py scripts/hrr/types.py`
- [ ] `git add docs/hrr_quality_gates.md docs/testing.md`
- [ ] `git add docs/handoffs/2026-01-20-hrr-plateau-detection-improvements.md`
- [ ] `git commit -m "feat(hrr): backward peak search and enhanced reanchoring triggers (#43)"`
- [ ] Close Issue #43
- [ ] Verify Issue #36 status (may be duplicate)

---

## Documentation Updated

- `/docs/hrr_quality_gates.md` - Added backward search section, r2_15_45 trigger, method conflict resolution
- `/docs/testing.md` - Updated S22 test case notes, enhanced rejection reasons
- `/docs/handoffs/2026-01-20-hrr-plateau-detection-improvements.md` - This file

---

## Architecture Notes

**Two failure modes, two fixes:**

| Pattern | scipy Behavior | Fix | Direction |
|---------|---------------|-----|-----------|
| Gradual deceleration | Detects END of plateau as "peak" | Backward search | Shift peak earlier |
| Delayed plateau | Detects peak OK, but decay stalls mid-interval | Forward reanchoring | Shift measurement window later |

**Why both exist:**
- Backward search: True peak HR was earlier than detected
- Forward reanchoring: Peak HR is correct, but exponential decay starts later

**Method trust hierarchy:**
- When slope and geometry agree (within 10s): Average them
- When they disagree significantly: Trust slope (geometry fails on declining plateaus)

---

## Questions for Next Thread

1. ~~Should we increase `backward_lookback_sec` from 30s to 60s? S22:I3's true peak was ~50s back but we only shifted 24s.~~
   **RESOLVED (2026-01-20)**: Increased to 60s after regression testing confirmed S22:I3 true peak was ~50s back.
2. Issue #36 vs #43 - consolidate or separate concerns?
3. Any other sessions known to have plateau issues worth spot-checking?

---

## Regression Testing Results (2026-01-20)

### Parameter Change
- `backward_lookback_sec`: 30 → 60 seconds

### Interval Count Changes
- **5 intervals removed** (109 → 104 total)
- All 5 were last-in-session intervals
- 4 of 5 were already rejected before the change
- Expected behavior: peak consolidation now merges these with earlier peaks

### Conclusion
The increased lookback correctly consolidates gradual deceleration patterns. The removed intervals were either already rejected or redundant last-in-session detections that are now properly merged with their true peaks.
