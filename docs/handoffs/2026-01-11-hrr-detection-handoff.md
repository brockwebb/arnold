# HRR Detection Algorithm Rewrite - Handoff

**Date:** 2026-01-11  
**Status:** Ready to implement  
**Goal:** Replace broken detection pipeline with simplified non-rising-run approach

---

## Context

The previous HRR detection pipeline (`hrr_feature_extraction.py`) failed after multiple iterations of threshold tuning. Core problems:

1. **Onset detection hunting for "catch-breath" phase** - added complexity, didn't converge
2. **Seven quality gates** - tuning one broke another
3. **Exponential fit as gatekeeper** - strength training doesn't produce clean exponential decay
4. **Wrong conceptual model** - trying to force clinical HRR onto non-clinical data

## The New Approach

**Detect contiguous non-rising HR runs, backtrack to peak, apply three simple gates.**

This came from parallel discussions with ChatGPT Health and Claude, converging on the same solution.

### Core Algorithm

```
1. Preprocess: resample to 1Hz → median(5s) → MA(5s)
2. Compute per-second diff: Δ[t] = HR[t] - HR[t-1]
3. Mark non-rising: non_rising = (Δ ≤ allowed_up_per_sec)
4. Find contiguous runs where non_rising == True and duration ≥ 60s
5. Backtrack from run start to find HR_peak within lookback window
6. Apply three gates:
   - Duration ≥ 60s (built into detection)
   - total_drop ≥ min_total_drop
   - peak_minus_rest ≥ low_signal_cutoff
```

### Device-Specific Parameters

Polar arm strap is the primary sensor. Use chest/arm strap parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `allowed_up_per_sec` | 0.1–0.3 bpm/s | Tight tolerance, good signal |
| `min_total_drop` | 5 bpm | Lower threshold, less noise |
| `lookback_local_max_s` | 10–30 s | Find peak before run start |
| `low_signal_cutoff` | 15–25 bpm | peak_minus_rest floor |
| `smoothing` | median(3) → MA(3) | Can be tighter than wrist |

Start with middle values: `allowed_up_per_sec=0.2`, `min_total_drop=5`, `lookback=20`, `low_signal=20`

---

## Data Situation

- **Source:** Polar arm strap via FIT files
- **Resolution:** 1-second HR samples
- **Sessions:** 60+ over past year, growing weekly
- **Location:** `hr_samples` table in Postgres (arnold_analytics)
- **Outcomes:** Ultrahuman HRV/sleep (next-day), session feeling rating (end of Polar session)

### Key Queries

```sql
-- Session count with HR data
SELECT COUNT(DISTINCT session_id) FROM hr_samples WHERE session_id IS NOT NULL;

-- Sample count per session (verify 1Hz)
SELECT session_id, COUNT(*) as samples, 
       MIN(sample_time) as start, MAX(sample_time) as end
FROM hr_samples 
WHERE session_id IS NOT NULL
GROUP BY session_id
ORDER BY start DESC
LIMIT 10;
```

---

## Files to Modify/Create

### Keep (reference)
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_per_peak.py` - ChatGPT's approach, useful reference
- `/Users/brock/Documents/GitHub/arnold/docs/hrr_research_protocol.md` - Full research context

### Replace
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_feature_extraction.py` - Current broken pipeline

### Create
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_detection.py` - New simplified detection
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_validate.py` - Visual validation (overlay plots)

---

## Implementation Steps

### Step 1: Minimal Detection Module

Write `hrr_detection.py` with:

```python
def detect_non_rising_intervals(hr_values, timestamps, config):
    """
    Find intervals where HR is non-rising for ≥60s.
    
    Returns list of dicts:
    {
        'run_start_idx': int,
        'run_end_idx': int,
        'peak_idx': int,
        'hr_peak': float,
        'hr_end': float,
        'total_drop': float,
        'duration_sec': int
    }
    """
```

Key implementation details:
- Apply smoothing first (median → MA)
- Use np.diff for per-second changes
- Find contiguous True runs in boolean array
- Backtrack to find local max before each run

### Step 2: Feature Computation

Compute features for each detected interval:

**Core features (always compute):**
- `HR_peak`, `HR_nadir`, `total_drop`
- `time_to_nadir`
- `HR_30s`, `HR_60s`, `HR_120s` (when available)
- `HRR30_abs`, `HRR60_abs`, `HRR120_abs`
- `peak_minus_rest` (local baseline from pre-peak window)
- `duration_seconds`

**Optional features (compute but don't gate on):**
- `tau`, `tau_r2` (exponential fit - diagnostic only)
- `HRR30_frac`, `HRR60_frac` (normalized)
- `ratio_30_60`
- Slopes, AUC

### Step 3: Visual Validation

Write `hrr_validate.py` to produce overlay plots:

- Full session HR trace
- Detected run boundaries (vertical lines)
- Peak markers
- HRR30/60/120 points annotated
- Save to `/tmp/hrr_session_{id}.png`

Run on 10-20 sessions, visually inspect all of them.

### Step 4: Iterate

If detection looks wrong:
- Adjust `allowed_up_per_sec` (too tight = misses intervals, too loose = false positives)
- Adjust smoothing (more smoothing = fewer micro-fluctuations triggering false ends)
- Check edge cases (very short rest periods, interrupted recoveries)

---

## What NOT to Do

1. **Don't add onset detection** - we tried this, it failed
2. **Don't gate on tau** - compute it, but don't reject intervals based on it
3. **Don't add more than 3 quality gates** - duration, drop, signal floor
4. **Don't integrate weather yet** - out of scope for Phase 1
5. **Don't build the ML pipeline yet** - detection first, modeling later

---

## Success Criteria

Phase 1 is done when:

- [ ] Detection runs on all Polar sessions without crashing
- [ ] Visual inspection of 20 sessions shows sensible interval boundaries
- [ ] Event yield: 3-8 intervals per strength session, 2-5 per endurance
- [ ] Features extracted and stored (or printed in dry-run)
- [ ] No complex gates, no onset detection, no threshold tuning death spiral

---

## Key Reference Documents

1. **Research protocol:** `/Users/brock/Documents/GitHub/arnold/docs/hrr_research_protocol.md`
   - Full scientific context, literature, value proposition
   - Sections 2-3 explain why we're doing this
   - Section 7 has the algorithm spec
   - Section 11 has validation strategy

2. **ChatGPT's approach:** `/Users/brock/Documents/GitHub/arnold/scripts/hrr_per_peak.py`
   - Alternative implementation using `find_peaks`
   - Useful for comparison, but we're using non-rising-runs approach

3. **Previous failed attempts:** `/Users/brock/Documents/GitHub/arnold/scripts/hrr_feature_extraction.py`
   - What NOT to do
   - Complex onset detection, 7 gates, threshold tuning hell

---

## Startup Prompt for New Thread

```
Read the handoff: /Users/brock/Documents/GitHub/arnold/docs/handoffs/2026-01-11-hrr-detection-handoff.md

Then skim the research protocol for context: /Users/brock/Documents/GitHub/arnold/docs/hrr_research_protocol.md (Sections 2, 3, 7)

Task: Implement the non-rising-run detection algorithm. Start with a minimal detection function, run on a few sessions, produce overlay plots for visual validation.

Key constraints:
- Polar arm strap data at 1-second resolution
- Three gates only: duration, total_drop, peak_minus_rest
- No onset detection, no tau gating
- Visual validation before any threshold tuning
```
