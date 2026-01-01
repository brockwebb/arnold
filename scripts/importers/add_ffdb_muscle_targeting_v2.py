#!/usr/bin/env python3
"""
Add TARGETS relationships from FFDB exercises to Muscle nodes.
Reads source Excel, matches exercises by name, creates relationships.

Run: python scripts/importers/add_ffdb_muscle_targeting_v2.py

Prerequisites:
- Neo4j running with CYBERDYNE-CORE database
- .env file with NEO4J_PASSWORD
- FFDB Excel file in ontologies/exercises/
"""

import pandas as pd
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()

EXCEL_FILE = Path(__file__).parent.parent.parent / "ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx"

# Muscle name mapping: FFDB source name -> our Muscle node ID
MUSCLE_MAP = {
    # From FFDB analysis - 42 unique muscle names
    'adductor magnus': 'MUSCLE:hip_adductors',
    'anconeus': 'MUSCLE:triceps_brachii',
    'anterior deltoids': 'MUSCLE:deltoid_anterior',
    'biceps brachii': 'MUSCLE:biceps_brachii',
    'biceps femoris': 'MUSCLE:biceps_femoris',
    'brachialis': 'MUSCLE:brachialis',
    'brachioradialis': 'MUSCLE:forearm_flexors',
    'erector spinae': 'MUSCLE:erector_spinae',
    'extensor digitorum longus': None,  # Skip - toe specific
    'extensor hallucis longus': None,   # Skip - toe specific
    'flexor carpi radialis': 'MUSCLE:forearm_flexors',
    'gastrocnemius': 'MUSCLE:gastrocnemius',
    'gluteus maximus': 'MUSCLE:gluteus_maximus',
    'gluteus medius': 'MUSCLE:gluteus_medius',
    'gluteus minimus': 'MUSCLE:gluteus_minimus',
    'iliopsoas': 'MUSCLE:iliopsoas',
    'infraspinatus': 'MUSCLE:infraspinatus',
    'lateral deltoids': 'MUSCLE:deltoid_lateral',
    'latissimus dorsi': 'MUSCLE:latissimus_dorsi',
    'levator scapulae': 'MUSCLE:trapezius_upper',
    'medial deltoids': 'MUSCLE:deltoid_lateral',
    'obliques': 'MUSCLE:external_obliques',
    'pectoralis major': 'MUSCLE:pectoralis_major',
    'posterior deltoids': 'MUSCLE:deltoid_posterior',
    'quadriceps femoris': 'MUSCLE:rectus_femoris',
    'rectus abdominis': 'MUSCLE:rectus_abdominis',
    'rectus femoris': 'MUSCLE:rectus_femoris',
    'rhomboids': 'MUSCLE:rhomboids',
    'serratus anterior': 'MUSCLE:serratus_anterior',
    'soleus': 'MUSCLE:soleus',
    'subscapularis': 'MUSCLE:subscapularis',
    'supraspinatus': 'MUSCLE:supraspinatus',
    'tensor fasciae latae': 'MUSCLE:tensor_fasciae_latae',
    'teres major': 'MUSCLE:teres_major',
    'teres minor': 'MUSCLE:teres_minor',
    'tibialis anterior': 'MUSCLE:tibialis_anterior',
    'tibialis posterior': 'MUSCLE:soleus',
    'transverse abdominis': 'MUSCLE:transverse_abdominis',
    'trapezius': 'MUSCLE:trapezius_middle',
    'triceps brachii': 'MUSCLE:triceps_brachii',
    'upper trapezius': 'MUSCLE:trapezius_upper',
    'vastus mediais': 'MUSCLE:vastus_medialis',  # Typo in source
}


def main():
    print(f"\n{'='*70}")
    print("FFDB → MUSCLE TARGETING IMPORT")
    print(f"{'='*70}\n")

    # Connect to Neo4j
    graph = ArnoldGraph()
    
    # Verify connection
    if not graph.verify_connectivity():
        print("ERROR: Cannot connect to Neo4j")
        return
    
    print("✓ Connected to Neo4j\n")

    # Load Excel - Column 1 = Exercise Name, 6 = Primary, 7 = Secondary, 8 = Tertiary
    # Header row is 15, data starts at 16
    print(f"Loading: {EXCEL_FILE}")
    df = pd.read_excel(EXCEL_FILE, sheet_name=0, header=None)
    print(f"✓ Loaded {len(df)} rows\n")

    # Build exercise name index from database
    print("Building exercise index from database...")
    result = graph.execute_query("""
        MATCH (ex:Exercise)
        WHERE ex.source = 'functional-fitness-db'
        RETURN ex.id as id, toLower(ex.name) as name
    """)
    
    exercise_index = {r['name']: r['id'] for r in result}
    print(f"✓ Indexed {len(exercise_index)} FFDB exercises\n")

    # Stats
    stats = {
        'rows_processed': 0,
        'exercises_matched': 0,
        'exercises_not_found': 0,
        'relationships_created': 0,
        'muscles_not_mapped': set()
    }

    # Process Excel rows (data starts at row 16, 0-indexed)
    print("Processing exercises...")
    
    for idx in range(16, len(df)):
        row = df.iloc[idx]
        
        # Get exercise name (column 1)
        exercise_name = row[1]
        if pd.isna(exercise_name) or str(exercise_name).strip() == '':
            continue
        
        exercise_name = str(exercise_name).strip()
        
        # Skip header-like rows
        if any(x in exercise_name.lower() for x in ['exercise', 'update notes', 'database', 'download']):
            continue
        
        stats['rows_processed'] += 1
        
        # Find exercise in database
        exercise_id = exercise_index.get(exercise_name.lower())
        if not exercise_id:
            stats['exercises_not_found'] += 1
            continue
        
        stats['exercises_matched'] += 1
        
        # Get muscle data (columns 6, 7, 8)
        primary = str(row[6]).strip().lower() if pd.notna(row[6]) else None
        secondary = str(row[7]).strip().lower() if pd.notna(row[7]) else None
        tertiary = str(row[8]).strip().lower() if pd.notna(row[8]) else None
        
        # Process each muscle
        for role, raw_name in [('primary', primary), ('secondary', secondary), ('secondary', tertiary)]:
            if not raw_name or raw_name == 'nan':
                continue
            
            # Skip header values
            if any(x in raw_name for x in ['prime mover', 'secondary muscle', 'tertiary']):
                continue
            
            # Map to muscle ID
            muscle_id = MUSCLE_MAP.get(raw_name)
            
            if muscle_id is None:
                if raw_name not in ['nan', '']:
                    stats['muscles_not_mapped'].add(raw_name)
                continue
            
            # Create TARGETS relationship
            result = graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (m:Muscle {id: $muscle_id})
                MERGE (ex)-[t:TARGETS]->(m)
                ON CREATE SET 
                    t.role = $role,
                    t.source = 'functional-fitness-db',
                    t.confidence = 0.8,
                    t.created_at = datetime()
                RETURN count(t) as created
            """, parameters={
                'ex_id': exercise_id,
                'muscle_id': muscle_id,
                'role': role
            })
            
            if result and result[0]['created'] > 0:
                stats['relationships_created'] += 1
        
        # Progress every 500
        if stats['rows_processed'] % 500 == 0:
            print(f"  Processed {stats['rows_processed']} rows...")

    graph.close()

    # Final report
    print(f"\n{'='*70}")
    print("IMPORT COMPLETE")
    print(f"{'='*70}\n")
    
    print(f"  Rows processed:        {stats['rows_processed']}")
    print(f"  Exercises matched:     {stats['exercises_matched']}")
    print(f"  Exercises not found:   {stats['exercises_not_found']}")
    print(f"  Relationships created: {stats['relationships_created']}")
    
    if stats['muscles_not_mapped']:
        print(f"\n  ⚠ Muscles not in mapping ({len(stats['muscles_not_mapped'])}):")
        for m in sorted(stats['muscles_not_mapped']):
            print(f"      - {m}")


if __name__ == "__main__":
    main()
