#!/usr/bin/env python3
"""
Exercise Relationship Matcher
Uses LLM reasoning to match user exercises to canonical exercises and build knowledge graph.

Relationship types:
- EXACT_MATCH: Same exercise, different name (alias)
- VARIATION_OF: Modified version (incline/decline/tempo/pause)
- SIMILAR_TO: Similar movement pattern, different equipment/setup
- SUBSTITUTES_FOR: Can replace in programming
- TARGETS: Links to muscle groups
"""

import os
import json
from typing import List, Dict, Optional
from neo4j import GraphDatabase
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time

# Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NUM_WORKERS = 1  # Parallel workers for LLM calls
MODEL = "gpt-5-mini-2025-08-07"

class ExerciseMatcher:
    """Match user exercises to canonical exercises using LLM reasoning."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        
    def find_canonical_candidates(self, exercise_name: str, limit: int = 20) -> List[Dict]:
        """Find potential canonical exercise matches using fuzzy search."""
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # Search by name similarity using CONTAINS
            search_terms = exercise_name.lower().split()
            
            result = session.run("""
                MATCH (ex:Exercise)
                WHERE (ex.source IN ['FFDB', 'free-exercise-db'] OR ex.id STARTS WITH 'CANONICAL')
                  AND (
                    ANY(term IN $search_terms WHERE toLower(ex.name) CONTAINS term)
                    OR toLower(ex.name) CONTAINS $full_name
                  )
                OPTIONAL MATCH (ex)-[:TARGETS]->(mg:MuscleGroup)
                WITH ex, collect(DISTINCT mg.name) as muscle_groups
                RETURN ex.id as id,
                       ex.name as name,
                       ex.source as source,
                       muscle_groups
                LIMIT $limit
            """, search_terms=search_terms, full_name=exercise_name.lower(), limit=limit)
            
            candidates = []
            for record in result:
                candidates.append({
                    'id': record['id'],
                    'name': record['name'],
                    'source': record['source'],
                    'muscle_groups': record['muscle_groups']
                })
            
            return candidates
    
    def analyze_relationship(self, user_exercise: str, canonical_exercise: Dict) -> Dict:
        """Use LLM to determine relationship type and confidence."""
        
        prompt = f"""You are an exercise science expert analyzing exercise relationships.

USER EXERCISE: "{user_exercise}"
CANONICAL EXERCISE: "{canonical_exercise['name']}"
MUSCLE GROUPS: {', '.join(canonical_exercise['muscle_groups']) if canonical_exercise['muscle_groups'] else 'Unknown'}

Determine the relationship between these exercises. Respond ONLY with valid JSON:

{{
  "relationship_type": "EXACT_MATCH" | "VARIATION_OF" | "SIMILAR_TO" | "SUBSTITUTES_FOR" | "UNRELATED",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "inherit_muscles": true|false
}}

RELATIONSHIP TYPES:
- EXACT_MATCH: Same exercise, just different name/alias (e.g., "Bench Press" = "Barbell Bench Press")
- VARIATION_OF: Modified version (e.g., "Incline Bench Press" is variation of "Bench Press")
- SIMILAR_TO: Similar movement, different equipment (e.g., "Dumbbell Press" similar to "Barbell Press")
- SUBSTITUTES_FOR: Can replace in programming (e.g., "Push-up" substitutes "Bench Press")
- UNRELATED: Completely different exercises

RULES:
- inherit_muscles = true if relationship is EXACT_MATCH, VARIATION_OF, or high-confidence SIMILAR_TO
- confidence > 0.9 for EXACT_MATCH
- confidence > 0.7 for VARIATION_OF
- confidence > 0.6 for SIMILAR_TO or SUBSTITUTES_FOR

Respond with JSON only, no markdown."""

        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=128000
            )
            
            # Parse response
            content = response.choices[0].message.content.strip()
            # Remove markdown if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            analysis = json.loads(content)
            
            # Validate
            valid_types = ["EXACT_MATCH", "VARIATION_OF", "SIMILAR_TO", "SUBSTITUTES_FOR", "UNRELATED"]
            if analysis['relationship_type'] not in valid_types:
                analysis['relationship_type'] = "UNRELATED"
            
            return analysis
            
        except Exception as e:
            print(f"LLM analysis failed: {e}")
            return {
                'relationship_type': 'UNRELATED',
                'confidence': 0.0,
                'reasoning': f'Error: {str(e)}',
                'inherit_muscles': False
            }
    
    def create_relationship(self, user_exercise_id: str, canonical_exercise_id: str, 
                          relationship_type: str, confidence: float, reasoning: str,
                          inherit_muscles: bool = False) -> bool:
        """Create relationship in Neo4j knowledge graph."""
        
        if relationship_type == "UNRELATED" or confidence < 0.6:
            return False
        
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # Create relationship
            session.run(f"""
                MATCH (user:Exercise {{id: $user_id}})
                MATCH (canonical:Exercise {{id: $canonical_id}})
                MERGE (user)-[r:{relationship_type}]->(canonical)
                ON CREATE SET 
                    r.confidence = $confidence,
                    r.reasoning = $reasoning,
                    r.created_at = datetime()
            """,
                user_id=user_exercise_id,
                canonical_id=canonical_exercise_id,
                confidence=confidence,
                reasoning=reasoning
            )
            
            # Inherit muscle mappings if appropriate
            if inherit_muscles:
                session.run("""
                    MATCH (user:Exercise {id: $user_id})
                    MATCH (canonical:Exercise {id: $canonical_id})-[:TARGETS]->(mg:MuscleGroup)
                    MERGE (user)-[r:TARGETS]->(mg)
                    ON CREATE SET r.inherited_from = $canonical_id
                """,
                    user_id=user_exercise_id,
                    canonical_id=canonical_exercise_id
                )
            
            return True
    
    def match_exercise(self, user_exercise_name: str, user_exercise_id: str) -> Dict:
        """
        Complete matching workflow:
        1. Find canonical candidates
        2. Analyze with LLM
        3. Create relationships
        4. Return best match
        """
        
        print(f"\n🔍 Matching: {user_exercise_name}")
        
        # Find candidates
        candidates = self.find_canonical_candidates(user_exercise_name)
        
        if not candidates:
            print("  ❌ No canonical candidates found")
            return {
                'matched': False,
                'reason': 'No similar canonical exercises found'
            }
        
        print(f"  Found {len(candidates)} candidates:")
        for c in candidates[:3]:
            print(f"    - {c['name']}")
        
        # Analyze top candidates with LLM
        best_match = None
        best_confidence = 0.0
        
        for candidate in candidates[:5]:  # Check top 5
            analysis = self.analyze_relationship(user_exercise_name, candidate)
            
            print(f"\n  Analyzing: {candidate['name']}")
            print(f"    Type: {analysis['relationship_type']}")
            print(f"    Confidence: {analysis['confidence']:.2f}")
            print(f"    Reasoning: {analysis['reasoning']}")
            
            if analysis['confidence'] > best_confidence and analysis['relationship_type'] != 'UNRELATED':
                best_match = {
                    'candidate': candidate,
                    'analysis': analysis
                }
                best_confidence = analysis['confidence']
        
        # Create relationship for best match
        if best_match:
            success = self.create_relationship(
                user_exercise_id,
                best_match['candidate']['id'],
                best_match['analysis']['relationship_type'],
                best_match['analysis']['confidence'],
                best_match['analysis']['reasoning'],
                best_match['analysis']['inherit_muscles']
            )
            
            if success:
                print(f"\n  ✅ Created {best_match['analysis']['relationship_type']} relationship")
                print(f"     → {best_match['candidate']['name']}")
                if best_match['analysis']['inherit_muscles']:
                    print(f"     → Inherited muscle mappings")
                
                return {
                    'matched': True,
                    'canonical_exercise': best_match['candidate']['name'],
                    'canonical_id': best_match['candidate']['id'],
                    'relationship_type': best_match['analysis']['relationship_type'],
                    'confidence': best_match['analysis']['confidence'],
                    'muscle_groups_inherited': best_match['analysis']['inherit_muscles']
                }
        
        print("\n  ❌ No confident match found")
        return {
            'matched': False,
            'reason': 'No confident relationship found'
        }
    
    def batch_match_exercises(self, exercise_list: List[Dict]) -> List[Dict]:
        """Match multiple exercises in batch with parallel processing."""
        results = [None] * len(exercise_list)
        
        def match_with_index(idx, exercise):
            result = self.match_exercise(exercise['name'], exercise['id'])
            result['user_exercise'] = exercise['name']
            return idx, result
        
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(match_with_index, i, ex): i 
                for i, ex in enumerate(exercise_list)
            }
            
            for future in tqdm(as_completed(futures), total=len(exercise_list), desc="Matching exercises"):
                idx, result = future.result()
                results[idx] = result
                time.sleep(0.1)  # Rate limiting
        
        return results
    
    def close(self):
        """Close Neo4j connection."""
        self.driver.close()


def main():
    """Test with yesterday's workout exercises."""
    
    print("=" * 80)
    print("EXERCISE RELATIONSHIP MATCHER")
    print("Building Knowledge Graph Relationships")
    print("=" * 80)
    
    # Test exercises from yesterday's workout
    test_exercises = [
        {"name": "Light Boxing", "id": "test-1"},
        {"name": "Sandbag Shoulder (Alternating)", "id": "test-2"},
        {"name": "Seated Quad Extension", "id": "test-3"},
        {"name": "Bear Hug Carry", "id": "test-4"},
        {"name": "Turkish Get-Up", "id": "test-5"},
        {"name": "Hanging Knee to Chest Raise", "id": "test-6"},
        {"name": "Ab Wheel Rollout", "id": "test-7"}
    ]
    
    matcher = ExerciseMatcher()
    
    try:
        results = matcher.batch_match_exercises(test_exercises)
        
        # Summary
        print("\n" + "=" * 80)
        print("MATCHING SUMMARY")
        print("=" * 80)
        
        matched = sum(1 for r in results if r['matched'])
        print(f"\nMatched: {matched}/{len(test_exercises)}")
        
        for result in results:
            if result['matched']:
                print(f"\n✅ {result['user_exercise']}")
                print(f"   → {result['canonical_exercise']}")
                print(f"   → {result['relationship_type']} (confidence: {result['confidence']:.2f})")
                if result['muscle_groups_inherited']:
                    print(f"   → Muscle groups inherited")
            else:
                print(f"\n❌ {result['user_exercise']}")
                print(f"   → {result['reason']}")
    
    finally:
        matcher.close()


if __name__ == "__main__":
    main()
