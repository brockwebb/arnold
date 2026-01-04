#!/usr/bin/env python3
"""
Import Ultrahuman manual CSV export to Postgres.

Usage:
    python scripts/import_ultrahuman_csv.py data/raw/ultrahuman/manual_export_2026-01-01.csv
    python scripts/import_ultrahuman_csv.py data/raw/ultrahuman/*.csv --dry-run
"""

import os
import sys
import csv
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")

# Map CSV columns to our metric types
COLUMN_MAPPING = {
    "Sleep Score": "sleep_score",
    "Recovery Score": "recovery_score",
    "Movement Score": "movement_index",
    "Total Steps": "steps",
    "Total Calories": "calories",
    "Total Sleep": "sleep_total_min",
    "Sleep Awake Time": "sleep_awake_min",
    "Deep Sleep": "sleep_deep_min",
    "REM Sleep": "sleep_rem_min",
    "Light Sleep": "sleep_light_min",
    "Sleep Efficiency": "sleep_efficiency",
    "Perceived Recovery": "perceived_recovery",
    "Average Temperature": "avg_temperature",
    "Average RHR": "resting_hr",
    "Average HRV": "hrv_morning",
    "Total Activity Minutes": "active_minutes",
}


def parse_csv(filepath: Path) -> list:
    """Parse Ultrahuman CSV export."""
    readings = []
    
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            date_str = row.get("Date", "").strip()
            if not date_str:
                continue
            
            # Parse date (format: YYYY-MM-DD)
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                print(f"  Skipping invalid date: {date_str}")
                continue
            
            # Extract each metric
            for csv_col, metric_type in COLUMN_MAPPING.items():
                value_str = row.get(csv_col, "").strip()
                
                if not value_str:
                    continue
                
                try:
                    value = float(value_str)
                    readings.append({
                        "date": date,
                        "metric_type": metric_type,
                        "value": value
                    })
                except ValueError:
                    # Skip non-numeric values
                    pass
    
    return readings


def upsert_biometrics(readings: list):
    """Insert or update biometric readings in Postgres."""
    if not readings:
        print("No readings to insert")
        return 0
    
    import psycopg2
    from psycopg2.extras import execute_values
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # Prepare rows: (reading_date, metric_type, value, source)
    rows = [(r['date'], r['metric_type'], float(r['value']), 'ultrahuman') for r in readings]
    
    # Upsert
    sql = """
    INSERT INTO biometric_readings (reading_date, metric_type, value, source)
    VALUES %s
    ON CONFLICT (reading_date, metric_type, source) DO UPDATE SET
        value = EXCLUDED.value,
        imported_at = NOW()
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    cur.close()
    conn.close()
    
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Import Ultrahuman CSV export")
    parser.add_argument("files", nargs="+", help="CSV file(s) to import")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't save")
    args = parser.parse_args()
    
    all_readings = []
    
    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            print(f"File not found: {filepath}")
            continue
        
        print(f"Parsing {path.name}...")
        readings = parse_csv(path)
        print(f"  Found {len(readings)} readings from {len(set(r['date'] for r in readings))} days")
        all_readings.extend(readings)
    
    print(f"\nTotal: {len(all_readings)} readings")
    
    # Show metric breakdown
    metric_counts = {}
    for r in all_readings:
        metric_counts[r['metric_type']] = metric_counts.get(r['metric_type'], 0) + 1
    
    print("\nMetrics found:")
    for metric, count in sorted(metric_counts.items()):
        print(f"  {metric}: {count}")
    
    # Date range
    dates = sorted(set(r['date'] for r in all_readings))
    if dates:
        print(f"\nDate range: {dates[0]} to {dates[-1]}")
    
    if args.dry_run:
        print("\nDRY RUN - not saving to database")
    else:
        count = upsert_biometrics(all_readings)
        print(f"\nUpserted {count} readings to Postgres")
    
    print("Done")


if __name__ == "__main__":
    main()
