#!/usr/bin/env python3
"""
Import Functional Fitness DB - FIXED VERSION
- Uses m.id instead of fma_id for muscle matching
- Stores raw muscle names for fallback
- Links to MovementPattern nodes
- Better muscle name normalization
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

# Muscle name normalization map
# Maps source names to our Muscle node names
MUSCLE_NAME_MAP = {
    # Core
    'rectus abdominis': 'Rectus Abdominis',
    'abs': 'Rectus Abdominis',
    'abdominals': 'Rectus Abdominis',
    'obliques': 'External Obliques',  # Default to external
    'external obliques': 'External Obliques',
    'internal obliques': 'Internal Obliques',
    'transverse abdominis': 'Transverse Abdominis',
    'transversus abdominis': 'Transverse Abdominis',
    'tva': 'Transverse Abdominis',
    'quadratus lumborum': 'Quadratus Lumborum',
    'ql': 'Quadratus Lumborum',
    'iliopsoas': 'Iliopsoas',
    'hip flexors': 'Iliopsoas',
    'psoas': 'Iliopsoas',
    
    # Back
    'latissimus dorsi': 'Latissimus Dorsi',
    'lats': 'Latissimus Dorsi',
    'rhomboids': 'Rhomboids',
    'rhomboid': 'Rhomboids',
    'trapezius': 'Trapezius (Middle)',  # Default to middle
    'traps': 'Trapezius (Middle)',
    'upper trapezius': 'Trapezius (Upper)',
    'upper traps': 'Trapezius (Upper)',
    'middle trapezius': 'Trapezius (Middle)',
    'mid traps': 'Trapezius (Middle)',
    'lower trapezius': 'Trapezius (Lower)',
    'lower traps': 'Trapezius (Lower)',
    'erector spinae': 'Erector Spinae',
    'spinal erectors': 'Erector Spinae',
    'erectors': 'Erector Spinae',
    'lower back': 'Erector Spinae',
    'teres major': 'Teres Major',
    
    # Chest
    'pectoralis major': 'Pectoralis Major',
    'pecs': 'Pectoralis Major',
    'chest': 'Pectoralis Major',
    'pectoralis minor': 'Pectoralis Minor',
    'serratus anterior': 'Serratus Anterior',
    'serratus': 'Serratus Anterior',
    
    # Shoulders
    'deltoid': 'Deltoid (Anterior)',  # Default to anterior
    'deltoids': 'Deltoid (Anterior)',
    'anterior deltoid': 'Deltoid (Anterior)',
    'front deltoid': 'Deltoid (Anterior)',
    'front delt': 'Deltoid (Anterior)',
    'lateral deltoid': 'Deltoid (Lateral)',
    'side deltoid': 'Deltoid (Lateral)',
    'medial deltoid': 'Deltoid (Lateral)',
    'posterior deltoid': 'Deltoid (Posterior)',
    'rear deltoid': 'Deltoid (Posterior)',
    'rear delt': 'Deltoid (Posterior)',
    'supraspinatus': 'Supraspinatus',
    'infraspinatus': 'Infraspinatus',
    'teres minor': 'Teres Minor',
    'subscapularis': 'Subscapularis',
    'rotator cuff': 'Infraspinatus',  # Map to one of the SITS muscles
    
    # Arms
    'biceps': 'Biceps Brachii',
    'biceps brachii': 'Biceps Brachii',
    'brachialis': 'Brachialis',
    'triceps': 'Triceps Brachii',
    'triceps brachii': 'Triceps Brachii',
    
    # Forearms
    'forearms': 'Forearm Flexors',
    'forearm': 'Forearm Flexors',
    'wrist flexors': 'Forearm Flexors',
    'wrist extensors': 'Forearm Extensors',
    'forearm flexors': 'Forearm Flexors',
    'forearm extensors': 'Forearm Extensors',
    
    # Glutes
    'gluteus maximus': 'Gluteus Maximus',
    'glutes': 'Gluteus Maximus',
    'glute max': 'Gluteus Maximus',
    'gluteus medius': 'Gluteus Medius',
    'glute med': 'Gluteus Medius',
    'gluteus minimus': 'Gluteus Minimus',
    'glute min': 'Gluteus Minimus',
    
    # Hamstrings
    'hamstrings': 'Biceps Femoris',  # Default to biceps femoris
    'biceps femoris': 'Biceps Femoris',
    'semimembranosus': 'Semimembranosus',
    'semitendinosus': 'Semitendinosus',
    
    # Quads
    'quadriceps': 'Rectus Femoris',  # Default to rectus femoris
    'quads': 'Rectus Femoris',
    'rectus femoris': 'Rectus Femoris',
    'vastus lateralis': 'Vastus Lateralis',
    'vastus medialis': 'Vastus Medialis',
    'vmo': 'Vastus Medialis',
    'vastus intermedius': 'Vastus Intermedius',
    
    # Lower leg
    'gastrocnemius': 'Gastrocnemius',
    'calves': 'Gastrocnemius',
    'calf': 'Gastrocnemius',
    'soleus': 'Soleus',
    'tibialis anterior': 'Tibialis Anterior',
    'shin': 'Tibialis Anterior',
    
    # Hip
    'hip adductors': 'Hip Adductors',
    'adductors': 'Hip Adductors',
    'tensor fasciae latae': 'Tensor Fasciae Latae',
    'tfl': 'Tensor Fasciae Latae',
    'hip abductors': 'Gluteus Medius',  # Primary hip abductor
}

# Movement pattern mapping from FFDB categories to our patterns
MOVEMENT_PATTERN_MAP = {
    # Pulls
    'pull': 'PATTERN:horizontal_pull',
    'vertical pull': 'PATTERN:vertical_pull',
    'horizontal pull': 'PATTERN:horizontal_pull',
    'row': 'PATTERN:horizontal_pull',
    'pulldown': 'PATTERN:vertical_pull',
    'pull-up': 'PATTERN:vertical_pull',
    'chin-up': 'PATTERN:vertical_pull',
    
    # Pushes
    'push': 'PATTERN:horizontal_push',
    'vertical push': 'PATTERN:vertical_push',
    'horizontal push': 'PATTERN:horizontal_push',
    'press': 'PATTERN:horizontal_push',
    'overhead press': 'PATTERN:vertical_push',
    'bench press': 'PATTERN:horizontal_push',
    'push-up': 'PATTERN:horizontal_push',
    
    # Lower body
    'squat': 'PATTERN:squat',
    'hinge': 'PATTERN:hip_hinge',
    'hip hinge': 'PATTERN:hip_hinge',
    'deadlift': 'PATTERN:hip_hinge',
    'lunge': 'PATTERN:lunge',
    'step': 'PATTERN:lunge',
    
    # Core
    'anti-extension': 'PATTERN:anti_extension',
    'anti-rotation': 'PATTERN:anti_rotation',
    'anti-lateral flexion': 'PATTERN:anti_lateral_flexion',
    'flexion': 'PATTERN:spinal_flexion',
    'rotation': 'PATTERN:rotation',
    
    # Functional
    'carry': 'PATTERN:loaded_carry',
    'loaded carry': 'PATTERN:loaded_carry',
}


class FunctionalFitnessImporterV2:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'muscle_links': 0,
            'muscle_not_found': [],
            'pattern_links': 0
        }
        self._muscle_cache = {}  # Cache muscle lookups

    def close(self):
        self.graph.close()

    def _build_muscle_cache(self):
        """Pre-load all muscles for fast lookup"""
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.deprecated IS NULL OR m.deprecated = false
            RETURN m.id as id, m.name as name, m.common_name as common_name
        """)
        
        for record in result:
            # Index by name and common_name (lowercase)
            self._muscle_cache[record['name'].lower()] = record['id']
            if record['common_name']:
                self._muscle_cache[record['common_name'].lower()] = record['id']
        
        print(f"  ✓ Loaded {len(result)} muscles into cache")

    def import_exercises(self):
        """Import Functional Fitness DB exercises with provenance"""

        print(f"\n{'='*70}")
        print("FUNCTIONAL FITNESS DB IMPORT V2 (FIXED)")
        print(f"{'='*70}\n")

        # Build muscle cache first
        print("Loading muscle cache...")
        self._build_muscle_cache()

        print(f"\nLoading: {EXCEL_FILE}")

        # Load with skiprows to avoid intro text, no header
        # Row 16 is the header row (0-indexed: 15), data starts at row 17
        df = pd.read_excel(EXCEL_FILE, sheet_name=0, skiprows=15, header=0)

        # Use first row as header, rename with our mapping
        df.columns = range(len(df.columns))
        df = df.rename(columns=COLUMN_MAPPING)

        # Filter out rows where exercise_name is NaN or contains header text
        df = df[df['exercise_name'].notna()]
        df = df[~df['exercise_name'].astype(str).str.contains('Exercise Name|exercise database|update notes', case=False, na=False)]

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
        print(f"  ✓ Pattern links created: {self.stats['pattern_links']}")
        print(f"  ✗ Failed: {self.stats['failed']}")
        
        if self.stats['muscle_not_found']:
            unique_missing = list(set(self.stats['muscle_not_found']))
            print(f"\n  ⚠ Muscles not found ({len(unique_missing)} unique):")
            for m in sorted(unique_missing)[:20]:
                print(f"      - {m}")
            if len(unique_missing) > 20:
                print(f"      ... and {len(unique_missing) - 20} more")

    def _import_exercise(self, idx, row):
        """Import a single exercise"""

        exercise_name = str(row.get('exercise_name', '')).strip()

        if not exercise_name or exercise_name == 'nan':
            raise ValueError("No exercise name")

        exercise_id = f"CANONICAL:FFDB:{idx}"

        # Extract and clean properties
        def clean_str(val, excludes=None):
            s = str(val).strip() if pd.notna(val) else None
            if s == 'nan':
                return None
            if excludes and any(x in s for x in excludes):
                return None
            return s

        difficulty = clean_str(row.get('difficulty'), ['Difficulty Level'])
        category = clean_str(row.get('category'))
        body_region = clean_str(row.get('body_region'), ['Body Region'])
        mechanics = clean_str(row.get('mechanics'), ['Mechanics'])
        force_type = clean_str(row.get('force_type'), ['Force Type'])
        
        # Store raw muscle names for fallback/debugging
        raw_primary = clean_str(row.get('primary_muscle'))
        raw_secondary = clean_str(row.get('secondary_muscle'))
        raw_tertiary = clean_str(row.get('tertiary_muscle'))
        
        # Store movement patterns from source
        pattern1 = clean_str(row.get('movement_pattern_1'))
        pattern2 = clean_str(row.get('movement_pattern_2'))
        pattern3 = clean_str(row.get('movement_pattern_3'))

        # Create exercise WITH PROVENANCE and raw muscle names
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
                ex.raw_primary_muscle = $raw_primary,
                ex.raw_secondary_muscle = $raw_secondary,
                ex.raw_tertiary_muscle = $raw_tertiary,
                ex.raw_pattern_1 = $pattern1,
                ex.raw_pattern_2 = $pattern2,
                ex.raw_pattern_3 = $pattern3,
                ex.imported_at = datetime(),
                ex.importer_version = 2
        """, parameters={
            'id': exercise_id,
            'name': exercise_name,
            'category': category,
            'difficulty': difficulty,
            'body_region': body_region,
            'mechanics': mechanics,
            'force_type': force_type,
            'raw_primary': raw_primary,
            'raw_secondary': raw_secondary,
            'raw_tertiary': raw_tertiary,
            'pattern1': pattern1,
            'pattern2': pattern2,
            'pattern3': pattern3
        })

        # Link muscles (primary, secondary, tertiary)
        muscles_linked = 0
        for muscle_name, role in [
            (raw_primary, 'primary'),
            (raw_secondary, 'secondary'),
            (raw_tertiary, 'tertiary')
        ]:
            if muscle_name:
                if self._link_to_muscle(exercise_id, muscle_name, role):
                    muscles_linked += 1

        self.stats['muscle_links'] += muscles_linked
        
        # Link movement patterns
        for pattern in [pattern1, pattern2, pattern3]:
            if pattern and self._link_to_pattern(exercise_id, pattern):
                self.stats['pattern_links'] += 1

    def _normalize_muscle_name(self, muscle_name):
        """Normalize muscle name to match our Muscle nodes"""
        if not muscle_name:
            return None
            
        normalized = muscle_name.lower().strip()
        
        # Check our mapping first
        if normalized in MUSCLE_NAME_MAP:
            return MUSCLE_NAME_MAP[normalized]
        
        # Try to find in cache directly
        if normalized in self._muscle_cache:
            # Get the actual name from the muscle
            muscle_id = self._muscle_cache[normalized]
            # Extract name from cache by finding the key
            for name, mid in self._muscle_cache.items():
                if mid == muscle_id and name[0].isupper():
                    return name.title()
        
        return None

    def _link_to_muscle(self, exercise_id, muscle_name, role):
        """Link exercise to specific Muscle node"""
        if not muscle_name:
            return False

        # Normalize the muscle name
        normalized_name = self._normalize_muscle_name(muscle_name)
        
        if not normalized_name:
            self.stats['muscle_not_found'].append(muscle_name)
            return False
        
        # Find the muscle ID from cache
        muscle_id = self._muscle_cache.get(normalized_name.lower())
        
        if not muscle_id:
            self.stats['muscle_not_found'].append(muscle_name)
            return False

        # Create TARGETS relationship using muscle id
        self.graph.execute_query("""
            MATCH (ex:Exercise {id: $ex_id})
            MATCH (m:Muscle {id: $muscle_id})
            MERGE (ex)-[t:TARGETS]->(m)
            SET t.role = $role,
                t.source = 'functional-fitness-db',
                t.raw_name = $raw_name,
                t.confidence = 0.8,
                t.human_verified = false
        """, parameters={
            'ex_id': exercise_id,
            'muscle_id': muscle_id,
            'role': role,
            'raw_name': muscle_name
        })

        return True

    def _link_to_pattern(self, exercise_id, pattern_name):
        """Link exercise to MovementPattern node"""
        if not pattern_name:
            return False
            
        normalized = pattern_name.lower().strip()
        
        # Check our mapping
        pattern_id = MOVEMENT_PATTERN_MAP.get(normalized)
        
        if not pattern_id:
            # Try partial matching
            for key, pid in MOVEMENT_PATTERN_MAP.items():
                if key in normalized or normalized in key:
                    pattern_id = pid
                    break
        
        if not pattern_id:
            return False
        
        # Create HAS_MOVEMENT_PATTERN relationship
        self.graph.execute_query("""
            MATCH (ex:Exercise {id: $ex_id})
            MATCH (mp:MovementPattern {id: $pattern_id})
            MERGE (ex)-[r:HAS_MOVEMENT_PATTERN]->(mp)
            SET r.source = 'functional-fitness-db',
                r.raw_name = $raw_name
        """, parameters={
            'ex_id': exercise_id,
            'pattern_id': pattern_id,
            'raw_name': pattern_name
        })

        return True


if __name__ == "__main__":
    importer = FunctionalFitnessImporterV2()
    try:
        importer.import_exercises()
    finally:
        importer.close()

    print(f"\n{'='*70}")
    print("✓ FUNCTIONAL FITNESS DB IMPORT V2 COMPLETE")
    print(f"{'='*70}\n")
