# FR-004 HRR Feature Extraction - Handoff Document
**Date**: 2026-01-11
**Status**: In Progress - Visualization and Classification Updates

## What Was Done This Session

### 1. Schema Migration 013 Applied
- `hr_recovery_intervals` table created (40+ columns)
- `hr_recovery_session_summary` table created
- 6 indexes for query performance

### 2. Feature Extraction Script Created
**File**: `scripts/hrr_feature_extraction.py`
- Pattern-based interval detection (sustained elevation → monotonic decline)
- 20+ features per interval (absolute, normalized, decay dynamics, context)
- Exponential fit for tau with R² quality metric
- Database connection fixed to use `POSTGRES_DSN` env var

### 3. Classification System Implemented
Three-category classification:
- **Valid**: Passed all quality checks, real recovery signal
- **Noise**: Floor effect (hr_reserve < 25 bpm) - can't measure recovery meaningfully  
- **Rejected**: Had signal but insufficient recovery (hrr60 < 5 bpm or ratio < 10%)

Config thresholds in `HRRConfig`:
```python
min_hrr60_abs: int = 5  # Minimum absolute drop
min_recovery_ratio: float = 0.10  # At least 10% of available drop
low_signal_threshold_bpm: int = 25  # hr_reserve below this = noise
```

### 4. Visualization Script Created
**File**: `scripts/hrr_visualize.py`
- Full session plot with HR trace and interval shading
- Color coding: GREEN=valid, YELLOW=noise, RED/SALMON=rejected
- Shows pre-peak avg HR (red horizontal lines)
- Bottom panel shows HR rate-of-change
- Detail view for individual intervals with exponential fit overlay

### 5. Test Run Results
Session 1 (112-min steady run):
```
15 raw intervals detected
Most had hrr60_abs of 1-7 bpm (essentially noise)
tau=300s (capped) for most = flat decay, no real recovery
```
This is EXPECTED - a steady-state run doesn't have true recovery intervals.

## Files Modified/Created

```
scripts/hrr_feature_extraction.py  # Main pipeline (UPDATED - 3-category filter)
scripts/hrr_visualize.py           # Visualization tool (CREATED)
scripts/migrations/013_hr_recovery_intervals.sql  # Schema (APPLIED)
docs/requirements/FR-004-recovery-interval-detection-v2.md  # Spec
research/papers/hrr_research_notes.md  # Literature + ChatGPT Health consultation
```

## What Needs to Be Done

### Immediate (needs update after this session's changes)
1. **Update visualization main()** to pass 3 categories:
   ```python
   valid_intervals, noise_intervals, rejected_intervals = filter_quality_intervals(intervals, config)
   plot_session_with_intervals(samples, valid_intervals, noise_intervals, rejected_intervals, ...)
   ```

2. **Test visualization**:
   ```bash
   python scripts/hrr_visualize.py --session-id 1 --source endurance --output /tmp/hr_session_1.png
   ```

3. **Test on a HIIT/interval session** - the Polar sessions should have actual recovery intervals

### Next Steps
1. Run `--all` to process all 67 sessions
2. Unsupervised analysis (clustering, anomaly detection)
3. Supervised models once we have labeled data (RPE, next-day HRV)

## Key Technical Decisions

1. **ML-native approach** over clinical single-timepoint paradigm
2. **Normalized metrics** (hrr60_frac = hrr60_abs / hr_reserve) essential for cross-intensity comparison
3. **Floor effect threshold** ~25 bpm hr_reserve below which HRR is noise
4. **Three-category classification** for transparency and paper-quality visualization
5. **Pre-peak avg HR** added as feature (sustained effort before drop)

## Data Availability
- hr_samples: 187,580 samples across 67 sessions
- Suunto: 2 sessions (long runs)
- Polar: 65 sessions (likely includes intervals)
- biometric_readings: RHR, HRV, sleep scores available for context

## Research Notes Location
`/research/papers/hrr_research_notes.md` contains:
- ChatGPT Health consultation (5 Q&A)
- Normalized metrics formulas
- Individual calibration procedure
- 21 references with links
