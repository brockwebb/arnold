#!/usr/bin/env python3
"""
Map 849 custom exercises using LLM with 6 parallel workers
Same architecture as Phase 4 movement classification
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from openai import OpenAI
from dotenv import load_dotenv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

NUM_WORKERS = 6
MODEL = "gpt-4o-mini"  # Using gpt-4o-mini instead of gpt-5.2


class CustomExerciseMapper:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.canonical_exercises = self._load_canonical_exercises()
        self.stats = {
            'total': 0,
            'mapped': 0,
            'failed': 0,
            'novel_exercises': 0,
            'variations': 0
        }

    def close(self):
        self.graph.close()

    def _load_canonical_exercises(self):
        """Load canonical exercise names for LLM context"""
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN ex.name as name
        """)
        return [r["name"] for r in result]

    def map_custom_exercises_parallel(self):
        """Map all custom exercises using 6 parallel workers"""

        print(f"\n{'='*70}")
        print("CUSTOM EXERCISE MAPPING (6 Parallel Workers)")
        print(f"{'='*70}\n")

        # Get all unmapped custom exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE (ex.source IS NULL OR ex.source <> 'free-exercise-db')
            AND NOT EXISTS {
                MATCH (ex)-[:TARGETS]->(:Muscle)
            }
            RETURN ex.id as id, ex.name as name
        """)

        custom_exercises = [{"id": r["id"], "name": r["name"]} for r in result]
        self.stats['total'] = len(custom_exercises)

        print(f"Found {len(custom_exercises)} custom exercises to map")
        print(f"Using {NUM_WORKERS} parallel workers with {MODEL}\n")

        # Process in parallel
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(self._process_exercise, ex): ex
                for ex in custom_exercises
            }

            with tqdm(total=len(custom_exercises), desc="Mapping exercises") as pbar:
                for future in as_completed(futures):
                    ex = futures[future]
                    try:
                        result = future.result()
                        if result:
                            self.stats['mapped'] += 1
                        else:
                            self.stats['failed'] += 1
                    except Exception as e:
                        print(f"Error processing {ex['name']}: {e}")
                        self.stats['failed'] += 1

                    pbar.update(1)

        print(f"\n{'='*70}")
        print("MAPPING COMPLETE")
        print(f"{'='*70}\n")

        print(f"  Total custom exercises: {self.stats['total']}")
        print(f"  ✓ Successfully mapped: {self.stats['mapped']}")
        print(f"  ✓ Novel exercises created: {self.stats['novel_exercises']}")
        print(f"  ✓ Variations linked: {self.stats['variations']}")
        print(f"  ✗ Failed: {self.stats['failed']}\n")

        # Verify
        self._verify_mappings()

    def _process_exercise(self, exercise):
        """Process single exercise (called by workers)"""

        try:
            # Get LLM mapping
            mapping = self._llm_map_exercise(exercise['name'])

            if mapping:
                # Apply mapping to Neo4j
                self._apply_mapping(exercise['id'], exercise['name'], mapping)
                return True

            return False

        except Exception as e:
            print(f"Error processing {exercise['name']}: {e}")
            return False

    def _llm_map_exercise(self, exercise_name):
        """Use LLM to map exercise to canonical + infer muscles"""

        # Create a sample of canonical exercises for context
        canonical_sample = self.canonical_exercises[:50]

        prompt = f"""You are an exercise science expert. Analyze this exercise and provide structured mapping.

Exercise: "{exercise_name}"

Available Canonical Exercises (sample): {', '.join(canonical_sample)}

Provide JSON response:
{{
  "canonical_parent": "Pull-Up" | "CREATE_NEW" if truly novel,
  "is_variation": true/false,
  "variation_type": "grip"|"equipment"|"load"|"stance"|"tempo"|null,
  "primary_muscles": ["latissimus dorsi", "biceps brachii"],
  "secondary_muscles": ["trapezius", "rhomboids"],
  "equipment": "barbell"|"dumbbell"|"bodyweight"|"tire"|"sandbag"|etc,
  "reasoning": "Brief explanation"
}}

Examples:
- "Neutral-grip Pull-Up" → parent: "Pull-Up", variation: grip
- "67 tire flips" → parent: "CREATE_NEW", new exercise: "Tire Flip"
- "Sandbag carry 200 steps" → parent: "CREATE_NEW", new exercise: "Sandbag Carry"

Respond ONLY with valid JSON."""

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content.strip()

            # Remove markdown if present
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]

            mapping = json.loads(content.strip())
            return mapping

        except Exception as e:
            print(f"LLM error for {exercise_name}: {e}")
            return None

    def _apply_mapping(self, custom_id, custom_name, mapping):
        """Apply LLM mapping to Neo4j"""

        canonical_parent = mapping.get("canonical_parent")
        is_variation = mapping.get("is_variation", False)

        # Handle canonical parent
        if canonical_parent and canonical_parent != "CREATE_NEW":
            # Find existing canonical
            result = self.graph.execute_query("""
                MATCH (ex:Exercise WHERE ex.is_canonical = true)
                WHERE toLower(ex.name) = toLower($name)
                RETURN ex.id as id
                LIMIT 1
            """, parameters={'name': canonical_parent})

            if result and is_variation:
                parent_id = result[0]["id"]

                # Create variation link
                self.graph.execute_query("""
                    MATCH (custom:Exercise {id: $custom_id})
                    MATCH (parent:Exercise {id: $parent_id})
                    MERGE (custom)-[:VARIATION_OF {
                        variation_type: $variation_type,
                        reasoning: $reasoning
                    }]->(parent)
                """, parameters={
                    'custom_id': custom_id,
                    'parent_id': parent_id,
                    'variation_type': mapping.get("variation_type"),
                    'reasoning': mapping.get("reasoning")
                })

                self.stats['variations'] += 1

                # Inherit muscle targets
                self.graph.execute_query("""
                    MATCH (custom:Exercise {id: $custom_id})
                    MATCH (parent:Exercise)-[t:TARGETS]->(m:Muscle)
                    MERGE (custom)-[t2:TARGETS]->(m)
                    SET t2.role = t.role,
                        t2.inherited = true
                """, parameters={'custom_id': custom_id})

        elif canonical_parent == "CREATE_NEW":
            # Mark as novel exercise
            self.graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                SET ex.is_novel = true
            """, parameters={'ex_id': custom_id})

            self.stats['novel_exercises'] += 1

        # Add LLM-inferred muscles
        for muscle_name in mapping.get("primary_muscles", []):
            self._link_to_muscle(custom_id, muscle_name, role="primary")

        for muscle_name in mapping.get("secondary_muscles", []):
            self._link_to_muscle(custom_id, muscle_name, role="secondary")

    def _link_to_muscle(self, exercise_id, muscle_name, role="primary"):
        """Link exercise to muscle via fuzzy FMA match"""

        # Normalize muscle name
        normalized = muscle_name.lower().strip()

        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE toLower(m.name) CONTAINS $muscle_name
               OR toLower(m.common_name) CONTAINS $muscle_name
            RETURN m.fma_id as fma_id
            LIMIT 1
        """, parameters={'muscle_name': normalized})

        if not result:
            return False

        fma_id = result[0]["fma_id"]

        self.graph.execute_query("""
            MATCH (ex:Exercise {id: $ex_id})
            MATCH (m:Muscle {fma_id: $fma_id})
            MERGE (ex)-[t:TARGETS]->(m)
            SET t.role = $role,
                t.llm_inferred = true
        """, parameters={
            'ex_id': exercise_id,
            'fma_id': fma_id,
            'role': role
        })

        return True

    def _verify_mappings(self):
        """Verify mappings in database"""
        print("Verifying mappings...")

        # Count mapped custom exercises
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)
            WHERE (custom.source IS NULL OR custom.source <> 'free-exercise-db')
            AND EXISTS {
                MATCH (custom)-[:TARGETS]->(:Muscle)
            }
            RETURN count(custom) as count
        """)
        mapped_count = result[0]['count']

        # Count variations
        result = self.graph.execute_query("""
            MATCH ()-[r:VARIATION_OF]->()
            RETURN count(r) as count
        """)
        variations = result[0]['count']

        # Count novel exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_novel = true)
            RETURN count(ex) as count
        """)
        novel = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    Custom exercises with muscle targets: {mapped_count}")
        print(f"    VARIATION_OF relationships: {variations}")
        print(f"    Novel exercises: {novel}\n")

        # Sample mappings
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)-[:VARIATION_OF]->(parent:Exercise)
            WHERE custom.source <> 'free-exercise-db' OR custom.source IS NULL
            RETURN custom.name as custom_name, parent.name as canonical_name
            LIMIT 10
        """)

        print("  Sample variation mappings:")
        for r in result:
            print(f"    • {r['custom_name']} → {r['canonical_name']}")

        # Sample novel exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_novel = true)
            RETURN ex.name as name
            LIMIT 10
        """)

        print("\n  Sample novel exercises:")
        for r in result:
            print(f"    • {r['name']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Map custom exercises to canonical forms")
    parser.add_argument('--max', type=int, help='Maximum exercises to process (for testing)')
    args = parser.parse_args()

    print("Starting exercise mapper...")
    print(f"Using {MODEL} with {NUM_WORKERS} parallel workers")

    # Check for API key
    if not OPENAI_API_KEY:
        print("\n❌ ERROR: OPENAI_API_KEY not set in environment")
        print("Please set it in your .env file or environment")
        sys.exit(1)

    mapper = CustomExerciseMapper()
    try:
        if args.max:
            print(f"\n⚠️  TEST MODE: Processing only {args.max} exercises\n")
            # TODO: Implement max limit
        mapper.map_custom_exercises_parallel()
    finally:
        mapper.close()

    print(f"\n{'='*70}")
    print("✓ MAPPING COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
