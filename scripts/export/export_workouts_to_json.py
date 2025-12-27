#!/usr/bin/env python3
"""
Export all workouts from Neo4j to individual JSON files.

Creates one JSON file per workout, named by workout date (YYYY-MM-DD.json).
Establishes the canonical workout schema and creates source of truth backup.

Usage:
    python scripts/export/export_workouts_to_json.py
"""

import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load environment variables
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

# Output directory
OUTPUT_DIR = Path("/Users/brock/Documents/GitHub/arnold/data/workouts")


class WorkoutExporter:
    """Export workouts from Neo4j to JSON files."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        self.warnings = []
        self.unmapped_exercises = set()

    def close(self):
        """Close Neo4j connection."""
        self.driver.close()

    def export_all_workouts(self):
        """Export all workouts for Brock to individual JSON files."""
        print("Exporting workouts for Brock...")

        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Query all workouts
        workouts = self._fetch_workouts()

        if not workouts:
            print("No workouts found!")
            return

        print(f"Found {len(workouts)} workouts from {workouts[0]['date']} to {workouts[-1]['date']}\n")

        # Export each workout
        for i, workout_data in enumerate(workouts, 1):
            workout_json = self._process_workout(workout_data, i, len(workouts))
            self._save_workout(workout_json)

        # Print summary
        self._print_summary(workouts)

    def _fetch_workouts(self):
        """Fetch all workouts from Neo4j."""
        query = """
        MATCH (a:Athlete {name: "Brock"})-[:PERFORMED]->(w:Workout)
        OPTIONAL MATCH (w)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(ex:Exercise)
        OPTIONAL MATCH (ex)-[:SAME_AS|MAPS_TO]->(canonical:Exercise)
        WHERE canonical.is_canonical = true
        OPTIONAL MATCH (ex)-[:TARGETS]->(m:Muscle)
        WITH w, s, ex, canonical,
             collect(DISTINCT {
                 muscle: m,
                 role: CASE
                     WHEN EXISTS((ex)-[:TARGETS {role: 'primary'}]->(m)) THEN 'primary'
                     WHEN EXISTS((ex)-[:TARGETS {role: 'secondary'}]->(m)) THEN 'secondary'
                     ELSE 'tertiary'
                 END
             }) as muscle_data
        WITH w, s, ex, canonical, muscle_data
        ORDER BY w.date, ex.name, s.set_number
        RETURN w,
               collect(DISTINCT {
                   set: s,
                   exercise: ex,
                   canonical: canonical,
                   muscles: muscle_data
               }) as workout_data
        ORDER BY w.date
        """

        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query)
            workouts = []

            for record in result:
                w = record["w"]
                workout_data = record["workout_data"]

                workouts.append({
                    "workout_node": w,
                    "date": w["date"],
                    "workout_data": workout_data
                })

            return workouts

    def _process_workout(self, workout_data, index, total):
        """Process a single workout into JSON format."""
        w = workout_data["workout_node"]
        raw_data = workout_data["workout_data"]

        # Get workout date
        workout_date = w["date"]
        if isinstance(workout_date, datetime):
            workout_date = workout_date.date().isoformat()

        print(f"Processing workout {index}/{total}: {workout_date}")

        # Group sets by exercise
        exercise_map = {}
        for item in raw_data:
            s = item["set"]
            ex = item["exercise"]
            canonical = item["canonical"]
            muscles = item["muscles"]

            if not ex:
                continue

            ex_id = ex.element_id
            if ex_id not in exercise_map:
                exercise_map[ex_id] = {
                    "exercise": ex,
                    "canonical": canonical,
                    "sets": [],
                    "muscles": muscles
                }

            if s:
                exercise_map[ex_id]["sets"].append(s)

        # Build exercises array
        exercises = []
        total_sets = 0

        for ex_id, ex_data in exercise_map.items():
            ex = ex_data["exercise"]
            canonical = ex_data["canonical"]
            sets = sorted(ex_data["sets"], key=lambda s: s.get("set_number", 0))
            muscles = ex_data["muscles"]

            # Track unmapped exercises
            if not canonical:
                self.unmapped_exercises.add(ex["name"])

            # Build sets array
            sets_json = []
            for s in sets:
                set_json = {
                    "set_number": s.get("set_number"),
                    "reps": s.get("reps"),
                    "load_lbs": s.get("load_lbs"),
                    "rpe": s.get("rpe"),
                    "notes": s.get("notes")
                }
                sets_json.append(set_json)
                total_sets += 1

            # Build target_muscles array
            target_muscles = []
            for m_data in muscles:
                m = m_data.get("muscle")
                if m:
                    target_muscles.append({
                        "muscle_name": m.get("name"),
                        "fma_id": m.get("fma_id"),
                        "role": m_data.get("role", "tertiary")
                    })

            # Build exercise JSON
            exercise_json = {
                "exercise_id": ex.get("id"),
                "exercise_name": ex.get("name"),
                "canonical_id": canonical.get("id") if canonical else None,
                "canonical_name": canonical.get("name") if canonical else None,
                "sets": sets_json,
                "target_muscles": sorted(target_muscles, key=lambda m: (
                    0 if m["role"] == "primary" else 1 if m["role"] == "secondary" else 2,
                    m["muscle_name"]
                ))
            }

            exercises.append(exercise_json)

        print(f"  - {len(exercises)} exercises, {total_sets} sets")

        # Build workout JSON
        workout_json = {
            "workout_id": w.element_id,
            "date": workout_date,
            "type": w.get("type", "strength"),
            "duration_minutes": w.get("duration_minutes"),
            "notes": w.get("notes"),
            "exercises": sorted(exercises, key=lambda e: e["exercise_name"])
        }

        return workout_json

    def _save_workout(self, workout_json):
        """Save workout to JSON file."""
        filename = f"{workout_json['date']}.json"
        filepath = OUTPUT_DIR / filename

        with open(filepath, 'w') as f:
            json.dump(workout_json, f, indent=2, default=str)

    def _print_summary(self, workouts):
        """Print export summary."""
        print("\n" + "="*60)
        print("Export complete!")
        print("="*60)

        # Count unique exercises
        all_exercises = set()
        mapped_exercises = set()

        for workout_file in OUTPUT_DIR.glob("*.json"):
            with open(workout_file, 'r') as f:
                data = json.load(f)
                for ex in data.get("exercises", []):
                    all_exercises.add(ex["exercise_name"])
                    if ex.get("canonical_id"):
                        mapped_exercises.add(ex["exercise_name"])

        print(f"\nSummary:")
        print(f"- {len(workouts)} workouts exported to {OUTPUT_DIR}/")
        print(f"- Date range: {workouts[0]['date']} to {workouts[-1]['date']}")
        print(f"- Total unique exercises: {len(all_exercises)}")
        print(f"- Canonically mapped: {len(mapped_exercises)}")
        print(f"- Not mapped: {len(self.unmapped_exercises)}")

        if self.unmapped_exercises:
            print(f"\nUnmapped exercises ({len(self.unmapped_exercises)}):")
            for ex_name in sorted(self.unmapped_exercises):
                print(f'  - "{ex_name}"')
            print("\nUnmapped exercises need review for weapons_locker promotion.")

        # Validate all files
        print(f"\nValidation:")
        file_count = len(list(OUTPUT_DIR.glob("*.json")))
        print(f"- {file_count} JSON files created")

        # Check file sizes
        large_files = []
        for filepath in OUTPUT_DIR.glob("*.json"):
            size_kb = filepath.stat().st_size / 1024
            if size_kb > 100:
                large_files.append((filepath.name, size_kb))

        if large_files:
            print(f"\nWarning: {len(large_files)} files > 100KB:")
            for name, size in large_files:
                print(f"  - {name}: {size:.1f} KB")
        else:
            print("- All files < 100KB ✓")

        print("\n" + "="*60)


def main():
    """Main entry point."""
    exporter = WorkoutExporter()

    try:
        exporter.export_all_workouts()
    finally:
        exporter.close()


if __name__ == "__main__":
    main()
