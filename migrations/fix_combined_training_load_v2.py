#!/usr/bin/env python3
"""
Migration: Update combined_training_load to use V2 schema

Run with: python migrations/fix_combined_training_load_v2.py

This script:
1. Backs up current view definition
2. Checks workout_summaries_v2 has required columns
3. Creates updated view in a transaction
4. Validates new view returns data through recent dates
5. Rolls back on any failure
"""

import psycopg2
from psycopg2 import sql
import sys
from datetime import datetime, timedelta

DB_URI = "postgresql://brock@localhost:5432/arnold_analytics"

def get_current_view_definition(cur, view_name):
    """Get current view definition for backup."""
    cur.execute("""
        SELECT definition FROM pg_views 
        WHERE schemaname = 'public' AND viewname = %s
    """, [view_name])
    row = cur.fetchone()
    return row[0] if row else None

def check_v2_columns(cur):
    """Verify workout_summaries_v2 has columns the view needs."""
    required = ['workout_date', 'workout_name', 'workout_type', 'total_volume_lbs', 
                'set_count', 'duration_minutes', 'polar_session_id', 
                'polar_match_confidence', 'polar_match_method']
    
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'workout_summaries_v2'
    """)
    available = {row[0] for row in cur.fetchall()}
    
    missing = set(required) - available
    return missing

def main():
    print("=" * 60)
    print("Migration: combined_training_load -> V2 schema")
    print("=" * 60)
    
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = False  # Explicit transaction control
    cur = conn.cursor()
    
    try:
        # Step 1: Backup current definition
        print("\n[1/5] Backing up current view definition...")
        old_def = get_current_view_definition(cur, 'combined_training_load')
        if not old_def:
            print("ERROR: combined_training_load view not found!")
            sys.exit(1)
        
        backup_file = f"/tmp/combined_training_load_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        with open(backup_file, 'w') as f:
            f.write(f"-- Backup of combined_training_load view\n")
            f.write(f"-- Created: {datetime.now().isoformat()}\n")
            f.write(f"CREATE OR REPLACE VIEW combined_training_load AS\n{old_def}")
        print(f"  Backup saved to: {backup_file}")
        
        # Step 2: Check current max date (before)
        print("\n[2/5] Checking current data range...")
        cur.execute("SELECT MAX(workout_date) FROM combined_training_load")
        old_max = cur.fetchone()[0]
        print(f"  Current max date: {old_max}")
        
        cur.execute("SELECT MAX(workout_date) FROM workout_summaries_v2")
        v2_max = cur.fetchone()[0]
        print(f"  V2 max date: {v2_max}")
        
        if old_max and v2_max and old_max >= v2_max:
            print("  WARNING: Legacy already has same/newer data. Migration may not be needed.")
            response = input("  Continue anyway? [y/N]: ")
            if response.lower() != 'y':
                print("  Aborted by user.")
                sys.exit(0)
        
        # Step 3: Check V2 has required columns
        print("\n[3/5] Verifying workout_summaries_v2 schema...")
        missing = check_v2_columns(cur)
        if missing:
            print(f"  ERROR: workout_summaries_v2 missing columns: {missing}")
            print("  Cannot proceed. View would fail.")
            sys.exit(1)
        print("  All required columns present.")
        
        # Step 4: Create updated view
        print("\n[4/5] Creating updated view...")
        new_view_sql = """
CREATE OR REPLACE VIEW combined_training_load AS
WITH volume_daily AS (
    SELECT 
        ws.workout_date,
        MAX(ws.workout_name) AS workout_name,
        MAX(ws.workout_type) AS workout_type,
        SUM(ws.total_volume_lbs) AS daily_volume_lbs,
        SUM(ws.set_count) AS daily_sets,
        MAX(ws.duration_minutes) AS arnold_duration,
        MAX(ps.duration_seconds / 60) AS polar_duration,
        MAX(ps.avg_hr) AS weighted_avg_hr,
        MAX(ps.max_hr) AS peak_hr,
        MAX(ps.sport_type) AS polar_sport,
        MAX(ws.polar_session_id) AS polar_session_id,
        MAX(ws.polar_match_confidence) AS polar_match_confidence,
        MAX(ws.polar_match_method) AS polar_match_method
    FROM workout_summaries_v2 ws
    LEFT JOIN polar_sessions ps ON ws.polar_session_id = ps.id
    GROUP BY ws.workout_date
),
hr_daily AS (
    SELECT 
        session_date AS workout_date,
        daily_trimp,
        daily_edwards_trimp,
        (SELECT MAX(intensity_factor) FROM polar_session_metrics psm 
         WHERE psm.session_date = hr_training_load_daily.session_date) AS intensity_factor,
        pct_low_intensity,
        pct_high_intensity
    FROM hr_training_load_daily
)
SELECT 
    v.workout_date,
    v.workout_name,
    v.workout_type,
    v.daily_sets,
    v.daily_volume_lbs,
    v.arnold_duration,
    v.polar_duration,
    v.weighted_avg_hr,
    v.peak_hr,
    v.polar_sport,
    h.daily_trimp,
    h.daily_edwards_trimp,
    h.intensity_factor,
    h.pct_low_intensity,
    h.pct_high_intensity,
    v.polar_match_confidence,
    v.polar_match_method,
    CASE WHEN v.polar_session_id IS NOT NULL THEN 'linked' ELSE 'volume_only' END AS data_coverage
FROM volume_daily v
LEFT JOIN hr_daily h ON v.workout_date = h.workout_date
"""
        cur.execute(new_view_sql)
        print("  View updated.")
        
        # Step 5: Validate
        print("\n[5/5] Validating new view...")
        cur.execute("SELECT MAX(workout_date), COUNT(*) FROM combined_training_load")
        new_max, count = cur.fetchone()
        print(f"  New max date: {new_max}")
        print(f"  Total rows: {count}")
        
        # Check we have recent data
        week_ago = (datetime.now() - timedelta(days=7)).date()
        cur.execute("SELECT COUNT(*) FROM combined_training_load WHERE workout_date >= %s", [week_ago])
        recent_count = cur.fetchone()[0]
        print(f"  Workouts in last 7 days: {recent_count}")
        
        # Check daily_status also works (depends on this view)
        cur.execute("SELECT MAX(date), COUNT(*) FROM daily_status")
        ds_max, ds_count = cur.fetchone()
        print(f"  daily_status max date: {ds_max}, rows: {ds_count}")
        
        if new_max is None or (v2_max and new_max < v2_max):
            print(f"\n  ERROR: Validation failed! Expected max {v2_max}, got {new_max}")
            print("  Rolling back...")
            conn.rollback()
            sys.exit(1)
        
        # Commit
        print("\n" + "=" * 60)
        print("Validation passed. Committing transaction...")
        conn.commit()
        print("SUCCESS!")
        print(f"\nView now uses workout_summaries_v2 (max date: {new_max})")
        print(f"Backup saved to: {backup_file}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        print("Rolling back transaction...")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
