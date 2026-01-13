#!/usr/bin/env python3
"""
Apple Health Staging → Postgres Loader

Loads Apple Health data from staging parquet files into biometric_readings table.
Handles: steps, gait metrics (asymmetry, double_support, step_length, speed, steadiness)

Follows sensor hierarchy (FR-002):
- Steps: Apple Health is PRIMARY (phone more consistent than ring)
- Gait: Apple Health is ONLY source

Usage:
  python apple_health_to_postgres.py                  # Load all Apple Health data
  python apple_health_to_postgres.py --dry-run       # Preview without writing
  python apple_health_to_postgres.py --verbose       # Show details
  python apple_health_to_postgres.py --metric steps  # Load specific metric only
"""

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
STAGING_DIR = PROJECT_ROOT / "data" / "staging"

# Database config
DB_CONFIG = {
    "dbname": "arnold_analytics",
    "user": "brock",
    "host": "localhost",
    "port": 5432,
}

# Mapping: parquet file → (metric_type in postgres, value_column, source_name, agg_func)
METRIC_MAPPINGS = {
    "apple_health_steps": {
        "metric_type": "steps",
        "value_col": "steps",
        "source": "apple_health",
        "agg_func": "sum",  # Total steps per day
    },
    "apple_health_walking_asymmetry": {
        "metric_type": "walking_asymmetry_pct",
        "value_col": "asymmetry_avg",
        "source": "apple_health",
        "agg_func": "mean",
    },
    "apple_health_walking_double_support": {
        "metric_type": "walking_double_support_pct",
        "value_col": "double_support_avg",
        "source": "apple_health",
        "agg_func": "mean",
    },
    "apple_health_walking_step_length": {
        "metric_type": "walking_step_length",
        "value_col": "step_length_avg",
        "source": "apple_health",
        "agg_func": "mean",
    },
    "apple_health_walking_speed": {
        "metric_type": "walking_speed",
        "value_col": "speed_avg",
        "source": "apple_health",
        "agg_func": "mean",
    },
    "apple_health_walking_steadiness": {
        "metric_type": "walking_steadiness",
        "value_col": "steadiness_avg",
        "source": "apple_health",
        "agg_func": "mean",
    },
}


def load_parquet(name: str) -> pd.DataFrame:
    """Load a parquet file from staging."""
    path = STAGING_DIR / f"{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def upsert_biometric_readings(df: pd.DataFrame, metric_type: str, value_col: str, 
                               source: str, dry_run: bool = False, verbose: bool = False,
                               agg_func: str = "mean") -> int:
    """Upsert records into biometric_readings table.
    
    Uses ON CONFLICT (reading_date, metric_type, source) DO UPDATE.
    Aggregates by date first to avoid duplicates (multiple source_names per day).
    
    Args:
        agg_func: How to aggregate multiple values per day - 'mean', 'sum', 'max'
    """
    if df is None or len(df) == 0:
        return 0
    
    # Aggregate by date to handle multiple source_names (Hexagon, Ultrahuman, etc.)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    
    if agg_func == "sum":
        daily = df.groupby("date")[value_col].sum().reset_index()
    elif agg_func == "max":
        daily = df.groupby("date")[value_col].max().reset_index()
    else:  # mean
        daily = df.groupby("date")[value_col].mean().reset_index()
    
    # Prepare records
    records = []
    for _, row in daily.iterrows():
        reading_date = row["date"]
        value = row[value_col]
        if pd.isna(value):
            continue
            
        records.append((reading_date, metric_type, float(value), source))
    
    if not records:
        return 0
    
    if dry_run:
        if verbose:
            print(f"    Would upsert {len(records)} records for {metric_type}")
        return len(records)
    
    # Upsert to Postgres
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    sql = """
        INSERT INTO biometric_readings (reading_date, metric_type, value, source, imported_at)
        VALUES %s
        ON CONFLICT (reading_date, metric_type, source) 
        DO UPDATE SET 
            value = EXCLUDED.value,
            imported_at = NOW()
    """
    
    # Add imported_at timestamp
    records_with_ts = [(r[0], r[1], r[2], r[3], datetime.now()) for r in records]
    
    execute_values(cur, sql, records_with_ts, 
                   template="(%s, %s, %s, %s, %s)")
    
    conn.commit()
    inserted = len(records)
    conn.close()
    
    if verbose:
        print(f"    Upserted {inserted} records for {metric_type}")
    
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Load Apple Health data to Postgres")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show details")
    parser.add_argument("--metric", choices=list(METRIC_MAPPINGS.keys()), 
                        help="Load specific metric only")
    args = parser.parse_args()
    
    print("Loading Apple Health data to Postgres...")
    
    if args.dry_run:
        print("DRY RUN - no changes will be made\n")
    
    total_loaded = 0
    metrics_to_load = [args.metric] if args.metric else list(METRIC_MAPPINGS.keys())
    
    for parquet_name in metrics_to_load:
        config = METRIC_MAPPINGS[parquet_name]
        
        print(f"\n  {parquet_name}:")
        df = load_parquet(parquet_name)
        
        if len(df) == 0:
            print(f"    No data in staging (run import_apple_health.py first)")
            continue
        
        if args.verbose:
            print(f"    Loaded {len(df)} rows from staging")
            if "date" in df.columns:
                print(f"    Date range: {df['date'].min()} to {df['date'].max()}")
        
        count = upsert_biometric_readings(
            df,
            metric_type=config["metric_type"],
            value_col=config["value_col"],
            source=config["source"],
            dry_run=args.dry_run,
            verbose=args.verbose,
            agg_func=config.get("agg_func", "mean")
        )
        total_loaded += count
    
    print(f"\n✓ Done: {total_loaded} total records {'would be ' if args.dry_run else ''}loaded")


if __name__ == "__main__":
    main()
