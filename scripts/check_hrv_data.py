#!/usr/bin/env python3
"""Quick check of HRV data in DuckDB."""

import duckdb

DB_PATH = "/Users/brock/Documents/GitHub/arnold/data/arnold_analytics.duckdb"
conn = duckdb.connect(DB_PATH, read_only=True)

print("=== APPLE HEALTH HRV ===")
result = conn.execute("""
    SELECT 
        MIN(date) as first_date,
        MAX(date) as last_date,
        COUNT(*) as total_rows
    FROM apple_health_hrv
""").fetchone()
print(f"Date range: {result[0]} → {result[1]}")
print(f"Total rows: {result[2]}")

print("\n=== HRV BY WEEK (recent) ===")
result = conn.execute("""
    SELECT 
        DATE_TRUNC('week', CAST(date AS DATE)) as week,
        COUNT(*) as samples,
        ROUND(AVG(hrv_ms), 1) as avg_hrv
    FROM apple_health_hrv
    GROUP BY DATE_TRUNC('week', CAST(date AS DATE))
    ORDER BY week DESC
    LIMIT 10
""").fetchall()
for row in result:
    print(f"  {str(row[0])[:10]}: {row[1]} samples, avg {row[2]} ms")

print("\n=== ULTRAHUMAN DAILY ===")
result = conn.execute("""
    SELECT 
        MIN(date) as first_date,
        MAX(date) as last_date,
        COUNT(*) as total_rows,
        COUNT(hrv_ms) as hrv_not_null
    FROM ultrahuman_daily
""").fetchone()
print(f"Date range: {result[0]} → {result[1]}")
print(f"Total rows: {result[2]}, HRV non-null: {result[3]}")

print("\n=== ULTRAHUMAN RECENT (last 30 days) ===")
result = conn.execute("""
    SELECT date, hrv_ms, recovery_score, sleep_score
    FROM ultrahuman_daily
    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    ORDER BY date DESC
    LIMIT 15
""").fetchall()
for row in result:
    print(f"  {str(row[0])[:10]}: HRV={row[1]}, Recovery={row[2]}, Sleep={row[3]}")

conn.close()
