# Arnold Metrics Reference

> **Purpose**: Document the semantics, sources, and limitations of each metric.
> This is the foundation for the data intelligence layer.

---

## Biometric Metrics

### Heart Rate Variability (HRV)

| Property | Value |
|----------|-------|
| **Field** | `hrv_ms`, `hrv_morning` |
| **Unit** | milliseconds (ms) |
| **Source** | Ultrahuman Ring (PPG sensor) |
| **Measurement** | Morning average, measured during sleep |
| **Algorithm** | Likely RMSSD (Root Mean Square of Successive Differences) |
| **Typical range** | 20-60ms (varies by individual, age, fitness) |

**Interpretation:**
- Higher = better parasympathetic tone, better recovery
- Day-to-day variation is normal (±20%)
- Look at 7-day rolling average for trends
- Individual baseline matters more than absolute values

**Limitations:**
- PPG (optical) less accurate than ECG
- Alcohol, caffeine, late meals affect readings
- Can't compare across different devices/algorithms
- Apple Health HRV uses different algorithm (see Issue #4)

**Statistical considerations:**
- Non-normal distribution; median may be more robust than mean
- Coefficient of variation (CV) can indicate autonomic flexibility
- Requires 7+ days for reliable trend detection

---

### HRV Coefficient of Variation (HRV CV)

| Property | Value |
|----------|-------|
| **Field** | `hrv_cv_7d` (computed) |
| **Unit** | percentage (%) |
| **Calculation** | (SD(HRV over 7 days) / Mean(HRV over 7 days)) × 100 |
| **Source** | Derived from daily HRV readings |

**Interpretation:**
- < 3%: Suppressed autonomic flexibility → possible overreaching
- 3-10%: Normal healthy variation
- 10-15%: Elevated → inconsistent recovery or lifestyle stress
- > 15%: Very high → investigate sleep, stress, alcohol, etc.

**Key insight**: CV is more predictive than absolute HRV because it normalizes for individual differences and detects autonomic saturation during heavy training.

**Limitations:**
- Requires 7+ days of consistent data
- Affected by measurement timing consistency
- Single outlier can skew 7-day window

---

### Resting Heart Rate (RHR)

| Property | Value |
|----------|-------|
| **Field** | `rhr_bpm`, `resting_hr` |
| **Unit** | beats per minute (bpm) |
| **Source** | Ultrahuman Ring (PPG sensor) |
| **Measurement** | Lowest sustained HR during sleep |
| **Typical range** | 45-75 bpm (athletes often lower) |

**Interpretation:**
- Lower = generally better cardiovascular fitness
- Elevated RHR can indicate: fatigue, illness, stress, overtraining
- ~5+ bpm above baseline warrants attention
- Inverse relationship with HRV (usually)

**Limitations:**
- Affected by hydration, temperature, alcohol
- Fitness improvements take weeks to manifest
- Individual variation is high

---

### Sleep Duration

| Property | Value |
|----------|-------|
| **Field** | `sleep_total_min`, `sleep_hours` |
| **Unit** | minutes / hours |
| **Source** | Ultrahuman Ring (accelerometer + PPG) |
| **Measurement** | Total time in bed classified as sleep |

**Sleep stages:**
- `sleep_deep_min`: Deep/slow-wave sleep (restorative)
- `sleep_rem_min`: REM sleep (cognitive recovery)
- `sleep_light_min`: Light sleep (transition)
- `sleep_awake_min`: Awake periods during night

**Derived metrics:**
- `restorative_pct`: (deep + REM) / total * 100
- Target: 7-9 hours total, >25% restorative

**Limitations:**
- Consumer devices overestimate sleep time
- Stage classification has ~70% accuracy vs. polysomnography
- Doesn't capture sleep quality subjectively

---

### Sleep Debt

| Property | Value |
|----------|-------|
| **Field** | `sleep_debt_7d` (computed) |
| **Unit** | hours |
| **Calculation** | Σ(Target - Actual) over 7 days |
| **Target** | 7.5 hours (configurable) |

**Interpretation:**
- < 0: Sleep surplus (well-rested)
- 0-3 hrs: Minor deficit, easily recovered
- 3-5 hrs: Moderate → performance impact likely
- 5-10 hrs: Significant → cognitive/physical impairment
- > 10 hrs: Critical → may take weeks to recover

**Key insight**: Sleep debt is cumulative. Five nights of 6.5 hours creates a 5-hour debt that doesn't disappear with one good night.

**Limitations:**
- Consumer devices overestimate sleep time
- Doesn't account for sleep quality
- Recovery from debt is non-linear (takes longer than debt accumulated)

---

### Recovery Score

| Property | Value |
|----------|-------|
| **Field** | `recovery_score` |
| **Unit** | percentage (0-100) |
| **Source** | Ultrahuman (composite algorithm) |
| **Components** | HRV, RHR, sleep, activity patterns |

**Interpretation:**
- Proprietary composite score
- Useful for relative trends, not absolute comparisons
- Correlates with readiness for high-intensity training

**Limitations:**
- Algorithm is opaque (black box)
- May not align with perceived readiness
- Use as one input among many, not gospel

---

## Training Load Metrics

### Volume (lbs)

| Property | Value |
|----------|-------|
| **Field** | `total_volume_lbs` |
| **Unit** | pounds |
| **Calculation** | Σ(sets × reps × weight) per workout |
| **Source** | Neo4j workout logs |

**Interpretation:**
- Raw measure of work performed
- Useful for week-over-week comparisons
- Different exercises aren't equivalent (deadlift ≠ curl)

**Limitations:**
- Doesn't account for effort/RPE
- Bodyweight exercises underrepresented
- Cardio not captured in this metric

---

### TRIMP (Training Impulse)

| Property | Value |
|----------|-------|
| **Field** | `trimp` (in polar_sessions) |
| **Unit** | arbitrary units |
| **Calculation** | Duration × HR intensity factor |
| **Source** | Polar HR data |

**Interpretation:**
- Accounts for both duration and intensity
- Standard for endurance training load
- Can be summed across sessions

**Limitations:**
- Requires HR data (not available for all sessions)
- Strength training underrepresented
- HR zones need individual calibration

---

### ACWR (Acute:Chronic Workload Ratio)

| Property | Value |
|----------|-------|
| **Field** | `acwr` |
| **Unit** | ratio |
| **Calculation** | 7-day avg load / 28-day avg load |
| **Source** | Calculated from training_load_daily |

**Interpretation:**
| ACWR | Zone | Meaning |
|------|------|---------|
| < 0.8 | Undertrained | Detraining risk |
| 0.8 - 1.0 | Sweet spot | Optimal adaptation |
| 1.0 - 1.3 | Productive | Overreach, monitor recovery |
| 1.3 - 1.5 | Caution | Elevated injury risk |
| > 1.5 | Danger | High injury risk |

**Limitations:**
- Based on Banister/Gabbett research, primarily endurance athletes
- Doesn't account for training type (strength vs cardio)
- Post-injury/layoff periods distort the ratio
- Currently using volume; TRIMP would be better for mixed training

**Statistical considerations:**
- Rolling averages smooth day-to-day noise
- Need 28+ days of data for meaningful chronic load
- Spikes are more predictive of injury than absolute values

---

### Training Monotony

| Property | Value |
|----------|-------|
| **Field** | `monotony_7d` (computed) |
| **Unit** | ratio (dimensionless) |
| **Calculation** | Mean(daily load, 7d) / SD(daily load, 7d) |
| **Source** | Daily training volume |

**Interpretation:**
- < 1.5: Good variation in training
- 1.5 - 2.0: Monitor → getting repetitive
- > 2.0: High monotony → staleness/overtraining risk

**Key insight**: Same load every day = high monotony. Varied load = low monotony. The body adapts better to varied stimuli.

**Limitations:**
- Rest days count as zero → can artificially lower monotony
- Different training types (strength vs cardio) should ideally be tracked separately

---

### Training Strain

| Property | Value |
|----------|-------|
| **Field** | `strain_7d` (computed) |
| **Unit** | arbitrary units |
| **Calculation** | Weekly Load × Monotony |
| **Source** | Derived from volume and monotony |

**Interpretation:**
- < 3000: Low strain → well tolerated
- 3000 - 6000: Moderate → productive training
- > 6000: High strain → elevated illness/injury risk

**Key insight**: Strain combines HOW MUCH you trained with HOW REPETITIVE it was. High volume with high monotony = danger zone.

**Citation**: Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome.

---

## Data Quality Indicators

### Completeness

| Metric | Threshold | Interpretation |
|--------|-----------|----------------|
| 7-day completeness | > 70% (5/7 days) | Minimally reliable |
| 30-day completeness | > 80% | Good trend detection |
| 90-day completeness | > 70% | Seasonal patterns visible |

### Freshness

| Metric | Threshold | Action |
|--------|-----------|--------|
| Days since HRV | ≤ 2 | Normal |
| Days since HRV | 3-7 | Check ring charging/sync |
| Days since HRV | > 7 | Data pipeline issue |

---

## Time Horizons

| Horizon | Days | Use Case |
|---------|------|----------|
| Week | 7 | Acute load, recent readiness |
| Month | 30 | Training block effectiveness |
| Quarter | 90 | Macro trends, seasonal patterns |
| Annual | 365 | Year-over-year comparison |

**Graceful degradation:**
- Reports work with whatever data exists
- Shorter horizons shown first
- Longer horizons only when sufficient data

---

## Future Metrics

See [TRAINING_METRICS.md](./TRAINING_METRICS.md) for full specifications.

**Implemented (Migration 011):**
- **Training Monotony**: `training_monotony_strain.monotony`
- **Training Strain**: `training_monotony_strain.strain`
- **HRV CV**: `biometric_derived.hrv_cv_7d`
- **Sleep Debt**: `biometric_derived.sleep_debt_hours_7d`
- **Readiness Composite**: `readiness_composite` view with `get_readiness()` function

**Implemented (Jan 2026):**
- **Pattern Last Trained**: `pattern_last_trained` view — days since each movement pattern
- **Muscle Volume Weekly**: `muscle_volume_weekly` view — sets/reps/volume per muscle per week
- **Exercise Relationship Cache**: `neo4j_cache_exercise_patterns`, `neo4j_cache_exercise_muscles`

**Not Yet Implemented:**
- **hrTSS / ATL / CTL / TSB**: Needs HR-workout linkage
- **Pattern Balance Score**: How evenly movement patterns are trained
- **Race Performance Index**: Normalized race times for longitudinal comparison

---

## Coaching Feedback Loop (Design Pattern)

A good coach doesn't just observe — they *probe*. When objective metrics indicate something worth investigating, Coach should prompt for subjective feedback to close the control loop.

### Trigger → Prompt Pattern

| Objective Trigger | Subjective Prompt |
|------------------|-------------------|
| HRV -15% from baseline | "How are your energy levels today? Feeling recovered?" |
| HRV CV < 3% (suppressed) | "Have you been feeling flat or stale in training lately?" |
| Sleep debt > 5 hrs | "How's your sleep been? Any trouble falling or staying asleep?" |
| ACWR > 1.3 | "How do your legs feel? Any unusual soreness or tightness?" |
| Monotony > 2.0 | "Is training feeling repetitive? Ready for some variety?" |
| Pattern gap > 10d | "Any reason you've been avoiding [pattern]? Discomfort?" |
| Missed planned workout | "What got in the way yesterday?" |

### Feedback Integration

Subjective responses should be captured as journal entries with:
1. **Link to triggering metric** (so we can correlate)
2. **Extracted structured data** (fatigue: 7/10, soreness: legs)
3. **Tags for retrieval** (fatigue, legs, post-workout)

### Control Loop Closure

```
Objective Data (sensors)      Subjective Data (journal)
        │                              │
        └─────────────┬──────────────┘
                      │
              ┌───────┴───────┐
              │   Coach AI    │
              │  (synthesis)  │
              └───────┬───────┘
                      │
              ┌───────┴───────┐
              │   Decision    │
              │ (program adj) │
              └───────────────┘
```

Without subjective feedback, it's an open-loop system — Coach can observe but can't verify. With feedback, Coach can:
- Validate that sensor anomalies reflect actual state
- Detect issues sensors can't measure (mood, motivation, pain)
- Build athlete-specific response profiles over time

---

## References

1. Gabbett TJ. The training-injury prevention paradox: should athletes be training smarter and harder? *Br J Sports Med*. 2016.
2. Plews DJ, et al. Training adaptation and heart rate variability in elite endurance athletes. *Int J Sports Physiol Perform*. 2013.
3. Buchheit M. Monitoring training status with HR measures. *Int J Sports Physiol Perform*. 2014.
