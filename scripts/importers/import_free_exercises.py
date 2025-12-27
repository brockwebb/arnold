#!/usr/bin/env python3
"""
Import Free-Exercise-DB exercises into Neo4j

Reads the consolidated exercises.json file and creates:
- Exercise nodes with metadata
- TARGETS relationships to muscles (primary/secondary)
- REQUIRES relationships to equipment
"""

import sys
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent / ".env")

EXERCISES_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/free-exercise-db/dist/exercises.json"


class ExerciseImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'exercises': 0,
            'primary_targets': 0,
            'secondary_targets': 0,
            'equipment_nodes': 0,
            'equipment_links': 0,
            'muscles_created': 0
        }
        self.equipment_cache = set()

    def close(self):
        self.graph.close()

    def import_exercises(self):
        """Import all exercises from Free-Exercise-DB"""

        print(f"\n{'='*70}")
        print("FREE-EXERCISE-DB IMPORT")
        print(f"{'='*70}\n")

        print(f"Loading exercises from: {EXERCISES_FILE}")
        with open(EXERCISES_FILE) as f:
            exercises = json.load(f)

        print(f"  ✓ Loaded {len(exercises)} exercises\n")

        print("Importing exercises...")
        for i, exercise in enumerate(exercises):
            self._import_exercise(exercise)

            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(exercises)} exercises...")

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Imported {self.stats['exercises']} exercises")
        print(f"  ✓ Primary muscle targets: {self.stats['primary_targets']}")
        print(f"  ✓ Secondary muscle targets: {self.stats['secondary_targets']}")
        print(f"  ✓ Equipment nodes created: {self.stats['equipment_nodes']}")
        print(f"  ✓ Equipment links: {self.stats['equipment_links']}")
        print(f"  ✓ Custom muscles created: {self.stats['muscles_created']}\n")

        # Verify
        self._verify_import()

    def _normalize_muscle_name(self, name: str) -> str:
        """Normalize muscle name for matching"""
        return name.lower().strip().replace('_', ' ').replace('-', ' ')

    def _find_or_create_muscle(self, muscle_name: str) -> str:
        """
        Find muscle in graph or create if not found.
        Tries to match against existing curated muscles first.
        """
        normalized = self._normalize_muscle_name(muscle_name)

        # Try to find existing muscle by name or common_name
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE toLower(m.name) = $name
               OR toLower(m.common_name) = $name
            RETURN m.id as id
            LIMIT 1
        """, parameters={'name': normalized})

        if result:
            return result[0]['id']

        # Create custom muscle node
        muscle_id = f"MUSCLE:{normalized.replace(' ', '_')}"

        # Check if this custom muscle already exists
        result = self.graph.execute_query("""
            MATCH (m:Muscle {id: $id})
            RETURN m.id as id
        """, parameters={'id': muscle_id})

        if result:
            return result[0]['id']

        # Create new custom muscle
        self.graph.execute_query("""
            MERGE (m:Muscle {id: $id})
            SET m.name = $name,
                m.source = 'free-exercise-db'
        """, parameters={'id': muscle_id, 'name': normalized})

        self.stats['muscles_created'] += 1
        return muscle_id

    def _import_exercise(self, exercise: dict):
        """Import a single exercise"""

        exercise_id = exercise.get('id')
        if not exercise_id:
            # Generate ID from name
            exercise_id = exercise['name'].lower().replace(' ', '_')

        exercise_id = f"EXERCISE:{exercise_id}"

        # Create Exercise node
        self.graph.execute_query("""
            MERGE (e:Exercise {id: $id})
            SET e.name = $name,
                e.aliases = $aliases,
                e.category = $category,
                e.force_type = $force_type,
                e.mechanic = $mechanic,
                e.difficulty = $difficulty,
                e.equipment = $equipment,
                e.instructions = $instructions,
                e.source = 'free-exercise-db'
        """, parameters={
            'id': exercise_id,
            'name': exercise.get('name', 'Unknown'),
            'aliases': exercise.get('aliases', []),
            'category': exercise.get('category', 'unknown'),
            'force_type': exercise.get('force', 'unknown'),
            'mechanic': exercise.get('mechanic', 'unknown'),
            'difficulty': exercise.get('level', 'beginner'),
            'equipment': exercise.get('equipment', 'none'),
            'instructions': ' '.join(exercise.get('instructions', []))
        })

        self.stats['exercises'] += 1

        # Link to primary muscles
        primary_muscles = exercise.get('primaryMuscles', [])
        for muscle_name in primary_muscles:
            muscle_id = self._find_or_create_muscle(muscle_name)

            self.graph.execute_query("""
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (e)-[:TARGETS {role: 'primary'}]->(m)
            """, parameters={
                'exercise_id': exercise_id,
                'muscle_id': muscle_id
            })

            self.stats['primary_targets'] += 1

        # Link to secondary muscles
        secondary_muscles = exercise.get('secondaryMuscles', [])
        for muscle_name in secondary_muscles:
            muscle_id = self._find_or_create_muscle(muscle_name)

            self.graph.execute_query("""
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (e)-[:TARGETS {role: 'secondary'}]->(m)
            """, parameters={
                'exercise_id': exercise_id,
                'muscle_id': muscle_id
            })

            self.stats['secondary_targets'] += 1

        # Create equipment node and link
        equipment = exercise.get('equipment', 'none')
        if equipment and equipment != 'none':
            equipment_id = f"EQUIPMENT:{equipment.replace(' ', '_').upper()}"

            # Only count if we haven't seen this equipment before
            if equipment_id not in self.equipment_cache:
                self.graph.execute_query("""
                    MERGE (eq:Equipment {id: $id})
                    SET eq.name = $name,
                        eq.category = $category
                """, parameters={
                    'id': equipment_id,
                    'name': equipment,
                    'category': equipment
                })

                self.equipment_cache.add(equipment_id)
                self.stats['equipment_nodes'] += 1

            # Link exercise to equipment
            self.graph.execute_query("""
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (eq:Equipment {id: $equipment_id})
                MERGE (e)-[:REQUIRES]->(eq)
            """, parameters={
                'exercise_id': exercise_id,
                'equipment_id': equipment_id
            })

            self.stats['equipment_links'] += 1

    def _verify_import(self):
        """Verify import in database"""
        print("Verifying import...")

        # Count exercises
        result = self.graph.execute_query("""
            MATCH (e:Exercise)
            RETURN count(e) as count
        """)
        exercises = result[0]['count']

        # Count equipment
        result = self.graph.execute_query("""
            MATCH (eq:Equipment)
            RETURN count(eq) as count
        """)
        equipment = result[0]['count']

        # Count TARGETS relationships
        result = self.graph.execute_query("""
            MATCH ()-[r:TARGETS]->()
            RETURN count(r) as count
        """)
        targets = result[0]['count']

        # Count muscles
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            RETURN count(m) as count
        """)
        muscles = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    Exercise nodes: {exercises}")
        print(f"    Muscle nodes: {muscles}")
        print(f"    Equipment nodes: {equipment}")
        print(f"    TARGETS relationships: {targets}\n")

        # Sample exercises
        result = self.graph.execute_query("""
            MATCH (e:Exercise)-[:TARGETS {role: 'primary'}]->(m:Muscle)
            RETURN e.name as exercise, collect(m.name)[0..3] as primary_muscles
            LIMIT 5
        """)

        print("  Sample exercises with primary muscles:")
        for r in result:
            muscles_str = ", ".join(r['primary_muscles'])
            print(f"    • {r['exercise']}: {muscles_str}")

        # Coverage by category
        result = self.graph.execute_query("""
            MATCH (e:Exercise)
            RETURN e.category as category, count(e) as count
            ORDER BY count DESC
            LIMIT 10
        """)

        print("\n  Exercises by category:")
        for r in result:
            print(f"    • {r['category']}: {r['count']}")


def main():
    print("Starting exercise import...")
    print("Source: Free-Exercise-DB (consolidated JSON)")

    importer = ExerciseImporter()
    try:
        importer.import_exercises()
    finally:
        importer.close()

    print(f"\n{'='*70}")
    print("✓ EXERCISE IMPORT COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
