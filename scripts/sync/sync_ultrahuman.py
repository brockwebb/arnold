#!/usr/bin/env python3
"""
Ultrahuman API Sync Script

Fetches health metrics from Ultrahuman Partner API and saves to raw data lake.

Environment Variables Required:
  ULTRAHUMAN_AUTH_TOKEN - API authorization token
  ULTRAHUMAN_USER_EMAIL - Email associated with Ultrahuman account

API Reference: https://vision.ultrahuman.com/developer/docs
Base URL: https://partner.ultrahuman.com/api/v1

Usage:
  python sync_ultrahuman.py                    # Sync last 7 days
  python sync_ultrahuman.py --days 30          # Sync last 30 days
  python sync_ultrahuman.py --start 2025-12-01 # Sync from date to today
  python sync_ultrahuman.py --start 2025-12-01 --end 2025-12-31  # Date range
"""

import os
import json
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import requests

# Configuration
BASE_URL = "https://partner.ultrahuman.com/api/v1"
RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "ultrahuman"

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


def fetch_metrics(token: str, email: str, target_date: date) -> dict:
    """
    Fetch health metrics for a single date.
    
    Returns the raw API response as a dict.
    """
    headers = {
        "Authorization": f"Bearer {token}",
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


def fetch_date_range(
    token: str, 
    email: str, 
    start_date: date, 
    end_date: date
) -> list[dict]:
    """
    Fetch metrics for a date range.
    
    Returns list of daily records with date included.
    """
    records = []
    current = start_date
    
    while current <= end_date:
        try:
            data = fetch_metrics(token, email, current)
            data["_sync_date"] = current.isoformat()
            data["_synced_at"] = datetime.utcnow().isoformat()
            records.append(data)
            print(f"  ✓ {current}")
        except requests.HTTPError as e:
            print(f"  ✗ {current}: {e}")
        except Exception as e:
            print(f"  ✗ {current}: {e}")
        
        current += timedelta(days=1)
    
    return records


def save_sync(records: list[dict], sync_date: date) -> Path:
    """Save sync results to raw directory."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    filename = f"api_sync_{sync_date.isoformat()}.json"
    filepath = RAW_DIR / filename
    
    with open(filepath, "w") as f:
        json.dump({
            "sync_date": sync_date.isoformat(),
            "record_count": len(records),
            "records": records
        }, f, indent=2)
    
    print(f"\nSaved {len(records)} records to {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Sync Ultrahuman metrics")
    parser.add_argument("--days", type=int, default=7, 
                        help="Number of days to sync (default: 7)")
    parser.add_argument("--start", type=str, 
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, 
                        help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be synced without fetching")
    
    args = parser.parse_args()
    
    # Determine date range
    if args.start:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end) if args.end else date.today()
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days - 1)
    
    print(f"Ultrahuman Sync: {start_date} → {end_date}")
    print(f"  ({(end_date - start_date).days + 1} days)")
    
    if args.dry_run:
        print("\n[DRY RUN] Would fetch these dates:")
        current = start_date
        while current <= end_date:
            print(f"  {current}")
            current += timedelta(days=1)
        return
    
    # Load credentials
    token, email = get_credentials()
    print(f"  User: {email}")
    
    # Fetch data
    print("\nFetching...")
    records = fetch_date_range(token, email, start_date, end_date)
    
    # Save
    if records:
        save_sync(records, date.today())
    else:
        print("\nNo records fetched.")


if __name__ == "__main__":
    main()
