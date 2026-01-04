#!/usr/bin/env python3
"""
Ultrahuman API Sync

Fetches biometric data from Ultrahuman Ring API.

API: https://partner.ultrahuman.com/api/v1/metrics
Auth: Token in Authorization header (not Bearer)
Params: email, date (YYYY-MM-DD)

Setup:
    Add to .env:
        ULTRAHUMAN_AUTH_TOKEN=your_token_here
        ULTRAHUMAN_USER_EMAIL=your_email@example.com

Usage:
    python scripts/sync_ultrahuman.py              # Fetch last 7 days
    python scripts/sync_ultrahuman.py --days 30   # Fetch last 30 days
    python scripts/sync_ultrahuman.py --since 2026-01-01  # Fetch since date
    python scripts/sync_ultrahuman.py --test      # Test API connection
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Configuration
API_URL = "https://partner.ultrahuman.com/api/v1/metrics"
PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def get_credentials():
    """Get API credentials from environment."""
    token = os.environ.get("ULTRAHUMAN_AUTH_TOKEN")
    email = os.environ.get("ULTRAHUMAN_USER_EMAIL")
    
    if not token:
        print("ERROR: ULTRAHUMAN_AUTH_TOKEN not set in .env")
        sys.exit(1)
    if not email:
        print("ERROR: ULTRAHUMAN_USER_EMAIL not set in .env")
        sys.exit(1)
    
    return token, email


def fetch_metrics(date_str: str) -> dict:
    """Fetch metrics for a specific date."""
    token, email = get_credentials()
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    params = {
        "email": email,
        "date": date_str
    }
    
    response = requests.get(API_URL, headers=headers, params=params, timeout=30)
    
    if response.status_code == 401:
        print("ERROR: Invalid API token")
        sys.exit(1)
    elif response.status_code == 404:
        return None  # No data for this date
    elif response.status_code != 200:
        print(f"ERROR: API returned {response.status_code}")
        print(response.text)
        return None
    
    return response.json()


def extract_biometrics(api_response: dict, date_str: str) -> list:
    """
    Extract biometric readings from API response.
    
    Actual API response structure:
    {
        "data": {
            "metric_data": [
                {"type": "night_rhr", "object": {"avg": 67, "values": [...]}},
                {"type": "avg_sleep_hrv", "object": {"value": 65}},
                {"type": "recovery_index", "object": {"value": 78}},
                {"type": "movement_index", "object": {"value": 75}},
                {"type": "vo2_max", "object": {"value": 36}},
                {"type": "steps", "object": {"values": [...]}},
                {"type": "Sleep", "object": {...}},
                ...
            ]
        },
        "status": 200
    }
    """
    readings = []
    data = api_response.get("data", {})
    metric_data = data.get("metric_data", [])
    
    if not metric_data:
        return readings
    
    # Build lookup by type
    metrics = {m["type"]: m.get("object", {}) for m in metric_data}
    
    # Resting HR (from night_rhr)
    if "night_rhr" in metrics:
        obj = metrics["night_rhr"]
        # Use avg if available, otherwise latest value from values array
        rhr = obj.get("avg")
        if rhr is None and obj.get("values"):
            # Get most recent non-null value
            for v in reversed(obj["values"]):
                if v.get("value") is not None:
                    rhr = v["value"]
                    break
        if rhr is not None:
            readings.append({
                "date": date_str,
                "metric_type": "resting_hr",
                "value": rhr
            })
    
    # HRV (from avg_sleep_hrv)
    if "avg_sleep_hrv" in metrics:
        obj = metrics["avg_sleep_hrv"]
        hrv = obj.get("value")
        if hrv is not None:
            readings.append({
                "date": date_str,
                "metric_type": "hrv_morning",
                "value": hrv
            })
    
    # Recovery Index
    if "recovery_index" in metrics:
        obj = metrics["recovery_index"]
        value = obj.get("value")
        if value is not None:
            readings.append({
                "date": date_str,
                "metric_type": "recovery_index",
                "value": value
            })
    
    # Movement Index
    if "movement_index" in metrics:
        obj = metrics["movement_index"]
        value = obj.get("value")
        if value is not None:
            readings.append({
                "date": date_str,
                "metric_type": "movement_index",
                "value": value
            })
    
    # VO2 Max
    if "vo2_max" in metrics:
        obj = metrics["vo2_max"]
        value = obj.get("value")
        if value is not None:
            readings.append({
                "date": date_str,
                "metric_type": "vo2_max",
                "value": value
            })
    
    # Active Minutes
    if "active_minutes" in metrics:
        obj = metrics["active_minutes"]
        value = obj.get("value")
        if value is not None:
            readings.append({
                "date": date_str,
                "metric_type": "active_minutes",
                "value": value
            })
    
    # Steps (may have values array or direct value)
    if "steps" in metrics:
        obj = metrics["steps"]
        steps = obj.get("value")
        if steps is None and obj.get("values"):
            # Sum all step values for the day
            steps = sum(v.get("value", 0) or 0 for v in obj["values"])
        if steps:
            readings.append({
                "date": date_str,
                "metric_type": "steps",
                "value": steps
            })
    
    # Sleep data - structure varies, try to extract what we can
    if "Sleep" in metrics:
        obj = metrics["Sleep"]
        
        # Total sleep time
        total_min = obj.get("total_sleep_minutes") or obj.get("total_sleep") or obj.get("duration_minutes")
        if total_min is not None:
            readings.append({
                "date": date_str,
                "metric_type": "sleep_total_min",
                "value": total_min
            })
        
        # Deep sleep
        deep_min = obj.get("deep_sleep_minutes") or obj.get("deep_sleep")
        if deep_min is not None:
            readings.append({
                "date": date_str,
                "metric_type": "sleep_deep_min",
                "value": deep_min
            })
        
        # REM sleep
        rem_min = obj.get("rem_sleep_minutes") or obj.get("rem_sleep")
        if rem_min is not None:
            readings.append({
                "date": date_str,
                "metric_type": "sleep_rem_min",
                "value": rem_min
            })
        
        # Sleep score
        sleep_score = obj.get("sleep_score") or obj.get("score")
        if sleep_score is not None:
            readings.append({
                "date": date_str,
                "metric_type": "sleep_score",
                "value": sleep_score
            })
    
    # Temperature
    if "temp" in metrics:
        obj = metrics["temp"]
        # Look for skin temp deviation
        temp_dev = obj.get("skin_temp_deviation") or obj.get("deviation") or obj.get("value")
        if temp_dev is not None:
            readings.append({
                "date": date_str,
                "metric_type": "skin_temp_deviation",
                "value": temp_dev
            })
    
    # Sleep RHR (different from night_rhr)
    if "sleep_rhr" in metrics:
        obj = metrics["sleep_rhr"]
        value = obj.get("value")
        if value is not None:
            readings.append({
                "date": date_str,
                "metric_type": "sleep_rhr",
                "value": value
            })
    
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
    affected = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    
    return len(rows)


def test_connection():
    """Test API connection with today's date."""
    print("Testing Ultrahuman API connection...")
    token, email = get_credentials()
    print(f"  Email: {email}")
    print(f"  Token: {token[:20]}...{token[-10:]}")
    
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"  Fetching data for: {today}")
    
    try:
        response = fetch_metrics(today)
        if response is None:
            print("  No data returned (might be normal if no data for today yet)")
        else:
            print("  SUCCESS! Response:")
            print(json.dumps(response, indent=2))
    except Exception as e:
        print(f"  ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="Sync data from Ultrahuman API")
    parser.add_argument("--days", type=int, default=7, help="Days of history to fetch (default: 7)")
    parser.add_argument("--since", type=str, help="Fetch since date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't save")
    parser.add_argument("--test", action="store_true", help="Test API connection only")
    parser.add_argument("--raw", action="store_true", help="Show raw API responses")
    args = parser.parse_args()
    
    if args.test:
        test_connection()
        return
    
    # Calculate date range
    end_date = datetime.now()
    if args.since:
        start_date = datetime.strptime(args.since, "%Y-%m-%d")
    else:
        start_date = end_date - timedelta(days=args.days)
    
    print(f"Fetching Ultrahuman data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    all_readings = []
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"  {date_str}...", end=" ")
        
        try:
            response = fetch_metrics(date_str)
            
            if args.raw and response:
                print()
                print(json.dumps(response, indent=2))
            
            if response and response.get("status") == 200:
                readings = extract_biometrics(response, date_str)
                all_readings.extend(readings)
                print(f"{len(readings)} metrics")
            elif response is None:
                print("no data")
            else:
                print(f"error: {response.get('error', 'unknown')}")
        except Exception as e:
            print(f"error: {e}")
        
        current_date += timedelta(days=1)
    
    print(f"\nTotal: {len(all_readings)} readings from {len(set(r['date'] for r in all_readings))} days")
    
    if args.dry_run:
        print("\nDRY RUN - not saving to database")
        if all_readings:
            print("\nSample readings:")
            for r in all_readings[:10]:
                print(f"  {r['date']} {r['metric_type']}: {r['value']}")
    else:
        if all_readings:
            count = upsert_biometrics(all_readings)
            print(f"Upserted {count} readings to Postgres")
        else:
            print("No readings to save")
    
    print("Done")


if __name__ == "__main__":
    main()
