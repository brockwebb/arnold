# ADR-005: Heart Rate Recovery (HRR) Pipeline Architecture

**Date:** January 12, 2026  
**Status:** Accepted  
**Deciders:** Brock Webb, Claude (Arnold development), with input from ChatGPT Health

## Context

Heart rate recovery (HRR) — how quickly HR drops after exertion — is a validated marker of autonomic fitness and recovery status. Changes in HRR can signal overtraining, illness, or accumulated fatigue before subjective symptoms appear.

Arnold collects high-resolution HR data from Polar H10 chest straps during strength and endurance sessions. We needed a system to:

1. Extract HRR intervals from real-world training (not controlled lab protocols)
2. Score confidence in each measurement (noisy data, variable conditions)
3. Detect meaningful trends versus normal day-to-day variation
4. Integrate signals into Arnold's coaching recommendations

Initial attempts using τ (time constant) from exponential fits failed — 82% of recovery windows were censored (HR never reached asymptote within available window). We pivoted to direct HRR30/HRR60 measurements with confidence scoring.

## Decision

### 1. Use Direct HRR Metrics, Not τ

**Primary signals:**
- `HRR30`: HR drop from peak at 30 seconds
- `HRR60`: HR drop from peak at 60 seconds  
- `HRR_frac`: HRR60 / (peak - local_baseline), normalized recovery
- `early_slope`: Linear slope of first 15 seconds (bpm/sec)

**Rationale:** τ requires the full recovery curve which we rarely capture in strength training (next set interrupts). HRR30/60 are robust to truncation and have strong research backing.

### 2. Local Pre-Peak Baseline

Use median HR from -180s to -60s before peak, not session minimum.

**Rationale:** Session minimum can be anomalously low (belt shift, standing rest). Local baseline reflects the physiological state immediately before the effort, providing a more accurate "effort" calculation.

### 3. Data Quality Filtering

**Quality filter for trend detection:** R² ≥ 0.75

Empirical analysis showed that R² strongly predicts HRR60 (r = 0.36, ρ = 0.47) even after controlling for legitimate factors. Q1 vs Q4 R² quartiles show 7.2 bpm difference (Cohen's d = 1.24). This exceeds the SDD, meaning measurement quality noise is larger than the signal we're detecting.

**High outliers:** Investigated and confirmed as real — they have higher R² (0.94 vs 0.87), higher effort, and higher normalized recovery. No winsorization needed; use median-based statistics which are inherently robust to outliers.

### 4. Confidence Scoring Formula

Each HRR interval receives a confidence score 0-1:

```python
confidence = (
    0.40 × mag_score +      # Was this a real effort?
    0.25 × frac_score +     # Good recovery relative to effort?
    0.25 × fit_score +      # How well did exponential fit?
    0.10 × window_score     # Was window complete?
)
```

Where:
- `mag_score = min(1.0, peak_minus_local / 13)` — effort magnitude
- `frac_score = min(1.0, hrr_frac / 0.3)` — normalized recovery quality
- `fit_score = R²` from exponential fit (clamped 0-1)
- `window_score = 1.0 if ≥60s complete, degrading for shorter windows`

**Rationale:** Not all HRR measurements are equal. A measurement from a hard set with clean signal should influence trends more than a measurement from a light warmup with motion artifact.

### 5. Weighted Values for Trend Detection

```python
weighted_HRR60 = HRR60 × confidence
```

Trend detectors operate on `weighted_HRR60`, not raw values. This naturally downweights unreliable measurements.

### 6. Gap-Aware EWMA (λ = 0.2)

Exponentially weighted moving average with reset logic:

```
z_t = λ × x_t + (1-λ) × z_{t-1}
```

**Reset condition:** Gap > 48 hours → reset to stratum baseline.

**Rationale:** After a long break, previous EWMA state is stale. Fresh athletes shouldn't start with a "ghost" of pre-break fatigue. λ = 0.2 balances responsiveness with noise rejection.

### 7. One-Sided CUSUM for Sustained Declines

Cumulative sum detector for persistent downward shifts:

```
s_t = max(0, s_{t-1} + (baseline - x_t) - k)
Alert when s_t ≥ h
```

**Parameters (SDD-based):**
- `k = 0.5 × SDD` — allowance for normal variation
- `h = 4.0 × SDD` — decision threshold

**Reset conditions:**
- Gap > 48 hours
- 3+ consecutive values near baseline (recovery reset)

**Rationale:** EWMA detects gradual drift but lags. CUSUM accumulates small consistent drops and triggers faster on sustained shifts. Together they cover different failure modes.

### 8. Per-Stratum Baselines and SDD

Separate statistics for each training context:

| Stratum | Baseline HRR60 | SDD | Warning | Action |
|---------|---------------|-----|---------|--------|
| STRENGTH | ~16.1 bpm | ~5.8 bpm | 10.3 | 4.5 |
| ENDURANCE | ~20.5 bpm | ~7.2 bpm | 13.3 | 6.1 |

**Rationale:** Recovery characteristics differ by activity type. Mixing strata would create spurious alerts when switching between strength and running blocks.

### 9. Extended Recovery Protocol (Weekly)

Once per week, perform a dedicated 5-minute supine recovery measurement:

1. Complete final work set at moderate-high effort (75-85% max HR)
2. Immediately lie supine (flat on back)
3. Remain still for 300 seconds (5 minutes)
4. Record as `protocol_type = 'dedicated'`, `recovery_posture = 'supine'`

**Rationale:** Standing inter-set recovery measures real-world capacity. Supine end-of-session measures maximal parasympathetic reactivation (“autonomic ceiling”). These are different constructs:

| Context | What it measures | Use case |
|---------|-----------------|----------|
| Standing inter-set | Ecological recovery | Day-to-day trend detection |
| Supine dedicated | Autonomic ceiling | Weekly longitudinal tracking, τ calculation |

**Critical:** Do not mix supine and standing data in the same EWMA. They require separate baselines.

### 10. Storage Architecture: Extract Once, Analyze On-Demand

```
HR Series → [Peak Extraction] → hr_recovery_intervals table
                                       ↓
                               [EWMA/CUSUM] → Alerts
```

**Extends existing table** (`hr_recovery_intervals` from migration 013) with new columns:

```sql
-- Migration 014: HRR Pipeline Extensions
ALTER TABLE hr_recovery_intervals ADD COLUMN confidence NUMERIC(4,3);
ALTER TABLE hr_recovery_intervals ADD COLUMN weighted_hrr60 NUMERIC(5,2);
ALTER TABLE hr_recovery_intervals ADD COLUMN actionable BOOLEAN DEFAULT TRUE;
ALTER TABLE hr_recovery_intervals ADD COLUMN recovery_posture VARCHAR(20);
ALTER TABLE hr_recovery_intervals ADD COLUMN protocol_type VARCHAR(20);
ALTER TABLE hr_recovery_intervals ADD COLUMN stratum VARCHAR(20);
ALTER TABLE hr_recovery_intervals ADD COLUMN local_baseline_hr SMALLINT;
ALTER TABLE hr_recovery_intervals ADD COLUMN peak_minus_local SMALLINT;
ALTER TABLE hr_recovery_intervals ADD COLUMN early_slope NUMERIC(5,3);
ALTER TABLE hr_recovery_intervals ADD COLUMN hr_180s SMALLINT;
ALTER TABLE hr_recovery_intervals ADD COLUMN hr_300s SMALLINT;
ALTER TABLE hr_recovery_intervals ADD COLUMN hrr180_abs SMALLINT;
ALTER TABLE hr_recovery_intervals ADD COLUMN hrr300_abs SMALLINT;

-- View for coaching queries
CREATE VIEW hrr_actionable AS
SELECT * FROM hr_recovery_intervals WHERE actionable = TRUE;
```

**Rationale:** Peak extraction from HR series is computationally expensive and deterministic. Once extracted, recomputing EWMA/CUSUM is cheap arithmetic. Don't re-extract 165 workouts every time we want a trend report.

## Rationale

### Why Not Use Raw HRR Values?

Day-to-day variation is large (~6-7 bpm SDD). A single low reading is noise. Confidence weighting and EWMA smoothing are necessary to extract signal from the noise floor.

### Why Two Detectors (EWMA + CUSUM)?

| Detector | Strength | Weakness |
|----------|----------|----------|
| EWMA | Smooths noise, tracks gradual drift | Lags on step changes |
| CUSUM | Fast on sustained shifts | Can false-alarm on single outliers (mitigated by recovery reset) |

Using both provides complementary coverage.

### Why SDD-Based Thresholds?

Static thresholds (e.g., "alert if HRR60 < 10 bpm") don't account for individual variation or measurement precision. SDD is calculated from the typical error in repeated measurements, making thresholds statistically meaningful: "alert if decline exceeds what's distinguishable from noise."

### Why 48-Hour Gap Reset?

Between-session physiological recovery is roughly complete in 48 hours for typical training. Longer gaps (travel, illness, vacation) mean the EWMA state is no longer predictive of current status.

## Consequences

### Positive

- Robust to real-world training conditions (variable windows, mixed intensities)
- Confidence scoring naturally downweights unreliable data
- Per-stratum baselines prevent cross-activity false alarms
- Efficient: extract once, query many times
- Alert thresholds have statistical interpretation (SDD multiples)

### Negative

- Requires sufficient data to establish per-stratum baselines (~20+ intervals)
- EWMA has inherent lag; won't catch single-session acute issues
- Confidence weights are heuristic; may need tuning for different athletes
- Recovery window still limits τ calculation for diagnostic purposes

### Trade-offs Accepted

- Prioritized HRR60 over τ despite τ being theoretically richer — pragmatism over elegance
- Chose λ = 0.2 without formal optimization — reasonable default from literature
- Single confidence formula for all athletes — may need personalization later

## Implementation

### Completed

- `src/arnold/hrr/detect.py` — EWMA, CUSUM, confidence scoring (~350 lines)
- `src/arnold/hrr/__init__.py` — Public API exports
- `scripts/hrr_batch.py` — Full extraction pipeline with `--report-ewma` flag
- `scripts/hrr_data_quality_analysis.py` — Data quality investigation (R² artifact, outliers)
- `docs/hrr-data-quality-checklist.md` — Operational documentation

### Pending

- Postgres migration for `hrr_observations` table
- Incremental sync hook in polar pipeline
- Arnold coaching integration (briefing additions)

### CLI Usage

```bash
# Full extraction with trend analysis
python scripts/hrr_batch.py \
    --output outputs/hrr_all.csv \
    --plot-beeswarm \
    --stratified \
    --report-ewma

# Test detectors on synthetic data
python src/arnold/hrr/detect.py
```

## Coaching Integration Guidelines

(From ChatGPT Health collaboration)

### Decision Matrix

| Signal Level | Criteria | Action |
|-------------|----------|--------|
| Green | All metrics nominal | Proceed with planned session |
| Yellow (Minor) | One metric modestly off | Reduce high-intensity volume |
| Orange (Moderate) | HRR decline > SDD + RHR/HRV shift | Low-volume, technique focus |
| Red (Major) | >2×SDD over several days | Scheduled deload, clinical review if symptomatic |

### What Arnold Should Say

When HRR CUSUM fires:
> "Your heart rate recovery has been trending down over the last few sessions. Combined with [other signals], I recommend dialing back today's intensity. Let's focus on movement quality rather than load."

When HRR EWMA shows sustained decline:
> "Recovery metrics suggest accumulated fatigue. Consider whether this is expected (end of block, increased load) or unexpected (poor sleep, stress). A lighter week might be warranted."

### Escalation Criteria

Refer to medical review if:
- New symptoms (chest pain, syncope, palpitations)
- Sustained resting tachycardia (RHR up >10 bpm for >3 days)
- Unexplained large HRR decline despite rest

## Related Decisions

- ADR-001: Data Layer Separation (HRR observations follow Postgres-for-facts pattern)
- ADR-002: Strength Workout Migration (workout_id FK relationship)

## References

- Cole CR et al. "Heart-rate recovery immediately after exercise as a predictor of mortality." NEJM 1999.
- Daanen HA et al. "Heart rate recovery during active and passive recovery." Int J Sports Physiol Perform. 2012.
- [hrr-data-quality-checklist.md](../hrr-data-quality-checklist.md)
- [hrr_research_protocol.md](../hrr_research_protocol.md)

## Changelog

- 2026-01-12: Removed winsorization — high outliers confirmed real, use median-based stats
- 2026-01-12: Added data quality filtering section (R² ≥ 0.75)
- 2026-01-12: Initial ADR documenting completed pipeline
