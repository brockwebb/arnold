#!/usr/bin/env python3
"""
LLM-Powered Workout Batch Ingestion - PARALLEL VERSION

Uses ThreadPoolExecutor to process multiple workouts simultaneously.

Usage:
    python scripts/llm_ingest_workouts_parallel.py --full
    python scripts/llm_ingest_workouts_parallel.py --test
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.llm_ingest import LLMWorkoutParser, get_exercise_database_from_graph

MAX_WORKERS = 6  # Parallel LLM calls
BATCH_SIZE = 10  # For rate limiting pauses


class ParallelWorkoutIngestion:
    """
    Parallel workout ingestion using ThreadPoolExecutor.
    """

    def __init__(self, graph: ArnoldGraph, exercise_db: List[Dict]):
        self.graph = graph
        self.exercise_db = exercise_db
        self.stats = {
            'workouts_processed': 0,
            'workouts_succeeded': 0,
            'workouts_failed': 0,
            'exercises_total': 0,
            'sets_total': 0,
            'volume_total': 0,
            'custom_exercises_created': 0,
            'parsing_errors': []
        }

    def parse_workout_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse a single workout file (thread-safe).

        Each thread gets its own LLMWorkoutParser instance.
        """
        parser = LLMWorkoutParser()

        try:
            parsed = parser.parse_workout_file(file_path, self.exercise_db)
            return {
                'success': True,
                'file': file_path.name,
                'data': parsed
            }
        except Exception as e:
            return {
                'success': False,
                'file': file_path.name,
                'error': str(e)
            }

    def ingest_parsed_workout(self, parsed_data: Dict) -> bool:
        """
        Ingest a parsed workout into Neo4j.

        NOTE: This uses graph writes so should be synchronized.
        """
        try:
            # Create Workout node
            workout_id = self._create_workout_node(parsed_data)

            # Create custom exercises if needed
            self._create_custom_exercises(parsed_data)

            # Create Set nodes and link to exercises
            self._create_sets_and_links(workout_id, parsed_data)

            # Link to Athlete
            self._link_to_athlete(workout_id)

            return True

        except Exception as e:
            print(f"    ✗ Ingestion error for {parsed_data.get('source_file')}: {e}")
            return False

    def _create_workout_node(self, parsed: Dict[str, Any]) -> str:
        """Create Workout node from parsed data."""
        workout_id = f"{parsed['date']}_workout"

        metadata = parsed.get('metadata', {})
        summary = parsed.get('summary', {})

        query = """
        CREATE (w:Workout {
            id: $workout_id,
            date: date($date),
            source_file: $source_file,
            total_volume: $total_volume,
            total_sets: $total_sets,
            total_exercises: $total_exercises,
            periodization_phase: $periodization_phase,
            perceived_intensity: $perceived_intensity,
            intended_intensity: $intended_intensity,
            tags: $tags,
            goals: $goals,
            equipment_used: $equipment_used,
            muscle_focus: $muscle_focus,
            energy_systems: $energy_systems,
            deviations: $deviations,
            notes: $notes
        })
        RETURN w.id as id
        """

        self.graph.execute_write(query, {
            'workout_id': workout_id,
            'date': parsed['date'],
            'source_file': parsed.get('source_file', ''),
            'total_volume': summary.get('total_volume', 0),
            'total_sets': summary.get('total_sets', 0),
            'total_exercises': summary.get('total_exercises', 0),
            'periodization_phase': metadata.get('periodization_phase'),
            'perceived_intensity': metadata.get('perceived_intensity'),
            'intended_intensity': metadata.get('intended_intensity'),
            'tags': metadata.get('tags', []),
            'goals': metadata.get('goals', []),
            'equipment_used': metadata.get('equipment_used', []),
            'muscle_focus': metadata.get('muscle_focus', []),
            'energy_systems': metadata.get('energy_systems', []),
            'deviations': metadata.get('deviations', []),
            'notes': parsed.get('notes', '')
        })

        return workout_id

    def _create_custom_exercises(self, parsed: Dict[str, Any]):
        """Create custom Exercise nodes for non-standard exercises."""
        custom_exercises = [
            ex for ex in parsed.get('exercises', [])
            if ex.get('is_custom', False)
        ]

        for exercise in custom_exercises:
            exercise_id = f"CUSTOM:{exercise['name'].replace(' ', '_')}"

            query = """
            MERGE (e:Exercise {id: $exercise_id})
            ON CREATE SET
                e.name = $name,
                e.custom = true,
                e.category = $category,
                e.source = 'user_workout_log',
                e.created_date = datetime()
            RETURN e.id as id
            """

            self.graph.execute_write(query, {
                'exercise_id': exercise_id,
                'name': exercise['name'],
                'category': exercise.get('category', 'custom')
            })

            # Update exercise with canonical_id for linking
            exercise['canonical_id'] = exercise_id

    def _create_sets_and_links(self, workout_id: str, parsed: Dict[str, Any]):
        """Create Set nodes and link to Workout and Exercise."""
        for exercise in parsed.get('exercises', []):
            canonical_id = exercise.get('canonical_id')

            if not canonical_id:
                # Skip exercises without canonical match
                continue

            # Create each set
            for set_data in exercise.get('sets', []):
                # Determine if time-based or weight-based
                is_time_based = 'duration_seconds' in set_data

                if is_time_based:
                    # Time-based set
                    query = """
                    MATCH (w:Workout {id: $workout_id})
                    MATCH (e:Exercise {id: $exercise_id})
                    CREATE (s:Set {
                        set_number: $set_number,
                        duration_seconds: $duration_seconds,
                        duration_display: $duration_display,
                        is_time_based: true,
                        notes: $notes
                    })
                    CREATE (w)-[:CONTAINS]->(s)
                    CREATE (s)-[:OF_EXERCISE]->(e)
                    """

                    self.graph.execute_write(query, {
                        'workout_id': workout_id,
                        'exercise_id': canonical_id,
                        'set_number': set_data.get('set_number', 1),
                        'duration_seconds': set_data.get('duration_seconds'),
                        'duration_display': set_data.get('duration_display', ''),
                        'notes': set_data.get('notes', '')
                    })

                else:
                    # Weight-based set
                    query = """
                    MATCH (w:Workout {id: $workout_id})
                    MATCH (e:Exercise {id: $exercise_id})
                    CREATE (s:Set {
                        set_number: $set_number,
                        weight: $weight,
                        weight_unit: $weight_unit,
                        reps: $reps,
                        volume: $volume,
                        rpe: $rpe,
                        is_time_based: false,
                        notes: $notes
                    })
                    CREATE (w)-[:CONTAINS]->(s)
                    CREATE (s)-[:OF_EXERCISE]->(e)
                    """

                    self.graph.execute_write(query, {
                        'workout_id': workout_id,
                        'exercise_id': canonical_id,
                        'set_number': set_data.get('set_number', 1),
                        'weight': set_data.get('weight', 0),
                        'weight_unit': set_data.get('weight_unit', 'lbs'),
                        'reps': set_data.get('reps', 0),
                        'volume': set_data.get('volume', 0),
                        'rpe': set_data.get('rpe'),
                        'notes': set_data.get('notes', '')
                    })

    def _link_to_athlete(self, workout_id: str):
        """Link Workout to Athlete."""
        query = """
        MATCH (a:Athlete {name: 'Brock'})
        MATCH (w:Workout {id: $workout_id})
        MERGE (a)-[:PERFORMED]->(w)
        """

        self.graph.execute_write(query, {'workout_id': workout_id})

    def parallel_ingest(self, workout_files: List[Path]):
        """
        Ingest workouts in parallel using ThreadPoolExecutor.
        """
        print(f"\n{'=' * 70}")
        print(f"PARALLEL LLM INGESTION: {len(workout_files)} files")
        print(f"Workers: {MAX_WORKERS}")
        print('=' * 70)

        # Step 1: Parse all workouts in parallel (LLM calls)
        print("\nStep 1: Parsing workouts with LLM (parallel)...")
        parsed_workouts = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {
                executor.submit(self.parse_workout_file, file_path): file_path
                for file_path in workout_files
            }

            with tqdm(total=len(workout_files), desc="Parsing") as pbar:
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    result = future.result()

                    if result['success']:
                        parsed_workouts.append(result['data'])
                        self.stats['workouts_succeeded'] += 1
                    else:
                        self.stats['workouts_failed'] += 1
                        self.stats['parsing_errors'].append({
                            'file': result['file'],
                            'error': result['error']
                        })

                    self.stats['workouts_processed'] += 1
                    pbar.update(1)

        # Step 2: Ingest into Neo4j (sequential - graph writes need to be synchronized)
        print("\nStep 2: Writing to Neo4j (sequential)...")

        for parsed in tqdm(parsed_workouts, desc="Ingesting"):
            success = self.ingest_parsed_workout(parsed)

            if success:
                self.stats['exercises_total'] += len(parsed.get('exercises', []))
                self.stats['sets_total'] += parsed['summary'].get('total_sets', 0)
                self.stats['volume_total'] += parsed['summary'].get('total_volume', 0)

    def print_stats(self):
        """Print ingestion statistics."""
        print("\n" + "=" * 70)
        print("INGESTION COMPLETE")
        print("=" * 70)
        print(f"Workouts processed: {self.stats['workouts_processed']}")
        print(f"  ✓ Succeeded: {self.stats['workouts_succeeded']}")
        print(f"  ✗ Failed: {self.stats['workouts_failed']}")
        print(f"\nExercises: {self.stats['exercises_total']}")
        print(f"Sets: {self.stats['sets_total']:,}")
        print(f"Total volume: {self.stats['volume_total']:,.0f} lbs")

        if self.stats['parsing_errors']:
            print(f"\nErrors encountered: {len(self.stats['parsing_errors'])}")
            for error in self.stats['parsing_errors'][:5]:
                print(f"  • {error['file']}: {error['error'][:80]}")


def main():
    parser = argparse.ArgumentParser(description="Parallel LLM workout ingestion")
    parser.add_argument('--test', action='store_true', help='Test on 10 sample workouts')
    parser.add_argument('--full', action='store_true', help='Ingest all 164 workouts')
    parser.add_argument('--files', type=str, help='Comma-separated list of specific files')

    args = parser.parse_args()

    # Workout directory
    workout_dir = Path("/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise")

    if not workout_dir.exists():
        print(f"Error: Workout directory not found: {workout_dir}")
        sys.exit(1)

    # Get workout files
    all_files = sorted(workout_dir.glob("*.md"))

    if args.files:
        # Specific files
        file_names = args.files.split(',')
        workout_files = [workout_dir / f.strip() for f in file_names]
        workout_files = [f for f in workout_files if f.exists()]
    elif args.test:
        # Test on 10 samples
        workout_files = all_files[:10]
    elif args.full:
        # All files
        workout_files = all_files
    else:
        print("Error: Specify --test, --full, or --files")
        sys.exit(1)

    print("=" * 70)
    print("PARALLEL LLM WORKOUT INGESTION")
    print("=" * 70)
    print(f"Total workout files available: {len(all_files)}")
    print(f"Files to process: {len(workout_files)}")
    print(f"Parallel workers: {MAX_WORKERS}")

    # Connect to graph
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        print("Error: Could not connect to Neo4j")
        sys.exit(1)

    print("  ✓ Connected")

    # Load exercise database
    print("\nLoading exercise database...")
    exercise_db = get_exercise_database_from_graph(graph)
    print(f"  ✓ Loaded {len(exercise_db)} exercises")

    # Create Athlete node
    print("\nCreating Athlete node...")
    query = """
    MERGE (a:Athlete {name: 'Brock'})
    ON CREATE SET
        a.created_date = datetime(),
        a.training_age_years = 5
    RETURN a.name as name
    """
    result = graph.execute_write(query)
    print(f"  ✓ Athlete node ready")

    # Run parallel ingestion
    pipeline = ParallelWorkoutIngestion(graph, exercise_db)
    pipeline.parallel_ingest(workout_files)
    pipeline.print_stats()

    graph.close()

    print("\n" + "=" * 70)
    print("✓ PARALLEL INGESTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
