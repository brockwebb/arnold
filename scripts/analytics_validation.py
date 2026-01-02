#!/usr/bin/env python3
"""Quick analytics validation queries."""

import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "arnold_analytics.duckdb"

conn = duckdb.connect(str(DB_PATH), read_only=True)

print("="*60)
print("ARNOLD ANALYTICS - VALIDATION QUERIES")
print("="*60)

# 1. Data completeness overview
print("\n1. DATA COMPLETENESS BY MONTH")
print("-"*50)
result = conn.execute("""
    SELECT 
        DATE_TRUNC('month', date)::DATE as month,
        COUNT(*) as days,
        SUM(CASE WHEN has_hrv THEN 1 ELSE 0 END) as hrv_days,
        SUM(CASE WHEN has_sleep THEN 1 ELSE 0 END) as sleep_days,
        SUM(CASE WHEN has_ultrahuman THEN 1 ELSE 0 END) as uh_days,
        SUM(CASE WHEN has_training THEN 1 ELSE 0 END) as train_days,
        ROUND(AVG(data_completeness), 1) as avg_completeness
    FROM daily_metrics
    GROUP BY DATE_TRUNC('month', date)
    ORDER BY month DESC
    LIMIT 8
""").fetchdf()
print(result.to_string(index=False))

# 2. Recent training load
print("\n2. WEEKLY TRAINING VOLUME (last 8 weeks)")
print("-"*50)
result = conn.execute("""
    SELECT 
        week_start::DATE as week,
        workouts,
        total_sets,
        total_reps,
        ROUND(total_volume_lbs/1000, 1) as volume_klbs,
        ROUND(avg_rpe, 1) as avg_rpe
    FROM weekly_training
    LIMIT 8
""").fetchdf()
print(result.to_string(index=False))

# 3. HRV trend
print("\n3. HRV TREND (7-day rolling)")
print("-"*50)
result = conn.execute("""
    SELECT 
        date,
        ROUND(hrv_avg, 0) as hrv,
        ROUND(hrv_7d_avg, 0) as hrv_7d,
        ROUND(resting_hr, 0) as rhr,
        workout_types,
        data_completeness as complete
    FROM hrv_training_correlation
    WHERE hrv_avg IS NOT NULL
    ORDER BY date DESC
    LIMIT 10
""").fetchdf()
print(result.to_string(index=False))

# 4. Sleep vs Recovery
print("\n4. SLEEP → RECOVERY (where both available)")
print("-"*50)
result = conn.execute("""
    SELECT 
        CASE 
            WHEN sleep_min < 360 THEN '<6 hrs'
            WHEN sleep_min < 420 THEN '6-7 hrs'
            WHEN sleep_min < 480 THEN '7-8 hrs'
            ELSE '8+ hrs'
        END as sleep_bucket,
        COUNT(*) as days,
        ROUND(AVG(recovery_score), 1) as avg_recovery,
        ROUND(AVG(hrv_avg), 1) as avg_hrv
    FROM daily_metrics
    WHERE sleep_min IS NOT NULL AND recovery_score IS NOT NULL
    GROUP BY 1
    ORDER BY 1
""").fetchdf()
print(result.to_string(index=False))

# 5. Movement pattern distribution (last 4 weeks)
print("\n5. MOVEMENT PATTERN VOLUME (last 4 weeks)")
print("-"*50)
result = conn.execute("""
    SELECT 
        pattern,
        SUM(sets) as total_sets,
        SUM(reps) as total_reps,
        ROUND(SUM(volume_lbs)/1000, 1) as volume_klbs
    FROM pattern_volume
    WHERE week_start >= CURRENT_DATE - INTERVAL '28 days'
    GROUP BY pattern
    ORDER BY total_sets DESC
    LIMIT 10
""").fetchdf()
print(result.to_string(index=False))

# 6. Deadlift progression (key goal)
print("\n6. DEADLIFT PROGRESSION (toward 405x5)")
print("-"*50)
result = conn.execute("""
    SELECT 
        date,
        max_load as max_lbs,
        max_reps,
        sets_performed,
        ROUND(avg_rpe, 1) as rpe
    FROM exercise_progression
    WHERE LOWER(exercise_name) LIKE '%deadlift%'
      AND exercise_name NOT LIKE '%Romanian%'
      AND exercise_name NOT LIKE '%Stiff%'
    ORDER BY date DESC
    LIMIT 10
""").fetchdf()
print(result.to_string(index=False))

# 7. Last 7 days snapshot
print("\n7. LAST 7 DAYS (detailed)")
print("-"*50)
result = conn.execute("""
    SELECT 
        date,
        ROUND(hrv_avg, 0) as hrv,
        recovery_score as recov,
        ROUND(sleep_min/60.0, 1) as sleep_hrs,
        workout_types as training,
        total_sets as sets,
        data_completeness as data
    FROM daily_metrics
    ORDER BY date DESC
    LIMIT 7
""").fetchdf()
print(result.to_string(index=False))

conn.close()
print("\n" + "="*60)
