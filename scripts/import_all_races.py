#!/usr/bin/env python3
"""
Comprehensive Race History Importer

Imports ALL race data from multiple CSV formats into Postgres.
Handles deduplication and merging of overlapping records.

Source files:
- Webb-Race-Resume - Running.csv: 70+ races, all distances, 2005-2016
- Webb-Race-Resume - Triathlon.csv: Sparse triathlon data
- brock_webb_race_history.csv: 47 ultra races, 2007-2023 (already imported)

Usage:
    python scripts/import_all_races.py                    # Import all
    python scripts/import_all_races.py --dry-run          # Preview only
    python scripts/import_all_races.py --source running   # Just running.csv
"""

import os
import sys
import re
import csv
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "old_race_info"

# Birth date for age calculation
BIRTH_DATE = date(1976, 4, 25)


def parse_date_flexible(date_str: str) -> Optional[date]:
    """Parse dates in various formats."""
    if not date_str or date_str.strip() == "":
        return None
    
    date_str = date_str.strip()
    
    # Handle year-only
    if re.match(r'^\d{4}$', date_str):
        return date(int(date_str), 6, 15)  # Mid-year estimate
    
    # Common formats
    formats = [
        "%d-%b-%Y",     # 24-Nov-2005
        "%Y-%m-%d",     # 2023-03-11
        "%m/%d/%Y",     # 7/6/2013
        "%d-%B-%Y",     # 12-November-2016
        "%b-%Y",        # Nov-2014
        "%B-%Y",        # November-2014
        "%m/%Y",        # 11/2014
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    # Try extracting month/year patterns
    match = re.match(r'(\d{1,2})/(\d{4})', date_str)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return date(year, month, 15)
    
    # Jun-2016 style
    match = re.match(r'([A-Za-z]+)-?(\d{4})', date_str)
    if match:
        try:
            month_str, year = match.groups()
            dt = datetime.strptime(f"{month_str} {year}", "%b %Y")
            return dt.date()
        except:
            try:
                dt = datetime.strptime(f"{month_str} {year}", "%B %Y")
                return dt.date()
            except:
                pass
    
    print(f"  Warning: Could not parse date '{date_str}'")
    return None


def parse_time_to_seconds(time_str: str) -> Optional[int]:
    """Parse time string to total seconds."""
    if not time_str or time_str.strip() == "":
        return None
    
    time_str = time_str.strip()
    
    # Handle H:MM:SS or HH:MM:SS
    match = re.match(r'(\d+):(\d{2}):(\d{2})', time_str)
    if match:
        h, m, s = map(int, match.groups())
        return h * 3600 + m * 60 + s
    
    # Handle MM:SS
    match = re.match(r'(\d+):(\d{2})$', time_str)
    if match:
        m, s = map(int, match.groups())
        return m * 60 + s
    
    return None


def calculate_age(race_date: date) -> int:
    """Calculate age at race date."""
    age = race_date.year - BIRTH_DATE.year
    if (race_date.month, race_date.day) < (BIRTH_DATE.month, BIRTH_DATE.day):
        age -= 1
    return age


def parse_running_csv(filepath: Path) -> list:
    """Parse Webb-Race-Resume - Running.csv"""
    races = []
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Skip empty rows
            if not row.get('Date') or not row.get('Name'):
                continue
            
            event_date = parse_date_flexible(row['Date'])
            if not event_date:
                continue
            
            # Parse distance
            dist_km = None
            dist_mi = None
            try:
                dist_km = float(row.get('Dist (k)', 0) or 0)
                dist_mi = float(row.get('Dist (mi)', 0) or 0)
            except:
                pass
            
            if not dist_km and not dist_mi:
                continue
            
            # Parse time
            finish_seconds = None
            try:
                hr = int(row.get('Time (hr)', 0) or 0)
                mn = int(row.get('Time (min)', 0) or 0)
                sc = int(row.get('Time (sec)', 0) or 0)
                if hr or mn or sc:
                    finish_seconds = hr * 3600 + mn * 60 + sc
            except:
                pass
            
            # Determine distance label
            if dist_mi:
                if dist_mi <= 3.5:
                    distance_label = "5K"
                elif dist_mi <= 5.5:
                    distance_label = "8K"
                elif dist_mi <= 7:
                    distance_label = "10K"
                elif dist_mi <= 11:
                    distance_label = "10 Miler"
                elif dist_mi <= 14:
                    distance_label = "Half Marathon"
                elif dist_mi <= 17:
                    distance_label = "25K"
                elif dist_mi <= 22:
                    distance_label = "20 Miler"
                elif dist_mi <= 28:
                    distance_label = "Marathon"
                elif dist_mi <= 35:
                    distance_label = "50K"
                elif dist_mi <= 55:
                    distance_label = "50 Miler"
                elif dist_mi <= 70:
                    distance_label = "100K"
                else:
                    distance_label = "100 Miler"
            else:
                distance_label = f"{dist_km}K"
            
            # Parse location
            location = row.get('Location', '').strip()
            city, state = '', ''
            if ',' in location:
                parts = location.rsplit(',', 1)
                city = parts[0].strip()
                state = parts[1].strip()
            else:
                city = location
            
            race = {
                'event_date': event_date,
                'event_year': event_date.year,
                'event_name': row['Name'].strip(),
                'distance_label': distance_label,
                'distance_km': dist_km or (dist_mi * 1.60934 if dist_mi else None),
                'distance_miles': dist_mi or (dist_km / 1.60934 if dist_km else None),
                'location_city': city,
                'location_state': state,
                'finish_seconds': finish_seconds,
                'finish_hours': finish_seconds / 3600 if finish_seconds else None,
                'age_at_race': calculate_age(event_date),
                'notes': row.get('Notes', '').strip()[:500] if row.get('Notes') else None,
                'source_file': 'running_csv',
                'status': 'official' if finish_seconds else 'incomplete'
            }
            
            races.append(race)
    
    return races


def parse_triathlon_csv(filepath: Path) -> list:
    """Parse Webb-Race-Resume - Triathlon.csv"""
    races = []
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()
    
    # Skip header rows, find data
    for line in lines[3:]:  # Skip first 3 header rows
        parts = line.strip().split(',')
        if len(parts) < 12 or not parts[0]:
            continue
        
        date_str = parts[0].strip()
        event_name = parts[1].strip()
        distance_desc = parts[2].strip()  # e.g., "1.2 / 56 / 13.1"
        total_time = parts[11].strip() if len(parts) > 11 else None
        
        if not event_name or not total_time:
            continue
        
        event_date = parse_date_flexible(date_str)
        if not event_date:
            continue
        
        finish_seconds = parse_time_to_seconds(total_time)
        
        # Determine distance label from description
        distance_label = "Triathlon"
        if "half" in event_name.lower() or "70.3" in distance_desc or "56" in distance_desc:
            distance_label = "Half Ironman"
        elif "xterra" in event_name.lower():
            distance_label = "XTERRA"
        
        race = {
            'event_date': event_date,
            'event_year': event_date.year,
            'event_name': event_name,
            'distance_label': distance_label,
            'distance_km': None,
            'distance_miles': None,
            'location_city': None,
            'location_state': None,
            'finish_seconds': finish_seconds,
            'finish_hours': finish_seconds / 3600 if finish_seconds else None,
            'age_at_race': calculate_age(event_date),
            'notes': f"Distance: {distance_desc}",
            'source_file': 'triathlon_csv',
            'status': 'official' if finish_seconds else 'incomplete'
        }
        
        races.append(race)
    
    return races


def upsert_races(races: list, dry_run: bool = False):
    """
    Insert new races, but DO NOT overwrite authoritative ultrasignup data.
    
    Priority: ultrasignup (import) > running_csv > triathlon_csv
    """
    if not races:
        print("No races to insert")
        return 0, 0
    
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # Get existing races from authoritative sources
    cur.execute("""
        SELECT event_date, event_name, distance_label, source_file 
        FROM race_history 
        WHERE source_file = 'import' OR source_file LIKE '%ultrasignup%'
    """)
    existing_authoritative = {
        (row[0], row[1].lower().strip(), row[2].lower().strip()): row[3]
        for row in cur.fetchall()
    }
    
    # Also get ALL existing to avoid duplicates
    cur.execute("SELECT event_date, event_name, distance_label FROM race_history")
    all_existing = {
        (row[0], row[1].lower().strip(), row[2].lower().strip())
        for row in cur.fetchall()
    }
    
    # Filter races
    new_races = []
    skipped_authoritative = []
    skipped_duplicate = []
    
    for r in races:
        key = (r['event_date'], r['event_name'].lower().strip(), r['distance_label'].lower().strip())
        
        if key in existing_authoritative:
            skipped_authoritative.append(r)
        elif key in all_existing:
            skipped_duplicate.append(r)
        else:
            new_races.append(r)
    
    if dry_run:
        print(f"\n=== DRY RUN ===")
        print(f"\nSkipping {len(skipped_authoritative)} races (authoritative ultrasignup data exists):")
        for r in skipped_authoritative[:10]:
            print(f"  {r['event_date']} - {r['event_name']} [{r['distance_label']}]")
        if len(skipped_authoritative) > 10:
            print(f"  ... and {len(skipped_authoritative) - 10} more")
        
        if skipped_duplicate:
            print(f"\nSkipping {len(skipped_duplicate)} races (already in database):")
            for r in skipped_duplicate[:5]:
                print(f"  {r['event_date']} - {r['event_name']}")
        
        print(f"\nWould INSERT {len(new_races)} NEW races:")
        for r in new_races[:20]:
            time_str = ""
            if r['finish_seconds']:
                h = r['finish_seconds'] // 3600
                m = (r['finish_seconds'] % 3600) // 60
                time_str = f" ({h}:{m:02d})"
            print(f"  {r['event_date']} - {r['event_name']} [{r['distance_label']}]{time_str}")
        if len(new_races) > 20:
            print(f"  ... and {len(new_races) - 20} more")
        
        cur.close()
        conn.close()
        return len(new_races), 0
    
    if not new_races:
        print("No new races to insert (all already exist or are from authoritative source)")
        cur.execute("SELECT COUNT(*) FROM race_history")
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
        return 0, total
    
    # Prepare data for INSERT only (no upsert)
    rows = []
    for r in new_races:
        # Format finish time
        finish_time = None
        if r['finish_seconds']:
            h = r['finish_seconds'] // 3600
            m = (r['finish_seconds'] % 3600) // 60
            s = r['finish_seconds'] % 60
            finish_time = f"{h}:{m:02d}:{s:02d}"
        
        rows.append((
            r['event_date'],
            r['event_name'],
            r['distance_label'],
            r['distance_km'],
            r['distance_miles'],
            r.get('location_city'),
            r.get('location_state'),
            finish_time,
            r['finish_seconds'],
            r['finish_hours'],
            None,  # overall_place
            None,  # division_place
            r['age_at_race'],
            None,  # rank_percent
            r['status'],
            r.get('notes'),
            r['source_file']
        ))
    
    # INSERT only - no conflict handling needed since we filtered
    sql = """
    INSERT INTO race_history (
        event_date, event_name, distance_label, distance_km, distance_miles,
        location_city, location_state, finish_time, finish_seconds, finish_hours,
        overall_place, division_place, age_at_race, rank_percent, status, notes, source_file
    ) VALUES %s
    ON CONFLICT (event_date, event_name, distance_label) DO NOTHING
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    
    print(f"Skipped {len(skipped_authoritative)} races (authoritative ultrasignup data preserved)")
    
    # Get count
    cur.execute("SELECT COUNT(*) FROM race_history")
    total = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return len(new_races), total


def ensure_table():
    """Ensure race_history table exists with proper schema."""
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # Check if table has all columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'race_history'
    """)
    existing_cols = {row[0] for row in cur.fetchall()}
    
    # Add location columns if missing
    if 'location_city' not in existing_cols:
        cur.execute("ALTER TABLE race_history ADD COLUMN location_city TEXT")
    if 'location_state' not in existing_cols:
        cur.execute("ALTER TABLE race_history ADD COLUMN location_state TEXT")
    
    # Update unique constraint if needed
    cur.execute("""
        SELECT constraint_name FROM information_schema.table_constraints 
        WHERE table_name = 'race_history' AND constraint_type = 'UNIQUE'
    """)
    constraints = [row[0] for row in cur.fetchall()]
    
    # Drop old constraint and create new one
    for c in constraints:
        if 'event_date' in c and 'event_name' not in c:
            cur.execute(f"ALTER TABLE race_history DROP CONSTRAINT {c}")
    
    # Create new unique constraint
    try:
        cur.execute("""
            ALTER TABLE race_history 
            ADD CONSTRAINT race_history_unique_event 
            UNIQUE (event_date, event_name, distance_label)
        """)
    except:
        pass  # Already exists
    
    conn.commit()
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Import all race history")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--source", choices=['running', 'triathlon', 'all'], default='all')
    args = parser.parse_args()
    
    print("=== Comprehensive Race History Import ===\n")
    
    ensure_table()
    
    all_races = []
    
    # Parse running races
    if args.source in ['running', 'all']:
        running_file = DATA_DIR / "Webb-Race-Resume - Running.csv"
        if running_file.exists():
            print(f"Parsing {running_file.name}...")
            running_races = parse_running_csv(running_file)
            print(f"  Found {len(running_races)} races")
            all_races.extend(running_races)
    
    # Parse triathlon races  
    if args.source in ['triathlon', 'all']:
        tri_file = DATA_DIR / "Webb-Race-Resume - Triathlon.csv"
        if tri_file.exists():
            print(f"Parsing {tri_file.name}...")
            tri_races = parse_triathlon_csv(tri_file)
            print(f"  Found {len(tri_races)} races")
            all_races.extend(tri_races)
    
    print(f"\nTotal: {len(all_races)} races to import")
    
    # Show distance breakdown
    from collections import Counter
    dist_counts = Counter(r['distance_label'] for r in all_races)
    print("\nBy distance:")
    for dist, count in sorted(dist_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {dist}: {count}")
    
    # Show year range
    years = [r['event_date'].year for r in all_races]
    print(f"\nYear range: {min(years)} - {max(years)}")
    
    # Upsert
    print()
    if args.dry_run:
        upsert_races(all_races, dry_run=True)
    else:
        inserted, total = upsert_races(all_races)
        print(f"Upserted {inserted} races")
        print(f"Total races in database: {total}")


if __name__ == "__main__":
    main()
