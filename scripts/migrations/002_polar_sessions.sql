-- Migration: Add Polar session and HR sample tables
-- Run: psql -d arnold_analytics -f scripts/migrations/002_polar_sessions.sql

-- Session-level summary (one row per Polar training session)
CREATE TABLE IF NOT EXISTS polar_sessions (
    id SERIAL PRIMARY KEY,
    polar_session_id TEXT UNIQUE NOT NULL,  -- extracted from filename
    start_time TIMESTAMPTZ NOT NULL,
    stop_time TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL,
    sport_type TEXT,  -- CIRCUIT_TRAINING, RUNNING, STRENGTH_TRAINING, etc.
    
    -- Heart rate summary
    avg_hr SMALLINT,
    max_hr SMALLINT,
    min_hr SMALLINT,
    calories INTEGER,
    
    -- Time in zones (seconds)
    zone_1_seconds INTEGER DEFAULT 0,
    zone_2_seconds INTEGER DEFAULT 0,
    zone_3_seconds INTEGER DEFAULT 0,
    zone_4_seconds INTEGER DEFAULT 0,
    zone_5_seconds INTEGER DEFAULT 0,
    
    -- Zone boundaries (for reference - these can change with settings)
    zone_1_lower SMALLINT,
    zone_1_upper SMALLINT,
    zone_2_lower SMALLINT,
    zone_2_upper SMALLINT,
    zone_3_lower SMALLINT,
    zone_3_upper SMALLINT,
    zone_4_lower SMALLINT,
    zone_4_upper SMALLINT,
    zone_5_lower SMALLINT,
    zone_5_upper SMALLINT,
    
    -- Physical snapshot at session time
    vo2max SMALLINT,
    resting_hr SMALLINT,
    max_hr_setting SMALLINT,
    ftp SMALLINT,
    weight_kg NUMERIC(5,2),
    
    -- Metadata
    timezone_offset INTEGER,  -- minutes from UTC
    feeling NUMERIC(4,3),  -- 0-1 scale RPE from Polar
    note TEXT,
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

-- Second-by-second HR samples
CREATE TABLE IF NOT EXISTS hr_samples (
    id BIGSERIAL PRIMARY KEY,  -- BIGSERIAL for potentially millions of rows
    session_id INTEGER NOT NULL REFERENCES polar_sessions(id) ON DELETE CASCADE,
    sample_time TIMESTAMPTZ NOT NULL,
    hr_value SMALLINT NOT NULL
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_polar_sessions_start ON polar_sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_polar_sessions_sport ON polar_sessions(sport_type);
CREATE INDEX IF NOT EXISTS idx_hr_samples_session ON hr_samples(session_id);
CREATE INDEX IF NOT EXISTS idx_hr_samples_session_time ON hr_samples(session_id, sample_time);

-- For joining to Arnold workouts by date
CREATE INDEX IF NOT EXISTS idx_polar_sessions_date ON polar_sessions((start_time::date));

COMMENT ON TABLE polar_sessions IS 'Polar HR monitor training sessions with zone data and physical snapshots';
COMMENT ON TABLE hr_samples IS 'Second-by-second heart rate samples from Polar sessions';
COMMENT ON COLUMN polar_sessions.sport_type IS 'User-tagged workout type: CIRCUIT_TRAINING, RUNNING, STRENGTH_TRAINING, HIIT, etc.';
COMMENT ON COLUMN polar_sessions.ftp IS 'Functional Threshold Power (watts) - cycling metric';

-- ============================================================================
-- ANALYTICS VIEWS
-- ============================================================================

-- Session-level metrics with TRIMP calculations
CREATE OR REPLACE VIEW polar_session_metrics AS
SELECT 
    ps.id,
    ps.polar_session_id,
    ps.start_time,
    ps.start_time::date as session_date,
    ps.sport_type,
    ps.duration_seconds,
    ps.duration_seconds / 60.0 as duration_minutes,
    ps.avg_hr,
    ps.max_hr,
    ps.min_hr,
    ps.resting_hr,
    ps.max_hr_setting,
    ps.calories,
    ps.feeling,
    
    -- Zone time in minutes
    ps.zone_1_seconds / 60.0 as zone_1_min,
    ps.zone_2_seconds / 60.0 as zone_2_min,
    ps.zone_3_seconds / 60.0 as zone_3_min,
    ps.zone_4_seconds / 60.0 as zone_4_min,
    ps.zone_5_seconds / 60.0 as zone_5_min,
    
    -- HR reserve ratio (0-1)
    CASE 
        WHEN ps.max_hr_setting IS NOT NULL AND ps.resting_hr IS NOT NULL 
             AND ps.max_hr_setting > ps.resting_hr
        THEN (ps.avg_hr - ps.resting_hr)::numeric / (ps.max_hr_setting - ps.resting_hr)
        ELSE NULL
    END as hr_reserve_ratio,
    
    -- Banister TRIMP (male formula)
    CASE 
        WHEN ps.max_hr_setting IS NOT NULL AND ps.resting_hr IS NOT NULL 
             AND ps.max_hr_setting > ps.resting_hr
        THEN ROUND(
            (ps.duration_seconds / 60.0) 
            * ((ps.avg_hr - ps.resting_hr)::numeric / (ps.max_hr_setting - ps.resting_hr))
            * 0.64 
            * EXP(1.92 * ((ps.avg_hr - ps.resting_hr)::numeric / (ps.max_hr_setting - ps.resting_hr)))
        , 1)
        ELSE NULL
    END as trimp,
    
    -- Zone-based training load (Edwards TRIMP)
    ROUND(
        (COALESCE(ps.zone_1_seconds, 0) * 1 +
         COALESCE(ps.zone_2_seconds, 0) * 2 +
         COALESCE(ps.zone_3_seconds, 0) * 3 +
         COALESCE(ps.zone_4_seconds, 0) * 4 +
         COALESCE(ps.zone_5_seconds, 0) * 5) / 60.0
    , 1) as edwards_trimp,
    
    -- Intensity Factor (avg_hr / threshold_hr)
    CASE 
        WHEN ps.max_hr_setting IS NOT NULL
        THEN ROUND(ps.avg_hr::numeric / (ps.max_hr_setting * 0.88), 2)
        ELSE NULL
    END as intensity_factor

FROM polar_sessions ps;

-- Daily HR-based training load aggregation
CREATE OR REPLACE VIEW hr_training_load_daily AS
SELECT 
    session_date,
    COUNT(*) as sessions,
    ROUND(SUM(duration_minutes), 0) as total_minutes,
    ROUND(AVG(avg_hr), 0) as weighted_avg_hr,
    MAX(max_hr) as peak_hr,
    ROUND(SUM(trimp), 1) as daily_trimp,
    ROUND(SUM(edwards_trimp), 1) as daily_edwards_trimp,
    ROUND(SUM(zone_1_min), 1) as z1_minutes,
    ROUND(SUM(zone_2_min), 1) as z2_minutes,
    ROUND(SUM(zone_3_min), 1) as z3_minutes,
    ROUND(SUM(zone_4_min), 1) as z4_minutes,
    ROUND(SUM(zone_5_min), 1) as z5_minutes,
    ROUND(100.0 * (SUM(COALESCE(zone_1_min,0)) + SUM(COALESCE(zone_2_min,0))) / 
          NULLIF(SUM(duration_minutes), 0), 1) as pct_low_intensity,
    ROUND(100.0 * (SUM(COALESCE(zone_4_min,0)) + SUM(COALESCE(zone_5_min,0))) / 
          NULLIF(SUM(duration_minutes), 0), 1) as pct_high_intensity,
    STRING_AGG(DISTINCT sport_type, ', ' ORDER BY sport_type) as sport_types
FROM polar_session_metrics
GROUP BY session_date;

-- TRIMP-based ACWR (more meaningful than volume-based)
CREATE OR REPLACE VIEW trimp_acwr AS
WITH daily_load AS (
    SELECT session_date, COALESCE(daily_edwards_trimp, 0) as trimp
    FROM hr_training_load_daily
),
date_series AS (
    SELECT generate_series(
        (SELECT MIN(session_date) FROM daily_load),
        CURRENT_DATE,
        '1 day'::interval
    )::date as dt
),
filled AS (
    SELECT ds.dt as session_date, COALESCE(dl.trimp, 0) as trimp
    FROM date_series ds
    LEFT JOIN daily_load dl ON dl.session_date = ds.dt
)
SELECT 
    session_date,
    trimp as daily_trimp,
    ROUND(SUM(trimp) OVER (ORDER BY session_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) as acute_trimp_7d,
    ROUND(AVG(trimp) OVER (ORDER BY session_date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) * 7, 1) as chronic_trimp_7d_equiv,
    ROUND(
        SUM(trimp) OVER (ORDER BY session_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) /
        NULLIF(AVG(trimp) OVER (ORDER BY session_date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) * 7, 0)
    , 2) as trimp_acwr
FROM filled
WHERE session_date >= (SELECT MIN(session_date) + 28 FROM daily_load);

-- Combined training load view (volume + HR)
CREATE OR REPLACE VIEW combined_training_load AS
WITH volume_daily AS (
    SELECT 
        workout_date,
        SUM(total_volume_lbs) as daily_volume_lbs,
        SUM(set_count) as daily_sets,
        STRING_AGG(DISTINCT workout_type, ', ') as workout_types
    FROM workout_summaries
    GROUP BY workout_date
),
hr_daily AS (
    SELECT 
        session_date as workout_date,
        total_minutes,
        weighted_avg_hr,
        peak_hr,
        daily_trimp,
        daily_edwards_trimp,
        pct_low_intensity,
        pct_high_intensity,
        sport_types
    FROM hr_training_load_daily
)
SELECT 
    COALESCE(v.workout_date, h.workout_date) as workout_date,
    v.daily_volume_lbs,
    v.daily_sets,
    v.workout_types,
    h.total_minutes as hr_minutes,
    h.weighted_avg_hr,
    h.peak_hr,
    h.daily_trimp,
    h.daily_edwards_trimp,
    h.pct_low_intensity,
    h.pct_high_intensity,
    h.sport_types as polar_sport,
    CASE 
        WHEN v.workout_date IS NOT NULL AND h.workout_date IS NOT NULL THEN 'complete'
        WHEN v.workout_date IS NOT NULL THEN 'volume_only'
        WHEN h.workout_date IS NOT NULL THEN 'hr_only'
    END as data_coverage
FROM volume_daily v
FULL OUTER JOIN hr_daily h ON v.workout_date = h.workout_date;

-- Daily readiness from biometrics
CREATE MATERIALIZED VIEW IF NOT EXISTS readiness_daily AS
SELECT 
    reading_date,
    MAX(CASE WHEN metric_type = 'hrv_morning' THEN value END) as hrv_ms,
    MAX(CASE WHEN metric_type = 'resting_hr' THEN value END) as rhr_bpm,
    MAX(CASE WHEN metric_type = 'sleep_total_min' THEN value END) as sleep_total_min,
    MAX(CASE WHEN metric_type = 'sleep_total_min' THEN value END) / 60.0 as sleep_hours,
    MAX(CASE WHEN metric_type = 'sleep_deep_min' THEN value END) as sleep_deep_min,
    MAX(CASE WHEN metric_type = 'sleep_rem_min' THEN value END) as sleep_rem_min,
    ROUND(100.0 * (
        COALESCE(MAX(CASE WHEN metric_type = 'sleep_deep_min' THEN value END), 0) +
        COALESCE(MAX(CASE WHEN metric_type = 'sleep_rem_min' THEN value END), 0)
    ) / NULLIF(MAX(CASE WHEN metric_type = 'sleep_total_min' THEN value END), 0), 1) as sleep_quality_pct
FROM biometric_readings
GROUP BY reading_date;

CREATE UNIQUE INDEX IF NOT EXISTS idx_readiness_date ON readiness_daily(reading_date);

-- Comprehensive daily status (training + readiness)
CREATE OR REPLACE VIEW daily_status AS
SELECT 
    COALESCE(ctl.workout_date, rd.reading_date) as date,
    ctl.workout_name,
    ctl.workout_type,
    ctl.daily_sets,
    ctl.daily_volume_lbs,
    ctl.polar_duration as duration_min,
    ctl.weighted_avg_hr as avg_hr,
    ctl.daily_trimp as trimp,
    ctl.daily_edwards_trimp as edwards_trimp,
    ctl.intensity_factor,
    rd.hrv_ms,
    rd.rhr_bpm,
    rd.sleep_hours,
    rd.sleep_deep_min,
    rd.sleep_rem_min,
    rd.sleep_quality_pct,
    CASE 
        WHEN ctl.workout_date IS NOT NULL AND ctl.data_coverage = 'linked' AND rd.reading_date IS NOT NULL THEN 'full'
        WHEN ctl.workout_date IS NOT NULL AND ctl.data_coverage = 'linked' THEN 'training+hr'
        WHEN ctl.workout_date IS NOT NULL AND rd.reading_date IS NOT NULL THEN 'training+readiness'
        WHEN ctl.workout_date IS NOT NULL THEN 'training_only'
        WHEN rd.reading_date IS NOT NULL THEN 'readiness_only'
        ELSE 'none'
    END as data_coverage
FROM combined_training_load ctl
FULL OUTER JOIN readiness_daily rd ON ctl.workout_date = rd.reading_date;
