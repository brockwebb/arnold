#!/usr/bin/env python3
"""
Re-link existing FFDB exercises to Muscle nodes
Uses the raw_* properties already stored on Exercise nodes
Safer than full reimport - only adds TARGETS relationships
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

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


def main():
    print(f"\n{'='*70}")
    print("RE-LINK FFDB EXERCISES TO MUSCLE NODES")
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

    # Get FFDB exercises without TARGETS→Muscle relationships
    print("Finding FFDB exercises to re-link...")
    
    result = graph.execute_query("""
        MATCH (ex:Exercise)
        WHERE ex.source = 'functional-fitness-db'
        OPTIONAL MATCH (ex)-[t:TARGETS]->(m:Muscle)
        WITH ex, count(m) as muscle_count
        WHERE muscle_count = 0
        RETURN ex.id as id, ex.name as name
        ORDER BY ex.id
    """)
    
    print(f"  Found {len(result)} exercises without muscle links\n")
    
    if len(result) == 0:
        print("  All FFDB exercises already have muscle links!")
        graph.close()
        return

    # Stats
    stats = {
        'processed': 0,
        'linked': 0,
        'not_found': []
    }

    # Process each exercise
    for record in tqdm(result, desc="Re-linking"):
        exercise_id = record['id']
        
        # Get raw muscle names from the exercise
        ex_result = graph.execute_query("""
            MATCH (ex:Exercise {id: $id})
            RETURN ex.raw_primary_muscle as primary,
                   ex.raw_secondary_muscle as secondary,
                   ex.raw_tertiary_muscle as tertiary
        """, parameters={'id': exercise_id})
        
        if not ex_result:
            continue
            
        ex_data = ex_result[0]
        stats['processed'] += 1
        
        # Link each muscle
        for role, raw_name in [
            ('primary', ex_data.get('primary')),
            ('secondary', ex_data.get('secondary')),
            ('tertiary', ex_data.get('tertiary'))
        ]:
            if not raw_name or raw_name == 'nan':
                continue
                
            normalized = raw_name.lower().strip()
            
            # Try mapping
            target_name = MUSCLE_NAME_MAP.get(normalized)
            
            if target_name:
                muscle_id = muscle_cache.get(target_name.lower())
                
                if muscle_id:
                    graph.execute_query("""
                        MATCH (ex:Exercise {id: $ex_id})
                        MATCH (m:Muscle {id: $muscle_id})
                        MERGE (ex)-[t:TARGETS]->(m)
                        SET t.role = $role,
                            t.source = 'functional-fitness-db',
                            t.raw_name = $raw_name,
                            t.confidence = 0.8,
                            t.human_verified = false,
                            t.created_at = datetime()
                    """, parameters={
                        'ex_id': exercise_id,
                        'muscle_id': muscle_id,
                        'role': role if role != 'tertiary' else 'secondary',
                        'raw_name': raw_name
                    })
                    stats['linked'] += 1
                else:
                    stats['not_found'].append(raw_name)
            else:
                stats['not_found'].append(raw_name)

    graph.close()

    print(f"\n{'='*70}")
    print("RE-LINK COMPLETE")
    print(f"{'='*70}\n")
    
    print(f"  Exercises processed: {stats['processed']}")
    print(f"  Muscle links created: {stats['linked']}")
    
    if stats['not_found']:
        unique_missing = list(set(stats['not_found']))
        print(f"\n  ⚠ Muscles not found ({len(unique_missing)} unique):")
        for m in sorted(unique_missing)[:20]:
            print(f"      - {m}")
        if len(unique_missing) > 20:
            print(f"      ... and {len(unique_missing) - 20} more")


if __name__ == "__main__":
    main()
