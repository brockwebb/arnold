#!/usr/bin/env python3
"""
Parallel LLM-Powered Movement Pattern Classification

Classifies all unclassified exercises in Neo4j using OpenAI gpt-5-mini
with 6 parallel workers (ThreadPoolExecutor pattern).

Usage:
    python scripts/classify_all_exercises_parallel.py --test    # 20 exercises
    python scripts/classify_all_exercises_parallel.py --full    # All unclassified
    python scripts/classify_all_exercises_parallel.py --batch 100  # First 100
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from dotenv import load_dotenv
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.classify_movements import MovementClassifier

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

MAX_WORKERS = 6  # Parallel LLM calls
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


class ParallelExerciseClassifier:
    """
    Parallel exercise classification using ThreadPoolExecutor.
    """

    def __init__(self, graph: ArnoldGraph):
        self.graph = graph
        self.movement_taxonomy = self._load_taxonomy()
        self.stats = {
            'total': 0,
            'classified': 0,
            'high_confidence': 0,
            'medium_confidence': 0,
            'low_confidence': 0,
            'errors': []
        }

    def _load_taxonomy(self) -> List[Dict[str, str]]:
        """Load movement pattern taxonomy from Neo4j."""
        print("Loading movement taxonomy from Neo4j...")

        result = self.graph.execute_query("""
        MATCH (m:Movement)
        RETURN m.id as id, m.name as name, m.type as type, m.description as description
        ORDER BY m.name
        """)

        taxonomy = []
        for r in result:
            taxonomy.append({
                'id': r['id'],
                'name': r['name'],
                'type': r['type'],
                'description': r.get('description', 'Fundamental movement pattern')
            })

        print(f"  ✓ Loaded {len(taxonomy)} movement patterns")
        return taxonomy

    def get_unclassified_exercises(self, limit: int = None) -> List[Dict]:
        """Get all unclassified exercises from Neo4j."""
        print("\nGetting unclassified exercises...")

        query = """
        MATCH (e:Exercise)
        WHERE NOT (e)-[:INVOLVES]->(:Movement)
        RETURN e.id as id, e.name as name, e.category as category, e.equipment as equipment
        ORDER BY e.name
        """

        if limit:
            query += f" LIMIT {limit}"

        result = self.graph.execute_query(query)

        exercises = []
        for r in result:
            exercises.append({
                'id': r['id'],
                'name': r['name'],
                'category': r['category'] or 'unknown',
                'equipment': r['equipment']
            })

        print(f"  ✓ Found {len(exercises)} unclassified exercises")
        return exercises

    def classify_single_exercise(self, exercise: Dict) -> Dict[str, Any]:
        """
        Classify a single exercise (thread-safe).

        Each thread gets its own MovementClassifier instance.
        """
        classifier = MovementClassifier(api_key=os.getenv('OPENAI_API_KEY'))

        try:
            result = classifier.classify_exercise(
                exercise['name'],
                exercise['category'],
                exercise['equipment'],
                self.movement_taxonomy
            )

            # Add exercise ID for Neo4j linking
            result['exercise_id'] = exercise['id']

            return result

        except Exception as e:
            return {
                'exercise': exercise['name'],
                'exercise_id': exercise['id'],
                'movements': [],
                'reasoning': f"Classification failed: {str(e)}",
                'confidence': 0.0,
                'error': str(e)
            }

    def parallel_classify(self, exercises: List[Dict]) -> List[Dict[str, Any]]:
        """
        Classify exercises in parallel using ThreadPoolExecutor.
        """
        print(f"\n{'='*70}")
        print(f"PARALLEL CLASSIFICATION: {len(exercises)} exercises")
        print(f"Workers: {MAX_WORKERS}")
        print('='*70)

        results = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all classification tasks
            future_to_exercise = {
                executor.submit(self.classify_single_exercise, exercise): exercise
                for exercise in exercises
            }

            # Process results as they complete
            with tqdm(total=len(exercises), desc="Classifying") as pbar:
                for future in as_completed(future_to_exercise):
                    exercise = future_to_exercise[future]

                    try:
                        result = future.result()
                        results.append(result)

                        # Update stats
                        self.stats['classified'] += 1

                        if result['confidence'] >= 0.8:
                            self.stats['high_confidence'] += 1
                        elif result['confidence'] >= 0.5:
                            self.stats['medium_confidence'] += 1
                        else:
                            self.stats['low_confidence'] += 1

                    except Exception as e:
                        self.stats['errors'].append({
                            'exercise': exercise['name'],
                            'error': str(e)
                        })

                    pbar.update(1)

        return results

    def save_results(self, results: List[Dict], filename: str = "movement_classifications.json"):
        """Save classification results to JSON."""
        output_file = OUTPUT_DIR / filename

        with open(output_file, 'w') as f:
            json.dump(results, indent=2, fp=f)

        print(f"\n✓ Results saved to: {output_file}")
        return output_file

    def print_stats(self):
        """Print classification statistics."""
        print("\n" + "=" * 70)
        print("CLASSIFICATION STATISTICS")
        print("=" * 70)

        total = self.stats['classified']

        print(f"\nTotal classified: {total}")
        print(f"  ✓ High confidence (≥0.8): {self.stats['high_confidence']} ({100*self.stats['high_confidence']/total:.1f}%)")
        print(f"  ⚠ Medium confidence (0.5-0.8): {self.stats['medium_confidence']} ({100*self.stats['medium_confidence']/total:.1f}%)")
        print(f"  ⚠ Low confidence (<0.5): {self.stats['low_confidence']} ({100*self.stats['low_confidence']/total:.1f}%)")

        if self.stats['errors']:
            print(f"\n✗ Errors: {len(self.stats['errors'])}")
            for err in self.stats['errors'][:5]:
                print(f"  • {err['exercise']}: {err['error'][:80]}")

    def generate_report(self, results: List[Dict]):
        """Generate classification report."""
        from collections import Counter

        print("\n" + "=" * 70)
        print("MOVEMENT PATTERN DISTRIBUTION")
        print("=" * 70)

        # Count pattern usage
        all_patterns = []
        for r in results:
            all_patterns.extend(r['movements'])

        pattern_counts = Counter(all_patterns)

        print("\nPattern usage:")
        for pattern, count in pattern_counts.most_common():
            pct = 100 * count / len(results)
            print(f"  {pattern:<20} {count:>4} exercises ({pct:>5.1f}%)")

        # Confidence distribution
        print("\n" + "=" * 70)
        print("CONFIDENCE DISTRIBUTION")
        print("=" * 70)

        confidence_ranges = {
            '0.9-1.0': [r for r in results if 0.9 <= r['confidence'] <= 1.0],
            '0.8-0.9': [r for r in results if 0.8 <= r['confidence'] < 0.9],
            '0.7-0.8': [r for r in results if 0.7 <= r['confidence'] < 0.8],
            '0.5-0.7': [r for r in results if 0.5 <= r['confidence'] < 0.7],
            '<0.5': [r for r in results if r['confidence'] < 0.5]
        }

        for range_name, exercises in confidence_ranges.items():
            count = len(exercises)
            pct = 100 * count / len(results)
            print(f"  {range_name}: {count:>4} exercises ({pct:>5.1f}%)")

        # Flag low confidence for review
        if confidence_ranges['<0.5']:
            print("\n⚠️  LOW CONFIDENCE EXERCISES (require manual review):")
            for ex in confidence_ranges['<0.5'][:10]:
                print(f"  • {ex['exercise']}: {ex['confidence']:.2f} - {ex['movements']}")


def main():
    parser = argparse.ArgumentParser(description="Parallel LLM exercise classification")
    parser.add_argument('--test', action='store_true', help='Test on 20 exercises')
    parser.add_argument('--full', action='store_true', help='Classify all unclassified exercises')
    parser.add_argument('--batch', type=int, help='Classify first N exercises')
    parser.add_argument('--save-progress', action='store_true', help='Save progress every 100 exercises')

    args = parser.parse_args()

    # Determine batch size
    if args.test:
        limit = 20
        filename = "test_classifications.json"
    elif args.batch:
        limit = args.batch
        filename = f"classifications_batch_{args.batch}.json"
    elif args.full:
        limit = None
        filename = "movement_classifications_full.json"
    else:
        print("Error: Specify --test, --full, or --batch N")
        sys.exit(1)

    print("=" * 70)
    print("PARALLEL MOVEMENT PATTERN CLASSIFICATION")
    print("=" * 70)
    print(f"Workers: {MAX_WORKERS}")
    print(f"Model: OpenAI gpt-5-mini (MoE)")

    # Connect to graph
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        print("Error: Could not connect to Neo4j")
        sys.exit(1)

    print("  ✓ Connected")

    # Initialize classifier
    classifier = ParallelExerciseClassifier(graph)

    # Get exercises to classify
    exercises = classifier.get_unclassified_exercises(limit=limit)

    if not exercises:
        print("\n✓ No unclassified exercises found!")
        graph.close()
        return

    # Estimate time and cost
    est_time_mins = len(exercises) * 30 / 60 / MAX_WORKERS  # 30s per exercise, 6 workers
    est_cost = len(exercises) * 0.01  # Rough estimate: $0.01 per classification

    print(f"\nEstimated time: ~{est_time_mins:.0f} minutes")
    print(f"Estimated cost: ~${est_cost:.2f}")

    # Run parallel classification
    start_time = time.time()
    results = classifier.parallel_classify(exercises)
    elapsed_time = time.time() - start_time

    # Save results
    output_file = classifier.save_results(results, filename)

    # Print statistics
    classifier.print_stats()
    classifier.generate_report(results)

    # Performance metrics
    print("\n" + "=" * 70)
    print("PERFORMANCE METRICS")
    print("=" * 70)
    print(f"Total time: {elapsed_time/60:.1f} minutes")
    print(f"Exercises per minute: {len(exercises)/(elapsed_time/60):.1f}")
    print(f"Average time per exercise: {elapsed_time/len(exercises):.1f} seconds")
    print(f"Speedup vs sequential: ~{MAX_WORKERS}x")

    graph.close()

    print("\n" + "=" * 70)
    print("✓ CLASSIFICATION COMPLETE")
    print("=" * 70)
    print(f"\nNext steps:")
    print(f"1. Review results in: {output_file}")
    print(f"2. Validate low-confidence classifications")
    print(f"3. Write to Neo4j: python scripts/write_classifications_to_neo4j.py")


if __name__ == "__main__":
    main()
