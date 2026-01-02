#!/usr/bin/env python3
"""
Stage Ultrahuman Data

Converts raw Ultrahuman exports (CSV manual exports + JSON API syncs) 
to normalized Parquet in staging directory.

Handles:
  - Manual CSV exports from Ultrahuman app
  - JSON files from API sync script
  - Deduplication by date
  - Column normalization

Output: /data/staging/ultrahuman_daily.parquet

Usage:
  python stage_ultrahuman.py              # Process all raw files
  python stage_ultrahuman.py --verbose    # Show processing details
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "ultrahuman"
STAGING_DIR = DATA_DIR / "staging"

# Column mapping: CSV column name -> standardized name
CSV_COLUMN_MAP = {
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Recovery Score": "recovery_score", 
    "Movement Score": "movement_score",
    "Total Steps": "steps",
    "Total Calories": "calories",
    "Total Sleep": "sleep_minutes",
    "Sleep Awake Time": "sleep_awake_minutes",
    "Deep Sleep": "deep_sleep_minutes",
    "REM Sleep": "rem_sleep_minutes",
    "Light Sleep": "light_sleep_minutes",
    "Sleep Efficiency": "sleep_efficiency",
    "Perceived Recovery": "perceived_recovery",
    "Phase Advance Steps": "phase_advance_steps",
    "Average Temperature": "skin_temp_c",
    "Average RHR": "resting_hr",
    "Average HRV": "hrv_ms",
    "Total Activity Minutes": "activity_minutes"
}

# API response field mapping (adjust based on actual API response structure)
API_FIELD_MAP = {
    "sleep_score": "sleep_score",
    "recovery_score": "recovery_score",
    "movement_score": "movement_score",
    "steps": "steps",
    "calories": "calories",
    "total_sleep_minutes": "sleep_minutes",
    "awake_minutes": "sleep_awake_minutes",
    "deep_sleep_minutes": "deep_sleep_minutes",
    "rem_sleep_minutes": "rem_sleep_minutes",
    "light_sleep_minutes": "light_sleep_minutes",
    "sleep_efficiency": "sleep_efficiency",
    "skin_temperature": "skin_temp_c",
    "resting_heart_rate": "resting_hr",
    "hrv": "hrv_ms",
    "activity_minutes": "activity_minutes"
}


def load_csv_export(filepath: Path) -> pd.DataFrame:
    """Load and normalize a CSV export."""
    df = pd.read_csv(filepath)
    
    # Rename columns
    df = df.rename(columns=CSV_COLUMN_MAP)
    
    # Parse date
    df["date"] = pd.to_datetime(df["date"]).dt.date
    
    # Add source metadata
    df["_source"] = "csv_export"
    df["_source_file"] = filepath.name
    
    return df


def load_api_sync(filepath: Path) -> pd.DataFrame:
    """Load and normalize an API sync JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    
    records = []
    for rec in data.get("records", []):
        normalized = {"date": rec.get("_sync_date")}
        
        # Map API fields to standard names
        for api_field, std_field in API_FIELD_MAP.items():
            if api_field in rec:
                normalized[std_field] = rec[api_field]
        
        normalized["_source"] = "api_sync"
        normalized["_source_file"] = filepath.name
        records.append(normalized)
    
    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    
    return df


def load_all_raw(verbose: bool = False) -> pd.DataFrame:
    """Load all raw files and combine."""
    frames = []
    
    for filepath in sorted(RAW_DIR.glob("*.csv")):
        if verbose:
            print(f"  Loading CSV: {filepath.name}")
        frames.append(load_csv_export(filepath))
    
    for filepath in sorted(RAW_DIR.glob("*.json")):
        if verbose:
            print(f"  Loading JSON: {filepath.name}")
        frames.append(load_api_sync(filepath))
    
    if not frames:
        return pd.DataFrame()
    
    df = pd.concat(frames, ignore_index=True)
    return df


def deduplicate(df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """
    Deduplicate by date.
    
    Priority: API sync > CSV export (API is more recent/authoritative)
    Within same source type: Keep most recent file
    """
    if df.empty:
        return df
    
    before = len(df)
    
    # Sort so API comes after CSV, and newer files come after older
    df = df.sort_values(["date", "_source", "_source_file"])
    
    # Keep last (most authoritative) per date
    df = df.drop_duplicates(subset=["date"], keep="last")
    
    after = len(df)
    if verbose and before != after:
        print(f"  Deduplicated: {before} → {after} rows")
    
    return df


def stage(df: pd.DataFrame, verbose: bool = False) -> Path:
    """Write to Parquet in staging directory."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    
    output_path = STAGING_DIR / "ultrahuman_daily.parquet"
    
    # Sort by date
    df = df.sort_values("date").reset_index(drop=True)
    
    # Convert date column to proper date type for parquet
    df["date"] = pd.to_datetime(df["date"])
    
    # Write parquet
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_path)
    
    if verbose:
        print(f"\nStaged to: {output_path}")
        print(f"  Rows: {len(df)}")
        print(f"  Date range: {df['date'].min().date()} → {df['date'].max().date()}")
        print(f"  Columns: {list(df.columns)}")
    
    return output_path


def update_catalog(df: pd.DataFrame):
    """Update catalog.json with Ultrahuman table metadata."""
    catalog_path = DATA_DIR / "catalog.json"
    
    if catalog_path.exists():
        with open(catalog_path) as f:
            catalog = json.load(f)
    else:
        catalog = {"version": "1.0", "sources": {}, "created_at": datetime.utcnow().isoformat()}
    
    # Ensure sources key exists
    if "sources" not in catalog:
        catalog["sources"] = {}
    
    # Build column metadata
    columns = {}
    for col in df.columns:
        dtype = str(df[col].dtype)
        if "int" in dtype:
            col_type = "int"
        elif "float" in dtype:
            col_type = "float"
        elif "datetime" in dtype or col == "date":
            col_type = "date"
        else:
            col_type = "string"
        
        columns[col] = {
            "type": col_type,
            "nullable": bool(df[col].isna().any())
        }
    
    # Get date range (handle both datetime.date and pandas Timestamp)
    min_date = df["date"].min()
    max_date = df["date"].max()
    # Extract date if it's a Timestamp, otherwise use as-is
    if hasattr(min_date, 'date') and callable(getattr(min_date, 'date')):
        min_date = min_date.date()
    if hasattr(max_date, 'date') and callable(getattr(max_date, 'date')):
        max_date = max_date.date()
    
    # Update catalog entry (matching existing structure)
    catalog["sources"]["ultrahuman"] = {
        "raw_path": "raw/ultrahuman/*.csv",
        "staging_table": "staging/ultrahuman_daily.parquet",
        "grain": "date",
        "row_count": len(df),
        "date_range": [str(min_date), str(max_date)],
        "time_handling": {
            "field": "date",
            "format": "YYYY-MM-DD",
            "tz": "local_implicit",
            "attribution": "metric_date",
            "note": "Daily aggregates. Sleep metrics attributed to wake date."
        },
        "columns": columns,
        "join_keys": ["date"],
        "measures": ["sleep_score", "recovery_score", "hrv_ms", "resting_hr", "steps", "calories"],
        "fitness_for_use": {
            "completeness": "high - daily metrics since ring activation",
            "consistency": "high - automated collection",
            "timeliness": "manual export currently"
        },
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Move ultrahuman from future_sources if it exists there
    if "future_sources" in catalog and "ultrahuman" in catalog["future_sources"]:
        del catalog["future_sources"]["ultrahuman"]
    
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Stage Ultrahuman data")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show processing details")
    args = parser.parse_args()
    
    print("Staging Ultrahuman data...")
    
    # Load
    if args.verbose:
        print("\nLoading raw files:")
    df = load_all_raw(verbose=args.verbose)
    
    if df.empty:
        print("No raw files found in", RAW_DIR)
        return
    
    print(f"\nLoaded {len(df)} total rows")
    
    # Deduplicate
    df = deduplicate(df, verbose=args.verbose)
    
    # Stage
    output_path = stage(df, verbose=args.verbose)
    
    # Update catalog
    update_catalog(df)
    print(f"Updated catalog.json")
    
    print("\n✓ Done")


if __name__ == "__main__":
    main()
