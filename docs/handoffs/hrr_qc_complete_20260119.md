# HRR QC Complete - Next Steps Handoff

**Date**: 2026-01-19  
**QC Status**: Complete (801/807 intervals human verified)

## QC Results Summary

| Metric | Count |
|--------|-------|
| Total Intervals | 807 |
| Passed | 240 (30%) |
| Rejected | 549 (68%) |
| Flagged | 18 (2%) |
| Human Verified | 801 (99%) |

### Rejection Reasons

| Reason | Count | Notes |
|--------|-------|-------|
| no_valid_r2_windows | 296 | Too short for 60s measurement |
| r2_30_60_below_0.75 | 193 | **167 have valid r2_0_60** → Issue #37 |
| r2_30_90_below_0.75 | 23 | Same issue |
| double_peak | 20 | Correct rejections |
| poor_fit_quality | 17 | Correct rejections |

## Open Issues (Priority Order)

### 1. Issue #37 - Cascading Validity (HIGH PRIORITY)
**Impact**: Recovers **167 intervals** with valid HRR60 (avg 13.4 bpm)

Current logic rejects entire interval when downstream segments fail. Should keep HRR60 if r2_0_60 ≥ 0.75, regardless of r2_30_60 or r2_30_90.

**Fix**: 
- Add `hrr60_valid`, `hrr120_valid`, etc. columns
- Change rejection logic: only reject if r2_0_60 < 0.75
- Segment checks become flags, not hard rejects

**Effort**: Medium (logic change + schema)

---

### 2. Issue #38 - Missing Peak Detection (HIGH PRIORITY)
**Impact**: Unknown number of recoveries not detected at all

Large gaps between detected intervals (3-6 minutes) contain visible peaks. Detection filters too aggressive.

**Investigation needed**:
- Query HR during gap periods
- Identify which filter rejects them
- Tune prominence/distance/elevation thresholds

**Effort**: Medium-High (requires investigation + tuning)

---

### 3. Issue #36 - Backward Peak Search (MEDIUM)
**Impact**: Peaks detected at wrong position for gradual deceleration

When athlete slows down over 30+ seconds, scipy finds local max at END of deceleration, missing true peak.

**Tracking cases**: S22:I3 (-50s), S33:I11 (-30s)

**Fix**: Search backward from detected peak for higher HR values

**Effort**: Medium (new detection function)

---

### 4. Issue #35 - r2_0_60 Gate (LOW - may be superseded)
**Impact**: Some intervals with poor 0-60s fit slip through

If Issue #37 is implemented correctly, r2_0_60 becomes the primary gate and this may be redundant.

**Effort**: Low (one-line change)

---

### 5. Issue #33 - NULL R² Bypass (FIXED)
Changed `return None` to `return -1.0` in `compute_segment_r2()`. Sentinel value triggers existing `< 0.75` check.

---

## Execution Plan

### Phase 1: Baseline Snapshot
```sql
CREATE TABLE hrr_baseline_20260119 AS 
SELECT id, polar_session_id, interval_order, quality_status, 
       auto_reject_reason, hrr60_abs, r2_0_60, r2_30_60
FROM hr_recovery_intervals;
```

### Phase 2: Fix #37 (Cascading Validity)
1. Add schema columns
2. Update `assess_quality()` in `metrics.py`
3. Reprocess all sessions
4. Diff against baseline - expect ~167 recoveries, 0 regressions

### Phase 3: Investigate #38 (Missing Peaks)
1. Query gaps in S15, find raw HR peaks
2. Run detection with logging to see what filters reject them
3. Tune thresholds or add sweep-based detection
4. Reprocess, verify new detections are valid

### Phase 4: Fix #36 (Backward Search)
1. Implement `search_backward_for_true_peak()`
2. Add to `extract_features()` pipeline
3. Verify S22:I3 and S33:I11 shift correctly
4. Reprocess, check for improvement

### Phase 5: Cleanup
1. Reassess #35 (may be redundant)
2. Update documentation
3. Remove temp tracking files

## Verification Queries

```sql
-- After each fix, run diff:
SELECT 
    CASE 
        WHEN b.quality_status = 'rejected' AND h.quality_status = 'pass' THEN 'recovered'
        WHEN b.quality_status = 'pass' AND h.quality_status = 'rejected' THEN 'REGRESSED'
        ELSE 'unchanged'
    END as change,
    COUNT(*)
FROM hr_recovery_intervals h
JOIN hrr_baseline_20260119 b USING (id)
GROUP BY 1;

-- Verify no passing intervals regressed:
SELECT b.polar_session_id, b.interval_order, b.hrr60_abs
FROM hr_recovery_intervals h
JOIN hrr_baseline_20260119 b USING (id)
WHERE b.quality_status = 'pass' AND h.quality_status = 'rejected';
```

## Use Cases Documented

- `docs/examples/hrr-use-case-activity-resumed.md` - S23:I9, correctly rejected when activity resumed mid-recovery

## Files to Clean Up

- `docs/hrr_peak_adjustment_candidates.md` - delete (query negative peak_shift instead)

## Related Documentation

- `docs/hrr_quality_gates.md` - needs update after #37
- `scripts/hrr/metrics.py` - assess_quality() is the target for #37
- `scripts/hrr/detection.py` - target for #36, #38
