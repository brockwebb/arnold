#!/usr/bin/env python3
"""
Import Functional Fitness DB ALONGSIDE Free-Exercise-DB
Tags exercises with source provenance
"""

import pandas as pd
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

EXCEL_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx"

# Column mapping based on analysis
COLUMN_MAPPING = {
    1: 'exercise_name',
    2: 'video_demo',
    3: 'video_explanation',
    4: 'difficulty',
    5: 'primary_muscle_group',
    6: 'primary_muscle',
    7: 'secondary_muscle',
    8: 'tertiary_muscle',
    9: 'equipment',
    10: 'num_primary_items',
    11: 'secondary_equipment',
    12: 'num_secondary_items',
    13: 'position',
    14: 'arm_type',
    15: 'arm_movement',
    16: 'grip',
    17: 'load_position',
    18: 'leg_movement',
    19: 'elevation',
    20: 'exercise_type',
    21: 'movement_pattern_1',
    22: 'movement_pattern_2',
    23: 'movement_pattern_3',
    24: 'plane_of_motion_1',
    25: 'plane_of_motion_2',
    26: 'plane_of_motion_3',
    27: 'body_region',
    28: 'force_type',
    29: 'mechanics',
    30: 'laterality',
    31: 'category'
}


class FunctionalFitnessImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'muscle_links': 0
        }

    def close(self):
        self.graph.close()

    def import_exercises(self):
        """Import Functional Fitness DB exercises with provenance"""

        print(f"\n{'='*70}")
        print("FUNCTIONAL FITNESS DB IMPORT")
        print(f"{'='*70}\n")

        print(f"Loading: {EXCEL_FILE}")

        # Load with skiprows to avoid intro text, no header
        df = pd.read_excel(EXCEL_FILE, sheet_name=0, skiprows=4, header=None)

        # Rename columns
        df = df.rename(columns=COLUMN_MAPPING)

        # Filter out rows where exercise_name is NaN or contains header text
        df = df[df['exercise_name'].notna()]
        df = df[~df['exercise_name'].str.contains('Exercise Name|exercise database', case=False, na=False)]

        print(f"  ✓ Loaded {len(df)} exercises from Functional Fitness DB\n")

        self.stats['total'] = len(df)

        # Process each exercise
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Importing"):
            try:
                self._import_exercise(idx, row)
                self.stats['successful'] += 1
            except Exception as e:
                print(f"\n  ❌ Error on row {idx}: {e}")
                self.stats['failed'] += 1

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  Total exercises: {self.stats['total']}")
        print(f"  ✓ Successfully imported: {self.stats['successful']}")
        print(f"  ✓ Muscle links created: {self.stats['muscle_links']}")
        print(f"  ✗ Failed: {self.stats['failed']}\n")

        self._print_stats()

    def _import_exercise(self, idx, row):
        """Import a single exercise"""

        exercise_name = str(row.get('exercise_name', '')).strip()

        if not exercise_name or exercise_name == 'nan':
            raise ValueError("No exercise name")

        exercise_id = f"CANONICAL:FFDB:{idx}"

        # Extract properties
        difficulty = str(row.get('difficulty', '')).strip()
        if difficulty == 'nan' or 'Difficulty Level' in difficulty:
            difficulty = None

        category = str(row.get('category', '')).strip()
        if category == 'nan':
            category = None

        body_region = str(row.get('body_region', '')).strip()
        if body_region == 'nan' or 'Body Region' in body_region:
            body_region = None

        mechanics = str(row.get('mechanics', '')).strip()
        if mechanics == 'nan' or 'Mechanics' in mechanics:
            mechanics = None

        force_type = str(row.get('force_type', '')).strip()
        if force_type == 'nan' or 'Force Type' in force_type:
            force_type = None

        # Create exercise WITH PROVENANCE
        self.graph.execute_query("""
            MERGE (ex:Exercise {id: $id})
            SET ex.name = $name,
                ex.category = $category,
                ex.is_canonical = true,
                ex.source = 'functional-fitness-db',
                ex.difficulty = $difficulty,
                ex.body_region = $body_region,
                ex.mechanics = $mechanics,
                ex.force_type = $force_type,
                ex.imported_at = datetime(),
                ex.provenance_verified = false
        """, parameters={
            'id': exercise_id,
            'name': exercise_name,
            'category': category,
            'difficulty': difficulty,
            'body_region': body_region,
            'mechanics': mechanics,
            'force_type': force_type
        })

        # Link equipment
        equipment = str(row.get('equipment', '')).strip()
        if equipment and equipment != 'nan':
            self._link_equipment(exercise_id, equipment)

        # Link muscles (primary, secondary, tertiary)
        muscles_linked = 0
        for col_name, role in [
            ('primary_muscle', 'primary'),
            ('secondary_muscle', 'secondary'),
            ('tertiary_muscle', 'tertiary')
        ]:
            muscle_name = str(row.get(col_name, '')).strip()
            if muscle_name and muscle_name != 'nan' and not any(x in muscle_name for x in ['Primary Muscle', 'Secondary', 'Tertiary']):
                if self._link_to_muscle(exercise_id, muscle_name, role):
                    muscles_linked += 1

        self.stats['muscle_links'] += muscles_linked

    def _link_equipment(self, exercise_id, equipment_str):
        """Link to equipment categories"""

        mapping = {
            'barbell': 'EQ_CAT:barbell',
            'dumbbell': 'EQ_CAT:dumbbell',
            'bodyweight': 'EQ_CAT:bodyweight',
            'body only': 'EQ_CAT:bodyweight',
            'band': 'EQ_CAT:resistance_band',
            'kettlebell': 'EQ_CAT:kettlebell',
            'cable': 'EQ_CAT:cable',
            'clubbell': 'EQ_CAT:clubbell',
            'sliders': 'EQ_CAT:sliders',
            'gymnastic rings': 'EQ_CAT:gymnastic_rings',
            'macebell': 'EQ_CAT:macebell',
            'suspension trainer': 'EQ_CAT:suspension_trainer',
        }

        equipment_lower = equipment_str.lower()

        for key, eq_id in mapping.items():
            if key in equipment_lower:
                # Create equipment category if needed
                self.graph.execute_query("""
                    MERGE (eq:EquipmentCategory {id: $eq_id})
                    SET eq.name = $name
                """, parameters={
                    'eq_id': eq_id,
                    'name': key.title()
                })

                # Link exercise to equipment
                self.graph.execute_query("""
                    MATCH (ex:Exercise {id: $ex_id})
                    MATCH (eq:EquipmentCategory {id: $eq_id})
                    MERGE (ex)-[:REQUIRES_EQUIPMENT]->(eq)
                """, parameters={
                    'ex_id': exercise_id,
                    'eq_id': eq_id
                })
                break  # Only link to first match

    def _link_to_muscle(self, exercise_id, muscle_name, role):
        """Link to FMA muscle or muscle group"""

        if not muscle_name:
            return False

        normalized = muscle_name.lower().strip()

        # Try Muscle first
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE toLower(m.name) CONTAINS $muscle_name
               OR toLower(m.common_name) CONTAINS $muscle_name
            RETURN m.fma_id as target_id, 'Muscle' as target_type
            LIMIT 1
        """, parameters={'muscle_name': normalized})

        # Try MuscleGroup if no Muscle found
        if not result:
            result = self.graph.execute_query("""
                MATCH (mg:MuscleGroup)
                WHERE toLower(mg.name) CONTAINS $muscle_name
                   OR toLower(mg.common_name) CONTAINS $muscle_name
                RETURN mg.id as target_id, 'MuscleGroup' as target_type
                LIMIT 1
            """, parameters={'muscle_name': normalized})

        if not result:
            return False

        target_id = result[0]['target_id']
        target_type = result[0]['target_type']

        if target_type == 'Muscle':
            self.graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (m:Muscle {fma_id: $target_id})
                MERGE (ex)-[t:TARGETS]->(m)
                SET t.role = $role,
                    t.source = 'functional-fitness-db',
                    t.llm_inferred = false,
                    t.human_verified = false
            """, parameters={
                'ex_id': exercise_id,
                'target_id': target_id,
                'role': role
            })
        else:  # MuscleGroup
            self.graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (mg:MuscleGroup {id: $target_id})
                MERGE (ex)-[t:TARGETS]->(mg)
                SET t.role = $role,
                    t.source = 'functional-fitness-db',
                    t.llm_inferred = false,
                    t.human_verified = false
            """, parameters={
                'ex_id': exercise_id,
                'target_id': target_id,
                'role': role
            })

        return True

    def _print_stats(self):
        """Print stats for both sources"""

        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN ex.source as source, count(ex) as count
            ORDER BY source
        """)

        print("📊 Canonical Exercises by Source:")
        for record in result:
            print(f"  {record['source']:30s}: {record['count']:4d}")

        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN count(ex) as total
        """)
        total = result[0]['total']
        print(f"  {'TOTAL':30s}: {total:4d}\n")


if __name__ == "__main__":
    importer = FunctionalFitnessImporter()
    try:
        importer.import_exercises()
    finally:
        importer.close()

    print(f"{'='*70}")
    print("✓ FUNCTIONAL FITNESS DB IMPORT COMPLETE")
    print(f"{'='*70}\n")
