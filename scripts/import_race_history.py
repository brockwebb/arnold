#!/usr/bin/env python3
"""
Import race history to Postgres analytics database.

Usage:
    python scripts/import_race_history.py data/raw/old_race_info/brock_webb_race_history.csv
    python scripts/import_race_history.py data/raw/old_race_info/*.csv --dry-run
"""

import os
import sys
import csv
import argparse
from pathlib import Path
from datetime import datetime

PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def create_table_if_not_exists(cur):
    """Create race_history table if it doesn't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS race_history (
            id SERIAL PRIMARY KEY,
            event_date DATE NOT NULL,
            event_year INTEGER,
            event_name VARCHAR(200) NOT NULL,
            distance_label VARCHAR(50),
            distance_km NUMERIC(6,2),
            distance_miles NUMERIC(6,2),
            location_city VARCHAR(100),
            location_state VARCHAR(50),
            finish_time INTERVAL,
            finish_seconds INTEGER,
            finish_hours NUMERIC(8,4),
            status VARCHAR(20) DEFAULT 'official',
            overall_place INTEGER,
            division_place INTEGER,
            age_at_race INTEGER,
            rank_percent NUMERIC(5,2),
            notes TEXT,
            source_file VARCHAR(200),
            imported_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(event_date, event_name, distance_label)
        );
        
        CREATE INDEX IF NOT EXISTS idx_race_date ON race_history(event_date);
        CREATE INDEX IF NOT EXISTS idx_race_distance ON race_history(distance_miles);
    """)


def parse_time_to_seconds(time_str: str) -> int:
    """Parse time string like '7:03:42' or '23:24:10' to seconds."""
    if not time_str or time_str.strip() == '':
        return None
    
    parts = time_str.strip().split(':')
    try:
        if len(parts) == 3:
            hours, mins, secs = int(parts[0]), int(parts[1]), int(parts[2])
            return hours * 3600 + mins * 60 + secs
        elif len(parts) == 2:
            mins, secs = int(parts[0]), int(parts[1])
            return mins * 60 + secs
    except ValueError:
        return None
    return None


def parse_clean_csv(filepath: Path) -> list:
    """Parse the clean brock_webb_race_history.csv format."""
    races = []
    
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Skip empty rows
            if not row.get('event_date') or not row.get('event_name'):
                continue
            
            try:
                event_date = datetime.strptime(row['event_date'], "%Y-%m-%d").date()
            except ValueError:
                print(f"  Skipping invalid date: {row.get('event_date')}")
                continue
            
            # Parse finish time
            finish_time = row.get('finish_time', '').strip()
            finish_seconds = None
            if finish_time:
                finish_seconds = parse_time_to_seconds(finish_time)
            elif row.get('finish_seconds'):
                try:
                    finish_seconds = int(float(row['finish_seconds']))
                except ValueError:
                    pass
            
            race = {
                'event_date': event_date,
                'event_year': int(row.get('event_year')) if row.get('event_year') else event_date.year,
                'event_name': row['event_name'].strip(),
                'distance_label': row.get('distance_label', '').strip() or None,
                'distance_km': float(row['distance_km']) if row.get('distance_km') else None,
                'distance_miles': float(row['distance_miles']) if row.get('distance_miles') else None,
                'location_city': row.get('location_city', '').strip() or None,
                'location_state': row.get('location_state', '').strip() or None,
                'finish_time': finish_time if finish_time else None,
                'finish_seconds': finish_seconds,
                'finish_hours': float(row['finish_hours']) if row.get('finish_hours') else None,
                'status': row.get('status', 'official').strip() or 'official',
                'overall_place': int(float(row['overall_place'])) if row.get('overall_place') and row['overall_place'].strip() else None,
                'division_place': int(float(row['division_place'])) if row.get('division_place') and row['division_place'].strip() else None,
                'age_at_race': int(float(row['age_at_race'])) if row.get('age_at_race') and row['age_at_race'].strip() else None,
                'rank_percent': float(row['rank_percent']) if row.get('rank_percent') and row['rank_percent'].strip() else None,
            }
            
            races.append(race)
    
    return races


def parse_running_csv(filepath: Path) -> list:
    """Parse the Webb-Race-Resume - Running.csv format (older, messier)."""
    races = []
    
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            date_str = row.get('Date', '').strip()
            name = row.get('Name', '').strip()
            
            if not date_str or not name:
                continue
            
            # Parse various date formats
            event_date = None
            for fmt in ['%d-%b-%Y', '%m/%d/%Y', '%Y', '%b-%Y', '%d-%B-%Y']:
                try:
                    event_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            
            if not event_date:
                print(f"  Skipping unparseable date: {date_str}")
                continue
            
            # Parse distance
            dist_km = None
            dist_mi = None
            try:
                dist_km = float(row.get('Dist (k)', 0) or 0)
                dist_mi = float(row.get('Dist (mi)', 0) or 0)
            except ValueError:
                pass
            
            # Parse time
            finish_seconds = None
            try:
                hours = int(row.get('Time (hr)', 0) or 0)
                mins = int(row.get('Time (min)', 0) or 0)
                secs = int(row.get('Time (sec)', 0) or 0)
                if hours or mins or secs:
                    finish_seconds = hours * 3600 + mins * 60 + secs
            except ValueError:
                pass
            
            # Format finish time string
            finish_time = None
            if finish_seconds:
                h = finish_seconds // 3600
                m = (finish_seconds % 3600) // 60
                s = finish_seconds % 60
                finish_time = f"{h}:{m:02d}:{s:02d}"
            
            # Parse location
            location = row.get('Location', '').strip()
            city, state = None, None
            if location:
                parts = location.replace('"', '').split(',')
                if len(parts) >= 2:
                    city = parts[0].strip()
                    state = parts[-1].strip()
                else:
                    city = location
            
            race = {
                'event_date': event_date,
                'event_year': event_date.year,
                'event_name': name,
                'distance_label': None,
                'distance_km': dist_km if dist_km else None,
                'distance_miles': dist_mi if dist_mi else None,
                'location_city': city,
                'location_state': state,
                'finish_time': finish_time,
                'finish_seconds': finish_seconds,
                'finish_hours': finish_seconds / 3600 if finish_seconds else None,
                'status': 'official',
                'overall_place': None,
                'division_place': None,
                'age_at_race': None,
                'rank_percent': None,
            }
            
            races.append(race)
    
    return races


def upsert_races(races: list, source_file: str) -> int:
    """Insert or update races in Postgres."""
    if not races:
        return 0
    
    import psycopg2
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    create_table_if_not_exists(cur)
    
    inserted = 0
    for race in races:
        try:
            cur.execute("""
                INSERT INTO race_history (
                    event_date, event_year, event_name, distance_label,
                    distance_km, distance_miles, location_city, location_state,
                    finish_time, finish_seconds, finish_hours, status,
                    overall_place, division_place, age_at_race, rank_percent,
                    source_file
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (event_date, event_name, distance_label) DO UPDATE SET
                    distance_km = COALESCE(EXCLUDED.distance_km, race_history.distance_km),
                    distance_miles = COALESCE(EXCLUDED.distance_miles, race_history.distance_miles),
                    finish_time = COALESCE(EXCLUDED.finish_time, race_history.finish_time),
                    finish_seconds = COALESCE(EXCLUDED.finish_seconds, race_history.finish_seconds),
                    overall_place = COALESCE(EXCLUDED.overall_place, race_history.overall_place),
                    division_place = COALESCE(EXCLUDED.division_place, race_history.division_place),
                    imported_at = NOW()
            """, (
                race['event_date'], race['event_year'], race['event_name'], race['distance_label'],
                race['distance_km'], race['distance_miles'], race['location_city'], race['location_state'],
                race['finish_time'], race['finish_seconds'], race['finish_hours'], race['status'],
                race['overall_place'], race['division_place'], race['age_at_race'], race['rank_percent'],
                source_file
            ))
            inserted += 1
        except Exception as e:
            print(f"  Error inserting {race['event_name']} ({race['event_date']}): {e}")
    
    conn.commit()
    cur.close()
    conn.close()
    
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Import race history")
    parser.add_argument("files", nargs="+", help="CSV file(s) to import")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't save")
    args = parser.parse_args()
    
    all_races = []
    
    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            print(f"File not found: {filepath}")
            continue
        
        print(f"Parsing {path.name}...")
        
        # Choose parser based on filename
        if 'brock_webb_race_history' in path.name:
            races = parse_clean_csv(path)
        elif 'Running' in path.name:
            races = parse_running_csv(path)
        else:
            print(f"  Unknown format, trying clean CSV parser...")
            races = parse_clean_csv(path)
        
        print(f"  Found {len(races)} races")
        
        for race in races:
            race['source_file'] = path.name
        
        all_races.extend(races)
    
    # Deduplicate by (date, name)
    seen = set()
    unique_races = []
    for race in all_races:
        key = (race['event_date'], race['event_name'])
        if key not in seen:
            seen.add(key)
            unique_races.append(race)
    
    print(f"\nTotal: {len(unique_races)} unique races")
    
    # Show distance breakdown
    by_distance = {}
    for race in unique_races:
        dist = race.get('distance_miles') or 0
        if dist >= 100:
            cat = '100+ miler'
        elif dist >= 50:
            cat = '50+ miler'
        elif dist >= 26:
            cat = 'marathon/ultra'
        elif dist >= 13:
            cat = 'half marathon'
        else:
            cat = 'shorter'
        by_distance[cat] = by_distance.get(cat, 0) + 1
    
    print("\nBy distance:")
    for cat in ['100+ miler', '50+ miler', 'marathon/ultra', 'half marathon', 'shorter']:
        if cat in by_distance:
            print(f"  {cat}: {by_distance[cat]}")
    
    # Date range
    dates = sorted(r['event_date'] for r in unique_races)
    if dates:
        print(f"\nDate range: {dates[0]} to {dates[-1]}")
    
    if args.dry_run:
        print("\nDRY RUN - not saving to database")
        print("\nSample races:")
        for race in unique_races[:5]:
            print(f"  {race['event_date']} {race['event_name']} ({race['distance_miles']}mi) - {race['finish_time']}")
    else:
        count = upsert_races(unique_races, "import")
        print(f"\nUpserted {count} races to Postgres")
    
    print("Done")


if __name__ == "__main__":
    main()
