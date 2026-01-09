#!/usr/bin/env python3
"""
Polar AccessLink API v3 → Postgres Sync

Fetches training sessions from Polar API and writes to polar_sessions/hr_samples tables.
Uses OAuth2 with refresh token for automated daily pulls.

Environment Variables Required:
  POLAR_CLIENT_ID      - OAuth2 client ID from admin.polaraccesslink.com
  POLAR_CLIENT_SECRET  - OAuth2 client secret
  POLAR_REFRESH_TOKEN  - Stored refresh token (from initial OAuth flow)
  
Optional:
  POLAR_ACCESS_TOKEN   - Current access token (auto-refreshed if expired)
  POLAR_USER_ID        - Polar user ID (saved during setup)
  DATABASE_URI         - Postgres connection (defaults to local)

Usage:
  # First-time setup (interactive OAuth flow):
  python polar_api.py --setup
  
  # Daily sync (automated):
  python polar_api.py                    # Sync last 7 days
  python polar_api.py --days 30          # Sync last 30 days (max API returns)
  python polar_api.py --from 2026-01-01  # Sync from specific date
  python polar_api.py --dry-run          # Preview without writing

Scopes: accesslink.read_all
API: v3 (https://www.polar.com/accesslink-api/)
"""

import os
import sys
import json
import argparse
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
import base64

import requests
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv, set_key

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

# Polar API endpoints
AUTH_URL = "https://flow.polar.com/oauth2/authorization"  # v3 uses flow.polar.com
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"        # Token endpoint per docs
API_BASE = "https://www.polaraccesslink.com/v3"              # v3 API base

# Scopes we need for training data
SCOPES = "accesslink.read_all"

# Database
PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def get_credentials():
    """Load OAuth credentials from environment."""
    client_id = os.environ.get("POLAR_CLIENT_ID")
    client_secret = os.environ.get("POLAR_CLIENT_SECRET")
    redirect_uri = os.environ.get("POLAR_REDIRECT_URI", "http://localhost:9876/callback")
    
    if not client_id or not client_secret:
        raise ValueError(
            "Missing Polar credentials. Set in .env:\n"
            "  POLAR_CLIENT_ID=your_client_id\n"
            "  POLAR_CLIENT_SECRET=your_secret\n"
        )
    return client_id, client_secret, redirect_uri


def get_tokens():
    """Load stored tokens from environment."""
    return {
        "access_token": os.environ.get("POLAR_ACCESS_TOKEN"),
        "refresh_token": os.environ.get("POLAR_REFRESH_TOKEN"),
    }


def save_tokens(access_token: str, refresh_token: str, user_id: str = None):
    """Save tokens to .env file."""
    set_key(ENV_FILE, "POLAR_ACCESS_TOKEN", access_token)
    set_key(ENV_FILE, "POLAR_REFRESH_TOKEN", refresh_token)
    if user_id:
        set_key(ENV_FILE, "POLAR_USER_ID", str(user_id))
        os.environ["POLAR_USER_ID"] = str(user_id)
    # Also update current environment
    os.environ["POLAR_ACCESS_TOKEN"] = access_token
    os.environ["POLAR_REFRESH_TOKEN"] = refresh_token
    print(f"  Tokens saved to {ENV_FILE}")


def refresh_access_token() -> str:
    """Use refresh token to get new access token."""
    client_id, client_secret, _ = get_credentials()
    tokens = get_tokens()
    
    if not tokens["refresh_token"]:
        raise ValueError("No refresh token. Run --setup first.")
    
    # Basic auth header
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=30,
    )
    
    if response.status_code != 200:
        raise ValueError(f"Token refresh failed: {response.status_code} - {response.text}")
    
    data = response.json()
    save_tokens(data["access_token"], data["refresh_token"])
    return data["access_token"]


def get_valid_access_token() -> str:
    """Get a valid access token, refreshing if needed."""
    tokens = get_tokens()
    
    if not tokens["access_token"]:
        print("No access token, refreshing...")
        return refresh_access_token()
    
    # Try the current token - v3/exercises works with Bearer token
    response = requests.get(
        f"{API_BASE}/exercises",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=10,
    )
    
    if response.status_code == 401:
        print("Access token expired, refreshing...")
        return refresh_access_token()
    
    return tokens["access_token"]


# --- OAuth Setup Flow ---

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to capture OAuth callback."""
    
    auth_code = None
    
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body>
                <h1>Authorization successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """)
        elif "error" in params:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error = params.get("error", ["unknown"])[0]
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def run_oauth_setup():
    """Interactive OAuth2 authorization flow."""
    client_id, client_secret, redirect_uri = get_credentials()
    
    print("=" * 60)
    print("Polar AccessLink OAuth Setup")
    print("=" * 60)
    print()
    print("This will open your browser to authorize Arnold to access")
    print("your Polar training data.")
    print()
    
    # Build authorization URL
    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": redirect_uri,
    }
    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"
    
    print(f"Opening: {auth_url}\n")
    webbrowser.open(auth_url)
    
    # Start local server to catch callback
    parsed_redirect = urlparse(redirect_uri)
    port = parsed_redirect.port or 8888
    
    print(f"Waiting for OAuth callback on port {port}...")
    server = HTTPServer(("localhost", port), OAuthCallbackHandler)
    server.handle_request()  # Handle single request
    
    if not OAuthCallbackHandler.auth_code:
        print("ERROR: No authorization code received")
        sys.exit(1)
    
    auth_code = OAuthCallbackHandler.auth_code
    print(f"\nAuthorization code received!")
    
    # Exchange code for tokens
    print("Exchanging code for tokens...")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    
    if response.status_code != 200:
        print(f"ERROR: Token exchange failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    print(f"  Token response keys: {data.keys()}")
    
    user_id = data.get("x_user_id")
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")  # May not exist in v3
    
    print(f"  User ID: {user_id}")
    print(f"  Access token: {access_token[:20] if access_token else 'None'}...")
    print(f"  Refresh token: {'Yes' if refresh_token else 'No'}")
    
    if not access_token:
        print("ERROR: No access token in response")
        sys.exit(1)
    
    save_tokens(access_token, refresh_token or "", user_id)
    
    # Register user with AccessLink (required for first-time access)
    if user_id:
        print(f"\nRegistering user {user_id} with AccessLink...")
        reg_response = requests.post(
            f"{API_BASE}/users",
            headers={
                "Authorization": f"Bearer {data['access_token']}",
                "Content-Type": "application/json",
            },
            json={"member-id": f"arnold-{user_id}"},
            timeout=30,
        )
        if reg_response.status_code == 200:
            print("  User registered successfully")
        elif reg_response.status_code == 409:
            print("  User already registered (OK)")
        else:
            print(f"  Registration note: {reg_response.status_code} - {reg_response.text}")
    
    print()
    print("=" * 60)
    print("SUCCESS! Polar API is now configured.")
    print("=" * 60)
    print()
    print("You can now run:")
    print("  python polar_api.py --days 30   # Sync last 30 days")
    print("  python polar_api.py             # Daily sync (last 7 days)")


# --- Training Session Sync ---

def _iso_utc_midnight(d: date) -> str:
    """ISO 8601 datetime at midnight UTC with explicit offset (Polar requires +00:00, not Z)."""
    return f"{d.isoformat()}T00:00:00+00:00"


def fetch_training_sessions(access_token: str, from_date: date, to_date: date) -> list:
    """Fetch training sessions from Polar API v3.
    
    Uses /v3/exercises which returns last 30 days of exercises.
    We filter client-side by date range.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    # v3 API doesn't take date params - returns last 30 days
    # We filter client-side
    params = {
        "samples": "true",
        "zones": "true",
    }

    print(f"  Fetching exercises from Polar API v3...")

    response = requests.get(
        f"{API_BASE}/exercises",
        headers=headers,
        params=params,
        timeout=60,
    )

    if response.status_code == 403:
        raise ValueError("Access forbidden - check scopes or re-authorize")

    if response.status_code != 200:
        print(f"  API error: {response.status_code} - {response.text}")
        print(f"  Request URL: {response.request.url}")
        response.raise_for_status()

    exercises = response.json()
    if not exercises:
        return []

    # Filter by date range client-side
    filtered = []
    for ex in exercises:
        start_time = ex.get("start_time", "")
        if not start_time:
            continue
        
        exercise_date = date.fromisoformat(start_time[:10])
        if from_date <= exercise_date <= to_date:
            filtered.append(ex)
    
    print(f"  Found {len(exercises)} total exercises, {len(filtered)} in date range")
    return filtered


def parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration (PT4050.564S or PT1H30M45S) to seconds."""
    import re
    if not duration_str:
        return 0
    
    # Handle simple seconds format
    match = re.match(r'PT(\d+(?:\.\d+)?)S', duration_str)
    if match:
        return int(float(match.group(1)))
    
    # Handle complex format
    total = 0
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    seconds = re.search(r'(\d+(?:\.\d+)?)S', duration_str)
    if hours:
        total += int(hours.group(1)) * 3600
    if minutes:
        total += int(minutes.group(1)) * 60
    if seconds:
        total += int(float(seconds.group(1)))
    return total


def parse_session(session_data: dict) -> dict:
    """Parse an exercise from v3 API response.
    
    v3 format has different field names and structure than v4.
    """
    hr_data = session_data.get("heart_rate", {})
    
    # Parse HR zones - v3 uses different keys
    hr_zones = {}
    zone_bounds = {}
    for zone in session_data.get("heart_rate_zones", []):
        idx = zone.get("index", 0)
        hr_zones[f"zone_{idx}_seconds"] = parse_iso_duration(zone.get("in-zone", "PT0S"))
        zone_bounds[f"zone_{idx}_lower"] = zone.get("lower-limit")
        zone_bounds[f"zone_{idx}_upper"] = zone.get("upper-limit")
    
    # v3 doesn't have physicalInformationSnapshot in same way
    start_time = session_data.get("start_time")
    duration_seconds = parse_iso_duration(session_data.get("duration", "PT0S"))
    
    # Calculate stop_time from start + duration
    stop_time = None
    if start_time and duration_seconds:
        start_dt = datetime.fromisoformat(start_time)
        stop_time = (start_dt + timedelta(seconds=duration_seconds)).isoformat()
    
    session = {
        "polar_session_id": str(session_data.get("id", "")),
        "start_time": start_time,
        "stop_time": stop_time,
        "duration_seconds": duration_seconds,
        "sport_type": session_data.get("sport") or session_data.get("detailed_sport_info"),
        "avg_hr": hr_data.get("average"),
        "max_hr": hr_data.get("maximum"),
        "min_hr": None,  # v3 doesn't provide min
        "calories": session_data.get("calories"),
        "zone_1_seconds": hr_zones.get("zone_1_seconds", 0),
        "zone_2_seconds": hr_zones.get("zone_2_seconds", 0),
        "zone_3_seconds": hr_zones.get("zone_3_seconds", 0),
        "zone_4_seconds": hr_zones.get("zone_4_seconds", 0),
        "zone_5_seconds": hr_zones.get("zone_5_seconds", 0),
        "zone_1_lower": zone_bounds.get("zone_1_lower"),
        "zone_1_upper": zone_bounds.get("zone_1_upper"),
        "zone_2_lower": zone_bounds.get("zone_2_lower"),
        "zone_2_upper": zone_bounds.get("zone_2_upper"),
        "zone_3_lower": zone_bounds.get("zone_3_lower"),
        "zone_3_upper": zone_bounds.get("zone_3_upper"),
        "zone_4_lower": zone_bounds.get("zone_4_lower"),
        "zone_4_upper": zone_bounds.get("zone_4_upper"),
        "zone_5_lower": zone_bounds.get("zone_5_lower"),
        "zone_5_upper": zone_bounds.get("zone_5_upper"),
        "vo2max": None,
        "resting_hr": None,
        "max_hr_setting": None,
        "ftp": None,
        "weight_kg": None,
        "timezone_offset": session_data.get("start_time_utc_offset"),
        "feeling": None,
        "note": None,
    }
    
    # Extract HR samples - v3 format is comma-separated values
    # sample_type "0" = HR (based on actual API response), recording_rate is seconds between samples
    samples = []
    for sample_block in session_data.get("samples", []):
        sample_type = sample_block.get("sample_type")  # underscore, not hyphen
        if sample_type == 0:  # HR samples (type 0 as int)
            recording_rate = sample_block.get("recording_rate", 1)  # underscore
            data_str = sample_block.get("data", "")
            if data_str:
                values = [int(v) for v in data_str.split(",") if v]
                start_time_str = session_data.get("start_time", "")
                if start_time_str:
                    base_dt = datetime.fromisoformat(start_time_str)
                    for i, hr_value in enumerate(values):
                        if hr_value > 0:  # Skip 0 values (no reading)
                            sample_time = base_dt + timedelta(seconds=i * recording_rate)
                            samples.append({
                                "sample_time": sample_time.isoformat(),
                                "hr_value": hr_value,
                            })
    
    return {"session": session, "samples": samples}


def upsert_session(cur, session: dict) -> int:
    """Insert or update a training session, return session ID."""
    # Check if exists
    cur.execute(
        "SELECT id FROM polar_sessions WHERE polar_session_id = %s",
        (session["polar_session_id"],)
    )
    existing = cur.fetchone()
    
    if existing:
        return existing[0]  # Already imported
    
    cur.execute("""
        INSERT INTO polar_sessions (
            polar_session_id, start_time, stop_time, duration_seconds, sport_type,
            avg_hr, max_hr, min_hr, calories,
            zone_1_seconds, zone_2_seconds, zone_3_seconds, zone_4_seconds, zone_5_seconds,
            zone_1_lower, zone_1_upper, zone_2_lower, zone_2_upper,
            zone_3_lower, zone_3_upper, zone_4_lower, zone_4_upper,
            zone_5_lower, zone_5_upper,
            vo2max, resting_hr, max_hr_setting, ftp, weight_kg,
            timezone_offset, feeling, note
        ) VALUES (
            %(polar_session_id)s, %(start_time)s, %(stop_time)s, %(duration_seconds)s, %(sport_type)s,
            %(avg_hr)s, %(max_hr)s, %(min_hr)s, %(calories)s,
            %(zone_1_seconds)s, %(zone_2_seconds)s, %(zone_3_seconds)s, %(zone_4_seconds)s, %(zone_5_seconds)s,
            %(zone_1_lower)s, %(zone_1_upper)s, %(zone_2_lower)s, %(zone_2_upper)s,
            %(zone_3_lower)s, %(zone_3_upper)s, %(zone_4_lower)s, %(zone_4_upper)s,
            %(zone_5_lower)s, %(zone_5_upper)s,
            %(vo2max)s, %(resting_hr)s, %(max_hr_setting)s, %(ftp)s, %(weight_kg)s,
            %(timezone_offset)s, %(feeling)s, %(note)s
        ) RETURNING id
    """, session)
    
    return cur.fetchone()[0]


def sync_sessions(from_date: date, to_date: date, dry_run: bool = False) -> dict:
    """Sync training sessions from Polar API to Postgres."""
    access_token = get_valid_access_token()
    
    print(f"Fetching sessions from {from_date} to {to_date}...")
    sessions = fetch_training_sessions(access_token, from_date, to_date)
    print(f"  Found {len(sessions)} sessions")
    
    if not sessions:
        return {"sessions_imported": 0, "samples_imported": 0, "skipped": 0}
    
    if dry_run:
        for ex in sessions:
            sport = ex.get("sport") or ex.get("detailed_sport_info") or "unknown"
            start = ex.get("start_time", "unknown")[:10]
            print(f"  - {start}: {sport}")
        return {"sessions_imported": len(sessions), "samples_imported": 0, "skipped": 0, "dry_run": True}
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    imported = 0
    skipped = 0
    total_samples = 0
    
    for session_data in sessions:
        parsed = parse_session(session_data)
        if not parsed:
            continue
        
        session = parsed["session"]
        samples = parsed["samples"]
        
        # Check if already exists
        cur.execute(
            "SELECT id FROM polar_sessions WHERE polar_session_id = %s",
            (session["polar_session_id"],)
        )
        if cur.fetchone():
            skipped += 1
            continue
        
        session_id = upsert_session(cur, session)
        imported += 1
        
        # Insert HR samples
        if samples:
            sample_data = [
                (session_id, s["sample_time"], s["hr_value"])
                for s in samples
            ]
            execute_batch(
                cur,
                "INSERT INTO hr_samples (session_id, sample_time, hr_value) VALUES (%s, %s, %s)",
                sample_data,
                page_size=1000,
            )
            total_samples += len(samples)
        
        sport = session.get("sport_type", "unknown")
        print(f"  ✓ {session['start_time'][:10]}: {sport} ({len(samples)} HR samples)")
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"sessions_imported": imported, "samples_imported": total_samples, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description="Polar AccessLink API Sync")
    parser.add_argument("--setup", action="store_true", help="Run OAuth setup flow")
    parser.add_argument("--days", type=int, default=7, help="Days to sync (default: 7)")
    parser.add_argument("--from", dest="from_date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    
    if args.setup:
        run_oauth_setup()
        return
    
    # Determine date range
    today = date.today()
    
    if args.from_date:
        from_date = date.fromisoformat(args.from_date)
        to_date = date.fromisoformat(args.to_date) if args.to_date else today
    else:
        to_date = today
        from_date = today - timedelta(days=args.days)
    
    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode}Polar API → Postgres: {from_date} to {to_date}")
    print()
    
    result = sync_sessions(from_date, to_date, dry_run=args.dry_run)
    
    print()
    print(f"{'Would import' if args.dry_run else 'Imported'}: "
          f"{result['sessions_imported']} sessions, {result['samples_imported']} HR samples")
    if result.get("skipped"):
        print(f"Skipped (already exist): {result['skipped']}")


if __name__ == "__main__":
    main()
