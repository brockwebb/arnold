#!/usr/bin/env python3
"""
Import all workout history files into CYBERDYNE-CORE.

Internal Codename: SKYNET-READER
Batch import workout logs and create temporal chains.

Usage:
    python scripts/import_workout_history.py
    python scripts/import_workout_history.py --source /path/to/workouts/
    python scripts/import_workout_history.py --limit 10  # Test with first 10 files
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.parser import parse_workout_file, normalize_exercise_name


def find_workout_files(source_dir: Path) -> List[Path]:
    """Find all workout markdown files in the source directory."""
    return sorted(source_dir.glob("*.md"))


def create_workout_node(graph: ArnoldGraph, parsed: Dict[str, Any]) -> str:
    """
    Create Workout node in Neo4j.

    Returns:
        workout_id
    """
    fm = parsed['frontmatter']
    filename = parsed['filename']

    # Generate workout ID
    workout_date = fm.get('date')
    if isinstance(workout_date, datetime):
        workout_date = workout_date.date()

    workout_id = f"{workout_date}_{fm.get('type', 'workout')}"

    # Prepare node properties
    props = {
        'id': workout_id,
        'source_file': filename,
        'date': str(workout_date) if workout_date else None,
        'type': fm.get('type'),
        'sport': fm.get('sport'),
        'periodization_phase': fm.get('periodization_phase'),
        'tags_raw': fm.get('tags', []),
        'goals_raw': fm.get('goals', []),
        'equipment_raw': fm.get('equipment_used', []),
        'injury_considerations': fm.get('injury_considerations', []),
        'deviations': fm.get('deviations', []),
        'intended_intensity': fm.get('intended_intensity'),
        'perceived_intensity': fm.get('perceived_intensity'),
        'muscle_focus': fm.get('muscle_focus', []),
        'energy_systems': fm.get('energy_systems', [])
    }

    # Remove None values
    props = {k: v for k, v in props.items() if v is not None}

    query = """
    MERGE (w:Workout {id: $id})
    SET w += $props
    RETURN w.id as id
    """

    result = graph.execute_write(query, {'id': workout_id, 'props': props})
    return workout_id


def create_exercise_instances(graph: ArnoldGraph, workout_id: str, parsed: Dict[str, Any]) -> int:
    """
    Create ExerciseInstance nodes for exercises in the workout.

    Returns:
        Number of instances created
    """
    instances_created = 0

    for section in parsed['sections']:
        section_name = section['name']

        for ex in section['exercises']:
            # Generate instance ID
            instance_id = f"{workout_id}_ex_{instances_created + 1}"

            # Calculate totals
            sets_data = ex.get('sets', [])
            total_sets = len(sets_data)
            total_reps = sum(s.get('reps', 0) for s in sets_data if isinstance(s.get('reps'), int))
            max_weight = max((s.get('weight', 0) for s in sets_data if isinstance(s.get('weight'), (int, float))), default=None)

            # Prepare instance properties
            props = {
                'id': instance_id,
                'exercise_name_raw': ex['name_raw'],
                'section': section_name,
                'order_in_workout': ex.get('order', 0),
                'total_sets': total_sets,
                'notes': ex.get('notes')
            }

            if total_reps > 0:
                props['total_reps'] = total_reps
            if max_weight is not None:
                props['max_weight'] = max_weight
            if ex.get('weight'):
                props['weight'] = ex['weight']
                props['weight_unit'] = ex.get('weight_unit', 'lb')

            # Remove None values
            props = {k: v for k, v in props.items() if v is not None}

            # Create instance node
            query = """
            MERGE (ei:ExerciseInstance {id: $id})
            SET ei += $props
            """
            graph.execute_write(query, {'id': instance_id, 'props': props})

            # Link to workout
            query = """
            MATCH (w:Workout {id: $workout_id})
            MATCH (ei:ExerciseInstance {id: $instance_id})
            MERGE (w)-[:CONTAINS]->(ei)
            """
            graph.execute_write(query, {
                'workout_id': workout_id,
                'instance_id': instance_id
            })

            # Try to link to Exercise node (fuzzy match)
            normalized_name = normalize_exercise_name(ex['name_raw'])
            exercise_id = find_matching_exercise(graph, normalized_name)

            if exercise_id:
                query = """
                MATCH (ei:ExerciseInstance {id: $instance_id})
                MATCH (e:Exercise {id: $exercise_id})
                MERGE (ei)-[:INSTANCE_OF]->(e)
                """
                graph.execute_write(query, {
                    'instance_id': instance_id,
                    'exercise_id': exercise_id
                })

            instances_created += 1

    return instances_created


def find_matching_exercise(graph: ArnoldGraph, normalized_name: str) -> str:
    """
    Try to match normalized exercise name to existing Exercise node.

    Returns exercise_id if found, None otherwise.
    """
    # Try exact match on normalized name
    query = """
    MATCH (e:Exercise)
    WHERE toLower(e.name) = $name
    RETURN e.id as id
    LIMIT 1
    """
    result = graph.execute_query(query, {'name': normalized_name})

    if result:
        return result[0]['id']

    # Try partial match (contains)
    query = """
    MATCH (e:Exercise)
    WHERE toLower(e.name) CONTAINS $name OR $name CONTAINS toLower(e.name)
    RETURN e.id as id, e.name as name
    LIMIT 1
    """
    result = graph.execute_query(query, {'name': normalized_name})

    if result:
        return result[0]['id']

    return None


def create_temporal_chain(graph: ArnoldGraph):
    """
    Create PREVIOUS relationships between workouts in chronological order.
    """
    print("\nCreating temporal chain...")

    query = """
    MATCH (w:Workout)
    WHERE w.date IS NOT NULL
    WITH w ORDER BY w.date
    WITH collect(w) as workouts
    UNWIND range(1, size(workouts)-1) as i
    WITH workouts[i] as current, workouts[i-1] as previous
    MERGE (current)-[:PREVIOUS]->(previous)
    RETURN count(*) as relationships_created
    """

    result = graph.execute_query(query)
    count = result[0]['relationships_created'] if result else 0
    print(f"  ✓ Created {count} PREVIOUS relationships")


def main():
    parser = argparse.ArgumentParser(description="Import workout history")
    parser.add_argument(
        "--source",
        type=str,
        help="Source directory containing workout markdown files"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to import (for testing)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SKYNET-READER: Workout History Import")
    print("=" * 60)

    # Determine source directory
    if args.source:
        source_dir = Path(args.source)
    else:
        # Default from config
        source_dir = Path("/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise/")

    if not source_dir.exists():
        print(f"❌ Source directory not found: {source_dir}")
        sys.exit(1)

    # Find workout files
    print(f"\nScanning {source_dir}...")
    workout_files = find_workout_files(source_dir)

    if args.limit:
        workout_files = workout_files[:args.limit]

    print(f"Found {len(workout_files)} workout files")

    if not workout_files:
        print("❌ No workout files found")
        sys.exit(1)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Import workouts
    print(f"\nImporting {len(workout_files)} workouts...")
    print("-" * 60)

    stats = {
        'workouts_imported': 0,
        'instances_created': 0,
        'parse_failures': []
    }

    for i, filepath in enumerate(workout_files, 1):
        try:
            # Parse
            parsed = parse_workout_file(filepath)

            # Create workout node
            workout_id = create_workout_node(graph, parsed)

            # Create exercise instances
            instances = create_exercise_instances(graph, workout_id, parsed)

            stats['workouts_imported'] += 1
            stats['instances_created'] += instances

            # Progress
            if i % 20 == 0 or i == len(workout_files):
                print(f"  Processed {i}/{len(workout_files)} workouts...")

        except Exception as e:
            print(f"  ! Failed to import {filepath.name}: {e}")
            stats['parse_failures'].append({
                'file': filepath.name,
                'error': str(e)
            })

    print("-" * 60)

    # Create temporal chain
    create_temporal_chain(graph)

    # Final statistics
    print("\n" + "=" * 60)
    print("Import Summary")
    print("=" * 60)
    print(f"Workouts imported: {stats['workouts_imported']}")
    print(f"Exercise instances created: {stats['instances_created']}")
    print(f"Parse failures: {len(stats['parse_failures'])}")

    if stats['parse_failures']:
        print("\nFailed files:")
        for failure in stats['parse_failures'][:10]:
            print(f"  - {failure['file']}: {failure['error']}")
        if len(stats['parse_failures']) > 10:
            print(f"  ... and {len(stats['parse_failures']) - 10} more")

    # Match rate
    query = """
    MATCH (ei:ExerciseInstance)
    OPTIONAL MATCH (ei)-[:INSTANCE_OF]->(e:Exercise)
    RETURN
        count(ei) as total,
        count(e) as linked,
        round(100.0 * count(e) / count(ei), 1) as match_rate_pct
    """
    result = graph.execute_query(query)
    if result:
        r = result[0]
        print(f"\nExercise matching:")
        print(f"  Total instances: {r['total']}")
        print(f"  Linked to exercises: {r['linked']}")
        print(f"  Match rate: {r['match_rate_pct']}%")

    print("\n" + "=" * 60)
    print("✓ Import complete")
    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
