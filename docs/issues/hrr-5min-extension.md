# HRR Pipeline: Extend recovery window to 300s and add protocol classification

**Labels:** enhancement, analytics, HRR

## Problem

The current HRR detection pipeline (`hrr_batch.py`) caps recovery windows at 120 seconds:

```python
end_idx = min(peak_idx + 120, n - 1)
```

This means deliberate 5-minute recovery tests (like supine rest after Tabata) only capture HRR60/HRR120, discarding 3 minutes of valuable decay data.

### Evidence

Session 71 (2026-01-13): Tabata burpees → 5-min supine rest for HRR data collection
- Peak HR: 171 bpm (100% age-predicted max)
- Full 5-min recovery curve available in `hr_samples`
- Current pipeline only extracts first 2 minutes

## Proposed Solution: Hybrid Approach

### 1. Extend Recovery Window to 300s

Add HRR metrics at extended timepoints:
- `hr_at_180`, `hrr180_abs`
- `hr_at_240`, `hrr240_abs`  
- `hr_at_300`, `hrr300_abs`
- Extended tau fitting (increase `TAU_UPPER_BOUND` from 300 to 600)
- R² at 180s, 240s, 300s windows

Update `extend_interval()` to allow up to 300s:
```python
for t in range(peak_idx + 1, min(peak_idx + 301, n)):  # was 121
```

### 2. Add Protocol Classification (Metadata Layer)

Not all 5-min recoveries are equal. Add context for stratification:

**Protocol types:**
- `inter_set` - typical strength training rest (30-120s)
- `walk_break` - active recovery during endurance (variable)
- `cooldown` - end of session wind-down
- `deliberate_test` - controlled HRR measurement protocol

**Posture inference:**
- `standing` - default for inter-set
- `walking` - active recovery
- `supine` - deliberate test (lowest HR expected)
- `seated` - post-exercise rest

**Detection heuristics for deliberate tests:**
- Duration ≥ 180s sustained non-rising
- Occurs in final 10 minutes of session
- Preceded by high-intensity effort (peak HR > 85% max)
- HR reaches stable plateau (< 3 bpm variance over 60s)

### 3. Capture Pre-Recovery Context

Store what happened BEFORE the recovery interval:
- `prior_block_type` - warmup/main/finisher/conditioning
- `prior_exercise_type` - strength/HIIT/steady-state/mixed
- `prior_peak_hr` - highest HR in 5 min before recovery
- `prior_effort_duration` - how long was the effort phase
- `time_into_session` - minutes since session start

This enables questions like:
- "How does HRR differ after Tabata vs after heavy deadlifts?"
- "Does recovery improve as session progresses (warmup effect)?"

## Schema Changes

```sql
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS
    hr_180s INTEGER,
    hr_240s INTEGER,
    hr_300s INTEGER,
    hrr180_abs INTEGER,
    hrr240_abs INTEGER,
    hrr300_abs INTEGER,
    r2_180 NUMERIC(4,3),
    r2_240 NUMERIC(4,3),
    r2_300 NUMERIC(4,3),
    -- Protocol context
    protocol_type VARCHAR(20) DEFAULT 'inter_set',
    posture VARCHAR(20) DEFAULT 'standing',
    is_deliberate_test BOOLEAN DEFAULT FALSE,
    -- Pre-recovery context  
    prior_block_type VARCHAR(20),
    prior_exercise_type VARCHAR(20),
    prior_peak_hr INTEGER,
    prior_effort_duration_sec INTEGER,
    session_elapsed_minutes NUMERIC(5,1);
```

## Implementation Order

1. **Phase 1**: Extend window to 300s, add HRR180/240/300 metrics
2. **Phase 2**: Add protocol classification heuristics
3. **Phase 3**: Capture pre-recovery context
4. **Phase 4**: Update trend detection (EWMA/CUSUM) to stratify by protocol

## Test Case

Session 71 (2026-01-13) provides ideal validation:
- Tabata burpees (known HIIT protocol)
- 171 bpm peak (maximal effort)
- 5-min supine rest (deliberate test)
- Full HR trace available

Expected: Should detect as `deliberate_test`, `supine` posture, with complete HRR60→HRR300 curve.

## Related

- ADR-001: Data Layer Separation (this adds to analytics layer)
- `config/hrr_defaults.json` - thresholds may need extension
- `src/arnold/hrr/detect.py` - confidence scoring for extended windows
