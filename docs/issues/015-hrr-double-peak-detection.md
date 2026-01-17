# Issue #015: Double-Peak Detection in HRR Extraction

**Created:** 2026-01-17  
**Closed:** 2026-01-17  
**Priority:** High  
**Status:** CLOSED  
**Component:** `scripts/hrr_feature_extraction.py`, `config/hrr_extraction.yaml`

## Problem

The peak detection algorithm identified two peaks within the same recovery interval, resulting in duplicate/overlapping intervals. Also, R² was computed from scipy's peak detection point rather than the true max HR, causing good recoveries to fail the r2_0_30 gate.

**Example from session 5:**
- Peak 7: starts 20:13:35, HR=169, duration=233s
- Peak 8: starts 20:13:54, HR=169, duration=214s

These are only 19 seconds apart with identical peak HR. Peak 7 is a false detection - Peak 8 is the true recovery start.

## Root Cause

1. **argmax returns first occurrence:** When HR plateaus at max (e.g., `[168, 168, 168, 168, 167, 166...]`), `np.argmax()` returns index 0, but exponential decay doesn't start until the plateau ends.

2. **R² computed from wrong start point:** The segment R² values were computed from scipy's detection point, not the onset-adjusted true max HR.

3. **No overlap detection:** When onset adjustment shifted one peak forward, it could collapse onto the next peak with no rejection.

## Solution Implemented

### 1. Last-occurrence max HR detection
Changed `detect_onset_maxhr()` to find the **last** occurrence of max HR, catching the end of plateaus:
```python
max_hr = max(hr_values)
max_indices = [i for i, hr in enumerate(hr_values) if hr == max_hr]
max_hr_idx = max_indices[-1] if max_indices else 0
```

### 2. Onset-adjusted R² computation
In `extract_features()`, R² is now computed from the onset-adjusted start:
```python
onset_offset = interval.onset_delay_sec or 0
adjusted_start_idx = peak_idx + onset_offset
interval_samples = samples[adjusted_start_idx:end_idx + 1]
```

### 3. Overlap detection gate
After all intervals are built, reject any interval whose adjusted start overlaps the next:
```python
if curr.start_time >= next_int.start_time:
    curr.quality_status = 'rejected'
    curr.auto_reject_reason = 'overlap_duplicate'
```

### 4. YAML config system
Created `config/hrr_extraction.yaml` with configurable gates, thresholds, and flags.

### 5. ONSET_ADJUSTED flag
Flag intervals with onset adjustment > 15 seconds for review (small adjustments are normal).

## Results

Before fix:
- 70% rejection rate (r2_0_30 gate catching plateaus as "double peaks")

After fix:
- 60% pass, 37% reject, 2% flagged
- Rejection breakdown:
  - r2_30_60_below_0.75: 95
  - r2_30_90_below_0.75: 62
  - double_peak: 51 (r2_0_30 < 0.5, still useful as secondary)
  - overlap_duplicate: 32 (new gate)
  - poor_fit_quality: 23
  - no_valid_r2_windows: 20

## Files Changed

- `scripts/hrr_feature_extraction.py` - onset detection, R² computation, overlap gate
- `config/hrr_extraction.yaml` - new config file

## Known Limitations

**Plateau detection for sustained efforts:** Scipy's `find_peaks` requires prominence (spike above surroundings). When HR is sustained at high level then gradually rolls off (common in running), no peak is detected. This is a separate issue - see Issue #020.

## Acceptance Criteria

- [x] No two intervals from same session have overlapping time windows
- [x] When double-peak detected, flag with `auto_reject_reason = 'overlap_duplicate'`
- [x] R² computed from onset-adjusted start point
- [x] Reprocess existing sessions
