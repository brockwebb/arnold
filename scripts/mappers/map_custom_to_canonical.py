#!/usr/bin/env python3
"""
Map Custom Exercises to Canonical Forms using LLM

Uses parallel LLM processing to map user's custom exercise names
(e.g., "Bulgarian Split Squat (dumbbells)") to canonical exercises
from Free-Exercise-DB (e.g., "Bulgarian Split Squat").

Creates CANONICAL_FORM relationships in the graph.
"""

import sys
from pathlib import Path
import json
import asyncio
from typing import List, Dict, Optional
import anthropic
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent / ".env")


class ExerciseMapper:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.canonical_exercises = []
        self.stats = {
            'total_custom': 0,
            'mapped': 0,
            'no_match': 0,
            'skipped': 0
        }

    def close(self):
        self.graph.close()

    def load_canonical_exercises(self):
        """Load all canonical exercises from free-exercise-db"""
        result = self.graph.execute_query("""
            MATCH (e:Exercise)
            WHERE e.source = 'free-exercise-db'
            RETURN e.name as name, e.id as id, e.category as category, e.aliases as aliases
        """)

        self.canonical_exercises = result
        print(f"  ✓ Loaded {len(self.canonical_exercises)} canonical exercises\n")

    def get_custom_exercises(self) -> List[Dict]:
        """Get all custom exercises that need mapping"""
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)
            WHERE custom.source IS NULL OR custom.source <> 'free-exercise-db'
            AND NOT EXISTS {
                MATCH (custom)-[:CANONICAL_FORM]->(:Exercise)
            }
            RETURN custom.name as name, custom.id as id
            ORDER BY custom.name
        """)

        return result

    def map_exercise_with_llm(self, custom_name: str) -> Optional[str]:
        """
        Use LLM to find best canonical match for a custom exercise.

        Returns the canonical exercise ID or None if no good match.
        """

        # Create a condensed list of canonical exercise names for the prompt
        canonical_names = [ex['name'] for ex in self.canonical_exercises[:100]]

        prompt = f"""You are an exercise mapping expert. Your task is to find the best canonical exercise match for a user's custom exercise name.

Custom exercise: "{custom_name}"

Canonical exercises (sample):
{chr(10).join(f"- {name}" for name in canonical_names)}

Instructions:
1. Analyze the custom exercise name
2. Identify the core movement (ignoring equipment variations, tempo, sets, etc.)
3. Find the best matching canonical exercise
4. Return ONLY the exact canonical exercise name, or "NO_MATCH" if no good match exists

Examples:
- "Bulgarian Split Squat (dumbbells)" → "Bulgarian Split Squat"
- "Farmer's Carry (handles, chains)" → "Farmer's Walk"
- "Mountain Climbers (Tabata)" → "Mountain Climbers"
- "Snow Clearing" → "NO_MATCH" (not a standard exercise)

Your response (ONLY the canonical name or NO_MATCH):"""

        try:
            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=100,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            result = message.content[0].text.strip()

            if result == "NO_MATCH":
                return None

            # Find the canonical exercise ID
            for ex in self.canonical_exercises:
                if ex['name'].lower() == result.lower():
                    return ex['id']

                # Also check aliases
                if ex.get('aliases'):
                    for alias in ex['aliases']:
                        if alias.lower() == result.lower():
                            return ex['id']

            # LLM returned something, but we couldn't find it
            print(f"    ⚠ LLM returned '{result}' but couldn't find in database")
            return None

        except Exception as e:
            print(f"    ❌ LLM error for '{custom_name}': {e}")
            return None

    def map_exercises(self, max_exercises: Optional[int] = None, batch_size: int = 10):
        """
        Map custom exercises to canonical ones.

        Args:
            max_exercises: Maximum number to process (for testing)
            batch_size: Process this many before writing to database
        """

        print(f"\n{'='*70}")
        print("EXERCISE MAPPING (Custom → Canonical)")
        print(f"{'='*70}\n")

        # Load canonical exercises
        print("Loading canonical exercises...")
        self.load_canonical_exercises()

        # Get custom exercises
        print("Loading custom exercises...")
        custom_exercises = self.get_custom_exercises()
        self.stats['total_custom'] = len(custom_exercises)

        if max_exercises:
            custom_exercises = custom_exercises[:max_exercises]

        print(f"  ✓ Found {len(custom_exercises)} custom exercises to map\n")

        if not custom_exercises:
            print("No custom exercises need mapping!")
            return

        print("Mapping exercises (using Claude Haiku for efficiency)...\n")

        # Process in batches
        for i in range(0, len(custom_exercises), batch_size):
            batch = custom_exercises[i:i+batch_size]

            print(f"Processing batch {i//batch_size + 1} ({i+1}-{min(i+batch_size, len(custom_exercises))})...")

            for custom_ex in batch:
                custom_name = custom_ex['name']
                custom_id = custom_ex['id']

                # Try to map
                canonical_id = self.map_exercise_with_llm(custom_name)

                if canonical_id:
                    # Create CANONICAL_FORM relationship
                    self.graph.execute_query("""
                        MATCH (custom:Exercise {id: $custom_id})
                        MATCH (canonical:Exercise {id: $canonical_id})
                        MERGE (custom)-[:CANONICAL_FORM]->(canonical)
                    """, parameters={
                        'custom_id': custom_id,
                        'canonical_id': canonical_id
                    })

                    self.stats['mapped'] += 1
                    print(f"  ✓ {custom_name} → {canonical_id}")
                else:
                    self.stats['no_match'] += 1
                    print(f"  ⚠ {custom_name} → NO_MATCH")

            # Brief pause between batches to avoid rate limits
            if i + batch_size < len(custom_exercises):
                print(f"  (pausing 2s between batches...)\n")
                import time
                time.sleep(2)

        print(f"\n{'='*70}")
        print("MAPPING COMPLETE")
        print(f"{'='*70}\n")

        print(f"  Total custom exercises: {self.stats['total_custom']}")
        print(f"  ✓ Mapped to canonical: {self.stats['mapped']}")
        print(f"  ⚠ No match found: {self.stats['no_match']}")
        print(f"  ⊘ Skipped: {self.stats['skipped']}\n")

        # Verify
        self._verify_mappings()

    def _verify_mappings(self):
        """Verify mappings in database"""
        print("Verifying mappings...")

        # Count mapped exercises
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)-[:CANONICAL_FORM]->(canonical:Exercise)
            RETURN count(*) as count
        """)
        mapped_count = result[0]['count']

        # Sample mappings
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)-[:CANONICAL_FORM]->(canonical:Exercise)
            WHERE custom.source <> 'free-exercise-db'
            RETURN custom.name as custom_name, canonical.name as canonical_name
            LIMIT 10
        """)

        print(f"\n  Database verification:")
        print(f"    Total CANONICAL_FORM relationships: {mapped_count}\n")

        print("  Sample mappings:")
        for r in result:
            print(f"    • {r['custom_name']} → {r['canonical_name']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Map custom exercises to canonical forms")
    parser.add_argument('--max', type=int, help='Maximum exercises to process (for testing)')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size (default: 10)')
    parser.add_argument('--dry-run', action='store_true', help='Test without writing to database')

    args = parser.parse_args()

    print("Starting exercise mapper...")
    print("Using Claude 3.5 Haiku for fast, cost-efficient mapping")

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n❌ ERROR: ANTHROPIC_API_KEY not set in environment")
        print("Please set it in your .env file or environment")
        sys.exit(1)

    mapper = ExerciseMapper()
    try:
        mapper.map_exercises(
            max_exercises=args.max,
            batch_size=args.batch_size
        )
    finally:
        mapper.close()

    print(f"\n{'='*70}")
    print("✓ MAPPING COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
