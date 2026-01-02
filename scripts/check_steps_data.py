#!/usr/bin/env python3
"""Check step count data."""

import duckdb

DB_PATH = "/Users/brock/Documents/GitHub/arnold/data/arnold_analytics.duckdb"
conn = duckdb.connect(DB_PATH, read_only=True)

print("=== STEP DATA OVERVIEW ===")
result = conn.execute("""
    SELECT 
        MIN(date) as first_date,
        MAX(date) as last_date,
        COUNT(*) as total_rows,
        COUNT(DISTINCT date) as unique_days
    FROM apple_health_steps
""").fetchone()
print(f"Date range: {result[0]} → {result[1]}")
print(f"Total rows: {result[2]}, Unique days: {result[3]}")

print("\n=== STEPS BY SOURCE ===")
result = conn.execute("""
    SELECT 
        source_name,
        COUNT(*) as entries,
        SUM(steps) as total_steps
    FROM apple_health_steps
    GROUP BY source_name
    ORDER BY total_steps DESC
""").fetchall()
for row in result:
    print(f"  {row[0]}: {row[1]} entries, {row[2]:,} total steps")

print("\n=== DAILY STEPS (last 14 days) ===")
result = conn.execute("""
    SELECT 
        date,
        SUM(steps) as daily_steps
    FROM apple_health_steps
    GROUP BY date
    ORDER BY date DESC
    LIMIT 14
""").fetchall()
for row in result:
    print(f"  {str(row[0])[:10]}: {row[1]:,} steps")

print("\n=== WEEKLY AVERAGES ===")
result = conn.execute("""
    SELECT 
        DATE_TRUNC('week', CAST(date AS DATE)) as week,
        ROUND(AVG(daily_steps)) as avg_steps
    FROM (
        SELECT date, SUM(steps) as daily_steps
        FROM apple_health_steps
        GROUP BY date
    )
    GROUP BY DATE_TRUNC('week', CAST(date AS DATE))
    ORDER BY week DESC
    LIMIT 8
""").fetchall()
for row in result:
    print(f"  {str(row[0])[:10]}: {int(row[1]):,} avg steps/day")

conn.close()
