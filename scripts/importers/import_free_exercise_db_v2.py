#!/usr/bin/env python3
"""
Import Free-Exercise-DB exercises - FIXED VERSION
- Uses m.id instead of fma_id for muscle matching
- Stores raw muscle names for fallback
- Better muscle name normalization
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

# Muscle name normalization map
# Maps Free-Exercise-DB names to our Muscle node names
MUSCLE_NAME_MAP = {
    # Core
    'abdominals': 'Rectus Abdominis',
    'abs': 'Rectus Abdominis',
    
    # Back
    'lats': 'Latissimus Dorsi',
    'middle back': 'Rhomboids',
    'lower back': 'Erector Spinae',
    'traps': 'Trapezius (Middle)',
    
    # Chest
    'chest': 'Pectoralis Major',
    
    # Shoulders
    'shoulders': 'Deltoid (Anterior)',  # Default - often need context
    
    # Arms
    'biceps': 'Biceps Brachii',
    'triceps': 'Triceps Brachii',
    'forearms': 'Forearm Flexors',
    
    # Glutes
    'glutes': 'Gluteus Maximus',
    
    # Legs
    'quadriceps': 'Rectus Femoris',
    'hamstrings': 'Biceps Femoris',
    'calves': 'Gastrocnemius',
    'adductors': 'Hip Adductors',
    'abductors': 'Gluteus Medius',
    
    # Neck (not in our ontology yet)
    'neck': None,
}

# Movement pattern inference from exercise properties
def infer_movement_pattern(ex_data):
    """Infer movement pattern from exercise metadata"""
    name = ex_data.get('name', '').lower()
    category = ex_data.get('category', '').lower()
    force = ex_data.get('force', '').lower()
    
    patterns = []
    
    # Pull movements
    if 'pull' in name or 'row' in name or 'curl' in name:
        if 'lat' in name or 'pulldown' in name or 'pull-up' in name or 'pullup' in name or 'chin' in name:
            patterns.append('PATTERN:vertical_pull')
        elif 'curl' in name:
            patterns.append('PATTERN:elbow_flexion')
        else:
            patterns.append('PATTERN:horizontal_pull')
    
    # Push movements
    if 'press' in name or 'push' in name or 'extension' in name:
        if 'overhead' in name or 'military' in name or 'shoulder' in name:
            patterns.append('PATTERN:vertical_push')
        elif 'bench' in name or 'floor' in name or 'push-up' in name or 'pushup' in name:
            patterns.append('PATTERN:horizontal_push')
        elif 'tricep' in name or 'skull' in name:
            patterns.append('PATTERN:elbow_extension')
    
    # Lower body
    if 'squat' in name:
        patterns.append('PATTERN:squat')
    if 'deadlift' in name or 'rdl' in name or 'romanian' in name or 'good morning' in name:
        patterns.append('PATTERN:hip_hinge')
    if 'lunge' in name or 'step' in name or 'split squat' in name:
        patterns.append('PATTERN:lunge')
    if 'leg curl' in name or 'hamstring curl' in name:
        patterns.append('PATTERN:knee_flexion')
    if 'leg extension' in name:
        patterns.append('PATTERN:knee_extension')
    if 'hip thrust' in name or 'glute bridge' in name:
        patterns.append('PATTERN:hip_extension')
    
    # Core
    if 'plank' in name:
        if 'side' in name:
            patterns.append('PATTERN:anti_lateral_flexion')
        else:
            patterns.append('PATTERN:anti_extension')
    if 'crunch' in name or 'sit-up' in name or 'situp' in name:
        patterns.append('PATTERN:spinal_flexion')
    if 'russian twist' in name or 'woodchop' in name or 'rotation' in name:
        patterns.append('PATTERN:rotation')
    if 'pallof' in name:
        patterns.append('PATTERN:anti_rotation')
    if 'leg raise' in name or 'knee raise' in name:
        patterns.append('PATTERN:hip_flexion')
    
    return patterns[:2]  # Max 2 patterns per exercise


class FreeExerciseDBImporterV2:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'exercises': 0,
            'primary_targets': 0,
            'secondary_targets': 0,
            'muscles_not_found': [],
            'pattern_links': 0
        }
        self._muscle_cache = {}

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
        """Import all exercises from Free-Exercise-DB"""

        print(f"\n{'='*70}")
        print("FREE-EXERCISE-DB IMPORT V2 (FIXED)")
        print(f"{'='*70}\n")

        # Build muscle cache first
        print("Loading muscle cache...")
        self._build_muscle_cache()

        print(f"\nLoading exercises from: {EXERCISES_FILE}")
        with open(EXERCISES_FILE) as f:
            exercises_data = json.load(f)

        print(f"  ✓ Loaded {len(exercises_data)} exercises\n")

        print("Importing exercises...")

        for i, ex_data in enumerate(exercises_data):
            self._import_exercise(ex_data)

            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(exercises_data)} exercises...")

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Imported {self.stats['exercises']} exercises")
        print(f"  ✓ Primary muscle targets: {self.stats['primary_targets']}")
        print(f"  ✓ Secondary muscle targets: {self.stats['secondary_targets']}")
        print(f"  ✓ Pattern links: {self.stats['pattern_links']}")
        
        if self.stats['muscles_not_found']:
            unique_missing = list(set(self.stats['muscles_not_found']))
            print(f"\n  ⚠ Muscles not found ({len(unique_missing)} unique):")
            for m in sorted(unique_missing):
                print(f"      - {m}")

        # Verify
        self._verify_import()

    def _import_exercise(self, ex_data):
        """Import a single exercise"""

        exercise_id = ex_data.get('id')
        if not exercise_id:
            exercise_id = ex_data['name'].lower().replace(' ', '_')

        exercise_id = f"EXERCISE:{exercise_id}"

        name = ex_data.get('name')
        category = ex_data.get('category')
        force_type = ex_data.get('force', 'unknown')
        mechanic = ex_data.get('mechanic', 'unknown')
        difficulty = ex_data.get('level', 'beginner')
        equipment = ex_data.get('equipment', 'none')
        instructions = ' '.join(ex_data.get('instructions', []))
        
        # Get raw muscle arrays
        primary_muscles = ex_data.get('primaryMuscles', [])
        secondary_muscles = ex_data.get('secondaryMuscles', [])

        # Create Exercise node with raw muscle data stored
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
                ex.source = 'free-exercise-db',
                ex.raw_primary_muscles = $raw_primary,
                ex.raw_secondary_muscles = $raw_secondary,
                ex.imported_at = datetime(),
                ex.importer_version = 2
        """, parameters={
            'id': exercise_id,
            'name': name,
            'category': category,
            'force_type': force_type,
            'mechanic': mechanic,
            'difficulty': difficulty,
            'equipment': equipment,
            'instructions': instructions,
            'raw_primary': primary_muscles,
            'raw_secondary': secondary_muscles
        })

        self.stats['exercises'] += 1

        # Link to primary muscles
        for muscle_name in primary_muscles:
            if self._link_to_muscle(exercise_id, muscle_name, role="primary"):
                self.stats['primary_targets'] += 1

        # Link to secondary muscles
        for muscle_name in secondary_muscles:
            if self._link_to_muscle(exercise_id, muscle_name, role="secondary"):
                self.stats['secondary_targets'] += 1

        # Infer and link movement patterns
        patterns = infer_movement_pattern(ex_data)
        for pattern_id in patterns:
            if self._link_to_pattern(exercise_id, pattern_id, name):
                self.stats['pattern_links'] += 1

    def _normalize_muscle_name(self, muscle_name):
        """Normalize muscle name to match our Muscle nodes"""
        if not muscle_name:
            return None
            
        normalized = muscle_name.lower().strip()
        
        # Check our mapping first
        if normalized in MUSCLE_NAME_MAP:
            mapped = MUSCLE_NAME_MAP[normalized]
            if mapped is None:  # Explicitly unmapped (e.g., 'neck')
                return None
            return mapped
        
        # Try to find in cache directly
        if normalized in self._muscle_cache:
            muscle_id = self._muscle_cache[normalized]
            # Return the proper capitalized name
            for name, mid in self._muscle_cache.items():
                if mid == muscle_id:
                    # Find the properly capitalized version
                    result = self.graph.execute_query("""
                        MATCH (m:Muscle {id: $id}) RETURN m.name as name
                    """, parameters={'id': muscle_id})
                    if result:
                        return result[0]['name']
        
        return None

    def _link_to_muscle(self, exercise_id, muscle_name, role="primary"):
        """Link exercise to specific Muscle node"""

        normalized_name = self._normalize_muscle_name(muscle_name)
        
        if not normalized_name:
            self.stats['muscles_not_found'].append(muscle_name)
            return False

        muscle_id = self._muscle_cache.get(normalized_name.lower())
        
        if not muscle_id:
            self.stats['muscles_not_found'].append(muscle_name)
            return False

        # Create TARGETS relationship
        self.graph.execute_query("""
            MATCH (ex:Exercise {id: $ex_id})
            MATCH (m:Muscle {id: $muscle_id})
            MERGE (ex)-[t:TARGETS]->(m)
            SET t.role = $role,
                t.source = 'free-exercise-db',
                t.raw_name = $raw_name,
                t.confidence = 0.7,
                t.human_verified = false
        """, parameters={
            'ex_id': exercise_id,
            'muscle_id': muscle_id,
            'role': role,
            'raw_name': muscle_name
        })

        return True

    def _link_to_pattern(self, exercise_id, pattern_id, exercise_name):
        """Link exercise to MovementPattern node"""
        
        # Check if pattern exists
        result = self.graph.execute_query("""
            MATCH (mp:MovementPattern {id: $pattern_id})
            RETURN mp.id
        """, parameters={'pattern_id': pattern_id})
        
        if not result:
            return False
        
        self.graph.execute_query("""
            MATCH (ex:Exercise {id: $ex_id})
            MATCH (mp:MovementPattern {id: $pattern_id})
            MERGE (ex)-[r:HAS_MOVEMENT_PATTERN]->(mp)
            SET r.source = 'inferred',
                r.confidence = 0.7
        """, parameters={
            'ex_id': exercise_id,
            'pattern_id': pattern_id
        })

        return True

    def _verify_import(self):
        """Verify import in database"""
        print("\nVerifying import...")

        # Count exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.source = 'free-exercise-db')
            RETURN count(ex) as count
        """)
        exercises = result[0]['count']

        # Count TARGETS relationships to Muscle nodes
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.source = 'free-exercise-db')-[t:TARGETS]->(m:Muscle)
            RETURN count(t) as count
        """)
        muscle_targets = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    Exercise nodes: {exercises}")
        print(f"    TARGETS → Muscle: {muscle_targets}")

        # Sample exercises with specific muscles
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.source = 'free-exercise-db')-[t:TARGETS {role: 'primary'}]->(m:Muscle)
            WITH ex, collect(m.name) as muscles
            WHERE size(muscles) > 0
            RETURN ex.name as exercise, muscles
            LIMIT 5
        """)

        print("\n  Sample exercises with specific muscle targets:")
        for r in result:
            muscles_str = ", ".join(r['muscles'])
            print(f"    • {r['exercise']}: {muscles_str}")


def main():
    print("Starting Free-Exercise-DB import V2...")

    importer = FreeExerciseDBImporterV2()
    try:
        importer.import_exercises()
    finally:
        importer.close()

    print(f"\n{'='*70}")
    print("✓ FREE-EXERCISE-DB IMPORT V2 COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
