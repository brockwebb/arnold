#!/usr/bin/env python3
"""
Ingest exercise enrichment JSON files into Neo4j.

Reads: data/enrichment/exercises/*.json
Writes: Neo4j INVOLVES and TARGETS relationships

Usage:
    python scripts/ingest_exercise_enrichment.py              # Process all JSON files
    python scripts/ingest_exercise_enrichment.py --dry-run    # Show what would be created
    python scripts/ingest_exercise_enrichment.py --force      # Replace existing relationships

Idempotent: Uses MERGE to create or update relationships.
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from neo4j import GraphDatabase

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
EXERCISES_DIR = PROJECT_ROOT / "data" / "enrichment" / "exercises"

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")


def load_exercise_files(exercises_dir: Path) -> list[dict]:
    """Load all JSON files from the exercises directory."""
    exercises = []
    for filepath in sorted(exercises_dir.glob('*.json')):
        with open(filepath) as f:
            data = json.load(f)
            data['_filepath'] = filepath
            exercises.append(data)
    return exercises


def verify_exercise_exists(tx, exercise_id: str) -> bool:
    """Check if exercise exists in Neo4j."""
    result = tx.run("""
        MATCH (e:Exercise {id: $id})
        RETURN e.name as name
    """, id=exercise_id)
    record = result.single()
    return record is not None


def clear_existing_relationships(tx, exercise_id: str, rel_type: str):
    """Delete existing relationships of a type for an exercise."""
    if rel_type == 'INVOLVES':
        tx.run("""
            MATCH (e:Exercise {id: $id})-[r:INVOLVES]->()
            DELETE r
        """, id=exercise_id)
    elif rel_type == 'TARGETS':
        tx.run("""
            MATCH (e:Exercise {id: $id})-[r:TARGETS]->()
            DELETE r
        """, id=exercise_id)


def create_involves_relationships(tx, exercise_id: str, patterns: list[dict], source_type: str):
    """Create INVOLVES relationships to MovementPatterns."""
    for pattern in patterns:
        result = tx.run("""
            MATCH (e:Exercise {id: $exercise_id})
            MATCH (mp:MovementPattern {name: $pattern_name})
            MERGE (e)-[r:INVOLVES]->(mp)
            SET r.source = $source,
                r.confidence = $confidence,
                r.classified_at = datetime(),
                r.human_verified = true,
                r.verified_at = datetime(),
                r.verified_by = 'brock'
            RETURN mp.name as pattern
        """, 
            exercise_id=exercise_id,
            pattern_name=pattern['name'],
            source=source_type,
            confidence=pattern.get('confidence', 0.9)
        )
        record = result.single()
        if record is None:
            print(f"    WARNING: Pattern not found: {pattern['name']}")


def create_targets_relationships(tx, exercise_id: str, muscles: dict, source_type: str):
    """Create TARGETS relationships to Muscles."""
    
    # Primary muscles
    for muscle_name in muscles.get('primary', []):
        result = tx.run("""
            MATCH (e:Exercise {id: $exercise_id})
            MATCH (m) WHERE (m:Muscle OR m:MuscleGroup) AND m.name = $muscle_name
            MERGE (e)-[r:TARGETS]->(m)
            SET r.role = 'primary',
                r.source = $source,
                r.confidence = 0.95,
                r.human_verified = true,
                r.verified_at = datetime(),
                r.verified_by = 'brock'
            RETURN m.name as muscle
        """,
            exercise_id=exercise_id,
            muscle_name=muscle_name,
            source=source_type
        )
        record = result.single()
        if record is None:
            print(f"    WARNING: Muscle not found: {muscle_name}")
    
    # Secondary muscles
    for muscle_name in muscles.get('secondary', []):
        result = tx.run("""
            MATCH (e:Exercise {id: $exercise_id})
            MATCH (m) WHERE (m:Muscle OR m:MuscleGroup) AND m.name = $muscle_name
            MERGE (e)-[r:TARGETS]->(m)
            SET r.role = 'secondary',
                r.source = $source,
                r.confidence = 0.90,
                r.human_verified = true,
                r.verified_at = datetime(),
                r.verified_by = 'brock'
            RETURN m.name as muscle
        """,
            exercise_id=exercise_id,
            muscle_name=muscle_name,
            source=source_type
        )
        record = result.single()
        if record is None:
            print(f"    WARNING: Muscle not found: {muscle_name}")


def process_exercise(driver, exercise: dict, force: bool = False, dry_run: bool = False) -> dict:
    """Process a single exercise JSON file."""
    
    exercise_id = exercise['exercise_id']
    exercise_name = exercise['exercise_name']
    source_type = exercise['source']['type']
    patterns = exercise.get('movement_patterns', [])
    muscles = exercise.get('muscles', {})
    
    stats = {
        'exercise': exercise_name,
        'patterns': len(patterns),
        'primary_muscles': len(muscles.get('primary', [])),
        'secondary_muscles': len(muscles.get('secondary', [])),
        'status': 'pending'
    }
    
    if dry_run:
        stats['status'] = 'dry_run'
        return stats
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Verify exercise exists
        exists = session.execute_read(verify_exercise_exists, exercise_id)
        if not exists:
            stats['status'] = 'exercise_not_found'
            return stats
        
        # Clear existing if force
        if force:
            session.execute_write(clear_existing_relationships, exercise_id, 'INVOLVES')
            session.execute_write(clear_existing_relationships, exercise_id, 'TARGETS')
        
        # Create relationships
        session.execute_write(create_involves_relationships, exercise_id, patterns, source_type)
        session.execute_write(create_targets_relationships, exercise_id, muscles, source_type)
        
        stats['status'] = 'success'
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Ingest exercise enrichment into Neo4j')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created')
    parser.add_argument('--force', action='store_true', help='Replace existing relationships')
    parser.add_argument('--file', type=str, help='Process only this JSON file')
    args = parser.parse_args()
    
    # Load exercise files
    print(f"Loading exercise files from {EXERCISES_DIR}...")
    exercises = load_exercise_files(EXERCISES_DIR)
    print(f"Found {len(exercises)} exercise files")
    
    if args.file:
        exercises = [e for e in exercises if e['_filepath'].name == args.file]
        print(f"Filtered to {len(exercises)} matching '{args.file}'")
    
    if not exercises:
        print("No exercises to process!")
        return
    
    # Connect to Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        # Process each exercise
        print(f"\n{'DRY RUN - ' if args.dry_run else ''}Processing {len(exercises)} exercises...")
        
        results = []
        for exercise in exercises:
            print(f"\n  {exercise['exercise_name']} ({exercise['exercise_id']})")
            
            stats = process_exercise(driver, exercise, force=args.force, dry_run=args.dry_run)
            results.append(stats)
            
            if stats['status'] == 'exercise_not_found':
                print(f"    ERROR: Exercise not found in Neo4j")
            else:
                print(f"    Patterns: {stats['patterns']}")
                print(f"    Primary muscles: {stats['primary_muscles']}")
                print(f"    Secondary muscles: {stats['secondary_muscles']}")
        
        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        success = sum(1 for r in results if r['status'] == 'success')
        not_found = sum(1 for r in results if r['status'] == 'exercise_not_found')
        dry_run = sum(1 for r in results if r['status'] == 'dry_run')
        
        if args.dry_run:
            print(f"Would process: {dry_run} exercises")
        else:
            print(f"Success: {success}")
            if not_found:
                print(f"Not found in Neo4j: {not_found}")
                print("  These exercises need to be created first")
        
        print(f"\nRun sync_exercise_relationships.py to update Postgres cache")
        
    finally:
        driver.close()


if __name__ == '__main__':
    main()
