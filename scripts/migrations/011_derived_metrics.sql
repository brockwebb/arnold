-- Migration 011: Derived Metrics (Monotony, Strain, HRV CV, Sleep Debt)
-- Purpose: Science-backed Tier 1 metrics for coaching decisions
-- Created: 2026-01-06
--
-- References:
--   Monotony/Strain: Foster (1998) - Monitoring training in athletes
--   HRV CV: Plews et al. (2012) - Variation in variability
--   Sleep Debt: Spiegel et al. (1999) - Impact of sleep debt
--
-- Design principles:
--   1. Views build on existing tables (no new raw data)
--   2. Graceful degradation with NULLs when data insufficient
--   3. Configurable parameters via constants
--   4. Pre-computed for fast coach brief queries

-- ============================================================================
-- CONSTANTS (as a reference table for easy adjustment)
-- ============================================================================

CREATE TABLE IF NOT EXISTS metric_config (
    metric_name VARCHAR(50) NOT NULL,
    param_name VARCHAR(50) NOT NULL,
    param_value NUMERIC NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (metric_name, param_name)
);

-- Insert default values (upsert pattern)
INSERT INTO metric_config (metric_name, param_name, param_value, description) VALUES
    ('sleep_debt', 'target_hours', 7.5, 'Target sleep hours per night'),
    ('monotony', 'high_threshold', 2.0, 'Monotony above this = staleness risk'),
    ('monotony', 'moderate_threshold', 1.5, 'Monotony above this = monitor'),
    ('strain', 'high_threshold', 6000, 'Strain above this = illness/injury risk'),
    ('strain', 'moderate_threshold', 3000, 'Strain above this = productive but monitor'),
    ('hrv_cv', 'low_threshold', 3.0, 'CV below this = suppressed autonomic flexibility'),
    ('hrv_cv', 'high_threshold', 15.0, 'CV above this = recovery inconsistency')
ON CONFLICT (metric_name, param_name) DO NOTHING;


-- ============================================================================
-- VIEW 1: training_monotony_strain
-- Adds Monotony and Strain to daily training load
-- ============================================================================

DROP VIEW IF EXISTS training_monotony_strain CASCADE;

CREATE VIEW training_monotony_strain AS
WITH daily_with_stats AS (
    SELECT 
        workout_date,
        daily_sets,
        daily_volume,
        workout_count,
        acute_7d,
        chronic_28d,
        acwr,
        
        -- 7-day rolling statistics for monotony calculation
        AVG(daily_volume) OVER w7 as avg_volume_7d,
        STDDEV_SAMP(daily_volume) OVER w7 as stddev_volume_7d,
        COUNT(*) OVER w7 as days_in_window,
        
        -- Weekly sum for strain (sum of 7 days, not avg * 7)
        SUM(daily_volume) OVER w7 as weekly_volume
        
    FROM training_load_daily
    WINDOW w7 AS (ORDER BY workout_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
)
SELECT 
    workout_date,
    daily_sets,
    daily_volume,
    workout_count,
    acute_7d,
    chronic_28d,
    acwr,
    
    -- Monotony = mean / stddev (only if we have full 7 days and stddev > 0)
    CASE 
        WHEN days_in_window >= 7 AND stddev_volume_7d > 0 
        THEN ROUND((avg_volume_7d / stddev_volume_7d)::numeric, 2)
        ELSE NULL 
    END as monotony,
    
    -- Monotony zone classification
    CASE 
        WHEN days_in_window < 7 OR stddev_volume_7d IS NULL OR stddev_volume_7d = 0 THEN 'insufficient_data'
        WHEN (avg_volume_7d / stddev_volume_7d) > 2.0 THEN 'high'
        WHEN (avg_volume_7d / stddev_volume_7d) > 1.5 THEN 'moderate'
        ELSE 'good'
    END as monotony_zone,
    
    -- Strain = weekly load × monotony
    CASE 
        WHEN days_in_window >= 7 AND stddev_volume_7d > 0 
        THEN ROUND((weekly_volume * (avg_volume_7d / stddev_volume_7d))::numeric, 0)
        ELSE NULL 
    END as strain,
    
    -- Strain zone classification  
    CASE 
        WHEN days_in_window < 7 OR stddev_volume_7d IS NULL OR stddev_volume_7d = 0 THEN 'insufficient_data'
        WHEN (weekly_volume * (avg_volume_7d / NULLIF(stddev_volume_7d, 0))) > 6000 THEN 'high'
        WHEN (weekly_volume * (avg_volume_7d / NULLIF(stddev_volume_7d, 0))) > 3000 THEN 'moderate'
        ELSE 'low'
    END as strain_zone,
    
    -- Raw components for debugging/analysis
    ROUND(avg_volume_7d::numeric, 0) as avg_volume_7d,
    ROUND(stddev_volume_7d::numeric, 0) as stddev_volume_7d,
    ROUND(weekly_volume::numeric, 0) as weekly_volume
    
FROM daily_with_stats
ORDER BY workout_date DESC;

COMMENT ON VIEW training_monotony_strain IS 
'Training load with Monotony and Strain metrics (Foster 1998). 
Monotony = consistency of daily load (high = same thing every day = staleness risk).
Strain = weekly load × monotony (combines volume and repetitiveness).';


-- ============================================================================
-- VIEW 2: biometric_derived  
-- Adds HRV CV and Sleep Debt to daily biometrics
-- ============================================================================

DROP VIEW IF EXISTS biometric_derived CASCADE;

CREATE VIEW biometric_derived AS
WITH daily_biometrics AS (
    -- Pivot biometric readings into daily rows
    SELECT 
        reading_date,
        MAX(CASE WHEN metric_type = 'hrv_morning' THEN value END) as hrv_ms,
        MAX(CASE WHEN metric_type = 'resting_hr' THEN value END) as rhr_bpm,
        MAX(CASE WHEN metric_type = 'sleep_total_min' THEN value END) as sleep_min
    FROM biometric_readings
    WHERE LOWER(source) = 'ultrahuman'
    GROUP BY reading_date
),
with_rolling AS (
    SELECT 
        reading_date,
        hrv_ms,
        rhr_bpm,
        sleep_min,
        sleep_min / 60.0 as sleep_hours,
        
        -- HRV rolling stats for CV calculation
        AVG(hrv_ms) OVER w7 as hrv_7d_avg,
        STDDEV_SAMP(hrv_ms) OVER w7 as hrv_7d_stddev,
        COUNT(hrv_ms) OVER w7 as hrv_7d_count,
        
        -- Sleep rolling for debt calculation (need actual values, not nulls)
        -- Target is 7.5 hours = 450 minutes
        SUM(CASE WHEN sleep_min IS NOT NULL THEN 450 - sleep_min ELSE 0 END) OVER w7 as sleep_debt_min_7d,
        COUNT(sleep_min) OVER w7 as sleep_7d_count
        
    FROM daily_biometrics
    WINDOW w7 AS (ORDER BY reading_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
)
SELECT 
    reading_date,
    hrv_ms,
    rhr_bpm,
    ROUND(sleep_hours::numeric, 1) as sleep_hours,
    
    -- HRV Coefficient of Variation
    CASE 
        WHEN hrv_7d_count >= 5 AND hrv_7d_avg > 0 AND hrv_7d_stddev IS NOT NULL
        THEN ROUND((hrv_7d_stddev / hrv_7d_avg * 100)::numeric, 1)
        ELSE NULL 
    END as hrv_cv_7d,
    
    -- HRV CV zone classification
    CASE 
        WHEN hrv_7d_count < 5 OR hrv_7d_avg IS NULL OR hrv_7d_avg = 0 THEN 'insufficient_data'
        WHEN (hrv_7d_stddev / hrv_7d_avg * 100) < 3 THEN 'suppressed'
        WHEN (hrv_7d_stddev / hrv_7d_avg * 100) > 15 THEN 'elevated'
        ELSE 'normal'
    END as hrv_cv_zone,
    
    -- Sleep Debt (positive = debt, negative = surplus)
    CASE 
        WHEN sleep_7d_count >= 5 
        THEN ROUND((sleep_debt_min_7d / 60.0)::numeric, 1)
        ELSE NULL 
    END as sleep_debt_hours_7d,
    
    -- Sleep debt zone classification
    CASE 
        WHEN sleep_7d_count < 5 THEN 'insufficient_data'
        WHEN (sleep_debt_min_7d / 60.0) > 10 THEN 'critical'
        WHEN (sleep_debt_min_7d / 60.0) > 5 THEN 'significant'
        WHEN (sleep_debt_min_7d / 60.0) > 3 THEN 'moderate'
        WHEN (sleep_debt_min_7d / 60.0) > 0 THEN 'minor'
        ELSE 'surplus'
    END as sleep_debt_zone,
    
    -- Data quality indicators
    hrv_7d_count,
    sleep_7d_count,
    ROUND(hrv_7d_avg::numeric, 1) as hrv_7d_avg,
    ROUND(hrv_7d_stddev::numeric, 1) as hrv_7d_stddev
    
FROM with_rolling
ORDER BY reading_date DESC;

COMMENT ON VIEW biometric_derived IS 
'Biometric data with HRV CV and Sleep Debt metrics.
HRV CV (Plews 2012): Low CV (<3%) = suppressed autonomic flexibility = possible overreaching.
Sleep Debt (Spiegel 1999): Cumulative deficit vs 7.5hr target over 7 days.';


-- ============================================================================
-- VIEW 3: readiness_composite
-- Single readiness score combining multiple inputs
-- ============================================================================

DROP VIEW IF EXISTS readiness_composite CASCADE;

CREATE VIEW readiness_composite AS
WITH combined AS (
    SELECT 
        COALESCE(b.reading_date, t.workout_date) as date,
        
        -- Biometric inputs
        b.hrv_ms,
        b.hrv_cv_7d,
        b.hrv_cv_zone,
        b.sleep_hours,
        b.sleep_debt_hours_7d,
        b.sleep_debt_zone,
        b.rhr_bpm,
        
        -- Training inputs
        t.acwr,
        t.monotony,
        t.monotony_zone,
        t.strain,
        t.strain_zone,
        
        -- HRV baseline comparison (from biometric_trends if available)
        bt.hrv_30d_avg,
        bt.hrv_7d_avg as hrv_recent_avg
        
    FROM biometric_derived b
    FULL OUTER JOIN training_monotony_strain t 
        ON b.reading_date = t.workout_date
    LEFT JOIN biometric_trends bt 
        ON b.reading_date = bt.reading_date
)
SELECT 
    date,
    hrv_ms,
    hrv_cv_7d,
    hrv_cv_zone,
    sleep_hours,
    sleep_debt_hours_7d,
    sleep_debt_zone,
    rhr_bpm,
    acwr,
    monotony,
    monotony_zone,
    strain,
    strain_zone,
    hrv_30d_avg,
    
    -- HRV vs baseline percentage
    CASE 
        WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL AND hrv_30d_avg > 0
        THEN ROUND(((hrv_ms - hrv_30d_avg) / hrv_30d_avg * 100)::numeric, 0)
        ELSE NULL 
    END as hrv_vs_baseline_pct,
    
    -- Count red flags for quick assessment
    (
        CASE WHEN hrv_cv_zone = 'suppressed' THEN 1 ELSE 0 END +
        CASE WHEN sleep_debt_zone IN ('significant', 'critical') THEN 1 ELSE 0 END +
        CASE WHEN strain_zone = 'high' THEN 1 ELSE 0 END +
        CASE WHEN acwr > 1.5 THEN 1 ELSE 0 END +
        CASE WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL 
             AND ((hrv_ms - hrv_30d_avg) / NULLIF(hrv_30d_avg, 0) * 100) < -20 THEN 1 ELSE 0 END
    ) as red_flag_count,
    
    -- Overall readiness assessment
    CASE 
        -- Red: Any critical condition
        WHEN hrv_cv_zone = 'suppressed' THEN 'recover'
        WHEN sleep_debt_zone = 'critical' THEN 'recover'
        WHEN strain_zone = 'high' THEN 'recover'
        WHEN acwr > 1.5 THEN 'recover'
        WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL 
             AND ((hrv_ms - hrv_30d_avg) / NULLIF(hrv_30d_avg, 0) * 100) < -20 THEN 'recover'
        
        -- Yellow: Caution conditions
        WHEN sleep_debt_zone = 'significant' THEN 'caution'
        WHEN monotony_zone = 'high' THEN 'caution'
        WHEN acwr > 1.3 THEN 'caution'
        WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL 
             AND ((hrv_ms - hrv_30d_avg) / NULLIF(hrv_30d_avg, 0) * 100) < -10 THEN 'caution'
        
        -- Green: Good to go
        ELSE 'ready'
    END as readiness_status
    
FROM combined
WHERE date IS NOT NULL
ORDER BY date DESC;

COMMENT ON VIEW readiness_composite IS 
'Combined readiness assessment from biometric and training metrics.
Red flags trigger "recover" status, yellow flags trigger "caution", otherwise "ready".';


-- ============================================================================
-- UPDATE: coach_brief_snapshot (add new metrics)
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS coach_brief_snapshot CASCADE;

CREATE MATERIALIZED VIEW coach_brief_snapshot AS
WITH latest_readiness AS (
    SELECT * FROM readiness_composite 
    WHERE date = (SELECT MAX(date) FROM readiness_composite)
    LIMIT 1
),
latest_training AS (
    SELECT * FROM training_monotony_strain
    WHERE workout_date = (SELECT MAX(workout_date) FROM training_monotony_strain)
    LIMIT 1
),
latest_biometric AS (
    SELECT * FROM biometric_derived
    WHERE reading_date = (SELECT MAX(reading_date) FROM biometric_derived WHERE hrv_ms IS NOT NULL)
    LIMIT 1
),
recent_workout_count AS (
    SELECT COUNT(*) as workouts_7d
    FROM strength_sessions
    WHERE session_date >= CURRENT_DATE - INTERVAL '7 days'
      AND status = 'completed'
),
data_freshness AS (
    SELECT 
        MAX(reading_date) FILTER (WHERE metric_type = 'hrv_morning') as last_hrv_date,
        MAX(reading_date) FILTER (WHERE metric_type = 'sleep_total_min') as last_sleep_date
    FROM biometric_readings
    WHERE LOWER(source) = 'ultrahuman'
)
SELECT 
    CURRENT_DATE as report_date,
    
    -- Readiness summary
    r.readiness_status,
    r.red_flag_count,
    
    -- Today's biometrics
    b.hrv_ms as today_hrv,
    b.rhr_bpm as today_rhr,
    b.sleep_hours as today_sleep_hours,
    
    -- Derived metrics
    b.hrv_cv_7d,
    b.hrv_cv_zone,
    b.sleep_debt_hours_7d,
    b.sleep_debt_zone,
    
    -- Training metrics
    t.acwr,
    t.monotony,
    t.monotony_zone,
    t.strain,
    t.strain_zone,
    
    -- Context
    r.hrv_vs_baseline_pct,
    r.hrv_30d_avg as hrv_baseline,
    w.workouts_7d,
    
    -- Data freshness
    f.last_hrv_date,
    f.last_sleep_date,
    CURRENT_DATE - f.last_hrv_date as days_since_hrv,
    CURRENT_DATE - f.last_sleep_date as days_since_sleep
    
FROM latest_readiness r
CROSS JOIN latest_training t
CROSS JOIN latest_biometric b
CROSS JOIN recent_workout_count w
CROSS JOIN data_freshness f;

CREATE INDEX idx_coach_brief_date ON coach_brief_snapshot(report_date);


-- ============================================================================
-- REFRESH FUNCTION (updated to include new views)
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_coach_views()
RETURNS void AS $$
BEGIN
    -- Refresh materialized views that depend on biometric_trends
    REFRESH MATERIALIZED VIEW biometric_trends;
    REFRESH MATERIALIZED VIEW training_trends;
    REFRESH MATERIALIZED VIEW coach_brief_snapshot;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- HELPER FUNCTION: Get current readiness assessment
-- ============================================================================

CREATE OR REPLACE FUNCTION get_readiness(check_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (
    date DATE,
    readiness_status TEXT,
    red_flag_count INT,
    hrv_ms NUMERIC,
    hrv_cv_7d NUMERIC,
    hrv_cv_zone TEXT,
    sleep_hours NUMERIC,
    sleep_debt_hours_7d NUMERIC,
    sleep_debt_zone TEXT,
    acwr NUMERIC,
    monotony NUMERIC,
    monotony_zone TEXT,
    strain NUMERIC,
    strain_zone TEXT,
    hrv_vs_baseline_pct NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        rc.date,
        rc.readiness_status,
        rc.red_flag_count::INT,
        rc.hrv_ms,
        rc.hrv_cv_7d,
        rc.hrv_cv_zone,
        rc.sleep_hours,
        rc.sleep_debt_hours_7d,
        rc.sleep_debt_zone,
        rc.acwr,
        rc.monotony,
        rc.monotony_zone,
        rc.strain,
        rc.strain_zone,
        rc.hrv_vs_baseline_pct
    FROM readiness_composite rc
    WHERE rc.date = check_date;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_readiness IS 
'Get readiness assessment for a specific date. Returns all derived metrics and overall status.';


-- ============================================================================
-- VIEW 4: srpe_training_load
-- Session RPE × Duration per Foster (1998)
-- ============================================================================

DROP VIEW IF EXISTS srpe_training_load CASCADE;

CREATE VIEW srpe_training_load AS
WITH session_data AS (
    SELECT 
        ss.session_date,
        ss.name,
        ss.total_volume_lbs,
        
        -- Duration cascade: Polar actual → strength_sessions logged → default 45
        COALESCE(
            ps.duration_seconds / 60,
            ss.duration_minutes,
            45  -- Default per user preference
        )::INT as duration_minutes,
        
        -- RPE cascade: session_rpe → avg_rpe → type-based default
        COALESCE(
            ss.session_rpe,
            ss.avg_rpe,
            CASE 
                WHEN LOWER(ss.name) LIKE '%fifty%' THEN 8
                WHEN LOWER(ss.name) LIKE '%conditioning%' THEN 7
                WHEN LOWER(ss.name) LIKE '%crossfit%' THEN 7
                WHEN LOWER(ss.name) LIKE '%endurance%' THEN 5
                WHEN LOWER(ss.name) LIKE '%strength%' THEN 6
                ELSE 6
            END
        )::NUMERIC as session_rpe,
        
        CASE 
            WHEN ss.session_rpe IS NOT NULL THEN 'user_provided'
            WHEN ss.avg_rpe IS NOT NULL THEN 'set_average'
            ELSE 'imputed'
        END as rpe_source,
        
        CASE 
            WHEN ps.duration_seconds IS NOT NULL THEN 'polar_actual'
            WHEN ss.duration_minutes IS NOT NULL THEN 'logged'
            ELSE 'default_45'
        END as duration_source
        
    FROM strength_sessions ss
    LEFT JOIN polar_sessions ps 
        ON DATE(ps.start_time) = ss.session_date
    WHERE ss.status = 'completed'
)
SELECT 
    session_date,
    name,
    duration_minutes,
    session_rpe,
    ROUND((session_rpe * duration_minutes)::NUMERIC, 0) as srpe_load,
    total_volume_lbs,
    rpe_source,
    duration_source
FROM session_data
ORDER BY session_date DESC;

COMMENT ON VIEW srpe_training_load IS 
'Session RPE load per Foster (1998). sRPE Load = RPE × Duration (minutes).
Data cascade: RPE (user → set_avg → imputed), Duration (polar → logged → 45min default).';


-- ============================================================================
-- VIEW 5: srpe_monotony_strain
-- Proper Foster Monotony/Strain using sRPE
-- ============================================================================

DROP VIEW IF EXISTS srpe_monotony_strain CASCADE;

CREATE VIEW srpe_monotony_strain AS
WITH daily_srpe AS (
    SELECT 
        session_date as workout_date,
        SUM(srpe_load) as daily_srpe_load,
        COUNT(*) as session_count,
        STRING_AGG(rpe_source, ', ') as rpe_sources,
        STRING_AGG(duration_source, ', ') as duration_sources
    FROM srpe_training_load
    GROUP BY session_date
),
date_series AS (
    SELECT generate_series(
        (SELECT MIN(workout_date) FROM daily_srpe),
        CURRENT_DATE,
        '1 day'::interval
    )::date AS dt
),
filled AS (
    SELECT 
        ds.dt as workout_date,
        COALESCE(d.daily_srpe_load, 0) as daily_srpe_load,
        COALESCE(d.session_count, 0) as session_count,
        d.rpe_sources,
        d.duration_sources
    FROM date_series ds
    LEFT JOIN daily_srpe d ON d.workout_date = ds.dt
),
with_rolling AS (
    SELECT 
        workout_date,
        daily_srpe_load,
        session_count,
        rpe_sources,
        duration_sources,
        AVG(daily_srpe_load) OVER w7 as avg_srpe_7d,
        STDDEV_SAMP(daily_srpe_load) OVER w7 as stddev_srpe_7d,
        SUM(daily_srpe_load) OVER w7 as weekly_srpe_load,
        COUNT(*) OVER w7 as days_in_window
    FROM filled
    WINDOW w7 AS (ORDER BY workout_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
)
SELECT 
    workout_date,
    daily_srpe_load,
    session_count,
    ROUND(weekly_srpe_load::numeric, 0) as weekly_srpe_load,
    
    CASE 
        WHEN days_in_window >= 7 AND stddev_srpe_7d > 0 
        THEN ROUND((avg_srpe_7d / stddev_srpe_7d)::numeric, 2)
        ELSE NULL 
    END as monotony,
    
    CASE 
        WHEN days_in_window < 7 OR stddev_srpe_7d IS NULL OR stddev_srpe_7d = 0 THEN 'insufficient_data'
        WHEN (avg_srpe_7d / stddev_srpe_7d) > 2.0 THEN 'high'
        WHEN (avg_srpe_7d / stddev_srpe_7d) > 1.5 THEN 'moderate'
        ELSE 'good'
    END as monotony_zone,
    
    CASE 
        WHEN days_in_window >= 7 AND stddev_srpe_7d > 0 
        THEN ROUND((weekly_srpe_load * (avg_srpe_7d / stddev_srpe_7d))::numeric, 0)
        ELSE NULL 
    END as strain,
    
    CASE 
        WHEN days_in_window < 7 OR stddev_srpe_7d IS NULL OR stddev_srpe_7d = 0 THEN 'insufficient_data'
        WHEN (weekly_srpe_load * (avg_srpe_7d / NULLIF(stddev_srpe_7d, 0))) > 6000 THEN 'very_high'
        WHEN (weekly_srpe_load * (avg_srpe_7d / NULLIF(stddev_srpe_7d, 0))) > 4000 THEN 'high'
        WHEN (weekly_srpe_load * (avg_srpe_7d / NULLIF(stddev_srpe_7d, 0))) > 2000 THEN 'moderate'
        ELSE 'low'
    END as strain_zone,
    
    rpe_sources,
    duration_sources,
    ROUND(avg_srpe_7d::numeric, 0) as avg_srpe_7d,
    ROUND(stddev_srpe_7d::numeric, 0) as stddev_srpe_7d
    
FROM with_rolling
WHERE workout_date >= (SELECT MIN(workout_date) + 27 FROM daily_srpe)
ORDER BY workout_date DESC;

COMMENT ON VIEW srpe_monotony_strain IS 
'Foster (1998) Monotony and Strain using session RPE × duration.
Monotony = Mean(daily load) / SD(daily load). High (>2.0) = staleness risk.
Strain = Weekly load × Monotony. >4000 AU = monitor, >6000 AU = high risk.';


-- ============================================================================
-- VIEW 6: daily_activity_context
-- Steps as lifestyle/NEAT indicator (NOT training load)
-- Science: Emerging evidence suggests reduced spontaneous activity may signal
-- overreaching (Smith 2000, 3ST project). Not yet validated like TRIMP/sRPE.
-- ============================================================================

DROP VIEW IF EXISTS daily_activity_context CASCADE;

CREATE VIEW daily_activity_context AS
WITH daily_steps AS (
    SELECT 
        reading_date,
        value as steps
    FROM biometric_readings
    WHERE metric_type = 'steps'
      AND LOWER(source) IN ('ultrahuman', 'apple_health')
),
with_baseline AS (
    SELECT 
        reading_date,
        steps,
        AVG(steps) OVER w30 as baseline_30d,
        STDDEV_SAMP(steps) OVER w30 as stddev_30d,
        COUNT(steps) OVER w30 as days_with_data_30d,
        AVG(steps) OVER w7 as avg_7d,
        COUNT(steps) OVER w7 as days_with_data_7d
    FROM daily_steps
    WINDOW 
        w7 AS (ORDER BY reading_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
        w30 AS (ORDER BY reading_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
SELECT 
    reading_date,
    steps::INT,
    ROUND(baseline_30d::numeric, 0)::INT as baseline_30d,
    ROUND(avg_7d::numeric, 0)::INT as avg_7d,
    
    CASE 
        WHEN baseline_30d > 0 
        THEN ROUND(((steps - baseline_30d) / baseline_30d * 100)::numeric, 0)
        ELSE NULL 
    END as pct_vs_baseline,
    
    CASE 
        WHEN stddev_30d > 0 
        THEN ROUND(((steps - baseline_30d) / stddev_30d)::numeric, 1)
        ELSE NULL 
    END as z_score,
    
    CASE 
        WHEN steps < 2500 THEN 'very_low'
        WHEN steps < 5000 THEN 'low'
        WHEN steps < 7500 THEN 'moderate'
        WHEN steps < 10000 THEN 'active'
        WHEN steps < 15000 THEN 'very_active'
        ELSE 'highly_active'
    END as activity_level,
    
    CASE 
        WHEN days_with_data_30d < 14 THEN 'insufficient_baseline'
        WHEN stddev_30d > 0 AND ((steps - baseline_30d) / stddev_30d) < -2.0 THEN 'significant_decrease'
        WHEN stddev_30d > 0 AND ((steps - baseline_30d) / stddev_30d) < -1.5 THEN 'notable_decrease'
        WHEN stddev_30d > 0 AND ((steps - baseline_30d) / stddev_30d) > 2.0 THEN 'significant_increase'
        ELSE 'normal'
    END as deviation_flag,
    
    days_with_data_30d,
    days_with_data_7d
    
FROM with_baseline
ORDER BY reading_date DESC;

COMMENT ON VIEW daily_activity_context IS 
'Daily step count as lifestyle/NEAT context indicator.
NOT a training load metric. Use for:
- Personal baseline comparison (deviation detection)
- Recovery tracking (post-surgery, illness)
- General activity level context
Significant decreases MAY indicate fatigue, illness, or overreaching (emerging research, not validated).';


-- ============================================================================
-- GRANTS
-- ============================================================================

GRANT SELECT ON training_monotony_strain TO PUBLIC;
GRANT SELECT ON biometric_derived TO PUBLIC;
GRANT SELECT ON readiness_composite TO PUBLIC;
GRANT SELECT ON coach_brief_snapshot TO PUBLIC;
GRANT SELECT ON metric_config TO PUBLIC;
GRANT SELECT ON srpe_training_load TO PUBLIC;
GRANT SELECT ON srpe_monotony_strain TO PUBLIC;
GRANT SELECT ON daily_activity_context TO PUBLIC;
