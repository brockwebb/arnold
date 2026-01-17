# Handoff: HRR Quality Gates Complete, QC and Import Next

**Date:** 2026-01-17  
**Status:** Quality gates implemented and validated

---

## Completed This Session

### Quality Gate Refinements
- Removed `r2_delta` metric (redundant with direct `r2_30_60` gate)
- Removed `quality_score` composite (replaced with explicit `auto_reject_reason`)
- Added `--quiet` flag for batch processing
- Fixed numpy type serialization for postgres
- Fixed postgres array format for `quality_flags`

### Final Quality Gate Architecture

**Hard Reject Criteria (stored in `auto_reject_reason`):**
| Gate | Metric | Threshold | Reason |
|------|--------|-----------|--------|
| 1 | slope_90_120 | > 0.1 bpm/sec | `activity_resumed` |
| 2 | best_r2 | None | `no_valid_r2_windows` |
| 3 | best_r2 | < 0.75 | `poor_fit_quality` |
| 4 | r2_30_60 | < 0.75 | `r2_30_60_below_0.75` |
| 5 | r2_30_90 | < 0.75 | `r2_30_90_below_0.75` |

**Flag Criteria (human review):**
- `LATE_RISE`: 0 < slope_90_120 ≤ 0.1
- `ONSET_DISAGREEMENT`: onset_confidence == 'low'
- `LOW_SIGNAL`: hr_reserve < 25 bpm

### Data Processed
```
Total intervals: 761
Sessions: 63
Pass: 260 (34%)
Rejected: 481 (66%)
Flagged for review: 20
```

Reject breakdown:
- `no_valid_r2_windows`: 262 (too short)
- `r2_30_60_below_0.75`: 117 
- `r2_30_90_below_0.75`: 79
- `poor_fit_quality`: 23

### Human Verification Workflow Tested
Used `verify_hrr_interval()` function successfully:
- ID 1396 (session 5, peak 3): excluded as `plateau_during_recovery`
- ID 1400 (session 5, peak 7): excluded as `double_peak`

---

## Known Issue

**Double-Peak Detection** - see `docs/issues/015-hrr-double-peak-detection.md` (Issue #015)

Peaks can be detected within another interval's window. Example: session 5 peaks 7 & 8 are 19 seconds apart with same HR. Need to add overlap check during validation.

---

## Database State

### Peak Timestamps Confirmed
`start_time` and `end_time` are stored for every interval:
```sql
SELECT start_time, end_time, duration_seconds FROM hr_recovery_intervals LIMIT 1;
```
This data is sufficient for implementing double-peak detection.

### Key Tables
- `hr_recovery_intervals`: All interval data with quality assessment
- `hr_samples`: Unified HR samples (source: polar_api, suunto_fit)
- Views: `hrr_review_queue`, `hrr_verified_clean`

### Verification Function
```sql
SELECT verify_hrr_interval(
    p_interval_id,      -- interval ID
    p_status,           -- 'confirmed', 'overridden_pass', 'overridden_fail'
    p_notes,            -- review notes
    p_exclude,          -- boolean: exclude from analytics
    p_exclusion_reason  -- reason code
);
```

---

## Next Steps

### 1. Complete QC of Flagged Intervals (20 remaining)
```sql
SELECT id, polar_session_id, interval_order, hr_peak, quality_flags 
FROM hr_recovery_intervals 
WHERE quality_status = 'flagged' AND human_verified = FALSE;
```

Use `hrr_qc_viz.py` to review each:
```bash
python scripts/hrr_qc_viz.py --session-id <N>
```

### 2. Fix Double-Peak Detection
Implement overlap check in `hrr_feature_extraction.py`:
- During peak validation, check if new peak falls within previous interval
- Auto-reject earlier peak as `double_peak`
- Reprocess all sessions with `--reprocess`

### 3. Import Historical Data
Priority order:
1. Suunto data (already have samples, need session linkage)
2. Garmin GPX/TCX logs
3. 20-year historical HRM data

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/hrr_feature_extraction.py` | Main extraction pipeline |
| `scripts/hrr_qc_viz.py` | Visual QC tool |
| `docs/hrr_quality_gates.md` | Gate documentation |
| `docs/issues/015-hrr-double-peak-detection.md` | Issue #015: Double-peak bug |
| `scripts/migrations/013_hr_recovery_intervals.sql` | Base schema |
| `scripts/migrations/017_hrr_quality_verification.sql` | QC fields |

---

## Commands Reference

```bash
# Process single session with output
python scripts/hrr_feature_extraction.py --session-id 71

# Process all sessions quietly
python scripts/hrr_feature_extraction.py --all -q --reprocess

# Visualize session for QC
python scripts/hrr_qc_viz.py --session-id 5

# Check flagged intervals
psql arnold_analytics -c "SELECT id, polar_session_id, interval_order, quality_flags FROM hr_recovery_intervals WHERE quality_status = 'flagged' AND human_verified = FALSE;"
```
