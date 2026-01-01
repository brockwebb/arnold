#!/usr/bin/env python3
"""
Add TARGETS relationships from Free-Exercise-DB exercises to Muscle nodes.
Reads source JSON, matches exercises by name, creates relationships.

Run: python scripts/importers/add_free_exercise_db_muscle_targeting.py

Prerequisites:
- Neo4j running with CYBERDYNE-CORE database
- .env file with NEO4J_PASSWORD
- Free-Exercise-DB JSON file in ontologies/exercises/
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()

JSON_FILE = Path(__file__).parent.parent.parent / "ontologies/exercises/free-exercise-db/dist/exercises.json"

# Muscle name mapping: Free-Exercise-DB name -> our Muscle node ID
# Free-Exercise-DB uses simple, lowercase muscle group names
MUSCLE_MAP = {
    'abdominals': 'MUSCLE:rectus_abdominis',
    'abductors': 'MUSCLE:gluteus_medius',  # Primary hip abductor
    'adductors': 'MUSCLE:hip_adductors',
    'biceps': 'MUSCLE:biceps_brachii',
    'calves': 'MUSCLE:gastrocnemius',
    'chest': 'MUSCLE:pectoralis_major',
    'forearms': 'MUSCLE:forearm_flexors',
    'glutes': 'MUSCLE:gluteus_maximus',
    'hamstrings': 'MUSCLE:biceps_femoris',
    'lats': 'MUSCLE:latissimus_dorsi',
    'lower back': 'MUSCLE:erector_spinae',
    'middle back': 'MUSCLE:rhomboids',
    'neck': None,  # Skip - not in our ontology
    'quadriceps': 'MUSCLE:rectus_femoris',
    'shoulders': 'MUSCLE:deltoid_anterior',  # Default to anterior
    'traps': 'MUSCLE:trapezius_middle',
    'triceps': 'MUSCLE:triceps_brachii',
}


def main():
    print(f"\n{'='*70}")
    print("FREE-EXERCISE-DB → MUSCLE TARGETING IMPORT")
    print(f"{'='*70}\n")

    # Connect to Neo4j
    graph = ArnoldGraph()
    
    # Verify connection
    if not graph.verify_connectivity():
        print("ERROR: Cannot connect to Neo4j")
        return
    
    print("✓ Connected to Neo4j\n")

    # Load JSON
    print(f"Loading: {JSON_FILE}")
    with open(JSON_FILE, 'r') as f:
        exercises = json.load(f)
    print(f"✓ Loaded {len(exercises)} exercises\n")

    # Build exercise name index from database
    print("Building exercise index from database...")
    result = graph.execute_query("""
        MATCH (ex:Exercise)
        WHERE ex.source = 'free-exercise-db'
        RETURN ex.id as id, toLower(ex.name) as name
    """)
    
    exercise_index = {r['name']: r['id'] for r in result}
    print(f"✓ Indexed {len(exercise_index)} Free-Exercise-DB exercises in database\n")

    # Stats
    stats = {
        'json_exercises': 0,
        'exercises_matched': 0,
        'exercises_not_found': [],
        'relationships_created': 0,
        'muscles_not_mapped': set()
    }

    # Process JSON exercises
    print("Processing exercises...")
    
    for ex_data in exercises:
        exercise_name = ex_data.get('name', '').strip()
        if not exercise_name:
            continue
        
        stats['json_exercises'] += 1
        
        # Find exercise in database
        exercise_id = exercise_index.get(exercise_name.lower())
        if not exercise_id:
            stats['exercises_not_found'].append(exercise_name)
            continue
        
        stats['exercises_matched'] += 1
        
        # Get muscle arrays
        primary_muscles = ex_data.get('primaryMuscles', [])
        secondary_muscles = ex_data.get('secondaryMuscles', [])
        
        # Process primary muscles
        for muscle_name in primary_muscles:
            muscle_name_lower = muscle_name.lower().strip()
            muscle_id = MUSCLE_MAP.get(muscle_name_lower)
            
            if muscle_id is None:
                if muscle_name_lower:
                    stats['muscles_not_mapped'].add(muscle_name_lower)
                continue
            
            result = graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (ex)-[t:TARGETS]->(m)
                ON CREATE SET 
                    t.role = 'primary',
                    t.source = 'free-exercise-db',
                    t.confidence = 0.7,
                    t.created_at = datetime()
                RETURN count(t) as created
            """, parameters={
                'ex_id': exercise_id,
                'muscle_id': muscle_id
            })
            
            if result and result[0]['created'] > 0:
                stats['relationships_created'] += 1
        
        # Process secondary muscles
        for muscle_name in secondary_muscles:
            muscle_name_lower = muscle_name.lower().strip()
            muscle_id = MUSCLE_MAP.get(muscle_name_lower)
            
            if muscle_id is None:
                if muscle_name_lower:
                    stats['muscles_not_mapped'].add(muscle_name_lower)
                continue
            
            result = graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (ex)-[t:TARGETS]->(m)
                ON CREATE SET 
                    t.role = 'secondary',
                    t.source = 'free-exercise-db',
                    t.confidence = 0.7,
                    t.created_at = datetime()
                RETURN count(t) as created
            """, parameters={
                'ex_id': exercise_id,
                'muscle_id': muscle_id
            })
            
            if result and result[0]['created'] > 0:
                stats['relationships_created'] += 1
        
        # Progress every 200
        if stats['json_exercises'] % 200 == 0:
            print(f"  Processed {stats['json_exercises']} exercises...")

    graph.close()

    # Final report
    print(f"\n{'='*70}")
    print("IMPORT COMPLETE")
    print(f"{'='*70}\n")
    
    print(f"  JSON exercises:        {stats['json_exercises']}")
    print(f"  Exercises matched:     {stats['exercises_matched']}")
    print(f"  Exercises not found:   {len(stats['exercises_not_found'])}")
    print(f"  Relationships created: {stats['relationships_created']}")
    
    if stats['exercises_not_found']:
        print(f"\n  ⚠ Exercises not in database ({len(stats['exercises_not_found'])}):")
        for ex in stats['exercises_not_found'][:10]:
            print(f"      - {ex}")
        if len(stats['exercises_not_found']) > 10:
            print(f"      ... and {len(stats['exercises_not_found']) - 10} more")
    
    if stats['muscles_not_mapped']:
        print(f"\n  ⚠ Muscles not in mapping ({len(stats['muscles_not_mapped'])}):")
        for m in sorted(stats['muscles_not_mapped']):
            print(f"      - {m}")


if __name__ == "__main__":
    main()
