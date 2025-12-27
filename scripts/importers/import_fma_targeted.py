#!/usr/bin/env python3
"""
Targeted import of FMA (Foundational Model of Anatomy)
Only imports muscles used by exercises in Free-Exercise-DB
~300 relevant anatomy nodes instead of 75,000
"""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from owlready2 import get_ontology
from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()

FMA_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/anatomy/fma.owl"
EXERCISES_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/free-exercise-db/dist/exercises.json"

class FMATargetedImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'muscles_found': 0,
            'muscles_not_found': 0,
            'body_parts': 0,
            'relationships': 0
        }
        self.imported_fma_ids = set()

    def close(self):
        self.graph.close()

    def get_muscles_from_exercises(self):
        """Extract unique muscle names from Free-Exercise-DB"""

        print("Scanning Free-Exercise-DB for muscle names...")
        with open(EXERCISES_FILE, 'r') as f:
            exercises = json.load(f)

        muscles = set()
        for ex in exercises:
            muscles.update(ex.get('primaryMuscles', []))
            muscles.update(ex.get('secondaryMuscles', []))

        print(f"  ✓ Found {len(muscles)} unique muscles in exercise database\n")
        return muscles

    def import_targeted_fma(self):
        """Import only relevant muscles from FMA"""

        print(f"\n{'='*70}")
        print("TARGETED FMA IMPORT")
        print(f"{'='*70}\n")

        # Get muscles we actually need
        exercise_muscles = self.get_muscles_from_exercises()

        print("Loading FMA ontology (this may take 1-2 minutes)...")
        onto = get_ontology(f"file://{FMA_FILE}").load()

        print(f"  ✓ Loaded FMA ontology ({len(list(onto.classes()))} total classes)\n")

        print("Searching FMA for exercise-relevant muscle terms...")

        for muscle_name in sorted(exercise_muscles):
            self._import_muscle(onto, muscle_name)

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Muscles found in FMA: {self.stats['muscles_found']}")
        print(f"  ⚠ Muscles not found: {self.stats['muscles_not_found']}")
        print(f"  ✓ Total body part nodes: {self.stats['body_parts']}")
        print(f"  ✓ Hierarchical relationships: {self.stats['relationships']}\n")

        # Verify
        self._verify_import()

    def _import_muscle(self, onto, muscle_name):
        """Find and import a specific muscle from FMA"""

        matches = self._find_fma_muscle(onto, muscle_name)

        if not matches:
            print(f"  ⚠ Not found in FMA: {muscle_name}")
            self.stats['muscles_not_found'] += 1
            return

        # Import the best match
        fma_term = matches[0]
        self._import_term(fma_term, common_name=muscle_name, is_primary=True)
        self.stats['muscles_found'] += 1

        # Import parent hierarchy (for semantic reasoning)
        self._import_parents(onto, fma_term)

        print(f"  ✓ Imported: {muscle_name} → {fma_term.name}")

    def _find_fma_muscle(self, onto, muscle_name):
        """Find FMA term matching muscle name"""
        matches = []

        search_terms = [muscle_name.lower()]

        # Add common variations
        if muscle_name == 'chest':
            search_terms.extend(['pectoralis major', 'pectoral'])
        elif muscle_name == 'lats':
            search_terms.extend(['latissimus dorsi'])
        elif muscle_name == 'traps':
            search_terms.extend(['trapezius'])
        elif muscle_name == 'abdominals':
            search_terms.extend(['rectus abdominis', 'abdominal wall'])
        elif muscle_name == 'lower back':
            search_terms.extend(['erector spinae', 'lower back muscle'])
        elif muscle_name == 'middle back':
            search_terms.extend(['rhomboid'])
        elif muscle_name == 'quadriceps':
            search_terms.extend(['quadriceps femoris'])
        elif muscle_name == 'glutes':
            search_terms.extend(['gluteus maximus', 'gluteal'])
        elif muscle_name == 'calves':
            search_terms.extend(['gastrocnemius', 'calf muscle'])
        elif muscle_name == 'shoulders':
            search_terms.extend(['deltoid'])
        elif muscle_name == 'biceps':
            search_terms.extend(['biceps brachii'])
        elif muscle_name == 'triceps':
            search_terms.extend(['triceps brachii'])

        # Search by label
        for cls in onto.classes():
            if not hasattr(cls, 'label') or not cls.label:
                continue

            for label in cls.label:
                label_text = str(label).lower()

                for search_term in search_terms:
                    if search_term in label_text:
                        # Check if it's actually a muscle
                        if self._is_muscle_term(cls):
                            matches.append(cls)
                            break

                if matches:
                    break

            if matches:
                break

        return matches

    def _is_muscle_term(self, cls):
        """Check if FMA term represents a muscle"""
        # Check label for muscle keywords
        if hasattr(cls, 'label') and cls.label:
            label_text = ' '.join([str(l) for l in cls.label]).lower()
            if 'muscle' in label_text or 'muscular' in label_text:
                return True

        return False

    def _import_term(self, fma_term, common_name=None, is_primary=False):
        """Import a single FMA term as a BodyPart node"""

        # Skip if already imported
        if fma_term.name in self.imported_fma_ids:
            return

        fma_id = fma_term.name
        name = str(fma_term.label[0]) if hasattr(fma_term, 'label') and fma_term.label else fma_term.name
        is_muscle = self._is_muscle_term(fma_term)

        # Create BodyPart node
        self.graph.execute_query("""
            MERGE (bp:BodyPart {fma_id: $fma_id})
            SET bp.name = $name,
                bp.source = 'fma',
                bp.common_name = $common_name,
                bp.is_muscle = $is_muscle
        """, parameters={
            'fma_id': fma_id,
            'name': name,
            'common_name': common_name,
            'is_muscle': is_muscle
        })

        # Add Muscle label if applicable
        if is_muscle:
            self.graph.execute_query("""
                MATCH (bp:BodyPart {fma_id: $fma_id})
                SET bp:Muscle
            """, parameters={'fma_id': fma_id})

        self.imported_fma_ids.add(fma_id)
        self.stats['body_parts'] += 1

    def _import_parents(self, onto, fma_term, max_depth=3, current_depth=0):
        """Import parent hierarchy (muscle → muscle group → region)"""

        if current_depth >= max_depth:
            return

        if not hasattr(fma_term, 'is_a'):
            return

        for parent_cls in fma_term.is_a:
            if not hasattr(parent_cls, 'name'):
                continue

            # Import parent term
            self._import_term(parent_cls)

            # Create IS_A relationship
            self.graph.execute_query("""
                MATCH (child:BodyPart {fma_id: $child_id})
                MATCH (parent:BodyPart {fma_id: $parent_id})
                MERGE (child)-[:IS_A]->(parent)
            """, parameters={
                'child_id': fma_term.name,
                'parent_id': parent_cls.name
            })

            self.stats['relationships'] += 1

            # Recursively import grandparents (with depth limit)
            self._import_parents(onto, parent_cls, max_depth, current_depth + 1)

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
            RETURN m.common_name as common_name, m.name as anatomical_name, m.fma_id as id
            ORDER BY m.common_name
            LIMIT 10
        """)

        print("  Sample imported muscles:")
        for r in result:
            print(f"    • {r['common_name']} → {r['anatomical_name']} ({r['id']})")

if __name__ == "__main__":
    print("Starting targeted FMA import...")
    print("Strategy: Data-driven import (only muscles used in exercises)")
    print("Goal: Lean graph with semantic reasoning, no bloat\n")

    importer = FMATargetedImporter()
    try:
        importer.import_targeted_fma()
    finally:
        importer.close()

    print(f"\n{'='*70}")
    print("✓ TARGETED FMA IMPORT COMPLETE")
    print(f"{'='*70}")
    print("\nResult: Lean anatomy graph with FMA IDs for scientific linking!\n")
