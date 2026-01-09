#!/usr/bin/env python3
"""
Import muscle targeting data from enrichment JSON files to Neo4j.

Reads from: data/enrichment/exercises/*.json
Writes to: Neo4j Exercise TARGETS relationships

Use this to recover muscle data that was lost during migration,
or to enrich newly created exercises.

Usage:
    python scripts/import_enrichment_muscles.py --dry-run    # Preview
    python scripts/import_enrichment_muscles.py              # Execute
    python scripts/import_enrichment_muscles.py --validate   # Check coverage
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from neo4j import GraphDatabase

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENRICHMENT_DIR = PROJECT_ROOT / "data" / "enrichment" / "exercises"

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

# Mapping from enrichment names to canonical exercise IDs
# The JSON files use CUSTOM:* IDs, but those have been migrated
EXERCISE_ID_MAPPING = {
    # Original CUSTOM IDs mapped to their new canonical IDs
    'CUSTOM:Kettlebell_Swings': 'CANONICAL:ARNOLD:KB_SWING_2H',
    'CUSTOM:Kickboxing': 'CANONICAL:ARNOLD:KICKBOXING',
    'CUSTOM:Sandbag_Overhead_Hold': 'CANONICAL:ARNOLD:SANDBAG_OVERHEAD_HOLD',
    'CUSTOM:Trap-Bar_Static_Hold': 'CANONICAL:ARNOLD:TRAP_BAR_STATIC_HOLD',
    'CUSTOM:Weighted_Pull-Up': 'EXERCISE:Weighted_Pull_Ups',
    'CUSTOM:AirDyne': 'CANONICAL:ARNOLD:AIRDYNE',
    'CUSTOM:Sandbag_Push_Press': 'CANONICAL:ARNOLD:SANDBAG_PUSH_PRESS',
    'CUSTOM:Trap_Bar_Romanian_Deadlift': 'CANONICAL:ARNOLD:TRAP_BAR_ROMANIAN_DEADLIFT',
    'CUSTOM:Prone_Y-Raises': 'CANONICAL:ARNOLD:PRONE_Y_RAISES',
    'CUSTOM:Mixed_Load_Farmer_Carry': 'CANONICAL:ARNOLD:MIXED_LOAD_FARMER_CARRY',
    'CUSTOM:Box_Step-Up': 'CANONICAL:ARNOLD:BOX_STEP_UP',
    'CUSTOM:Sternum_Pull-Up': 'CANONICAL:ARNOLD:STERNUM_PULL_UP',
    'CUSTOM:Bear-Hug_Static_Hold': 'CANONICAL:ARNOLD:BEAR_HUG_STATIC_HOLD',
    'CUSTOM:Kneeling_Ab_Wheel': 'EXERCISE:Ab_Roller',
    'CUSTOM:Weighted_Dead_Hang': 'CANONICAL:ARNOLD:WEIGHTED_DEAD_HANG',
    'CUSTOM:Rowing_Machine': 'CANONICAL:ARNOLD:ROWING_MACHINE',
    'CUSTOM:Sandbag_Box_Squat': 'CANONICAL:ARNOLD:SANDBAG_BOX_SQUAT',
    'CUSTOM:Viking_Press': 'CANONICAL:ARNOLD:VIKING_PRESS',
    'CUSTOM:Plank_with_Weighted_Reach-Throughs': 'CANONICAL:ARNOLD:PLANK_WITH_WEIGHTED_REACH_THROUGHS',
    'CUSTOM:Duffel_Row': 'CANONICAL:ARNOLD:DUFFEL_ROW',
    'CUSTOM:Goblet_Squat_Hold': 'CANONICAL:ARNOLD:GOBLET_SQUAT_HOLD',
    'CUSTOM:Sandbag_Floor_Press': 'CANONICAL:ARNOLD:SANDBAG_FLOOR_PRESS',
    'CUSTOM:One-Arm_Dead_Hang': 'CANONICAL:ARNOLD:ONE_ARM_DEAD_HANG',
    'CUSTOM:Sandbag_Overhead_Carry': 'CANONICAL:ARNOLD:SANDBAG_OVERHEAD_CARRY',
    'CUSTOM:Elbow_Plank': 'CANONICAL:ARNOLD:ELBOW_PLANK',
    'CUSTOM:Scap_Push-Up': 'CANONICAL:ARNOLD:SCAP_PUSH_UP',
    'CUSTOM:Gladiator_Squat': 'CANONICAL:ARNOLD:GLADIATOR_SQUAT',
    'CUSTOM:Sandbag_Strict_Press': 'CANONICAL:ARNOLD:SANDBAG_STRICT_PRESS',
    'CUSTOM:Boxing': 'CANONICAL:ARNOLD:BOXING',
    'CUSTOM:Farmer_Carry': 'EXERCISE:Farmers_Walk',
    'CUSTOM:KB_V-Sit_Pass-Over': 'CANONICAL:ARNOLD:KB_V_SIT_PASS_OVER',
    'CUSTOM:Side_Plank_Crunches': 'CANONICAL:ARNOLD:SIDE_PLANK_CRUNCHES',
    'CUSTOM:Sledgehammer_Tire_Slams': 'CANONICAL:ARNOLD:SLEDGEHAMMER_TIRE_SLAMS',
    'CUSTOM:Suitcase_Carry': 'CANONICAL:ARNOLD:SUITCASE_CARRY',
    'CUSTOM:Sandbag_Row': 'CANONICAL:ARNOLD:SANDBAG_ROW',
    'CUSTOM:Helms_Row': 'CANONICAL:ARNOLD:HELMS_ROW',
    'CUSTOM:Jefferson_Curl': 'CANONICAL:ARNOLD:JEFFERSON_CURL',
    'CUSTOM:Sandbag_Good_Morning': 'CANONICAL:ARNOLD:SANDBAG_GOOD_MORNING',
    'CUSTOM:Sandbag_March': 'CANONICAL:ARNOLD:SANDBAG_MARCH',
    'CUSTOM:Turkish_Get-Up': 'CANONICAL:ARNOLD:TURKISH_GET_UP',
    'CUSTOM:Pallof_Press': 'EXERCISE:Pallof_Press',
    'CUSTOM:Shoulder_Dislocate': 'CANONICAL:ARNOLD:SHOULDER_DISLOCATE',
    'CUSTOM:Side-Lying_Clamshells': 'CANONICAL:FFDB:3238',
    'CUSTOM:Scapular_Pull-Up': 'EXERCISE:Scapular_Pull-Up',
}

# Standard muscle name mappings to handle variations
MUSCLE_ALIASES = {
    'glutes': 'Gluteus Maximus',
    'gluteus maximus': 'Gluteus Maximus',
    'hamstrings': 'Biceps Femoris',
    'biceps femoris': 'Biceps Femoris',
    'lower back': 'Erector Spinae',
    'erector spinae': 'Erector Spinae',
    'core': 'Rectus Abdominis',
    'abdominals': 'Rectus Abdominis',
    'rectus abdominis': 'Rectus Abdominis',
    'obliques': 'External Obliques',
    'external obliques': 'External Obliques',
    'internal obliques': 'Internal Obliques',
    'transverse abdominis': 'Transverse Abdominis',
    'lats': 'Latissimus Dorsi',
    'latissimus dorsi': 'Latissimus Dorsi',
    'traps': 'Trapezius (Upper)',
    'trapezius': 'Trapezius (Upper)',
    'trapezius (middle)': 'Trapezius (Middle)',
    'trapezius (lower)': 'Trapezius (Lower)',
    'rhomboids': 'Rhomboid Major',
    'deltoid (posterior)': 'Deltoid (Posterior)',
    'deltoid (anterior)': 'Deltoid (Anterior)',
    'deltoid (lateral)': 'Deltoid (Lateral)',
    'posterior deltoids': 'Deltoid (Posterior)',
    'anterior deltoids': 'Deltoid (Anterior)',
    'shoulders': 'Deltoid (Anterior)',
    'rotator cuff': 'Infraspinatus',
    'rotator cuffs': 'Infraspinatus',
    'forearms': 'Forearm Flexors',
    'forearm flexors': 'Forearm Flexors',
    'grip muscles': 'Forearm Flexors',
    'quadriceps': 'Rectus Femoris',
    'quads': 'Rectus Femoris',
    'rectus femoris': 'Rectus Femoris',
    'hip adductors': 'Adductor Magnus',
    'adductors': 'Adductor Magnus',
    'calves': 'Gastrocnemius',
    'gastrocnemius': 'Gastrocnemius',
    'soleus': 'Soleus',
    'biceps': 'Biceps Brachii',
    'biceps brachii': 'Biceps Brachii',
    'triceps': 'Triceps Brachii',
    'triceps brachii': 'Triceps Brachii',
    'pecs': 'Pectoralis Major',
    'chest': 'Pectoralis Major',
    'pectoralis major': 'Pectoralis Major',
    'pectoralis minor': 'Pectoralis Minor',
    'serratus anterior': 'Serratus Anterior',
    'hip flexors': 'Iliopsoas',
    'iliopsoas': 'Iliopsoas',
    'gluteus medius': 'Gluteus Medius',
    'gluteus minimus': 'Gluteus Minimus',
    'tensor fasciae latae': 'Tensor Fasciae Latae',
    'tfl': 'Tensor Fasciae Latae',
}


def normalize_muscle_name(name: str) -> str:
    """Normalize muscle name to match Neo4j Muscle nodes."""
    normalized = name.lower().strip()
    return MUSCLE_ALIASES.get(normalized, name.title())


class MuscleImporter:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.stats = {
            'files_processed': 0,
            'exercises_matched': 0,
            'exercises_skipped': 0,
            'muscles_created': 0,
            'errors': []
        }
    
    def close(self):
        self.driver.close()
    
    def log(self, msg: str):
        prefix = "[DRY-RUN] " if self.dry_run else ""
        print(f"{prefix}{msg}")
    
    def find_exercise(self, json_id: str, exercise_name: str = None) -> str | None:
        """Map JSON exercise ID to current Neo4j ID.
        
        Resolution order:
        1. Check explicit mapping
        2. Direct ID lookup
        3. Search by alias (exercise name from JSON)
        4. Generate likely CANONICAL:ARNOLD:* ID and check
        """
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # 1. Check explicit mapping
            if json_id in EXERCISE_ID_MAPPING:
                target_id = EXERCISE_ID_MAPPING[json_id]
                result = session.run(
                    "MATCH (e:Exercise {id: $id}) RETURN e.id as id",
                    id=target_id
                )
                record = result.single()
                if record:
                    return record['id']
            
            # 2. Direct ID lookup
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.id as id",
                id=json_id
            )
            record = result.single()
            if record:
                return record['id']
            
            # 3. Search by alias (exercise name)
            if exercise_name:
                result = session.run("""
                    MATCH (e:Exercise)
                    WHERE e.name = $name 
                       OR $name IN e.aliases
                       OR toLower(e.name) = toLower($name)
                    RETURN e.id as id
                    LIMIT 1
                """, name=exercise_name)
                record = result.single()
                if record:
                    return record['id']
            
            # 4. Generate likely CANONICAL:ARNOLD:* ID from CUSTOM:* ID
            if json_id.startswith('CUSTOM:'):
                # CUSTOM:Side_Plank_Bag_Slide -> CANONICAL:ARNOLD:SIDE_PLANK_BAG_SLIDE
                name_part = json_id.replace('CUSTOM:', '').upper().replace('-', '_')
                canonical_id = f"CANONICAL:ARNOLD:{name_part}"
                result = session.run(
                    "MATCH (e:Exercise {id: $id}) RETURN e.id as id",
                    id=canonical_id
                )
                record = result.single()
                if record:
                    return record['id']
            
            return None
    
    def find_muscle(self, muscle_name: str) -> str | None:
        """Find muscle node by name."""
        normalized = normalize_muscle_name(muscle_name)
        
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # Try exact match first
            result = session.run(
                "MATCH (m:Muscle) WHERE m.name = $name RETURN m.name as name",
                name=normalized
            )
            record = result.single()
            if record:
                return record['name']
            
            # Try case-insensitive contains
            result = session.run(
                "MATCH (m:Muscle) WHERE toLower(m.name) CONTAINS toLower($name) RETURN m.name as name LIMIT 1",
                name=normalized
            )
            record = result.single()
            return record['name'] if record else None
    
    def import_muscles(self, exercise_id: str, primary: list, secondary: list, source: str):
        """Create TARGETS relationships for an exercise."""
        if self.dry_run:
            self.log(f"  Would create {len(primary)} primary + {len(secondary)} secondary relationships")
            return
        
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # Delete existing relationships first
            session.run(
                "MATCH (e:Exercise {id: $id})-[r:TARGETS]->() DELETE r",
                id=exercise_id
            )
            
            # Create primary relationships
            for muscle_name in primary:
                muscle = self.find_muscle(muscle_name)
                if muscle:
                    session.run("""
                        MATCH (e:Exercise {id: $eid})
                        MATCH (m:Muscle {name: $muscle})
                        MERGE (e)-[r:TARGETS]->(m)
                        SET r.role = 'primary',
                            r.source = $source,
                            r.imported_at = datetime()
                    """, eid=exercise_id, muscle=muscle, source=source)
                    self.stats['muscles_created'] += 1
                else:
                    self.stats['errors'].append(f"Muscle not found: {muscle_name}")
            
            # Create secondary relationships
            for muscle_name in secondary:
                muscle = self.find_muscle(muscle_name)
                if muscle:
                    session.run("""
                        MATCH (e:Exercise {id: $eid})
                        MATCH (m:Muscle {name: $muscle})
                        MERGE (e)-[r:TARGETS]->(m)
                        SET r.role = 'secondary',
                            r.source = $source,
                            r.imported_at = datetime()
                    """, eid=exercise_id, muscle=muscle, source=source)
                    self.stats['muscles_created'] += 1
                else:
                    self.stats['errors'].append(f"Muscle not found: {muscle_name}")
    
    def process_file(self, filepath: Path):
        """Process a single enrichment JSON file."""
        self.log(f"\nProcessing: {filepath.name}")
        
        with open(filepath) as f:
            data = json.load(f)
        
        json_id = data.get('exercise_id')
        if not json_id:
            self.log(f"  SKIP: No exercise_id in file")
            self.stats['exercises_skipped'] += 1
            return
        
        # Get exercise name for fuzzy matching
        exercise_name = data.get('exercise_name')
        
        # Find current exercise ID
        exercise_id = self.find_exercise(json_id, exercise_name)
        if not exercise_id:
            self.log(f"  SKIP: Exercise not found in Neo4j ({json_id})")
            self.stats['exercises_skipped'] += 1
            self.stats.setdefault('not_found', []).append(json_id)
            return
        
        self.log(f"  Mapped: {json_id} → {exercise_id}")
        
        # Extract muscle data
        muscles = data.get('muscles', {})
        primary = muscles.get('primary', [])
        secondary = muscles.get('secondary', [])
        
        if not primary and not secondary:
            self.log(f"  SKIP: No muscle data in file")
            self.stats['exercises_skipped'] += 1
            return
        
        # Get source info
        source = data.get('source', {})
        source_type = source.get('type', 'unknown')
        
        self.log(f"  Muscles: {len(primary)} primary, {len(secondary)} secondary")
        
        # Import
        self.import_muscles(exercise_id, primary, secondary, source_type)
        
        self.stats['exercises_matched'] += 1
        self.stats['files_processed'] += 1
    
    def run(self):
        """Process all enrichment files."""
        if not ENRICHMENT_DIR.exists():
            print(f"ERROR: Enrichment directory not found: {ENRICHMENT_DIR}")
            return
        
        json_files = list(ENRICHMENT_DIR.glob("*.json"))
        self.log(f"Found {len(json_files)} enrichment files")
        
        for filepath in sorted(json_files):
            try:
                self.process_file(filepath)
            except Exception as e:
                self.stats['errors'].append(f"{filepath.name}: {e}")
                self.log(f"  ERROR: {e}")
        
        return self.summary()
    
    def summary(self) -> str:
        lines = [
            "",
            "="*60,
            "IMPORT SUMMARY",
            "="*60,
            f"  Files processed:     {self.stats['files_processed']}",
            f"  Exercises matched:   {self.stats['exercises_matched']}",
            f"  Exercises skipped:   {self.stats['exercises_skipped']}",
            f"  Muscles created:     {self.stats['muscles_created']}",
        ]
        not_found = self.stats.get('not_found', [])
        if not_found:
            lines.append(f"  Not found in Neo4j:  {len(not_found)}")
            for nf in not_found[:15]:
                lines.append(f"    - {nf}")
            if len(not_found) > 15:
                lines.append(f"    ... and {len(not_found) - 15} more")
        if self.stats['errors']:
            lines.append(f"  Errors:              {len(self.stats['errors'])}")
            for e in self.stats['errors'][:10]:
                lines.append(f"    - {e}")
        lines.append("="*60)
        return "\n".join(lines)


def run_validation(driver):
    """Check muscle coverage."""
    print("\n" + "="*60)
    print("MUSCLE COVERAGE VALIDATION")
    print("="*60)
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # CANONICAL:ARNOLD exercises
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CANONICAL:ARNOLD:'
            OPTIONAL MATCH (e)-[r:TARGETS]->(m)
            WITH e, count(r) as muscle_count
            RETURN 
                count(e) as total,
                sum(CASE WHEN muscle_count > 0 THEN 1 ELSE 0 END) as have_muscles,
                sum(CASE WHEN muscle_count = 0 THEN 1 ELSE 0 END) as no_muscles
        """)
        r = result.single()
        print(f"\nCANONICAL:ARNOLD exercises:")
        print(f"  Total:        {r['total']}")
        print(f"  Have muscles: {r['have_muscles']}")
        print(f"  No muscles:   {r['no_muscles']}")
        
        # List ones missing muscles
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CANONICAL:ARNOLD:'
            AND NOT (e)-[:TARGETS]->()
            RETURN e.id as id, e.name as name
            ORDER BY e.name
            LIMIT 20
        """)
        missing = list(result)
        if missing:
            print(f"\n  Missing muscle data (first 20):")
            for r in missing:
                print(f"    - {r['name']}")
    
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(description='Import muscle data from enrichment JSON files')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--validate', action='store_true', help='Only check coverage')
    args = parser.parse_args()
    
    print("="*60)
    print("MUSCLE DATA IMPORT")
    print(f"Started: {datetime.now().isoformat()}")
    if args.dry_run:
        print("MODE: DRY RUN")
    if args.validate:
        print("MODE: VALIDATE ONLY")
    print("="*60)
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        if args.validate:
            run_validation(driver)
            return
        
        importer = MuscleImporter(dry_run=args.dry_run)
        importer.driver = driver
        
        summary = importer.run()
        print(summary)
        
        if not args.dry_run:
            run_validation(driver)
            print("\n✅ Import complete")
            print("\nNext: python scripts/sync_exercise_relationships.py")
        else:
            print("\n⚠️  DRY RUN - no changes made")
    
    finally:
        driver.close()


if __name__ == '__main__':
    main()
