#!/usr/bin/env python3
import os
import re
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv('/Users/brock/Documents/GitHub/arnold/.env')

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

WORKOUT_DIR = Path("/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise")

def extract_date_from_filename(filepath):
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
    return match.group(1) if match else None

def simple_exercise_extract(content):
    """Extract exercises with VERY simple regex - just get the exercises."""
    exercises = []

    # Pattern: ### 1) Exercise Name or **Exercise Name:** or 1. **Exercise Name**
    exercise_pattern = r'(?:###\s*\d*\)?\s*|^\d+\.\s*\*\*|\*\*)([A-Z][^*\n:]+?)(?:\*\*:|:|\(|$)'

    for match in re.finditer(exercise_pattern, content, re.MULTILINE):
        ex_name = match.group(1).strip()
        if len(ex_name) > 3:  # Filter garbage
            exercises.append({'name': ex_name, 'sets': [{}]})  # Minimal set data

    return exercises if exercises else None

def import_workout(filepath):
    workout_date = extract_date_from_filename(filepath)
    if not workout_date:
        return False

    try:
        content = filepath.read_text(encoding='utf-8')
        exercises = simple_exercise_extract(content)

        if not exercises:
            return False

        with driver.session(database=NEO4J_DATABASE) as session:
            # Check if exists
            exists = session.run("""
                MATCH (w:Workout {date: date($date)})
                RETURN count(w) > 0 as exists
            """, date=workout_date).single()['exists']

            if exists:
                return False

            # Create workout
            workout_id = session.run("""
                CREATE (w:Workout {
                    id: randomUUID(),
                    date: date($date),
                    type: 'workout',
                    source: 'bulk_simple_import',
                    imported_at: datetime()
                })
                RETURN w.id as id
            """, date=workout_date).single()['id']

            # Create exercises (minimal data)
            for ex_data in exercises:
                ex_id = session.run("""
                    MERGE (ex:Exercise {name: $name, source: 'user'})
                    ON CREATE SET ex.id = randomUUID()
                    RETURN ex.id as id
                """, name=ex_data['name']).single()['id']

                # Create 1 set per exercise (placeholder)
                session.run("""
                    MATCH (w:Workout {id: $workout_id})
                    MATCH (ex:Exercise {id: $ex_id})
                    CREATE (s:Set {id: randomUUID(), set_number: 1})
                    CREATE (w)-[:CONTAINS]->(s)-[:OF_EXERCISE]->(ex)
                """, workout_id=workout_id, ex_id=ex_id)

            return True

    except Exception as e:
        print(f"Error {filepath.name}: {e}")
        return False

# Run import
files = sorted([f for f in WORKOUT_DIR.glob("*.md") if re.match(r'\d{4}-\d{2}-\d{2}', f.name)])
imported = 0

for f in files:
    if import_workout(f):
        imported += 1
        print(f"✓ {f.name}")

print(f"\nImported: {imported}")
driver.close()
