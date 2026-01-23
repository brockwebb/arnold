# ADR-008: Device Telemetry Layer

**Date:** January 20, 2026  
**Status:** Proposed  
**Deciders:** Brock Webb, Claude, ChatGPT Health  
**Related:** ADR-001 (Data Layer Separation), ADR-007 (Simplified Workout Schema)

## Context

The Arnold system needs to integrate data from multiple fitness devices:
- **Polar** — HR straps, watches (Training Load, HRV)
- **Suunto** — GPS watches (PTE, EPOC, Training Effect)
- **Garmin** — Historical data (Training Load, VO2max estimates)
- **Ultrahuman** — Ring biometrics (HRV, sleep, recovery)
- **Apple Health** — Aggregated data from various sources

ADR-006 attempted to solve this with sport-specific tables (`v2_running_intervals`, `v2_rowing_intervals`, etc.). This failed because:

1. **Device data ≠ sport-typed data** — The schema should reflect data sources (devices), not activities (sports)
2. **Nobody manually logs running intervals** — That data comes from FIT files with device-native schemas
3. **Vendor metrics are not interchangeable** — Garmin Training Load ≠ Polar Training Load ≠ Suunto PTE

The correct separation is:
- **Workout Log** (ADR-007) — Human-authored, universal, simple
- **Device Telemetry** (this ADR) — Device-authored, raw fidelity, provenance-tracked
- **Canonical Metrics** — Computed from raw telemetry, formula-versioned

## Decision

Implement a three-layer device telemetry architecture with strict provenance, athlete calibration, and many-to-many workout linkage.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  WORKOUT LOG (human-authored) — ADR-007                         │
│  workouts → blocks → sets                                       │
│  Source: manual entry, plan completion                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ many-to-many via workout_telemetry
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  DEVICE TELEMETRY (raw, immutable)                              │
│                                                                 │
│  fit_files ─────► fit_sessions ─────► fit_records               │
│  (file metadata)  (session summary)   (time-series samples)     │
│                                                                 │
│  polar_sessions   suunto_sessions   ultrahuman_daily            │
│  (API-synced device data with vendor-native fields)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ computed on ingest / nightly batch
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  CANONICAL METRICS (computed, versioned)                        │
│                                                                 │
│  canonical_metrics ──► daily_load_rollup ──► athlete_baselines  │
│  (TRIMP, TSS, HRR)    (7d/28d/42d ATL/CTL)  (personal norms)    │
│                                                                 │
│  Formula versioning, athlete calibration linkage, reprocessing  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

#### 1. Ingest Raw, Compute Canonical

Never trust vendor scores as universal metrics. Store vendor values unchanged, then compute your own canonical metrics from raw data (HR samples, power, pace) using documented formulas.

```
Vendor data (opaque)     →  Store as-is in vendor_metrics_json
Raw samples (HR, power)  →  Compute TRIMP/TSS with your formula
```

#### 2. Immutability and Provenance

Raw telemetry is append-only. Re-parsing a file creates a new version, not an overwrite. Every computed metric links back to:
- Source file(s) / session(s)
- Formula name and version
- Athlete parameters used
- Computation timestamp

#### 3. Many-to-Many Workout ↔ Session Linking

A workout can have multiple device sessions (HR strap + GPS watch). A device session can span multiple workouts (forgot to stop recording). The `workout_telemetry` junction table handles this with match confidence scores.

#### 4. Athlete Calibration is Mandatory

TRIMP and TSS are meaningless without athlete-specific parameters (HRmax, HRrest, FTP, threshold pace). Store these with timestamps and link to which parameter set was used for each computation.

#### 5. Device Tables, Not Sport Tables

Tables are organized by data source, not activity type:
- `fit_files` / `fit_sessions` / `fit_records` — Any FIT-compatible device
- `polar_sessions` — Polar API data
- `suunto_sessions` — Suunto API/export data
- `ultrahuman_daily` — Ring biometrics (not workout-linked)

---

## Schema Design

### Layer 1: Raw Device Data

#### fit_files
```sql
CREATE TABLE fit_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  athlete_id UUID NOT NULL,
  
  -- File identification
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,  -- Idempotent ingest key
  file_size_bytes INT,
  blob_storage_ref TEXT,        -- S3/local path to original file
  
  -- Device metadata
  device_manufacturer TEXT,     -- garmin, suunto, wahoo, etc.
  device_product TEXT,
  device_serial TEXT,
  firmware_version TEXT,
  
  -- Ingest tracking
  ingest_ts TIMESTAMPTZ DEFAULT NOW(),
  parse_status TEXT DEFAULT 'pending',  -- pending, success, failed, reprocessing
  parse_error TEXT,
  parse_version INT DEFAULT 1,  -- Increments on re-parse
  
  -- Raw preservation
  developer_fields JSONB,       -- Unknown/extended fields
  
  CONSTRAINT fit_files_unique_hash UNIQUE (sha256)
);

CREATE INDEX idx_fit_files_athlete ON fit_files(athlete_id);
CREATE INDEX idx_fit_files_ingest ON fit_files(ingest_ts);
```

#### fit_sessions
```sql
CREATE TABLE fit_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fit_file_id UUID REFERENCES fit_files(id),
  
  -- Timing (always store UTC + local + timezone)
  start_ts_utc TIMESTAMPTZ NOT NULL,
  end_ts_utc TIMESTAMPTZ,
  start_ts_local TIMESTAMP,
  timezone TEXT,                -- IANA timezone
  device_clock_offset_seconds INT,  -- Detected drift
  
  -- Session summary (from FIT session message)
  sport_hint TEXT,              -- Device's sport classification
  sub_sport TEXT,
  total_elapsed_time_s NUMERIC,
  total_timer_time_s NUMERIC,
  total_distance_m NUMERIC,
  total_calories INT,
  avg_hr INT,
  max_hr INT,
  avg_power_watts NUMERIC,
  max_power_watts NUMERIC,
  
  -- Vendor training scores (preserved exactly as device reports)
  vendor_metrics_json JSONB,    -- {training_effect: 3.2, training_load: 145, ...}
  
  -- Raw preservation
  developer_fields JSONB,
  extra JSONB,
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_fit_sessions_file ON fit_sessions(fit_file_id);
CREATE INDEX idx_fit_sessions_time ON fit_sessions(start_ts_utc);
CREATE INDEX idx_fit_sessions_sport ON fit_sessions(sport_hint);
```

#### fit_records
```sql
CREATE TABLE fit_records (
  id BIGSERIAL PRIMARY KEY,     -- BIGSERIAL for high cardinality
  fit_session_id UUID REFERENCES fit_sessions(id),
  
  -- Timing
  ts_utc TIMESTAMPTZ NOT NULL,
  sample_index INT,             -- Order within session
  
  -- Common fields (nullable - use what device provides)
  hr_bpm INT,
  power_watts NUMERIC,
  cadence_rpm INT,
  speed_mps NUMERIC,
  distance_m NUMERIC,           -- Cumulative
  
  -- GPS
  latitude NUMERIC(10, 7),
  longitude NUMERIC(10, 7),
  altitude_m NUMERIC,
  
  -- Quality flags
  hr_quality TEXT,              -- good, interpolated, dropped
  gps_quality TEXT,
  
  -- Raw preservation
  raw_record_json JSONB         -- Full record if needed
  
) PARTITION BY RANGE (ts_utc);  -- Partition by time for scale

-- Create partitions (example: monthly)
CREATE TABLE fit_records_2025_q4 PARTITION OF fit_records
  FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');
CREATE TABLE fit_records_2026_q1 PARTITION OF fit_records
  FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

CREATE INDEX idx_fit_records_session_time ON fit_records(fit_session_id, ts_utc);
```

#### fit_laps
```sql
CREATE TABLE fit_laps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fit_session_id UUID REFERENCES fit_sessions(id),
  
  lap_index INT NOT NULL,
  trigger_type TEXT,            -- manual, distance, time, position, etc.
  
  start_ts_utc TIMESTAMPTZ,
  end_ts_utc TIMESTAMPTZ,
  total_elapsed_time_s NUMERIC,
  total_distance_m NUMERIC,
  
  avg_hr INT,
  max_hr INT,
  avg_power_watts NUMERIC,
  avg_cadence INT,
  
  extra JSONB
);

CREATE INDEX idx_fit_laps_session ON fit_laps(fit_session_id);
```

#### Device-Specific Tables (API-synced data)

```sql
-- Polar API data (beyond what's in FIT)
CREATE TABLE polar_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  athlete_id UUID NOT NULL,
  polar_exercise_id TEXT UNIQUE,  -- Polar's ID
  
  start_ts_utc TIMESTAMPTZ NOT NULL,
  duration_seconds INT,
  sport TEXT,
  
  -- Polar-specific metrics
  training_load_score NUMERIC,
  cardio_load NUMERIC,          -- TRIMP-based
  muscle_load_joules NUMERIC,
  perceived_load NUMERIC,       -- If sRPE entered in Polar
  
  hr_avg INT,
  hr_max INT,
  calories INT,
  
  -- Link to FIT if also imported
  fit_session_id UUID REFERENCES fit_sessions(id),
  
  raw_api_response JSONB,
  synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Suunto data
CREATE TABLE suunto_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  athlete_id UUID NOT NULL,
  suunto_workout_id TEXT UNIQUE,
  
  start_ts_utc TIMESTAMPTZ NOT NULL,
  duration_seconds INT,
  activity_type TEXT,
  
  -- Suunto-specific metrics
  pte NUMERIC,                  -- Peak Training Effect
  epoc_ml_kg NUMERIC,
  recovery_time_hours NUMERIC,
  feeling INT,                  -- User-entered
  
  hr_avg INT,
  hr_max INT,
  distance_m NUMERIC,
  ascent_m NUMERIC,
  
  fit_session_id UUID REFERENCES fit_sessions(id),
  
  raw_json JSONB,
  synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ultrahuman ring (daily, not workout-linked)
CREATE TABLE ultrahuman_daily (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  athlete_id UUID NOT NULL,
  date DATE NOT NULL,
  
  -- Recovery metrics
  recovery_score NUMERIC,
  hrv_ms NUMERIC,
  rhr_bpm INT,
  sleep_score NUMERIC,
  
  -- Sleep details
  sleep_duration_minutes INT,
  deep_sleep_minutes INT,
  rem_sleep_minutes INT,
  sleep_efficiency NUMERIC,
  
  -- Movement
  steps INT,
  active_calories INT,
  
  raw_api_response JSONB,
  synced_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(athlete_id, date)
);
```

### Layer 2: Workout ↔ Telemetry Linkage

```sql
CREATE TABLE workout_telemetry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  workout_id UUID NOT NULL,     -- FK to workouts table
  fit_session_id UUID REFERENCES fit_sessions(id),
  polar_session_id UUID REFERENCES polar_sessions(id),
  suunto_session_id UUID REFERENCES suunto_sessions(id),
  
  -- Match metadata
  match_method TEXT NOT NULL,   -- time_overlap, manual, hr_correlation, gps_overlap
  match_score NUMERIC,          -- 0-1 confidence
  match_confidence TEXT,        -- high, medium, low
  matched_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Manual override
  manual_override BOOLEAN DEFAULT FALSE,
  override_reason TEXT,
  overridden_by TEXT,
  overridden_at TIMESTAMPTZ,
  
  notes TEXT,
  
  -- At least one session must be linked
  CONSTRAINT at_least_one_session CHECK (
    fit_session_id IS NOT NULL OR 
    polar_session_id IS NOT NULL OR 
    suunto_session_id IS NOT NULL
  )
);

CREATE INDEX idx_workout_telemetry_workout ON workout_telemetry(workout_id);
CREATE INDEX idx_workout_telemetry_fit ON workout_telemetry(fit_session_id);
```

### Layer 3: Athlete Calibration

```sql
CREATE TABLE athlete_parameters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  athlete_id UUID NOT NULL,
  
  -- Cardiac parameters
  hr_max INT,                   -- Maximum heart rate
  hr_rest INT,                  -- Resting heart rate
  hr_reserve INT GENERATED ALWAYS AS (hr_max - hr_rest) STORED,
  lt_hr INT,                    -- Lactate threshold HR (optional)
  
  -- Power/pace thresholds
  ftp_watts NUMERIC,            -- Functional Threshold Power (cycling)
  threshold_pace_min_km NUMERIC, -- Running threshold pace
  
  -- Body metrics
  weight_kg NUMERIC,
  height_cm NUMERIC,
  sex TEXT,
  birth_date DATE,
  
  -- Provenance
  source TEXT,                  -- manual, device_detected, test_result
  effective_from DATE NOT NULL,
  effective_to DATE,            -- NULL = current
  notes TEXT,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_athlete_params_athlete ON athlete_parameters(athlete_id, effective_from);

-- View for current parameters
CREATE VIEW current_athlete_parameters AS
SELECT DISTINCT ON (athlete_id) *
FROM athlete_parameters
WHERE effective_to IS NULL OR effective_to > CURRENT_DATE
ORDER BY athlete_id, effective_from DESC;
```

### Layer 4: Canonical Metrics

```sql
CREATE TABLE canonical_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Links (at least one required)
  workout_id UUID,
  fit_session_id UUID REFERENCES fit_sessions(id),
  athlete_id UUID NOT NULL,
  
  -- The metric
  metric_name TEXT NOT NULL,    -- trimp_edwards, trimp_banister, tss, hrr60, etc.
  metric_value NUMERIC NOT NULL,
  metric_unit TEXT,             -- AU (arbitrary units), seconds, etc.
  
  -- Computation provenance
  formula_name TEXT NOT NULL,   -- edwards_trimp_v1, banister_trimp_v1, coggan_tss_v1
  formula_version TEXT NOT NULL,
  parameters_used JSONB,        -- {hr_max: 185, hr_rest: 52, ...}
  athlete_params_id UUID REFERENCES athlete_parameters(id),
  
  -- Source tracking
  source_fit_file_ids UUID[],   -- Array of fit_file IDs used
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Quality
  confidence TEXT,              -- high, medium, low
  notes TEXT
);

CREATE INDEX idx_canonical_metrics_workout ON canonical_metrics(workout_id);
CREATE INDEX idx_canonical_metrics_session ON canonical_metrics(fit_session_id);
CREATE INDEX idx_canonical_metrics_name ON canonical_metrics(metric_name);
CREATE INDEX idx_canonical_metrics_computed ON canonical_metrics(computed_at);

-- Materialized view for daily training load
CREATE MATERIALIZED VIEW daily_load_rollup AS
SELECT 
  athlete_id,
  DATE(computed_at) AS date,
  metric_name,
  SUM(metric_value) AS daily_total,
  COUNT(*) AS session_count
FROM canonical_metrics
WHERE metric_name IN ('trimp_edwards', 'trimp_banister', 'tss')
GROUP BY athlete_id, DATE(computed_at), metric_name;
```

### Layer 5: Vendor Score Mapping (Optional)

```sql
-- For mapping vendor scores to canonical when raw HR not available
CREATE TABLE vendor_mapping_models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  vendor_name TEXT NOT NULL,    -- garmin, polar, suunto
  vendor_metric TEXT NOT NULL,  -- training_load, training_effect, pte
  target_metric TEXT NOT NULL,  -- trimp_edwards, trimp_banister
  
  -- Model parameters
  model_type TEXT NOT NULL,     -- linear, polynomial, lookup
  parameters JSONB NOT NULL,    -- {slope: 1.2, intercept: 5.0, r2: 0.87}
  
  -- Scope
  athlete_id UUID,              -- NULL = population model
  
  -- Validity
  trained_on_date_range DATERANGE,
  sample_size INT,
  r_squared NUMERIC,
  rmse NUMERIC,
  
  -- Lifecycle
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  invalidated_at TIMESTAMPTZ,
  invalidation_reason TEXT
);
```

---

## Matching Heuristics

Workout ↔ Device Session matching uses layered criteria:

| Priority | Method | Criteria |
|----------|--------|----------|
| 1 | Time overlap | Session start within [workout_start - 10min, workout_end + 10min] |
| 2 | Duration similarity | Session duration within 20% of workout duration |
| 3 | HR correlation | Cross-correlation > 0.6 (when both have HR data) |
| 4 | GPS overlap | Route similarity for outdoor activities |
| 5 | Manual | User explicitly links session to workout |

Match score = weighted sum of satisfied criteria. Store `match_method` for audit.

Allow manual override with `manual_override=true` + reason. Never delete failed matches—flag them for review.

---

## Canonical Metric Formulas

Store implementations in code with version tags. Reference in DB.

### TRIMP Variants

| Formula | Description | When to Use |
|---------|-------------|-------------|
| `edwards_trimp_v1` | Zone-based: Σ(minutes × zone_weight) | Simple, population-level |
| `banister_trimp_v1` | Exponential: Σ(minutes × e^(1.92 × %HRR)) | Physiological, needs good HRmax |
| `itrimp_v1` | Individualized lactate curve | Best accuracy, needs LT calibration |

**Recommendation:** Compute Edwards + Banister for all sessions. Store both. Let athlete preference or downstream app choose which to display.

### TSS (Training Stress Score)

| Formula | Description | When to Use |
|---------|-------------|-------------|
| `coggan_tss_v1` | (duration × NP × IF) / (FTP × 3600) × 100 | Cycling with power |
| `rtss_v1` | Running TSS from pace vs threshold | Running with pace data |
| `hrtss_v1` | HR-based TSS approximation | When power not available |

## Decision Summary

### What We Keep (Original Intent)

- **Workout → Block → Set → Exercise** as the canonical human plan model
- **Blocks as first-class** (warmup / main / conditioning / circuit / emom / cooldown)
- **Sets = station or single set** — simple, standard semantics

### What We Keep (From Device-First Exploration)

- **Device telemetry as raw truth** — Immutable FIT blobs, vendor fields preserved
- **Canonical metrics computed, not assumed** — Recompute TRIMP/TSS from raw HR/power
- **Provenance & versioning** — Formula versions, firmware, parameter sets linked

### What We Add

- **workout_telemetry junction** — Many-to-many with match_score, match_method, manual_override
- **athlete_parameters** — HR max/rest, FTP, weight with timestamps; link to each computation
- **Minimal deviation surface** — planned_set_id, deviation_type (controlled vocab), deviation_magnitude, deviation_note
- **Idempotent ingest** — SHA256 + file versioning + raw immutability
- **Partitioned fit_records** — For query performance (not deletion)

---

## Hard Policy Decisions

These must be decided before implementation:

### 1. Canonical Internal Load Formula(s)

**Decision:** Compute both Edwards TRIMP and Banister TRIMP for all sessions with HR data.

| Formula | Version | Status |
|---------|---------|--------|
| Edwards TRIMP | `edwards_trimp_v1` | Primary (simpler, population-friendly) |
| Banister TRIMP | `banister_trimp_v1` | Secondary (physiological, needs good HRmax) |
| iTRIMP | Deferred | Requires lactate curve calibration |

Store both. Let downstream consumers choose which to display.

### 2. Reprocessing Policy

**Decision:** Historical data is **never automatically recomputed** when formulas change.

Reprocessing requires:
- [ ] ADR documenting the change and rationale
- [ ] Defined reprocess window (e.g., "last 2 years" or "all data")
- [ ] Validation comparing old vs new values
- [ ] Explicit signoff before execution

Rationale: Longitudinal comparisons break if historical values silently change.

### 3. Vendor → Canonical Mapping Strategy

**Decision:** Prefer recomputation from raw data. Use regression mapping only as fallback.

| Priority | Method | When |
|----------|--------|------|
| 1 | Recompute from raw HR | HR samples available in fit_records |
| 2 | Recompute from session HR | Only avg/max HR available |
| 3 | Per-athlete regression | No raw HR, only vendor score |

Regression models require:
- Minimum 20 sessions with both raw and vendor data
- R² > 0.7 to be considered valid
- Model parameters stored with expiry and invalidation triggers

---

## Migration Guardrails

Before dropping or replacing anything:

1. **Snapshot/export old tables** — pg_dump before any destructive operation
2. **Backfill validation window** — Populate new tables for 2 weeks alongside old
3. **Reconciliation tests** — Compare canonical_trimp vs mapped_trimp (R² threshold)
4. **Consumer switchover** — Only flip when thresholds pass
5. **Rollback window** — Keep old tables until 30 days post-migration with no issues

---

## Immediate Priorities (Lock These First)

| Priority | Task | Acceptance Criteria |
|----------|------|--------------------|
| 1 | Finalize TRIMP implementations | `edwards_trimp_v1` and `banister_trimp_v1` code committed with tests |
| 2 | Create `athlete_parameters` table | Brock's values populated, every canonical row links to param set |
| 3 | Implement `fit_files.sha256` + idempotent ingest | Duplicate file imports rejected cleanly |
| 4 | Create `workout_telemetry` junction | Manual override flow working |
| 5 | Run 1-week validation | New tables populated alongside existing, no regressions |

---

Arnold already has sync pipelines for device data:

| Source | Method | Script Location |
|--------|--------|----------------|
| Polar | API sync | `scripts/sync/polar_to_postgres.py` |
| Ultrahuman | API sync | `scripts/sync/ultrahuman_to_postgres.py` |
| Apple Health | XML export | `scripts/sync/apple_health_to_postgres.py` |
| Suunto | FIT file import | Manual import via FIT parser |
| Garmin | FIT file import | Manual import via FIT parser |

This ADR does not replace these pipelines—it defines **where the data lands**. Phase 1 updates existing scripts to write to the new schema.

## Data Retention Philosophy

**Keep everything forever.** This is a digital twin, not a SaaS product with storage costs to optimize.

### Raw Microdata (Immutable)

- `fit_records` — Full-resolution time-series (HR samples, GPS, power)
- `fit_files` — Original files archived permanently
- `*_sessions` — Session-level summaries with vendor API responses
- Partitioned by time for **query performance**, not deletion
- Never aggregated away — always reprocessable

### Tabulations / Data Products (Pre-computed)

Like Census Bureau publications (SIPP, ACS), we pre-compute statistics at various time grains:

| Grain | Table | Contents | Refresh |
|-------|-------|----------|--------|
| Daily | `daily_digest` | HRV, sleep, resting HR, training load, recovery score, readiness | On sync |
| Weekly | `weekly_summary` | Total volume, avg metrics, pattern distribution, load trends | Sunday night |
| Monthly | `monthly_report` | Trends, PRs achieved, goal progress, block summaries | 1st of month |
| Quarterly | `quarterly_review` | Periodization analysis, injury history, longitudinal comparisons | End of quarter |
| Annual | `annual_report` | Year in review, YoY comparisons, lifetime PRs, milestone tracking | Jan 1 |

These are **materialized views or tables**, not queries against microdata. Dashboards and reports hit tabulations; research/debugging hits microdata.

### Compute Strategy

```
fit_records (billions of rows)
    ↓ aggregate on ingest
fit_sessions (thousands of rows)
    ↓ daily batch
daily_digest (one row per day)
    ↓ weekly batch  
weekly_summary (52 rows per year)
    ↓ monthly batch
monthly_report (12 rows per year)
    ↓ quarterly batch
quarterly_review (4 rows per year)
    ↓ annual batch
annual_report (1 row per year)
```

Each layer is cheap to query. Microdata remains available for ad-hoc analysis and reprocessing.

## Implementation Phases

### Phase 1: Foundation (Do First)
- [ ] Create `athlete_parameters` table
- [ ] Populate with Brock's current values (HRmax, HRrest, weight)
- [ ] Create `fit_files` and `fit_sessions` tables
- [ ] Update existing sync scripts to write to new tables (polar, ultrahuman, suunto, apple_health)

### Phase 2: Existing Data Migration
- [ ] Migrate existing `polar_sessions` data to new schema
- [ ] Migrate existing `endurance_sessions` to `fit_sessions` (if FIT-sourced)
- [ ] Create `workout_telemetry` junction entries for existing links

### Phase 3: Canonical Metrics
- [ ] Implement Edwards TRIMP formula
- [ ] Implement Banister TRIMP formula
- [ ] Create `canonical_metrics` table
- [ ] Backfill TRIMP for all sessions with HR data

### Phase 4: High-Resolution Data
- [ ] Create partitioned `fit_records` table
- [ ] Extend FIT parser to extract time-series
- [ ] Implement HRR extraction from records

### Phase 5: Matching & Automation
- [ ] Implement time-overlap matching heuristic
- [ ] Create matching job (run on ingest + nightly)
- [ ] Add manual override UI flow

### Phase 6: Monitoring & Quality
- [ ] Unmatched session alert (weekly digest)
- [ ] Mapping model drift detection
- [ ] TRIMP vs vendor score correlation tracking

---

## Consequences

### Positive
- **Device-agnostic** — Add new devices without schema changes
- **Provenance-complete** — Every metric traceable to source data + formula
- **Reprocessing-ready** — Can re-run computations with new formulas
- **Athlete-calibrated** — Metrics use personal parameters, not population averages
- **Many-to-many linking** — Handles multi-device workouts correctly

### Negative
- **More tables** — Operational complexity
- **Storage growth** — `fit_records` will be large (partition for query performance, not deletion)
- **Matching complexity** — Heuristics need tuning per athlete/device
- **Migration effort** — Existing data needs restructuring

### Neutral
- Workout log (ADR-007) unchanged—this is additive
- Vendor metrics preserved alongside canonical—no data loss

---

## Open Questions

1. **Ultrahuman HRV timing** — Their HRV is measured overnight. How does this link to morning readiness vs previous day's workout?

2. **Suunto historical data** — FIT files going back to 2019. Batch import strategy? Partition scheme?

3. **Garmin Connect archive** — Different export format. Separate parser or normalize to FIT?

4. **Apple Health role** — Aggregator of aggregators. Use as backup source or ignore?

5. **Real-time vs batch** — Polar/Suunto sync: push notifications or polling? Affects latency of canonical metric availability.

---

## References

- **AALL-006:** `/docs/adr/AALL-006-unified-workout-schema.md` — Why device data needs its own layer
- ADR-001: Data Layer Separation (Postgres facts, Neo4j relationships)
- ADR-007: Simplified Workout Schema (the workout log this links to)
- ChatGPT Health consultation (January 2026) — Device telemetry architecture
- Banister TRIMP: Banister et al. (1991) "Modeling human performance in running"
- Edwards TRIMP: Edwards (1993) "The Heart Rate Monitor Book"
- Coggan TSS: Coggan & Allen, "Training and Racing with a Power Meter"
- FIT SDK: https://developer.garmin.com/fit/protocol/
