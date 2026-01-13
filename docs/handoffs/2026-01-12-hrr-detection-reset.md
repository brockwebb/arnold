# HRR Detection - Algorithm Reset Handoff

**Date:** 2026-01-12
**Status:** Algorithm fundamentally broken, needs fresh approach
**Previous Handoff:** `/Users/brock/Documents/GitHub/arnold/docs/handoffs/2026-01-11-hrr-detection-handoff.md`

## Summary

Multiple iterations of HRR detection have failed. The current implementation in `hrr_sliding_v2.py` has accumulated technical debt and the algorithm doesn't reliably detect valid recovery intervals. Time to step back and rethink.

## The Core Problem

We're trying to detect heart rate recovery (HRR) intervals from real-world training data where:
- Athlete stops exertion → HR drops → we measure HRR60 (drop at 60s) and HRR120 (drop at 120s)
- Unlike clinical settings, real-world data has: double-peaks, plateaus (active recovery), gradual climbs, sensor noise

## What We Tried (All Failed or Problematic)

1. **Non-rising-run detection** - Too sensitive to noise
2. **Peak-first with scipy prominence** - Produced overlapping regions
3. **Grid search parameter tuning** - Found parameters but algorithm still flawed
4. **Sliding window with gates** - Current approach, accumulated too many band-aids

## Current Script Location

```
/Users/brock/Documents/GitHub/arnold/scripts/hrr_sliding_v2.py
```

## Current Algorithm (Broken)

```
0a. Peak must be higher than preceding lookback avg
0b. t=0 must be max in lookahead window (catch double-peaks)
1. First 7s must be mostly negative
2. Check 60s window: can't exceed nadir by > max_rise_60
3. If 60s passes, check 61-120s with max_rise_120
4. Return fixed 60s or 120s intervals only
```

**Why it's broken:**
- Gate 0a fails on gradual climbs (lookback avg catches up to peak)
- Gate 0b with 15s lookahead is arbitrary, doesn't always catch double-peaks
- Rise tolerance was HARDCODED (now fixed to 999 defaults but algorithm still wrong)
- Plateau detection never really worked
- Too many interdependent parameters that don't map to intuition

## Key Test Case: Session 31

```bash
python scripts/hrr_sliding_v2.py --session-id 31 --debug-range "12-16,74-77"
```

**Known issues in Session 31:**
- ~13 min: Has a double-peak that keeps getting detected wrong
- ~75 min: Clean recovery (139→83 bpm) that should be detected but isn't
- Many false rejections due to gate 0a (gradual climbs)

## Data Access

```python
# Load session from Postgres
import psycopg2
conn = psycopg2.connect('postgresql://brock@localhost:5432/arnold_analytics')

query = """
    SELECT sample_time, hr_value
    FROM hr_samples
    WHERE session_id = %s
    ORDER BY sample_time
"""
# 61 sessions available, 1-second resolution HR data
```

## What a Good Algorithm Should Do

User's intuition (from conversation):
> "Peak → descent → nadir. Just slide a window."
> "Any time we are above the observed local min for more than N seconds, it should end - plateaus represent breathers in middle of a set"

**Fixed windows only:** Report HRR60 (60s) or HRR120 (120s) - no variable lengths.

## Measurement Properties (from calibration)

- Instrument noise: 0.438 bpm (Polar arm strap)
- This is low - most variation is biological, not sensor noise

## Suggested Fresh Approach

Instead of layered gates, consider:

1. **Find ALL local maxima** (peaks) with some minimum prominence
2. **For each peak, simulate forward:**
   - Track the minimum HR seen so far (running nadir)
   - At t=60s, record HRR60 = peak - HR[t=60]
   - At t=120s, record HRR120 = peak - HR[t=120]
3. **Quality filter after detection:**
   - Reject if total_drop < 9 bpm
   - Reject if peak wasn't meaningfully above baseline
4. **Handle double-peaks:** If a higher peak exists within N seconds, skip to it

The key insight: **detect first, filter later** - not gate everything upfront.

## Files

**Current (broken):**
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_sliding_v2.py`

**Previous iterations (reference only):**
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_pipeline.py`
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_peak_first.py`
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_sensitivity.py`
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_calibration.py`

**Transcript of this session:**
- `/mnt/transcripts/2026-01-12-13-58-07-hrr-sliding-window-v2-progressive-tolerance.txt`

## Anti-Patterns Learned

1. **NO HARDCODING** - All parameters in Config dataclass with CLI exposure
2. **Don't accumulate band-aids** - If algorithm needs 5+ special cases, it's wrong
3. **Test with visual feedback** - The plot is the ground truth
4. **Debug output must show actual config** - Silent parameter ignoring wasted hours

## To Start New Thread

```bash
# Orient yourself
cat /Users/brock/Documents/GitHub/arnold/docs/handoffs/2026-01-12-hrr-detection-reset.md

# See current broken state
python scripts/hrr_sliding_v2.py --session-id 31

# View the data
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://brock@localhost:5432/arnold_analytics')
cur = conn.cursor()
cur.execute('SELECT COUNT(*), MIN(sample_time), MAX(sample_time) FROM hr_samples WHERE session_id = 31')
print(cur.fetchone())
"
```

## User Preferences

- Substance over praise
- No hardcoding - everything configurable
- Simple algorithms that match visual intuition
- Fixed 60/120s windows only
- Batch-by-batch verification, not bulk automation
