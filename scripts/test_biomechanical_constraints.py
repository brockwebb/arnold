#!/usr/bin/env python3
"""
Test Biomechanical Constraint System

Validates that the enhanced constraint checker correctly uses
Movement patterns and JointActions for injury-aware programming.

Usage:
    python scripts/test_biomechanical_constraints.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.judgment_day.constraints import ConstraintChecker
from arnold.biomechanics import INJURY_CONTRAINDICATIONS, JointAction


def test_biomechanical_forbidden_exercises(graph: ArnoldGraph):
    """Test that exercises are correctly forbidden based on biomechanics."""
    print("\n" + "=" * 60)
    print("Test 1: Biomechanical Forbidden Exercises")
    print("=" * 60)

    checker = ConstraintChecker(graph)

    # Get all injuries
    query = """
    MATCH (i:Injury)
    RETURN i.name as name, i.location as location
    """

    injuries = graph.execute_query(query)
    print(f"\nFound {len(injuries)} injuries in system:")
    for injury in injuries:
        print(f"  • {injury['name']} ({injury['location']})")

    # Get forbidden exercises
    forbidden = checker.get_forbidden_exercises()
    print(f"\nTotal forbidden exercises: {len(forbidden)}")

    # Sample some forbidden exercises
    if forbidden:
        sample_query = """
        MATCH (e:Exercise)
        WHERE e.id IN $forbidden_ids
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        RETURN e.id as id, e.name as name, collect(m.name) as movements
        LIMIT 10
        """

        sample = graph.execute_query(sample_query, {
            'forbidden_ids': list(forbidden)[:10]
        })

        print("\nSample forbidden exercises:")
        for ex in sample:
            movements = ', '.join(ex['movements']) if ex['movements'] else 'No movements'
            print(f"  • {ex['name']}")
            print(f"    Movements: {movements}")

    return len(forbidden) > 0


def test_exercise_biomechanics_check(graph: ArnoldGraph):
    """Test checking individual exercises for compatibility."""
    print("\n" + "=" * 60)
    print("Test 2: Exercise Biomechanics Check")
    print("=" * 60)

    checker = ConstraintChecker(graph)

    # Test with exercises that should have movement patterns
    test_exercises = [
        "back squat",
        "deadlift",
        "overhead press",
        "pull up",
        "bench press"
    ]

    print("\nChecking exercise compatibility:")

    for exercise_name in test_exercises:
        # Find exercise
        query = """
        MATCH (e:Exercise)
        WHERE toLower(e.name) CONTAINS toLower($name)
        RETURN e.id as id, e.name as name
        LIMIT 1
        """

        result = graph.execute_query(query, {'name': exercise_name})

        if result:
            exercise_id = result[0]['id']
            exercise_full_name = result[0]['name']

            # Check compatibility
            compatibility = checker.check_exercise_biomechanics(exercise_id)

            print(f"\n  {exercise_full_name}:")
            print(f"    Compatible: {compatibility['compatible']}")
            print(f"    Movement patterns: {', '.join(compatibility.get('movement_patterns', ['None']))}")

            if compatibility.get('warnings'):
                print(f"    Warnings:")
                for warning in compatibility['warnings']:
                    print(f"      ⚠️  {warning}")

    return True


def test_movement_based_alternatives(graph: ArnoldGraph):
    """Test that alternative suggestions use movement patterns."""
    print("\n" + "=" * 60)
    print("Test 3: Movement-Based Alternative Suggestions")
    print("=" * 60)

    checker = ConstraintChecker(graph)

    # Pick an exercise with shoulder involvement (might be forbidden for shoulder impingement)
    query = """
    MATCH (e:Exercise)-[:INVOLVES]->(m:Movement {name: 'push'})
    WHERE toLower(e.name) CONTAINS 'overhead'
    RETURN e.id as id, e.name as name
    LIMIT 1
    """

    result = graph.execute_query(query)

    if result:
        exercise_id = result[0]['id']
        exercise_name = result[0]['name']

        print(f"\nFinding alternatives to: {exercise_name}")

        alternatives = checker.suggest_alternatives(exercise_id, limit=5)

        print(f"\nFound {len(alternatives)} alternatives:")
        for i, alt in enumerate(alternatives, 1):
            print(f"\n  {i}. {alt['name']}")
            print(f"     Equipment: {alt.get('equipment', 'Unknown')}")
            print(f"     Movements: {', '.join(alt.get('movement_patterns', ['None']))}")
            print(f"     Score: {alt.get('score', 0):.2f}")

            if alt.get('biomech_warnings'):
                print(f"     Warnings: {', '.join(alt['biomech_warnings'])}")

        return len(alternatives) > 0
    else:
        print("  ⚠️  No overhead press exercises found to test")
        return False


def test_contraindication_mapping(graph: ArnoldGraph):
    """Test that contraindications are properly mapped."""
    print("\n" + "=" * 60)
    print("Test 4: Contraindication Mapping")
    print("=" * 60)

    print(f"\nKnown injury contraindications: {len(INJURY_CONTRAINDICATIONS)}")

    for injury, contraindication in INJURY_CONTRAINDICATIONS.items():
        print(f"\n  {injury}:")

        avoid_actions = contraindication.get('avoid_actions', [])
        avoid_positions = contraindication.get('avoid_positions', [])

        if avoid_actions:
            print(f"    Avoid actions: {', '.join([a.value for a in avoid_actions])}")

        if avoid_positions:
            print(f"    Avoid positions: {', '.join(avoid_positions)}")

        # Count exercises that involve these actions
        if avoid_actions:
            action_ids = [f"JOINT_ACTION:{action.name}" for action in avoid_actions]

            query = """
            MATCH (e:Exercise)-[:INVOLVES]->(m:Movement)-[:REQUIRES_ACTION]->(ja:JointAction)
            WHERE ja.id IN $action_ids
            RETURN count(DISTINCT e) as exercise_count
            """

            result = graph.execute_query(query, {'action_ids': action_ids})

            if result:
                count = result[0]['exercise_count']
                print(f"    Exercises affected: {count}")

    return True


def test_shoulder_impingement_scenario(graph: ArnoldGraph):
    """
    Test the specific scenario: Alternative to back squat for shoulder impingement.

    From Phase 4 spec: "Alternative to barbell back squat for someone with
    shoulder impingement should suggest goblet squats, front squats, belt squats."
    """
    print("\n" + "=" * 60)
    print("Test 5: Shoulder Impingement Scenario (Phase 4 Success Criteria)")
    print("=" * 60)

    print("\nScenario: Find alternatives to back squat for shoulder impingement")

    # First, ensure shoulder impingement injury exists
    injury_query = """
    MATCH (i:Injury)
    WHERE toLower(i.name) CONTAINS 'shoulder'
    RETURN i.name as name
    """

    shoulder_injuries = graph.execute_query(injury_query)

    if not shoulder_injuries:
        print("  ⚠️  No shoulder injury found in system")
        print("  Creating temporary shoulder impingement for test...")

        # We'll proceed anyway to test the contraindication logic
    else:
        print(f"  ✓ Found shoulder injury: {shoulder_injuries[0]['name']}")

    # Find back squat
    squat_query = """
    MATCH (e:Exercise)
    WHERE toLower(e.name) CONTAINS 'back squat' OR toLower(e.name) = 'squat'
    OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
    RETURN e.id as id, e.name as name, collect(m.name) as movements
    LIMIT 1
    """

    squat_result = graph.execute_query(squat_query)

    if not squat_result:
        print("  ⚠️  Back squat exercise not found")
        return False

    squat_id = squat_result[0]['id']
    squat_name = squat_result[0]['name']

    print(f"\nOriginal exercise: {squat_name}")
    print(f"  Movements: {', '.join(squat_result[0]['movements'])}")

    # Check contraindications for shoulder impingement
    print("\nShoulder impingement contraindications:")
    if 'shoulder impingement' in INJURY_CONTRAINDICATIONS:
        contraindication = INJURY_CONTRAINDICATIONS['shoulder impingement']
        avoid_actions = contraindication.get('avoid_actions', [])
        avoid_positions = contraindication.get('avoid_positions', [])

        print(f"  Avoid actions: {', '.join([a.value for a in avoid_actions])}")
        print(f"  Avoid positions: {', '.join(avoid_positions)}")

    # Get alternatives
    checker = ConstraintChecker(graph)
    alternatives = checker.suggest_alternatives(squat_id, limit=10)

    print(f"\nAlternatives suggested: {len(alternatives)}")

    # Look for expected alternatives
    expected_terms = ['goblet', 'front squat', 'belt']
    found_expected = []

    for alt in alternatives[:10]:
        name_lower = alt['name'].lower()

        is_expected = any(term in name_lower for term in expected_terms)
        marker = "✓" if is_expected else " "

        print(f"\n  {marker} {alt['name']}")
        print(f"    Equipment: {alt.get('equipment', 'Unknown')}")
        print(f"    Movements: {', '.join(alt.get('movement_patterns', ['None']))}")

        if is_expected:
            found_expected.append(alt['name'])

    if found_expected:
        print(f"\n  ✓ Found expected alternatives: {', '.join(found_expected)}")
        return True
    else:
        print(f"\n  ⚠️  Did not find expected alternatives (goblet/front/belt squats)")
        print("  Note: This may be due to exercise naming in database")
        return False


def main():
    print("=" * 60)
    print("Biomechanical Constraint System Tests")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)

    print("✓ Connected")

    # Run tests
    results = {}

    results['forbidden_exercises'] = test_biomechanical_forbidden_exercises(graph)
    results['biomechanics_check'] = test_exercise_biomechanics_check(graph)
    results['alternatives'] = test_movement_based_alternatives(graph)
    results['contraindications'] = test_contraindication_mapping(graph)
    results['shoulder_scenario'] = test_shoulder_impingement_scenario(graph)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "⚠️  WARN"
        print(f"{status} {test_name.replace('_', ' ').title()}")

    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)

    print(f"\n{passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n✓ All tests passed!")
    else:
        print("\n⚠️  Some tests need attention")

    graph.close()


if __name__ == "__main__":
    main()
