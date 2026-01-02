# Training Metrics Specification

> **Purpose**: Evidence-based training metrics for Arnold's coaching decisions
> **Last Updated**: January 1, 2026
> **Author**: Defined in collaboration between Brock Webb and Claude

---

## Overview

Arnold uses a tiered approach to training metrics based on data availability and evidence quality. All metrics are grounded in peer-reviewed sports science literature with explicit citations.

---

## Tier 1: Strength Training Metrics (Calculated from Logged Workouts)

These metrics can be calculated immediately from the workout data already in Neo4j/DuckDB.

### 1.1 Volume Load (Tonnage)

**Definition**: Total mechanical work performed.

```
Volume Load = Σ (sets × reps × load_lbs)
```

**Timeframes**: Per workout, rolling 7d, rolling 28d, per exercise

**Use Case**: 
- Track total training stress
- Compare across training phases
- Input to ACWR calculation

**Citation**: 
> Haff, G.G. (2010). Quantifying Workloads in Resistance Training: A Brief Review. *Strength and Conditioning Journal*, 32(6), 21-25.

---

### 1.2 Sets Per Muscle Group Per Week

**Definition**: Count of working sets targeting each muscle group in a rolling 7-day window.

**Evidence-Based Targets**:

| Level | Sets/Week/Muscle | Citation |
|-------|------------------|----------|
| Minimum effective (hypertrophy) | 4 sets | Schoenfeld et al. (2017) |
| Optimal range | 10-20 sets | Schoenfeld et al. (2017); Wernbom et al. (2007) |
| Upper limit (recovery concern) | >15 sets | Israetel et al. (2019) |

**Per-Session Limit**:
> "Performing more than 8 sets per muscle group within a workout only leads to additional fatigue rather than contributing to more muscle growth."
> — Ochi et al. (2018). Higher training frequency is important for gaining muscular strength under volume-matched training. *Frontiers in Physiology*, 9, 744.

**Use Case**:
- Volume distribution monitoring
- Identify neglected muscle groups
- Guide session structure

**Citations**:
> Schoenfeld, B.J., Ogborn, D., & Krieger, J.W. (2017). Dose-response relationship between weekly resistance training volume and increases in muscle mass: A systematic review and meta-analysis. *Journal of Sports Sciences*, 35(11), 1073-1082.

> Wernbom, M., Augustsson, J., & Thomeé, R. (2007). The influence of frequency, intensity, volume and mode of strength training on whole muscle cross-sectional area in humans. *Sports Medicine*, 37(3), 225-264.

---

### 1.3 Movement Pattern Frequency

**Definition**: Days since last training of each movement pattern.

**Patterns Tracked**:
- Hip Hinge
- Squat
- Vertical Pull
- Vertical Push
- Horizontal Pull
- Horizontal Push
- Carry
- Core (Anti-Extension, Anti-Rotation, Anti-Lateral Flexion)

**Evidence-Based Target**:
> Training each muscle group at least twice per week promoted superior hypertrophic outcomes compared to once per week, with an effect size of 0.49 for higher frequency versus 0.30 for lower frequency.
> — Schoenfeld, B.J., Ogborn, D., & Krieger, J.W. (2016). Effects of Resistance Training Frequency on Measures of Muscle Hypertrophy: A Systematic Review and Meta-Analysis. *Sports Medicine*, 46(11), 1689-1697.

**Use Case**:
- Identify pattern gaps
- Balance training distribution
- Suggest today's focus

---

### 1.4 ACWR (Acute:Chronic Workload Ratio) - Strength

**Definition**: Ratio of recent training load to baseline training load.

```
ACWR = Acute Load (7-day) / Chronic Load (28-day rolling average)
```

**Risk Zones**:

| ACWR | Risk Level | Interpretation |
|------|------------|----------------|
| < 0.8 | Undertrained | Detraining risk, not prepared for demands |
| 0.8 - 1.3 | Sweet Spot | Optimal adaptation, low injury risk |
| 1.3 - 1.5 | Caution | Elevated injury risk, monitor closely |
| > 1.5 | Danger | High injury risk, reduce load |

**Calculation Method**: 
We use EWMA (Exponentially Weighted Moving Average) rather than simple rolling average:

> "The EWMA is more sensitive to changes in workload and provides a more accurate injury risk assessment than the rolling average model."
> — Murray, N.B., Gabbett, T.J., Townshend, A.D., & Blanch, P. (2017). Calculating acute:chronic workload ratios using exponentially weighted moving averages provides a more sensitive indicator of injury likelihood than rolling averages. *British Journal of Sports Medicine*, 51(9), 749-754.

**EWMA Formula**:
```
EWMA_today = Load_today × λ + EWMA_yesterday × (1 - λ)

Where:
- λ_acute = 2 / (7 + 1) = 0.25
- λ_chronic = 2 / (28 + 1) ≈ 0.069
```

**Use Case**:
- Prevent load spikes (injury prevention)
- Guide deload timing
- Validate periodization is working

**Primary Citation**:
> Gabbett, T.J. (2016). The training—injury prevention paradox: should athletes be training smarter and harder? *British Journal of Sports Medicine*, 50(5), 273-280.

**Supporting Citations**:
> Blanch, P., & Gabbett, T.J. (2016). Has the athlete trained enough to return to play safely? The acute:chronic workload ratio permits clinicians to quantify a player's risk of subsequent injury. *British Journal of Sports Medicine*, 50(8), 471-475.

> Hulin, B.T., Gabbett, T.J., Lawson, D.W., Caputi, P., & Sampson, J.A. (2016). The acute:chronic workload ratio predicts injury: high chronic workload may decrease injury risk in elite rugby league players. *British Journal of Sports Medicine*, 50(4), 231-236.

---

### 1.5 Training Monotony

**Definition**: Measure of training variation. High monotony = doing the same thing daily = overtraining risk.

```
Monotony = Mean(Daily Load over 7 days) / SD(Daily Load over 7 days)
```

**Interpretation**:
- Low monotony (< 1.5): Good variation
- Moderate monotony (1.5 - 2.0): Monitor
- High monotony (> 2.0): Risk of staleness/overtraining

**Citation**:
> Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome. *Medicine & Science in Sports & Exercise*, 30(7), 1164-1168.

---

### 1.6 Training Strain

**Definition**: Combined measure of load and monotony.

```
Strain = Weekly Load × Monotony
```

**Interpretation**:
High strain values are associated with illness and injury. Used as early warning system.

**Citation**:
> Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome. *Medicine & Science in Sports & Exercise*, 30(7), 1164-1168.

---

### 1.7 Exercise Progression (Estimated 1RM)

**Definition**: Track strength gains over time per exercise using estimated 1RM.

**Brzycki Formula**:
```
Estimated 1RM = Weight × (36 / (37 - Reps))
```

Valid for reps ≤ 10. Alternative formulas (Epley, Lombardi) available.

**Use Case**:
- Track progress toward goals (e.g., Deadlift 405)
- Identify stalled lifts
- Validate programming effectiveness

**Citation**:
> Brzycki, M. (1993). Strength Testing—Predicting a One-Rep Max from Reps-to-Fatigue. *Journal of Physical Education, Recreation & Dance*, 64(1), 88-90.

---

## Tier 2: Biometric-Enhanced Metrics (Require HRV, Sleep, HR Data)

These metrics require wearable data from Ultrahuman, Apple Health, or similar sources.

### 2.1 Readiness Score

**Definition**: Composite assessment of training readiness based on multiple inputs.

**Components**:
- HRV trend (vs personal baseline)
- Sleep quality and duration
- Resting heart rate trend
- Recent training strain
- Recovery score (if available from Ultrahuman)

**Arnold's Readiness Classification**:

| Status | Criteria | Coaching Action |
|--------|----------|-----------------|
| 🟢 Ready | HRV normal, sleep >6.5h, RHR normal | Train as planned |
| 🟡 Caution | HRV -10% or sleep <6h or RHR +5% | Reduce intensity, extend warmup |
| 🔴 Recover | HRV -20% or sleep <5h or illness signs | Light movement only or rest |

**Citation**:
> Plews, D.J., Laursen, P.B., Stanley, J., Kilding, A.E., & Buchheit, M. (2013). Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. *Sports Medicine*, 43(9), 773-781.

---

### 2.2 hrTSS (Heart Rate Training Stress Score)

**Definition**: Training load quantification for cardio activities based on heart rate.

**Formula**:
```
hrTSS = (Duration_seconds × hrIF × HRR_factor) / (LTHR × 3600) × 100

Where:
- hrIF (Intensity Factor) = Avg HR / LTHR
- HRR_factor = (Avg HR - Resting HR) / (Max HR - Resting HR)
- LTHR (Lactate Threshold HR) ≈ 0.85 × Max HR (or from field test)
- Max HR estimate = 220 - age (or actual if known)
```

**For Brock (age 50)**:
- Estimated Max HR: 220 - 50 = 170 bpm
- Estimated LTHR: 0.85 × 170 = 144.5 bpm
- Resting HR: ~50 bpm (from Ultrahuman data)

**TSS Reference Points**:
| Activity | Typical TSS |
|----------|-------------|
| 1 hour easy run | 40-60 |
| 1 hour threshold effort | 100 |
| 1 hour all-out race | 150+ |
| Strength session (moderate) | 30-50 |

**Primary Citation**:
> Coggan, A.R. (2003). Training and racing using a power meter: An introduction. *USA Cycling Level 2 Coaching Manual*.

**Note**: TSS was originally developed by TrainingPeaks for power-based cycling. hrTSS is the heart rate adaptation.

---

### 2.3 ATL (Acute Training Load) / Fatigue

**Definition**: Short-term training stress accumulation.

```
ATL = EWMA of daily TSS with λ = 2/(7+1) = 0.25
```

Represents recent training load / current fatigue level.

---

### 2.4 CTL (Chronic Training Load) / Fitness

**Definition**: Long-term training stress accumulation.

```
CTL = EWMA of daily TSS with λ = 2/(42+1) ≈ 0.047
```

Represents training base / fitness level.

**Citation**:
> Banister, E.W., Calvert, T.W., Savage, M.V., & Bach, T. (1975). A systems model of training for athletic performance. *Australian Journal of Sports Medicine*, 7, 57-61.

---

### 2.5 TSB (Training Stress Balance) / Form

**Definition**: Balance between fitness and fatigue.

```
TSB = CTL - ATL
```

**Interpretation**:
| TSB | State | Interpretation |
|-----|-------|----------------|
| Positive (> +10) | Fresh | Rested, ready to race |
| Near zero (-10 to +10) | Optimal training | Building fitness |
| Negative (< -10) | Fatigued | Heavy training block |
| Very negative (< -30) | Overreaching | Risk zone, need recovery |

**Citation**:
> Banister, E.W. (1991). Modeling elite athletic performance. In J.D. MacDougall, H.A. Wenger, & H.J. Green (Eds.), *Physiological Testing of the High-Performance Athlete* (2nd ed., pp. 403-424). Human Kinetics.

---

## Tier 3: External Source Metrics (Require Suunto/Platform Export)

These metrics are calculated by external platforms. We can import them if available, or calculate equivalents using Tier 2 methods.

### 3.1 Suunto TSS

**What Suunto Provides**:
> "TSS is automatically calculated based on activity type and data available. Usually heart rate data is used, but in activities like running and swimming TSS is calculated based on threshold pace."
> — Suunto Support Documentation

**Suunto also calculates**:
- ATL (Acute Training Load) - 7-day EWMA
- CTL (Chronic Training Load) - 42-day EWMA  
- TSB (Training Stress Balance) = CTL - ATL

**Data Availability**:
- ❌ TSS does NOT sync to Apple Health
- ✅ TSS is stored in FIT files (manual export)
- ✅ TSS visible in Suunto app Progress view
- 🔄 May be available via Suunto API (not yet explored)

**Fallback**: Use hrTSS calculated from HR data in Apple Health.

---

### 3.2 rTSS (Running TSS)

**Definition**: Pace-based TSS for running, more accurate than hrTSS for trained runners.

Requires functional threshold pace (FTP) setting in watch.

**When Available**: Only from Suunto/Garmin exports, not Apple Health.

**Fallback**: hrTSS from HR data.

---

## Modality-Specific ACWR

**Key Insight**: Different modalities don't share fatigue equally. Running load doesn't directly impact deadlift recovery (though systemic fatigue exists).

**Recommended Approach**: Calculate separate ACWR per modality:

| Modality | Load Metric |
|----------|-------------|
| Strength (all patterns) | Volume Load (reps × weight) |
| Running/Cardio | TSS or hrTSS |
| Kickboxing | Duration × RPE (or hrTSS if HR available) |

**Combined Load** for global fatigue assessment can normalize to TSS-equivalents:
- 1 hour strength at RPE 7 ≈ 50-70 TSS
- 1 hour easy run ≈ 50 TSS
- 1 hour threshold run ≈ 100 TSS

---

## Balance Ratios

### Push:Pull Ratio

```
Push:Pull = (Chest + Shoulders + Triceps volume) / (Back + Biceps + Forearms volume)
```

**Target**: 0.6 - 1.0 (slight pull dominance is healthier for posture)

### Upper:Lower Ratio

```
Upper:Lower = (All upper body volume) / (All lower body volume)
```

**Target**: 0.8 - 1.2 (balanced)

### Quad:Hamstring Ratio

```
Quad:Ham = Quadriceps volume / Hamstring volume
```

**Target**: 1.0 - 1.5 (slight quad dominance is normal)

---

## Data Pipeline

### What Arnold Can Calculate Now (Tier 1)

| Metric | Data Source | Refresh |
|--------|-------------|---------|
| Volume Load | Neo4j sets | After each workout |
| Sets/Muscle/Week | Neo4j sets → muscles | Rolling |
| Pattern Frequency | Neo4j workouts → patterns | Rolling |
| ACWR (Strength) | Neo4j sets | Daily |
| Monotony/Strain | Neo4j workouts | Weekly |
| Exercise Progression | Neo4j sets | Per exercise |

### What Requires Biometric Data (Tier 2)

| Metric | Data Source | Gap |
|--------|-------------|-----|
| Readiness Score | Ultrahuman HRV, sleep | HRV gap Dec 6 → present |
| hrTSS | Apple Health HR during workouts | Need Polar paired during sessions |
| ATL/CTL/TSB | Calculated from TSS | Depends on hrTSS quality |

### What Requires External Import (Tier 3)

| Metric | Data Source | Status |
|--------|-------------|--------|
| Suunto TSS | FIT files or API | Manual export only |
| rTSS | Suunto running activities | Not in Apple Health |

---

## Coaching Decision Matrix

| Metric | Threshold | Coaching Response |
|--------|-----------|-------------------|
| ACWR > 1.5 | 🔴 | Reduce volume 20-30%, prioritize recovery |
| ACWR < 0.8 | 🟡 | Increase volume gradually (10%/week max) |
| Monotony > 2.0 | 🟡 | Add variation, change exercises or rep ranges |
| Pattern gap > 7d | 🟡 | Prioritize that pattern in next session |
| Sets/muscle/week < 4 | 🟡 | Insufficient stimulus, add volume |
| Sets/muscle/week > 20 | 🟡 | Potential overtraining, monitor recovery |
| HRV -20% from baseline | 🔴 | Recovery day or light movement only |
| Sleep < 6h | 🟡 | Reduce intensity, extend warmup |
| TSB < -30 | 🔴 | Planned overreach or deload needed |

---

## References (Full)

### Workload Management

1. Gabbett, T.J. (2016). The training—injury prevention paradox: should athletes be training smarter and harder? *British Journal of Sports Medicine*, 50(5), 273-280.

2. Murray, N.B., Gabbett, T.J., Townshend, A.D., & Blanch, P. (2017). Calculating acute:chronic workload ratios using exponentially weighted moving averages provides a more sensitive indicator of injury likelihood than rolling averages. *British Journal of Sports Medicine*, 51(9), 749-754.

3. Blanch, P., & Gabbett, T.J. (2016). Has the athlete trained enough to return to play safely? The acute:chronic workload ratio permits clinicians to quantify a player's risk of subsequent injury. *British Journal of Sports Medicine*, 50(8), 471-475.

4. Hulin, B.T., Gabbett, T.J., Lawson, D.W., Caputi, P., & Sampson, J.A. (2016). The acute:chronic workload ratio predicts injury: high chronic workload may decrease injury risk in elite rugby league players. *British Journal of Sports Medicine*, 50(4), 231-236.

### Training Volume

5. Schoenfeld, B.J., Ogborn, D., & Krieger, J.W. (2017). Dose-response relationship between weekly resistance training volume and increases in muscle mass: A systematic review and meta-analysis. *Journal of Sports Sciences*, 35(11), 1073-1082.

6. Wernbom, M., Augustsson, J., & Thomeé R. (2007). The influence of frequency, intensity, volume and mode of strength training on whole muscle cross-sectional area in humans. *Sports Medicine*, 37(3), 225-264.

7. Ochi, E., Maruo, M., Tsuchiya, Y., Ishii, N., Miura, K., & Sasaki, K. (2018). Higher training frequency is important for gaining muscular strength under volume-matched training. *Frontiers in Physiology*, 9, 744.

8. Schoenfeld, B.J., Ogborn, D., & Krieger, J.W. (2016). Effects of Resistance Training Frequency on Measures of Muscle Hypertrophy: A Systematic Review and Meta-Analysis. *Sports Medicine*, 46(11), 1689-1697.

### Training Monitoring

9. Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome. *Medicine & Science in Sports & Exercise*, 30(7), 1164-1168.

10. Haff, G.G. (2010). Quantifying Workloads in Resistance Training: A Brief Review. *Strength and Conditioning Journal*, 32(6), 21-25.

11. Suchomel, T.J., Nimphius, S., Bellon, C.R., Hornsby, W.G., & Stone, M.H. (2021). Training for Muscular Strength: Methods for Monitoring and Adjusting Training Intensity. *Sports Medicine*, 51(10), 2051-2066.

### Periodization

12. Bompa, T.O., & Haff, G.G. (2009). *Periodization: Theory and Methodology of Training* (5th ed.). Human Kinetics.

13. Issurin, V.B. (2010). New horizons for the methodology and physiology of training periodization. *Sports Medicine*, 40(3), 189-206.

### Fitness-Fatigue Model

14. Banister, E.W., Calvert, T.W., Savage, M.V., & Bach, T. (1975). A systems model of training for athletic performance. *Australian Journal of Sports Medicine*, 7, 57-61.

15. Banister, E.W. (1991). Modeling elite athletic performance. In J.D. MacDougall, H.A. Wenger, & H.J. Green (Eds.), *Physiological Testing of the High-Performance Athlete* (2nd ed., pp. 403-424). Human Kinetics.

### HRV and Readiness

16. Plews, D.J., Laursen, P.B., Stanley, J., Kilding, A.E., & Buchheit, M. (2013). Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. *Sports Medicine*, 43(9), 773-781.

### Strength Prediction

17. Brzycki, M. (1993). Strength Testing—Predicting a One-Rep Max from Reps-to-Fatigue. *Journal of Physical Education, Recreation & Dance*, 64(1), 88-90.

---

## Version History

| Date | Change |
|------|--------|
| 2026-01-01 | Initial specification created |
