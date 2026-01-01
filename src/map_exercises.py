#!/usr/bin/env python3
"""
Map exercises that need muscle assignments.
Called after workout logging when exercises have no muscle mappings.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from exercise_matcher import ExerciseMatcher
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")


def get_unmapped_exercises():
    """Get exercises that have no muscle group mappings."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (ex:Exercise)
            WHERE NOT (ex)-[:TARGETS]->(:MuscleGroup)
              AND NOT (ex)-[:EXACT_MATCH|VARIATION_OF|SIMILAR_TO]->(:Exercise)
              AND ex.source = 'user'
            RETURN ex.id as id, ex.name as name
            ORDER BY ex.created_at DESC
            LIMIT 20
        """)
        
        exercises = []
        for record in result:
            exercises.append({
                'id': record['id'],
                'name': record['name']
            })
    
    driver.close()
    return exercises


def map_exercises(exercise_ids: list = None, exercise_names: list = None):
    """
    Map exercises to canonical exercises and inherit muscle mappings.
    
    Args:
        exercise_ids: List of specific exercise IDs to map
        exercise_names: List of (name, id) tuples to map
    """
    
    if exercise_names:
        # Use provided exercise names
        exercises = [{'name': name, 'id': ex_id} for name, ex_id in exercise_names]
    elif exercise_ids:
        # Fetch from Neo4j by ID
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (ex:Exercise)
                WHERE ex.id IN $ids
                RETURN ex.id as id, ex.name as name
            """, ids=exercise_ids)
            exercises = [{'id': r['id'], 'name': r['name']} for r in result]
        driver.close()
    else:
        # Get all unmapped exercises
        exercises = get_unmapped_exercises()
    
    if not exercises:
        print("No exercises to map!")
        return []
    
    print(f"\n📋 Found {len(exercises)} exercises to map\n")
    
    # Match exercises
    matcher = ExerciseMatcher()
    try:
        results = matcher.batch_match_exercises(exercises)
        
        # Summary
        print("\n" + "=" * 80)
        print("MAPPING SUMMARY")
        print("=" * 80)
        
        matched = [r for r in results if r['matched']]
        unmatched = [r for r in results if not r['matched']]
        
        print(f"\n✅ Matched: {len(matched)}/{len(exercises)}")
        print(f"❌ Unmatched: {len(unmatched)}/{len(exercises)}")
        
        if matched:
            print("\n" + "-" * 80)
            print("MATCHED EXERCISES:")
            print("-" * 80)
            for r in matched:
                print(f"\n{r['user_exercise']}")
                print(f"  → {r['canonical_exercise']}")
                print(f"  → Relationship: {r['relationship_type']}")
                print(f"  → Confidence: {r['confidence']:.0%}")
                if r['muscle_groups_inherited']:
                    print(f"  → ✓ Muscle groups inherited")
        
        if unmatched:
            print("\n" + "-" * 80)
            print("UNMATCHED EXERCISES (need manual mapping):")
            print("-" * 80)
            for r in unmatched:
                print(f"  • {r['user_exercise']}")
        
        return results
        
    finally:
        matcher.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Map exercises to canonical exercises')
    parser.add_argument('--ids', nargs='+', help='Specific exercise IDs to map')
    parser.add_argument('--all', action='store_true', help='Map all unmapped exercises')
    
    args = parser.parse_args()
    
    if args.ids:
        map_exercises(exercise_ids=args.ids)
    else:
        map_exercises()
