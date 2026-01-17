# Handoff: HRR QC Visualization Tool Enhancement

**Date**: 2026-01-17  
**From**: Issue #020 plateau detection session  
**Priority**: Medium  

## Context

The HRR feature extraction pipeline (`scripts/hrr_feature_extraction.py`) now produces rich diagnostic data:
- Segment R² values (r2_0_30, r2_30_60, r2_30_90, etc.)
- Late slope analysis (slope_90_120)
- Quality status (pass/flagged/rejected) with reasons
- Valley-detected peaks in addition to scipy peaks

The existing QC viz tool (`scripts/hrr_qc_viz.py`) needs enhancement to visualize this data for human review.

## Current State

The summary tables now show all intervals (including rejected) with:
- R² per segment with asterisk markers for values below threshold
- Slope values with `!` for definite activity resumption, `?` for borderline
- Quality status and rejection reasons

But the **graphical visualization** (`hrr_qc_viz.py`) hasn't been updated to match.

## Requested Enhancements

### 1. Show All Intervals (Not Just Passed)
Currently the viz may filter to only passed intervals. Show all with visual distinction:
- **Passed**: Normal color (green markers)
- **Flagged**: Yellow/orange markers
- **Rejected**: Red markers with rejection reason annotation

### 2. Segment R² Overlay
Add optional subplot or annotation showing R² quality per segment:
- Color-code the recovery curve segments by their R² value
- Or add a small inset showing R² bar chart for each interval

### 3. Peak Source Annotation
Mark whether each peak came from:
- `scipy` - traditional prominence-based detection
- `valley` - valley-based discovery (Issue #020)

This helps validate that valley detection is finding real recoveries.

### 4. Rejection Reason Display
For rejected intervals, show why:
- `double_peak` - r2_0_30 < 0.5
- `r2_30_60_below_0.75` - second segment failed
- `r2_30_90_below_0.75` - transition zone failed
- `activity_resumed` - slope_90_120 > 0.1
- `poor_fit_quality` - best R² < 0.75

### 5. Interactive Mode (Optional)
If using matplotlib interactive backend, allow clicking an interval to see detailed diagnostics.

## Files to Modify

- `scripts/hrr_qc_viz.py` - Main visualization script
- Possibly create `scripts/hrr_interval_detail.py` for single-interval deep dive

## Reference Data

Test with session 51 which has good variety:
- 18 intervals total
- 10 pass, 1 flagged, 7 rejected
- Mix of scipy and valley-detected peaks
- Various rejection reasons

```bash
python scripts/hrr_qc_viz.py --session-id 51
```

## Database Schema Reference

Key columns in `hr_recovery_intervals`:
```sql
-- Quality
quality_status      -- 'pass', 'flagged', 'rejected'
quality_flags       -- array: ['LATE_RISE', 'LOW_SIGNAL', etc.]
auto_reject_reason  -- why rejected

-- Segment R²
r2_0_30, r2_30_60, r2_0_60, r2_30_90, r2_0_90
r2_0_120, r2_0_180, r2_0_240, r2_0_300

-- Late slope
slope_90_120, slope_90_120_r2
```

## Related Issues

- #015: Double-peak detection (resolved) - added r2_0_30 gate
- #020: Plateau detection (resolved) - added valley-based discovery
- #021: Extended decay windows (open) - may add more data to visualize
