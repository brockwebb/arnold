#!/usr/bin/env python3
"""
FIT File Importer for Arnold (Postgres-First Architecture)

Imports endurance workouts from Garmin/Suunto/Wahoo FIT files.
Per ADR-001: Postgres is source of truth, Neo4j gets lightweight reference.

Usage:
    python scripts/import_fit_workouts.py                    # Import all new FIT files
    python scripts/import_fit_workouts.py --dry-run          # Preview what would be imported
    python scripts/import_fit_workouts.py --file <path.fit>  # Import specific file

FIT files should be placed in: data/raw/suunto/ (or data/raw/garmin/, etc.)

Architecture (ADR-001):
    1. Parse FIT file for session data and laps
    2. Insert into Postgres (endurance_sessions, endurance_laps) - SOURCE OF TRUTH
    3. Create lightweight reference in Neo4j for relationship queries
    4. Track imported files in manifest to avoid duplicates
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import fitparse
except ImportError:
    print("ERROR: fitparse not installed. Run: pip install fitparse")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_RAW = PROJECT_ROOT / "data" / "raw"
FIT_DIRS = [
    DATA_RAW / "suunto",
    DATA_RAW / "garmin",
    DATA_RAW / "wahoo",
    DATA_RAW / "fit",  # Generic
]
MANIFEST_FILE = DATA_RAW / "fit_import_manifest.json"

# Database connections
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://brock@localhost:5432/arnold_analytics")
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")


def load_manifest() -> dict:
    """Load the manifest of previously imported files."""
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {"imported_files": {}}


def save_manifest(manifest: dict):
    """Save the manifest."""
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2, default=str)


def parse_fit_file(filepath: Path) -> Optional[dict]:
    """
    Parse a FIT file and extract workout data.
    
    Returns dict with session data and lap splits, or None if parsing fails.
    """
    try:
        fit = fitparse.FitFile(str(filepath))
    except Exception as e:
        print(f"  ERROR: Failed to parse {filepath.name}: {e}")
        return None
    
    workout = {
        "source_file": filepath.name,
        "source_path": str(filepath),
        "laps": [],
    }
    
    # Extract session data
    for record in fit.get_messages('session'):
        for field in record:
            if field.value is not None:
                workout[field.name] = field.value
    
    # Check if we got meaningful data
    if 'sport' not in workout:
        print(f"  WARN: No sport type found in {filepath.name}")
        return None
    
    # Extract lap data
    fit = fitparse.FitFile(str(filepath))  # Re-read for laps
    for i, record in enumerate(fit.get_messages('lap'), 1):
        lap = {"lap_number": i}
        for field in record:
            if field.value is not None:
                lap[field.name] = field.value
        workout["laps"].append(lap)
    
    return workout


def format_session_for_postgres(raw: dict) -> dict:
    """
    Transform raw FIT data into Postgres endurance_sessions row.
    """
    # Calculate derived fields
    distance_m = raw.get('total_distance', 0)
    distance_miles = distance_m / 1609.34 if distance_m else None
    
    duration_sec = raw.get('total_timer_time', 0)
    
    # Calculate pace (min/mile)
    avg_pace = None
    if distance_miles and distance_miles > 0 and duration_sec and duration_sec > 0:
        pace_sec_per_mile = duration_sec / distance_miles
        pace_min = int(pace_sec_per_mile // 60)
        pace_sec = int(pace_sec_per_mile % 60)
        avg_pace = f"{pace_min}:{pace_sec:02d}/mi"
    
    # Get start time
    start_time = raw.get('start_time')
    if start_time:
        if hasattr(start_time, 'date'):
            session_date = start_time.date()
            session_time = start_time.time() if hasattr(start_time, 'time') else None
        else:
            session_date = start_time
            session_time = None
    else:
        session_date = None
        session_time = None
    
    # Sport type
    sport = str(raw.get('sport', 'unknown')).lower()
    
    # Determine source from path
    source_path = raw.get('source_path', '')
    if 'suunto' in source_path.lower():
        source = 'suunto'
    elif 'garmin' in source_path.lower():
        source = 'garmin'
    elif 'wahoo' in source_path.lower():
        source = 'wahoo'
    elif 'polar' in source_path.lower():
        source = 'polar'
    else:
        source = 'fit_import'
    
    # Build name
    name = f"{sport.title()} - {distance_miles:.1f}mi" if distance_miles else f"{sport.title()}"
    
    return {
        "session_date": session_date,
        "session_time": session_time,
        "name": name,
        "sport": sport,
        "source": source,
        "source_file": raw.get('source_file'),
        "distance_miles": round(distance_miles, 2) if distance_miles else None,
        "distance_meters": round(distance_m, 1) if distance_m else None,
        "duration_seconds": int(duration_sec) if duration_sec else None,
        "avg_pace": avg_pace,
        "avg_hr": raw.get('avg_heart_rate'),
        "max_hr": raw.get('max_heart_rate'),
        "min_hr": raw.get('min_heart_rate'),
        "elevation_gain_m": raw.get('total_ascent'),
        "elevation_loss_m": raw.get('total_descent'),
        "max_altitude_m": raw.get('enhanced_max_altitude', raw.get('max_altitude')),
        "min_altitude_m": raw.get('enhanced_min_altitude', raw.get('min_altitude')),
        "avg_cadence": raw.get('avg_running_cadence', raw.get('avg_cadence')),
        "max_cadence": raw.get('max_running_cadence', raw.get('max_cadence')),
        "calories": raw.get('total_calories'),
        "tss": raw.get('training_stress_score'),
        "training_effect": raw.get('total_training_effect'),
        "recovery_time_hours": raw.get('recovery_time', 0) / 3600 if raw.get('recovery_time') else None,
    }


def format_laps_for_postgres(raw: dict) -> list:
    """
    Transform raw lap data into list of Postgres endurance_laps rows.
    """
    laps = []
    for lap in raw.get('laps', []):
        distance_m = lap.get('total_distance', 0)
        distance_miles = distance_m / 1609.34 if distance_m else None
        
        duration_sec = lap.get('total_timer_time', 0)
        
        # Calculate pace
        pace = None
        if distance_miles and distance_miles > 0 and duration_sec and duration_sec > 0:
            pace_sec_per_mile = duration_sec / distance_miles
            pace_min = int(pace_sec_per_mile // 60)
            pace_sec = int(pace_sec_per_mile % 60)
            pace = f"{pace_min}:{pace_sec:02d}/mi"
        
        laps.append({
            "lap_number": lap.get('lap_number'),
            "distance_miles": round(distance_miles, 2) if distance_miles else None,
            "distance_meters": round(distance_m, 1) if distance_m else None,
            "duration_seconds": int(duration_sec) if duration_sec else None,
            "pace": pace,
            "avg_hr": lap.get('avg_heart_rate'),
            "max_hr": lap.get('max_heart_rate'),
            "avg_cadence": lap.get('avg_running_cadence', lap.get('avg_cadence')),
            "elevation_gain_m": lap.get('total_ascent'),
            "calories": lap.get('total_calories'),
        })
    
    return laps


def check_postgres_duplicate(conn, session: dict) -> Optional[int]:
    """
    Check if a similar session already exists in Postgres.
    
    Returns session ID if duplicate found, None otherwise.
    """
    if not session.get('session_date') or not session.get('distance_miles'):
        return None
    
    query = """
    SELECT id FROM endurance_sessions
    WHERE session_date = %s
      AND distance_miles IS NOT NULL
      AND ABS(distance_miles - %s) < 0.1
      AND ABS(COALESCE(duration_seconds, 0) - %s) < 120
    LIMIT 1
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(query, (
                session['session_date'],
                session['distance_miles'],
                session.get('duration_seconds', 0) or 0,
            ))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as e:
        print(f"  WARN: Duplicate check failed: {e}")
        return None


def insert_session_to_postgres(conn, session: dict, laps: list, dry_run: bool = False) -> Optional[int]:
    """
    Insert session and laps into Postgres.
    
    Returns the session ID.
    """
    if dry_run:
        print(f"  Would create in Postgres: {session.get('name')} on {session.get('session_date')}")
        print(f"    Distance: {session.get('distance_miles')}mi, Duration: {session.get('duration_seconds', 0)//60}min")
        print(f"    HR: {session.get('avg_hr')}/{session.get('max_hr')}, TSS: {session.get('tss')}")
        print(f"    Laps: {len(laps)}")
        return -1  # Dummy ID for dry run
    
    session_query = """
    INSERT INTO endurance_sessions (
        session_date, session_time, name, sport, source, source_file,
        distance_miles, distance_meters, duration_seconds, avg_pace,
        avg_hr, max_hr, min_hr,
        elevation_gain_m, elevation_loss_m, max_altitude_m, min_altitude_m,
        avg_cadence, max_cadence, calories,
        tss, training_effect, recovery_time_hours
    ) VALUES (
        %(session_date)s, %(session_time)s, %(name)s, %(sport)s, %(source)s, %(source_file)s,
        %(distance_miles)s, %(distance_meters)s, %(duration_seconds)s, %(avg_pace)s,
        %(avg_hr)s, %(max_hr)s, %(min_hr)s,
        %(elevation_gain_m)s, %(elevation_loss_m)s, %(max_altitude_m)s, %(min_altitude_m)s,
        %(avg_cadence)s, %(max_cadence)s, %(calories)s,
        %(tss)s, %(training_effect)s, %(recovery_time_hours)s
    )
    RETURNING id
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(session_query, session)
            session_id = cur.fetchone()[0]
            
            # Insert laps
            if laps:
                lap_query = """
                INSERT INTO endurance_laps (
                    session_id, lap_number, distance_miles, distance_meters,
                    duration_seconds, pace, avg_hr, max_hr, avg_cadence,
                    elevation_gain_m, calories
                ) VALUES %s
                """
                lap_values = [
                    (
                        session_id,
                        lap['lap_number'],
                        lap.get('distance_miles'),
                        lap.get('distance_meters'),
                        lap.get('duration_seconds'),
                        lap.get('pace'),
                        lap.get('avg_hr'),
                        lap.get('max_hr'),
                        lap.get('avg_cadence'),
                        lap.get('elevation_gain_m'),
                        lap.get('calories'),
                    )
                    for lap in laps
                ]
                execute_values(cur, lap_query, lap_values)
            
            conn.commit()
            return session_id
            
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: Failed to insert session: {e}")
        return None


def create_neo4j_reference(driver, session: dict, postgres_id: int, dry_run: bool = False) -> Optional[str]:
    """
    Create lightweight reference node in Neo4j for relationship queries.
    
    Per ADR-001: Neo4j holds just enough to support graph queries.
    Full data lives in Postgres.
    """
    if dry_run:
        print(f"  Would create Neo4j reference: postgres_id={postgres_id}")
        return "DRY-RUN-UUID"
    
    query = """
    MATCH (p:Person {name: 'Brock Webb'})
    CREATE (ew:EnduranceWorkout {
        id: randomUUID(),
        postgres_id: $postgres_id,
        date: date($date),
        sport: $sport,
        distance_miles: $distance_miles,
        tss: $tss,
        name: $name,
        created_at: datetime()
    })
    CREATE (p)-[:PERFORMED]->(ew)
    RETURN ew.id as id
    """
    
    try:
        with driver.session() as neo_session:
            result = neo_session.run(query, {
                "postgres_id": postgres_id,
                "date": str(session.get('session_date')),
                "sport": session.get('sport'),
                "distance_miles": session.get('distance_miles'),
                "tss": session.get('tss'),
                "name": session.get('name'),
            })
            record = result.single()
            return record['id'] if record else None
    except Exception as e:
        print(f"  WARN: Failed to create Neo4j reference: {e}")
        return None


def update_postgres_neo4j_ref(conn, postgres_id: int, neo4j_id: str):
    """Update Postgres session with Neo4j reference ID."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE endurance_sessions SET neo4j_id = %s WHERE id = %s",
                (neo4j_id, postgres_id)
            )
            conn.commit()
    except Exception as e:
        print(f"  WARN: Failed to update neo4j_id: {e}")


def find_fit_files() -> list:
    """Find all .fit files in the configured directories."""
    fit_files = []
    
    for dir_path in FIT_DIRS:
        if dir_path.exists():
            for fit_file in dir_path.glob("*.fit"):
                fit_files.append(fit_file)
            for fit_file in dir_path.glob("*.FIT"):
                fit_files.append(fit_file)
    
    return fit_files


def main():
    parser = argparse.ArgumentParser(description="Import FIT files (Postgres-first per ADR-001)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--file", type=Path, help="Import specific FIT file")
    parser.add_argument("--force", action="store_true", help="Re-import even if already in manifest")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j reference creation")
    args = parser.parse_args()
    
    print("=" * 60)
    print("FIT File Importer (Postgres-First Architecture)")
    print("=" * 60)
    
    # Load manifest
    manifest = load_manifest()
    
    # Find files to import
    if args.file:
        if not args.file.exists():
            print(f"ERROR: File not found: {args.file}")
            sys.exit(1)
        fit_files = [args.file]
    else:
        fit_files = find_fit_files()
    
    if not fit_files:
        print("No FIT files found in:")
        for d in FIT_DIRS:
            print(f"  - {d}")
        return
    
    print(f"Found {len(fit_files)} FIT file(s)")
    
    # Filter already imported
    if not args.force:
        new_files = []
        for f in fit_files:
            if str(f) not in manifest.get("imported_files", {}):
                new_files.append(f)
            else:
                print(f"  Skipping (already imported): {f.name}")
        fit_files = new_files
    
    if not fit_files:
        print("No new files to import")
        return
    
    print(f"Importing {len(fit_files)} new file(s)")
    
    # Connect to databases
    pg_conn = None
    neo4j_driver = None
    
    if not args.dry_run:
        try:
            pg_conn = psycopg2.connect(POSTGRES_DSN)
            print("✓ Connected to Postgres")
        except Exception as e:
            print(f"ERROR: Cannot connect to Postgres: {e}")
            sys.exit(1)
        
        if not args.skip_neo4j:
            try:
                neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                neo4j_driver.verify_connectivity()
                print("✓ Connected to Neo4j")
            except Exception as e:
                print(f"WARN: Cannot connect to Neo4j: {e}")
                print("  Continuing without Neo4j references")
    
    # Process each file
    imported = 0
    skipped = 0
    failed = 0
    
    for fit_file in fit_files:
        print(f"\nProcessing: {fit_file.name}")
        
        # Parse FIT file
        raw = parse_fit_file(fit_file)
        if not raw:
            failed += 1
            continue
        
        # Format for Postgres
        session = format_session_for_postgres(raw)
        laps = format_laps_for_postgres(raw)
        
        if not session.get('session_date'):
            print(f"  WARN: No date found, skipping")
            skipped += 1
            continue
        
        # Check for duplicates in Postgres
        if pg_conn and not args.force:
            dup_id = check_postgres_duplicate(pg_conn, session)
            if dup_id:
                print(f"  Duplicate found in Postgres (ID: {dup_id}), skipping")
                manifest.setdefault("imported_files", {})[str(fit_file)] = {
                    "imported_at": datetime.now().isoformat(),
                    "status": "duplicate",
                    "postgres_id": dup_id,
                }
                skipped += 1
                continue
        
        # Insert into Postgres (SOURCE OF TRUTH)
        postgres_id = insert_session_to_postgres(pg_conn, session, laps, dry_run=args.dry_run)
        
        if postgres_id:
            print(f"  ✓ Postgres: {session.get('name')} (ID: {postgres_id})")
            print(f"    {session.get('distance_miles')}mi | {(session.get('duration_seconds') or 0)//60}min | HR {session.get('avg_hr')}/{session.get('max_hr')} | TSS {session.get('tss')}")
            
            # Create Neo4j reference (lightweight)
            neo4j_id = None
            if neo4j_driver and not args.dry_run:
                neo4j_id = create_neo4j_reference(neo4j_driver, session, postgres_id, dry_run=args.dry_run)
                if neo4j_id:
                    print(f"  ✓ Neo4j reference: {neo4j_id[:8]}...")
                    update_postgres_neo4j_ref(pg_conn, postgres_id, neo4j_id)
            
            if not args.dry_run:
                manifest.setdefault("imported_files", {})[str(fit_file)] = {
                    "imported_at": datetime.now().isoformat(),
                    "status": "imported",
                    "postgres_id": postgres_id,
                    "neo4j_id": neo4j_id,
                    "date": str(session.get('session_date')),
                    "distance_miles": session.get('distance_miles'),
                }
            
            imported += 1
        else:
            failed += 1
    
    # Save manifest
    if not args.dry_run and imported > 0:
        save_manifest(manifest)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Summary: {imported} imported, {skipped} skipped, {failed} failed")
    
    if pg_conn:
        pg_conn.close()
    if neo4j_driver:
        neo4j_driver.close()


if __name__ == "__main__":
    main()
