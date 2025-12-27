#!/usr/bin/env python3
"""
Simple Custom Exercise Mapper using GPT-5.2
Maps user exercises to best canonical match with MAPS_TO relationship
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

# CRITICAL: Use GPT-5.2 as Brock specified
MODEL = "gpt-5.2"
NUM_WORKERS = 6

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)


class SimpleCustomMapper:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.canonicals = self._load_canonicals()
        self.stats = {
            'total': 0,
            'mapped': 0,
            'failed': 0,
            'fedb_mapped': 0,
            'ffdb_mapped': 0,
            'confidences': [],
            'low_confidence': 0
        }

    def close(self):
        self.graph.close()

    def _load_canonicals(self):
        """Load all canonical exercise names from both sources"""
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
            OPTIONAL MATCH (winner:Exercise)-[:HIGHER_QUALITY_THAN]->(ex)
            WHERE winner IS NULL
            RETURN ex.id as id, ex.name as name, ex.source as source
            ORDER BY ex.name
        """)

        canonicals = [dict(r) for r in result]
        print(f"  Loaded {len(canonicals)} canonical exercises")
        return canonicals

    def _load_customs(self):
        """Load custom exercises (no SOURCED_FROM relationship)"""
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE NOT EXISTS {
                MATCH (ex)-[:SOURCED_FROM]->(:ExerciseSource)
            }
            RETURN ex.id as id, ex.name as name
            ORDER BY ex.name
        """)

        customs = [dict(r) for r in result]
        print(f"  Found {len(customs)} custom exercises to map\\n")
        return customs

    def _llm_find_match(self, custom_name):
        """Use GPT-5.2 to find best canonical match"""

        # Create abbreviated list for prompt (first 200)
        canonical_names = [c['name'] for c in self.canonicals]

        prompt = f"""You are an exercise science expert. Find the best canonical exercise match for this custom exercise.

Custom Exercise: "{custom_name}"

Available Canonical Exercises (showing first 200 of {len(canonical_names)}):
{chr(10).join(f"- {name}" for name in canonical_names[:200])}
... (and {len(canonical_names) - 200} more)

INSTRUCTIONS:
- Find the BEST match from the canonical list
- Ignore equipment variations: "DB Bench" matches "Dumbbell Bench Press"
- Ignore tempo/load: "Slow Pull-Up" matches "Pull-Up"
- Ignore stance/grip: "Wide Squat" matches "Squat"
- If NO reasonable match exists, return null for canonical_match

Return ONLY valid JSON:
{{
  "canonical_match": "Pull-Up" | null,
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}}

Examples:
- "Bulgarian Split Squat (dumbbells)" → "Bulgarian Split Squat", confidence: 0.95
- "Wide-grip Pull-Up" → "Pull-Up", confidence: 0.90
- "DB Bench" → "Dumbbell Bench Press", confidence: 0.85
- "Brock's Crazy Exercise" → null, confidence: 0.0
"""

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an exercise mapping expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_completion_tokens=300
            )

            content = response.choices[0].message.content.strip()

            # Remove markdown if present
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]

            result = json.loads(content.strip())
            return result

        except Exception as e:
            print(f"    ⚠️  LLM error for '{custom_name}': {e}")
            return None

    def _fuzzy_find_canonical_id(self, canonical_name):
        """Find canonical exercise ID by name (fuzzy)"""
        if not canonical_name:
            return None

        # Exact match (case insensitive)
        for c in self.canonicals:
            if c['name'].lower() == canonical_name.lower():
                return c['id'], c['source']

        # Contains match
        for c in self.canonicals:
            if canonical_name.lower() in c['name'].lower() or c['name'].lower() in canonical_name.lower():
                return c['id'], c['source']

        # Word overlap
        name_words = set(canonical_name.lower().split())
        for c in self.canonicals:
            c_words = set(c['name'].lower().split())
            if len(name_words & c_words) >= 2:
                return c['id'], c['source']

        return None, None

    def _map_one_custom(self, custom):
        """Map one custom exercise using GPT-5.2"""

        try:
            # Get LLM match
            match = self._llm_find_match(custom['name'])

            if not match or not match.get('canonical_match'):
                return None

            # Find canonical ID
            canonical_id, source = self._fuzzy_find_canonical_id(match['canonical_match'])

            if not canonical_id:
                return None

            confidence = match.get('confidence', 0.5)
            reasoning = match.get('reasoning', '')

            # Create MAPS_TO relationship
            self.graph.execute_query("""
                MATCH (custom:Exercise {id: $custom_id})
                MATCH (canonical:Exercise {id: $canonical_id})
                MERGE (custom)-[m:MAPS_TO]->(canonical)
                SET m.confidence = $confidence,
                    m.reasoning = $reasoning,
                    m.llm_model = $model,
                    m.mapped_at = datetime()
            """, parameters={
                'custom_id': custom['id'],
                'canonical_id': canonical_id,
                'confidence': confidence,
                'reasoning': reasoning,
                'model': MODEL
            })

            return {
                'success': True,
                'confidence': confidence,
                'source': source
            }

        except Exception as e:
            raise Exception(f"Error mapping {custom['name']}: {e}")

    def map_all_customs(self):
        """Map all custom exercises using parallel workers"""

        print(f"\\n{'='*70}")
        print("SIMPLE CUSTOM EXERCISE MAPPER (GPT-5.2)")
        print(f"{'='*70}\\n")

        customs = self._load_customs()
        self.stats['total'] = len(customs)

        print(f"Using {NUM_WORKERS} parallel workers with {MODEL}")
        print(f"Expected: ~600-700 mapped, avg confidence >0.85\\n")

        # Clear existing MAPS_TO relationships
        print("Clearing existing MAPS_TO relationships...")
        self.graph.execute_query("""
            MATCH ()-[m:MAPS_TO]->()
            DELETE m
        """)
        print("  ✓ Cleared\\n")

        # Process in parallel
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(self._map_one_custom, custom): custom
                for custom in customs
            }

            with tqdm(total=len(customs), desc="Mapping exercises") as pbar:
                for future in as_completed(futures):
                    custom = futures[future]
                    try:
                        result = future.result()
                        if result:
                            self.stats['mapped'] += 1
                            self.stats['confidences'].append(result['confidence'])

                            if result['confidence'] < 0.7:
                                self.stats['low_confidence'] += 1

                            if result['source'] == 'free-exercise-db':
                                self.stats['fedb_mapped'] += 1
                            else:
                                self.stats['ffdb_mapped'] += 1
                        else:
                            self.stats['failed'] += 1
                    except Exception as e:
                        print(f"\\n  ❌ Error: {e}")
                        self.stats['failed'] += 1

                    pbar.update(1)

        self._print_stats()

    def _print_stats(self):
        """Print final statistics"""

        print(f"\\n{'='*70}")
        print("MAPPING COMPLETE")
        print(f"{'='*70}\\n")

        print(f"  Total custom exercises: {self.stats['total']}")
        print(f"  ✓ Successfully mapped: {self.stats['mapped']}")
        print(f"  ✗ Failed to map: {self.stats['failed']}\\n")

        print(f"  Mapping by source:")
        print(f"    Free-Exercise-DB: {self.stats['fedb_mapped']}")
        print(f"    Functional-Fitness-DB: {self.stats['ffdb_mapped']}\\n")

        if self.stats['confidences']:
            avg_conf = sum(self.stats['confidences']) / len(self.stats['confidences'])
            min_conf = min(self.stats['confidences'])
            max_conf = max(self.stats['confidences'])

            print(f"  Confidence scores:")
            print(f"    Average: {avg_conf:.3f}")
            print(f"    Min: {min_conf:.3f}")
            print(f"    Max: {max_conf:.3f}")
            print(f"    Low confidence (<0.7): {self.stats['low_confidence']}\\n")

        # Sample mappings
        result = self.graph.execute_query("""
            MATCH (custom:Exercise)-[m:MAPS_TO]->(canonical:Exercise)
            RETURN custom.name as custom_name,
                   canonical.name as canonical_name,
                   canonical.source as source,
                   m.confidence as confidence
            ORDER BY m.confidence DESC
            LIMIT 10
        """)

        if result:
            print(f"  Sample mappings (highest confidence):")
            for r in result:
                print(f"    • {r['custom_name']} → {r['canonical_name']} ({r['source']}, conf: {r['confidence']:.2f})")


def main():
    print("Starting simple custom exercise mapper with GPT-5.2...")

    # Check for API key
    if not OPENAI_API_KEY:
        print("\\n❌ ERROR: OPENAI_API_KEY not set in environment")
        print("Please set it in your .env file or environment")
        sys.exit(1)

    mapper = SimpleCustomMapper()
    try:
        mapper.map_all_customs()
    finally:
        mapper.close()

    print(f"\\n{'='*70}")
    print("✓ SIMPLE MAPPING COMPLETE")
    print(f"{'='*70}\\n")


if __name__ == "__main__":
    main()
