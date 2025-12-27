#!/usr/bin/env python3
"""
Import exercise database (free-exercise-db) into Arnold graph.

This script:
1. Clones/updates free-exercise-db repository
2. Parses exercise JSON files
3. Creates Exercise and Equipment nodes
4. Links exercises to muscles and equipment

Usage:
    python scripts/import_exercises.py
    python scripts/import_exercises.py --update  # Force update repo
"""

import sys
import argparse
import json
import yaml
import subprocess
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph


def load_config():
    """Load Arnold configuration."""
    config_path = Path(__file__).parent.parent / "config" / "arnold.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def clone_or_update_repo(repo_url: str, local_path: Path) -> bool:
    """Clone the exercise database repository or update if it exists."""
    if local_path.exists():
        print(f"Repository already exists at {local_path}")
        print("Updating...")
        try:
            subprocess.run(
                ["git", "-C", str(local_path), "pull"],
                check=True,
                capture_output=True
            )
            print("✓ Updated repository")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Update failed: {e}")
            return False
    else:
        print(f"Cloning {repo_url}...")
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", repo_url, str(local_path)],
                check=True,
                capture_output=True
            )
            print(f"✓ Cloned to {local_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Clone failed: {e}")
            return False


def normalize_muscle_name(name: str) -> str:
    """Normalize muscle names for matching."""
    # Convert to lowercase, remove special chars
    name = name.lower().strip()
    name = name.replace('_', ' ').replace('-', ' ')
    return name


def find_muscle_in_graph(graph: ArnoldGraph, muscle_name: str) -> str:
    """
    Try to find a muscle node by fuzzy matching.

    Returns the muscle ID if found, otherwise creates a custom muscle node.
    """
    normalized = normalize_muscle_name(muscle_name)

    # Try exact match on name
    query = """
    MATCH (m:Muscle)
    WHERE toLower(m.name) CONTAINS $name
    RETURN m.id as id
    LIMIT 1
    """
    result = graph.execute_query(query, {'name': normalized})

    if result:
        return result[0]['id']

    # Try synonym match
    query = """
    MATCH (m:Muscle)
    WHERE any(syn IN m.synonyms WHERE toLower(syn) CONTAINS $name)
    RETURN m.id as id
    LIMIT 1
    """
    result = graph.execute_query(query, {'name': normalized})

    if result:
        return result[0]['id']

    # Create custom muscle node for exercises
    muscle_id = f"CUSTOM:{muscle_name.upper().replace(' ', '_')}"
    query = """
    MERGE (m:Muscle {id: $id})
    SET m.name = $name,
        m.source = 'free-exercise-db',
        m.synonyms = []
    RETURN m.id as id
    """
    graph.execute_write(query, {'id': muscle_id, 'name': muscle_name})

    return muscle_id


def import_exercises_to_graph(exercises_path: Path, graph: ArnoldGraph):
    """Parse free-exercise-db and import to Neo4j."""
    # Find all JSON files
    json_files = list(exercises_path.glob("exercises/**/*.json"))
    print(f"\nFound {len(json_files)} exercise files")

    if not json_files:
        print("❌ No exercise JSON files found")
        return

    # Track unique equipment
    equipment_set = set()
    exercises_imported = 0
    muscles_linked = 0

    print("\nImporting exercises...")

    for json_file in json_files:
        try:
            with open(json_file) as f:
                data = json.load(f)

            # Extract exercise data
            exercise_id = f"EXERCISE:{data.get('id', data['name'].upper().replace(' ', '_'))}"
            exercise_data = {
                'id': exercise_id,
                'name': data['name'],
                'aliases': data.get('aliases', []),
                'category': data.get('category', 'unknown'),
                'force_type': data.get('force', 'unknown'),
                'mechanic': data.get('mechanic', 'unknown'),
                'difficulty': data.get('level', 'beginner'),
                'instructions': ' '.join(data.get('instructions', [])),
            }

            # Create exercise node
            query = """
            MERGE (e:Exercise {id: $id})
            SET e.name = $name,
                e.aliases = $aliases,
                e.category = $category,
                e.force_type = $force_type,
                e.mechanic = $mechanic,
                e.difficulty = $difficulty,
                e.instructions = $instructions,
                e.source = 'free-exercise-db'
            """
            graph.execute_write(query, exercise_data)
            exercises_imported += 1

            # Link to primary muscles
            primary_muscles = data.get('primaryMuscles', [])
            for muscle_name in primary_muscles:
                muscle_id = find_muscle_in_graph(graph, muscle_name)
                query = """
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (e)-[:TARGETS {role: 'primary'}]->(m)
                """
                graph.execute_write(query, {
                    'exercise_id': exercise_id,
                    'muscle_id': muscle_id
                })
                muscles_linked += 1

            # Link to secondary muscles
            secondary_muscles = data.get('secondaryMuscles', [])
            for muscle_name in secondary_muscles:
                muscle_id = find_muscle_in_graph(graph, muscle_name)
                query = """
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (e)-[:TARGETS {role: 'synergist'}]->(m)
                """
                graph.execute_write(query, {
                    'exercise_id': exercise_id,
                    'muscle_id': muscle_id
                })
                muscles_linked += 1

            # Track equipment
            equipment = data.get('equipment', 'none')
            if equipment and equipment != 'none':
                equipment_set.add(equipment)

                # Create equipment node and link
                equipment_id = f"EQUIPMENT:{equipment.upper().replace(' ', '_')}"
                query = """
                MERGE (eq:Equipment {id: $id})
                SET eq.name = $name,
                    eq.category = $category,
                    eq.user_has = false
                """
                graph.execute_write(query, {
                    'id': equipment_id,
                    'name': equipment,
                    'category': equipment
                })

                query = """
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (eq:Equipment {id: $equipment_id})
                MERGE (e)-[:REQUIRES]->(eq)
                """
                graph.execute_write(query, {
                    'exercise_id': exercise_id,
                    'equipment_id': equipment_id
                })

        except Exception as e:
            print(f"  ! Error processing {json_file.name}: {e}")
            continue

        # Progress indicator
        if exercises_imported % 100 == 0:
            print(f"  Processed {exercises_imported} exercises...")

    print(f"\n✓ Imported {exercises_imported} exercises")
    print(f"✓ Created {muscles_linked} muscle relationships")
    print(f"✓ Found {len(equipment_set)} unique equipment types")


def main():
    parser = argparse.ArgumentParser(description="Import exercise database")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Force update of exercise repository"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Exercise Database Importer")
    print("free-exercise-db → Arnold")
    print("=" * 60)

    # Load configuration
    config = load_config()
    exercise_config = config['data_sources']['exercises']
    local_path = Path(exercise_config['local_path'])

    # Clone or update repository
    if args.update or not local_path.exists():
        if not clone_or_update_repo(exercise_config['repo'], local_path):
            sys.exit(1)
    else:
        print(f"Using existing repository: {local_path}")

    # Connect to graph
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Import
    import_exercises_to_graph(local_path, graph)

    # Show statistics
    from arnold.graph import print_stats
    stats = graph.get_stats()
    print_stats(stats)

    graph.close()

    print("\n" + "=" * 60)
    print("✓ Import complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
