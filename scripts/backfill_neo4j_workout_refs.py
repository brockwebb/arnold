#!/usr/bin/env python3
"""
Backfill Neo4j workout reference nodes from Postgres.

This script syncs workouts from the Postgres `workouts` table to Neo4j as
StrengthWorkout or EnduranceWorkout reference nodes, per ADR-002.

Run: python scripts/backfill_neo4j_workout_refs.py

Problem this solves:
- Workouts logged to Postgres after Jan 9, 2026 are missing from Neo4j
- This causes load_briefing to not show recent workouts
"""

import os
from datetime import date
from neo4j import GraphDatabase
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

# Postgres connection
PG_URI = os.getenv("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")

# Person ID (from profile.json)
PERSON_ID = "73d17934-4397-4498-ba15-52e19b2ce08f"


def get_postgres_workouts(since_date: str = "2026-01-09"):
    """Get all workouts from Postgres since given date."""
    conn = psycopg2.connect(PG_URI)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            w.workout_id,
            w.start_time::date as workout_date,
            COALESCE(w.purpose, w.notes, 'Workout') as name,
            COALESCE(w.sport_type, 'strength') as sport_type,
            w.duration_seconds / 60.0 as duration_minutes,
            COUNT(DISTINCT s.set_id) as total_sets,
            COALESCE(SUM(s.reps * s.load), 0) as total_volume_lbs
        FROM workouts w
        LEFT JOIN blocks b ON w.workout_id = b.workout_id
        LEFT JOIN sets s ON b.block_id = s.block_id
        WHERE w.start_time::date >= %s
        GROUP BY w.workout_id, w.start_time, w.purpose, w.notes, w.sport_type, w.duration_seconds
        ORDER BY w.start_time DESC
    """, [since_date])

    workouts = []
    for row in cur.fetchall():
        workouts.append({
            'workout_id': row[0],
            'date': row[1].isoformat(),
            'name': row[2],
            'sport_type': row[3],
            'duration_minutes': float(row[4]) if row[4] else None,
            'total_sets': row[5],
            'total_volume_lbs': float(row[6]) if row[6] else None
        })

    cur.close()
    conn.close()
    return workouts


def get_existing_neo4j_workout_ids():
    """Get workout IDs already in Neo4j."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    existing_ids = set()
    with driver.session(database=NEO4J_DATABASE) as session:
        # Check both Workout.id and StrengthWorkout.workout_id / EnduranceWorkout.workout_id
        result = session.run("""
            MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w)
            WHERE w:Workout OR w:StrengthWorkout OR w:EnduranceWorkout
            RETURN COALESCE(w.workout_id, w.id) as id
        """, person_id=PERSON_ID)

        for record in result:
            if record['id']:
                existing_ids.add(record['id'])

    driver.close()
    return existing_ids


def create_neo4j_workout_ref(workout: dict, driver):
    """Create a workout reference node in Neo4j."""
    sport_type = workout['sport_type'].lower()
    is_strength = sport_type in ['strength', 'strength_training', 'weight_training']

    with driver.session(database=NEO4J_DATABASE) as session:
        if is_strength:
            result = session.run("""
                MATCH (p:Person {id: $person_id})

                CREATE (sw:StrengthWorkout {
                    id: randomUUID(),
                    workout_id: $workout_id,
                    date: date($date),
                    name: $name,
                    total_volume_lbs: $total_volume_lbs,
                    total_sets: $total_sets,
                    created_at: datetime()
                })

                CREATE (p)-[:PERFORMED]->(sw)

                RETURN sw.id as id
            """,
                person_id=PERSON_ID,
                workout_id=workout['workout_id'],
                date=workout['date'],
                name=workout['name'],
                total_volume_lbs=workout['total_volume_lbs'],
                total_sets=workout['total_sets']
            )
        else:
            result = session.run("""
                MATCH (p:Person {id: $person_id})

                CREATE (ew:EnduranceWorkout {
                    id: randomUUID(),
                    workout_id: $workout_id,
                    date: date($date),
                    name: $name,
                    sport: $sport,
                    duration_minutes: $duration_minutes,
                    created_at: datetime()
                })

                CREATE (p)-[:PERFORMED]->(ew)

                RETURN ew.id as id
            """,
                person_id=PERSON_ID,
                workout_id=workout['workout_id'],
                date=workout['date'],
                name=workout['name'],
                sport=sport_type,
                duration_minutes=workout['duration_minutes']
            )

        record = result.single()
        return record['id'] if record else None


def main():
    print("=" * 60)
    print("Backfill Neo4j Workout References from Postgres")
    print("=" * 60)

    # Get Postgres workouts
    print("\n[1/3] Fetching workouts from Postgres...")
    pg_workouts = get_postgres_workouts()
    print(f"  Found {len(pg_workouts)} workouts since 2026-01-09")

    # Get existing Neo4j workout IDs
    print("\n[2/3] Checking existing Neo4j workout refs...")
    existing_ids = get_existing_neo4j_workout_ids()
    print(f"  Found {len(existing_ids)} existing workout refs in Neo4j")

    # Find missing workouts
    missing = [w for w in pg_workouts if w['workout_id'] not in existing_ids]
    print(f"  Missing: {len(missing)} workouts need to be synced")

    if not missing:
        print("\n✅ All workouts are already synced to Neo4j!")
        return

    # Create missing refs
    print("\n[3/3] Creating missing Neo4j workout refs...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    created = 0
    failed = 0
    for workout in missing:
        try:
            ref_id = create_neo4j_workout_ref(workout, driver)
            if ref_id:
                print(f"  ✅ {workout['date']}: {workout['name']} ({workout['sport_type']})")
                created += 1
            else:
                print(f"  ❌ {workout['date']}: {workout['name']} - Failed to create")
                failed += 1
        except Exception as e:
            print(f"  ❌ {workout['date']}: {workout['name']} - Error: {e}")
            failed += 1

    driver.close()

    print("\n" + "=" * 60)
    print(f"Summary: Created {created}, Failed {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
