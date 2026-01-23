#!/usr/bin/env python3
"""
Sync exercise-pattern relationships from Neo4j to Postgres.

This mirrors the (:Exercise)-[:INVOLVES]->(:MovementPattern) relationships
and (:Exercise)-[:TARGETS]->(:Muscle) relationships to Postgres for
efficient analytics joins.

Run: python scripts/sync_exercise_patterns.py

Part of the analytics data pipeline - called by sync_pipeline.py
"""

import os
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


def get_exercise_patterns_from_neo4j():
    """
    Extract all exercises with their patterns and primary muscles from Neo4j.

    Returns list of dicts with:
        - exercise_id
        - exercise_name
        - patterns (list of pattern names)
        - primary_muscles (list of muscle names)
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    query = """
    MATCH (e:Exercise)
    OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
    OPTIONAL MATCH (e)-[:TARGETS {role: 'primary'}]->(m:Muscle)
    WITH e,
         collect(DISTINCT mp.name) AS patterns,
         collect(DISTINCT m.name) AS primary_muscles
    RETURN
        e.id AS exercise_id,
        e.name AS exercise_name,
        [p IN patterns WHERE p IS NOT NULL] AS patterns,
        [m IN primary_muscles WHERE m IS NOT NULL] AS primary_muscles
    ORDER BY e.name
    """

    exercises = []
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        for record in result:
            exercises.append({
                'exercise_id': record['exercise_id'],
                'exercise_name': record['exercise_name'],
                'patterns': record['patterns'] or [],
                'primary_muscles': record['primary_muscles'] or []
            })

    driver.close()
    return exercises


def sync_to_postgres(exercises):
    """
    Upsert exercise patterns to Postgres.
    """
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()

    # Prepare rows
    rows = [
        (
            ex['exercise_id'],
            ex['exercise_name'],
            ex['patterns'],
            ex['primary_muscles'],
            'neo4j_sync'
        )
        for ex in exercises
        if ex['exercise_id'] and ex['exercise_name']
    ]

    # Upsert
    sql = """
    INSERT INTO exercise_patterns
        (exercise_id, exercise_name, patterns, primary_muscles, source, synced_at)
    VALUES %s
    ON CONFLICT (exercise_id) DO UPDATE SET
        exercise_name = EXCLUDED.exercise_name,
        patterns = EXCLUDED.patterns,
        primary_muscles = EXCLUDED.primary_muscles,
        source = EXCLUDED.source,
        synced_at = NOW()
    """

    # Add synced_at to template
    template = "(%(exercise_id)s, %(exercise_name)s, %(patterns)s, %(primary_muscles)s, %(source)s, NOW())"

    execute_values(
        cur,
        sql,
        rows,
        template="(%s, %s, %s, %s, %s, NOW())"
    )

    conn.commit()

    # Get stats
    cur.execute("SELECT COUNT(*) FROM exercise_patterns")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM exercise_patterns WHERE cardinality(patterns) > 0")
    with_patterns = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM exercise_patterns WHERE cardinality(primary_muscles) > 0")
    with_muscles = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        'total': total,
        'with_patterns': with_patterns,
        'with_muscles': with_muscles,
        'synced': len(rows)
    }


def main():
    """Run the sync."""
    print("=" * 60)
    print("Sync Exercise Patterns: Neo4j → Postgres")
    print("=" * 60)

    print("\n[1/2] Extracting from Neo4j...")
    exercises = get_exercise_patterns_from_neo4j()
    print(f"  Found {len(exercises)} exercises")

    # Sample check
    with_patterns = sum(1 for e in exercises if e['patterns'])
    with_muscles = sum(1 for e in exercises if e['primary_muscles'])
    print(f"  - {with_patterns} with movement patterns")
    print(f"  - {with_muscles} with primary muscles")

    print("\n[2/2] Syncing to Postgres...")
    stats = sync_to_postgres(exercises)
    print(f"  Synced: {stats['synced']} exercises")
    print(f"  Total in table: {stats['total']}")
    print(f"  With patterns: {stats['with_patterns']}")
    print(f"  With muscles: {stats['with_muscles']}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
