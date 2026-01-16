# HRR 5-Minute Extension - Implementation Handoff

## Context

Brock performed a deliberate HRR test on 2026-01-13:
- Tabata burpees → 171 bpm max HR (100% predicted max)
- 5-minute supine rest for recovery data
- Polar session 71 has full HR trace (2800 samples)

**Problem:** Current `hrr_batch.py` caps at 120s, discarding 3 minutes of data.

## What Needs to Be Done

### Phase 1: Extend the Algorithm (Do This First)

File: `scripts/hrr_batch.py`

1. **Change window cap from 120 to 300 seconds**
   - `extend_interval()` function: change `min(peak_idx + 121, n)` to `min(peak_idx + 301, n)`
   - Update `end_reason` logic for "reached_300"

2. **Add new metrics in `HRRInterval` dataclass:**
   ```python
   hr_at_180: Optional[float] = None
   hr_at_240: Optional[float] = None
   hr_at_300: Optional[float] = None
   hrr180: Optional[float] = None
   hrr240: Optional[float] = None
   hrr300: Optional[float] = None
   r2_180: Optional[float] = None
   r2_240: Optional[float] = None
   r2_300: Optional[float] = None
   ```

3. **Extract features at new timepoints** in `extract_interval_features()`:
   ```python
   if peak_idx + 180 < n:
       interval.hr_at_180 = hr[peak_idx + 180]
       interval.hrr180 = peak_hr - hr[peak_idx + 180]
       # R² at 180s
       window_180 = hr[peak_idx:peak_idx + 181]
       r2_180, _, _ = fit_exponential(window_180)
       interval.r2_180 = round(r2_180, 3)
   # Similar for 240, 300
   ```

4. **Update tau fitting** - increase `TAU_UPPER_BOUND` from 300 to 600

5. **Update `write_intervals_to_db()`** - add new columns to INSERT

### Phase 2: Schema Migration

Create migration: `scripts/migrations/015_hrr_extended_window.sql`

```sql
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hr_180s INTEGER,
ADD COLUMN IF NOT EXISTS hr_240s INTEGER,
ADD COLUMN IF NOT EXISTS hr_300s INTEGER,
ADD COLUMN IF NOT EXISTS hrr180_abs INTEGER,
ADD COLUMN IF NOT EXISTS hrr240_abs INTEGER,
ADD COLUMN IF NOT EXISTS hrr300_abs INTEGER,
ADD COLUMN IF NOT EXISTS r2_180 NUMERIC(4,3),
ADD COLUMN IF NOT EXISTS r2_240 NUMERIC(4,3),
ADD COLUMN IF NOT EXISTS r2_300 NUMERIC(4,3);
```

### Phase 3: Test with Session 71

```bash
# Run migration
psql -d arnold_analytics -f scripts/migrations/015_hrr_extended_window.sql

# Reprocess all sessions (or just session 71 for testing)
python scripts/hrr_batch.py --write-db --clear-existing

# Visualize session 71
python scripts/hrr_qc_viz.py --session-id 71
```

Session 71 should now show:
- HRR60 ≈ 31 bpm (171 → 140)
- HRR120 ≈ 42 bpm (171 → 129)
- HRR180, HRR240, HRR300 populated
- Extended tau fit

### Phase 4: Protocol Classification (Future)

After Phase 1-3 work, add metadata layer:
- `protocol_type`: inter_set, walk_break, cooldown, deliberate_test
- `posture`: standing, walking, supine, seated
- `prior_*` context fields

Detection heuristics for `deliberate_test`:
- Duration ≥ 180s sustained non-rising
- Final 10 minutes of session
- Preceded by high-intensity (peak > 85% max)
- Reaches stable plateau

## Files to Modify

1. `scripts/hrr_batch.py` - main detection logic
2. `scripts/hrr_qc_viz.py` - visualization (may need updates for 5-min display)
3. `scripts/migrations/015_hrr_extended_window.sql` - new migration
4. `config/hrr_defaults.json` - may need new thresholds

## Issue Document

Full issue with rationale: `docs/issues/hrr-5min-extension.md`

## Test Data Available

- Session 71: 2800 HR samples, 46:39 duration
- Peak at 17:45:06-10 (171 bpm) during Tabata finale
- 5-min supine recovery immediately after
- Manual HRR calculations from transcript:
  - HRR60: 31 bpm
  - HRR120: 42 bpm
  - Recovery curve: 171 → 140 → 129 → 118 → 115 plateau

## Questions to Consider

1. Should `high_quality` flag require different R² thresholds for longer windows?
2. Should confidence scoring weight longer windows higher?
3. For EWMA/CUSUM trend detection, should 5-min tests get their own stratum?
