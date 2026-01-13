-- Migration 013: HR Recovery Intervals Table
-- Created: 2026-01-11
-- Purpose: Store detected recovery intervals and computed HRR features for FR-004

-- Recovery Intervals Table (per-interval features)
CREATE TABLE hr_recovery_intervals (
    id SERIAL PRIMARY KEY,
    
    -- Session links (at least one required)
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    endurance_session_id INTEGER REFERENCES endurance_sessions(id),
    
    -- Interval timing
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL,
    interval_order SMALLINT,  -- 1st, 2nd, 3rd in session
    
    -- Raw HR values
    hr_peak SMALLINT NOT NULL,
    hr_30s SMALLINT,
    hr_60s SMALLINT,
    hr_90s SMALLINT,
    hr_120s SMALLINT,
    hr_nadir SMALLINT,
    rhr_baseline SMALLINT,  -- Morning RHR for that day
    
    -- Absolute metrics
    hrr30_abs SMALLINT,
    hrr60_abs SMALLINT,
    hrr90_abs SMALLINT,
    hrr120_abs SMALLINT,
    total_drop SMALLINT,
    
    -- Normalized metrics (0.000 to 1.000+)
    hr_reserve SMALLINT,  -- peak - rhr_baseline
    hrr30_frac NUMERIC(5,4),
    hrr60_frac NUMERIC(5,4),
    hrr90_frac NUMERIC(5,4),
    hrr120_frac NUMERIC(5,4),
    recovery_ratio NUMERIC(5,4),  -- total_drop / hr_reserve
    peak_pct_max NUMERIC(5,4),  -- peak / estimated_max_hr
    
    -- Decay dynamics
    tau_seconds NUMERIC(6,2),  -- Exponential decay constant
    tau_fit_r2 NUMERIC(5,4),   -- Fit quality (0-1)
    decline_slope_30s NUMERIC(6,4),  -- bpm/sec (negative)
    decline_slope_60s NUMERIC(6,4),
    time_to_50pct_sec SMALLINT,
    auc_60s NUMERIC(10,2),  -- Area under curve, first 60s
    
    -- Pre-peak context
    sustained_effort_sec SMALLINT,  -- How long HR was elevated before peak
    effort_avg_hr SMALLINT,  -- Average HR during sustained effort
    
    -- Context (denormalized for query performance)
    session_type VARCHAR(20),  -- 'strength', 'run', 'hiit', 'mixed'
    session_elapsed_min SMALLINT,  -- Minutes into session when interval started
    
    -- Quality flags
    sample_count INTEGER,  -- Actual samples in interval
    expected_sample_count INTEGER,  -- Expected based on duration
    sample_completeness NUMERIC(5,4),  -- sample_count / expected
    is_clean BOOLEAN DEFAULT true,  -- No major artifacts detected
    is_low_signal BOOLEAN DEFAULT false,  -- hr_reserve < 25 bpm
    
    -- ML outputs (populated by model, nullable until trained)
    predicted_rpe NUMERIC(3,1),
    anomaly_score NUMERIC(6,4),
    recovery_cluster VARCHAR(30),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraint: at least one session FK required
    CONSTRAINT hr_recovery_session_required CHECK (
        polar_session_id IS NOT NULL OR endurance_session_id IS NOT NULL
    )
);

-- Indexes for common queries
CREATE INDEX idx_hr_recovery_polar ON hr_recovery_intervals(polar_session_id) WHERE polar_session_id IS NOT NULL;
CREATE INDEX idx_hr_recovery_endurance ON hr_recovery_intervals(endurance_session_id) WHERE endurance_session_id IS NOT NULL;
CREATE INDEX idx_hr_recovery_start_time ON hr_recovery_intervals(start_time);
CREATE INDEX idx_hr_recovery_session_type ON hr_recovery_intervals(session_type);
CREATE INDEX idx_hr_recovery_anomaly ON hr_recovery_intervals(anomaly_score DESC NULLS LAST) WHERE anomaly_score IS NOT NULL;
CREATE INDEX idx_hr_recovery_low_signal ON hr_recovery_intervals(is_low_signal) WHERE is_low_signal = true;

-- Session-level summary (materialized view approach - table for now)
CREATE TABLE hr_recovery_session_summary (
    id SERIAL PRIMARY KEY,
    
    -- Session link
    polar_session_id INTEGER REFERENCES polar_sessions(id) UNIQUE,
    endurance_session_id INTEGER REFERENCES endurance_sessions(id) UNIQUE,
    
    -- Counts
    interval_count INTEGER NOT NULL,
    clean_interval_count INTEGER,
    low_signal_count INTEGER,
    
    -- Aggregate metrics
    avg_hrr60_abs NUMERIC(5,2),
    avg_hrr60_frac NUMERIC(5,4),
    avg_tau_seconds NUMERIC(6,2),
    avg_recovery_ratio NUMERIC(5,4),
    
    min_hrr60_abs SMALLINT,
    max_hrr60_abs SMALLINT,
    std_hrr60_abs NUMERIC(5,2),
    
    -- Fatigue trend within session (comparing first vs last intervals)
    first_interval_hrr60_frac NUMERIC(5,4),
    last_interval_hrr60_frac NUMERIC(5,4),
    intrasession_fatigue_delta NUMERIC(6,4),  -- last - first (negative = fatigue)
    
    -- Flags
    has_anomaly BOOLEAN DEFAULT false,
    anomaly_interval_count INTEGER DEFAULT 0,
    
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT hr_summary_session_required CHECK (
        polar_session_id IS NOT NULL OR endurance_session_id IS NOT NULL
    )
);

CREATE INDEX idx_hr_summary_polar ON hr_recovery_session_summary(polar_session_id) WHERE polar_session_id IS NOT NULL;
CREATE INDEX idx_hr_summary_endurance ON hr_recovery_session_summary(endurance_session_id) WHERE endurance_session_id IS NOT NULL;

-- Comments
COMMENT ON TABLE hr_recovery_intervals IS 'Detected recovery intervals with computed HRR features for FR-004';
COMMENT ON COLUMN hr_recovery_intervals.tau_seconds IS 'Exponential decay time constant from fit HR(t) = A*exp(-t/tau) + C';
COMMENT ON COLUMN hr_recovery_intervals.is_low_signal IS 'True when hr_reserve < 25 bpm (floor effect)';
COMMENT ON COLUMN hr_recovery_intervals.recovery_cluster IS 'ML-assigned cluster: fast_full, slow_partial, etc.';
