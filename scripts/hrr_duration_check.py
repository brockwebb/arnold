#!/usr/bin/env python3
"""Quick check: what's the duration distribution of recovery intervals?"""

import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / '.env')

dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
conn = psycopg2.connect(dsn)

query = """
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE duration_seconds >= 60) as gte_60,
    COUNT(*) FILTER (WHERE duration_seconds >= 90) as gte_90,
    COUNT(*) FILTER (WHERE duration_seconds >= 120) as gte_120,
    COUNT(*) FILTER (WHERE duration_seconds >= 150) as gte_150,
    MIN(duration_seconds) as min_dur,
    MAX(duration_seconds) as max_dur,
    AVG(duration_seconds)::int as avg_dur,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds)::int as median_dur,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_seconds)::int as p90_dur
FROM hr_recovery_intervals
"""

with conn.cursor() as cur:
    cur.execute(query)
    row = cur.fetchone()

print("HRR Interval Duration Distribution")
print("=" * 40)
print(f"Total intervals: {row[0]}")
print(f"  >= 60s:  {row[1]} ({row[1]/row[0]*100:.1f}%)")
print(f"  >= 90s:  {row[2]} ({row[2]/row[0]*100:.1f}%)")
print(f"  >= 120s: {row[3]} ({row[3]/row[0]*100:.1f}%)")
print(f"  >= 150s: {row[4]} ({row[4]/row[0]*100:.1f}%)")
print(f"\nMin: {row[5]}s, Max: {row[6]}s")
print(f"Mean: {row[7]}s, Median: {row[8]}s, 90th: {row[9]}s")

conn.close()
