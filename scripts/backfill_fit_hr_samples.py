#!/usr/bin/env python3
"""
Backfill HR samples for existing FIT-imported sessions.

Issue #23: Extract per-second HR samples from FIT files

This script:
1. Finds endurance_sessions that were imported from FIT files
2. Checks if they already have HR samples
3. Re-parses the FIT files to extract HR samples
4. Inserts samples with proper provenance

Usage:
    python scripts/backfill_fit_hr_samples.py           # Backfill all
    python scripts/backfill_fit_hr_samples.py --dry-run # Preview
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import fitparse
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_RAW = PROJECT_ROOT / "data" / "raw"
FIT_DIRS = {
    "suunto": DATA_RAW / "suunto",
    "garmin": DATA_RAW / "garmin",
    "wahoo": DATA_RAW / "wahoo",
    "polar": DATA_RAW / "polar",
    "fit_import": DATA_RAW / "fit",
}

POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://brock@localhost:5432/arnold_analytics")


def extract_hr_samples_from_fit(filepath: Path) -> list:
    """Extract per-second HR samples from FIT file 'record' messages."""
    try:
        fit = fitparse.FitFile(str(filepath))
    except Exception as e:
        print(f"  ERROR: Failed to parse {filepath.name}: {e}")
        return []
    
    samples = []
    
    for record in fit.get_messages('record'):
        sample = {'hr_value': None, 'sample_time': None}
        
        for field in record:
            if field.name == 'heart_rate' and field.value is not None:
                try:
                    hr = int(field.value)
                    if 30 <= hr <= 250:
                        sample['hr_value'] = hr
                except (ValueError, TypeError):
                    pass
            elif field.name == 'timestamp' and field.value is not None:
                sample['sample_time'] = field.value
        
        if sample['hr_value'] and sample['sample_time']:
            samples.append(sample)
    
    return samples


def find_fit_file(source: str, source_file: str) -> Path | None:
    """Find the FIT file for a given source and filename."""
    # Try source-specific directory first
    if source in FIT_DIRS:
        path = FIT_DIRS[source] / source_file
        if path.exists():
            return path
    
    # Search all directories
    for dir_path in FIT_DIRS.values():
        if dir_path.exists():
            path = dir_path / source_file
            if path.exists():
                return path
    
    return None


def get_sessions_needing_backfill(conn) -> list:
    """Get endurance_sessions from FIT imports that lack HR samples."""
    query = """
    SELECT es.id, es.session_date, es.name, es.source, es.source_file,
           (SELECT COUNT(*) FROM hr_samples WHERE endurance_session_id = es.id) as hr_count
    FROM endurance_sessions es
    WHERE es.source_file IS NOT NULL
      AND es.source_file LIKE '%.fit'
    ORDER BY es.session_date DESC
    """
    
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def insert_hr_samples(conn, endurance_session_id: int, samples: list, source: str) -> int:
    """Batch insert HR samples."""
    if not samples:
        return 0
    
    query = """
    INSERT INTO hr_samples (endurance_session_id, sample_time, hr_value, source)
    VALUES %s
    """
    values = [
        (endurance_session_id, s['sample_time'], s['hr_value'], source)
        for s in samples
    ]
    
    with conn.cursor() as cur:
        execute_values(cur, query, values, page_size=1000)
    conn.commit()
    
    return len(samples)


def main():
    parser = argparse.ArgumentParser(description="Backfill HR samples for existing FIT imports")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--force", action="store_true", help="Re-backfill even if samples exist")
    args = parser.parse_args()
    
    print("=" * 60)
    print("FIT HR Sample Backfill (Issue #23)")
    print("=" * 60)
    
    conn = psycopg2.connect(POSTGRES_DSN)
    print("✓ Connected to Postgres")
    
    sessions = get_sessions_needing_backfill(conn)
    print(f"Found {len(sessions)} FIT-imported sessions")
    
    backfilled = 0
    skipped = 0
    failed = 0
    total_samples = 0
    
    for session in sessions:
        session_id = session['id']
        existing_count = session['hr_count']
        source = session['source']
        source_file = session['source_file']
        
        print(f"\n[{session_id}] {session['name']} ({session['session_date']})")
        
        # Skip if already has samples (unless --force)
        if existing_count > 0 and not args.force:
            print(f"  Already has {existing_count} HR samples, skipping")
            skipped += 1
            continue
        
        # Find FIT file
        fit_path = find_fit_file(source, source_file)
        if not fit_path:
            print(f"  ERROR: FIT file not found: {source_file}")
            failed += 1
            continue
        
        # Extract HR samples
        samples = extract_hr_samples_from_fit(fit_path)
        if not samples:
            print(f"  WARN: No HR samples found in FIT file")
            failed += 1
            continue
        
        hr_source = f"{source}_fit"
        
        if args.dry_run:
            print(f"  Would insert {len(samples)} HR samples ({hr_source})")
            backfilled += 1
            total_samples += len(samples)
            continue
        
        # Delete existing samples if --force
        if existing_count > 0 and args.force:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM hr_samples WHERE endurance_session_id = %s", (session_id,))
            conn.commit()
            print(f"  Deleted {existing_count} existing samples")
        
        # Insert new samples
        count = insert_hr_samples(conn, session_id, samples, hr_source)
        print(f"  ✓ Inserted {count} HR samples ({hr_source})")
        backfilled += 1
        total_samples += count
    
    conn.close()
    
    print("\n" + "=" * 60)
    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode}Summary: {backfilled} backfilled, {skipped} skipped, {failed} failed")
    print(f"{mode}Total HR samples: {total_samples}")


if __name__ == "__main__":
    main()
