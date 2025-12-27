#!/usr/bin/env python3
"""
Create Graph Relationship Layer for Dual-Source Exercise Import

NO DATA DELETION - Only adds relationships:
- ExerciseSource nodes for provenance
- SOURCED_FROM relationships
- SAME_AS relationships (cross-source duplicates)
- HIGHER_QUALITY_THAN relationships (LLM quality assessment)
"""

import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

load_dotenv()

NUM_WORKERS = 6


class GraphRelationshipBuilder:
    def __init__(self):
        self.graph = ArnoldGraph()
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.stats = {
            'source_nodes': 0,
            'sourced_from': 0,
            'duplicates_found': 0,
            'same_as_created': 0,
            'higher_quality_created': 0
        }

    def close(self):
        self.graph.close()

    def create_source_nodes(self):
        """Create ExerciseSource nodes for provenance tracking"""

        print(f"\n{'='*70}")
        print("STEP 1: Create ExerciseSource Nodes")
        print(f"{'='*70}\n")

        sources = [
            {
                'id': 'SOURCE:free-exercise-db',
                'name': 'Free Exercise DB',
                'short_name': 'free-exercise-db',
                'license': 'CC0',
                'url': 'https://github.com/yuhonas/free-exercise-db',
                'description': 'Open source exercise database with good muscle mappings'
            },
            {
                'id': 'SOURCE:functional-fitness-db',
                'name': 'Functional Fitness Database',
                'short_name': 'functional-fitness-db',
                'version': '2.9',
                'description': 'Comprehensive fitness database with detailed muscle mappings'
            }
        ]

        for source in sources:
            self.graph.execute_query("""
                MERGE (s:ExerciseSource {id: $id})
                SET s.name = $name,
                    s.short_name = $short_name,
                    s.license = $license,
                    s.url = $url,
                    s.version = $version,
                    s.description = $description,
                    s.created_at = datetime()
            """, parameters={
                'id': source['id'],
                'name': source['name'],
                'short_name': source['short_name'],
                'license': source.get('license'),
                'url': source.get('url'),
                'version': source.get('version'),
                'description': source.get('description')
            })
            self.stats['source_nodes'] += 1
            print(f"  ✓ Created: {source['name']}")

    def link_exercises_to_sources(self):
        """Create SOURCED_FROM relationships"""

        print(f"\n{'='*70}")
        print("STEP 2: Link Exercises to Sources")
        print(f"{'='*70}\n")

        # Link Free-Exercise-DB exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE ex.is_canonical = true
              AND ex.source = 'free-exercise-db'
            MATCH (s:ExerciseSource {short_name: 'free-exercise-db'})
            MERGE (ex)-[r:SOURCED_FROM]->(s)
            SET r.imported_at = ex.imported_at
            RETURN count(r) as count
        """)

        fedb_count = result[0]['count']
        self.stats['sourced_from'] += fedb_count
        print(f"  ✓ Free-Exercise-DB: {fedb_count} SOURCED_FROM links")

        # Link Functional-Fitness-DB exercises
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE ex.is_canonical = true
              AND ex.source = 'functional-fitness-db'
            MATCH (s:ExerciseSource {short_name: 'functional-fitness-db'})
            MERGE (ex)-[r:SOURCED_FROM]->(s)
            SET r.imported_at = ex.imported_at
            RETURN count(r) as count
        """)

        ffdb_count = result[0]['count']
        self.stats['sourced_from'] += ffdb_count
        print(f"  ✓ Functional-Fitness-DB: {ffdb_count} SOURCED_FROM links")

        print(f"\n  Total SOURCED_FROM links: {self.stats['sourced_from']}")

    def find_cross_source_duplicates(self) -> List[Tuple[str, str, str, str]]:
        """Find exercises with exact name matches across sources"""

        print(f"\n{'='*70}")
        print("STEP 3: Find Cross-Source Duplicates")
        print(f"{'='*70}\n")

        result = self.graph.execute_query("""
            MATCH (ex1:Exercise)-[:SOURCED_FROM]->(:ExerciseSource {short_name: 'free-exercise-db'})
            MATCH (ex2:Exercise)-[:SOURCED_FROM]->(:ExerciseSource {short_name: 'functional-fitness-db'})
            WHERE toLower(ex1.name) = toLower(ex2.name)
            RETURN ex1.id as id1,
                   ex1.name as name1,
                   ex2.id as id2,
                   ex2.name as name2
            ORDER BY ex1.name
        """)

        duplicates = [(r['id1'], r['name1'], r['id2'], r['name2']) for r in result]
        self.stats['duplicates_found'] = len(duplicates)

        print(f"  ✓ Found {len(duplicates)} cross-source duplicates\n")

        if duplicates:
            print("  Sample duplicates:")
            for id1, name1, id2, name2 in duplicates[:5]:
                print(f"    • {name1}")

        return duplicates

    def _assess_quality_llm(self, ex1_data: Dict, ex2_data: Dict) -> Dict:
        """Use LLM to assess which exercise has higher quality data"""

        prompt = f"""Compare these two exercise entries and determine which has higher quality data.

Exercise 1 (Free-Exercise-DB):
Name: {ex1_data['name']}
Category: {ex1_data.get('category', 'N/A')}
Difficulty: {ex1_data.get('difficulty', 'N/A')}
Muscle Targets: {ex1_data.get('muscle_count', 0)} muscles
Has Equipment: {ex1_data.get('has_equipment', False)}

Exercise 2 (Functional-Fitness-DB):
Name: {ex2_data['name']}
Category: {ex2_data.get('category', 'N/A')}
Difficulty: {ex2_data.get('difficulty', 'N/A')}
Body Region: {ex2_data.get('body_region', 'N/A')}
Mechanics: {ex2_data.get('mechanics', 'N/A')}
Force Type: {ex2_data.get('force_type', 'N/A')}
Muscle Targets: {ex2_data.get('muscle_count', 0)} muscles
Has Equipment: {ex2_data.get('has_equipment', False)}

Assess quality based on:
1. Muscle target completeness (more is better)
2. Metadata richness (category, difficulty, mechanics, etc.)
3. Specificity of classifications

Return JSON only:
{{
    "winner": "ex1" or "ex2",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using available model
                messages=[
                    {"role": "system", "content": "You are an exercise database quality assessor. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=200
            )

            result_text = response.choices[0].message.content.strip()

            # Extract JSON if wrapped in markdown
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            return json.loads(result_text)

        except Exception as e:
            print(f"    ⚠️  LLM error: {e}")
            # Default to ex2 (Functional Fitness DB) as it has more metadata
            return {
                "winner": "ex2",
                "confidence": 0.5,
                "reasoning": "Default to FFDB due to LLM error"
            }

    def _process_duplicate_pair(self, duplicate: Tuple[str, str, str, str]) -> Dict:
        """Process a single duplicate pair with LLM assessment"""

        id1, name1, id2, name2 = duplicate

        # Get exercise data for both
        ex1_result = self.graph.execute_query("""
            MATCH (ex:Exercise {id: $id})
            OPTIONAL MATCH (ex)-[:TARGETS]->(m)
            OPTIONAL MATCH (ex)-[:REQUIRES_EQUIPMENT]->(eq)
            RETURN ex.name as name,
                   ex.category as category,
                   ex.difficulty as difficulty,
                   ex.body_region as body_region,
                   ex.mechanics as mechanics,
                   ex.force_type as force_type,
                   count(DISTINCT m) as muscle_count,
                   count(DISTINCT eq) > 0 as has_equipment
        """, parameters={'id': id1})

        ex2_result = self.graph.execute_query("""
            MATCH (ex:Exercise {id: $id})
            OPTIONAL MATCH (ex)-[:TARGETS]->(m)
            OPTIONAL MATCH (ex)-[:REQUIRES_EQUIPMENT]->(eq)
            RETURN ex.name as name,
                   ex.category as category,
                   ex.difficulty as difficulty,
                   ex.body_region as body_region,
                   ex.mechanics as mechanics,
                   ex.force_type as force_type,
                   count(DISTINCT m) as muscle_count,
                   count(DISTINCT eq) > 0 as has_equipment
        """, parameters={'id': id2})

        ex1_data = ex1_result[0] if ex1_result else {}
        ex2_data = ex2_result[0] if ex2_result else {}

        # LLM assessment
        assessment = self._assess_quality_llm(ex1_data, ex2_data)

        # Determine winner and loser
        if assessment['winner'] == 'ex1':
            winner_id, loser_id = id1, id2
        else:
            winner_id, loser_id = id2, id1

        return {
            'id1': id1,
            'id2': id2,
            'name': name1,
            'winner_id': winner_id,
            'loser_id': loser_id,
            'confidence': assessment['confidence'],
            'reasoning': assessment['reasoning']
        }

    def create_same_as_relationships(self, duplicates: List[Tuple[str, str, str, str]]):
        """Create SAME_AS and HIGHER_QUALITY_THAN relationships using LLM"""

        print(f"\n{'='*70}")
        print("STEP 4: Create Relationship Layer (LLM Assessment)")
        print(f"{'='*70}\n")

        if not duplicates:
            print("  ℹ️  No duplicates to process\n")
            return

        print(f"  Processing {len(duplicates)} duplicate pairs with {NUM_WORKERS} workers...\n")

        results = []

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(self._process_duplicate_pair, dup): dup
                for dup in duplicates
            }

            for future in tqdm(as_completed(futures), total=len(duplicates), desc="LLM Assessment"):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f"    ❌ Error processing duplicate: {e}")

        # Create relationships in batch
        print(f"\n  Creating relationships...")

        for result in tqdm(results, desc="Creating SAME_AS"):
            # Create bidirectional SAME_AS relationship
            self.graph.execute_query("""
                MATCH (ex1:Exercise {id: $id1})
                MATCH (ex2:Exercise {id: $id2})
                MERGE (ex1)-[r1:SAME_AS]->(ex2)
                MERGE (ex2)-[r2:SAME_AS]->(ex1)
                SET r1.confidence = $confidence,
                    r1.llm_assessed = true,
                    r1.assessed_at = datetime(),
                    r2.confidence = $confidence,
                    r2.llm_assessed = true,
                    r2.assessed_at = datetime()
            """, parameters={
                'id1': result['id1'],
                'id2': result['id2'],
                'confidence': result['confidence']
            })
            self.stats['same_as_created'] += 1

            # Create HIGHER_QUALITY_THAN relationship
            self.graph.execute_query("""
                MATCH (winner:Exercise {id: $winner_id})
                MATCH (loser:Exercise {id: $loser_id})
                MERGE (winner)-[r:HIGHER_QUALITY_THAN]->(loser)
                SET r.confidence = $confidence,
                    r.reasoning = $reasoning,
                    r.llm_assessed = true,
                    r.assessed_at = datetime()
            """, parameters={
                'winner_id': result['winner_id'],
                'loser_id': result['loser_id'],
                'confidence': result['confidence'],
                'reasoning': result['reasoning']
            })
            self.stats['higher_quality_created'] += 1

        print(f"\n  ✓ Created {self.stats['same_as_created']} SAME_AS relationships")
        print(f"  ✓ Created {self.stats['higher_quality_created']} HIGHER_QUALITY_THAN relationships")

    def print_final_stats(self):
        """Print final statistics"""

        print(f"\n{'='*70}")
        print("GRAPH RELATIONSHIP LAYER COMPLETE")
        print(f"{'='*70}\n")

        print("📊 Relationship Layer Stats:")
        print(f"  ExerciseSource nodes: {self.stats['source_nodes']}")
        print(f"  SOURCED_FROM links: {self.stats['sourced_from']}")
        print(f"  Cross-source duplicates: {self.stats['duplicates_found']}")
        print(f"  SAME_AS relationships: {self.stats['same_as_created']}")
        print(f"  HIGHER_QUALITY_THAN relationships: {self.stats['higher_quality_created']}\n")

        # Query final counts
        result = self.graph.execute_query("""
            MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
            WITH ex.source as source, count(ex) as count
            RETURN source, count
            ORDER BY source
        """)

        print("📚 Exercises by Source:")
        for r in result:
            print(f"  {r['source']:30s}: {r['count']:4d}")

        result = self.graph.execute_query("""
            MATCH (ex:Exercise)-[:SOURCED_FROM]->(:ExerciseSource)
            RETURN count(DISTINCT ex) as total
        """)
        print(f"  {'TOTAL':30s}: {result[0]['total']:4d}\n")

    def run(self):
        """Execute all steps"""

        print(f"\n{'='*70}")
        print("DUAL-SOURCE GRAPH RELATIONSHIP BUILDER")
        print(f"{'='*70}\n")
        print("📌 No data deletion - only adding relationship layer\n")

        self.create_source_nodes()
        self.link_exercises_to_sources()
        duplicates = self.find_cross_source_duplicates()
        self.create_same_as_relationships(duplicates)
        self.print_final_stats()


if __name__ == "__main__":
    builder = GraphRelationshipBuilder()
    try:
        builder.run()
    finally:
        builder.close()

    print(f"{'='*70}")
    print("✓ GRAPH RELATIONSHIP LAYER COMPLETE")
    print(f"{'='*70}\n")
