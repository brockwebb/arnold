#!/usr/bin/env python3
"""
Add muscle groups - V2
Works with the FMA muscles we actually have (parent classes, not individual muscles)
Creates semantic groupings for exercise mapping
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()


class MuscleGroupCreatorV2:
    def __init__(self):
        self.graph = ArnoldGraph()

    def close(self):
        self.graph.close()

    def create_muscle_groups(self):
        """Create muscle groups based on actual FMA muscles we have"""

        print(f"\n{'='*70}")
        print("MUSCLE GROUP CREATION V2")
        print("Working with actual FMA parent class muscles")
        print(f"{'='*70}\n")

        # Map muscle groups to the FMA muscles we actually have
        groups = {
            'HAMSTRINGS': {
                'name': 'Hamstrings',
                'common_name': 'hamstrings',
                'region': 'posterior_thigh',
                'fma_common_names': ['biceps']  # We have biceps femoris
            },
            'QUADRICEPS': {
                'name': 'Quadriceps',
                'common_name': 'quadriceps',
                'region': 'anterior_thigh',
                'fma_common_names': ['quadriceps']  # We have quadriceps node
            },
            'GLUTES': {
                'name': 'Glutes',
                'common_name': 'glutes',
                'region': 'hip',
                'fma_common_names': ['glutes']  # We have gluteal muscle
            },
            'CHEST': {
                'name': 'Chest',
                'common_name': 'chest',
                'region': 'anterior_torso',
                'fma_common_names': ['chest']  # We have pectoral muscle
            },
            'BACK': {
                'name': 'Back',
                'common_name': 'back',
                'region': 'posterior_torso',
                'fma_common_names': ['lats', 'traps', 'middle back', 'lower back']
            },
            'SHOULDERS': {
                'name': 'Shoulders',
                'common_name': 'shoulders',
                'region': 'shoulder_girdle',
                'fma_common_names': ['shoulders']  # We have deltoid
            },
            'ARMS': {
                'name': 'Arms',
                'common_name': 'arms',
                'region': 'upper_limb',
                'fma_common_names': ['biceps', 'triceps']  # Note: biceps here is femoris, not brachii!
            },
            'LEGS': {
                'name': 'Legs',
                'common_name': 'legs',
                'region': 'lower_limb',
                'fma_common_names': ['quadriceps', 'biceps', 'calves']
            },
            'CORE': {
                'name': 'Core',
                'common_name': 'core',
                'region': 'trunk',
                'fma_common_names': ['abdominals', 'lower back']
            }
        }

        for group_id, group_data in groups.items():
            self._create_group(group_id, group_data)

        # Verify
        self._verify_creation()

        print(f"\n{'='*70}")
        print("✓ MUSCLE GROUPS CREATED")
        print(f"{'='*70}\n")

    def _create_group(self, group_id, group_data):
        """Create a single muscle group and link to FMA muscles"""

        print(f"Creating {group_data['name']}...")

        # Create MuscleGroup node
        self.graph.execute_query("""
            MERGE (mg:MuscleGroup {id: $id})
            SET mg.name = $name,
                mg.common_name = $common_name,
                mg.region = $region
        """, parameters={
            'id': f"MUSCLE_GROUP:{group_id.lower()}",
            'name': group_data['name'],
            'common_name': group_data['common_name'],
            'region': group_data['region']
        })

        # Link to FMA muscles
        muscles_found = 0
        for common_name in group_data['fma_common_names']:
            result = self.graph.execute_query("""
                MATCH (mg:MuscleGroup {id: $group_id})
                MATCH (m:Muscle)
                WHERE m.common_name = $common_name
                  AND m.fma_id IS NOT NULL
                MERGE (mg)-[:INCLUDES]->(m)
                RETURN m.name as muscle_name
            """, parameters={
                'group_id': f"MUSCLE_GROUP:{group_id.lower()}",
                'common_name': common_name
            })

            if result:
                muscles_found += len(result)
                for r in result:
                    print(f"  ✓ {group_data['name']} includes: {r['muscle_name']}")

        if muscles_found == 0:
            print(f"  ⚠️  No muscles found for {group_data['name']}")

    def _verify_creation(self):
        """Verify muscle groups were created"""

        print("\nVerifying muscle groups...")

        result = self.graph.execute_query("""
            MATCH (mg:MuscleGroup)
            OPTIONAL MATCH (mg)-[:INCLUDES]->(m:Muscle)
            RETURN mg.name as group_name,
                   count(m) as muscle_count
            ORDER BY muscle_count DESC, group_name
        """)

        print(f"\n  Muscle Groups Created: {len(result)}")
        for r in result:
            print(f"    • {r['group_name']:15s}: {r['muscle_count']} muscles")


if __name__ == "__main__":
    creator = MuscleGroupCreatorV2()
    try:
        creator.create_muscle_groups()
    finally:
        creator.close()
