# HRR QC Review Session Handoff

**Date:** 2026-01-17
**Status:** In Progress - QC Review Workflow Established

---

## Summary

Established complete HRR quality control workflow with manual peak adjustments, interval-level reviews, and session-level tracking. Fixed critical bug where short intervals (<60s) were incorrectly passing quality gates.

---

## What Was Done This Session

### 1. Bug Fix: Insufficient Duration Pass-Through

**Problem:** Intervals with duration < 60s were passing quality gates because:
- `r2_30_60` was NULL (no data), not failing
- `best_r2` included `r2_0_30`, so short intervals got good scores
- No HRR60 data, but marked as "pass"

**Fix in `hrr_feature_extraction.py`:**
```python
# Gate 0: Insufficient duration - can't compute HRR60
if interval.r2_0_60 is None:
    hard_reject = True
    reject_reason = 'insufficient_duration'
```

Also removed `r2_0_30` from `best_r2` calculation.

### 2. Peak Adjustments Table (Migration 018)

For false peak detection where scipy anchors on plateau:

```sql
CREATE TABLE peak_adjustments (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    interval_order SMALLINT NOT NULL,
    shift_seconds SMALLINT NOT NULL,  -- positive = shift later
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,
    UNIQUE(polar_session_id, interval_order)
);
```

**Current adjustments:**
| Session | Peak | Shift | Reason |
|---------|------|-------|--------|
| 51 | 3 | +54s | False peak |
| 5 | 10 | +120s | Plateau anchor |

### 3. Interval-Level Reviews Table (Migration 019)

For human review decisions at granular level:

```sql
CREATE TABLE hrr_interval_reviews (
    id SERIAL PRIMARY KEY,
    interval_id INTEGER REFERENCES hr_recovery_intervals(id),
    review_action VARCHAR(30),  -- flags_cleared, peak_shift_verified, accepted, rejected_override
    original_flags TEXT[],
    notes TEXT,
    reviewed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(interval_id, review_action)
);
```

**Helper view:** `hrr_review_status`

### 4. Session-Level QC Tracking

Added to `polar_sessions`:
- `hrr_qc_status` VARCHAR(20) - pending, reviewed, needs_reprocess
- `hrr_qc_reviewed_at` TIMESTAMPTZ

---

## Current Review Status

**Sessions reviewed:** 2 of 65
- Session 5 (2025-06-17) - STRENGTH_TRAINING - ✅ reviewed
- Session 51 (2025-07-27) - RUNNING - ✅ reviewed

**Interval reviews recorded:**
| Session | Peak | Action | Notes |
|---------|------|--------|-------|
| 5 | 6 | flags_cleared | ONSET flags OK - R² excellent |
| 5 | 8 | flags_cleared | ONSET flags OK - R² excellent |
| 5 | 10 | peak_shift_verified | Shifted 120s - corrected |
| 51 | 3 | peak_shift_verified | Shifted 54s - false peak corrected |

---

## QC Workflow

### 1. Visualize Session
```bash
python scripts/hrr_qc_viz.py --session-id <N>
```

### 2. For False Peaks (plateau anchor, r2_30_60 garbage)
```sql
INSERT INTO peak_adjustments (polar_session_id, interval_order, shift_seconds, reason)
VALUES (<session>, <peak>, <seconds>, 'reason');
```
Then reprocess:
```bash
python scripts/hrr_feature_extraction.py --session-id <N>
```

### 3. For Informational Flags (ONSET_DISAGREEMENT with good R²)
```sql
INSERT INTO hrr_interval_reviews (interval_id, review_action, original_flags, notes)
SELECT id, 'flags_cleared', quality_flags, 'ONSET flags OK - R² excellent'
FROM hr_recovery_intervals
WHERE polar_session_id = <N> AND interval_order IN (...);
```

### 4. Verify Peak Shifts
```sql
INSERT INTO hrr_interval_reviews (interval_id, review_action, original_flags, notes)
SELECT id, 'peak_shift_verified', quality_flags, 'Shift confirmed correct'
FROM hr_recovery_intervals
WHERE polar_session_id = <N> AND interval_order = <peak>;
```

### 5. Mark Session Complete
```sql
UPDATE polar_sessions 
SET hrr_qc_status = 'reviewed', hrr_qc_reviewed_at = NOW() 
WHERE id = <N>;
```

---

## Key Files Modified

- `scripts/hrr_feature_extraction.py` - Added insufficient_duration gate, peak adjustment loading
- `scripts/migrations/018_peak_adjustments.sql` - Peak adjustment table
- `scripts/migrations/019_hrr_interval_reviews.sql` - Interval review table + view
- `docs/hrr_quality_gates.md` - Full workflow documentation
- `docs/DATA_DICTIONARY.md` - Table schemas
- `docs/HANDOFF.md` - Updated HRR pipeline section

---

## Next Steps

1. **Continue QC review** - 63 sessions pending
   - Start with cleanest: Session 70 (Jan 10) - 11 pass, 0 flagged, 1 rejected
   - Or most recent: Sessions 68-71 (Jan 2026)

2. **Quick wins query:**
```sql
SELECT id, start_time::date, sport_type, 
       SUM(CASE WHEN quality_status = 'pass' THEN 1 ELSE 0 END) as pass,
       SUM(CASE WHEN quality_status = 'flagged' THEN 1 ELSE 0 END) as flagged,
       SUM(CASE WHEN quality_status = 'rejected' THEN 1 ELSE 0 END) as rejected
FROM polar_sessions p
JOIN hr_recovery_intervals i ON i.polar_session_id = p.id
WHERE hrr_qc_status = 'pending'
GROUP BY p.id, p.start_time, p.sport_type
HAVING SUM(CASE WHEN quality_status = 'flagged' THEN 1 ELSE 0 END) = 0
ORDER BY rejected ASC
LIMIT 10;
```

3. **Consider:** Batch-approve sessions with 0 flagged, low rejected, after spot-checking a few

---

## Commands Quick Reference

```bash
# Visualize
python scripts/hrr_qc_viz.py --session-id <N>

# Reprocess after adjustment
python scripts/hrr_feature_extraction.py --session-id <N>

# Reprocess all
python scripts/hrr_feature_extraction.py --all
```

---

## Documentation

- `/docs/hrr_quality_gates.md` - Complete workflow reference
- `/docs/DATA_DICTIONARY.md` - Table schemas
- `/docs/adr/005-hrr-pipeline-architecture.md` - Architecture decisions
