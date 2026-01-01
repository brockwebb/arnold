#!/usr/bin/env python3
"""
Export Neo4j workout data to raw JSON and staging Parquet.
Follows the data lake pattern: raw (native) -> staging (parquet) -> analytics (duckdb)
"""

import json
import os
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use defaults

from neo4j import GraphDatabase
import pyarrow as pa
import pyarrow.parquet as pq

# Paths
ARNOLD_ROOT = Path("/Users/brock/Documents/GitHub/arnold")
RAW_DIR = ARNOLD_ROOT / "data" / "raw" / "neo4j_snapshots"
STAGING_DIR = ARNOLD_ROOT / "data" / "staging"

# Neo4j connection (same as MCP servers use)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


def get_session(driver):
    return driver.session(database=NEO4J_DATABASE)


def export_workouts(driver):
    """Export all workouts to raw JSON and staging Parquet."""
    print("Exporting workouts...")
    
    query = """
    MATCH (p:Person {name: 'Brock Webb'})-[:PERFORMED]->(w:Workout)
    RETURN 
      w.id as workout_id,
      toString(w.date) as date,
      w.type as type,
      w.duration_minutes as duration_min,
      w.notes as notes
    ORDER BY w.date
    """
    
    with get_session(driver) as session:
        result = session.run(query)
        workouts = [dict(record) for record in result]
    
    print(f"  Found {len(workouts)} workouts")
    
    # Save raw JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"workouts_{timestamp}.json"
    with open(raw_file, 'w') as f:
        json.dump(workouts, f, indent=2)
    print(f"  Raw: {raw_file}")
    
    # Convert to Parquet
    table = pa.Table.from_pylist(workouts)
    staging_file = STAGING_DIR / "workouts.parquet"
    pq.write_table(table, staging_file)
    print(f"  Staging: {staging_file}")
    
    return len(workouts)


def export_sets(driver):
    """Export all sets with exercise info to raw JSON and staging Parquet."""
    print("Exporting sets...")
    
    query = """
    MATCH (w:Workout)-[:HAS_BLOCK]->(wb:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
    OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
    WITH w, s, e, collect(DISTINCT mp.name) as patterns
    RETURN 
      s.id as set_id,
      w.id as workout_id,
      toString(w.date) as date,
      s.set_number as set_number,
      s.reps as reps,
      s.load_lbs as load_lbs,
      s.rpe as rpe,
      s.duration_seconds as duration_sec,
      s.distance_miles as distance_miles,
      s.notes as notes,
      e.id as exercise_id,
      e.name as exercise_name,
      patterns
    ORDER BY w.date, s.set_number
    """
    
    with get_session(driver) as session:
        result = session.run(query)
        sets = [dict(record) for record in result]
    
    print(f"  Found {len(sets)} sets")
    
    # Save raw JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"sets_{timestamp}.json"
    with open(raw_file, 'w') as f:
        json.dump(sets, f, indent=2)
    print(f"  Raw: {raw_file}")
    
    # Flatten patterns list to string for Parquet (can't have nested lists easily)
    for s in sets:
        s['patterns'] = ','.join(s['patterns']) if s['patterns'] else None
    
    # Convert to Parquet
    table = pa.Table.from_pylist(sets)
    staging_file = STAGING_DIR / "sets.parquet"
    pq.write_table(table, staging_file)
    print(f"  Staging: {staging_file}")
    
    return len(sets)


def export_exercises(driver):
    """Export exercise reference data."""
    print("Exporting exercises...")
    
    query = """
    MATCH (e:Exercise)
    OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
    WITH e, collect(DISTINCT mp.name) as patterns
    RETURN 
      e.id as exercise_id,
      e.name as name,
      e.equipment as equipment,
      e.force as force_type,
      e.mechanic as mechanic,
      patterns
    ORDER BY e.name
    """
    
    with get_session(driver) as session:
        result = session.run(query)
        exercises = [dict(record) for record in result]
    
    print(f"  Found {len(exercises)} exercises")
    
    # Save raw JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"exercises_{timestamp}.json"
    with open(raw_file, 'w') as f:
        json.dump(exercises, f, indent=2)
    print(f"  Raw: {raw_file}")
    
    # Flatten patterns for Parquet
    for ex in exercises:
        ex['patterns'] = ','.join(ex['patterns']) if ex['patterns'] else None
    
    # Convert to Parquet
    table = pa.Table.from_pylist(exercises)
    staging_file = STAGING_DIR / "exercises.parquet"
    pq.write_table(table, staging_file)
    print(f"  Staging: {staging_file}")
    
    return len(exercises)


def export_movement_patterns(driver):
    """Export movement pattern reference data."""
    print("Exporting movement patterns...")
    
    query = """
    MATCH (mp:MovementPattern)
    RETURN 
      mp.id as pattern_id,
      mp.name as name,
      mp.plane as plane_of_motion
    ORDER BY mp.name
    """
    
    with get_session(driver) as session:
        result = session.run(query)
        patterns = [dict(record) for record in result]
    
    print(f"  Found {len(patterns)} movement patterns")
    
    # Save raw JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"movement_patterns_{timestamp}.json"
    with open(raw_file, 'w') as f:
        json.dump(patterns, f, indent=2)
    print(f"  Raw: {raw_file}")
    
    # Convert to Parquet
    table = pa.Table.from_pylist(patterns)
    staging_file = STAGING_DIR / "movement_patterns.parquet"
    pq.write_table(table, staging_file)
    print(f"  Staging: {staging_file}")
    
    return len(patterns)


def main():
    print("=" * 60)
    print("Arnold Analytics Export")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Ensure directories exist
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    
    driver = get_driver()
    
    try:
        workout_count = export_workouts(driver)
        set_count = export_sets(driver)
        exercise_count = export_exercises(driver)
        pattern_count = export_movement_patterns(driver)
        
        print("=" * 60)
        print("Export complete!")
        print(f"  Workouts: {workout_count}")
        print(f"  Sets: {set_count}")
        print(f"  Exercises: {exercise_count}")
        print(f"  Patterns: {pattern_count}")
        print("=" * 60)
        
    finally:
        driver.close()


if __name__ == "__main__":
    main()
