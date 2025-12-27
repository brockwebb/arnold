#!/usr/bin/env python3
"""
Import UBERON anatomy ontology into Neo4j
Creates BodyPart nodes with hierarchical relationships
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pronto
from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent / ".env")

UBERON_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/uberon/uberon-basic.obo"


class UberonImporter:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.stats = {
            'body_parts': 0,
            'muscles': 0,
            'relationships': 0
        }

    def close(self):
        self.graph.close()

    def import_uberon(self):
        """Import UBERON ontology into Neo4j"""

        print(f"\n{'='*70}")
        print("UBERON ANATOMY ONTOLOGY IMPORT")
        print(f"{'='*70}\n")

        print(f"Loading UBERON ontology from: {UBERON_FILE}")
        ont = pronto.Ontology(UBERON_FILE)

        print(f"  ✓ Loaded {len(ont)} terms\n")

        print("Importing anatomical structures...")

        # Import all anatomical structures
        for i, term in enumerate(ont.terms()):
            if i % 1000 == 0:
                print(f"  Processing term {i}/{len(ont)}...")

            uberon_id = term.id
            name = term.name
            definition = str(term.definition) if hasattr(term, 'definition') and term.definition else None

            # Determine if this is a muscle
            is_muscle = self._is_muscle(term)

            # Create BodyPart node
            self.graph.execute_query("""
                MERGE (bp:BodyPart {uberon_id: $uberon_id})
                SET bp.name = $name,
                    bp.definition = $definition,
                    bp.is_muscle = $is_muscle
            """, uberon_id=uberon_id, name=name, definition=definition, is_muscle=is_muscle)

            self.stats['body_parts'] += 1

            # Add Muscle label if applicable
            if is_muscle:
                self.graph.execute_query("""
                    MATCH (bp:BodyPart {uberon_id: $uberon_id})
                    SET bp:Muscle
                """, uberon_id=uberon_id)
                self.stats['muscles'] += 1

            # Create hierarchical relationships (is_a)
            for parent in term.superclasses(distance=1, with_self=False):
                parent_id = parent.id
                self.graph.execute_query("""
                    MATCH (child:BodyPart {uberon_id: $child_id})
                    MATCH (parent:BodyPart {uberon_id: $parent_id})
                    MERGE (child)-[:IS_A]->(parent)
                """, child_id=uberon_id, parent_id=parent_id)
                self.stats['relationships'] += 1

        print(f"\n{'='*70}")
        print("IMPORT COMPLETE")
        print(f"{'='*70}\n")

        print(f"  ✓ Imported {self.stats['body_parts']} body parts")
        print(f"  ✓ Identified {self.stats['muscles']} muscles")
        print(f"  ✓ Created {self.stats['relationships']} hierarchical relationships\n")

        # Verify in database
        self._verify_import()

    def _is_muscle(self, term):
        """Determine if a UBERON term represents a muscle"""
        name = term.name.lower() if term.name else ""
        definition = str(term.definition).lower() if hasattr(term, 'definition') and term.definition else ""

        muscle_keywords = ['muscle', 'muscular', 'musculature']

        # Check name and definition
        return any(kw in name or kw in definition for kw in muscle_keywords)

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

        # Sample muscles
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            RETURN m.name as name
            LIMIT 10
        """)

        print("  Sample muscles:")
        for r in result:
            print(f"    • {r['name']}")


def main():
    print("Starting UBERON import...")

    importer = UberonImporter()
    try:
        importer.import_uberon()
    finally:
        importer.close()

    print("\n✓ UBERON import complete!\n")


if __name__ == "__main__":
    main()
