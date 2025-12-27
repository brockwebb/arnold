#!/usr/bin/env python3
"""
Import curated muscle list into Neo4j
Creates Muscle nodes with common/anatomical names
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


class MuscleImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'muscles': 0,
            'hierarchies': 0
        }

    def close(self):
        self.graph.close()

    def import_muscles(self):
        """Import curated muscle list"""

        print(f"\n{'='*70}")
        print("MUSCLE IMPORT")
        print(f"{'='*70}\n")

        # Extract muscles from Free-Exercise-DB
        print("Extracting muscles from Free-Exercise-DB...")
        muscles_from_db = self._extract_muscles_from_db()
        print(f"  ✓ Found {len(muscles_from_db)} unique muscles\n")

        # Add curated muscle names with hierarchies
        muscle_data = self._get_curated_muscles()

        print("Importing muscles...")
        for muscle_info in muscle_data:
            muscle_id = muscle_info['id']
            name = muscle_info['name']
            common_name = muscle_info.get('common_name', name)
            muscle_group = muscle_info.get('group')
            anatomical_name = muscle_info.get('anatomical_name', name)

            # Create Muscle node
            self.graph.execute_query("""
                MERGE (m:Muscle {id: $id})
                SET m.name = $name,
                    m.common_name = $common_name,
                    m.anatomical_name = $anatomical_name,
                    m.muscle_group = $muscle_group
            """, parameters={
                'id': muscle_id,
                'name': name,
                'common_name': common_name,
                'anatomical_name': anatomical_name,
                'muscle_group': muscle_group
            })

            self.stats['muscles'] += 1

            # Create muscle group hierarchy
            if muscle_group:
                self.graph.execute_query("""
                    MERGE (g:MuscleGroup {name: $group_name})
                    WITH g
                    MATCH (m:Muscle {id: $muscle_id})
                    MERGE (m)-[:PART_OF]->(g)
                """, parameters={'group_name': muscle_group, 'muscle_id': muscle_id})
                self.stats['hierarchies'] += 1

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Imported {self.stats['muscles']} muscles")
        print(f"  ✓ Created {self.stats['hierarchies']} group relationships\n")

        # Verify
        self._verify_import()

    def _extract_muscles_from_db(self):
        """Extract unique muscle names from Free-Exercise-DB"""
        with open(EXERCISES_FILE, 'r') as f:
            exercises = json.load(f)

        muscles = set()
        for ex in exercises:
            muscles.update(ex.get('primaryMuscles', []))
            muscles.update(ex.get('secondaryMuscles', []))

        return sorted(muscles)

    def _get_curated_muscles(self):
        """Get curated muscle list with hierarchies"""
        return [
            # Core
            {'id': 'MUSCLE:abdominals', 'name': 'abdominals', 'common_name': 'abs', 'group': 'core', 'anatomical_name': 'rectus abdominis'},
            {'id': 'MUSCLE:obliques', 'name': 'obliques', 'group': 'core', 'anatomical_name': 'external obliques'},
            {'id': 'MUSCLE:lower_back', 'name': 'lower back', 'group': 'core', 'anatomical_name': 'erector spinae'},
            {'id': 'MUSCLE:serratus', 'name': 'serratus anterior', 'common_name': 'serratus', 'group': 'core'},

            # Chest
            {'id': 'MUSCLE:chest', 'name': 'chest', 'common_name': 'pecs', 'group': 'chest', 'anatomical_name': 'pectoralis major'},
            {'id': 'MUSCLE:middle_chest', 'name': 'middle chest', 'group': 'chest'},

            # Back
            {'id': 'MUSCLE:lats', 'name': 'lats', 'group': 'back', 'anatomical_name': 'latissimus dorsi'},
            {'id': 'MUSCLE:middle_back', 'name': 'middle back', 'group': 'back', 'anatomical_name': 'rhomboids'},
            {'id': 'MUSCLE:traps', 'name': 'traps', 'group': 'back', 'anatomical_name': 'trapezius'},
            {'id': 'MUSCLE:teres_major', 'name': 'teres major', 'group': 'back'},

            # Shoulders
            {'id': 'MUSCLE:shoulders', 'name': 'shoulders', 'common_name': 'delts', 'group': 'shoulders', 'anatomical_name': 'deltoids'},
            {'id': 'MUSCLE:rotator_cuff', 'name': 'rotator cuff', 'group': 'shoulders'},

            # Arms
            {'id': 'MUSCLE:biceps', 'name': 'biceps', 'group': 'arms', 'anatomical_name': 'biceps brachii'},
            {'id': 'MUSCLE:triceps', 'name': 'triceps', 'group': 'arms', 'anatomical_name': 'triceps brachii'},
            {'id': 'MUSCLE:forearms', 'name': 'forearms', 'group': 'arms'},
            {'id': 'MUSCLE:brachialis', 'name': 'brachialis', 'group': 'arms'},

            # Legs
            {'id': 'MUSCLE:quadriceps', 'name': 'quadriceps', 'common_name': 'quads', 'group': 'legs'},
            {'id': 'MUSCLE:hamstrings', 'name': 'hamstrings', 'group': 'legs'},
            {'id': 'MUSCLE:glutes', 'name': 'glutes', 'group': 'legs', 'anatomical_name': 'gluteus maximus'},
            {'id': 'MUSCLE:calves', 'name': 'calves', 'group': 'legs', 'anatomical_name': 'gastrocnemius'},
            {'id': 'MUSCLE:adductors', 'name': 'adductors', 'group': 'legs'},
            {'id': 'MUSCLE:abductors', 'name': 'abductors', 'group': 'legs', 'anatomical_name': 'gluteus medius'},
            {'id': 'MUSCLE:hip_flexors', 'name': 'hip flexors', 'group': 'legs', 'anatomical_name': 'iliopsoas'},

            # Neck
            {'id': 'MUSCLE:neck', 'name': 'neck', 'group': 'neck'},
        ]

    def _verify_import(self):
        """Verify import"""
        print("Verifying import...")

        # Count muscles
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            RETURN count(m) as count
        """)
        muscles = result[0]['count']

        # Count muscle groups
        result = self.graph.execute_query("""
            MATCH (g:MuscleGroup)
            RETURN count(g) as count
        """)
        groups = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    Muscle nodes: {muscles}")
        print(f"    MuscleGroup nodes: {groups}\n")

        # Show groups
        result = self.graph.execute_query("""
            MATCH (g:MuscleGroup)
            OPTIONAL MATCH (m:Muscle)-[:PART_OF]->(g)
            RETURN g.name as group, count(m) as muscle_count
            ORDER BY muscle_count DESC
        """)

        print("  Muscle groups:")
        for r in result:
            print(f"    • {r['group']}: {r['muscle_count']} muscles")


def main():
    print("Starting muscle import...")

    importer = MuscleImporter()
    try:
        importer.import_muscles()
    finally:
        importer.close()

    print("\n✓ Muscle import complete!\n")


if __name__ == "__main__":
    main()
