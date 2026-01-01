#!/usr/bin/env python3
"""
Add muscle targeting to FFDB exercises from source Excel file
Matches exercises by NAME (not index) for robustness
"""

import pandas as pd
import sys
from pathlib import Path
import re

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

EXCEL_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx"

# Muscle name normalization map
MUSCLE_NAME_MAP = {
    # Core
    'rectus abdominis': 'Rectus Abdominis',
    'abs': 'Rectus Abdominis',
    'abdominals': 'Rectus Abdominis',
    'obliques': 'External Obliques',
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
    'rhomboid major': 'Rhomboids',
    'rhomboid minor': 'Rhomboids',
    'trapezius': 'Trapezius (Middle)',
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
    'middle back': 'Rhomboids',
    
    # Chest
    'pectoralis major': 'Pectoralis Major',
    'pectoralis': 'Pectoralis Major',
    'pecs': 'Pectoralis Major',
    'chest': 'Pectoralis Major',
    'pectoralis minor': 'Pectoralis Minor',
    'serratus anterior': 'Serratus Anterior',
    'serratus': 'Serratus Anterior',
    
    # Shoulders
    'deltoid': 'Deltoid (Anterior)',
    'deltoids': 'Deltoid (Anterior)',
    'shoulders': 'Deltoid (Anterior)',
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
    'rotator cuff': 'Infraspinatus',
    
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
    'hamstrings': 'Biceps Femoris',
    'biceps femoris': 'Biceps Femoris',
    'semimembranosus': 'Semimembranosus',
    'semitendinosus': 'Semitendinosus',
    
    # Quads
    'quadriceps': 'Rectus Femoris',
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
    'hip abductors': 'Gluteus Medius',
    'abductors': 'Gluteus Medius',
}


def normalize_name(name):
    """Normalize exercise name for matching"""
    if not name:
        return None
    # Lowercase, strip whitespace, remove extra spaces
    n = str(name).lower().strip()
    n = re.sub(r'\s+', ' ', n)
    return n


def main():
    print(f"\n{'='*70}")
    print("ADD MUSCLE TARGETING TO FFDB EXERCISES")
    print(f"{'='*70}\n")

    graph = ArnoldGraph()
    
    # Build muscle cache
    print("Building muscle cache...")
    result = graph.execute_query("""
        MATCH (m:Muscle)
        WHERE m.deprecated IS NULL OR m.deprecated = false
        RETURN m.id as id, m.name as name, m.common_name as common_name
    """)
    
    muscle_cache = {}
    for record in result:
        muscle_cache[record['name'].lower()] = record['id']
        if record['common_name']:
            muscle_cache[record['common_name'].lower()] = record['id']
    
    print(f"  ✓ Loaded {len(result)} muscles\n")

    # Build exercise name to ID mapping from database
    print("Building exercise name index...")
    result = graph.execute_query("""
        MATCH (ex:Exercise)
        WHERE ex.source = 'functional-fitness-db'
        RETURN ex.id as id, ex.name as name
    """)
    
    exercise_index = {}
    for record in result:
        normalized = normalize_name(record['name'])
        if normalized:
            exercise_index[normalized] = record['id']
    
    print(f"  ✓ Indexed {len(exercise_index)} exercises\n")

    # Load Excel file
    print(f"Loading: {EXCEL_FILE}")
    df = pd.read_excel(EXCEL_FILE, sheet_name=0, header=None)
    
    # Find header row (row 15 based on earlier analysis)
    # Columns: 0=Exercise, 5=Prime Mover, 6=Secondary, 7=Tertiary
    
    print(f"  ✓ Loaded Excel file\n")

    # Stats
    stats = {
        'excel_rows': 0,
        'matched': 0,
        'not_matched': [],
        'muscle_links': 0,
        'muscles_not_found': []
    }

    # Process each row starting after header
    print("Processing Excel rows...")
    for idx in tqdm(range(16, len(df)), desc="Adding muscle links"):
        row = df.iloc[idx]
        
        exercise_name = row[0]
        if pd.isna(exercise_name) or str(exercise_name) == 'nan':
            continue
            
        exercise_name = str(exercise_name).strip()
        
        # Skip header-like rows
        if any(x in exercise_name.lower() for x in ['exercise', 'update notes', 'database']):
            continue
            
        stats['excel_rows'] += 1
        
        # Find matching exercise in database
        normalized = normalize_name(exercise_name)
        exercise_id = exercise_index.get(normalized)
        
        if not exercise_id:
            stats['not_matched'].append(exercise_name)
            continue
            
        stats['matched'] += 1
        
        # Get muscle names from Excel
        primary = str(row[5]).strip() if pd.notna(row[5]) else None
        secondary = str(row[6]).strip() if pd.notna(row[6]) else None
        tertiary = str(row[7]).strip() if pd.notna(row[7]) else None
        
        # Process each muscle
        for role, raw_name in [
            ('primary', primary),
            ('secondary', secondary),
            ('secondary', tertiary)  # Treat tertiary as secondary
        ]:
            if not raw_name or raw_name == 'nan':
                continue
                
            # Skip header row values
            if any(x in raw_name.lower() for x in ['prime mover', 'secondary muscle', 'tertiary']):
                continue
                
            normalized_muscle = raw_name.lower().strip()
            
            # Try mapping
            target_name = MUSCLE_NAME_MAP.get(normalized_muscle)
            
            if target_name:
                muscle_id = muscle_cache.get(target_name.lower())
                
                if muscle_id:
                    # Check if relationship already exists
                    existing = graph.execute_query("""
                        MATCH (ex:Exercise {id: $ex_id})-[t:TARGETS]->(m:Muscle {id: $muscle_id})
                        RETURN t
                    """, parameters={
                        'ex_id': exercise_id,
                        'muscle_id': muscle_id
                    })
                    
                    if not existing:
                        graph.execute_query("""
                            MATCH (ex:Exercise {id: $ex_id})
                            MATCH (m:Muscle {id: $muscle_id})
                            CREATE (ex)-[t:TARGETS {
                                role: $role,
                                source: 'functional-fitness-db',
                                raw_name: $raw_name,
                                confidence: 0.8,
                                human_verified: false,
                                created_at: datetime()
                            }]->(m)
                        """, parameters={
                            'ex_id': exercise_id,
                            'muscle_id': muscle_id,
                            'role': role,
                            'raw_name': raw_name
                        })
                        stats['muscle_links'] += 1
                else:
                    stats['muscles_not_found'].append(raw_name)
            else:
                stats['muscles_not_found'].append(raw_name)

    graph.close()

    print(f"\n{'='*70}")
    print("COMPLETE")
    print(f"{'='*70}\n")
    
    print(f"  Excel rows processed: {stats['excel_rows']}")
    print(f"  Exercises matched: {stats['matched']}")
    print(f"  Exercises not matched: {len(stats['not_matched'])}")
    print(f"  Muscle links created: {stats['muscle_links']}")
    
    if stats['not_matched']:
        print(f"\n  ⚠ Exercises not found in DB ({len(stats['not_matched'])}):")
        for ex in stats['not_matched'][:10]:
            print(f"      - {ex}")
        if len(stats['not_matched']) > 10:
            print(f"      ... and {len(stats['not_matched']) - 10} more")
    
    if stats['muscles_not_found']:
        unique_missing = list(set(stats['muscles_not_found']))
        print(f"\n  ⚠ Muscles not mapped ({len(unique_missing)} unique):")
        for m in sorted(unique_missing)[:20]:
            print(f"      - {m}")
        if len(unique_missing) > 20:
            print(f"      ... and {len(unique_missing) - 20} more")


if __name__ == "__main__":
    main()
