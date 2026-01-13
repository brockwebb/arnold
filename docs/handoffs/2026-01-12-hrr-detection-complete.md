# HRR Detection Algorithm - Handoff Document

**Date**: 2026-01-12  
**Status**: Working algorithm, ready for multi-session testing

## Summary

Rebuilt HRR detection from scratch after previous v2 implementation accumulated technical debt with layered gates that didn't match visual intuition. New approach uses scipy for peak detection + exponential fit validation.

## Algorithm Overview

### Pipeline
1. **Smooth**: 5-point median + moving average
2. **Peak Detection**: scipy `find_peaks(prominence=5, distance=10)`
3. **Initial Descent Test**: 15s linear fit (slope < 0, R² > 0.5)
4. **Interval Extension**: Track nadir, end on plateau (>3bpm rise for >5s)
5. **Quality Gates**:
   - Duration ≥ 60s required
   - HRR60 ≥ 9bpm required
   - R² calculated but NOT gated (diagnostic only currently)

### Key Files
- `/scripts/hrr_simple.py` - Main detection script
- `/scripts/hrr_sensitivity.py` - Multi-window R² analysis + threshold plotting

### Usage
```bash
# Basic detection with debug output
python scripts/hrr_simple.py --session-id 31 --debug

# Sensitivity analysis
python scripts/hrr_sensitivity.py --session-id 31 --plot-threshold
```

## Key Design Decisions

### Why scipy for peaks?
Previous attempts at custom peak detection kept failing on edge cases (double-peaks, mid-descent detection). scipy's `find_peaks` with prominence parameter reliably finds true local maxima.

### Why linear fit for initial test?
The step-by-step "7 second test" with noise allowances was too strict for real HR data. A 15-second linear regression (slope negative, R² > 0.5) captures "is this descending?" without micromanaging individual steps.

### Why exponential R² as diagnostic, not gate?
We discovered that R² and HRR measure DIFFERENT things:
- **R²**: Signal quality (is this a clean exponential decay?)
- **HRR**: Magnitude (did HR drop meaningfully?)

High R² + low HRR = clean but shallow recovery (valid data, just not impressive)
Low R² + any HRR = noisy signal, don't trust

## Recovery Activation Threshold

### Research Basis
Meaningful parasympathetic-mediated HRR requires exercise intensity high enough to substantially suppress vagal tone. This occurs at approximately **≥70% HRmax** (≈50-60% VO₂max), roughly at/above VT1.

- HRV indices (RMSSD) reach near-minimum around 120-140 bpm
- Below threshold: vagal tone substantial → gentle drift, not exponential decay
- Above threshold: vagal withdrawal near maximal → parasympathetic rebound triggers exponential decay

### For Brock (age 50)
- Tanaka HRmax: 208 - (0.7 × 50) = **173 bpm**
- Research threshold (70%): **121 bpm**

### Validation Approach
Compare research-based threshold to empirical threshold (lowest peak HR with R²≥0.7 & HRR≥9). Track deviation over time as potential biomarker of autonomic state.

### Key Citations
- Frontiers in Physiology 2017: https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2017.00301/full
- PMC8548865: https://pmc.ncbi.nlm.nih.gov/articles/PMC8548865/
- PubMed 27617566: https://pubmed.ncbi.nlm.nih.gov/27617566/

Full research notes: `/research/papers/hrr-threshold-research.md`

## Future Work

### Immediate (Next Session)
1. Test on multiple sessions (not just #31)
2. Validate threshold plot with more data
3. Consider R² > 0.7 as additional quality gate

### DFA-α1 Integration (Personal VT1 Detection)
Polar H10 provides RR intervals - we can compute DFA-α1 to detect personal VT1:
- α1 ≈ 1.0 at low intensity (fractal dynamics)
- α1 → 0.75 at VT1 (HRVT1)
- α1 → 0.5 at VT2 (HRVT2)

This would replace the 70% HRmax estimate with a measured personal threshold.
See: `/research/papers/hrr-threshold-research.md` for implementation details.

### Longitudinal Modeling Framework
Linear mixed-effects model to track HRR changes over time:

```
HRR_ij = β₀ + b₀ᵢ + β₁·FAge_i + (β₂ + b₁ᵢ)·Time_ij + β₃ᵀ·X_ij + ε_ij
```

Key decomposition:
- `FAge_i` = age at first measurement (between-person effect)
- `Time_ij = Age_ij - FAge_i` = within-person aging
- Random slopes capture individual aging trajectories

This separates cross-sectional age differences from longitudinal aging effects.
Key finding: within-subject SD of HRR ≈ 10.8 bpm (larger than between-subject!).

### Statistical Quality Control
- Aggregate validated intervals to build personal "expected recovery curve"
- Use control limits to flag outliers
- HRR60 = 25 when typical is 18±3 → exceptional or artifact?
- HRR60 = 8 when typical is 18 → fatigue/dehydration/overtraining?

### Bee Swarm Visualization
Build DataFrame structure capturing:
```
session_id, peak_time, workout_type, 
hrr_30, hrr_60, hrr_120,
r2_30, r2_60, r2_120,
peak_hr, nadir_hr,
ambient_temp, humidity, time_of_day,
sleep_score, hrv_morning, ...
```
Then facet/color by workout_type (running/HIIT/strength) or other dimensions.

### Threshold Tracking Over Time
- Plot threshold estimate per session over months
- Correlate with training load, HRV trends, sleep quality
- This becomes a fitness/recovery capacity metric itself

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| smooth_kernel | 5 | Smoothing window size |
| prominence | 5.0 | scipy peak prominence threshold |
| distance | 10 | Minimum seconds between peaks |
| max_rise_from_nadir | 3.0 | bpm rise that triggers plateau detection |
| max_plateau_sec | 5 | Seconds rise must persist to end interval |
| min_hrr60 | 9.0 | Minimum HRR60 to be valid |
| min_hrr120 | 12.0 | Minimum HRR120 to be valid |
| min_display_duration | 50 | Show rejected intervals if duration >= this |

## Session 31 Results
- **Valid**: 9 HRR60 + 3 HRR120 = 12 total
- **Rejected (near-miss)**: 15 displayed
- **R² range for valid**: 0.69 - 0.979
- All valid intervals visually confirmed as real recoveries

## Algorithm Evolution Summary

1. **v1** (pre-session): Layered gates, technical debt, didn't match intuition
2. **Attempt 1**: Custom peak detection → failed on edge cases
3. **Attempt 2**: scipy peaks + strict 7s step test → rejected everything
4. **Attempt 3**: scipy peaks + 15s linear fit → works!
5. **Current**: Added exponential R² as diagnostic, discovered threshold hypothesis
