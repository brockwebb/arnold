#!/usr/bin/env python3
"""
Validate Phase 1 implementation with example queries.

This script runs the validation queries from the spec to ensure
the graph is properly set up and queryable.

Usage:
    python scripts/validate_phase1.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph


def run_validation_queries(graph: ArnoldGraph):
    """Run the Phase 1 validation queries from the spec."""

    print("\n" + "=" * 60)
    print("Phase 1 Validation Queries")
    print("=" * 60)

    # Query 1: What muscles does deadlift target?
    print("\n[Query 1] What muscles does deadlift target?")
    query = """
    MATCH (e:Exercise)-[r:TARGETS]->(m:Muscle)
    WHERE toLower(e.name) CONTAINS 'deadlift'
    RETURN e.name as exercise, r.role as role, m.name as muscle
    LIMIT 10
    """
    results = graph.execute_query(query)
    if results:
        print(f"  Found {len(results)} muscle relationships:")
        for r in results[:5]:
            print(f"    {r['exercise']} → {r['role']} → {r['muscle']}")
        if len(results) > 5:
            print(f"    ... and {len(results) - 5} more")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL: No deadlift exercises found or no muscle relationships")

    # Query 2: What exercises target the gluteus maximus?
    print("\n[Query 2] What exercises target the gluteus maximus?")
    query = """
    MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
    WHERE toLower(m.name) CONTAINS 'glute' OR toLower(m.name) CONTAINS 'gluteus'
    RETURN DISTINCT e.name as exercise
    LIMIT 10
    """
    results = graph.execute_query(query)
    if results:
        print(f"  Found {len(results)} exercises:")
        for r in results[:5]:
            print(f"    - {r['exercise']}")
        if len(results) > 5:
            print(f"    ... and {len(results) - 5} more")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL: No gluteus muscles found or no exercises linked")

    # Query 3: What equipment do I have for pull exercises?
    print("\n[Query 3] What equipment do I have for pull exercises?")
    query = """
    MATCH (eq:Equipment)
    WHERE eq.user_has = true
    RETURN eq.name as equipment, eq.category as category
    LIMIT 20
    """
    results = graph.execute_query(query)
    if results:
        print(f"  Found {len(results)} equipment items:")
        for r in results[:10]:
            print(f"    - {r['equipment']} ({r['category']})")
        if len(results) > 10:
            print(f"    ... and {len(results) - 10} more")
        print("  ✓ PASS")
    else:
        print("  ! WARNING: No user equipment marked. Did you import profile?")

    # Query 4: What are my current injuries?
    print("\n[Query 4] What are my current injuries?")
    query = """
    MATCH (i:Injury)
    WHERE i.status IN ['active', 'recovering']
    RETURN i.name as injury, i.status as status, i.notes as notes
    """
    results = graph.execute_query(query)
    if results:
        print(f"  Found {len(results)} injuries:")
        for r in results:
            print(f"    - {r['injury']} ({r['status']})")
            if r['notes']:
                print(f"      {r['notes']}")
        print("  ✓ PASS")
    else:
        print("  ! WARNING: No injuries found. Did you import profile?")

    # Query 5: What constraints exist?
    print("\n[Query 5] What constraints exist?")
    query = """
    MATCH (i:Injury)-[:CREATES]->(c:Constraint)
    RETURN i.name as injury, c.description as constraint, c.constraint_type as type
    LIMIT 10
    """
    results = graph.execute_query(query)
    if results:
        print(f"  Found {len(results)} constraints:")
        for r in results[:5]:
            print(f"    {r['injury']}: {r['constraint']} ({r['type']})")
        if len(results) > 5:
            print(f"    ... and {len(results) - 5} more")
        print("  ✓ PASS")
    else:
        print("  ! WARNING: No constraints found. Did you import profile?")

    # Query 6: Graph connectivity test
    print("\n[Query 6] Graph connectivity - exercises to muscles")
    query = """
    MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
    RETURN count(DISTINCT e) as exercises, count(DISTINCT m) as muscles, count(*) as relationships
    """
    results = graph.execute_query(query)
    if results:
        r = results[0]
        print(f"  {r['exercises']} exercises linked to {r['muscles']} muscles via {r['relationships']} relationships")
        if r['relationships'] > 0:
            print("  ✓ PASS")
        else:
            print("  ✗ FAIL: No exercise-muscle relationships found")
    else:
        print("  ✗ FAIL: Query returned no results")

    # Summary statistics
    print("\n" + "=" * 60)
    print("Graph Summary")
    print("=" * 60)

    from arnold.graph import print_stats
    stats = graph.get_stats()
    print_stats(stats)


def main():
    print("=" * 60)
    print("Arnold Phase 1 Validation")
    print("Cyberdyne Systems Model 101")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to Neo4j...")
    try:
        graph = ArnoldGraph()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Run validation
    run_validation_queries(graph)

    graph.close()

    print("\n" + "=" * 60)
    print("Validation complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
