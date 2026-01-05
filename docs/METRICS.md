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

## Future Metrics (Not Yet Implemented)

- **Training Monotony**: Consistency vs variety of load
- **Training Strain**: Week load / monotony
- **Readiness Index**: Composite of HRV, sleep, subjective
- **Pattern Balance Score**: How evenly movement patterns are trained
- **Race Performance Index**: Normalized race times for longitudinal comparison

---

## References

1. Gabbett TJ. The training-injury prevention paradox: should athletes be training smarter and harder? *Br J Sports Med*. 2016.
2. Plews DJ, et al. Training adaptation and heart rate variability in elite endurance athletes. *Int J Sports Physiol Perform*. 2013.
3. Buchheit M. Monitoring training status with HR measures. *Int J Sports Physiol Perform*. 2014.
