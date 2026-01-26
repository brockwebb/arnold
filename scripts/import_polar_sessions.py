#!/usr/bin/env python3
"""
Import Polar training session data into Postgres.

Usage:
    python scripts/import_polar_sessions.py /path/to/polar-export-folder

Expects folder containing:
    - training-session-*.json files
    - Optionally: calendar-items-*.json for weight data
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_batch


# Database connection - use env var or default to local brock user
import os
PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration (PT4050.564S) to seconds."""
    if not duration_str:
        return 0
    match = re.match(r'PT(\d+(?:\.\d+)?)S', duration_str)
    if match:
        return int(float(match.group(1)))
    # Handle more complex durations like PT1H30M45S
    total_seconds = 0
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    seconds = re.search(r'(\d+(?:\.\d+)?)S', duration_str)
    if hours:
        total_seconds += int(hours.group(1)) * 3600
    if minutes:
        total_seconds += int(minutes.group(1)) * 60
    if seconds:
        total_seconds += int(float(seconds.group(1)))
    return total_seconds


def parse_datetime(dt_str: str, tz_offset_minutes: int = 0) -> datetime:
    """Parse datetime string and apply timezone offset."""
    # Handle formats like "2026-01-03T09:51:43.850"
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return dt


def extract_session_id(filename: str) -> str:
    """Extract session ID from filename like training-session-2026-01-03-8251681144-..."""
    # Pattern: training-session-YYYY-MM-DD-{polar_id}-{uuid}.json
    match = re.search(r'training-session-\d{4}-\d{2}-\d{2}-(\d+)-', filename)
    if match:
        return match.group(1)
    return filename


def parse_training_session(filepath: Path) -> Optional[dict]:
    """Parse a training session JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    if not data.get('exercises'):
        print(f"  Skipping {filepath.name}: no exercises")
        return None
    
    exercise = data['exercises'][0]  # Primary exercise
    hr_zones = {}
    zone_bounds = {}
    
    if 'zones' in exercise and 'heart_rate' in exercise['zones']:
        for zone in exercise['zones']['heart_rate']:
            idx = zone['zoneIndex']
            hr_zones[f'zone_{idx}_seconds'] = parse_iso_duration(zone.get('inZone', 'PT0S'))
            zone_bounds[f'zone_{idx}_lower'] = zone.get('lowerLimit')
            zone_bounds[f'zone_{idx}_upper'] = zone.get('higherLimit')
    
    phys = data.get('physicalInformationSnapshot', {})
    hr_data = exercise.get('heartRate', {})
    
    session = {
        'polar_session_id': extract_session_id(filepath.name),
        'start_time': parse_datetime(data['startTime']),
        'stop_time': parse_datetime(data['stopTime']),
        'duration_seconds': parse_iso_duration(data.get('duration', 'PT0S')),
        'sport_type': exercise.get('sport'),
        'avg_hr': hr_data.get('avg'),
        'max_hr': hr_data.get('max'),
        'min_hr': hr_data.get('min'),
        'calories': exercise.get('kiloCalories') or data.get('kiloCalories'),
        'zone_1_seconds': hr_zones.get('zone_1_seconds', 0),
        'zone_2_seconds': hr_zones.get('zone_2_seconds', 0),
        'zone_3_seconds': hr_zones.get('zone_3_seconds', 0),
        'zone_4_seconds': hr_zones.get('zone_4_seconds', 0),
        'zone_5_seconds': hr_zones.get('zone_5_seconds', 0),
        'zone_1_lower': zone_bounds.get('zone_1_lower'),
        'zone_1_upper': zone_bounds.get('zone_1_upper'),
        'zone_2_lower': zone_bounds.get('zone_2_lower'),
        'zone_2_upper': zone_bounds.get('zone_2_upper'),
        'zone_3_lower': zone_bounds.get('zone_3_lower'),
        'zone_3_upper': zone_bounds.get('zone_3_upper'),
        'zone_4_lower': zone_bounds.get('zone_4_lower'),
        'zone_4_upper': zone_bounds.get('zone_4_upper'),
        'zone_5_lower': zone_bounds.get('zone_5_lower'),
        'zone_5_upper': zone_bounds.get('zone_5_upper'),
        'vo2max': phys.get('vo2Max'),
        'resting_hr': phys.get('restingHeartRate'),
        'max_hr_setting': phys.get('maximumHeartRate'),
        'ftp': phys.get('functionalThresholdPower'),
        'weight_kg': phys.get('weight, kg'),
        'timezone_offset': data.get('timeZoneOffset'),
        'feeling': float(data['feeling']) if data.get('feeling') else None,
        'note': data.get('note') or None,
    }
    
    # Extract HR samples (skip dropouts where value is missing)
    samples = []
    if 'samples' in exercise and 'heartRate' in exercise['samples']:
        for sample in exercise['samples']['heartRate']:
            if 'value' in sample:  # Skip HR dropouts
                samples.append({
                    'sample_time': parse_datetime(sample['dateTime']),
                    'hr_value': sample['value']
                })
    
    return {'session': session, 'samples': samples}


def import_sessions(folder_path: Path):
    """Import all training sessions from a Polar export folder."""
    session_files = sorted(folder_path.glob('training-session-*.json'))
    print(f"Found {len(session_files)} training session files")
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # EFFICIENCY FIX: Query all known session IDs upfront to avoid per-file DB queries
    cur.execute("SELECT polar_session_id FROM polar_sessions")
    known_sessions = {row[0] for row in cur.fetchall()}
    print(f"  Already imported: {len(known_sessions)} sessions")
    
    # Filter to only new files BEFORE opening them
    new_files = [
        f for f in session_files
        if extract_session_id(f.name) not in known_sessions
    ]
    
    if not new_files:
        print("  No new sessions to import")
        cur.close()
        conn.close()
        return
    
    print(f"  New sessions to import: {len(new_files)}")
    
    sessions_imported = 0
    samples_imported = 0
    
    for filepath in new_files:
        print(f"Processing {filepath.name}...")
        
        try:
            result = parse_training_session(filepath)
            if not result:
                continue
            
            session = result['session']
            samples = result['samples']
            
            # Insert session
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
            sessions_imported += 1
            
            # Insert HR samples in batches with source provenance
            if samples:
                sample_data = [
                    (session_id, s['sample_time'], s['hr_value'], 'polar_file')
                    for s in samples
                ]
                execute_batch(
                    cur,
                    "INSERT INTO hr_samples (session_id, sample_time, hr_value, source) VALUES (%s, %s, %s, %s)",
                    sample_data,
                    page_size=1000
                )
                samples_imported += len(samples)
                print(f"  Imported {len(samples)} HR samples")
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"  ERROR: {e}")
            continue
    
    cur.close()
    conn.close()
    
    print(f"\n=== Import Complete ===")
    print(f"Sessions imported: {sessions_imported}")
    print(f"HR samples imported: {samples_imported}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python import_polar_sessions.py /path/to/polar-export-folder")
        sys.exit(1)
    
    folder_path = Path(sys.argv[1])
    if not folder_path.exists():
        print(f"Error: folder not found: {folder_path}")
        sys.exit(1)
    
    import_sessions(folder_path)


if __name__ == '__main__':
    main()
