#!/usr/bin/env python3
"""
Import Free-Exercise-DB exercises with variation hierarchy
Creates canonical exercises and links to FMA muscles
"""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()

EXERCISES_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/free-exercise-db/dist/exercises.json"


class CanonicalExerciseImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'exercises': 0,
            'primary_targets': 0,
            'secondary_targets': 0,
            'equipment_categories': 0,
            'muscles_not_found': 0
        }
        self.equipment_cache = set()

    def close(self):
        self.graph.close()

    def import_exercises(self):
        """Import all exercises from Free-Exercise-DB"""

        print(f"\n{'='*70}")
        print("FREE-EXERCISE-DB CANONICAL IMPORT")
        print(f"{'='*70}\n")

        print(f"Loading exercises from: {EXERCISES_FILE}")
        with open(EXERCISES_FILE) as f:
            exercises_data = json.load(f)

        print(f"  ✓ Loaded {len(exercises_data)} exercises\n")

        print("Importing canonical exercises...")

        for i, ex_data in enumerate(exercises_data):
            self._import_exercise(ex_data)

            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(exercises_data)} exercises...")

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Imported {self.stats['exercises']} canonical exercises")
        print(f"  ✓ Primary muscle targets: {self.stats['primary_targets']}")
        print(f"  ✓ Secondary muscle targets: {self.stats['secondary_targets']}")
        print(f"  ✓ Equipment categories: {self.stats['equipment_categories']}")
        print(f"  ⚠ Muscles not found in FMA: {self.stats['muscles_not_found']}\n")

        # Verify
        self._verify_import()

    def _import_exercise(self, ex_data):
        """Import a single exercise"""

        exercise_id = ex_data.get('id')
        if not exercise_id:
            # Generate ID from name
            exercise_id = ex_data['name'].lower().replace(' ', '_')

        exercise_id = f"CANONICAL:{exercise_id}"

        name = ex_data.get('name')
        category = ex_data.get('category')
        force_type = ex_data.get('force', 'unknown')
        mechanic = ex_data.get('mechanic', 'unknown')
        difficulty = ex_data.get('level', 'beginner')
        equipment = ex_data.get('equipment', 'none')
        instructions = ' '.join(ex_data.get('instructions', []))

        # Create canonical Exercise node
        self.graph.execute_query("""
            MERGE (ex:Exercise {id: $id})
            SET ex.name = $name,
                ex.category = $category,
                ex.force_type = $force_type,
                ex.mechanic = $mechanic,
                ex.difficulty = $difficulty,
                ex.equipment = $equipment,
                ex.instructions = $instructions,
                ex.is_canonical = true,
                ex.source = 'free-exercise-db'
        """, parameters={
            'id': exercise_id,
            'name': name,
            'category': category,
            'force_type': force_type,
            'mechanic': mechanic,
            'difficulty': difficulty,
            'equipment': equipment,
            'instructions': instructions
        })

        self.stats['exercises'] += 1

        # Link to primary muscles
        primary_muscles = ex_data.get('primaryMuscles', [])
        for muscle_name in primary_muscles:
            if self._link_to_muscle(exercise_id, muscle_name, role="primary"):
                self.stats['primary_targets'] += 1

        # Link to secondary muscles
        secondary_muscles = ex_data.get('secondaryMuscles', [])
        for muscle_name in secondary_muscles:
            if self._link_to_muscle(exercise_id, muscle_name, role="secondary"):
                self.stats['secondary_targets'] += 1

        # Create equipment category if needed
        if equipment and equipment != 'none':
            self._ensure_equipment_category(equipment)

    def _link_to_muscle(self, exercise_id, muscle_name, role="primary"):
        """Link exercise to muscle via FMA"""

        # Normalize muscle name
        normalized = muscle_name.lower().strip().replace('_', ' ').replace('-', ' ')

        # Find muscle in FMA nodes - prioritize common_name match
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.fma_id IS NOT NULL
              AND (toLower(m.common_name) = $muscle_name
                   OR toLower(m.name) CONTAINS $muscle_name)
            RETURN m.fma_id as fma_id
            LIMIT 1
        """, parameters={'muscle_name': normalized})

        if not result:
            self.stats['muscles_not_found'] += 1
            return False

        fma_id = result[0]['fma_id']

        # Create TARGETS relationship
        self.graph.execute_query("""
            MATCH (ex:Exercise {id: $ex_id})
            MATCH (m:Muscle {fma_id: $fma_id})
            MERGE (ex)-[t:TARGETS]->(m)
            SET t.role = $role
        """, parameters={
            'ex_id': exercise_id,
            'fma_id': fma_id,
            'role': role
        })

        return True

    def _ensure_equipment_category(self, equipment_name):
        """Create equipment category node if it doesn't exist"""

        # Map Free-Exercise-DB equipment names to categories
        equipment_mapping = {
            'barbell': 'EQ_CAT:barbell',
            'dumbbell': 'EQ_CAT:dumbbell',
            'body only': 'EQ_CAT:bodyweight',
            'bodyweight': 'EQ_CAT:bodyweight',
            'bands': 'EQ_CAT:resistance_band',
            'resistance band': 'EQ_CAT:resistance_band',
            'kettlebells': 'EQ_CAT:kettlebell',
            'cable': 'EQ_CAT:cable',
            'machine': 'EQ_CAT:machine',
            'medicine ball': 'EQ_CAT:medicine_ball',
            'foam roll': 'EQ_CAT:foam_roller',
            'exercise ball': 'EQ_CAT:stability_ball',
            'e-z curl bar': 'EQ_CAT:ez_bar',
            'other': 'EQ_CAT:other'
        }

        equipment_id = equipment_mapping.get(equipment_name.lower(), f"EQ_CAT:{equipment_name.lower().replace(' ', '_')}")

        # Only create if we haven't seen this category before
        if equipment_id not in self.equipment_cache:
            self.graph.execute_query("""
                MERGE (eq:EquipmentCategory {id: $id})
                SET eq.name = $name
            """, parameters={
                'id': equipment_id,
                'name': equipment_name
            })

            self.equipment_cache.add(equipment_id)
            self.stats['equipment_categories'] += 1

    def _verify_import(self):
        """Verify import in database"""
        print("Verifying import...")

        # Count exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN count(ex) as count
        """)
        exercises = result[0]['count']

        # Count TARGETS relationships
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)-[t:TARGETS]->(:Muscle)
            RETURN count(t) as count
        """)
        targets = result[0]['count']

        # Count equipment categories
        result = self.graph.execute_query("""
            MATCH (eq:EquipmentCategory)
            RETURN count(eq) as count
        """)
        equipment = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    Canonical Exercise nodes: {exercises}")
        print(f"    TARGETS relationships: {targets}")
        print(f"    EquipmentCategory nodes: {equipment}\n")

        # Sample exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)-[:TARGETS {role: 'primary'}]->(m:Muscle)
            RETURN ex.name as exercise, collect(m.name)[0..2] as primary_muscles
            LIMIT 5
        """)

        print("  Sample exercises with primary muscles:")
        for r in result:
            muscles_str = ", ".join(r['primary_muscles'])
            print(f"    • {r['exercise']}: {muscles_str}")

        # Coverage by category
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN ex.category as category, count(ex) as count
            ORDER BY count DESC
            LIMIT 10
        """)

        print("\n  Exercises by category:")
        for r in result:
            print(f"    • {r['category']}: {r['count']}")


def main():
    print("Starting canonical exercise import...")
    print("Source: Free-Exercise-DB (with FMA muscle linking)")

    importer = CanonicalExerciseImporter()
    try:
        importer.import_exercises()
    finally:
        importer.close()

    print(f"\n{'='*70}")
    print("✓ CANONICAL EXERCISE IMPORT COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
