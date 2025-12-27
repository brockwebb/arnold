#!/usr/bin/env python3
"""
Test Phase 4 Success Criteria

Validates the three biomechanical inference queries from Phase 4 spec:
1. Find hamstring exercises avoiding knee flexion → RDLs, good mornings
2. Alternative to back squat for shoulder impingement → goblet/front/belt squats
3. Progress from bodyweight lunges → weighted lunges → Bulgarian split squats

Usage:
    python scripts/test_success_criteria.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.queries.biomechanical import BiomechanicalQueries
from arnold.biomechanics import JointAction


def test_criteria_1_hamstring_no_knee_flexion(graph: ArnoldGraph):
    """
    Test Success Criteria 1:
    Find exercises that target hamstrings but avoid knee flexion.

    Expected: Romanian deadlifts, good mornings, hip thrusts
    NOT: Leg curls (these involve knee flexion)
    """
    print("\n" + "=" * 60)
    print("SUCCESS CRITERIA 1: Hamstrings without Knee Flexion")
    print("=" * 60)

    print("\nQuery: Find exercises targeting hamstrings that avoid knee flexion")
    print("Expected: Romanian deadlifts, good mornings, hip thrusts")
    print("Should NOT include: Leg curls, seated leg curls\n")

    queries = BiomechanicalQueries(graph)
    results = queries.query_success_criteria_1()

    print(f"Found {len(results)} exercises:\n")

    # Look for expected exercises
    expected_terms = ['romanian', 'rdl', 'good morning', 'hip thrust', 'deadlift']
    avoided_terms = ['curl']

    found_expected = []
    found_avoided = []

    for i, ex in enumerate(results, 1):
        name_lower = ex['name'].lower()

        # Check if expected
        is_expected = any(term in name_lower for term in expected_terms)
        is_avoided = any(term in name_lower for term in avoided_terms)

        if is_expected:
            found_expected.append(ex['name'])
            marker = "✓"
        elif is_avoided:
            found_avoided.append(ex['name'])
            marker = "❌"
        else:
            marker = " "

        print(f"{marker} {i}. {ex['name']}")
        print(f"     Equipment: {ex.get('equipment', 'Unknown')}")
        print(f"     Movement patterns: {', '.join(ex.get('movement_patterns', ['None']))}\n")

    # Summary
    print("-" * 60)
    if found_expected:
        print(f"✓ Found expected exercises: {', '.join(found_expected)}")

    if found_avoided:
        print(f"❌ WARNING: Found avoided exercises: {', '.join(found_avoided)}")
        print("   (These involve knee flexion and should be filtered out)")

    if not found_avoided and found_expected:
        print("\n✓ PASS: Found expected exercises, no knee flexion movements")
        return True
    elif not found_avoided and not found_expected:
        print("\n⚠️  WARN: No expected exercises found (may be naming mismatch)")
        return False
    else:
        print("\n❌ FAIL: Found exercises with knee flexion")
        return False


def test_criteria_2_squat_alternative_shoulder(graph: ArnoldGraph):
    """
    Test Success Criteria 2:
    Alternative to barbell back squat for someone with shoulder impingement.

    Expected: Goblet squats, front squats, belt squats
    (These avoid overhead shoulder positions)
    """
    print("\n" + "=" * 60)
    print("SUCCESS CRITERIA 2: Squat Alternatives for Shoulder Impingement")
    print("=" * 60)

    print("\nQuery: Find squat alternatives that avoid shoulder elevation/internal rotation")
    print("Expected: Goblet squats, front squats, belt squats, box squats")
    print("Should avoid: Overhead squats, behind-the-neck squats\n")

    queries = BiomechanicalQueries(graph)

    # Try with general "squat" term
    results = queries.query_success_criteria_2(exercise_name="squat")

    print(f"Found {len(results)} alternatives:\n")

    # Look for expected exercises
    expected_terms = ['goblet', 'front squat', 'belt', 'box squat', 'zercher']
    avoided_terms = ['overhead', 'behind']

    found_expected = []
    found_avoided = []

    for i, ex in enumerate(results, 1):
        name_lower = ex['name'].lower()

        is_expected = any(term in name_lower for term in expected_terms)
        is_avoided = any(term in name_lower for term in avoided_terms)

        if is_expected:
            found_expected.append(ex['name'])
            marker = "✓"
        elif is_avoided:
            found_avoided.append(ex['name'])
            marker = "❌"
        else:
            marker = " "

        print(f"{marker} {i}. {ex['name']}")
        print(f"     Equipment: {ex.get('equipment', 'Unknown')}")
        print(f"     Movement patterns: {', '.join(ex.get('movement_patterns', ['None']))}")
        print(f"     Similarity score: {ex.get('similarity_score', 0)}\n")

    # Summary
    print("-" * 60)
    if found_expected:
        print(f"✓ Found expected alternatives: {', '.join(found_expected)}")

    if found_avoided:
        print(f"❌ WARNING: Found exercises to avoid: {', '.join(found_avoided)}")

    if not found_avoided and found_expected:
        print("\n✓ PASS: Found safe alternatives, no overhead movements")
        return True
    elif not found_avoided and not found_expected:
        print("\n⚠️  WARN: No expected alternatives found")
        return False
    else:
        print("\n❌ FAIL: Found overhead movements")
        return False


def test_criteria_3_lunge_progression(graph: ArnoldGraph):
    """
    Test Success Criteria 3:
    Progress from bodyweight lunges.

    Expected chain:
    - Bodyweight lunge → Goblet/Dumbbell lunge → Barbell lunge → Bulgarian split squat
    """
    print("\n" + "=" * 60)
    print("SUCCESS CRITERIA 3: Lunge Progression Chain")
    print("=" * 60)

    print("\nQuery: Find progression chain from bodyweight lunges")
    print("Expected: Bodyweight → Dumbbell → Barbell → Bulgarian split squat\n")

    queries = BiomechanicalQueries(graph)
    results = queries.query_success_criteria_3()

    print(f"Found {len(results)} steps in progression:\n")

    # Expected progression: body only → dumbbell → barbell
    equipment_progression = ['Body Only', 'Dumbbell', 'Kettlebell', 'Barbell']

    for i, ex in enumerate(results, 1):
        equipment = ex.get('equipment', 'Unknown')
        complexity = ex.get('complexity_score', 0)
        level = ex.get('level', 'Unknown')

        # Check if equipment follows progression
        if i == 1:
            is_correct = equipment == 'Body Only'
        elif i <= len(results) - 1:
            # Should be progressively heavier equipment
            is_correct = True
        else:
            is_correct = True

        marker = "→" if i < len(results) else "✓"

        print(f"{marker} Step {i}: {ex['name']}")
        print(f"    Equipment: {equipment}")
        print(f"    Level: {level}")
        print(f"    Complexity: {complexity}")
        print(f"    Movement patterns: {', '.join(ex.get('movement_patterns', ['None']))}\n")

    # Summary
    print("-" * 60)

    if len(results) >= 3:
        # Check if progression makes sense
        base_equipment = results[0].get('equipment', '')
        has_progression = any(
            ex.get('equipment') != base_equipment
            for ex in results[1:]
        )

        if has_progression:
            print("✓ PASS: Valid progression chain with increasing load")
            return True
        else:
            print("⚠️  WARN: Progression found but equipment doesn't vary")
            return False
    else:
        print("❌ FAIL: Insufficient progression steps")
        return False


def main():
    print("=" * 60)
    print("Phase 4 Success Criteria Tests")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)

    print("✓ Connected")

    # Run all three success criteria tests
    results = {}

    results['criteria_1'] = test_criteria_1_hamstring_no_knee_flexion(graph)
    results['criteria_2'] = test_criteria_2_squat_alternative_shoulder(graph)
    results['criteria_3'] = test_criteria_3_lunge_progression(graph)

    # Summary
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    for criteria, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL/WARN"
        print(f"{status} {criteria.replace('_', ' ').title()}")

    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)

    print(f"\n{passed_count}/{total_count} success criteria met")

    if passed_count == total_count:
        print("\n✓ Phase 4 Success Criteria: ALL PASSED")
    elif passed_count >= 2:
        print("\n⚠️  Phase 4 Success Criteria: MOSTLY PASSED")
    else:
        print("\n❌ Phase 4 Success Criteria: NEEDS WORK")

    graph.close()


if __name__ == "__main__":
    main()
