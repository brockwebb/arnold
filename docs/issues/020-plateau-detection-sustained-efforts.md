# Issue #020: Plateau Detection for Sustained Efforts

**Status**: Resolved  
**Created**: 2026-01-16  
**Resolved**: 2026-01-17  
**Related**: #015 (double-peak detection), #021 (extended decay windows), #022 (modular refactor)

## Problem

Recovery intervals from sustained efforts (e.g., steady-state running, long intervals) often lack sharp HR peaks. The HR plateaus at working level then transitions smoothly into recovery. scipy.signal.find_peaks misses these because they lack "prominence" - the sharp spike that makes traditional peaks detectable.

### Example: Session 51 at 30:48

The HR trace shows:
- 30:00-30:48: HR plateau at 159-165
- 30:48: Peak at 165 bpm (no sharp spike, just end of plateau)
- 31:00-32:00: Decline from 165 → 141 (24 bpm drop)
- 32:00: Nadir at 141

This is a valid recovery interval (HRR60=22) but scipy missed it entirely.

## Root Cause

1. **scipy peak detection** requires prominence (sharp rise then fall). Plateaus that roll off don't trigger detection.
2. **Initial valley approach** looked back 5 minutes and used `argmax` to find the peak - this grabbed older, irrelevant peaks (like 29:07 at 168) instead of the most recent local maximum.

## Solution

### Valley-Based Peak Discovery

Complement scipy peak detection by working backwards from valleys:

1. Find all valleys (local HR minima) using `scipy.signal.find_peaks(-hr_smooth)`
2. For each valley, look back within a configurable window (default 2 min)
3. Find **local peaks** in the lookback window using low-prominence peak detection
4. Use the **most recent** local peak (not absolute max) as the recovery start
5. Validate: peak must be elevated above RHR, drop must exceed minimum threshold

### Key Insight

The fix was finding the **most recent local peak** before the valley, not the absolute maximum in the lookback window. This correctly identifies the end of the current effort rather than grabbing noise from previous intervals.

### Configuration (config/hrr_extraction.yaml)

```yaml
valley_detection:
  lookback_window_sec: 120     # How far back to search for peak before valley
  min_drop_bpm: 12             # Minimum HR drop from peak to valley
  valley_prominence: 10        # Prominence for finding valleys
  valley_distance_sec: 60      # Minimum seconds between valleys
  local_peak_prominence: 5     # Prominence for local peaks in lookback window
  local_peak_distance_sec: 10  # Distance between local peaks
```

### Integration

Valley detection feeds candidates into the same pipeline as scipy:

1. `detect_peaks()` - scipy method (primary)
2. `detect_valley_peaks()` - valley method (complementary)
3. `merge_peak_candidates()` - dedupe within 30s, scipy takes priority
4. Same validation, quality gates, and feature extraction for all candidates

## Results

Session 51 before/after:
- Before: 14 intervals, 7 pass
- After: 18 intervals, 10 pass

New recoveries detected:
- **30:49** (peak 165, HRR60=22, R²=0.92) - the target plateau-to-decline
- **40:33** (peak 163, HRR60=21, R²=0.91) - another plateau pattern
- **110:45** (peak 146, HRR60=11, R²=0.92) - late session recovery

## Files Modified

- `scripts/hrr_feature_extraction.py` - Added `detect_valley_peaks()`, `merge_peak_candidates()`
- `config/hrr_extraction.yaml` - Added `valley_detection` section with tunable parameters
- `docs/issues/020-plateau-detection-sustained-efforts.md` - This document

## Verification

```bash
python scripts/hrr_feature_extraction.py --session-id 51 --dry-run
```

Look for interval at ~30:49 with peak 165 and HRR60 ~22.
