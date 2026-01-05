-- Migration 006: Coach Brief Materialized Views
-- Purpose: Pre-computed trend metrics for coach brief reports
-- Created: 2026-01-04
--
-- Design principles:
-- 1. Graceful degradation: Views work with whatever data exists
-- 2. Tiered horizons: 7-day (week), 30-day (month), 90-day (quarter)
-- 3. Trend indicators: Direction + magnitude of change
-- 4. Data fitness flags: Know when data is sparse or missing

-- ============================================================================
-- VIEW 1: biometric_trends
-- Rolling averages and trend direction for HRV, RHR, sleep
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS biometric_trends CASCADE;

CREATE MATERIALIZED VIEW biometric_trends AS
WITH daily_metrics AS (
    -- Aggregate by date, preferring lowercase 'ultrahuman' source
    SELECT 
        reading_date,
        MAX(CASE WHEN metric_type = 'hrv_morning' THEN value END) as hrv_ms,
        MAX(CASE WHEN metric_type = 'resting_hr' THEN value END) as rhr_bpm,
        MAX(CASE WHEN metric_type = 'sleep_total_min' THEN value END) as sleep_min,
        MAX(CASE WHEN metric_type = 'sleep_deep_min' THEN value END) as deep_min,
        MAX(CASE WHEN metric_type = 'sleep_rem_min' THEN value END) as rem_min,
        MAX(CASE WHEN metric_type = 'recovery_score' THEN value END) as recovery_score,
        MAX(CASE WHEN metric_type = 'sleep_score' THEN value END) as sleep_score
    FROM biometric_readings
    WHERE LOWER(source) = 'ultrahuman'  -- Normalize case
    GROUP BY reading_date
),
with_rolling AS (
    SELECT 
        reading_date,
        hrv_ms,
        rhr_bpm,
        sleep_min,
        deep_min,
        rem_min,
        recovery_score,
        sleep_score,
        
        -- 7-day rolling averages
        AVG(hrv_ms) OVER w7 as hrv_7d_avg,
        AVG(rhr_bpm) OVER w7 as rhr_7d_avg,
        AVG(sleep_min) OVER w7 as sleep_7d_avg,
        COUNT(hrv_ms) OVER w7 as hrv_7d_count,
        COUNT(rhr_bpm) OVER w7 as rhr_7d_count,
        COUNT(sleep_min) OVER w7 as sleep_7d_count,
        
        -- 30-day rolling averages
        AVG(hrv_ms) OVER w30 as hrv_30d_avg,
        AVG(rhr_bpm) OVER w30 as rhr_30d_avg,
        AVG(sleep_min) OVER w30 as sleep_30d_avg,
        COUNT(hrv_ms) OVER w30 as hrv_30d_count,
        COUNT(rhr_bpm) OVER w30 as rhr_30d_count,
        COUNT(sleep_min) OVER w30 as sleep_30d_count,
        
        -- 90-day rolling averages
        AVG(hrv_ms) OVER w90 as hrv_90d_avg,
        AVG(rhr_bpm) OVER w90 as rhr_90d_avg,
        AVG(sleep_min) OVER w90 as sleep_90d_avg,
        COUNT(hrv_ms) OVER w90 as hrv_90d_count,
        
        -- Previous period for trend calculation (7d ago)
        LAG(hrv_ms, 7) OVER (ORDER BY reading_date) as hrv_prev_week,
        LAG(rhr_bpm, 7) OVER (ORDER BY reading_date) as rhr_prev_week,
        LAG(sleep_min, 7) OVER (ORDER BY reading_date) as sleep_prev_week
        
    FROM daily_metrics
    WINDOW 
        w7 AS (ORDER BY reading_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
        w30 AS (ORDER BY reading_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW),
        w90 AS (ORDER BY reading_date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW)
)
SELECT 
    reading_date,
    hrv_ms,
    rhr_bpm,
    sleep_min,
    ROUND((sleep_min / 60.0)::numeric, 1) as sleep_hours,
    deep_min,
    rem_min,
    CASE WHEN sleep_min > 0 
        THEN ROUND((100.0 * (COALESCE(deep_min, 0) + COALESCE(rem_min, 0)) / sleep_min)::numeric, 1)
        ELSE NULL 
    END as restorative_pct,
    recovery_score,
    sleep_score,
    
    -- Rolling averages
    ROUND(hrv_7d_avg::numeric, 1) as hrv_7d_avg,
    ROUND(hrv_30d_avg::numeric, 1) as hrv_30d_avg,
    ROUND(hrv_90d_avg::numeric, 1) as hrv_90d_avg,
    ROUND(rhr_7d_avg::numeric, 1) as rhr_7d_avg,
    ROUND(rhr_30d_avg::numeric, 1) as rhr_30d_avg,
    ROUND(rhr_90d_avg::numeric, 1) as rhr_90d_avg,
    ROUND((sleep_7d_avg / 60.0)::numeric, 2) as sleep_7d_hours,
    ROUND((sleep_30d_avg / 60.0)::numeric, 2) as sleep_30d_hours,
    
    -- Trend indicators: positive = improving (HRV up, RHR down)
    CASE 
        WHEN hrv_ms IS NOT NULL AND hrv_prev_week IS NOT NULL 
        THEN ROUND(((hrv_ms - hrv_prev_week) / NULLIF(hrv_prev_week, 0) * 100)::numeric, 1)
        ELSE NULL 
    END as hrv_trend_pct,
    
    CASE 
        WHEN rhr_bpm IS NOT NULL AND rhr_prev_week IS NOT NULL 
        THEN ROUND(((rhr_prev_week - rhr_bpm) / NULLIF(rhr_prev_week, 0) * 100)::numeric, 1)  -- Inverted: lower is better
        ELSE NULL 
    END as rhr_trend_pct,
    
    -- Data fitness: how complete is our data?
    hrv_7d_count,
    hrv_30d_count,
    hrv_90d_count,
    ROUND((hrv_7d_count / 7.0 * 100)::numeric, 0) as hrv_7d_completeness,
    ROUND((hrv_30d_count / 30.0 * 100)::numeric, 0) as hrv_30d_completeness
    
FROM with_rolling
ORDER BY reading_date;

CREATE INDEX idx_biometric_trends_date ON biometric_trends(reading_date);


-- ============================================================================
-- VIEW 2: training_trends  
-- Week-over-week training load comparisons
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS training_trends CASCADE;

CREATE MATERIALIZED VIEW training_trends AS
WITH weekly_summary AS (
    SELECT 
        DATE_TRUNC('week', workout_date)::date as week_start,
        COUNT(*) as workouts,
        SUM(total_volume_lbs) as volume_lbs,
        SUM(set_count) as total_sets
    FROM workout_summaries
    GROUP BY DATE_TRUNC('week', workout_date)
),
with_comparisons AS (
    SELECT 
        week_start,
        workouts,
        volume_lbs,
        total_sets,
        LAG(workouts) OVER w as prev_week_workouts,
        LAG(volume_lbs) OVER w as prev_week_volume,
        LAG(total_sets) OVER w as prev_week_sets,
        -- 4-week rolling average
        AVG(volume_lbs) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) as volume_4wk_avg,
        AVG(workouts) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) as workouts_4wk_avg
    FROM weekly_summary
    WINDOW w AS (ORDER BY week_start)
)
SELECT 
    week_start,
    workouts,
    volume_lbs,
    total_sets,
    prev_week_workouts,
    prev_week_volume,
    ROUND(volume_4wk_avg::numeric, 0) as volume_4wk_avg,
    ROUND(workouts_4wk_avg::numeric, 1) as workouts_4wk_avg,
    
    -- Week-over-week change
    CASE 
        WHEN prev_week_volume IS NOT NULL AND prev_week_volume > 0
        THEN ROUND(((volume_lbs - prev_week_volume) / prev_week_volume * 100)::numeric, 1)
        ELSE NULL 
    END as volume_wow_pct,
    
    CASE 
        WHEN prev_week_workouts IS NOT NULL AND prev_week_workouts > 0
        THEN ROUND(((workouts - prev_week_workouts)::numeric / prev_week_workouts * 100)::numeric, 1)
        ELSE NULL 
    END as workouts_wow_pct
    
FROM with_comparisons
ORDER BY week_start;

CREATE INDEX idx_training_trends_week ON training_trends(week_start);


-- ============================================================================
-- VIEW 3: coach_brief_snapshot
-- Single-row view optimized for coach brief generation
-- Consolidates key metrics for "right now" without heavy queries
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS coach_brief_snapshot CASCADE;

CREATE MATERIALIZED VIEW coach_brief_snapshot AS
WITH latest_biometrics AS (
    SELECT * FROM biometric_trends 
    WHERE reading_date = (SELECT MAX(reading_date) FROM biometric_trends WHERE hrv_ms IS NOT NULL)
),
latest_training AS (
    SELECT * FROM training_load_daily
    WHERE workout_date = (SELECT MAX(workout_date) FROM training_load_daily)
),
recent_workout_count AS (
    SELECT COUNT(*) as workouts_7d
    FROM workout_summaries
    WHERE workout_date >= CURRENT_DATE - INTERVAL '7 days'
),
data_freshness AS (
    SELECT 
        MAX(reading_date) FILTER (WHERE metric_type = 'hrv_morning') as last_hrv_date,
        MAX(reading_date) FILTER (WHERE metric_type = 'sleep_total_min') as last_sleep_date,
        MAX(reading_date) FILTER (WHERE metric_type = 'resting_hr') as last_rhr_date
    FROM biometric_readings
    WHERE LOWER(source) = 'ultrahuman'
)
SELECT 
    CURRENT_DATE as report_date,
    
    -- Today's metrics
    b.hrv_ms as today_hrv,
    b.rhr_bpm as today_rhr,
    b.sleep_hours as today_sleep_hours,
    b.restorative_pct as today_restorative_pct,
    b.recovery_score as today_recovery,
    
    -- Trend context
    b.hrv_7d_avg,
    b.hrv_30d_avg,
    b.hrv_90d_avg,
    b.hrv_trend_pct,
    b.rhr_7d_avg,
    b.rhr_trend_pct,
    
    -- Training load
    t.acwr,
    t.acute_7d as load_acute,
    t.chronic_28d as load_chronic,
    r.workouts_7d,
    
    -- Data fitness
    b.hrv_7d_completeness,
    b.hrv_30d_completeness,
    f.last_hrv_date,
    f.last_sleep_date,
    f.last_rhr_date,
    CURRENT_DATE - f.last_hrv_date as days_since_hrv,
    CURRENT_DATE - f.last_sleep_date as days_since_sleep
    
FROM latest_biometrics b
CROSS JOIN latest_training t  
CROSS JOIN recent_workout_count r
CROSS JOIN data_freshness f;


-- ============================================================================
-- REFRESH FUNCTION
-- Call after sync pipeline runs
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_coach_brief_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW biometric_trends;
    REFRESH MATERIALIZED VIEW training_trends;
    REFRESH MATERIALIZED VIEW coach_brief_snapshot;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT SELECT ON biometric_trends TO PUBLIC;
GRANT SELECT ON training_trends TO PUBLIC;
GRANT SELECT ON coach_brief_snapshot TO PUBLIC;
