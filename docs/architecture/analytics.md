# Analytics Intelligence Framework

> **Last Updated**: January 8, 2026
> **Related**: [TRAINING_METRICS.md](../TRAINING_METRICS.md) for evidence-based metrics with citations

---

## Design Philosophy: Data Lake, Not Data Warehouse

Key insight: **Solve problems you can observe, not problems you imagine.**

Rather than prematurely optimizing with star schemas and dimensional models, Arnold uses a data lake approach:

1. **Raw stays raw** — Never destroy source fidelity
2. **Staging is dumb** — Just flattened Parquet, easy to rebuild
3. **Intelligence is external** — Catalog describes, doesn't prescribe
4. **Transform at runtime OR pre-build** — Your choice per use case

---

## Control Systems Model

Arnold's analytics layer is not a static dashboard—it's a **closed-loop control system** that learns and adapts to the individual.

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENSORS (Measurement)                        │
│  Wearables, labs, manual entry, workouts                        │
│  Each with known error bounds and confidence                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OBSERVER (State Estimation)                  │
│  What's the current state? What patterns exist?                 │
│  Bayesian updating, uncertainty quantification                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROLLER (Decision Logic)                  │
│  Given state + goals + constraints → recommendations            │
│  Risk-neutral, dampened response to noise                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ACTUATOR (Interventions)                     │
│  Training plan, rest day, intensity adjustment                  │
│  Coach makes recommendation, human decides                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PLANT (The Individual)                       │
│  Biological system with unique response characteristics         │
│  The thing we're trying to optimize                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ (response)
                            ▼
                    Back to SENSORS
```

---

## System Lifecycle

| Phase | What Happens | Uncertainty |
|-------|--------------|-------------|
| **Startup** | Initial data collection, baseline estimation | High — wide credible intervals |
| **Calibration** | Learning individual response curves, tuning priors | Medium — intervals narrowing |
| **Loop Tuning** | Adjusting dampening, identifying lag structures | Medium-Low — patterns stabilizing |
| **Optimization** | Exploiting learned patterns, fine-tuning | Low — confident interventions |

The system **never stops learning**. Even in optimization phase, beliefs update, drift is detected, new patterns emerge.

---

## Bayesian Evidence Framework

**Why not p-values?** P < 0.05 is a binary gate that:
- Treats p=0.049 and p=0.051 completely differently
- Answers the wrong question ("probability of data given null" ≠ "probability effect is real")
- Ignores prior knowledge
- Doesn't account for multiple testing

**Instead, we use:**

```python
class PatternEvidence:
    """Represents belief about a discovered pattern."""
    
    # Effect
    effect_size: float              # Point estimate
    credible_interval: tuple        # (low, high) - 95% HDI
    effect_direction: str           # "positive", "negative", "unclear"
    
    # Confidence
    prior_plausibility: float       # 0-1, based on domain knowledge
    posterior_probability: float    # 0-1, P(real | data)
    bayes_factor: float             # Strength of evidence vs null
    
    # Stability
    temporal_consistency: float     # Does it hold across time windows?
    sample_size: int
    
    # Actionability
    effect_meaningful: bool         # Is effect size large enough to matter?
    intervention_available: bool    # Can we do anything about it?
    
    def evidence_grade(self) -> str:
        """
        Returns: 'strong', 'moderate', 'suggestive', 'weak', 'insufficient'
        
        NOT a binary gate. A communication tool.
        Underlying numbers always available.
        """
```

---

## Prior Sources (Confidence-Weighted)

| Source | Confidence | Use |
|--------|------------|-----|
| Peer-reviewed literature | High | Population-level priors |
| Exercise science consensus | High | Physiological plausibility |
| Your historical data | Very High | Individual response patterns |
| Single studies | Medium | Hypothesis generation |
| Expert opinion | Medium | Where data sparse |
| Pseudoscience measurements | Low | Trend-only, cross-validate |

---

## Dampening and Noise Handling

**Risk-neutral approach:** Don't chase noise, but don't ignore persistent signals.

```python
class SignalProcessor:
    def process_observation(self, new_data, pattern):
        # 1. Update estimate with dampening (learned per-pattern)
        alpha = self.get_dampening_factor(pattern)
        smoothed = alpha * new_data + (1 - alpha) * self.current_estimate
        
        # 2. Track persistence
        if signal_direction_consistent(new_data, window=7):
            pattern.persistence_count += 1
        else:
            pattern.persistence_count = max(0, pattern.persistence_count - 1)
        
        # 3. Escalate attention if persistent
        if pattern.persistence_count > threshold:
            flag_for_investigation(pattern)
            # "This keeps showing up. Let's look closer."
        
        # 4. Update uncertainty bounds
        pattern.credible_interval = update_interval(
            prior=pattern.credible_interval,
            new_evidence=new_data
        )
```

---

## Transparency Architecture

**Three layers of explanation, available on demand:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER-FACING OUTPUT                           │
│  "Your HRV is down. Consider a lighter session today."          │
│  Simple. Actionable. No jargon.                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │ [Why?]
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    REASONING LAYER                              │
│  "HRV is 18% below your 7-day average. Based on 180 days of     │
│  your data, this predicts elevated RPE (+1.2 on average).       │
│  Confidence: moderate (CI: 0.8-1.6 RPE points)."                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ [Show me the math]
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FULL DERIVATION                              │
│  Model: Bayesian linear regression                              │
│  Prior: N(0.5, 0.3) based on literature + Q1-Q2 data            │
│  Likelihood: N(1.2, 0.4) from current data                      │
│  Posterior: N(1.05, 0.25)                                       │
│  Credible interval: [0.56, 1.54] 95% HDI                        │
│  Bayes factor vs null: 4.2 (moderate evidence)                  │
│  Raw data: [attached], Code: [link to computation]              │
└─────────────────────────────────────────────────────────────────┘
```

**Every recommendation is traceable to source data and explicit assumptions.**

---

## Individualization as First Principle

Population studies tell us: "On average, sleep affects recovery."

Your data tells us: "For YOU, sleep 2 nights ago matters more than last night, the effect is ~0.8 RPE points per SD of sleep score, and this holds except during deload weeks."

```python
# Population prior (from literature)
population_effect = Normal(mean=0.5, std=0.3)

# Your data updates the prior
your_posterior = update(
    prior=population_effect,
    likelihood=your_data_likelihood
)

# With enough data, your posterior dominates
# With sparse data, fall back toward population
# Automatic regularization via Bayesian updating
```

**What's important for you ≠ what's important for everyone.** The system learns YOUR transfer functions, YOUR lag structures, YOUR response curves.

---

## Value Extraction Pipeline

```
RAW MEASUREMENTS (Parquet)
    │
    ▼
FEATURE ENGINEERING (DuckDB + Python)
    Rolling averages, deltas, lag features, z-scores
    │
    ▼
PATTERN DETECTION (Statistical + ML)
    Correlation, regression, clustering, anomaly detection
    │
    ▼
DISCOVERED KNOWLEDGE (Neo4j)
    Patterns become graph nodes with relationships
    │
    ▼
COACHING DECISIONS (Claude)
    Knowledge informs recommendations
```

**Raw time-series stays tabular. Discovered patterns become graph relationships.**

---

## Training Metrics (Summary)

For evidence-based training metrics with full citations, see **[TRAINING_METRICS.md](../TRAINING_METRICS.md)**.

**Tier 1 (From Logged Workouts)**:
- Volume Load (tonnage)
- ACWR (Acute:Chronic Workload Ratio) using EWMA
- Training Monotony & Strain
- Sets per muscle group per week
- Movement pattern frequency
- Exercise progression (estimated 1RM)

**Tier 2 (Requires Biometric Data)**:
- Readiness Score (HRV + sleep + RHR)
- hrTSS (heart rate-based Training Stress Score)
- ATL/CTL/TSB (Acute/Chronic Training Load, Training Stress Balance)

**Tier 3 (Requires External Platform Export)**:
- Suunto TSS (not available via Apple Health sync)
- rTSS (pace-based running TSS)

---

## Output Modes

**1. Dashboard (Pre-Computed)**

Standardized views refreshed on schedule. Always ready, no query latency.

```sql
-- Weekly training volume (pre-computed)
SELECT week, total_sets, total_reps, session_count
FROM weekly_summary
ORDER BY week DESC
LIMIT 12;
```

**2. Hot Reports (On-Demand Intelligence)**

Ad-hoc analysis that surfaces patterns and anomalies. Claude generates these in response to questions or proactively.

```
🔥 HOT REPORT: Week 52 Analysis

Volume: 47 sets (+12% vs 4-week avg)
Intensity: 72% of sets @RPE 7+ (normal)
Pattern Gap: No horizontal pull in 10 days ⚠️

Notable:
• Deadlift trending up: 275→295→315 over 3 sessions
• Sleep avg 6.2 hrs (down from 7.1 last month)
• HRV elevated post-surgery, stabilizing

Suggestion: Add rowing or face pulls to Thursday
```

**3. Exploratory (Custom SQL)**

When the data intelligence layer knows what exists, Claude can write custom queries.

**4. Visual Artifacts (React)**

Interactive charts for exploration:
- Progress toward goals (line chart)
- Volume distribution by pattern (stacked bar)
- Training calendar heatmap
- Correlation matrices

---

## Visualization: Muscle Heatmap Dashboard

Standalone Streamlit app (`src/muscle_heatmap.py`) visualizes training load distribution.

| Component | Description |
|-----------|-------------|
| Stack | Streamlit + DuckDB (reads Parquet directly) |
| Math | Weber-Fechner logarithmic normalization |
| Input | `sets.parquet`, `muscle_targeting.csv` |
| Features | Date range picker, rolling window, role weighting |

**Why log normalization?** Legs handle 300lb squats while biceps work with 25lb curls. Linear scaling would wash out small muscles. Weber-Fechner law: human perception of intensity is logarithmic.

Run: `streamlit run src/muscle_heatmap.py`
