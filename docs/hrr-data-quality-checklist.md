# HRR Data Quality Checklist

Practical guidance for collecting cleaner, more useful heart rate recovery data from everyday training. Data quality advice only — no medical claims.

## Production Summary

We extract repeated in-session HRR intervals (HRR30/60, HRR_frac, early slope, AUC₀₋₆₀) using a local pre-peak baseline and per-interval confidence (R², motion, window length). Intervals with <5 bpm peak-over-local baseline are excluded; censored τ and truncated windows are flagged and not used for alerts. Events are aggregated into a confidence-weighted `weighted_value` stream and monitored with gap-aware EWMA (λ=0.2) and one-sided CUSUM detectors; alert thresholds are tied to per-stratum SDD (data-driven) rather than static bpm cutoffs. For this dataset the strength stratum baseline HRR60 ≈ 16.1 bpm with SDD ≈ 5.8 bpm — practical alerts are triggered on sustained declines larger than the SDD (≈6 bpm) and conservative action when declines exceed ~2×SDD (~12 bpm). τ is retained for uncensored windows as diagnostic only.

## Trend Detection (EWMA & CUSUM)

We monitor a confidence-weighted HRR stream using two complementary detectors:

**EWMA (λ=0.20)** — sensitive to gradual drift; we compute the athlete's recent baseline (per-stratum) and SDD (Smallest Detectable Difference). A warning is raised when the EWMA falls below `baseline − 1.0 × SDD` (i.e., a sustained drop of ~1×SDD), and an action is raised when the EWMA falls below `baseline − 2.0 × SDD` (i.e., a sustained drop of ~2×SDD).

**CUSUM (one-sided downward)** — sensitive to accumulating small drops; parameterized with `k = 0.5 × SDD` and `h = 4.0 × SDD`. The CUSUM accumulator resets on long data gaps or when several consecutive recent events recover to near-baseline; an alert fires when the accumulator ≥ `h`.

**Example (current strength stratum):** baseline HRR60 ≈ 16.1 bpm, SDD ≈ 5.8 bpm → EWMA warning = baseline − 1×SDD = 10.3 bpm (≈ a 5.8 bpm sustained drop), EWMA action = baseline − 2×SDD = 4.5 bpm (≈ a 11.6 bpm sustained drop).

**Implementation notes:** Detectors are gap-aware (reset after session gaps), require a minimum number of recent events (default 5), and use per-interval confidence (R², accel quietness, window length) to weight each event; τ is used only descriptively when uncensored and with acceptable fit R².

---

## Priority 1: Do These First

- [x] **Use local pre-peak baseline** — Median HR from -180s to -60s before peak; session-min as fallback only
- [ ] **Chest strap for strength sessions** — PPG wrist is noisy during arm movement; Polar H10 gives clinical-grade signal
- [ ] **Extend post-effort windows to ≥180s** — Prevents censored τ fits; enables HRR120 measurement
- [ ] **Record session metadata** — Mode (strength/run/HIIT), set type (work/warmup/accessory), device, sleep hours

## Priority 2: Next Improvements

- [ ] **Artifact rejection** — Drop events with high accelerometer variance in first 30s of recovery
- [ ] **Conservative smoothing** — Median(5s) → MA(5s); add notch filter if stride-frequency noise dominates
- [ ] **Record RR intervals** — Enables HRV analysis and cleaner τ diagnostics; Polar H10 provides this
- [x] **Mark censored/truncated data** — Don't include censored τ in stats; report counts separately
- [ ] **Paired device calibration** — Occasional chest+wrist simultaneous sessions to quantify wrist bias

## Priority 3: Reliability & Monitoring

- [x] **Per-stratum TE/SDD** — Compute separately for strength vs running vs HIIT; don't use global thresholds
- [x] **Aggregate low-effort events** — Singles <13 bpm useful only in aggregate; build weekly trends
- [ ] **QA dashboard** — Show censored τ count, truncated windows, low-R² fits, worst 5% examples

## Nice-to-Have

- [ ] **Periodic lab-style protocol** — 10-min hard + 5-min supine every few months for personal reference
- [x] **Raw data archival** — Keep per-second files and config versions for reprocessing
- [ ] **User annotations** — Flag illness, jetlag, meds for outlier exclusion

## One-Line Summary

> Chest strap + longer windows + local baseline + SDD thresholds + accel gating = biggest gains

## Decision Rules

```
Include:     peak_minus_local >= 5 bpm
Quality:     R² >= 0.75 for trend detection (exclude low-quality fits)
Actionable:  single-event HRR60 < 13 bpm (investigate)
Exceptional: single-event HRR60 >= 18 bpm (good recovery)
Alert:       EWMA decline > SDD (~6.7 bpm) sustained over 3+ sessions
```

## Data Quality Findings (2026-01-12)

Empirical analysis revealed measurement quality (R²) confounds HRR60:
- R² → HRR60 correlation: r = 0.36, ρ = 0.47 (moderate-strong)
- Q1 vs Q4 R² quartiles: 7.2 bpm difference (Cohen's d = 1.24, large effect)
- R² explains 10.3% additional variance beyond legitimate factors

**Implication:** Low R² readings have systematically lower HRR60. Use R² ≥ 0.75 filter for actionable alerts.

**High outliers** (>32 bpm): Investigated and confirmed as REAL (higher R², higher effort). No special handling needed — use median-based statistics which are inherently robust.

See: `scripts/hrr_data_quality_analysis.py` for full analysis.

**Primary signals** (in-session): HRR30, HRR60, HRR_frac, early_slope, AUC_0_60  
**Secondary** (descriptive only): τ (censored in 82% of windows)  
**Trend detection**: Confidence-weighted EWMA with SDD-based thresholds

## Current Implementation Status

| Item | Status | Notes |
|------|--------|-------|
| Local pre-peak baseline | ✅ Done | `peak_minus_local` in hrr_batch.py |
| Censored τ flagging | ✅ Done | `tau_censored` boolean |
| Truncated window flagging | ✅ Done | `truncated_window` boolean |
| Early slope | ✅ Done | Linear fit first 15s |
| AUC 0-60s | ✅ Done | Trapezoidal area above nadir |
| HRR_frac | ✅ Done | HRR60 / effort (normalized) |
| Per-stratum SDD | ✅ Done | STRENGTH/ENDURANCE/OTHER |
| Stratified visualization | ✅ Done | `--stratified` flag |
| Confidence scoring | ✅ Done | R² + window + effort combined |
| Weighted value | ✅ Done | HRR × confidence for trends |
| EWMA detector | ✅ Done | Gap-aware, SDD thresholds |
| CUSUM detector | ✅ Done | One-sided downward, recovery reset |
| Session metadata | 🟡 Partial | Have sport_type; need set type, posture |
| Accelerometer gating | ❌ TODO | Need to pull accel data from Polar |
| RR interval analysis | ❌ TODO | Data available, not yet extracted |
| `--report-ewma` CLI | ✅ Done | Run trend detection on output |
| R² quality filter | ✅ Done | R² >= 0.75 for actionable readings |
| High outlier investigation | ✅ Done | Confirmed real, no winsorization needed |
| Data quality analysis | ✅ Done | `scripts/hrr_data_quality_analysis.py` |

## Related Documentation

- **[ADR-005: HRR Pipeline Architecture](adr/005-hrr-pipeline-architecture.md)** — Architectural decisions, rationale, and coaching integration guidelines
- **[hrr_research_protocol.md](hrr_research_protocol.md)** — Research methodology and literature review

## Config Reference

See `config/hrr_defaults.json` for current thresholds:
- `min_effort_bpm`: 5 (include filter)
- `single_event_actionable_bpm`: 13
- `exceptional_bpm`: 18
- `hrr_frac_actionable`: 0.3
- `tau_cap_seconds`: 300
- `min_tau_r2`: 0.6
- `ewma_lambda`: 0.20
- `cusum_k_mult`: 0.5
- `cusum_h_mult`: 4.0

## Module Structure

```
src/arnold/hrr/
├── __init__.py
└── detect.py      # EWMA, CUSUM, confidence scoring

scripts/
└── hrr_batch.py   # Main extraction pipeline
```

## Usage

```bash
# Basic extraction
python scripts/hrr_batch.py --output outputs/hrr_all.csv

# With stratified visualization
python scripts/hrr_batch.py --output outputs/hrr_all.csv --plot-beeswarm --stratified

# Work sets only (higher effort threshold)
python scripts/hrr_batch.py --output outputs/hrr_work.csv --min-effort 20 --plot-beeswarm

# Test EWMA/CUSUM detectors
python src/arnold/hrr/detect.py
```
