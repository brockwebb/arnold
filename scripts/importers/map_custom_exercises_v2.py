#!/usr/bin/env python3
"""
Map Custom Exercises V2 - Improved LLM Mapping
- More aggressive canonical matching (fewer "novel" exercises)
- Confidence scoring on all relationships
- Better fuzzy matching
- Links to MuscleGroups as well as individual Muscles
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

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

NUM_WORKERS = 6
MODEL = "gpt-4o-mini"


class CustomExerciseMapperV2:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.canonical_exercises = self._load_canonical_exercises()
        self.stats = {
            'total': 0,
            'mapped': 0,
            'failed': 0,
            'novel_exercises': 0,
            'variations': 0,
            'avg_confidence': 0.0
        }

    def close(self):
        self.graph.close()

    def _load_canonical_exercises(self):
        """Load canonical exercise names from BOTH sources (excluding quality losers)"""
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
            WHERE NOT EXISTS {
                MATCH (ex)-[:HIGHER_QUALITY_THAN]->()
            }
            OR NOT EXISTS {
                MATCH ()-[:HIGHER_QUALITY_THAN]->(ex)
            }
            RETURN DISTINCT ex.name as name, ex.id as id
            ORDER BY ex.name
        """)

        # For duplicates, prefer the winner
        # Get all exercises, then deduplicate by name preferring quality winners
        all_exercises = self.graph.execute_query("""
            MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
            OPTIONAL MATCH (winner:Exercise)-[:HIGHER_QUALITY_THAN]->(ex)
            WITH ex, winner
            WHERE winner IS NULL  // Only include exercises that didn't lose quality comparison
            RETURN DISTINCT ex.name as name, ex.id as id
            ORDER BY ex.name
        """)

        print(f"  Loaded {len(all_exercises)} unique canonical exercises from both sources")

        return all_exercises

    def map_custom_exercises_parallel(self, clear_existing=False):
        """Map all custom exercises using 6 parallel workers"""

        print(f"\n{'='*70}")
        print("CUSTOM EXERCISE MAPPING V2 (Improved)")
        print(f"{'='*70}\n")

        if clear_existing:
            print("Clearing existing mappings...")
            self.graph.execute_query("""
                MATCH (ex:Exercise)-[r:VARIATION_OF]->()
                WHERE NOT EXISTS {
                    MATCH (ex)-[:SOURCED_FROM]->(:ExerciseSource)
                }
                DELETE r
            """)
            self.graph.execute_query("""
                MATCH (ex:Exercise)-[r:TARGETS]->()
                WHERE NOT EXISTS {
                    MATCH (ex)-[:SOURCED_FROM]->(:ExerciseSource)
                }
                AND r.llm_inferred = true
                DELETE r
            """)
            self.graph.execute_query("""
                MATCH (ex:Exercise)
                WHERE NOT EXISTS {
                    MATCH (ex)-[:SOURCED_FROM]->(:ExerciseSource)
                }
                REMOVE ex.is_novel
            """)
            print("  ✓ Cleared existing LLM-generated mappings\n")

        # Get all custom exercises (those without SOURCED_FROM relationship)
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE NOT EXISTS {
                MATCH (ex)-[:SOURCED_FROM]->(:ExerciseSource)
            }
            RETURN ex.id as id, ex.name as name
        """)

        custom_exercises = [{"id": r["id"], "name": r["name"]} for r in result]
        self.stats['total'] = len(custom_exercises)

        print(f"Found {len(custom_exercises)} custom exercises to map")
        print(f"Using {NUM_WORKERS} parallel workers with {MODEL}")
        print(f"Improvements: Aggressive matching, confidence scoring, fuzzy search\n")

        # Process in parallel
        confidence_scores = []
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
                            if 'confidence' in result:
                                confidence_scores.append(result['confidence'])
                        else:
                            self.stats['failed'] += 1
                    except Exception as e:
                        print(f"\n  ❌ Error processing {ex['name']}: {e}")
                        self.stats['failed'] += 1

                    pbar.update(1)

        # Calculate average confidence
        if confidence_scores:
            self.stats['avg_confidence'] = sum(confidence_scores) / len(confidence_scores)

        print(f"\n{'='*70}")
        print("MAPPING COMPLETE")
        print(f"{'='*70}\n")

        print(f"  Total custom exercises: {self.stats['total']}")
        print(f"  ✓ Successfully mapped: {self.stats['mapped']}")
        print(f"  ✓ Variations linked: {self.stats['variations']}")
        print(f"  ✓ Novel exercises: {self.stats['novel_exercises']}")
        print(f"  ✓ Average confidence: {self.stats['avg_confidence']:.2f}")
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
                confidence = self._apply_mapping(exercise['id'], exercise['name'], mapping)
                return {'success': True, 'confidence': confidence}

            return None

        except Exception as e:
            raise Exception(f"Error processing {exercise['name']}: {e}")

    def _llm_map_exercise(self, exercise_name):
        """Use LLM to map exercise to canonical + infer muscles"""

        # Create full list of canonical exercises for better matching
        canonical_names = [ex['name'] for ex in self.canonical_exercises]

        prompt = f"""You are an exercise science expert. Map this custom exercise to a canonical form.

Custom Exercise: "{exercise_name}"

Available Canonical Exercises:
{chr(10).join(f"- {name}" for name in canonical_names[:100])}
... (and {len(canonical_names) - 100} more)

IMPORTANT: Be AGGRESSIVE about finding matches. Most custom exercises are just variations.
- Remove equipment mentions: "Bulgarian Split Squat (dumbbells)" → "Bulgarian Split Squat"
- Remove tempo/technique: "Slow Eccentric Pull-Up" → "Pull-Up"
- Remove load info: "67 tire flips" → "Tire Flip"
- Normalize names: "DB Bench" → "Dumbbell Bench Press"

Only use "CREATE_NEW" for truly unique movements not in the canonical list.

Provide JSON response:
{{
  "canonical_parent": "Pull-Up" | "CREATE_NEW" if truly novel,
  "confidence": 0.95,  // 0-1 how confident in this mapping
  "is_variation": true/false,
  "variation_type": "grip"|"equipment"|"load"|"stance"|"tempo"|"technique"|null,
  "primary_muscles": ["chest", "shoulders", "triceps"],  // Use common names
  "secondary_muscles": ["lats", "core"],
  "reasoning": "Brief explanation"
}}

Examples:
- "Bulgarian Split Squat (dumbbells)" → parent: "Bulgarian Split Squat", confidence: 0.95, variation: equipment
- "Wide-grip Pull-Up" → parent: "Pull-Up", confidence: 0.9, variation: grip
- "67 tire flips" → parent: "CREATE_NEW", confidence: 0.8 (if Tire Flip not in canonical list)

Respond ONLY with valid JSON."""

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2  # Lower temperature for more consistent matching
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
            # Silent failure, will be caught upstream
            return None

    def _fuzzy_find_canonical(self, name):
        """Fuzzy search for canonical exercise by name"""

        # First try exact match (case insensitive)
        for ex in self.canonical_exercises:
            if ex['name'].lower() == name.lower():
                return ex['id']

        # Try contains match
        for ex in self.canonical_exercises:
            if name.lower() in ex['name'].lower() or ex['name'].lower() in name.lower():
                return ex['id']

        # Try word overlap
        name_words = set(name.lower().split())
        for ex in self.canonical_exercises:
            ex_words = set(ex['name'].lower().split())
            if len(name_words & ex_words) >= 2:  # At least 2 words in common
                return ex['id']

        return None

    def _apply_mapping(self, custom_id, custom_name, mapping):
        """Apply LLM mapping to Neo4j"""

        canonical_parent = mapping.get("canonical_parent")
        is_variation = mapping.get("is_variation", False)
        confidence = mapping.get("confidence", 0.5)

        # Handle canonical parent with fuzzy matching
        if canonical_parent and canonical_parent != "CREATE_NEW":
            # Use fuzzy search to find canonical
            parent_id = self._fuzzy_find_canonical(canonical_parent)

            if parent_id and is_variation:
                # Create variation link (handle null variation_type)
                variation_type = mapping.get("variation_type") or "unspecified"

                self.graph.execute_query("""
                    MATCH (custom:Exercise {id: $custom_id})
                    MATCH (parent:Exercise {id: $parent_id})
                    MERGE (custom)-[:VARIATION_OF {
                        variation_type: $variation_type,
                        confidence: $confidence,
                        llm_inferred: true,
                        human_verified: false,
                        reasoning: $reasoning
                    }]->(parent)
                """, parameters={
                    'custom_id': custom_id,
                    'parent_id': parent_id,
                    'variation_type': variation_type,
                    'confidence': confidence,
                    'reasoning': mapping.get("reasoning", "")
                })

                self.stats['variations'] += 1

                # Inherit muscle targets from parent
                self.graph.execute_query("""
                    MATCH (custom:Exercise {id: $custom_id})
                    MATCH (parent:Exercise)-[pt:TARGETS]->(m)
                    MERGE (custom)-[ct:TARGETS]->(m)
                    SET ct.role = pt.role,
                        ct.inherited = true,
                        ct.confidence = $confidence,
                        ct.llm_inferred = true,
                        ct.human_verified = false
                """, parameters={
                    'custom_id': custom_id,
                    'confidence': confidence
                })

        elif canonical_parent == "CREATE_NEW":
            # Mark as novel exercise
            self.graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                SET ex.is_novel = true
            """, parameters={'ex_id': custom_id})

            self.stats['novel_exercises'] += 1

        # Add LLM-inferred muscles (map to both individual Muscles and MuscleGroups)
        for muscle_name in mapping.get("primary_muscles", []):
            self._link_to_muscle(custom_id, muscle_name, role="primary", confidence=confidence)

        for muscle_name in mapping.get("secondary_muscles", []):
            self._link_to_muscle(custom_id, muscle_name, role="secondary", confidence=confidence)

        return confidence

    def _link_to_muscle(self, exercise_id, muscle_name, role="primary", confidence=0.8):
        """Link exercise to muscle OR muscle group via fuzzy match"""

        normalized = muscle_name.lower().strip()

        # Try to link to Muscle first
        result = self.graph.execute_query("""
            MATCH (m:Muscle)
            WHERE toLower(m.name) CONTAINS $muscle_name
               OR toLower(m.common_name) = $muscle_name
            RETURN m.fma_id as target_id, 'Muscle' as target_type
            LIMIT 1
        """, parameters={'muscle_name': normalized})

        # If no Muscle found, try MuscleGroup
        if not result:
            result = self.graph.execute_query("""
                MATCH (mg:MuscleGroup)
                WHERE toLower(mg.common_name) = $muscle_name
                   OR toLower(mg.name) CONTAINS $muscle_name
                RETURN mg.id as target_id, 'MuscleGroup' as target_type
                LIMIT 1
            """, parameters={'muscle_name': normalized})

        if not result:
            return False

        target = result[0]

        # Link to either Muscle or MuscleGroup
        if target['target_type'] == 'Muscle':
            self.graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (m:Muscle {fma_id: $target_id})
                MERGE (ex)-[t:TARGETS]->(m)
                SET t.role = $role,
                    t.llm_inferred = true,
                    t.confidence = $confidence,
                    t.human_verified = false
            """, parameters={
                'ex_id': exercise_id,
                'target_id': target['target_id'],
                'role': role,
                'confidence': confidence
            })
        else:  # MuscleGroup
            self.graph.execute_query("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (mg:MuscleGroup {id: $target_id})
                MERGE (ex)-[t:TARGETS]->(mg)
                SET t.role = $role,
                    t.llm_inferred = true,
                    t.confidence = $confidence,
                    t.human_verified = false
            """, parameters={
                'ex_id': exercise_id,
                'target_id': target['target_id'],
                'role': role,
                'confidence': confidence
            })

        return True

    def _verify_mappings(self):
        """Verify mappings in database"""
        print("Verifying mappings...")

        # Count variations
        result = self.graph.execute_query("""
            MATCH ()-[r:VARIATION_OF]->()
            WHERE r.llm_inferred = true
            RETURN count(r) as count, avg(r.confidence) as avg_conf
        """)
        variations = result[0]['count']
        avg_conf = result[0]['avg_conf'] or 0.0

        # Count novel exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_novel = true)
            RETURN count(ex) as count
        """)
        novel = result[0]['count']

        # Count custom exercises with targets
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)
            WHERE NOT EXISTS {
                MATCH (custom)-[:SOURCED_FROM]->(:ExerciseSource)
            }
            AND EXISTS {
                MATCH (custom)-[:TARGETS]->()
            }
            RETURN count(custom) as count
        """)
        with_targets = result[0]['count']

        print(f"\n  Database verification:")
        print(f"    VARIATION_OF relationships: {variations}")
        print(f"    Average variation confidence: {avg_conf:.2f}")
        print(f"    Novel exercises: {novel}")
        print(f"    Custom exercises with muscle targets: {with_targets}\n")

        # Sample mappings
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)-[v:VARIATION_OF]->(parent:Exercise)
            WHERE NOT EXISTS {
                MATCH (custom)-[:SOURCED_FROM]->(:ExerciseSource)
            }
            RETURN custom.name as custom_name,
                   parent.name as canonical_name,
                   v.confidence as confidence
            ORDER BY v.confidence DESC
            LIMIT 10
        """)

        if result:
            print("  Sample variation mappings (highest confidence):")
            for r in result:
                print(f"    • {r['custom_name']} → {r['canonical_name']} (conf: {r['confidence']:.2f})")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Map custom exercises to canonical forms (V2)")
    parser.add_argument('--clear', action='store_true', help='Clear existing mappings before running')
    args = parser.parse_args()

    print("Starting exercise mapper V2...")
    print("Improvements: Aggressive matching, confidence scoring, fuzzy search")

    # Check for API key
    if not OPENAI_API_KEY:
        print("\n❌ ERROR: OPENAI_API_KEY not set in environment")
        print("Please set it in your .env file or environment")
        sys.exit(1)

    mapper = CustomExerciseMapperV2()
    try:
        mapper.map_custom_exercises_parallel(clear_existing=args.clear)
    finally:
        mapper.close()

    print(f"\n{'='*70}")
    print("✓ MAPPING COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
