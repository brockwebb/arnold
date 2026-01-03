#!/usr/bin/env python3
"""
⚠️  DEPRECATED - DO NOT USE ⚠️
================================
This script diverged from the DATA_DICTIONARY.md spec and creates views
that don't match what arnold-analytics-mcp expects.

Use instead: scripts/create_analytics_db.py

This file is kept for reference only. Delete after confirming no dependencies.

---
Original description:
Creates DuckDB analytics database with Tier 1 training metrics.
Metrics implemented: Volume Load, ACWR, Monotony, Strain, etc.
References: docs/TRAINING_METRICS.md
"""

import duckdb
from pathlib import Path
import sys

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
STAGING_DIR = DATA_DIR / "staging"
DB_PATH = DATA_DIR / "arnold_analytics.duckdb"


def create_database():
    """Create DuckDB database and load staging data."""
    
    print(f"Creating database: {DB_PATH}")
    
    # Remove existing database
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("  Removed existing database")
    
    conn = duckdb.connect(str(DB_PATH))
    
    # Load staging tables
    staging_files = {
        "sets": STAGING_DIR / "sets.parquet",
        "workouts": STAGING_DIR / "workouts.parquet",
        "exercises": STAGING_DIR / "exercises.parquet",
        "movement_patterns": STAGING_DIR / "movement_patterns.parquet",
        "muscle_targeting": STAGING_DIR / "muscle_targeting.csv",
        "ultrahuman_daily": STAGING_DIR / "ultrahuman_daily.parquet",
        "apple_health_sleep": STAGING_DIR / "apple_health_sleep.parquet",
        "apple_health_hrv": STAGING_DIR / "apple_health_hrv.parquet",
        "apple_health_resting_hr": STAGING_DIR / "apple_health_resting_hr.parquet",
        "race_history": STAGING_DIR / "race_history.parquet",
    }
    
    for table_name, file_path in staging_files.items():
        if file_path.exists():
            if file_path.suffix == ".csv":
                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path}')")
            else:
                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{file_path}')")
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            print(f"  Loaded {table_name}: {count:,} rows")
        else:
            print(f"  SKIP {table_name}: file not found")
    
    return conn


def create_tier1_views(conn):
    """Create views for Tier 1 metrics (from logged workouts)."""
    
    print("\nCreating Tier 1 metric views...")
    
    # 1. Daily Volume Load
    conn.execute("""
        CREATE OR REPLACE VIEW daily_volume AS
        SELECT 
            date,
            COUNT(DISTINCT workout_id) as workout_count,
            COUNT(*) as total_sets,
            SUM(COALESCE(reps, 0)) as total_reps,
            SUM(COALESCE(reps, 1) * COALESCE(load_lbs, 0)) as volume_load,
            AVG(NULLIF(rpe, 0)) as avg_rpe
        FROM sets
        WHERE date IS NOT NULL
        GROUP BY date
        ORDER BY date
    """)
    print("  ✓ daily_volume")
    
    # 2. Weekly Volume Load
    conn.execute("""
        CREATE OR REPLACE VIEW weekly_volume AS
        SELECT 
            DATE_TRUNC('week', CAST(date AS DATE)) as week_start,
            YEARWEEK(CAST(date AS DATE)) as year_week,
            COUNT(DISTINCT workout_id) as workout_count,
            COUNT(*) as total_sets,
            SUM(COALESCE(reps, 0)) as total_reps,
            SUM(COALESCE(reps, 1) * COALESCE(load_lbs, 0)) as volume_load,
            AVG(NULLIF(rpe, 0)) as avg_rpe
        FROM sets
        WHERE date IS NOT NULL
        GROUP BY DATE_TRUNC('week', CAST(date AS DATE)), YEARWEEK(CAST(date AS DATE))
        ORDER BY week_start
    """)
    print("  ✓ weekly_volume")
    
    # 3. ACWR using Rolling Averages (simple, no nested window functions)
    conn.execute("""
        CREATE OR REPLACE VIEW acwr_daily AS
        WITH date_series AS (
            SELECT UNNEST(generate_series(
                (SELECT MIN(CAST(date AS DATE)) FROM sets),
                (SELECT MAX(CAST(date AS DATE)) FROM sets),
                INTERVAL 1 DAY
            ))::DATE as date
        ),
        daily_load AS (
            SELECT 
                ds.date,
                COALESCE(dv.volume_load, 0) as volume_load
            FROM date_series ds
            LEFT JOIN daily_volume dv ON ds.date = CAST(dv.date AS DATE)
        ),
        with_rolling AS (
            SELECT 
                date,
                volume_load,
                AVG(volume_load) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as acute_7d,
                AVG(volume_load) OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) as chronic_28d
            FROM daily_load
        )
        SELECT 
            date,
            volume_load,
            ROUND(acute_7d, 0) as acute_load_7d,
            ROUND(chronic_28d, 0) as chronic_load_28d,
            CASE WHEN chronic_28d > 0 THEN ROUND(acute_7d / chronic_28d, 2) ELSE NULL END as acwr,
            CASE 
                WHEN chronic_28d = 0 THEN 'insufficient_data'
                WHEN acute_7d / NULLIF(chronic_28d, 0) < 0.8 THEN 'undertrained'
                WHEN acute_7d / NULLIF(chronic_28d, 0) <= 1.3 THEN 'optimal'
                WHEN acute_7d / NULLIF(chronic_28d, 0) <= 1.5 THEN 'caution'
                ELSE 'danger'
            END as acwr_zone
        FROM with_rolling
        WHERE date >= (SELECT MIN(CAST(date AS DATE)) + INTERVAL 28 DAY FROM sets)
        ORDER BY date
    """)
    print("  ✓ acwr_daily")
    
    # 4. Training Monotony & Strain
    conn.execute("""
        CREATE OR REPLACE VIEW training_monotony AS
        WITH daily_load AS (
            SELECT 
                date,
                SUM(COALESCE(reps, 1) * COALESCE(load_lbs, 0)) as volume_load
            FROM sets
            WHERE date IS NOT NULL
            GROUP BY date
        ),
        rolling_stats AS (
            SELECT 
                date,
                volume_load,
                AVG(volume_load) OVER w as mean_7d,
                STDDEV(volume_load) OVER w as stddev_7d,
                SUM(volume_load) OVER w as sum_7d
            FROM daily_load
            WINDOW w AS (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
        )
        SELECT 
            date,
            volume_load,
            ROUND(mean_7d, 0) as mean_7d,
            ROUND(stddev_7d, 0) as stddev_7d,
            CASE WHEN stddev_7d > 0 THEN ROUND(mean_7d / stddev_7d, 2) ELSE NULL END as monotony,
            CASE WHEN stddev_7d > 0 THEN ROUND(sum_7d * (mean_7d / stddev_7d), 0) ELSE NULL END as strain,
            CASE 
                WHEN stddev_7d = 0 OR stddev_7d IS NULL THEN 'insufficient_variation'
                WHEN mean_7d / stddev_7d < 1.5 THEN 'good_variation'
                WHEN mean_7d / stddev_7d < 2.0 THEN 'moderate'
                ELSE 'high_monotony'
            END as monotony_status
        FROM rolling_stats
        ORDER BY date
    """)
    print("  ✓ training_monotony")
    
    # 5. Sets per Muscle Group per Week
    conn.execute("""
        CREATE OR REPLACE VIEW muscle_volume_weekly AS
        WITH set_muscles AS (
            SELECT 
                s.set_id,
                s.date,
                DATE_TRUNC('week', CAST(s.date AS DATE)) as week_start,
                s.reps,
                s.load_lbs,
                mt.muscle_name,
                mt.target_role,
                CASE 
                    WHEN mt.target_role = 'primary' THEN 1.0
                    WHEN mt.target_role = 'secondary' THEN 0.5
                    ELSE 0.25
                END as role_weight
            FROM sets s
            JOIN muscle_targeting mt ON s.exercise_id = mt.exercise_id
            WHERE s.date IS NOT NULL
        )
        SELECT 
            week_start,
            muscle_name,
            COUNT(DISTINCT set_id) as total_sets,
            SUM(CASE WHEN target_role = 'primary' THEN 1 ELSE 0 END) as primary_sets,
            SUM(CASE WHEN target_role = 'secondary' THEN 1 ELSE 0 END) as secondary_sets,
            ROUND(SUM(role_weight), 1) as weighted_sets,
            ROUND(SUM(COALESCE(reps, 1) * COALESCE(load_lbs, 0) * role_weight), 0) as weighted_volume,
            CASE 
                WHEN SUM(role_weight) < 4 THEN 'insufficient'
                WHEN SUM(role_weight) <= 10 THEN 'minimum'
                WHEN SUM(role_weight) <= 20 THEN 'optimal'
                ELSE 'high'
            END as volume_status
        FROM set_muscles
        GROUP BY week_start, muscle_name
        ORDER BY week_start DESC, weighted_volume DESC
    """)
    print("  ✓ muscle_volume_weekly")
    
    # 6. Movement Pattern Frequency (splits comma-separated patterns)
    conn.execute("""
        CREATE OR REPLACE VIEW pattern_frequency AS
        WITH split_patterns AS (
            SELECT 
                CAST(date AS DATE) as date,
                TRIM(UNNEST(STRING_SPLIT(patterns, ','))) as pattern
            FROM sets
            WHERE patterns IS NOT NULL AND patterns != ''
        ),
        pattern_dates AS (
            SELECT 
                pattern,
                MAX(date) as last_trained
            FROM split_patterns
            WHERE pattern != ''
            GROUP BY pattern
        ),
        latest_date AS (
            SELECT MAX(CAST(date AS DATE)) as max_date FROM sets
        )
        SELECT 
            pd.pattern,
            pd.last_trained,
            ld.max_date - pd.last_trained as days_since,
            CASE 
                WHEN ld.max_date - pd.last_trained <= 3 THEN 'recent'
                WHEN ld.max_date - pd.last_trained <= 7 THEN 'adequate'
                WHEN ld.max_date - pd.last_trained <= 14 THEN 'gap'
                ELSE 'neglected'
            END as frequency_status
        FROM pattern_dates pd
        CROSS JOIN latest_date ld
        ORDER BY days_since DESC
    """)
    print("  ✓ pattern_frequency")
    
    # 7. Exercise Progression (Estimated 1RM)
    conn.execute("""
        CREATE OR REPLACE VIEW exercise_progression AS
        WITH working_sets AS (
            SELECT 
                date,
                exercise_id,
                exercise_name,
                reps,
                load_lbs,
                CASE 
                    WHEN reps > 0 AND reps <= 10 AND load_lbs > 0
                    THEN ROUND(load_lbs * (36.0 / (37.0 - reps)), 1)
                    WHEN reps > 10 AND load_lbs > 0
                    THEN ROUND(load_lbs * (1 + reps / 30.0), 1)
                    ELSE NULL
                END as estimated_1rm
            FROM sets
            WHERE load_lbs > 0 AND reps > 0
        ),
        daily_best AS (
            SELECT 
                date,
                exercise_id,
                exercise_name,
                MAX(estimated_1rm) as best_e1rm,
                MAX(load_lbs) as max_load
            FROM working_sets
            GROUP BY date, exercise_id, exercise_name
        )
        SELECT 
            date,
            exercise_id,
            exercise_name,
            best_e1rm,
            max_load,
            MAX(best_e1rm) OVER (
                PARTITION BY exercise_id 
                ORDER BY date 
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) as running_pr,
            CASE 
                WHEN best_e1rm = MAX(best_e1rm) OVER (
                    PARTITION BY exercise_id 
                    ORDER BY date 
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) THEN true
                ELSE false
            END as is_pr
        FROM daily_best
        ORDER BY exercise_name, date
    """)
    print("  ✓ exercise_progression")
    
    # 8. Summary Dashboard View
    conn.execute("""
        CREATE OR REPLACE VIEW dashboard_current AS
        WITH latest AS (
            SELECT MAX(CAST(date AS DATE)) as latest_date FROM sets
        ),
        recent_acwr AS (
            SELECT acwr, acwr_zone 
            FROM acwr_daily 
            WHERE date = (SELECT latest_date FROM latest)
        ),
        recent_monotony AS (
            SELECT monotony, strain, monotony_status
            FROM training_monotony
            WHERE date = (SELECT latest_date FROM latest)
        ),
        week_volume AS (
            SELECT volume_load, workout_count, total_sets
            FROM weekly_volume
            WHERE week_start = DATE_TRUNC('week', (SELECT latest_date FROM latest))
        ),
        pattern_gaps AS (
            SELECT STRING_AGG(pattern, ', ') as neglected_patterns
            FROM pattern_frequency
            WHERE frequency_status IN ('gap', 'neglected')
        )
        SELECT 
            l.latest_date,
            wv.workout_count as workouts_this_week,
            wv.total_sets as sets_this_week,
            wv.volume_load as volume_this_week,
            a.acwr,
            a.acwr_zone,
            m.monotony,
            m.strain,
            m.monotony_status,
            pg.neglected_patterns
        FROM latest l
        LEFT JOIN recent_acwr a ON 1=1
        LEFT JOIN recent_monotony m ON 1=1
        LEFT JOIN week_volume wv ON 1=1
        LEFT JOIN pattern_gaps pg ON 1=1
    """)
    print("  ✓ dashboard_current")
    
    return conn


def create_tier2_views(conn):
    """Create views for Tier 2 metrics (require biometric data)."""
    
    print("\nCreating Tier 2 metric views...")
    
    # Check if we have ultrahuman data
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    
    if 'ultrahuman_daily' in table_names:
        conn.execute("""
            CREATE OR REPLACE VIEW readiness_daily AS
            SELECT 
                date,
                recovery_score,
                sleep_score,
                hrv_ms,
                resting_hr as rhr_bpm,
                ROUND(sleep_minutes / 60.0, 2) as sleep_hours,
                CASE 
                    WHEN recovery_score >= 70 AND sleep_minutes >= 390 THEN 'ready'
                    WHEN recovery_score >= 50 OR sleep_minutes >= 330 THEN 'caution'
                    ELSE 'recover'
                END as readiness_status,
                AVG(hrv_ms) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as hrv_7d_avg,
                AVG(resting_hr) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as rhr_7d_avg
            FROM ultrahuman_daily
            WHERE date IS NOT NULL
            ORDER BY date
        """)
        print("  ✓ readiness_daily (from Ultrahuman)")
    else:
        print("  ⚠ readiness_daily skipped (no ultrahuman_daily table)")
    
    return conn


def create_unified_views(conn):
    """Create unified views for MCP server queries."""
    
    print("\nCreating unified views for MCP...")
    
    # Check available tables
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    
    has_ultrahuman = 'ultrahuman_daily' in table_names
    has_apple_sleep = 'apple_health_sleep' in table_names
    has_apple_hrv = 'apple_health_hrv' in table_names
    has_apple_rhr = 'apple_health_resting_hr' in table_names
    
    # 1. daily_metrics - unified view combining training + biometrics
    # This is the main view the MCP queries
    conn.execute("""
        CREATE OR REPLACE VIEW daily_metrics AS
        WITH date_spine AS (
            -- Generate all dates from first workout to today
            SELECT UNNEST(generate_series(
                (SELECT MIN(CAST(date AS DATE)) FROM sets),
                CURRENT_DATE,
                INTERVAL 1 DAY
            ))::DATE as date
        ),
        training_daily AS (
            -- Training metrics per day
            SELECT 
                CAST(date AS DATE) as date,
                COUNT(DISTINCT workout_id) as workout_count,
                STRING_AGG(DISTINCT workout_type, ', ') as workout_types,
                COUNT(*) as total_sets,
                SUM(COALESCE(reps, 0)) as total_reps,
                SUM(COALESCE(reps, 1) * COALESCE(load_lbs, 0)) as volume_lbs,
                AVG(NULLIF(rpe, 0)) as avg_rpe
            FROM sets
            WHERE date IS NOT NULL
            GROUP BY CAST(date AS DATE)
        ),
        ultrahuman_metrics AS (
            -- Ultrahuman biometrics (if available)
            SELECT 
                CAST(date AS DATE) as date,
                recovery_score,
                sleep_score,
                hrv_ms as hrv_avg,
                resting_hr,
                sleep_minutes as sleep_min,
                deep_sleep_minutes as deep_min,
                rem_sleep_minutes as rem_min
            FROM ultrahuman_daily
            WHERE date IS NOT NULL
        )
        SELECT 
            ds.date,
            -- Training metrics
            t.workout_count,
            t.workout_types,
            t.total_sets,
            t.total_reps,
            t.volume_lbs,
            t.avg_rpe,
            -- Biometric metrics (from Ultrahuman)
            u.hrv_avg,
            u.resting_hr,
            u.sleep_min,
            u.sleep_score,
            u.recovery_score,
            u.deep_min,
            u.rem_min,
            -- Calculated sleep efficiency
            CASE WHEN u.sleep_min > 0 
                THEN ROUND((u.deep_min + u.rem_min) / u.sleep_min * 100, 1)
                ELSE NULL 
            END as sleep_efficiency_calc,
            -- Data availability flags
            (u.hrv_avg IS NOT NULL) as has_hrv,
            (u.sleep_min IS NOT NULL) as has_sleep,
            (u.recovery_score IS NOT NULL) as has_ultrahuman,
            (t.total_sets IS NOT NULL AND t.total_sets > 0) as has_training,
            -- Data completeness score (0-4)
            COALESCE((u.hrv_avg IS NOT NULL)::INT, 0) +
            COALESCE((u.sleep_min IS NOT NULL)::INT, 0) +
            COALESCE((u.recovery_score IS NOT NULL)::INT, 0) +
            COALESCE((t.total_sets IS NOT NULL AND t.total_sets > 0)::INT, 0) as data_completeness
        FROM date_spine ds
        LEFT JOIN training_daily t ON ds.date = t.date
        LEFT JOIN ultrahuman_metrics u ON ds.date = u.date
        ORDER BY ds.date
    """)
    print("  ✓ daily_metrics (unified training + biometrics)")
    
    # 2. weekly_training - weekly aggregates for MCP
    conn.execute("""
        CREATE OR REPLACE VIEW weekly_training AS
        SELECT 
            DATE_TRUNC('week', CAST(date AS DATE))::DATE as week_start,
            COUNT(DISTINCT workout_id) as workouts,
            COUNT(*) as total_sets,
            SUM(COALESCE(reps, 0)) as total_reps,
            SUM(COALESCE(reps, 1) * COALESCE(load_lbs, 0)) as total_volume_lbs,
            AVG(NULLIF(rpe, 0)) as avg_rpe
        FROM sets
        WHERE date IS NOT NULL
        GROUP BY DATE_TRUNC('week', CAST(date AS DATE))
        ORDER BY week_start
    """)
    print("  ✓ weekly_training")
    
    # 3. pattern_volume - weekly pattern distribution for MCP
    conn.execute("""
        CREATE OR REPLACE VIEW pattern_volume AS
        WITH split_patterns AS (
            SELECT 
                DATE_TRUNC('week', CAST(date AS DATE))::DATE as week_start,
                set_id,
                TRIM(UNNEST(STRING_SPLIT(patterns, ','))) as pattern
            FROM sets
            WHERE patterns IS NOT NULL AND patterns != ''
        )
        SELECT 
            week_start,
            pattern,
            COUNT(*) as sets
        FROM split_patterns
        WHERE pattern != ''
        GROUP BY week_start, pattern
        ORDER BY week_start DESC, sets DESC
    """)
    print("  ✓ pattern_volume")
    
    return conn


def verify_database(conn):
    """Run verification queries."""
    
    print("\n" + "="*60)
    print("DATABASE VERIFICATION")
    print("="*60)
    
    # List all tables and views
    result = conn.execute("""
        SELECT table_name, table_type 
        FROM information_schema.tables 
        WHERE table_schema = 'main'
        ORDER BY table_type, table_name
    """).fetchall()
    
    print("\nTables and Views:")
    for name, type_ in result:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {type_:5} {name}: {count:,} rows")
    
    # Sample dashboard
    print("\n" + "-"*60)
    print("CURRENT DASHBOARD:")
    print("-"*60)
    dashboard = conn.execute("SELECT * FROM dashboard_current").fetchone()
    if dashboard:
        cols = [desc[0] for desc in conn.description]
        for col, val in zip(cols, dashboard):
            print(f"  {col}: {val}")
    
    # Recent ACWR trend
    print("\n" + "-"*60)
    print("ACWR TREND (Last 7 Days):")
    print("-"*60)
    acwr = conn.execute("""
        SELECT date, volume_load, acute_load_7d, chronic_load_28d, acwr, acwr_zone 
        FROM acwr_daily 
        ORDER BY date DESC 
        LIMIT 7
    """).fetchall()
    print(f"  {'Date':<12} {'Volume':>8} {'Acute':>8} {'Chronic':>8} {'ACWR':>6} Zone")
    for row in acwr:
        print(f"  {row[0]!s:<12} {row[1] or 0:>8.0f} {row[2] or 0:>8.0f} {row[3] or 0:>8.0f} {row[4] or 0:>6.2f} {row[5]}")
    
    # Pattern gaps
    print("\n" + "-"*60)
    print("MOVEMENT PATTERN STATUS:")
    print("-"*60)
    patterns = conn.execute("""
        SELECT pattern, last_trained, days_since, frequency_status 
        FROM pattern_frequency 
        ORDER BY days_since DESC
    """).fetchall()
    for p in patterns:
        status_emoji = {'recent': '🟢', 'adequate': '🟡', 'gap': '🟠', 'neglected': '🔴'}.get(p[3], '⚪')
        print(f"  {status_emoji} {p[0]:<20} {p[2]:>3}d ago ({p[3]})")
    
    # Top exercises by progression
    print("\n" + "-"*60)
    print("EXERCISE PRs (Recent):")
    print("-"*60)
    prs = conn.execute("""
        SELECT exercise_name, date, best_e1rm, running_pr
        FROM exercise_progression 
        WHERE is_pr = true
        ORDER BY date DESC
        LIMIT 10
    """).fetchall()
    for pr in prs:
        print(f"  {pr[1]} {pr[0]:<30} e1RM: {pr[2]:.0f} lbs")
    
    return conn


def main():
    """Main entry point."""
    
    print("="*60)
    print("ARNOLD ANALYTICS DATABASE SETUP")
    print("="*60)
    
    if not STAGING_DIR.exists():
        print(f"ERROR: Staging directory not found: {STAGING_DIR}")
        sys.exit(1)
    
    conn = create_database()
    create_tier1_views(conn)
    create_tier2_views(conn)
    create_unified_views(conn)  # Add unified views for MCP
    verify_database(conn)
    conn.close()
    
    print("\n" + "="*60)
    print(f"Database created: {DB_PATH}")
    print("="*60)
    
    print("""
To query the database:

    import duckdb
    conn = duckdb.connect('data/arnold_analytics.duckdb')
    
    # Current status
    conn.execute("SELECT * FROM dashboard_current").fetchdf()
    
    # ACWR history
    conn.execute("SELECT * FROM acwr_daily ORDER BY date DESC LIMIT 30").fetchdf()
    
    # Muscle volume this week
    conn.execute("SELECT * FROM muscle_volume_weekly WHERE week_start = DATE_TRUNC('week', CURRENT_DATE)").fetchdf()
""")


if __name__ == "__main__":
    main()
