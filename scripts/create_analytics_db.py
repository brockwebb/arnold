#!/usr/bin/env python3
"""
Create arnold_analytics.duckdb from staged Parquet files.
Builds unified views for coaching analytics.
"""

import duckdb
from pathlib import Path

# Paths
STAGING_DIR = Path(__file__).parent.parent / "data" / "staging"
DB_PATH = Path(__file__).parent.parent / "data" / "arnold_analytics.duckdb"

def main():
    # Remove existing DB for clean rebuild
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing {DB_PATH.name}")
    
    conn = duckdb.connect(str(DB_PATH))
    
    # =========================================================================
    # LOAD ALL PARQUET FILES AS TABLES
    # =========================================================================
    
    parquet_files = list(STAGING_DIR.glob("*.parquet"))
    print(f"\nLoading {len(parquet_files)} Parquet files...")
    
    for pq_file in sorted(parquet_files):
        table_name = pq_file.stem  # filename without extension
        conn.execute(f"""
            CREATE TABLE {table_name} AS 
            SELECT * FROM read_parquet('{pq_file}')
        """)
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"  {table_name}: {row_count:,} rows")
    
    # =========================================================================
    # UNIFIED DAILY VIEW
    # Joins biometrics + training for daily coaching context
    # =========================================================================
    
    print("\nCreating unified views...")
    
    conn.execute("""
        CREATE VIEW daily_metrics AS
        WITH date_spine AS (
            -- All dates we have any data for, normalized to DATE
            SELECT DISTINCT CAST(date AS DATE) as date FROM ultrahuman_daily
            UNION
            SELECT DISTINCT CAST(date AS DATE) FROM workouts
            UNION
            SELECT DISTINCT CAST(date AS DATE) FROM apple_health_hrv
            UNION
            SELECT DISTINCT CAST(date AS DATE) FROM apple_health_sleep
            UNION
            SELECT DISTINCT CAST(date AS DATE) FROM apple_health_resting_hr
        ),
        -- Apple Health as primary biometrics source
        hrv_daily AS (
            SELECT 
                CAST(date AS DATE) as date,
                AVG(hrv_ms) as hrv_avg,
                MIN(hrv_ms) as hrv_min,
                MAX(hrv_ms) as hrv_max,
                STDDEV(hrv_ms) as hrv_stddev,
                COUNT(*) as hrv_samples
            FROM apple_health_hrv
            GROUP BY CAST(date AS DATE)
        ),
        rhr_daily AS (
            SELECT 
                CAST(date AS DATE) as date,
                AVG(resting_hr) as resting_hr,
                COUNT(*) as rhr_samples
            FROM apple_health_resting_hr
            GROUP BY CAST(date AS DATE)
        ),
        sleep_daily AS (
            SELECT
                CAST(date AS DATE) as date,
                SUM(duration_minutes) as sleep_min,
                SUM(CASE WHEN sleep_stage IN ('asleepdeep') THEN duration_minutes ELSE 0 END) as deep_min,
                SUM(CASE WHEN sleep_stage IN ('asleeprem') THEN duration_minutes ELSE 0 END) as rem_min,
                SUM(CASE WHEN sleep_stage IN ('asleepcore', 'asleep') THEN duration_minutes ELSE 0 END) as light_min,
                SUM(CASE WHEN sleep_stage = 'awake' THEN duration_minutes ELSE 0 END) as awake_min
            FROM apple_health_sleep
            GROUP BY CAST(date AS DATE)
        ),
        training_daily AS (
            SELECT 
                CAST(w.date AS DATE) as date,
                COUNT(DISTINCT w.workout_id) as workout_count,
                STRING_AGG(DISTINCT w.type, ', ') as workout_types,
                SUM(s.reps) as total_reps,
                COUNT(s.set_id) as total_sets,
                MAX(s.load_lbs) as max_load_lbs,
                AVG(s.rpe) as avg_rpe,
                SUM(s.load_lbs * s.reps) as volume_lbs
            FROM workouts w
            LEFT JOIN sets s ON w.workout_id = s.workout_id
            GROUP BY CAST(w.date AS DATE)
        ),
        -- Ultrahuman only for computed scores (not available in Apple Health)
        ultrahuman_scores AS (
            SELECT
                CAST(date AS DATE) as date,
                sleep_score,
                recovery_score,
                movement_score,
                sleep_efficiency
            FROM ultrahuman_daily
        )
        SELECT 
            d.date,
            
            -- PRIMARY: Apple Health biometrics
            h.hrv_avg,
            h.hrv_min,
            h.hrv_max,
            h.hrv_stddev,
            h.hrv_samples,
            r.resting_hr,
            
            -- PRIMARY: Apple Health sleep
            sl.sleep_min,
            sl.deep_min,
            sl.rem_min,
            sl.light_min,
            sl.awake_min,
            CASE WHEN sl.sleep_min > 0 
                 THEN ROUND(100.0 * (sl.sleep_min - sl.awake_min) / sl.sleep_min, 1)
                 ELSE NULL END as sleep_efficiency_calc,
            
            -- SECONDARY: Ultrahuman computed scores (proprietary algorithms)
            u.sleep_score,
            u.recovery_score,
            u.movement_score,
            u.sleep_efficiency as ultrahuman_efficiency,
            
            -- Training
            t.workout_count,
            t.workout_types,
            t.total_sets,
            t.total_reps,
            t.max_load_lbs,
            t.volume_lbs,
            t.avg_rpe,
            
            -- DATA AVAILABILITY FLAGS
            CASE WHEN h.hrv_samples IS NOT NULL THEN TRUE ELSE FALSE END as has_hrv,
            CASE WHEN sl.sleep_min IS NOT NULL THEN TRUE ELSE FALSE END as has_sleep,
            CASE WHEN u.recovery_score IS NOT NULL THEN TRUE ELSE FALSE END as has_ultrahuman,
            CASE WHEN t.workout_count IS NOT NULL THEN TRUE ELSE FALSE END as has_training,
            
            -- Data quality indicator (0-4 sources present)
            (CASE WHEN h.hrv_samples IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sl.sleep_min IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN u.recovery_score IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN t.workout_count IS NOT NULL THEN 1 ELSE 0 END) as data_completeness
            
        FROM date_spine d
        LEFT JOIN hrv_daily h ON d.date = h.date
        LEFT JOIN rhr_daily r ON d.date = r.date
        LEFT JOIN sleep_daily sl ON d.date = sl.date
        LEFT JOIN ultrahuman_scores u ON d.date = u.date
        LEFT JOIN training_daily t ON d.date = t.date
        ORDER BY d.date DESC
    """)
    print("  daily_metrics: unified daily view (Apple primary, Ultrahuman scores)")
    
    # =========================================================================
    # WEEKLY TRAINING SUMMARY
    # =========================================================================
    
    conn.execute("""
        CREATE VIEW weekly_training AS
        SELECT 
            DATE_TRUNC('week', CAST(w.date AS DATE)) as week_start,
            COUNT(DISTINCT w.workout_id) as workouts,
            COUNT(s.set_id) as total_sets,
            SUM(s.reps) as total_reps,
            SUM(s.load_lbs * s.reps) as total_volume_lbs,
            AVG(s.rpe) as avg_rpe,
            COUNT(DISTINCT s.exercise_name) as unique_exercises
        FROM workouts w
        JOIN sets s ON w.workout_id = s.workout_id
        GROUP BY DATE_TRUNC('week', CAST(w.date AS DATE))
        ORDER BY week_start DESC
    """)
    print("  weekly_training: weekly volume summary")
    
    # =========================================================================
    # EXERCISE PROGRESSION VIEW
    # Track PRs and progression per exercise
    # =========================================================================
    
    conn.execute("""
        CREATE VIEW exercise_progression AS
        SELECT 
            s.exercise_name,
            CAST(s.date AS DATE) as date,
            MAX(s.load_lbs) as max_load,
            MAX(s.reps) as max_reps,
            MAX(s.load_lbs * s.reps) as max_volume,
            COUNT(*) as sets_performed,
            AVG(s.rpe) as avg_rpe
        FROM sets s
        WHERE s.load_lbs IS NOT NULL
        GROUP BY s.exercise_name, CAST(s.date AS DATE)
        ORDER BY s.exercise_name, date
    """)
    print("  exercise_progression: per-exercise tracking")
    
    # =========================================================================
    # HRV-TRAINING CORRELATION VIEW
    # For analyzing recovery vs performance
    # =========================================================================
    
    conn.execute("""
        CREATE VIEW hrv_training_correlation AS
        SELECT 
            dm.date,
            dm.hrv_avg,
            dm.resting_hr,
            dm.recovery_score,
            dm.sleep_score,
            dm.sleep_min,
            dm.workout_types,
            dm.total_sets,
            dm.volume_lbs,
            dm.avg_rpe,
            dm.data_completeness,
            -- Previous day metrics for lag analysis
            LAG(dm.hrv_avg) OVER (ORDER BY dm.date) as prev_day_hrv,
            LAG(dm.recovery_score) OVER (ORDER BY dm.date) as prev_day_recovery,
            LAG(dm.total_sets) OVER (ORDER BY dm.date) as prev_day_sets,
            LAG(dm.volume_lbs) OVER (ORDER BY dm.date) as prev_day_volume,
            -- 7-day rolling averages
            AVG(dm.hrv_avg) OVER (ORDER BY dm.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as hrv_7d_avg,
            AVG(dm.sleep_min) OVER (ORDER BY dm.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as sleep_7d_avg
        FROM daily_metrics dm
        WHERE dm.has_hrv OR dm.has_training
        ORDER BY dm.date
    """)
    print("  hrv_training_correlation: recovery analysis (with rolling averages)")
    
    # =========================================================================
    # MOVEMENT PATTERN VOLUME
    # Track volume by movement pattern over time
    # =========================================================================
    
    conn.execute("""
        CREATE VIEW pattern_volume AS
        WITH unnested AS (
            SELECT 
                DATE_TRUNC('week', CAST(s.date AS DATE)) as week_start,
                TRIM(UNNEST(STRING_SPLIT(s.patterns, ','))) as pattern,
                s.reps,
                s.load_lbs
            FROM sets s
            WHERE s.patterns IS NOT NULL AND s.patterns != ''
        )
        SELECT 
            week_start,
            pattern,
            COUNT(*) as sets,
            SUM(reps) as reps,
            SUM(load_lbs * reps) as volume_lbs
        FROM unnested
        WHERE pattern != ''
        GROUP BY week_start, pattern
        ORDER BY week_start DESC, pattern
    """)
    print("  pattern_volume: movement pattern tracking")
    
    # =========================================================================
    # LAB TRENDS VIEW
    # For biomarker analysis
    # =========================================================================
    
    conn.execute("""
        CREATE VIEW lab_trends AS
        SELECT 
            test_name,
            loinc_code,
            date,
            value,
            unit,
            ref_range_low,
            ref_range_high,
            CASE 
                WHEN ref_range_low IS NOT NULL AND value < ref_range_low THEN 'low'
                WHEN ref_range_high IS NOT NULL AND value > ref_range_high THEN 'high'
                ELSE 'normal'
            END as status
        FROM clinical_labs
        WHERE value IS NOT NULL
        ORDER BY test_name, date
    """)
    print("  lab_trends: biomarker tracking")
    
    # =========================================================================
    # RACE PERFORMANCE VIEW
    # =========================================================================
    
    conn.execute("""
        CREATE VIEW race_performance AS
        SELECT 
            event_date,
            event_name,
            distance_label,
            distance_miles,
            finish_time,
            finish_seconds,
            finish_seconds / 60.0 / distance_miles as pace_min_per_mile,
            overall_place,
            overall_field,
            ROUND(100.0 * (overall_field - overall_place) / overall_field, 1) as percentile,
            age_at_race,
            sport,
            race_type
        FROM race_history
        WHERE finish_seconds IS NOT NULL
        ORDER BY event_date DESC
    """)
    print("  race_performance: race analytics")
    
    # =========================================================================
    # SUMMARY STATS
    # =========================================================================
    
    print("\n" + "="*60)
    print("DATABASE CREATED SUCCESSFULLY")
    print("="*60)
    
    # Table counts
    tables = conn.execute("""
        SELECT table_name, 
               (SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = t.table_name) as columns
        FROM information_schema.tables t
        WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """).fetchall()
    
    print(f"\nTables: {len(tables)}")
    for name, cols in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name}: {count:,} rows, {cols} cols")
    
    # View counts
    views = conn.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'main' AND table_type = 'VIEW'
        ORDER BY table_name
    """).fetchall()
    
    print(f"\nViews: {len(views)}")
    for (name,) in views:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name}: {count:,} rows")
    
    # Date ranges
    print("\nDate Ranges:")
    ranges = conn.execute("""
        SELECT 'workouts' as source, MIN(date), MAX(date) FROM workouts
        UNION ALL
        SELECT 'ultrahuman', MIN(date), MAX(date) FROM ultrahuman_daily
        UNION ALL
        SELECT 'apple_hrv', MIN(date), MAX(date) FROM apple_health_hrv
        UNION ALL
        SELECT 'clinical_labs', MIN(date), MAX(date) FROM clinical_labs
        UNION ALL
        SELECT 'race_history', MIN(event_date), MAX(event_date) FROM race_history
    """).fetchall()
    
    for source, min_date, max_date in ranges:
        print(f"  {source}: {min_date} → {max_date}")
    
    conn.close()
    print(f"\nDatabase: {DB_PATH}")

if __name__ == "__main__":
    main()
