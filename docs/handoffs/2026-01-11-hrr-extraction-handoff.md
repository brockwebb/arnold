# HRR Feature Extraction - Handoff Document
## Date: 2026-01-11
## Status: NEEDS RETHINK - Results degrading

---

## What We Were Trying To Do

Implement FR-004: Heart Rate Recovery (HRR) feature extraction from per-second HR data captured during strength training sessions. Goal is to detect recovery intervals after effort peaks and compute metrics like HRR60 (HR drop in 60 seconds) and tau (exponential decay time constant).

## The Core Problem

Strength training HR patterns differ fundamentally from clinical HRR tests:
- **Clinical test**: Treadmill stops → immediate exponential decay
- **Strength training**: Set ends → "catch-breath" plateau (10-90+ seconds) → then decay → then HR rises for next set

Our intervals are V-shaped dips between efforts, not sustained exponential decays.

---

## What We Implemented

### 1. Basic Detection (`hrr_feature_extraction.py`)
- Peak detection using scipy.signal.find_peaks
- Sustained effort verification before peak
- Decline interval detection
- Feature computation (HRR30/60/90/120, tau, slopes, etc.)

### 2. Onset Detection (Dual-Method Ensemble)
Two methods to find where real recovery starts after catch-breath:
- **Max HR method**: Find highest HR in first N seconds
- **Sliding window method**: Find 60s window with maximum drop

Agreement scoring: high (≤5s), medium (≤15s), low (>15s)

### 3. Quality Filtering
Multiple gates tried:
- Minimum samples
- Low signal (hr_reserve < 25)
- Minimum HRR60 drop (≥5 bpm)
- Persistence (hr_60s near nadir)
- Valid tau fit OR recovery ratio

---

## What Went Wrong

### Problem 1: Interval boundaries wrong
Intervals extended past nadir into the climb. Fixed by ending at nadir instead of when rise detected, but this broke other things.

### Problem 2: Onset detection "reaching"
Sliding window searches entire interval, finds 60s drops deep into the data (onset=96s, 187s with low confidence). These aren't real recoveries - just any downward slope.

### Problem 3: ChatGPT validator mismatch
Tried integrating ChatGPT's robust validator (trend + magnitude + persistence + fit gates), but it computes features differently than our pipeline. Double-computed features with conflicting assumptions led to 0 valid intervals, then wrong tuning.

### Problem 4: Threshold tuning death spiral
Each fix broke something else. Lowered thresholds → bad intervals pass. Raised thresholds → good intervals rejected. No stable equilibrium found.

---

## Key Insights from ChatGPT Health Analysis

### Their Core Recommendation
Don't treat whole session as one event. Use **per-peak segmentation**:
1. find_peaks with prominence filter
2. For each peak, find the following trough (min HR before next peak)
3. Evaluate recovery on that peak→trough pair
4. Apply ensemble gates (trend + magnitude + persistence + fit) per pair

### Their Parameter Suggestions
- `prominence=6-8 bpm` (filter micro-peaks)
- `min_distance=20-40s` between peaks
- `max_trough_search=120-240s`
- Use **local** HR_rest (median of 60-180s before peak), not global RHR

### Their Key Point
> "Walk breaks and interval breaks create repeated peak/trough cycles — evaluating each pair independently uses local context (local peak, local trough) instead of a misleading global baseline."

---

## Current File State

### Modified Files
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_feature_extraction.py` - Main pipeline, currently broken
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_visualize.py` - Visualization with beeswarm distribution
- `/Users/brock/Documents/GitHub/arnold/scripts/hrr_drop_detection.py` - ChatGPT's validator (unused now)

### The Last Working-ish State
Before the final "end at nadir" change, we had ~9 valid intervals but some were questionable. The UNRELIABLE_ONSET gate (onset > 60s with low confidence) was helping.

---

## Recommended Path Forward

### Option A: Adopt ChatGPT's per_peak_drops Approach
Replace our detection entirely with their approach:
- Simpler: peak → trough pairs, evaluate each
- Local context: doesn't assume global RHR
- All-in-one: detection and validation together

Code is in the transcript and in uploaded documents.

### Option B: Fix Our Pipeline Incrementally
1. **Revert detect_decline_interval** to track current_min not nadir
2. **Tighten onset limits**: max 45-60s, reject low confidence > 30s
3. **Require valid tau < 150s** (not 200 or 300)
4. **Add shape validation**: after onset, HR must actually decline monotonically for at least 30s

### Option C: Simplify Radically
- Don't try to find "real" recovery start
- Just measure peak → nadir for each V-dip
- Report total_drop and time_to_nadir
- Accept that strength training doesn't produce clean HRR curves

---

## Test Commands

```bash
# Dry run with verbose
python scripts/hrr_feature_extraction.py --session-id 1 --source endurance --dry-run -v

# Visualize
python scripts/hrr_visualize.py --session-id 1 --source endurance --output /tmp/hr_session_1.png

# Distribution plot
python scripts/hrr_visualize.py --session-id 1 --source endurance --dist --output /tmp/hrr60_dist.png
```

---

## Key Files to Review

1. **Transcript**: `/mnt/transcripts/2026-01-11-20-35-22-hrr-onset-detection-ensemble.txt`
2. **ChatGPT per_peak_drops code**: In document index 6 from this conversation
3. **ChatGPT robust validator**: `/Users/brock/Documents/GitHub/arnold/scripts/hrr_drop_detection.py`

---

## Questions to Answer in Next Thread

1. Is HRR even the right metric for strength training? Maybe time_to_nadir and total_drop are more meaningful.
2. Should we abandon onset detection and just measure peak → nadir?
3. Do we need to separate "endurance" sessions (hiking with breaks) from true strength sessions?
4. What's the minimum viable feature set for FR-004?
