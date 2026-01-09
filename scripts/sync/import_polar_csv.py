#!/usr/bin/env python3
"""
Import Polar Flow CSV exports to Postgres.

Usage:
  python import_polar_csv.py /path/to/file.csv
  python import_polar_csv.py /path/to/folder/   # Import all CSVs in folder
  python import_polar_csv.py --dry-run /path/to/file.csv
"""

import os
import sys
import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch

PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def parse_duration(duration_str: str) -> int:
    """Parse HH:MM:SS to seconds."""
    if not duration_str:
        return 0
    parts = duration_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0])


def parse_polar_csv(filepath: Path) -> dict:
    """Parse a Polar Flow CSV export."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Row 1: headers, Row 2: values
    headers = [h.strip() for h in lines[0].split(',')]
    values = [v.strip() for v in lines[1].split(',')]
    summary = dict(zip(headers, values))
    
    # Generate unique ID from filename
    filename = filepath.stem  # e.g., Brock_Webb_2026-01-03_09-51-43
    session_id = hashlib.md5(filename.encode()).hexdigest()[:12]
    
    # Parse date and start time
    date_str = summary.get("Date", "")  # 03-01-2026 (DD-MM-YYYY)
    time_str = summary.get("Start time", "")  # 09:51:43
    
    # Convert DD-MM-YYYY to YYYY-MM-DD
    if date_str:
        parts = date_str.split("-")
        if len(parts) == 3:
            date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
    
    start_time = f"{date_str}T{time_str}" if date_str and time_str else None
    duration_secs = parse_duration(summary.get("Duration", ""))
    
    # Calculate stop_time
    stop_time = None
    if start_time and duration_secs:
        base_dt = datetime.fromisoformat(start_time)
        stop_time = (base_dt + timedelta(seconds=duration_secs)).isoformat()
    
    # Parse HR samples (starting at row 4, 0-indexed = row 3)
    samples = []
    if start_time:
        base_dt = datetime.fromisoformat(start_time)
        for line in lines[3:]:
            parts = line.strip().split(',')
            if len(parts) >= 3:
                time_offset = parts[1].strip()  # 00:00:05
                hr_str = parts[2].strip()
                if time_offset and hr_str and hr_str.isdigit():
                    hr = int(hr_str)
                    if hr > 0:
                        offset_secs = parse_duration(time_offset)
                        sample_time = base_dt + timedelta(seconds=offset_secs)
                        samples.append({
                            "sample_time": sample_time.isoformat(),
                            "hr_value": hr,
                        })
    
    # Calculate avg/max HR from samples
    hr_values = [s["hr_value"] for s in samples]
    avg_hr = int(sum(hr_values) / len(hr_values)) if hr_values else None
    max_hr = max(hr_values) if hr_values else None
    min_hr = min(hr_values) if hr_values else None
    
    # Use summary avg_hr if available
    if summary.get("Average heart rate (bpm)"):
        avg_hr = int(summary["Average heart rate (bpm)"])
    
    session = {
        "polar_session_id": f"csv-{session_id}",
        "start_time": start_time,
        "stop_time": stop_time,
        "duration_seconds": duration_secs,
        "sport_type": summary.get("Sport", "UNKNOWN"),
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "min_hr": min_hr,
        "calories": int(summary["Calories"]) if summary.get("Calories") else None,
        "zone_1_seconds": 0,
        "zone_2_seconds": 0,
        "zone_3_seconds": 0,
        "zone_4_seconds": 0,
        "zone_5_seconds": 0,
        "zone_1_lower": None, "zone_1_upper": None,
        "zone_2_lower": None, "zone_2_upper": None,
        "zone_3_lower": None, "zone_3_upper": None,
        "zone_4_lower": None, "zone_4_upper": None,
        "zone_5_lower": None, "zone_5_upper": None,
        "vo2max": int(summary["VO2max"]) if summary.get("VO2max") else None,
        "resting_hr": int(summary["HR sit"]) if summary.get("HR sit") else None,
        "max_hr_setting": int(summary["HR max"]) if summary.get("HR max") else None,
        "ftp": None,
        "weight_kg": float(summary["Weight (lbs)"]) * 0.453592 if summary.get("Weight (lbs)") else None,
        "timezone_offset": None,
        "feeling": None,
        "note": summary.get("Notes"),
    }
    
    return {"session": session, "samples": samples, "filename": filepath.name}


def import_session(cur, session: dict, samples: list) -> tuple:
    """Import session and samples. Returns (imported, skipped)."""
    # Check if exists
    cur.execute(
        "SELECT id FROM polar_sessions WHERE polar_session_id = %s",
        (session["polar_session_id"],)
    )
    if cur.fetchone():
        return (0, 1)  # Already exists
    
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
    
    session_id = cur.fetchone()[0]
    
    # Insert samples
    if samples:
        sample_data = [(session_id, s["sample_time"], s["hr_value"]) for s in samples]
        execute_batch(
            cur,
            "INSERT INTO hr_samples (session_id, sample_time, hr_value) VALUES (%s, %s, %s)",
            sample_data,
            page_size=1000,
        )
    
    return (1, 0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import Polar CSV exports")
    parser.add_argument("path", help="CSV file or folder")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    
    path = Path(args.path)
    
    # Collect files
    if path.is_dir():
        files = sorted(path.glob("*.CSV")) + sorted(path.glob("*.csv"))
    else:
        files = [path]
    
    if not files:
        print("No CSV files found")
        return
    
    print(f"Found {len(files)} CSV file(s)")
    
    # Parse all
    parsed = []
    for f in files:
        try:
            data = parse_polar_csv(f)
            parsed.append(data)
            session = data["session"]
            samples = data["samples"]
            print(f"  {f.name}: {session['sport_type']} - {session['start_time'][:10]} "
                  f"({session['duration_seconds']//60}min, {len(samples)} HR samples)")
        except Exception as e:
            print(f"  {f.name}: ERROR - {e}")
    
    if args.dry_run:
        print(f"\n[DRY RUN] Would import {len(parsed)} sessions")
        return
    
    # Import
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    imported = 0
    skipped = 0
    total_samples = 0
    
    for data in parsed:
        imp, skip = import_session(cur, data["session"], data["samples"])
        imported += imp
        skipped += skip
        if imp:
            total_samples += len(data["samples"])
            print(f"  ✓ {data['filename']}")
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\nImported: {imported} sessions, {total_samples} HR samples")
    if skipped:
        print(f"Skipped (already exist): {skipped}")


if __name__ == "__main__":
    main()
