#!/usr/bin/env python3
"""
Add Movement Pattern nodes and relationships to CYBERDYNE-CORE.

Creates Movement nodes and links them to:
- Exercises (via INVOLVES relationship)
- Joint actions
- Anatomical planes

Usage:
    python scripts/add_movement_patterns.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.biomechanics import (
    MovementPattern,
    AnatomicalPlane,
    JointAction,
    get_movement_patterns_for_exercise,
    get_joint_actions_for_movement,
    get_exercise_complexity_score
)


def create_movement_nodes(graph: ArnoldGraph) -> int:
    """Create Movement pattern nodes."""
    print("\nCreating Movement pattern nodes...")

    created = 0
    for pattern in MovementPattern:
        query = """
        MERGE (m:Movement {id: $id})
        SET m.name = $name,
            m.type = $type
        RETURN m.id as id
        """

        graph.execute_write(query, {
            'id': f"MOVEMENT:{pattern.name}",
            'name': pattern.value,
            'type': 'fundamental_pattern'
        })
        created += 1

    print(f"  ✓ Created {created} Movement nodes")
    return created


def create_joint_action_nodes(graph: ArnoldGraph) -> int:
    """Create JointAction nodes."""
    print("\nCreating JointAction nodes...")

    created = 0
    for action in JointAction:
        # Determine plane
        plane = None
        if action.value in ['flexion', 'extension', 'dorsiflexion', 'plantarflexion']:
            plane = AnatomicalPlane.SAGITTAL.value
        elif action.value in ['abduction', 'adduction', 'lateral_flexion', 'elevation', 'depression']:
            plane = AnatomicalPlane.FRONTAL.value
        elif 'rotation' in action.value or action.value in ['pronation', 'supination']:
            plane = AnatomicalPlane.TRANSVERSE.value

        query = """
        MERGE (ja:JointAction {id: $id})
        SET ja.name = $name,
            ja.plane = $plane
        RETURN ja.id as id
        """

        graph.execute_write(query, {
            'id': f"JOINT_ACTION:{action.name}",
            'name': action.value,
            'plane': plane
        })
        created += 1

    print(f"  ✓ Created {created} JointAction nodes")
    return created


def link_movements_to_joint_actions(graph: ArnoldGraph) -> int:
    """Link Movement patterns to JointActions."""
    print("\nLinking Movements to JointActions...")

    linked = 0
    for pattern in MovementPattern:
        joint_actions = get_joint_actions_for_movement(pattern)

        for joint, actions in joint_actions.items():
            for action in actions:
                query = """
                MATCH (m:Movement {id: $movement_id})
                MATCH (ja:JointAction {id: $action_id})
                MERGE (m)-[r:REQUIRES_ACTION {joint: $joint}]->(ja)
                RETURN count(r) as count
                """

                graph.execute_write(query, {
                    'movement_id': f"MOVEMENT:{pattern.name}",
                    'action_id': f"JOINT_ACTION:{action.name}",
                    'joint': joint
                })
                linked += 1

    print(f"  ✓ Created {linked} Movement->JointAction relationships")
    return linked


def link_exercises_to_movements(graph: ArnoldGraph) -> dict:
    """Link Exercises to Movement patterns."""
    print("\nLinking Exercises to Movement patterns...")

    # Get all exercises
    query = """
    MATCH (e:Exercise)
    RETURN e.id as id, e.name as name, e.equipment as equipment
    """

    exercises = graph.execute_query(query)

    stats = {
        'exercises_processed': 0,
        'exercises_linked': 0,
        'relationships_created': 0,
        'complexity_scores_added': 0
    }

    for ex in exercises:
        patterns = get_movement_patterns_for_exercise(ex['name'])

        if patterns:
            # Link to movement patterns
            for pattern in patterns:
                query = """
                MATCH (e:Exercise {id: $exercise_id})
                MATCH (m:Movement {id: $movement_id})
                MERGE (e)-[:INVOLVES]->(m)
                """

                graph.execute_write(query, {
                    'exercise_id': ex['id'],
                    'movement_id': f"MOVEMENT:{pattern.name}"
                })
                stats['relationships_created'] += 1

            stats['exercises_linked'] += 1

            # Calculate and add complexity score
            # Get muscle count
            muscle_query = """
            MATCH (e:Exercise {id: $exercise_id})-[:TARGETS]->(m:Muscle)
            RETURN count(m) as muscle_count
            """
            result = graph.execute_query(muscle_query, {'exercise_id': ex['id']})
            muscle_count = result[0]['muscle_count'] if result else 0

            complexity = get_exercise_complexity_score(
                patterns,
                ex.get('equipment', ''),
                muscle_count
            )

            # Add complexity to exercise
            query = """
            MATCH (e:Exercise {id: $exercise_id})
            SET e.complexity_score = $complexity
            """
            graph.execute_write(query, {
                'exercise_id': ex['id'],
                'complexity': complexity
            })
            stats['complexity_scores_added'] += 1

        stats['exercises_processed'] += 1

        if stats['exercises_processed'] % 100 == 0:
            print(f"    Processed {stats['exercises_processed']} exercises...")

    print(f"  ✓ Processed {stats['exercises_processed']} exercises")
    print(f"  ✓ Linked {stats['exercises_linked']} exercises to movements")
    print(f"  ✓ Created {stats['relationships_created']} relationships")
    print(f"  ✓ Added {stats['complexity_scores_added']} complexity scores")

    return stats


def verify_biomechanical_integrity(graph: ArnoldGraph):
    """Verify that biomechanical relationships make sense."""
    print("\nVerifying biomechanical integrity...")

    # Test 1: Squats should involve squat movement pattern
    query = """
    MATCH (e:Exercise)-[:INVOLVES]->(m:Movement {name: 'squat'})
    WHERE toLower(e.name) CONTAINS 'squat'
    RETURN count(e) as squat_count
    """
    result = graph.execute_query(query)
    squat_count = result[0]['squat_count'] if result else 0
    print(f"  ✓ {squat_count} squat exercises linked to squat movement")

    # Test 2: Pull-ups should involve pull pattern
    query = """
    MATCH (e:Exercise)-[:INVOLVES]->(m:Movement {name: 'pull'})
    WHERE toLower(e.name) CONTAINS 'pull'
    RETURN count(e) as pull_count
    """
    result = graph.execute_query(query)
    pull_count = result[0]['pull_count'] if result else 0
    print(f"  ✓ {pull_count} pull exercises linked to pull movement")

    # Test 3: Check movement to joint action links
    query = """
    MATCH (m:Movement)-[:REQUIRES_ACTION]->(ja:JointAction)
    RETURN m.name as movement, count(ja) as actions
    ORDER BY actions DESC
    LIMIT 5
    """
    results = graph.execute_query(query)
    print(f"\n  Movement patterns with most joint actions:")
    for r in results:
        print(f"    • {r['movement']}: {r['actions']} actions")


def main():
    print("=" * 60)
    print("Add Movement Patterns to CYBERDYNE-CORE")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Create nodes and relationships
    movement_count = create_movement_nodes(graph)
    action_count = create_joint_action_nodes(graph)
    movement_action_links = link_movements_to_joint_actions(graph)
    exercise_stats = link_exercises_to_movements(graph)

    # Verify
    verify_biomechanical_integrity(graph)

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Movement nodes created: {movement_count}")
    print(f"JointAction nodes created: {action_count}")
    print(f"Movement->JointAction links: {movement_action_links}")
    print(f"Exercises linked to movements: {exercise_stats['exercises_linked']}")
    print(f"Exercise->Movement links: {exercise_stats['relationships_created']}")
    print(f"Complexity scores added: {exercise_stats['complexity_scores_added']}")

    print("\n" + "=" * 60)
    print("✓ Biomechanical enhancement complete")
    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
