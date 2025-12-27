#!/usr/bin/env python3
"""
Validate Phase 2a workout import.

Internal Codename: SKYNET-READER
Verify workout history is properly imported into CYBERDYNE-CORE.

Usage:
    python scripts/validate_phase2.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph, print_stats


def run_validation_queries(graph: ArnoldGraph):
    """Run Phase 2a validation queries."""

    print("\n" + "=" * 60)
    print("Phase 2a Validation Queries")
    print("=" * 60)

    # Query 1: Total workouts
    print("\n[Query 1] Total workouts imported")
    result = graph.execute_query("MATCH (w:Workout) RETURN count(w) as total")
    total = result[0]['total']
    print(f"  Found {total} workouts")
    print(f"  {'✓ PASS' if total >= 160 else '✗ FAIL: Expected ~160'}")

    # Query 2: Date range
    print("\n[Query 2] Workout date range")
    result = graph.execute_query("""
        MATCH (w:Workout)
        WHERE w.date IS NOT NULL
        RETURN min(w.date) as earliest, max(w.date) as latest
    """)
    if result:
        print(f"  Earliest: {result[0]['earliest']}")
        print(f"  Latest: {result[0]['latest']}")
        print("  ✓ PASS")

    # Query 3: Total exercise instances
    print("\n[Query 3] Total exercise instances")
    result = graph.execute_query("MATCH (ei:ExerciseInstance) RETURN count(ei) as total")
    total_instances = result[0]['total']
    print(f"  Found {total_instances} exercise instances")
    print(f"  {'✓ PASS' if total_instances > 800 else '✗ FAIL: Expected 800+'}")

    # Query 4: Instances linked to Exercise nodes
    print("\n[Query 4] Exercise instance matching")
    result = graph.execute_query("""
        MATCH (ei:ExerciseInstance)
        OPTIONAL MATCH (ei)-[:INSTANCE_OF]->(e:Exercise)
        RETURN
            count(ei) as total,
            count(e) as linked,
            round(100.0 * count(e) / count(ei), 1) as match_rate_pct
    """)
    if result:
        r = result[0]
        print(f"  Total instances: {r['total']}")
        print(f"  Linked to exercises: {r['linked']}")
        print(f"  Match rate: {r['match_rate_pct']}%")
        print(f"  {'✓ PASS' if r['match_rate_pct'] >= 5.0 else '⚠️  WARNING: Low match rate (expected for Phase 2a)'}")

    # Query 5: Temporal chain
    print("\n[Query 5] Temporal chain integrity")
    result = graph.execute_query("""
        MATCH (w1:Workout)
        WHERE NOT ()-[:PREVIOUS]->(w1)
        OPTIONAL MATCH path = (w1)-[:PREVIOUS*]->(w2:Workout)
        RETURN count(DISTINCT w1) as chain_starts, max(length(path)) + 1 as max_chain_length
    """)
    if result:
        r = result[0]
        print(f"  Chain starts: {r['chain_starts']}")
        print(f"  Max chain length: {r['max_chain_length']}")
        print(f"  {'✓ PASS' if r['chain_starts'] <= 10 else '⚠️  WARNING: Multiple disconnected chains'}")

    # Query 6: Workouts by type
    print("\n[Query 6] Workouts by type")
    result = graph.execute_query("""
        MATCH (w:Workout)
        RETURN w.type as type, count(*) as count
        ORDER BY count DESC
        LIMIT 10
    """)
    if result:
        for r in result:
            print(f"  {r['type']}: {r['count']}")
        print("  ✓ PASS")

    # Query 7: Most common exercises
    print("\n[Query 7] Top 10 most common exercises")
    result = graph.execute_query("""
        MATCH (ei:ExerciseInstance)
        RETURN ei.exercise_name_raw as exercise, count(*) as times_performed
        ORDER BY times_performed DESC
        LIMIT 10
    """)
    if result:
        for r in result:
            print(f"  {r['exercise']}: {r['times_performed']}x")
        print("  ✓ PASS")

    # Query 8: Unmapped exercises (top 20)
    print("\n[Query 8] Top 20 unmapped exercises (for Phase 2b)")
    result = graph.execute_query("""
        MATCH (ei:ExerciseInstance)
        WHERE NOT (ei)-[:INSTANCE_OF]->(:Exercise)
        RETURN ei.exercise_name_raw as raw_name, count(*) as occurrences
        ORDER BY occurrences DESC
        LIMIT 20
    """)
    if result:
        print(f"  Found {len(result)} unmapped exercise types:")
        for r in result[:10]:
            print(f"    • {r['raw_name']}: {r['occurrences']}x")
        if len(result) > 10:
            print(f"    ... and {len(result) - 10} more")
        print("  ℹ️  These will be normalized in Phase 2b")

    # Query 9: Recent training volume
    print("\n[Query 9] Training volume (last 4 weeks from most recent workout)")
    result = graph.execute_query("""
        MATCH (latest:Workout)
        WITH latest ORDER BY latest.date DESC LIMIT 1
        MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)
        WHERE w.date >= date(latest.date) - duration('P28D')
        WITH date.truncate('week', w.date) as week, count(ei) as sets
        RETURN week, sets
        ORDER BY week
    """)
    if result:
        print("  Week | Sets")
        print("  -----|-----")
        for r in result:
            print(f"  {r['week']} | {r['sets']}")
        print("  ✓ PASS")

    # Query 10: Frontmatter coverage
    print("\n[Query 10] Frontmatter field coverage")
    result = graph.execute_query("""
        MATCH (w:Workout)
        RETURN
            sum(CASE WHEN w.periodization_phase IS NOT NULL THEN 1 ELSE 0 END) as has_phase,
            sum(CASE WHEN size(w.tags_raw) > 0 THEN 1 ELSE 0 END) as has_tags,
            sum(CASE WHEN size(w.goals_raw) > 0 THEN 1 ELSE 0 END) as has_goals,
            sum(CASE WHEN w.perceived_intensity IS NOT NULL THEN 1 ELSE 0 END) as has_intensity,
            count(w) as total
    """)
    if result:
        r = result[0]
        total = r['total']
        print(f"  Periodization phase: {r['has_phase']}/{total} ({round(100*r['has_phase']/total, 1)}%)")
        print(f"  Tags: {r['has_tags']}/{total} ({round(100*r['has_tags']/total, 1)}%)")
        print(f"  Goals: {r['has_goals']}/{total} ({round(100*r['has_goals']/total, 1)}%)")
        print(f"  Perceived intensity: {r['has_intensity']}/{total} ({round(100*r['has_intensity']/total, 1)}%)")
        print("  ✓ PASS")


def main():
    print("=" * 60)
    print("Arnold Phase 2a Validation")
    print("SKYNET-READER: Workout History Import")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Run validation queries
    run_validation_queries(graph)

    # Show overall graph statistics
    print("\n" + "=" * 60)
    print("CYBERDYNE-CORE Statistics")
    print("=" * 60)
    stats = graph.get_stats()
    print_stats(stats)

    print("\n" + "=" * 60)
    print("✓ Phase 2a Validation Complete")
    print("=" * 60)
    print("\nNext steps:")
    print("  • Phase 2b: Tag normalization and exercise matching")
    print("  • Run: python scripts/export_raw_tags.py")
    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
