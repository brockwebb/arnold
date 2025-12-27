#!/usr/bin/env python3
"""
Write Movement Pattern Classifications to Neo4j

Reads LLM-generated movement pattern classifications and creates
(:Exercise)-[:INVOLVES]->(:Movement) relationships in Neo4j.

Usage:
    python scripts/write_classifications_to_neo4j.py <classifications_file.json>
    python scripts/write_classifications_to_neo4j.py data/movement_classifications_full.json
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")


class ClassificationWriter:
    """
    Write LLM classifications to Neo4j graph.
    """

    def __init__(self, graph: ArnoldGraph):
        self.graph = graph
        self.stats = {
            'total_exercises': 0,
            'exercises_with_patterns': 0,
            'total_relationships': 0,
            'skipped_existing': 0,
            'skipped_no_patterns': 0,
            'high_confidence': 0,
            'medium_confidence': 0,
            'low_confidence': 0
        }

    def write_classifications(
        self,
        classifications: List[Dict[str, Any]],
        overwrite: bool = False,
        min_confidence: float = 0.0,
        verbose: bool = False
    ):
        """
        Write classifications to Neo4j.

        Args:
            classifications: List of classification dicts
            overwrite: If True, overwrite existing classifications
            min_confidence: Minimum confidence threshold (0.0-1.0)
            verbose: If True, print detailed progress
        """
        self.stats['total_exercises'] = len(classifications)
        self.verbose = verbose

        print(f"\n{'='*70}")
        print(f"WRITING CLASSIFICATIONS TO NEO4J")
        print(f"{'='*70}")
        print(f"Total classifications: {len(classifications)}")
        print(f"Min confidence threshold: {min_confidence}")
        print(f"Overwrite existing: {overwrite}")
        print()

        for i, classification in enumerate(classifications):
            if verbose and i < 5:  # Show first 5 in verbose mode
                print(f"\n[{i+1}] Processing: {classification.get('exercise')}")

            self._write_single_classification(
                classification,
                overwrite=overwrite,
                min_confidence=min_confidence
            )

            if verbose and i == 4:
                print(f"\n... (continuing with remaining {len(classifications)-5} exercises)")

        self._print_summary()

    def _write_single_classification(
        self,
        classification: Dict[str, Any],
        overwrite: bool,
        min_confidence: float
    ):
        """Write a single exercise classification."""
        exercise_name = classification.get('exercise')
        movements = classification.get('movements', [])
        confidence = classification.get('confidence', 0.0)
        reasoning = classification.get('reasoning', '')

        # Skip if no exercise name
        if not exercise_name:
            print(f"⚠️  Skipping: No exercise name")
            self.stats['skipped_no_patterns'] += 1
            return

        # Skip if no movements
        if not movements:
            self.stats['skipped_no_patterns'] += 1
            return

        # Skip if below confidence threshold
        if confidence < min_confidence:
            print(f"⚠️  Skipping {exercise_name}: confidence {confidence:.2f} < {min_confidence:.2f}")
            self.stats['skipped_no_patterns'] += 1
            return

        # Check if exercise already has classifications
        if not overwrite:
            existing_count = self.graph.execute_query("""
            MATCH (e:Exercise {name: $exercise_name})-[:INVOLVES]->(:Movement)
            RETURN count(*) as count
            """, parameters={'exercise_name': exercise_name})[0]['count']

            if existing_count > 0:
                self.stats['skipped_existing'] += 1
                return

        # Track confidence stats
        if confidence >= 0.8:
            self.stats['high_confidence'] += 1
        elif confidence >= 0.5:
            self.stats['medium_confidence'] += 1
        else:
            self.stats['low_confidence'] += 1

        # Write relationships
        relationships_created = 0

        for movement_name in movements:
            # Convert movement name to lowercase to match Neo4j nodes
            movement_name_lower = movement_name.lower()

            # First check if exercise exists
            ex_check = self.graph.execute_query("""
            MATCH (e:Exercise {name: $exercise_name})
            RETURN count(e) as count
            """, parameters={'exercise_name': exercise_name})

            if not ex_check or ex_check[0]['count'] == 0:
                if self.verbose:
                    print(f"    ⚠️  Exercise not found: {exercise_name}")
                continue  # Exercise not found, skip

            # Create INVOLVES relationship
            result = self.graph.execute_query("""
            MATCH (e:Exercise {name: $exercise_name})
            MATCH (m:Movement {name: $movement_name})
            MERGE (e)-[r:INVOLVES]->(m)
            SET r.confidence = $confidence,
                r.reasoning = $reasoning,
                r.source = 'llm_classification',
                r.model = 'gpt-5-mini',
                r.classified_at = datetime()
            RETURN e.name as exercise, m.name as movement
            """, parameters={
                'exercise_name': exercise_name,
                'movement_name': movement_name_lower,
                'confidence': confidence,
                'reasoning': reasoning
            })

            if result:
                relationships_created += 1
                if self.verbose:
                    print(f"    ✓ Created: {exercise_name} -> {movement_name}")
            else:
                if self.verbose:
                    print(f"    ⚠️  No result for: {exercise_name} -> {movement_name}")

        if relationships_created > 0:
            self.stats['exercises_with_patterns'] += 1
            self.stats['total_relationships'] += relationships_created

    def _print_summary(self):
        """Print writing summary."""
        print(f"\n{'='*70}")
        print("WRITE SUMMARY")
        print(f"{'='*70}")
        print(f"\nTotal classifications processed: {self.stats['total_exercises']}")
        print(f"  ✓ Exercises with patterns written: {self.stats['exercises_with_patterns']}")
        print(f"  ✓ Total relationships created: {self.stats['total_relationships']}")
        print(f"  ⊘ Skipped (existing classifications): {self.stats['skipped_existing']}")
        print(f"  ⊘ Skipped (no patterns/low confidence): {self.stats['skipped_no_patterns']}")

        print(f"\nConfidence breakdown (written exercises):")
        print(f"  ✓ High (≥0.8): {self.stats['high_confidence']}")
        print(f"  ⚠ Medium (0.5-0.8): {self.stats['medium_confidence']}")
        print(f"  ⚠ Low (<0.5): {self.stats['low_confidence']}")

        # Verify final coverage
        print(f"\n{'='*70}")
        print("FINAL DATABASE COVERAGE")
        print(f"{'='*70}")

        coverage = self.graph.execute_query("""
        MATCH (e:Exercise)
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        WITH e, count(m) as movement_count
        RETURN
            count(e) as total_exercises,
            sum(CASE WHEN movement_count > 0 THEN 1 ELSE 0 END) as classified,
            sum(CASE WHEN movement_count = 0 THEN 1 ELSE 0 END) as unclassified
        """)[0]

        total = coverage['total_exercises']
        classified = coverage['classified']
        unclassified = coverage['unclassified']
        pct = 100 * classified / total if total > 0 else 0

        print(f"\nTotal exercises in database: {total}")
        print(f"  ✓ Classified (have movement patterns): {classified} ({pct:.1f}%)")
        print(f"  ⚠ Unclassified (no movement patterns): {unclassified} ({100-pct:.1f}%)")

        if pct >= 90:
            print(f"\n🎉 **TARGET ACHIEVED:** {pct:.1f}% coverage (target was ≥90%)")
        else:
            print(f"\n⚠️  Target not yet met: {pct:.1f}% coverage (target is ≥90%)")


def main():
    parser = argparse.ArgumentParser(description="Write classifications to Neo4j")
    parser.add_argument('classification_file', help='Path to classification JSON file')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing classifications')
    parser.add_argument('--min-confidence', type=float, default=0.0, help='Minimum confidence threshold (default: 0.0)')
    parser.add_argument('--verbose', action='store_true', help='Show detailed progress')

    args = parser.parse_args()

    # Load classifications
    classification_file = Path(args.classification_file)
    if not classification_file.exists():
        print(f"Error: File not found: {classification_file}")
        sys.exit(1)

    print(f"Loading classifications from: {classification_file}")
    with open(classification_file) as f:
        classifications = json.load(f)

    print(f"  ✓ Loaded {len(classifications)} classifications")

    # Connect to Neo4j
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        print("Error: Could not connect to Neo4j")
        sys.exit(1)

    print("  ✓ Connected")

    # Write classifications
    writer = ClassificationWriter(graph)
    writer.write_classifications(
        classifications,
        overwrite=args.overwrite,
        min_confidence=args.min_confidence,
        verbose=args.verbose
    )

    graph.close()

    print(f"\n{'='*70}")
    print("✓ WRITE COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
