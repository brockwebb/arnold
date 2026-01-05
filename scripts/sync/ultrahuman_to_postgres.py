#!/usr/bin/env python3
"""
Ultrahuman API → Postgres Direct Sync

Fetches health metrics from Ultrahuman Partner API and writes directly
to biometric_readings table. No intermediate files.

Environment Variables Required:
  ULTRAHUMAN_AUTH_TOKEN - API authorization token
  ULTRAHUMAN_USER_EMAIL - Email associated with Ultrahuman account
  DATABASE_URI - Postgres connection string (optional, defaults to local)

Usage:
  python ultrahuman_to_postgres.py                    # Sync yesterday
  python ultrahuman_to_postgres.py --days 7          # Sync last 7 days
  python ultrahuman_to_postgres.py --date 2025-12-07 # Sync specific date
  python ultrahuman_to_postgres.py --start 2025-12-07 --end 2026-01-05  # Date range
  python ultrahuman_to_postgres.py --days 30 --dry-run  # Preview without writing
"""

import os
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Configuration
BASE_URL = "https://partner.ultrahuman.com/api/v1"
PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")

# API response field → biometric_readings.metric_type mapping
# Based on actual Ultrahuman API response structure (metric_data array)
METRIC_MAP = {
    # Type in API → (our metric_type, value_key)
    "night_rhr": ("resting_hr", "avg"),
    "avg_sleep_hrv": ("hrv_morning", "value"),
    "active_minutes": ("active_minutes", "value"),
    "vo2_max": ("vo2_max", "value"),
    "recovery_index": ("recovery_score", "value"),
    "movement_index": ("movement_index", "value"),
    "sleep_rhr": ("sleep_rhr", "value"),
    "steps": ("steps", "value"),
}


def get_credentials() -> tuple[str, str]:
    """Load credentials from environment."""
    token = os.environ.get("ULTRAHUMAN_AUTH_TOKEN")
    email = os.environ.get("ULTRAHUMAN_USER_EMAIL")
    
    if not token or not email:
        raise ValueError(
            "Missing environment variables. Set:\n"
            "  ULTRAHUMAN_AUTH_TOKEN=your_token\n"
            "  ULTRAHUMAN_USER_EMAIL=your_email"
        )
    return token, email


def fetch_day(token: str, email: str, target_date: date) -> dict:
    """Fetch metrics for a single date from Ultrahuman API."""
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    
    params = {
        "email": email,
        "date": target_date.isoformat()
    }
    
    response = requests.get(
        f"{BASE_URL}/metrics",
        headers=headers,
        params=params,
        timeout=30
    )
    
    response.raise_for_status()
    return response.json()


def extract_metrics(api_response: dict, target_date: date) -> list[tuple]:
    """
    Extract metrics from API response into rows for biometric_readings.
    
    Returns list of tuples: (reading_date, metric_type, value, source)
    """
    rows = []
    
    # Navigate to metric_data array
    metric_data = api_response.get("data", {}).get("metric_data", [])
    
    for item in metric_data:
        api_type = item.get("type")
        obj = item.get("object", {})
        
        if api_type in METRIC_MAP:
            our_metric, value_key = METRIC_MAP[api_type]
            value = obj.get(value_key)
            
            if value is not None:
                try:
                    numeric_value = float(value)
                    rows.append((target_date, our_metric, numeric_value, "ultrahuman"))
                except (ValueError, TypeError):
                    pass  # Skip non-numeric values
    
    return rows


def upsert_to_postgres(rows: list[tuple], dry_run: bool = False) -> int:
    """
    Upsert rows to biometric_readings table.
    
    Returns count of rows upserted.
    """
    if not rows:
        return 0
    
    if dry_run:
        return len(rows)
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    sql = """
    INSERT INTO biometric_readings (reading_date, metric_type, value, source)
    VALUES %s
    ON CONFLICT (reading_date, metric_type, source) DO UPDATE SET
        value = EXCLUDED.value,
        imported_at = NOW()
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    
    count = len(rows)
    cur.close()
    conn.close()
    
    return count


def sync_date_range(
    token: str,
    email: str,
    start_date: date,
    end_date: date,
    dry_run: bool = False,
    verbose: bool = True
) -> dict:
    """
    Sync a date range from Ultrahuman API to Postgres.
    
    Returns summary dict with counts.
    """
    total_rows = 0
    days_synced = 0
    days_failed = 0
    
    current = start_date
    while current <= end_date:
        try:
            api_data = fetch_day(token, email, current)
            rows = extract_metrics(api_data, current)
            
            if rows:
                count = upsert_to_postgres(rows, dry_run=dry_run)
                total_rows += count
                days_synced += 1
                if verbose:
                    print(f"  ✓ {current}: {count} metrics")
            else:
                if verbose:
                    print(f"  - {current}: no data")
                    print(f"    API response: {api_data}")
                    
        except requests.HTTPError as e:
            days_failed += 1
            if verbose:
                print(f"  ✗ {current}: HTTP {e.response.status_code}")
        except Exception as e:
            days_failed += 1
            if verbose:
                print(f"  ✗ {current}: {e}")
        
        current += timedelta(days=1)
    
    return {
        "days_synced": days_synced,
        "days_failed": days_failed,
        "total_rows": total_rows,
        "dry_run": dry_run
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sync Ultrahuman metrics directly to Postgres"
    )
    parser.add_argument(
        "--days", type=int,
        help="Number of days to sync (default: 1 = yesterday)"
    )
    parser.add_argument(
        "--date", type=str,
        help="Specific date to sync (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--start", type=str,
        help="Start date for range (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end", type=str,
        help="End date for range (YYYY-MM-DD), defaults to yesterday"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without writing to database"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress per-day output"
    )
    
    args = parser.parse_args()
    
    # Determine date range
    yesterday = date.today() - timedelta(days=1)
    
    if args.date:
        start_date = end_date = date.fromisoformat(args.date)
    elif args.start:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end) if args.end else yesterday
    elif args.days:
        end_date = yesterday
        start_date = end_date - timedelta(days=args.days - 1)
    else:
        # Default: sync yesterday only
        start_date = end_date = yesterday
    
    # Load credentials
    token, email = get_credentials()
    
    # Header
    days_count = (end_date - start_date).days + 1
    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode}Ultrahuman → Postgres: {start_date} to {end_date} ({days_count} days)")
    
    if not args.quiet:
        print(f"  User: {email}\n")
    
    # Sync
    result = sync_date_range(
        token, email, start_date, end_date,
        dry_run=args.dry_run,
        verbose=not args.quiet
    )
    
    # Summary
    print(f"\n{'Would sync' if args.dry_run else 'Synced'}: "
          f"{result['total_rows']} metrics from {result['days_synced']} days")
    
    if result['days_failed']:
        print(f"Failed: {result['days_failed']} days")


if __name__ == "__main__":
    main()
