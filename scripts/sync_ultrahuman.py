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
import time
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
API_RATE_LIMIT_DELAY = 0.5  # seconds between API calls
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # exponential backoff base


def retry_with_backoff(func, *args, max_retries=MAX_RETRIES, **kwargs):
    """
    Retry a function with exponential backoff.
    Returns (result, success) tuple.
    """
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            return result, True
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                delay = RETRY_BASE_DELAY ** (attempt + 1)
                print(f"timeout, retrying in {delay}s...", end=" ")
                time.sleep(delay)
            else:
                return None, False
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = RETRY_BASE_DELAY ** (attempt + 1)
                print(f"error ({e}), retrying in {delay}s...", end=" ")
                time.sleep(delay)
            else:
                return None, False
    return None, False


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
    
    # Sleep data - nested structure
    if "Sleep" in metrics:
        obj = metrics["Sleep"]
        
        # Total sleep time - nested under total_sleep.minutes
        if "total_sleep" in obj and isinstance(obj["total_sleep"], dict):
            total_min = obj["total_sleep"].get("minutes")
            if total_min is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "sleep_total_min",
                    "value": total_min
                })
        
        # Deep sleep - nested under deep_sleep.minutes
        if "deep_sleep" in obj and isinstance(obj["deep_sleep"], dict):
            deep_min = obj["deep_sleep"].get("minutes")
            if deep_min is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "sleep_deep_min",
                    "value": deep_min
                })
        
        # REM sleep - nested under rem_sleep.minutes
        if "rem_sleep" in obj and isinstance(obj["rem_sleep"], dict):
            rem_min = obj["rem_sleep"].get("minutes")
            if rem_min is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "sleep_rem_min",
                    "value": rem_min
                })
        
        # Light sleep - nested under light_sleep.minutes
        if "light_sleep" in obj and isinstance(obj["light_sleep"], dict):
            light_min = obj["light_sleep"].get("minutes")
            if light_min is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "sleep_light_min",
                    "value": light_min
                })
        
        # Sleep score - nested under sleep_score.score
        if "sleep_score" in obj and isinstance(obj["sleep_score"], dict):
            score = obj["sleep_score"].get("score")
            if score is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "sleep_score",
                    "value": score
                })
        
        # Sleep efficiency - nested under sleep_efficiency.percentage
        if "sleep_efficiency" in obj and isinstance(obj["sleep_efficiency"], dict):
            efficiency = obj["sleep_efficiency"].get("percentage")
            if efficiency is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "sleep_efficiency",
                    "value": efficiency
                })
        
        # Awake time - can calculate from time_in_bed - total_sleep
        if "time_in_bed" in obj and isinstance(obj["time_in_bed"], dict):
            tib_min = obj["time_in_bed"].get("minutes")
            total_sleep_min = obj.get("total_sleep", {}).get("minutes")
            if tib_min is not None and total_sleep_min is not None:
                awake_min = tib_min - total_sleep_min
                if awake_min >= 0:
                    readings.append({
                        "date": date_str,
                        "metric_type": "sleep_awake_min",
                        "value": awake_min
                    })
        
        # SpO2 - nested under spo2.value
        if "spo2" in obj and isinstance(obj["spo2"], dict):
            spo2_val = obj["spo2"].get("value")
            if spo2_val is not None:
                readings.append({
                    "date": date_str,
                    "metric_type": "spo2",
                    "value": spo2_val
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
    # Filter out any readings where value is not a number
    rows = []
    for r in readings:
        val = r['value']
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            rows.append((r['date'], r['metric_type'], float(val), 'ultrahuman'))
        else:
            print(f"  Skipping {r['metric_type']} on {r['date']}: value is {type(val).__name__}, not number")
    
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


def extract_samples(api_response: dict) -> list:
    """
    Extract time-series samples from API response.
    
    Returns list of samples with:
    - sample_time: datetime
    - metric_type: hr, hrv, skin_temp, sleep_stage
    - value: numeric value (or None for sleep_stage)
    - text_value: text label (for sleep_stage)
    """
    samples = []
    data = api_response.get("data", {})
    metric_data = data.get("metric_data", [])
    
    if not metric_data:
        return samples
    
    # Build lookup by type
    metrics = {m["type"]: m.get("object", {}) for m in metric_data}
    
    # Heart rate time series
    if "hr" in metrics:
        obj = metrics["hr"]
        for v in obj.get("values", []):
            ts = v.get("timestamp")
            val = v.get("value")
            if ts and val is not None:
                samples.append({
                    "sample_time": datetime.fromtimestamp(ts),
                    "metric_type": "hr",
                    "value": val,
                    "text_value": None
                })
    
    # HRV time series
    if "hrv" in metrics:
        obj = metrics["hrv"]
        for v in obj.get("values", []):
            ts = v.get("timestamp")
            val = v.get("value")
            if ts and val is not None:
                samples.append({
                    "sample_time": datetime.fromtimestamp(ts),
                    "metric_type": "hrv",
                    "value": val,
                    "text_value": None
                })
    
    # Skin temperature time series
    if "temp" in metrics:
        obj = metrics["temp"]
        for v in obj.get("values", []):
            ts = v.get("timestamp")
            val = v.get("value")
            if ts and val is not None:
                samples.append({
                    "sample_time": datetime.fromtimestamp(ts),
                    "metric_type": "skin_temp",
                    "value": val,
                    "text_value": None
                })
    
    # Night RHR time series (during sleep)
    if "night_rhr" in metrics:
        obj = metrics["night_rhr"]
        for v in obj.get("values", []):
            ts = v.get("timestamp")
            val = v.get("value")
            if ts and val is not None:
                samples.append({
                    "sample_time": datetime.fromtimestamp(ts),
                    "metric_type": "night_rhr",
                    "value": val,
                    "text_value": None
                })
    
    # Sleep stages from sleep_cycles in Sleep object
    if "Sleep" in metrics:
        sleep_obj = metrics["Sleep"]
        sleep_cycles = sleep_obj.get("sleep_cycles", {})
        for cycle in sleep_cycles.get("cycles", []):
            start_ts = cycle.get("startTime")
            cycle_type = cycle.get("cycleType")
            if start_ts and cycle_type:
                # Map cycle types to stage names
                stage_map = {
                    "light_sleep": "LIGHT",
                    "deep_sleep": "DEEP",
                    "rem_sleep": "REM",
                    "awake": "AWAKE",
                    "none": None,
                    "complete": None,
                    "partial": None
                }
                stage = stage_map.get(cycle_type)
                if stage:
                    samples.append({
                        "sample_time": datetime.fromtimestamp(start_ts),
                        "metric_type": "sleep_stage",
                        "value": None,
                        "text_value": stage
                    })
    
    return samples


def upsert_samples(samples: list):
    """
    Insert or update time-series samples in biometric_samples table.
    """
    if not samples:
        return 0
    
    import psycopg2
    from psycopg2.extras import execute_values
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # Dedupe by (sample_time, metric_type) - keep last occurrence
    seen = {}
    for s in samples:
        key = (s['sample_time'], s['metric_type'])
        seen[key] = s
    deduped = list(seen.values())
    
    # Prepare rows: (sample_time, metric_type, value, text_value, source)
    rows = []
    for s in deduped:
        val = s['value']
        # Convert value to float if numeric, else None
        if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
            val = float(val)
        else:
            val = None
        rows.append((
            s['sample_time'],
            s['metric_type'],
            val,
            s.get('text_value'),
            'ultrahuman'
        ))
    
    # Upsert
    sql = """
    INSERT INTO biometric_samples (sample_time, metric_type, value, text_value, source)
    VALUES %s
    ON CONFLICT (sample_time, metric_type, source) DO UPDATE SET
        value = EXCLUDED.value,
        text_value = EXCLUDED.text_value,
        imported_at = NOW()
    """
    
    execute_values(cur, sql, rows)
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
    all_samples = []
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"  {date_str}...", end=" ")
        
        try:
            response, success = retry_with_backoff(fetch_metrics, date_str)
            
            if not success:
                print("failed after retries")
                current_date += timedelta(days=1)
                time.sleep(API_RATE_LIMIT_DELAY)
                continue
            
            if args.raw and response:
                print()
                print(json.dumps(response, indent=2))
            
            if response and response.get("status") == 200:
                readings = extract_biometrics(response, date_str)
                samples = extract_samples(response)
                all_readings.extend(readings)
                all_samples.extend(samples)
                print(f"{len(readings)} metrics, {len(samples)} samples")
            elif response is None:
                print("no data")
            else:
                print(f"error: {response.get('error', 'unknown')}")
        except Exception as e:
            print(f"error: {e}")
        
        current_date += timedelta(days=1)
        
        # Rate limit: pause between API calls
        if current_date <= end_date:
            time.sleep(API_RATE_LIMIT_DELAY)
    
    print(f"\nTotal: {len(all_readings)} daily readings, {len(all_samples)} time-series samples")
    
    if args.dry_run:
        print("\nDRY RUN - not saving to database")
        if all_readings:
            print("\nSample daily readings:")
            for r in all_readings[:10]:
                print(f"  {r['date']} {r['metric_type']}: {r['value']}")
        if all_samples:
            print("\nSample time-series:")
            for s in all_samples[:10]:
                print(f"  {s['sample_time']} {s['metric_type']}: {s['value'] or s['text_value']}")
    else:
        if all_readings:
            count = upsert_biometrics(all_readings)
            print(f"Upserted {count} daily readings to biometric_readings")
        if all_samples:
            count = upsert_samples(all_samples)
            print(f"Upserted {count} samples to biometric_samples")
    
    print("Done")


if __name__ == "__main__":
    main()
