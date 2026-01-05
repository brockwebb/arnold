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
    """Extract all workouts from Neo4j with exercise details."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Two-phase extraction: first get workout summaries, then exercise details
    
    # Phase 1: Workout summaries with patterns
    summary_query = """
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
    
    # Phase 2: Exercise details per workout
    exercise_query = """
    MATCH (w:Workout)-[:HAS_BLOCK]->(wb:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
    WITH w.id as workout_id, e.name as exercise_name, 
         COLLECT({
             set_num: s.set_number,
             reps: s.reps,
             load_lbs: s.load_lbs,
             rpe: s.rpe,
             duration_sec: s.duration_seconds
         }) as sets
    WITH workout_id, exercise_name, sets,
         SIZE(sets) as set_count,
         REDUCE(max_load = 0, s IN sets | CASE WHEN COALESCE(s.load_lbs, 0) > max_load THEN s.load_lbs ELSE max_load END) as max_load,
         REDUCE(total_reps = 0, s IN sets | total_reps + COALESCE(s.reps, 0)) as total_reps
    RETURN workout_id, 
           COLLECT({
               name: exercise_name,
               sets: set_count,
               max_load: max_load,
               total_reps: total_reps,
               set_details: sets
           }) as exercises
    """
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Get summaries
        result = session.run(summary_query)
        workouts = {r['neo4j_id']: dict(r) for r in result}
        
        # Get exercise details
        result = session.run(exercise_query)
        for r in result:
            workout_id = r['workout_id']
            if workout_id in workouts:
                workouts[workout_id]['exercises'] = r['exercises']
    
    driver.close()
    return list(workouts.values())


def load_to_postgres(workouts):
    """Load workouts into Postgres."""
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()
    
    # Prepare data for insertion
    rows = []
    for w in workouts:
        if not w['workout_date']:
            continue
        
        # Process exercises - convert Neo4j types and clean up
        exercises = w.get('exercises', [])
        if exercises:
            clean_exercises = []
            for ex in exercises:
                clean_ex = {
                    'name': ex['name'],
                    'sets': ex['sets'],
                    'max_load': float(ex['max_load']) if ex['max_load'] else None,
                    'total_reps': int(ex['total_reps']) if ex['total_reps'] else 0,
                }
                # Include set details for exercise history queries
                if ex.get('set_details'):
                    clean_ex['set_details'] = [
                        {
                            'set_num': s.get('set_num'),
                            'reps': s.get('reps'),
                            'load_lbs': float(s['load_lbs']) if s.get('load_lbs') else None,
                            'rpe': float(s['rpe']) if s.get('rpe') else None,
                            'duration_sec': s.get('duration_sec')
                        }
                        for s in ex['set_details']
                    ]
                clean_exercises.append(clean_ex)
            exercises_json = json.dumps(clean_exercises)
        else:
            exercises_json = None
            
        rows.append((
            w['neo4j_id'],
            w['workout_date'],
            w['workout_name'],
            w['workout_type'],
            w['duration_minutes'],
            w['set_count'],
            float(w['total_volume_lbs']) if w['total_volume_lbs'] else 0,
            json.dumps(w['patterns']) if w['patterns'] else '[]',
            exercises_json,
            w.get('source', 'imported')
        ))
    
    # Upsert
    sql = """
    INSERT INTO workout_summaries 
        (neo4j_id, workout_date, workout_name, workout_type, duration_minutes, 
         set_count, total_volume_lbs, patterns, exercises, source)
    VALUES %s
    ON CONFLICT (neo4j_id) DO UPDATE SET
        workout_date = EXCLUDED.workout_date,
        workout_name = EXCLUDED.workout_name,
        workout_type = EXCLUDED.workout_type,
        duration_minutes = EXCLUDED.duration_minutes,
        set_count = EXCLUDED.set_count,
        total_volume_lbs = EXCLUDED.total_volume_lbs,
        patterns = EXCLUDED.patterns,
        exercises = EXCLUDED.exercises,
        source = EXCLUDED.source,
        synced_at = NOW()
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    
    print(f"Synced {len(rows)} workouts to Postgres")
    
    # Refresh materialized views that depend on workout_summaries
    print("Refreshing materialized views...")
    cur.execute("REFRESH MATERIALIZED VIEW biometric_trends;")
    cur.execute("REFRESH MATERIALIZED VIEW training_trends;")
    conn.commit()
    
    cur.close()
    conn.close()


def main():
    print("Extracting workouts from Neo4j...")
    workouts = get_neo4j_workouts()
    print(f"Found {len(workouts)} workouts")
    
    # Count workouts with exercise data
    with_exercises = sum(1 for w in workouts if w.get('exercises'))
    print(f"  - {with_exercises} with exercise details")
    
    print("Loading to Postgres...")
    load_to_postgres(workouts)
    
    print("Done!")


if __name__ == "__main__":
    main()
