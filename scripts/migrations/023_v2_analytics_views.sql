-- =================================================================
-- MIGRATION 023: Update Analytics Views to Use V2 Schema
-- =================================================================
-- Purpose: Update training load views to query V2 schema tables
--          instead of legacy strength_sessions/strength_sets.
--
-- Context: V2 schema (workouts_v2, segments, v2_strength_sets) is now
--          the source of truth for strength workouts since Jan 11, 2026.
--          The v2_completion_migration.sql backfilled set_category to
--          maintain semantic parity with legacy.
--
-- Affected views:
--   - training_load_daily: ACWR calculations from volume
--   - coach_brief_snapshot: Recent workout count
--   - srpe_training_load: Session RPE load
--   - srpe_monotony_strain: Foster monotony/strain
--
-- Related: GitHub Issue #40, v2_completion_migration.sql
-- Date: 2026-01-19
-- =================================================================

BEGIN;

-- =================================================================
-- 1. Update training_load_daily to use V2
-- =================================================================
-- Original: Queried strength_sessions.session_date, total_sets, total_volume_lbs
-- New: Query workouts_v2 joined with segments and v2_strength_sets

DROP VIEW IF EXISTS training_load_daily CASCADE;

CREATE VIEW training_load_daily AS
WITH daily_load AS (
    SELECT
        (w.start_time AT TIME ZONE COALESCE(w.timezone, 'America/Los_Angeles'))::date AS workout_date,
        COUNT(s.set_id) AS daily_sets,
        COALESCE(SUM(
            CASE WHEN s.load_unit = 'kg'
                 THEN s.load * 2.20462 * COALESCE(s.reps, 0)
                 ELSE COALESCE(s.load, 0) * COALESCE(s.reps, 0)
            END
        ), 0) AS daily_volume,
        COUNT(DISTINCT w.workout_id) AS workout_count
    FROM workouts_v2 w
    JOIN segments seg ON w.workout_id = seg.workout_id
    JOIN v2_strength_sets s ON seg.segment_id = s.segment_id
    WHERE seg.sport_type = 'strength'
    GROUP BY (w.start_time AT TIME ZONE COALESCE(w.timezone, 'America/Los_Angeles'))::date
),
date_series AS (
    SELECT generate_series(
        (SELECT MIN(workout_date) FROM daily_load),
        CURRENT_DATE,
        '1 day'::interval
    )::date AS dt
),
filled AS (
    SELECT
        ds.dt AS workout_date,
        COALESCE(dl.daily_sets, 0) AS daily_sets,
        COALESCE(dl.daily_volume, 0) AS daily_volume,
        COALESCE(dl.workout_count, 0) AS workout_count
    FROM date_series ds
    LEFT JOIN daily_load dl ON dl.workout_date = ds.dt
)
SELECT
    workout_date,
    daily_sets,
    daily_volume,
    workout_count,
    SUM(daily_volume) OVER (ORDER BY workout_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS acute_7d,
    ROUND(AVG(daily_volume) OVER (ORDER BY workout_date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) * 7, 0) AS chronic_28d,
    ROUND(
        SUM(daily_volume) OVER (ORDER BY workout_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) /
        NULLIF(AVG(daily_volume) OVER (ORDER BY workout_date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) * 7, 0)
    , 2) AS acwr
FROM filled
WHERE workout_date >= (SELECT MIN(workout_date) + 27 FROM daily_load)
ORDER BY workout_date DESC;

COMMENT ON VIEW training_load_daily IS
'Daily training load from V2 schema. Volume ACWR for injury risk assessment.
Source: workouts_v2 -> segments -> v2_strength_sets (migration 023).';


-- =================================================================
-- 2. Recreate views that depend on training_load_daily
-- =================================================================

-- training_monotony_strain depends on training_load_daily
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
        AVG(daily_volume) OVER w7 as avg_volume_7d,
        STDDEV_SAMP(daily_volume) OVER w7 as stddev_volume_7d,
        COUNT(*) OVER w7 as days_in_window,
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
    CASE
        WHEN days_in_window >= 7 AND stddev_volume_7d > 0
        THEN ROUND((avg_volume_7d / stddev_volume_7d)::numeric, 2)
        ELSE NULL
    END as monotony,
    CASE
        WHEN days_in_window < 7 OR stddev_volume_7d IS NULL OR stddev_volume_7d = 0 THEN 'insufficient_data'
        WHEN (avg_volume_7d / stddev_volume_7d) > 2.0 THEN 'high'
        WHEN (avg_volume_7d / stddev_volume_7d) > 1.5 THEN 'moderate'
        ELSE 'good'
    END as monotony_zone,
    CASE
        WHEN days_in_window >= 7 AND stddev_volume_7d > 0
        THEN ROUND((weekly_volume * (avg_volume_7d / stddev_volume_7d))::numeric, 0)
        ELSE NULL
    END as strain,
    CASE
        WHEN days_in_window < 7 OR stddev_volume_7d IS NULL OR stddev_volume_7d = 0 THEN 'insufficient_data'
        WHEN (weekly_volume * (avg_volume_7d / NULLIF(stddev_volume_7d, 0))) > 6000 THEN 'high'
        WHEN (weekly_volume * (avg_volume_7d / NULLIF(stddev_volume_7d, 0))) > 3000 THEN 'moderate'
        ELSE 'low'
    END as strain_zone,
    ROUND(avg_volume_7d::numeric, 0) as avg_volume_7d,
    ROUND(stddev_volume_7d::numeric, 0) as stddev_volume_7d,
    ROUND(weekly_volume::numeric, 0) as weekly_volume
FROM daily_with_stats
ORDER BY workout_date DESC;

COMMENT ON VIEW training_monotony_strain IS
'Training load with Monotony and Strain metrics (Foster 1998). Updated for V2 schema.';


-- =================================================================
-- 3. Update srpe_training_load to use V2
-- =================================================================
-- This view calculates Session RPE load per Foster (1998)

DROP VIEW IF EXISTS srpe_training_load CASCADE;

CREATE VIEW srpe_training_load AS
WITH session_data AS (
    SELECT
        (w.start_time AT TIME ZONE COALESCE(w.timezone, 'America/Los_Angeles'))::date AS session_date,
        COALESCE(
            -- Try to get workout name from notes or source
            NULLIF(w.notes, ''),
            w.source,
            'Strength Session'
        ) AS name,
        COALESCE(SUM(
            CASE WHEN s.load_unit = 'kg'
                 THEN s.load * 2.20462 * COALESCE(s.reps, 0)
                 ELSE COALESCE(s.load, 0) * COALESCE(s.reps, 0)
            END
        ), 0) AS total_volume_lbs,
        -- Duration cascade: V2 duration -> Polar actual -> default 45
        COALESCE(
            w.duration_seconds / 60,
            (SELECT ps.duration_seconds / 60
             FROM polar_sessions ps
             WHERE DATE(ps.start_time) = (w.start_time AT TIME ZONE COALESCE(w.timezone, 'America/Los_Angeles'))::date
             LIMIT 1),
            45
        )::INT as duration_minutes,
        -- RPE cascade: session_rpe -> avg set RPE -> type-based default
        COALESCE(
            w.rpe,
            AVG(s.rpe),
            6  -- Default RPE for strength work
        )::NUMERIC as session_rpe,
        CASE
            WHEN w.rpe IS NOT NULL THEN 'user_provided'
            WHEN AVG(s.rpe) IS NOT NULL THEN 'set_average'
            ELSE 'imputed'
        END as rpe_source,
        CASE
            WHEN w.duration_seconds IS NOT NULL THEN 'v2_logged'
            WHEN EXISTS (SELECT 1 FROM polar_sessions ps
                        WHERE DATE(ps.start_time) = (w.start_time AT TIME ZONE COALESCE(w.timezone, 'America/Los_Angeles'))::date)
            THEN 'polar_actual'
            ELSE 'default_45'
        END as duration_source
    FROM workouts_v2 w
    JOIN segments seg ON w.workout_id = seg.workout_id
    JOIN v2_strength_sets s ON seg.segment_id = s.segment_id
    WHERE seg.sport_type = 'strength'
    GROUP BY w.workout_id, w.start_time, w.timezone, w.notes, w.source, w.duration_seconds, w.rpe
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
'Session RPE load per Foster (1998). Updated for V2 schema. sRPE Load = RPE x Duration.';


-- =================================================================
-- 4. Recreate srpe_monotony_strain (depends on srpe_training_load)
-- =================================================================

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
'Foster (1998) Monotony and Strain using session RPE x duration. Updated for V2 schema.';


-- =================================================================
-- 5. Recreate readiness_composite (depends on training_monotony_strain)
-- =================================================================

DROP VIEW IF EXISTS readiness_composite CASCADE;

CREATE VIEW readiness_composite AS
WITH combined AS (
    SELECT
        COALESCE(b.reading_date, t.workout_date) as date,
        b.hrv_ms,
        b.hrv_cv_7d,
        b.hrv_cv_zone,
        b.sleep_hours,
        b.sleep_debt_hours_7d,
        b.sleep_debt_zone,
        b.rhr_bpm,
        t.acwr,
        t.monotony,
        t.monotony_zone,
        t.strain,
        t.strain_zone,
        bt.hrv_30d_avg,
        bt.hrv_7d_avg AS hrv_recent_avg
    FROM biometric_derived b
    FULL OUTER JOIN training_monotony_strain t ON b.reading_date = t.workout_date
    LEFT JOIN biometric_trends bt ON b.reading_date = bt.reading_date
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
    CASE
        WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL AND hrv_30d_avg > 0
        THEN ROUND(((hrv_ms - hrv_30d_avg) / hrv_30d_avg * 100)::numeric, 0)
        ELSE NULL
    END as hrv_vs_baseline_pct,
    (
        CASE WHEN hrv_cv_zone = 'suppressed' THEN 1 ELSE 0 END +
        CASE WHEN sleep_debt_zone IN ('significant', 'critical') THEN 1 ELSE 0 END +
        CASE WHEN strain_zone = 'high' THEN 1 ELSE 0 END +
        CASE WHEN acwr > 1.5 THEN 1 ELSE 0 END +
        CASE WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL
             AND ((hrv_ms - hrv_30d_avg) / NULLIF(hrv_30d_avg, 0) * 100) < -20 THEN 1 ELSE 0 END
    ) as red_flag_count,
    CASE
        WHEN hrv_cv_zone = 'suppressed' THEN 'recover'
        WHEN sleep_debt_zone = 'critical' THEN 'recover'
        WHEN strain_zone = 'high' THEN 'recover'
        WHEN acwr > 1.5 THEN 'recover'
        WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL
             AND ((hrv_ms - hrv_30d_avg) / NULLIF(hrv_30d_avg, 0) * 100) < -20 THEN 'recover'
        WHEN sleep_debt_zone = 'significant' THEN 'caution'
        WHEN monotony_zone = 'high' THEN 'caution'
        WHEN acwr > 1.3 THEN 'caution'
        WHEN hrv_ms IS NOT NULL AND hrv_30d_avg IS NOT NULL
             AND ((hrv_ms - hrv_30d_avg) / NULLIF(hrv_30d_avg, 0) * 100) < -10 THEN 'caution'
        ELSE 'ready'
    END as readiness_status
FROM combined
WHERE date IS NOT NULL
ORDER BY date DESC;

COMMENT ON VIEW readiness_composite IS
'Combined readiness assessment from biometric and training metrics. Updated for V2 schema.';


-- =================================================================
-- 6. Refresh materialized view that depends on training_load_daily
-- =================================================================

-- coach_brief_snapshot uses readiness_composite
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
    -- Updated to use V2 schema
    SELECT COUNT(DISTINCT w.workout_id) as workouts_7d
    FROM workouts_v2 w
    JOIN segments seg ON w.workout_id = seg.workout_id
    WHERE seg.sport_type = 'strength'
      AND w.start_time >= CURRENT_DATE - INTERVAL '7 days'
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
    r.readiness_status,
    r.red_flag_count,
    b.hrv_ms as today_hrv,
    b.rhr_bpm as today_rhr,
    b.sleep_hours as today_sleep_hours,
    b.hrv_cv_7d,
    b.hrv_cv_zone,
    b.sleep_debt_hours_7d,
    b.sleep_debt_zone,
    t.acwr,
    t.monotony,
    t.monotony_zone,
    t.strain,
    t.strain_zone,
    r.hrv_vs_baseline_pct,
    r.hrv_30d_avg as hrv_baseline,
    wc.workouts_7d,
    f.last_hrv_date,
    f.last_sleep_date,
    CURRENT_DATE - f.last_hrv_date as days_since_hrv,
    CURRENT_DATE - f.last_sleep_date as days_since_sleep
FROM latest_readiness r
CROSS JOIN latest_training t
CROSS JOIN latest_biometric b
CROSS JOIN recent_workout_count wc
CROSS JOIN data_freshness f;

CREATE INDEX idx_coach_brief_date ON coach_brief_snapshot(report_date);


-- =================================================================
-- 7. Validation
-- =================================================================

DO $$
DECLARE
    v2_workout_count INTEGER;
    view_workout_count INTEGER;
BEGIN
    -- Count V2 workouts
    SELECT COUNT(DISTINCT w.workout_id) INTO v2_workout_count
    FROM workouts_v2 w
    JOIN segments seg ON w.workout_id = seg.workout_id
    WHERE seg.sport_type = 'strength';

    -- Count from training_load_daily
    SELECT COUNT(*) INTO view_workout_count
    FROM training_load_daily
    WHERE workout_count > 0;

    RAISE NOTICE '=== MIGRATION 023 VALIDATION ===';
    RAISE NOTICE 'V2 strength workouts: %', v2_workout_count;
    RAISE NOTICE 'Days with workouts in view: %', view_workout_count;
    RAISE NOTICE '=== MIGRATION SUCCESSFUL ===';
END $$;

-- Show recent data to verify
SELECT workout_date, daily_sets, daily_volume, workout_count, acwr
FROM training_load_daily
ORDER BY workout_date DESC
LIMIT 10;

COMMIT;
