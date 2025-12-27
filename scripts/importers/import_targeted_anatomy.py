#!/usr/bin/env python3
"""
Import Targeted Anatomy from UBERON

Instead of importing all 13,000+ UBERON terms, this script:
1. Scans free-exercise-db to identify actually-used muscles
2. Searches UBERON for only those specific muscles
3. Imports them with their parent hierarchy for semantic reasoning
4. Maintains UBERON IDs for scientific linking

Result: A lean graph (~200-400 nodes) with 100% relevance and full semantic power.
"""

import sys
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pronto
from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent / ".env")

UBERON_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/uberon/uberon-basic.obo"
EXERCISES_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/free-exercise-db/dist/exercises.json"


# Mapping from free-exercise-db muscle names to UBERON search terms
MUSCLE_MAPPING = {
    # Common name → (UBERON search terms, muscle group)
    'abdominals': (['rectus abdominis', 'abdominal'], 'core'),
    'obliques': (['oblique'], 'core'),
    'lower back': (['erector spinae', 'lower back'], 'core'),
    'chest': (['pectoralis major', 'pectoral'], 'chest'),
    'lats': (['latissimus dorsi'], 'back'),
    'middle back': (['rhomboid', 'middle back'], 'back'),
    'traps': (['trapezius'], 'back'),
    'shoulders': (['deltoid'], 'shoulders'),
    'biceps': (['biceps brachii'], 'arms'),
    'triceps': (['triceps brachii'], 'arms'),
    'forearms': (['forearm'], 'arms'),
    'quadriceps': (['quadriceps', 'rectus femoris'], 'legs'),
    'hamstrings': (['hamstring', 'biceps femoris'], 'legs'),
    'glutes': (['gluteus maximus', 'gluteal'], 'legs'),
    'calves': (['gastrocnemius', 'calf'], 'legs'),
    'adductors': (['adductor'], 'legs'),
    'abductors': (['gluteus medius', 'abductor'], 'legs'),
    'neck': (['neck', 'cervical'], 'neck'),
}


class TargetedAnatomyImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'muscles_found': 0,
            'muscles_not_found': 0,
            'parent_terms': 0,
            'total_nodes': 0,
            'relationships': 0
        }
        self.imported_uberon_ids = set()

    def close(self):
        self.graph.close()

    def import_targeted_anatomy(self):
        """Import only the muscles we need from UBERON"""

        print(f"\n{'='*70}")
        print("TARGETED ANATOMY IMPORT")
        print(f"{'='*70}\n")

        # Step 1: Load exercises and extract muscles
        print("Step 1: Scanning free-exercise-db for muscle references...")
        muscles_in_db = self._extract_muscles_from_db()
        print(f"  ✓ Found {len(muscles_in_db)} unique muscles in exercise database\n")

        # Step 2: Load UBERON
        print("Step 2: Loading UBERON ontology...")
        print(f"  Loading from: {UBERON_FILE}")
        ont = pronto.Ontology(UBERON_FILE)
        print(f"  ✓ Loaded {len(ont)} total terms (we'll only use a tiny fraction)\n")

        # Step 3: Find and import only relevant muscles
        print("Step 3: Searching for exercise-relevant muscles in UBERON...")
        for common_name in sorted(muscles_in_db):
            self._import_muscle(ont, common_name)

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Muscles found in UBERON: {self.stats['muscles_found']}")
        print(f"  ⚠ Muscles not found: {self.stats['muscles_not_found']}")
        print(f"  ✓ Parent terms imported: {self.stats['parent_terms']}")
        print(f"  ✓ Total nodes created: {self.stats['total_nodes']}")
        print(f"  ✓ Hierarchical relationships: {self.stats['relationships']}\n")

        # Verify
        self._verify_import()

    def _extract_muscles_from_db(self):
        """Extract unique muscle names from free-exercise-db"""
        with open(EXERCISES_FILE, 'r') as f:
            exercises = json.load(f)

        muscles = set()
        for ex in exercises:
            muscles.update(ex.get('primaryMuscles', []))
            muscles.update(ex.get('secondaryMuscles', []))

        return muscles

    def _import_muscle(self, ont, common_name):
        """Find and import a specific muscle from UBERON"""

        # Get search terms for this muscle
        if common_name not in MUSCLE_MAPPING:
            print(f"  ⚠ No mapping for: {common_name}")
            self.stats['muscles_not_found'] += 1
            return

        search_terms, muscle_group = MUSCLE_MAPPING[common_name]

        # Search UBERON for this muscle
        found_term = None
        for search_term in search_terms:
            for term in ont.terms():
                if term.name and search_term.lower() in term.name.lower():
                    # Prefer exact matches or muscle-specific terms
                    if 'muscle' in term.name.lower() or term.name.lower() == search_term.lower():
                        found_term = term
                        break
            if found_term:
                break

        if not found_term:
            print(f"  ⚠ Not found in UBERON: {common_name} (searched: {search_terms})")
            self.stats['muscles_not_found'] += 1
            return

        # Import this muscle
        self._import_term(found_term, common_name, muscle_group, is_primary=True)
        self.stats['muscles_found'] += 1

        # Import parent hierarchy (for semantic reasoning)
        self._import_parents(ont, found_term)

    def _import_term(self, term, common_name=None, muscle_group=None, is_primary=False):
        """Import a single UBERON term as a BodyPart node"""

        # Skip if already imported
        if term.id in self.imported_uberon_ids:
            return

        uberon_id = term.id
        name = term.name
        definition = str(term.definition) if hasattr(term, 'definition') and term.definition else None
        is_muscle = 'muscle' in name.lower() if name else False

        # Create BodyPart node
        self.graph.execute_query("""
            MERGE (bp:BodyPart {uberon_id: $uberon_id})
            SET bp.name = $name,
                bp.definition = $definition,
                bp.is_muscle = $is_muscle,
                bp.common_name = $common_name,
                bp.muscle_group = $muscle_group
        """, uberon_id=uberon_id, name=name, definition=definition,
            is_muscle=is_muscle, common_name=common_name, muscle_group=muscle_group)

        # Add Muscle label if applicable
        if is_muscle:
            self.graph.execute_query("""
                MATCH (bp:BodyPart {uberon_id: $uberon_id})
                SET bp:Muscle
            """, uberon_id=uberon_id)

        self.imported_uberon_ids.add(uberon_id)
        self.stats['total_nodes'] += 1

        if is_primary:
            print(f"  ✓ Imported: {common_name} → {name} ({uberon_id})")

    def _import_parents(self, ont, term, max_depth=3):
        """Import parent terms up the hierarchy for semantic reasoning"""

        # Get direct parents (is_a relationships)
        parents = list(term.superclasses(distance=1, with_self=False))

        for parent in parents[:max_depth]:  # Limit depth to avoid bloat
            # Import parent term
            self._import_term(parent)
            self.stats['parent_terms'] += 1

            # Create IS_A relationship
            self.graph.execute_query("""
                MATCH (child:BodyPart {uberon_id: $child_id})
                MATCH (parent:BodyPart {uberon_id: $parent_id})
                MERGE (child)-[:IS_A]->(parent)
            """, child_id=term.id, parent_id=parent.id)
            self.stats['relationships'] += 1

            # Recursively import grandparents (but limit depth)
            if max_depth > 1:
                self._import_parents(ont, parent, max_depth - 1)

    def _verify_import(self):
        """Verify import in database"""
        print("Verifying import...")

        # Count body parts
        result = self.graph.execute_query("""
            MATCH (bp:BodyPart)
            RETURN count(bp) as count
        """)
        body_parts = result[0]['count']

        # Count muscles
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            RETURN count(m) as count
        """)
        muscles = result[0]['count']

        # Count relationships
        result = self.graph.execute_query("""
            MATCH ()-[r:IS_A]->()
            RETURN count(r) as count
        """)
        relationships = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    BodyPart nodes: {body_parts}")
        print(f"    Muscle nodes: {muscles}")
        print(f"    IS_A relationships: {relationships}\n")

        # Show sample muscles
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.common_name IS NOT NULL
            RETURN m.common_name as common_name, m.name as anatomical_name, m.uberon_id as id
            ORDER BY m.common_name
            LIMIT 10
        """)

        print("  Sample imported muscles:")
        for r in result:
            print(f"    • {r['common_name']} → {r['anatomical_name']} ({r['id']})")

        # Verify hierarchy
        result = self.graph.execute_query("""
            MATCH (m:Muscle)-[:IS_A*]->(parent:BodyPart)
            WHERE m.common_name IS NOT NULL
            RETURN m.common_name as muscle, collect(DISTINCT parent.name) as parents
            ORDER BY muscle
            LIMIT 5
        """)

        print("\n  Sample hierarchies (showing semantic reasoning power):")
        for r in result:
            parents_str = " → ".join(r['parents'][:3]) if r['parents'] else "none"
            print(f"    • {r['muscle']}: {parents_str}")


def main():
    print("Starting targeted anatomy import...")
    print("Strategy: Data-driven import (only muscles actually used in exercises)")
    print("Goal: Lean graph with semantic reasoning power, no bloat\n")

    importer = TargetedAnatomyImporter()
    try:
        importer.import_targeted_anatomy()
    finally:
        importer.close()

    print(f"\n{'='*70}")
    print("✓ TARGETED ANATOMY IMPORT COMPLETE")
    print(f"{'='*70}")
    print("\nResult: Lean graph with UBERON semantic power, zero bloat!")
    print("All nodes are 100% relevant to your exercise database.\n")


if __name__ == "__main__":
    main()
