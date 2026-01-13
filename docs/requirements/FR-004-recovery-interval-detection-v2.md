# FR-004: Recovery Interval Detection (Heart Rate Recovery) — v2

## Metadata
- **Priority**: High
- **Status**: Ready for Implementation
- **Created**: 2026-01-09
- **Revised**: 2026-01-11
- **Dependencies**: Issue #23 ✅ (HR samples now available)

## Overview

Extract recovery intervals from per-second HR streams and build ML-based models to detect fatigue, predict session stress, and track fitness trends. This moves beyond clinical single-timepoint HRR metrics to a feature-rich approach validated against real-world messy data.

**Key insight**: We're not replicating clinical treadmill tests. We're extracting signal from free-living training data using pattern detection and machine learning, with interpretability via SHAP.

---

## Phase 1: Feature Extraction Layer

### 1.1 Recovery Interval Detection

Detect recovery intervals by pattern, not by external event markers:

```python
def detect_recovery_intervals(
    hr_samples: List[HRSample],
    rhr_baseline: int,
    min_elevation_bpm: int = 25,      # Peak must be this far above RHR
    min_decline_duration_sec: int = 30,
    max_interval_duration_sec: int = 300
) -> List[RecoveryInterval]:
    """
    Detect recovery intervals from HR stream patterns.
    
    Pattern: Sustained elevation → monotonic decline
    
    1. Find segments where HR > RHR + min_elevation_bpm for 30+ sec (effort)
    2. Detect transition to declining HR (peak detection)
    3. Track decline until HR rises again or plateaus
    4. If decline duration >= min_decline_duration_sec, record interval
    
    Returns intervals with raw HR series for feature extraction.
    """
```

**Quality Filters:**
- Require peak HR >= RHR + 25 bpm (floor effect guard)
- Require ≥30 seconds of sustained elevation before peak
- Discard intervals with >10% missing samples
- Apply median filter (window=3) before peak detection

### 1.2 Per-Interval Feature Extraction

For each detected interval, compute:

#### Absolute Metrics
| Feature | Formula | Notes |
|---------|---------|-------|
| `hr_peak` | Max HR in pre-decline window | Last 10s of effort |
| `hr_30s` | HR at t=30s post-peak | |
| `hr_60s` | HR at t=60s post-peak | |
| `hr_nadir` | Minimum HR in interval | |
| `hrr30_abs` | `hr_peak - hr_30s` | Raw 30s drop |
| `hrr60_abs` | `hr_peak - hr_60s` | Raw 60s drop |
| `total_drop` | `hr_peak - hr_nadir` | |

#### Normalized Metrics (Critical)
| Feature | Formula | Notes |
|---------|---------|-------|
| `hr_reserve` | `hr_peak - rhr_baseline` | Available drop range |
| `hrr30_frac` | `hrr30_abs / hr_reserve` | % recovered at 30s |
| `hrr60_frac` | `hrr60_abs / hr_reserve` | % recovered at 60s |
| `recovery_ratio` | `total_drop / hr_reserve` | Total % of available drop |
| `peak_pct_max` | `hr_peak / hr_max_estimated` | Intensity relative to max |

#### Decay Dynamics
| Feature | Formula | Notes |
|---------|---------|-------|
| `tau` | Fit: `HR(t) = A * exp(-t/τ) + C` | Exponential decay constant |
| `decline_slope_30s` | Linear slope, first 30s | bpm/sec |
| `decline_slope_60s` | Linear slope, first 60s | bpm/sec |
| `time_to_50pct` | Seconds to recover 50% of `hr_reserve` | |
| `auc_60s` | Area under curve, first 60s | Integral of HR |

#### HRV in Recovery (if RR intervals available)
| Feature | Formula | Notes |
|---------|---------|-------|
| `rmssd_30_60s` | RMSSD from t=30s to t=60s | Vagal reactivation |
| `sdnn_recovery` | SDNN over recovery window | Overall variability |

### 1.3 Context Features

Captured per-session or per-interval:

| Feature | Source | Notes |
|---------|--------|-------|
| `session_type` | Workout metadata | strength/run/hiit/mixed |
| `interval_order` | Detection sequence | 1st, 2nd, 3rd... in session |
| `session_elapsed_min` | Clock time | Fatigue accumulation |
| `sustained_effort_sec` | Pattern detection | Duration of pre-peak elevation |
| `ambient_temp_c` | Weather API / manual | Critical confounder |
| `rhr_morning` | Ultrahuman/manual | That day's baseline |
| `hrv_morning` | Ultrahuman | Parasympathetic state |
| `sleep_hours` | Ultrahuman | Recovery context |
| `sleep_score` | Ultrahuman | Quality not just quantity |
| `days_since_hard` | Training log | Accumulated fatigue |
| `session_rpe` | Post-session input | Subjective effort (label candidate) |

---

## Phase 2: Machine Learning Layer

### 2.1 Target Variables

Train separate models for different prediction tasks:

| Target | Type | Source | Use Case |
|--------|------|--------|----------|
| `session_rpe` | Continuous (1-10) | User input | Does recovery pattern predict perceived effort? |
| `next_set_reps_delta` | Continuous | Training log | Does poor HRR predict performance drop? |
| `fatigued_flag` | Binary | Derived (RPE≥8 or reps dropped) | Classification target |
| `hrv_next_morning_delta` | Continuous | Ultrahuman | Does session recovery predict next-day autonomic state? |
| `anomaly_flag` | Binary | Unsupervised detection | Unusual recovery pattern |

### 2.2 Model Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Per-Second HR Stream                    │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Interval Detection + Filtering              │
│         (Pattern-based, quality thresholds)              │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│               Feature Extraction (20+ features)          │
│    Absolute | Normalized | Decay | HRV | Context         │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Random Forest                         │
│         (Grouped CV: leave-week-out)                     │
└─────────────────────────┬───────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
┌─────────────────────┐   ┌─────────────────────┐
│   Gini Importance   │   │   SHAP Values       │
│ (Global: which      │   │ (Local: why THIS    │
│  features matter?)  │   │  prediction?)       │
└─────────────────────┘   └─────────────────────┘
```

### 2.3 Training Protocol

**Cross-Validation**: Grouped by week (leave-week-out) to prevent temporal leakage.

```python
from sklearn.model_selection import GroupKFold

# Groups = week number
groups = df['session_date'].dt.isocalendar().week

gkf = GroupKFold(n_splits=5)
for train_idx, val_idx in gkf.split(X, y, groups):
    # Train on 4 weeks, validate on 1
    pass
```

**Metrics by Target Type**:
- Continuous: MAE, RMSE, R²
- Binary: ROC-AUC, Precision-Recall AUC, F1
- For anomaly detection: Prioritize precision (minimize false alarms)

### 2.4 Interpretability Layer

**Global Importance** (Gini):
- Which features consistently matter across all predictions?
- Does τ beat simple HRR60_frac? Does context (temp, sleep) dominate?

**Local Explanations** (SHAP):
```python
import shap

explainer = shap.TreeExplainer(rf_model)
shap_values = explainer.shap_values(X_test)

# For a flagged session:
# "τ was normal, but hrr60_frac was 1.8σ below baseline 
#  AND ambient_temp was 33°C AND sleep_score was 62"
```

---

## Phase 3: Unsupervised Baseline

Before supervised learning, establish "normal" patterns:

### 3.1 Clustering

```python
from sklearn.cluster import KMeans

# Cluster recovery intervals into archetypes
# e.g., "fast_full_recovery", "slow_partial", "flat_no_recovery"
kmeans = KMeans(n_clusters=4)
df['recovery_cluster'] = kmeans.fit_predict(X_features)
```

### 3.2 Anomaly Detection

```python
from sklearn.ensemble import IsolationForest

iso = IsolationForest(contamination=0.05)
df['is_anomaly'] = iso.fit_predict(X_features) == -1
```

Use anomalies as:
1. Candidates for manual review
2. Potential labels for supervised anomaly detection
3. Signals to investigate (was something actually wrong that day?)

---

## Data Model (Revised)

### Recovery Intervals Table

```sql
CREATE TABLE hr_recovery_intervals (
    id SERIAL PRIMARY KEY,
    
    -- Session links (at least one required)
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    endurance_session_id INTEGER REFERENCES endurance_sessions(id),
    strength_session_id INTEGER REFERENCES strength_sessions(id),
    
    -- Interval timing
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL,
    interval_order SMALLINT,  -- 1st, 2nd, 3rd in session
    
    -- Raw HR values
    hr_peak SMALLINT NOT NULL,
    hr_30s SMALLINT,
    hr_60s SMALLINT,
    hr_nadir SMALLINT,
    rhr_baseline SMALLINT,  -- Morning or pre-session RHR
    
    -- Absolute metrics
    hrr30_abs SMALLINT,
    hrr60_abs SMALLINT,
    total_drop SMALLINT,
    
    -- Normalized metrics
    hr_reserve SMALLINT,
    hrr30_frac NUMERIC(4,3),  -- 0.000 to 1.000
    hrr60_frac NUMERIC(4,3),
    recovery_ratio NUMERIC(4,3),
    peak_pct_max NUMERIC(4,3),
    
    -- Decay dynamics
    tau_seconds NUMERIC(5,1),  -- Exponential decay constant
    decline_slope_30s NUMERIC(5,3),  -- bpm/sec
    decline_slope_60s NUMERIC(5,3),
    time_to_50pct_sec SMALLINT,
    
    -- Context (denormalized for query performance)
    session_type VARCHAR(20),
    ambient_temp_c NUMERIC(4,1),
    session_elapsed_min SMALLINT,
    
    -- Quality
    sample_completeness NUMERIC(4,3),  -- % of expected samples present
    is_clean BOOLEAN DEFAULT true,
    
    -- ML outputs (populated by model)
    predicted_rpe NUMERIC(3,1),
    anomaly_score NUMERIC(5,3),
    recovery_cluster VARCHAR(30),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_recovery_polar ON hr_recovery_intervals(polar_session_id);
CREATE INDEX idx_recovery_endurance ON hr_recovery_intervals(endurance_session_id);
CREATE INDEX idx_recovery_strength ON hr_recovery_intervals(strength_session_id);
CREATE INDEX idx_recovery_date ON hr_recovery_intervals(start_time);
CREATE INDEX idx_recovery_anomaly ON hr_recovery_intervals(anomaly_score DESC);
```

### Model Artifacts Table

```sql
CREATE TABLE hr_recovery_models (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(50) NOT NULL,  -- 'rpe_predictor', 'fatigue_classifier'
    target_variable VARCHAR(50) NOT NULL,
    
    -- Performance metrics
    cv_score NUMERIC(5,3),  -- Primary metric (R² or AUC)
    cv_std NUMERIC(5,3),
    n_samples INTEGER,
    n_features INTEGER,
    
    -- Feature importance (top 10)
    feature_importance JSONB,  -- {"hrr60_frac": 0.23, "tau": 0.18, ...}
    
    -- Model binary (or path)
    model_path VARCHAR(255),
    
    trained_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);
```

---

## Implementation Phases

### Phase 1: Feature Extraction (Week 1)
- [ ] Implement interval detection from HR stream
- [ ] Implement all feature extractors
- [ ] Validate on 2 Suunto sessions (manual inspection)
- [ ] Populate `hr_recovery_intervals` table

### Phase 2: Unsupervised Exploration (Week 2)
- [ ] Run clustering on extracted features
- [ ] Run IsolationForest for anomalies
- [ ] Manual review of clusters and anomalies
- [ ] Refine feature engineering based on findings

### Phase 3: Supervised Models (Week 3)
- [ ] Define target variables (need sufficient labeled data)
- [ ] Train RF models with grouped CV
- [ ] Evaluate Gini importance
- [ ] Generate SHAP explanations for sample predictions

### Phase 4: Integration (Week 4)
- [ ] MCP endpoint: `analyze_recovery_intervals(session_id)`
- [ ] MCP endpoint: `get_recovery_trend(days)`
- [ ] Surface anomalies in coach briefing
- [ ] Store model predictions in intervals table

---

## MCP Interface (Revised)

```typescript
// Analyze a session's recovery intervals
analyze_recovery_intervals(session_id: string, session_type: 'polar' | 'endurance')
  → {
      interval_count: 8,
      intervals: [
        {
          start: '17:05:30',
          duration_sec: 65,
          hr_peak: 145,
          hrr60_frac: 0.67,
          tau: 42.3,
          recovery_cluster: 'fast_full',
          anomaly_score: 0.12,
          is_anomaly: false
        },
        ...
      ],
      session_summary: {
        avg_hrr60_frac: 0.62,
        avg_tau: 48.5,
        anomaly_count: 0,
        fatigue_trend: 'stable'  // intervals 1-8 comparison
      },
      feature_importance: {  // From active model
        hrr60_frac: 0.23,
        tau: 0.18,
        ambient_temp: 0.15,
        ...
      }
    }

// Get recovery trend over time
get_recovery_trend(days: number = 30, session_type?: string)
  → {
      data_points: [
        { 
          date: '2026-01-09', 
          avg_hrr60_frac: 0.65, 
          avg_tau: 45.2,
          session_type: 'strength',
          anomaly_count: 0
        },
        ...
      ],
      trend: {
        hrr60_frac: 'improving',  // +0.05 over period
        tau: 'stable',
        significance: 0.82  // Confidence in trend
      },
      baseline: {
        hrr60_frac_mean: 0.58,
        hrr60_frac_std: 0.12,
        tau_mean: 52.3,
        tau_std: 8.4
      }
    }

// Explain a specific anomaly
explain_recovery_anomaly(interval_id: number)
  → {
      shap_explanation: [
        { feature: 'hrr60_frac', value: 0.32, impact: -0.45, note: '2.1σ below baseline' },
        { feature: 'ambient_temp_c', value: 34.2, impact: -0.22, note: 'Heat stress' },
        { feature: 'sleep_score', value: 58, impact: -0.12, note: 'Below average' },
        ...
      ],
      recommendation: 'Recovery significantly impaired. Consider: heat, poor sleep, accumulated fatigue.'
    }
```

---

## Clinical Safety Guardrails

**This is NOT a diagnostic tool.** But we should flag truly concerning patterns:

### Hard Flags (Surface to User)
- Sustained resting HR >120 bpm for >5 min post-exercise
- HR fails to decline at all for >3 min (flat line, not sensor dropout)
- Pattern of HRR60_frac < 0.2 across 3+ consecutive sessions (when baseline is >0.5)

### Soft Flags (Coach Briefing, Not Alerts)
- Anomaly score in top 5% for this user
- τ > 2σ above personal baseline
- Cluster assignment changed from "fast_full" to "slow_partial" for 2+ sessions

### What We Do NOT Flag
- Single-session variations (too noisy)
- Absolute thresholds from clinical literature (context mismatch)
- Anything during heat training or known illness (annotated)

---

## Research Extension (Future)

If this proves useful, potential paper:

**Title**: "Machine Learning Approaches to Heart Rate Recovery in Free-Living Training Data: Moving Beyond Clinical Protocols"

**Core contribution**: 
1. Feature engineering for real-world HRR (normalized metrics, τ, context features)
2. Validation of RF approach with SHAP interpretability
3. Comparison of single-timepoint HRR vs ML-derived features for predicting fatigue/fitness

**Data needed**: 
- N=10-20 athletes with 50+ sessions each
- Per-second HR, session type, RPE, environmental data
- 6+ months longitudinal

---

## References

See `/research/papers/hrr_research_notes.md` for full literature review and citations.

Key sources:
1. Cole et al. (1999) - HRR prognostic value
2. PMC5336925 - Methodological considerations
3. MDPI 2023 - Inter-set HR in resistance training
4. Brighton - Heat acclimation effects
