#!/usr/bin/env python3
"""
Sync workout data from Neo4j to Postgres analytics database.

Run: python scripts/sync_neo4j_to_postgres.py
"""

import os
import json
from neo4j import GraphDatabase
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

# Postgres connection
PG_URI = os.getenv("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def get_neo4j_workouts():
    """Extract all workouts from Neo4j."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    MATCH (w:Workout)
    OPTIONAL MATCH (w)-[:HAS_BLOCK]->(wb:WorkoutBlock)-[:CONTAINS]->(s:Set)
    OPTIONAL MATCH (s)-[:OF_EXERCISE]->(e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
    WITH w, 
         COUNT(DISTINCT s) as set_count,
         SUM(COALESCE(s.load_lbs, 0) * COALESCE(s.reps, 0)) as total_volume,
         COLLECT(DISTINCT mp.name) as patterns
    RETURN w.id as neo4j_id,
           toString(w.date) as workout_date,
           w.name as workout_name,
           w.type as workout_type,
           w.duration_minutes as duration_minutes,
           set_count,
           total_volume as total_volume_lbs,
           patterns,
           w.source as source
    ORDER BY w.date DESC
    """
    
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        workouts = [dict(record) for record in result]
    
    driver.close()
    return workouts


def load_to_postgres(workouts):
    """Load workouts into Postgres."""
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # Prepare data for insertion
    rows = []
    for w in workouts:
        if not w['workout_date']:
            continue
            
        rows.append((
            w['neo4j_id'],
            w['workout_date'],
            w['workout_name'],
            w['workout_type'],
            w['duration_minutes'],
            w['set_count'],
            float(w['total_volume_lbs']) if w['total_volume_lbs'] else 0,
            json.dumps(w['patterns']) if w['patterns'] else '[]',
            w.get('source', 'imported')
        ))
    
    # Upsert
    sql = """
    INSERT INTO workout_summaries 
        (neo4j_id, workout_date, workout_name, workout_type, duration_minutes, 
         set_count, total_volume_lbs, patterns, source)
    VALUES %s
    ON CONFLICT (neo4j_id) DO UPDATE SET
        workout_date = EXCLUDED.workout_date,
        workout_name = EXCLUDED.workout_name,
        workout_type = EXCLUDED.workout_type,
        duration_minutes = EXCLUDED.duration_minutes,
        set_count = EXCLUDED.set_count,
        total_volume_lbs = EXCLUDED.total_volume_lbs,
        patterns = EXCLUDED.patterns,
        source = EXCLUDED.source,
        synced_at = NOW()
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    
    print(f"Synced {len(rows)} workouts to Postgres")
    
    # Refresh materialized views
    print("Refreshing materialized views...")
    cur.execute("REFRESH MATERIALIZED VIEW training_load_daily;")
    cur.execute("REFRESH MATERIALIZED VIEW readiness_daily;")
    conn.commit()
    
    cur.close()
    conn.close()


def main():
    print("Extracting workouts from Neo4j...")
    workouts = get_neo4j_workouts()
    print(f"Found {len(workouts)} workouts")
    
    print("Loading to Postgres...")
    load_to_postgres(workouts)
    
    print("Done!")


if __name__ == "__main__":
    main()
