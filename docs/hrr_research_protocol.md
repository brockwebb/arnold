# HRR Feature Extraction from Consumer Wearables: Research Protocol

**Status:** Draft  
**Date:** 2026-01-11  
**Author:** Brock Tibert  

---

## Title

**Reliable Heart Rate Recovery Extraction from Unstructured Training: A Signal-Processing Approach for Consumer Wearables**

---

## 1. Problem Statement

Consumer wearables produce high-volume, noisy, unstructured HR traces from real workouts. We need a robust, auditable, device-tuned signal-processing pipeline to extract per-event HRR measures for monitoring and research—without requiring lab protocols.

**Core challenge:** Clinical HRR metrics (HRR60, tau) assume maximal sustained effort, abrupt cessation, and uninterrupted decay to true resting state. Strength training and unstructured endurance sessions provide none of these. We need metrics that are:

1. Reliably extractable from noisy, real-world data
2. Comparable within-person over time
3. Predictive of meaningful outcomes (recovery status, readiness)

---

## 2. Clinical Context & Rationale

### The Prognostic Value of HRR

Heart rate recovery (HRR) is a well-established marker of cardiovascular health and autonomic function. The landmark 1999 study by Cole et al. demonstrated that an abnormal HRR (≤12 bpm at one minute post-exercise) was a powerful predictor of mortality, independent of workload, heart rate changes during exercise, and other risk factors [1]. Subsequent research has confirmed HRR as predictive of coronary artery disease, heart failure, diabetes, and hypertension [2, 3].

The physiological basis is autonomic function: HRR reflects the reactivation of parasympathetic tone after exercise cessation. Blunted HRR indicates impaired vagal function, which is associated with increased cardiovascular risk [4]. Conversely, improved HRR following cardiac rehabilitation correlates with better long-term survival [5].

### The Problem with Population Thresholds

Clinical HRR assessment faces two fundamental limitations:

**1. Episodic measurement in artificial conditions.** HRR is typically measured during exercise stress tests—perhaps once every few years, under standardized but artificial protocols. Different facilities use different rest protocols (active vs. passive), making comparisons difficult. A single data point provides no trend information [6].

**2. Population thresholds miss individuals.** The commonly cited "18 bpm or higher" guideline is derived from population studies [6]. However, as Cleveland Clinic notes: "there isn't one magic number for everyone. What counts as a good heart rate recovery depends on many factors" [6]. This creates two failure modes:

| Failure Mode | Population Approach | Consequence |
|--------------|---------------------|-------------|
| **False alarm** | Individual with naturally slower autonomic recovery scores 15 bpm | Unnecessary anxiety, potential over-testing |
| **Missed signal** | Individual normally at 30+ bpm declines to 22 bpm | Still "normal" by population standards, meaningful personal decline missed |

### The Opportunity: Individualized Continuous Monitoring

Consumer wearables now provide high-frequency heart rate data during every training session. This creates an opportunity to shift from episodic population-referenced assessment to continuous individualized monitoring:

- **Establish personal baselines** from hundreds of observations under naturalistic conditions
- **Detect deviations from individual norms** rather than population cutoffs
- **Contextualize measurements** with environmental and training load covariates
- **Flag meaningful changes early** when they may still be reversible or warrant investigation

As Cleveland Clinic advises: "If your HRR is low, don't panic. Instead, know that you have one more tool in your toolkit that you can use to your advantage" [6]. Our approach operationalizes this principle—providing ongoing surveillance that complements rather than replaces clinical assessment.

### Related Work: Wearable HRR and Machine Learning

There is a growing body of work using consumer-grade wearables to derive HRR-like measures and feed them into machine learning models for risk prediction and digital phenotyping. Most studies either (a) explicitly compute HRR from wearable HR data and use it as a feature, or (b) learn latent "recovery dynamics" from continuous HR + activity streams without naming it HRR [13, 14, 15, 16].

**Direct HRR from wearables:**

- A 2025 University of Illinois study used a smart-ECG shirt during treadmill walking, continuously tracked HRR after exercise, and applied ML classifiers to separate higher- vs lower-risk participants using a 1-minute HRR threshold around 28 bpm, reaching ~86% accuracy for risk classification [17, 14].

- A 2024 digital frailty study used a wearable that captured heart rate and gait mechanics in daily life, automatically found "episodes" with a peak HR and subsequent recovery, computed HRR, and showed that a heart-rate analyzer using these HRR values predicted frailty and functional status with AUCs in the 0.80–0.86 range [18].

**ML on high-resolution wearable HR dynamics:**

- A 2022 "digital phenotype" study processed high-resolution HR and steps from consumer wearables, extracting features related to exercise response and recovery (including HRR-like post-stress slopes), and showed these were associated with cardiometabolic risk and added predictive value beyond simple summaries like resting HR [15].

- A 2023 Nature Digital Medicine paper built a hybrid physiological + ML model that predicts the full HR response curve to exercise from wearable-derived step count, speed, and elevation, effectively learning personalized recovery trajectories that could be used to derive individualized HRR metrics for new workouts [16].

**Machine learning methods used:**

- *Classical methods:* Logistic regression, random forests, and SVMs are common for classifying individuals as higher vs lower risk based on HRR magnitude and related features (e.g., early vs late recovery slopes, HR at multiple recovery time points) [14, 17, 18].

- *Deep learning:* Convolutional/recurrent networks and hybrid physiologic-ML models learn latent representations of heart-rate dynamics from raw time series, which implicitly encode recovery speed and are then mapped to outcomes such as cardiometabolic disease, frailty, or fitness level [13, 15, 16].

**Key insight for this work:** HRR extracted from wrist or chest wearables is noisy on a per-bout basis, but aggregating many detected recovery events and using ML on features like HRR at 60s, multi-point decay curves, and context (pace, load, environment) yields clinically meaningful signal for cardiometabolic risk and functional status [15, 18].

### Where This Work Fits

Existing wearable HRR studies largely focus on:
- **Clinical populations** (cardiac rehab, frailty screening)
- **Controlled protocols** (treadmill walking, standardized exercise)
- **Population-level risk stratification** (higher vs lower risk classification)

Our contribution addresses a gap:
- **Healthy active population** (athletes, recreational exercisers)
- **Unstructured real-world training** (strength, hybrid, variable rest periods)
- **Individualized longitudinal monitoring** (within-person change detection, not population classification)
- **Training adaptation context** (recovery status, readiness, overtraining detection)

The signal processing challenge is harder (noisier data, less structured protocols), but the statistical opportunity is greater (many more observations per individual, enabling personalized baselines).

---

## 3. Value Proposition

### Core Thesis

Clinical HRR assessment relies on single measurements against population norms, missing both false positives (individuals with naturally slower recovery) and false negatives (meaningful personal decline masked by "normal" absolute values). We propose a continuous, individualized monitoring approach using consumer wearables during routine training. By establishing within-person baselines and detecting deviations exceeding measurement error, this method identifies changes that warrant attention—regardless of whether absolute values cross population thresholds.

### Practical Value

Turn routine training sessions into repeated, statistically powerful autonomic recovery observations. Provide athletes, coaches, and researchers with standardized recovery metrics that are:

- **Derived from existing behavior** — no new protocol required
- **Robust to noise** — deterministic detection with device-specific tuning
- **Interpretable** — matches clinical anchors where possible, honest about limitations
- **Actionable** — supports longitudinal monitoring with statistically-grounded thresholds (SDD)
- **Individualized** — flags deviations from personal baseline, not population norms

### The "Don't Panic / Don't Miss" Framework

Two failure modes we protect against:

| Scenario | Population Approach | Individualized Approach |
|----------|---------------------|-------------------------|
| Athlete A: HRR = 15 bpm (below 18 threshold) | Triggers concern | Stable at personal baseline → no flag |
| Athlete B: HRR = 22 bpm (above threshold) but normally 32+ | Looks "normal" | 10+ bpm decline from baseline → flag for attention |

Both approaches have a role. Population thresholds identify individuals who may warrant clinical evaluation. Individualized monitoring detects *changes* that population thresholds miss. The combination provides more complete surveillance than either alone.

### Real-World Data is the Point

Clinical HRR measurement requires:
- Standardized maximal exercise protocol (treadmill/bike to exhaustion)
- Controlled recovery conditions (passive supine or active walking at fixed pace)
- Clinical supervision and equipment
- Scheduling, travel, cost

Result: One measurement every few years, if that.

Our approach accepts the noise of real-world training because:
- **Volume compensates for variance:** Hundreds of measurements beat one clean one
- **No behavior change required:** Athletes train how they train
- **Continuous surveillance:** Detect changes in weeks, not years
- **Zero marginal cost:** Data collection is a byproduct of normal activity

The measurements are noisier. The sample size is vastly larger. For detecting *within-person change over time*, the latter wins.

This is the same logic that made consumer wearables valuable for atrial fibrillation detection [20]: individual PPG readings are far less accurate than clinical ECG, but continuous passive monitoring catches events that episodic clinical measurement misses.

---

## 4. Research Questions

### Primary

**Can heart rate dynamics during training sessions predict next-day recovery status in a longitudinal n-of-1 design?**

### Secondary

1. What is the detection reliability (precision/recall) of the non-rising-run algorithm across session types?
2. What is the measurement reliability (TE/SDD) of extracted HRR features?
3. Which features carry predictive signal for recovery outcomes?
4. Do HRR metrics differ meaningfully between training block types (accumulation vs deload)?

---

## 5. Prediction Targets (Dependent Variables)

### Primary Outcome

**Next-morning HRV** (RMSSD or HRV score from Ultrahuman) — delta from 7-day rolling baseline

### Secondary Outcomes

1. **Subjective readiness score** — journal entry, standardized 1-10 scale
2. **Sleep quality metrics** — total sleep, deep sleep %, sleep score (Ultrahuman)
3. **Resting HR delta** — from 7-day baseline
4. **Next-session RPE** — proxy for accumulated fatigue

### Exploratory Outcome

**Performance deviation** — did athlete hit prescribed weights/reps vs underperform on next similar workout?

---

## 6. Feature Set (Independent Variables)

### Per-Event Features

From each detected recovery interval:

| Feature | Description | Unit |
|---------|-------------|------|
| `HR_peak` | Maximum HR at interval start | bpm |
| `HR_nadir` | Minimum HR during interval | bpm |
| `total_drop` | HR_peak - HR_nadir | bpm |
| `time_to_nadir` | Duration from peak to nadir | seconds |
| `HR_30s` | HR at 30s post-peak | bpm |
| `HR_60s` | HR at 60s post-peak | bpm |
| `HR_120s` | HR at 120s post-peak (if available) | bpm |
| `HRR30_abs` | HR_peak - HR_30s | bpm |
| `HRR60_abs` | HR_peak - HR_60s | bpm |
| `HRR120_abs` | HR_peak - HR_120s | bpm |
| `HRR30_frac` | HRR30_abs / peak_minus_rest | ratio |
| `HRR60_frac` | HRR60_abs / peak_minus_rest | ratio |
| `ratio_30_60` | HRR30_abs / HRR60_abs | ratio |
| `tau` | Exponential decay time constant | seconds |
| `tau_r2` | Fit quality for tau | 0-1 |
| `peak_minus_rest` | HR_peak - local_hr_rest (effort indicator) | bpm |
| `local_hr_rest` | Median HR in pre-peak window | bpm |
| `duration_seconds` | Total interval duration | seconds |
| `confidence_score` | Composite quality score | 0-1 |

### Session-Level Aggregates

| Feature | Description |
|---------|-------------|
| `hrr60_mean` | Mean HRR60_abs across events |
| `hrr60_median` | Median HRR60_abs |
| `hrr60_sd` | Standard deviation of HRR60_abs |
| `event_count` | Number of valid intervals detected |
| `hrr60_best` | Maximum HRR60_abs (best recovery) |
| `hrr60_worst` | Minimum HRR60_abs (worst recovery) |
| `total_drop_mean` | Mean total_drop across events |
| `session_load` | sRPE × duration |
| `session_type` | strength / endurance / hybrid |

### Environmental Covariates

| Feature | Description | Source |
|---------|-------------|--------|
| `ambient_temp_f` | Temperature during session | Weather API / manual |
| `humidity_pct` | Relative humidity | Weather API |
| `location_type` | indoor_controlled / indoor_unconditioned / outdoor | Manual tag |
| `time_of_day` | Session start hour | Timestamp |
| `days_since_last` | Recovery days since previous session | Calculated |
| `acwr_7d` | Acute:chronic workload ratio | Calculated |
| `sleep_prior_night` | Hours of sleep night before | Ultrahuman |
| `sleep_quality_prior` | Sleep score night before | Ultrahuman |
| `caffeine` | Caffeine intake if logged | Journal |

### Workout Type Metadata

Session and effort context that may influence HRR patterns:

| Field | Values | Source | Rationale |
|-------|--------|--------|----------|
| `session_type` | strength, endurance, hybrid, hiit | Manual / inferred | Different metabolic demands |
| `effort_modality` | running, rowing, sandbag, barbell, bodyweight | Manual / inferred | Movement pattern affects HR response |
| `effort_structure` | continuous, interval, circuit | Manual / inferred | Steady-state vs repeated peaks |
| `muscle_groups` | lower, upper, full_body, cardio | Workout plan | Local vs systemic fatigue |
| `movement_patterns` | hip_hinge, squat, push, pull, carry, locomotion | Exercise metadata | May correlate with HR elevation |
| `rest_structure` | timed, auto-regulated, walk_break | Protocol | Affects recovery window length |
| `protocol_name` | tabata, emom, amrap, tempo_run, easy_run | Workout plan | Named protocols have expected patterns |

**Potential Analyses:**

1. **Cross-modality comparison:** Does sandbag shouldering produce different HRR than barbell deadlifts at similar RPE?

2. **Structure effects:** Do interval sessions (repeated peaks) show different recovery patterns than continuous efforts?

3. **Muscle group effects:** Does lower-body strength work produce different cardiovascular recovery than upper-body?

4. **Running stratification:** Easy runs vs tempo runs vs intervals—different expected HRR distributions?

**Inference from existing data:**

Your Neo4j workout data includes:
- Exercise names → can infer modality, muscle groups, movement patterns
- Set/rep structure → can infer rest patterns
- Session tags → may indicate protocol type

This allows retrospective labeling of historical sessions for subgroup analysis.

---

## 7. Detection Algorithm

### Core Approach

Detect contiguous "non-rising" HR runs, backtrack to peak, apply minimal quality gates.

### Operational Rule

1. **Preprocess:** Resample to 1 Hz → median(5s) → moving average(5s)
2. **Compute diff:** `Δ[t] = HR[t] − HR[t−1]`
3. **Mark non-rising:** `non_rising = (Δ ≤ allowed_up_per_sec)`
4. **Find runs:** Contiguous sequences where `non_rising == True` and `duration ≥ 60s`
5. **Backtrack:** Find `HR_peak` within `lookback_local_max_s` before run start
6. **Apply gates:**
   - Duration ≥ 60s
   - `total_drop ≥ min_total_drop`
   - `peak_minus_rest ≥ low_signal_cutoff`

### Device-Specific Parameters

| Parameter | Wrist PPG (Ultrahuman) | Chest/Arm Strap (Polar) |
|-----------|------------------------|-------------------------|
| `allowed_up_per_sec` | 0.5–1.0 bpm/s | 0.1–0.3 bpm/s |
| `min_total_drop` | 8–10 bpm | 5 bpm |
| `lookback_local_max_s` | 20–40 s | 10–30 s |
| `low_signal_cutoff` | 20–30 bpm | 15–25 bpm |
| `smoothing` | median(5) → MA(5) | median(3) → MA(3) |

### Activity-Specific Adjustments

**Strength/HIIT:**
- Accept HRR30 as primary anchor (short rest periods)
- Stricter accelerometer gating if using wrist
- Prefer arm/chest strap

**Running/Endurance:**
- Stronger smoothing (stride noise)
- Higher `min_total_drop` (10 bpm)
- HRR120 more often available

---

## 8. Environmental Data Integration

### Outdoor Sessions

- Extract geolocation from FIT/GPX files
- Pull historical weather data via Open-Meteo API (free, covers historical)
- Average temperature and humidity over session duration
- Flag precipitation, wind speed as potential confounders

### Indoor Sessions

**Location types:**
- `indoor_climate_controlled` — gym with HVAC, assume ~68-72°F
- `indoor_unconditioned` — garage gym, use outdoor temp as proxy
- `outdoor` — use weather API

**Schema additions:**
```sql
ALTER TABLE training_sessions ADD COLUMN location_type VARCHAR(30);
ALTER TABLE training_sessions ADD COLUMN ambient_temp_f DECIMAL(4,1);
ALTER TABLE training_sessions ADD COLUMN humidity_pct DECIMAL(4,1);
ALTER TABLE training_sessions ADD COLUMN weather_source VARCHAR(20);
```

### Weather API Integration

**Open-Meteo Historical Weather API:**
- Free, no API key required
- Endpoint: `https://archive-api.open-meteo.com/v1/archive`
- Parameters: latitude, longitude, start_date, end_date, hourly variables
- Variables: `temperature_2m`, `relative_humidity_2m`, `precipitation`

---

## 9. Sample Size & Statistical Power

### Available Data

- ~165 workouts in Neo4j
- ~18 months of training history
- Daily HRV/sleep from Ultrahuman
- Per-second HR from Polar arm strap (recent sessions)
- FIT files from Suunto (endurance, variable HR availability)

### Event Yield Estimates

| Session Type | Expected Events | Basis |
|--------------|-----------------|-------|
| Strength | 3-8 | Rest periods between compound sets |
| Endurance with breaks | 2-5 | Walk breaks, water stops |
| Continuous endurance | 0-1 | Cooldown only |

**Conservative estimate:** 4 events/session average  
**Total events:** 165 sessions × 4 = ~660 recovery intervals

### Power Analysis

**For regression/ML:**
- Rule of thumb: 10-20 observations per predictor
- With 15-20 features: need 150-400 observations minimum
- Available N (~660) is adequate for exploratory modeling

**For reliability (TE/SDD):**
- Need ≥10 comparable sessions (same type, similar conditions)
- Available data likely sufficient

**For correlation detection:**
- r = 0.3 with 80% power: ~85 paired observations required
- r = 0.2 with 80% power: ~200 paired observations required
- Available N adequate for moderate effects, marginal for small effects

---

## 10. Study Phases

### Phase 1: Detection Validation (Week 1-2)

**Objective:** Verify the non-rising-run detection algorithm works reliably.

**Tasks:**
1. Implement simplified detection module
2. Run on 20 sessions (10 strength, 10 endurance)
3. Visual inspection of all detected intervals (overlay plots)
4. Manual label 50 events (true positive / false positive / missed)
5. Compute precision, recall, F1

**Acceptance criteria:**
- Precision ≥ 0.80
- Recall ≥ 0.70
- Visual inspection confirms sensible interval boundaries

**Deliverables:**
- Detection module code
- 20 overlay plots
- Labeled event spreadsheet
- Precision/recall report

### Phase 2: Feature Extraction & Reliability (Week 2-3)

**Objective:** Extract features at scale and establish measurement reliability.

**Tasks:**
1. Extract full feature set for all sessions with HR data
2. Compute TE and SDD for HRR60, total_drop, tau across comparable sessions
3. Identify reliable features (TE < 20% of mean)
4. Document unreliable features (exclude from prediction models)

**Deliverables:**
- Feature extraction pipeline
- Feature database table
- Reliability report (TE/SDD for each metric)
- Feature inclusion/exclusion decisions

### Phase 3: Outcome Alignment (Week 3-4)

**Objective:** Create analysis-ready dataset joining features to outcomes.

**Tasks:**
1. Join session features to next-day outcomes (HRV, sleep, readiness)
2. Integrate environmental covariates (weather API backfill)
3. Create analysis dataset with complete cases
4. Document missingness patterns
5. Compute descriptive statistics

**Deliverables:**
- Aligned analysis dataset (CSV/parquet)
- Data dictionary
- Missingness report
- Descriptive statistics table

### Phase 4: Predictive Modeling (Week 4-6)

**Objective:** Test whether extracted features predict recovery outcomes.

**Tasks:**
1. Correlation matrix: all features vs all outcomes
2. Random forest: session-level features → next-day HRV delta
3. SHAP analysis: identify features carrying signal
4. Time-series cross-validation (walk-forward, no shuffling)
5. Sensitivity analysis: model stability across parameter variations

**Analysis plan:**
- Primary model: Random Forest
- Secondary: XGBoost
- Validation: Time-series CV (5-fold walk-forward)
- Metrics: R², MAE, RMSE
- Interpretation: SHAP feature importance

**Deliverables:**
- Model code and results
- SHAP visualizations
- Cross-validation performance report
- Feature importance rankings

### Phase 5: Longitudinal Validation (Week 6-8)

**Objective:** Demonstrate practical utility for training monitoring.

**Tasks:**
1. Identify training blocks (accumulation vs deload) from history
2. Test whether HRR metrics differ between block types by > SDD
3. Visualize trends with SDD bands
4. Develop case examples of meaningful deviations
5. Create monitoring dashboard prototype

**Deliverables:**
- Block-level analysis report
- Trend visualizations with SDD bands
- Case study narratives
- Dashboard mockup/prototype

---

## 11. Validation Strategy

### A. Controlled Protocol Sub-Study (Prospective)

To establish ground truth and within-person reliability, conduct standardized HRR measurement sessions with known effort and recovery timing.

**Standardized Warm-Up (choose one, use consistently):**
- 3 min rowing at fixed stroke rate (e.g., 22 spm), keeping HR in Zone 1-2
- 1 min jumping jacks (less controllable, but equipment-free)

**Effort Protocols (rotate across sessions):**

| Protocol | Description | Duration | Expected HR Response |
|----------|-------------|----------|---------------------|
| **Sandbag Shouldering** | 100 lb sandbag, continuous shouldering | 10 min | Sustained elevated HR, strength-endurance |
| **Tabata Burpees** | 20s work / 10s rest × 8 rounds (×2 sets) | 8-16 min | Peak HR near max, repeated spikes |
| **Tempo Run** | Steady state at threshold pace | 10-20 min | Sustained high HR, aerobic |
| **Hill Repeats** | 30-60s hard uphill, walk down recovery | 15-20 min | Repeated peak/recovery cycles |

**Standardized Recovery Protocol:**
- **Active recovery (default):** Remain standing, walk slowly, normal between-set behavior
- **Passive recovery (optional comparison):** Supine on mat for subset of sessions to quantify posture effect
- Minimum 2 minutes, preferably 3-5 minutes
- Record exact time of effort stop (ground truth onset)
- Log session RPE, subjective effort, environmental conditions

**Note on Recovery Position:**

Clinical HRR studies use either passive (supine) or active (slow walking) recovery protocols, which produce different absolute values [6]. Most athletes don't lie down between sets—they stand, walk around, drink water, set up for the next effort. 

This is a feature, not a limitation:
- **Ecological validity:** Measures what athletes actually do
- **Accessibility:** No behavior change required
- **Generalizability:** Results apply to real training, not lab conditions

The tradeoff: Active recovery produces smaller absolute HRR values than passive (orthostatic load keeps HR elevated). Population thresholds (e.g., "18 bpm") derived from specific protocols won't apply directly. This reinforces the core thesis: **individualized baselines matter more than population cutoffs.**

Optionally, conduct a small subset (N=5-10) of passive recovery measurements to quantify the within-person active vs passive difference. This calibration data helps interpret how your measurements relate to clinical literature.

**Data Capture:**
- Polar arm strap (primary) + Ultrahuman ring (comparison)
- Note exact timestamps: warm-up start, effort start, effort stop, recovery end
- Count reps where applicable (burpees per round, sandbag reps)

**Recommended Schedule:**
- 2-3 controlled sessions per week for 4 weeks
- Rotate protocols to get N ≥ 5 per protocol type
- Total: ~10-12 controlled recovery measurements per protocol

**Outputs:**
- Ground truth onset times for detection validation
- Paired device comparison (wrist vs arm)
- Within-protocol TE/SDD (reliability)
- Cross-protocol HRR comparison (do different efforts produce different recovery patterns?)

**Session Metadata to Record:**

| Field | Example | Purpose |
|-------|---------|--------|
| `protocol_type` | sandbag_shoulder | Cross-protocol comparison |
| `effort_duration_sec` | 600 | Dose-response analysis |
| `effort_reps` | 47 | Intensity proxy for strength |
| `effort_stop_time` | 14:32:15 | Ground truth onset |
| `recovery_position` | supine | Control for posture effect |
| `ambient_temp_f` | 45 | Environmental covariate |
| `session_rpe` | 8 | Subjective effort |
| `prior_sleep_hrs` | 6.5 | Recovery context |
| `days_since_last_session` | 1 | Fatigue context |

### B. Detection Validation (Manual Labels)

**From controlled protocols (Section A):**
- Ground truth onset = exact time of effort stop
- Compare detected onset to ground truth
- Compute onset timing error (seconds)
- Target: median error < 5 seconds

**From unstructured training:**
- Annotate onset and trough for N ≈ 50-100 intervals
- Mix of session types (running, HIIT, strength)
- Compute precision, recall, F1
- Target: Precision ≥ 0.80, Recall ≥ 0.70

**Running with walk breaks (natural experiment):**
- Your regular training includes 1-2 min walk breaks
- Each walk break = recovery interval with relatively clean onset
- High event count per session (potentially 5-10+ per long run)
- Natural variation in effort intensity, duration, environmental conditions
- Provides large N for within-person reliability without extra protocol burden

### C. Paired Device Calibration

- N ≥ 20 sessions with simultaneous wrist + chest/arm recording
- Compute bias and MAE for HRR60, event start offset
- Bland-Altman plot for device agreement
- Calibrate wrist thresholds based on chest ground truth

### D. Measurement Reliability

- From ≥10 comparable sessions, compute:
  - **Typical Error (TE):** SD of differences / √2
  - **Smallest Detectable Difference (SDD):** 1.96 × √2 × SEM
- Use SDD to set meaningful-change thresholds

### E. Longitudinal Sensitivity

- Demonstrate that block-level training changes produce HRR changes exceeding SDD
- Compare accumulation weeks vs deload weeks
- Effect size reporting (Cohen's d)

### F. Ablation Studies

- Remove individual gates (magnitude, duration, low-signal)
- Quantify impact on precision/recall
- Justify minimal gate set

---

## 12. Limitations & Constraints

### Data Quality

- **Wrist PPG:** Limited per-second fidelity; requires looser thresholds
- **Chest/arm strap:** Better signal but less historical data
- **Historical Suunto data:** Variable HR availability (some sessions lack HRM data)

### Confounders

- Heat, medications, posture, caffeine, hydration, sleep all affect HRR
- Capture covariates where possible (weather, sleep prior night)
- Report effect sizes with and without covariate adjustment

### Generalizability

- n-of-1 design: findings may not generalize to other individuals
- Single device ecosystem (Ultrahuman ring, Polar arm strap)
- Specific training style (strength + ultrarunning hybrid)

### Scope

- This is monitoring/research, not clinical diagnosis
- Treat HRR deviations as signals prompting evaluation, not conclusions
- Do not make clinical claims without symptom co-occurrence

---

## 13. Expected Outputs

### Per-Event Record Schema

```
{
  session_id,
  event_id,
  event_order,
  peak_time,
  HR_peak,
  HR_nadir,
  HR_rest_local,
  HR_30s,
  HR_60s,
  HR_120s,
  HRR30_abs,
  HRR60_abs,
  HRR120_abs,
  HRR30_frac,
  HRR60_frac,
  ratio_30_60,
  total_drop,
  time_to_nadir,
  duration_s,
  tau,
  tau_r2,
  peak_minus_rest,
  device_type,
  confidence_score,
  tag_low_signal
}
```

### Session-Level Record Schema

```
{
  session_id,
  session_date,
  session_type,
  event_count,
  hrr60_mean,
  hrr60_median,
  hrr60_sd,
  hrr60_best,
  hrr60_worst,
  total_drop_mean,
  session_load_srpe,
  ambient_temp_f,
  humidity_pct,
  location_type,
  next_day_hrv_delta,
  next_day_rhr_delta,
  next_day_sleep_score,
  next_day_readiness
}
```

---

## 14. Figures & Tables for Paper

### Figures

1. **Flow diagram:** Detection pipeline (preprocess → non-rising runs → backtrack → gates → features)
2. **Example session plot:** Detected peaks/troughs with annotated HRR30/60/120
3. **Bland-Altman plot:** Wrist vs chest/arm HRR60 agreement
4. **Histogram:** Event counts per session by type
5. **SHAP summary plot:** Feature importance for HRV prediction
6. **Longitudinal trend:** HRR60 over time with SDD bands, block annotations
7. **Correlation heatmap:** Features vs outcomes

### Tables

1. **Detection performance:** Precision, recall, F1 by session type
2. **Reliability metrics:** TE, SDD, ICC for each feature
3. **Descriptive statistics:** Feature distributions by session type
4. **Model performance:** R², MAE, RMSE across CV folds
5. **Feature importance:** Top 10 features by SHAP value
6. **Parameter sensitivity:** Detection metrics across parameter variations

---

## 15. Publication Venues

| Venue | Fit | Notes |
|-------|-----|-------|
| JMIR mHealth and uHealth | Strong | Methods + validation focus, accepts n-of-1 |
| IEEE EMBC / BSN | Strong | Conference, faster turnaround, signal processing audience |
| Journal of Sports Sciences | Moderate | Needs stronger physiological interpretation |
| PLOS ONE | Moderate | Broad audience, accepts negative results |
| Frontiers in Physiology | Moderate | Open access, sports physiology section |

---

## 16. Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Detection Validation | 1-2 weeks | Week 2 |
| Phase 2: Feature Extraction | 1 week | Week 3 |
| Phase 3: Outcome Alignment | 0.5-1 week | Week 4 |
| Phase 4: Predictive Modeling | 1-2 weeks | Week 6 |
| Phase 5: Longitudinal Validation | 1-2 weeks | Week 8 |
| Writing & Revision | 2-4 weeks | Week 12 |

**Total: 8-12 weeks to complete analysis and draft paper**

---

## 17. Minimum Viable Paper

Even if prediction models show weak effects (R² < 0.1), publishable contributions include:

1. **Methods:** Robust detection algorithm for unstructured sessions
2. **Reliability:** First published TE/SDD for wrist-derived HRR in strength training
3. **Descriptive:** Event yield per session type, feature distributions
4. **Negative result:** "Consumer wearable HRR features do not strongly predict next-day HRV" is publishable if rigorously demonstrated
5. **Device comparison:** Wrist vs arm strap bias quantification

The SHAP analysis may reveal unexpected findings—perhaps total_drop and time_to_nadir carry all signal, and clinical HRR60 adds nothing. That's a finding.

---

## Appendix A: References

### Foundational HRR Research

[1] Cole CR, Blackstone EH, Pashkow FJ, Snader CE, Lauer MS. **Heart-rate recovery immediately after exercise as a predictor of mortality.** N Engl J Med. 1999;341(18):1351-1357. doi:10.1056/NEJM199910283411804

- Landmark study establishing HRR as independent mortality predictor
- Defined abnormal HRR as ≤12 bpm at 1 minute (active recovery)
- N=2,428 patients, 6-year follow-up
- Relative risk 4.0 for abnormal vs normal HRR

[2] Cole CR, Foody JM, Blackstone EH, Lauer MS. **Heart rate recovery after submaximal exercise testing as a predictor of mortality in a cardiovascularly healthy cohort.** Ann Intern Med. 2000;132(7):552-555. doi:10.7326/0003-4819-132-7-200004040-00007

- Extended findings to healthy population without known heart disease
- Abnormal HRR predicted mortality even in low-risk individuals

[3] Nishime EO, Cole CR, Blackstone EH, Pashkow FJ, Lauer MS. **Heart rate recovery and treadmill exercise score as predictors of mortality in patients referred for exercise ECG.** JAMA. 2000;284(11):1392-1398. doi:10.1001/jama.284.11.1392

- Combined HRR with Duke treadmill score for improved risk stratification
- Abnormal HRR added prognostic value beyond exercise capacity

### Physiological Mechanisms

[4] Pierpont GL, Stolpman DR, Bhargava V. **Heart rate recovery post-exercise as an index of parasympathetic activity.** J Auton Nerv Syst. 2000;80(3):169-174. doi:10.1016/s0165-1838(00)00090-4

- Established parasympathetic reactivation as mechanism for HRR
- Demonstrated correlation between HRR and vagal tone markers

[5] Stanley J, Peake JM, Buchheit M. **Cardiac parasympathetic reactivation following exercise: implications for training prescription.** Sports Med. 2013;43(12):1259-1277. doi:10.1007/s40279-013-0083-4

- Comprehensive review of post-exercise autonomic recovery
- Discussed implications for training load monitoring
- Addressed factors affecting HRR: fitness, fatigue, environment

### Clinical Guidelines & Consumer Context

[6] Cleveland Clinic. **Heart Rate Recovery: What It Is and How to Calculate It.** Cleveland Clinic Health Library. Updated July 18, 2022. Accessed January 11, 2026. https://my.clevelandclinic.org/health/articles/23490-heart-rate-recovery

- Consumer-facing clinical guidance
- Key quote: "there isn't one magic number for everyone"
- Discusses active vs passive recovery protocols
- Notes importance of individual context

### Training Monitoring Applications

[7] Buchheit M. **Monitoring training status with HR measures: do all roads lead to Rome?** Front Physiol. 2014;5:73. doi:10.3389/fphys.2014.00073

- Review of HR-based training monitoring methods
- Discussed HRR alongside HRV for athlete monitoring
- Addressed day-to-day variability and meaningful change thresholds

[8] Daanen HAM, Lamberts RP, Stam WT, Swaart KS, Sentija D. **A systematic review on heart-rate recovery to monitor changes in training status in athletes.** Int J Sports Physiol Perform. 2012;7(3):251-260. doi:10.1123/ijspp.7.3.251

- Systematic review of HRR for training status monitoring
- Found limited evidence for HRR sensitivity to training changes
- Highlighted need for individualized approaches and larger samples

### Measurement Reliability

[9] Bosquet L, Gamelin FX, Berthoin S. **Reliability of postexercise heart rate recovery.** Int J Sports Med. 2008;29(3):238-243. doi:10.1055/s-2007-965162

- Established reliability metrics for HRR measurement
- Reported typical error and smallest worthwhile change
- Basis for SDD calculations in longitudinal monitoring

[10] Lamberts RP, Swart J, Capostagno B, Noakes TD, Lambert MI. **Heart rate recovery as a guide to monitor fatigue and predict changes in performance parameters.** Scand J Med Sci Sports. 2010;20(3):449-457. doi:10.1111/j.1600-0838.2009.00977.x

- Demonstrated HRR changes with training load manipulation
- Showed sensitivity to overreaching in cyclists
- Supported use of HRR for fatigue monitoring

### Wearable Device Validation

[11] Gilgen-Ammann R, Schweizer T, Wyss T. **RR interval signal quality of a heart rate monitor and an ECG Holter at rest and during exercise.** Eur J Appl Physiol. 2019;119(7):1525-1532. doi:10.1007/s00421-019-04142-5

- Validated consumer HR monitors against ECG
- Quantified accuracy during rest and exercise
- Relevant for understanding device-specific measurement error

[12] Bent B, Goldstein BA, Kibbe WA, Dunn JP. **Investigating sources of inaccuracy in wearable optical heart rate sensors.** NPJ Digit Med. 2020;3:18. doi:10.1038/s41746-020-0226-6

- Characterized PPG sensor limitations
- Identified motion artifact as primary error source
- Relevant for device-specific threshold tuning

### Wearable HRR and Machine Learning

[13] Natarajan A, Su HW, Heneghan C. **Assessment of physiological signs associated with COVID-19 measured using wearable devices.** NPJ Digit Med. 2020;3:156. doi:10.1038/s41746-020-00363-7

- Early work on extracting physiological features from consumer wearables
- Demonstrated feasibility of automated feature extraction from continuous HR streams
- PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC8811688/

[14] EMJ Reviews. **Smart ECG shirt monitors heart rate recovery, predicts cardiovascular risk.** EMJ Cardiology. 2025.

- University of Illinois study using smart-ECG shirt
- ML classifiers achieved ~86% accuracy for risk classification
- Used 1-minute HRR threshold around 28 bpm
- https://www.emjreviews.com/cardiology/news/smart-ecg-shirt-monitors-heart-rate-recovery-predicts-cardiovascular-risk/

[15] Dunn J, Kidzinski L, Runge R, et al. **Wearable sensors enable personalized predictions of clinical laboratory measurements.** J Med Internet Res. 2022;7:e34669. doi:10.2196/34669

- "Digital phenotype" study with high-resolution HR and steps from consumer wearables
- Extracted HRR-like post-stress slopes as features
- Associated with cardiometabolic risk beyond resting HR
- https://www.jmir.org/2022/7/e34669/

[16] Xu Y, Marsden AL, Hunter C, et al. **A hybrid physiological and machine learning model for predicting exercise heart rate response.** Nat Digit Med. 2023. doi:10.1038/s41746-023-00926-4

- Hybrid physiological + ML model predicting full HR response curve
- Learns personalized recovery trajectories from wearable data
- Could derive individualized HRR metrics for new workouts
- https://www.nature.com/articles/s41746-023-00926-4

[17] University of Illinois News. **Wearable technology continuously monitors heart rate recovery to predict risk.** Illinois News Bureau. 2025.

- Press coverage of smart-ECG shirt study
- Continuous HRR tracking during treadmill walking
- https://news.illinois.edu/wearable-technology-continuously-monitors-heart-rate-recovery-to-predict-risk/

[18] Chkeir A, et al. **Digital frailty assessment using wearable heart rate and gait analysis.** BMC Geriatr. 2024. doi:10.1186/s12877-024-05421-5

- Wearable HR + gait mechanics in daily life
- Automatic detection of peak HR and recovery episodes
- HRR predicted frailty with AUC 0.80–0.86
- PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC11487206/

### Additional Relevant Work

[19] Ballinger B, Hsieh J, Singh A, et al. **DeepHeart: Semi-supervised sequence learning for cardiovascular risk prediction.** arXiv. 2018;1807.04667.

- Deep learning on wearable HR time series
- Semi-supervised approach for cardiovascular risk
- https://arxiv.org/abs/1807.04667

[20] Perez MV, Mahaffey KW, Hedlin H, et al. **Large-scale assessment of a smartwatch to identify atrial fibrillation.** N Engl J Med. 2019;381(20):1909-1917. doi:10.1056/NEJMoa1901183

- Apple Heart Study demonstrating clinical utility of consumer wearables
- Established precedent for wearable-derived cardiac insights

[21] Bent B, Cho PJ, Henriquez M, et al. **Engineering digital biomarkers of interstitial glucose from noninvasive smartwatches.** NPJ Digit Med. 2021;4:89. doi:10.1038/s41746-021-00465-w

- Methodology for extracting clinically relevant features from wearables
- Relevant for feature engineering approach

---

## Appendix B: Code Repository Structure

```
arnold/
├── scripts/
│   ├── hrr_detection.py          # Non-rising run detection
│   ├── hrr_features.py           # Feature extraction
│   ├── hrr_weather.py            # Weather API integration
│   └── hrr_analysis.py           # Modeling and visualization
├── docs/
│   └── hrr_research_protocol.md  # This document
├── notebooks/
│   ├── 01_detection_validation.ipynb
│   ├── 02_reliability_analysis.ipynb
│   ├── 03_predictive_modeling.ipynb
│   └── 04_longitudinal_analysis.ipynb
└── data/
    ├── labeled_events.csv        # Manual labels for validation
    └── analysis_dataset.parquet  # Aligned features + outcomes
```

---

## Appendix C: Checklist Before Proceeding

- [ ] Verify HRV data availability and date range (Ultrahuman)
- [ ] Count sessions with usable HR data by source
- [ ] Identify sessions with paired devices (wrist + arm/chest)
- [ ] Define subjective readiness scale for journal entries
- [ ] Set up weather API integration
- [ ] Create location_type metadata for existing sessions
