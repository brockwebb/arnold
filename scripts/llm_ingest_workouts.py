#!/usr/bin/env python3
"""
LLM-Powered Workout Batch Ingestion

Uses OpenAI API to intelligently parse and ingest all workout logs.

Usage:
    # Test on 3 samples
    python scripts/llm_ingest_workouts.py --test

    # Full ingestion (all 164 files)
    python scripts/llm_ingest_workouts.py --full

    # Specific files
    python scripts/llm_ingest_workouts.py --files 2024-12-16_workout.md,2025-03-12_workout.md
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.llm_ingest import LLMWorkoutParser, get_exercise_database_from_graph


class WorkoutIngestionPipeline:
    """
    Complete pipeline for LLM-powered workout ingestion.

    Pipeline:
    1. Load exercise database from Neo4j
    2. Parse workout files with OpenAI
    3. Create Athlete node (Brock's digital twin)
    4. Create Workout nodes with metadata
    5. Create Set nodes with granular data
    6. Link everything together
    7. Calculate volumes and metrics
    """

    def __init__(self, graph: ArnoldGraph):
        """
        Initialize ingestion pipeline.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph
        self.parser = LLMWorkoutParser()
        self.exercise_db = None
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

    def load_exercise_database(self):
        """Load canonical exercise database from Neo4j."""
        print("\nLoading exercise database from Neo4j...")
        self.exercise_db = get_exercise_database_from_graph(self.graph)
        print(f"  ✓ Loaded {len(self.exercise_db)} canonical exercises")

    def create_athlete_node(self):
        """Create Brock's athlete node (digital twin)."""
        print("\nCreating Athlete node...")

        query = """
        MERGE (a:Athlete {name: 'Brock'})
        ON CREATE SET
            a.created_date = datetime(),
            a.training_age_years = 5
        RETURN a.name as name
        """

        result = self.graph.execute_write(query)
        print(f"  ✓ Athlete node ready: {result}")

    def ingest_workout(self, file_path: Path) -> bool:
        """
        Ingest single workout file.

        Args:
            file_path: Path to workout markdown file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse with LLM
            parsed = self.parser.parse_workout_file(file_path, self.exercise_db)

            # Create Workout node
            workout_id = self._create_workout_node(parsed)

            # Create custom exercises if needed
            self._create_custom_exercises(parsed)

            # Create Set nodes and link to exercises
            self._create_sets_and_links(workout_id, parsed)

            # Link to Athlete
            self._link_to_athlete(workout_id)

            # Update stats
            self.stats['workouts_succeeded'] += 1
            self.stats['exercises_total'] += len(parsed.get('exercises', []))
            self.stats['sets_total'] += parsed['summary'].get('total_sets', 0)
            self.stats['volume_total'] += parsed['summary'].get('total_volume', 0)

            return True

        except Exception as e:
            print(f"    ✗ Error: {e}")
            self.stats['workouts_failed'] += 1
            self.stats['parsing_errors'].append({
                'file': file_path.name,
                'error': str(e)
            })
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

            self.stats['custom_exercises_created'] += 1

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

    def batch_ingest(self, workout_files: List[Path]):
        """
        Ingest multiple workout files.

        Args:
            workout_files: List of workout file paths
        """
        print(f"\n{'=' * 70}")
        print(f"BATCH INGESTION: {len(workout_files)} files")
        print('=' * 70)

        for i, file_path in enumerate(workout_files, 1):
            self.stats['workouts_processed'] += 1

            print(f"\n[{i}/{len(workout_files)}] Processing {file_path.name}...")

            success = self.ingest_workout(file_path)

            if success:
                print(f"  ✓ Success")
            else:
                print(f"  ✗ Failed")

            # Rate limiting (avoid hitting API limits)
            if i % 10 == 0:
                print(f"\n  Pausing 5s to avoid rate limits...")
                time.sleep(5)

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
        print(f"Custom exercises created: {self.stats['custom_exercises_created']}")

        if self.stats['parsing_errors']:
            print(f"\nErrors encountered: {len(self.stats['parsing_errors'])}")
            for error in self.stats['parsing_errors'][:5]:
                print(f"  • {error['file']}: {error['error']}")

    def verify_data(self):
        """Run verification queries."""
        print("\n" + "=" * 70)
        print("DATA VERIFICATION")
        print("=" * 70)

        # Total workouts
        result = self.graph.execute_query("""
            MATCH (a:Athlete {name: 'Brock'})-[:PERFORMED]->(w:Workout)
            RETURN count(w) as total_workouts
        """)
        print(f"Total workouts in graph: {result[0]['total_workouts']}")

        # Total sets
        result = self.graph.execute_query("""
            MATCH (s:Set)
            RETURN count(s) as total_sets
        """)
        print(f"Total sets in graph: {result[0]['total_sets']:,}")

        # Total volume
        result = self.graph.execute_query("""
            MATCH (s:Set)
            WHERE s.volume IS NOT NULL
            RETURN sum(s.volume) as total_volume
        """)
        print(f"Total volume: {result[0]['total_volume']:,.0f} lbs")

        # Most frequent exercises
        print("\nTop 10 exercises by set count:")
        result = self.graph.execute_query("""
            MATCH (s:Set)-[:OF_EXERCISE]->(e:Exercise)
            RETURN e.name as exercise, count(s) as sets
            ORDER BY sets DESC
            LIMIT 10
        """)
        for r in result:
            print(f"  {r['exercise']:<40} {r['sets']:>5} sets")


def main():
    parser = argparse.ArgumentParser(description="LLM-powered workout ingestion")
    parser.add_argument('--test', action='store_true', help='Test on 3 sample workouts')
    parser.add_argument('--full', action='store_true', help='Ingest all 164 workouts')
    parser.add_argument('--files', type=str, help='Comma-separated list of specific files')
    parser.add_argument('--clear', action='store_true', help='Clear existing workout data before ingestion')

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
        # Test on 3 samples
        workout_files = [
            workout_dir / "2024-12-16_workout.md",
            workout_dir / "2025-03-12_workout.md",
            workout_dir / "2025-05-14_workout.md"
        ]
        workout_files = [f for f in workout_files if f.exists()]
    elif args.full:
        # All files
        workout_files = all_files
    else:
        print("Error: Specify --test, --full, or --files")
        print("\nUsage:")
        print("  python scripts/llm_ingest_workouts.py --test")
        print("  python scripts/llm_ingest_workouts.py --full")
        print("  python scripts/llm_ingest_workouts.py --files 2024-12-16_workout.md")
        sys.exit(1)

    print("=" * 70)
    print("LLM-POWERED WORKOUT INGESTION")
    print("=" * 70)
    print(f"Total workout files available: {len(all_files)}")
    print(f"Files to process: {len(workout_files)}")

    # Connect to graph
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        print("Error: Could not connect to Neo4j")
        sys.exit(1)

    print("  ✓ Connected")

    # Clear existing data if requested
    if args.clear:
        confirm = input("\n⚠️  Clear existing workout data? This cannot be undone. (yes/no): ")
        if confirm.lower() == 'yes':
            print("\nClearing existing workout data...")
            graph.execute_write("MATCH (w:Workout) DETACH DELETE w")
            graph.execute_write("MATCH (s:Set) DETACH DELETE s")
            print("  ✓ Cleared")
        else:
            print("  Aborted")
            sys.exit(0)

    # Run ingestion pipeline
    pipeline = WorkoutIngestionPipeline(graph)
    pipeline.load_exercise_database()
    pipeline.create_athlete_node()
    pipeline.batch_ingest(workout_files)
    pipeline.print_stats()
    pipeline.verify_data()

    graph.close()

    print("\n" + "=" * 70)
    print("✓ INGESTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
