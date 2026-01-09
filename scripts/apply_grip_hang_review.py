#!/usr/bin/env python3
"""
Apply Grip/Hang pattern review decisions to Neo4j.

Reads the reviewed CSV and deletes INVOLVES relationships for exercises
marked as NOT being Grip/Hang pattern exercises.

Usage:
    python scripts/apply_grip_hang_review.py [--dry-run]
    
Input: data/review/grip_hang_pattern_review.csv
  - Column 'keep': T = keep relationship, F = delete relationship
  - Empty = skip (not reviewed)
"""

import csv
import sys
from pathlib import Path
from neo4j import GraphDatabase

import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Config
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

CSV_PATH = Path(__file__).parent.parent / "data" / "review" / "grip_hang_pattern_review.csv"


def load_decisions(csv_path: Path) -> tuple[list[str], list[str], int]:
    """Load review decisions from CSV.
    
    Returns:
        (keep_ids, delete_ids, skipped_count)
    """
    keep = []
    delete = []
    skipped = 0
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            exercise_id = row['exercise_id']
            decision = row.get('keep', '').strip().upper()
            
            if decision == 'T':
                keep.append(exercise_id)
            elif decision == 'F':
                delete.append(exercise_id)
            else:
                skipped += 1
    
    return keep, delete, skipped


def mark_verified(driver, exercise_ids: list[str], dry_run: bool = True):
    """Mark INVOLVES relationships as human_verified."""
    
    query = """
    MATCH (e:Exercise)-[r:INVOLVES {source: 'name_inference'}]->(mp:MovementPattern {name: 'Grip / Hang'})
    WHERE e.id IN $exercise_ids
    RETURN e.id as exercise_id, e.name as exercise_name
    """
    
    update_query = """
    MATCH (e:Exercise)-[r:INVOLVES {source: 'name_inference'}]->(mp:MovementPattern {name: 'Grip / Hang'})
    WHERE e.id IN $exercise_ids
    SET r.human_verified = true,
        r.verified_at = datetime(),
        r.verified_by = 'brock'
    RETURN count(r) as verified_count
    """
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Preview what will be verified
        result = session.run(query, exercise_ids=exercise_ids)
        records = list(result)
        
        print(f"\nRelationships to mark verified: {len(records)}")
        for rec in records[:5]:
            print(f"  ✓ {rec['exercise_name']}")
        if len(records) > 5:
            print(f"  ... and {len(records) - 5} more")
        
        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return 0
        
        # Actually update
        result = session.run(update_query, exercise_ids=exercise_ids)
        verified = result.single()['verified_count']
        print(f"\nMarked {verified} relationships as human_verified.")
        return verified


def delete_relationships(driver, exercise_ids: list[str], dry_run: bool = True):
    """Delete INVOLVES relationships to Grip/Hang pattern."""
    
    query = """
    MATCH (e:Exercise)-[r:INVOLVES {source: 'name_inference'}]->(mp:MovementPattern {name: 'Grip / Hang'})
    WHERE e.id IN $exercise_ids
    RETURN e.id as exercise_id, e.name as exercise_name
    """
    
    delete_query = """
    MATCH (e:Exercise)-[r:INVOLVES {source: 'name_inference'}]->(mp:MovementPattern {name: 'Grip / Hang'})
    WHERE e.id IN $exercise_ids
    DELETE r
    RETURN count(r) as deleted_count
    """
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Preview what will be deleted
        result = session.run(query, exercise_ids=exercise_ids)
        records = list(result)
        
        print(f"\nRelationships to delete: {len(records)}")
        for rec in records[:10]:
            print(f"  - {rec['exercise_name']}")
        if len(records) > 10:
            print(f"  ... and {len(records) - 10} more")
        
        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return 0
        
        # Actually delete
        result = session.run(delete_query, exercise_ids=exercise_ids)
        deleted = result.single()['deleted_count']
        print(f"\nDeleted {deleted} relationships.")
        return deleted


def main():
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)
    
    keep, delete, skipped = load_decisions(CSV_PATH)
    
    print(f"Review Summary:")
    print(f"  Keep (T):   {len(keep)}")
    print(f"  Delete (F): {len(delete)}")
    print(f"  Skipped:    {skipped}")
    
    if not delete and not keep:
        print("\nNo exercises reviewed. Nothing to do.")
        return
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        if keep:
            mark_verified(driver, keep, dry_run=dry_run)
        if delete:
            delete_relationships(driver, delete, dry_run=dry_run)
    finally:
        driver.close()
    
    if not dry_run:
        print("\n⚠️  Remember to re-sync Neo4j → Postgres cache:")
        print("   python scripts/sync_pipeline.py --steps relationships")


if __name__ == "__main__":
    main()
