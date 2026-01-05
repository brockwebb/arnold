#!/usr/bin/env python3
"""
Import Apple Health data from staged Parquet files into Postgres.

Usage:
    python scripts/import_apple_health.py

Imports:
- Resting HR (daily)
- HRV (aggregated to daily morning average)
- Sleep (aggregated to daily totals)
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from pathlib import Path

# Database connection
DB_CONFIG = {
    "dbname": "arnold_analytics",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
}

STAGING_DIR = Path(__file__).parent.parent / "data" / "staging"


def import_resting_hr(conn, cur):
    """Import resting heart rate - already daily level."""
    fp = STAGING_DIR / "apple_health_resting_hr.parquet"
    if not fp.exists():
        print(f"File not found: {fp}")
        return 0
    
    df = pd.read_parquet(fp)
    print(f"Resting HR: {len(df)} records")
    
    # Convert to records
    records = []
    for _, row in df.iterrows():
        records.append({
            'reading_date': row['date'].date() if hasattr(row['date'], 'date') else row['date'],
            'metric_type': 'resting_hr',
            'value': float(row['resting_hr']),
            'source': row['source_name'].lower()  # Normalize to lowercase
        })
    
    # Upsert
    execute_batch(
        cur,
        """
        INSERT INTO biometric_readings (reading_date, metric_type, value, source)
        VALUES (%(reading_date)s, %(metric_type)s, %(value)s, %(source)s)
        ON CONFLICT (reading_date, metric_type, source) 
        DO UPDATE SET value = EXCLUDED.value, imported_at = NOW()
        """,
        records,
        page_size=100
    )
    conn.commit()
    return len(records)


def import_hrv(conn, cur):
    """Import HRV - aggregate to daily morning average (before 10am)."""
    fp = STAGING_DIR / "apple_health_hrv.parquet"
    if not fp.exists():
        print(f"File not found: {fp}")
        return 0
    
    df = pd.read_parquet(fp)
    print(f"HRV raw: {len(df)} records")
    
    # Convert measured_at to datetime if needed
    df['measured_at'] = pd.to_datetime(df['measured_at'])
    df['date'] = df['measured_at'].dt.date
    df['hour'] = df['measured_at'].dt.hour
    
    # Morning window: 4am-10am (best for morning HRV reading)
    morning_df = df[(df['hour'] >= 4) & (df['hour'] < 10)]
    
    # Aggregate by date - take mean of morning readings
    daily = morning_df.groupby(['date', 'source_name']).agg({
        'hrv_ms': 'mean'
    }).reset_index()
    
    print(f"HRV daily (morning avg): {len(daily)} records")
    
    records = []
    for _, row in daily.iterrows():
        records.append({
            'reading_date': row['date'],
            'metric_type': 'hrv_morning',
            'value': round(float(row['hrv_ms']), 1),
            'source': row['source_name'].lower()  # Normalize to lowercase
        })
    
    execute_batch(
        cur,
        """
        INSERT INTO biometric_readings (reading_date, metric_type, value, source)
        VALUES (%(reading_date)s, %(metric_type)s, %(value)s, %(source)s)
        ON CONFLICT (reading_date, metric_type, source) 
        DO UPDATE SET value = EXCLUDED.value, imported_at = NOW()
        """,
        records,
        page_size=100
    )
    conn.commit()
    return len(records)


def import_sleep(conn, cur):
    """Import sleep - aggregate stages to daily totals."""
    fp = STAGING_DIR / "apple_health_sleep.parquet"
    if not fp.exists():
        print(f"File not found: {fp}")
        return 0
    
    df = pd.read_parquet(fp)
    print(f"Sleep raw: {len(df)} records")
    
    # Map stages to categories
    stage_map = {
        'awake': 'awake',
        'asleepcore': 'light',
        'asleepdeep': 'deep',
        'asleeprem': 'rem',
        'inbed': 'awake',  # in bed but not sleeping
    }
    df['stage_category'] = df['sleep_stage'].map(stage_map).fillna('other')
    
    # Aggregate by date - sum minutes per stage
    daily = df.groupby(['date', 'source_name', 'stage_category']).agg({
        'duration_minutes': 'sum'
    }).reset_index()
    
    # Pivot to get one row per date with columns for each stage
    pivot = daily.pivot_table(
        index=['date', 'source_name'],
        columns='stage_category',
        values='duration_minutes',
        fill_value=0
    ).reset_index()
    
    print(f"Sleep daily: {len(pivot)} records")
    
    records = []
    for _, row in pivot.iterrows():
        date = row['date'].date() if hasattr(row['date'], 'date') else row['date']
        source = row['source_name'].lower()  # Normalize to lowercase
        
        # Total sleep (excluding awake)
        total_sleep = row.get('light', 0) + row.get('deep', 0) + row.get('rem', 0)
        
        records.append({
            'reading_date': date,
            'metric_type': 'sleep_total_min',
            'value': float(total_sleep),
            'source': source
        })
        
        if row.get('deep', 0) > 0:
            records.append({
                'reading_date': date,
                'metric_type': 'sleep_deep_min',
                'value': float(row['deep']),
                'source': source
            })
        
        if row.get('rem', 0) > 0:
            records.append({
                'reading_date': date,
                'metric_type': 'sleep_rem_min',
                'value': float(row['rem']),
                'source': source
            })
    
    execute_batch(
        cur,
        """
        INSERT INTO biometric_readings (reading_date, metric_type, value, source)
        VALUES (%(reading_date)s, %(metric_type)s, %(value)s, %(source)s)
        ON CONFLICT (reading_date, metric_type, source) 
        DO UPDATE SET value = EXCLUDED.value, imported_at = NOW()
        """,
        records,
        page_size=100
    )
    conn.commit()
    return len(records)


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        print("\n=== Importing Apple Health Data ===\n")
        
        rhr_count = import_resting_hr(conn, cur)
        print(f"  Resting HR: {rhr_count} records\n")
        
        hrv_count = import_hrv(conn, cur)
        print(f"  HRV: {hrv_count} records\n")
        
        sleep_count = import_sleep(conn, cur)
        print(f"  Sleep: {sleep_count} records\n")
        
        print(f"=== Import Complete ===")
        print(f"Total: {rhr_count + hrv_count + sleep_count} biometric readings")
        
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
