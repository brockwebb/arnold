#!/usr/bin/env python3
"""
Export all raw tags and exercise names for normalization review.

Internal Codename: SKYNET-READER
Export unique values that need normalization.

Usage:
    python scripts/export_raw_tags.py
    python scripts/export_raw_tags.py --output data/normalization/raw_tags.json
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph


def export_unique_exercise_names(graph: ArnoldGraph) -> dict:
    """Export all unique exercise names with frequencies."""
    query = """
    MATCH (ei:ExerciseInstance)
    RETURN ei.exercise_name_raw as name, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    return {
        "total_unique": len(results),
        "items": [{"name": r["name"], "freq": r["freq"]} for r in results]
    }


def export_unique_tags(graph: ArnoldGraph) -> dict:
    """Export all unique workout tags with frequencies."""
    query = """
    MATCH (w:Workout)
    UNWIND w.tags_raw as tag
    RETURN tag, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    return {
        "total_unique": len(results),
        "items": [{"name": r["tag"], "freq": r["freq"]} for r in results]
    }


def export_unique_goals(graph: ArnoldGraph) -> dict:
    """Export all unique goals with frequencies."""
    query = """
    MATCH (w:Workout)
    UNWIND w.goals_raw as goal
    RETURN goal, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    return {
        "total_unique": len(results),
        "items": [{"name": r["goal"], "freq": r["freq"]} for r in results]
    }


def export_unique_equipment(graph: ArnoldGraph) -> dict:
    """Export all unique equipment with frequencies."""
    query = """
    MATCH (w:Workout)
    UNWIND w.equipment_raw as equip
    RETURN equip, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    return {
        "total_unique": len(results),
        "items": [{"name": r["equip"], "freq": r["freq"]} for r in results]
    }


def export_unique_phases(graph: ArnoldGraph) -> dict:
    """Export all unique periodization phases with frequencies."""
    query = """
    MATCH (w:Workout)
    WHERE w.periodization_phase IS NOT NULL
    RETURN w.periodization_phase as phase, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    return {
        "total_unique": len(results),
        "items": [{"name": r["phase"], "freq": r["freq"]} for r in results]
    }


def export_unmapped_exercises(graph: ArnoldGraph) -> dict:
    """Export exercise instances not linked to Exercise nodes."""
    query = """
    MATCH (ei:ExerciseInstance)
    WHERE NOT (ei)-[:INSTANCE_OF]->(:Exercise)
    RETURN ei.exercise_name_raw as name, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    return {
        "total_unique": len(results),
        "items": [{"name": r["name"], "freq": r["freq"]} for r in results]
    }


def main():
    parser = argparse.ArgumentParser(description="Export raw tags for normalization")
    parser.add_argument(
        "--output",
        type=str,
        default="data/normalization/raw_tags.json",
        help="Output JSON file path"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SKYNET-READER: Export Raw Tags")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Export all categories
    print("\nExporting unique values...")

    exports = {}

    print("  • Exercise names...")
    exports["exercise_names"] = export_unique_exercise_names(graph)
    print(f"    Found {exports['exercise_names']['total_unique']} unique")

    print("  • Unmapped exercises...")
    exports["unmapped_exercises"] = export_unmapped_exercises(graph)
    print(f"    Found {exports['unmapped_exercises']['total_unique']} unmapped")

    print("  • Workout tags...")
    exports["tags"] = export_unique_tags(graph)
    print(f"    Found {exports['tags']['total_unique']} unique")

    print("  • Goals...")
    exports["goals"] = export_unique_goals(graph)
    print(f"    Found {exports['goals']['total_unique']} unique")

    print("  • Equipment...")
    exports["equipment"] = export_unique_equipment(graph)
    print(f"    Found {exports['equipment']['total_unique']} unique")

    print("  • Periodization phases...")
    exports["phases"] = export_unique_phases(graph)
    print(f"    Found {exports['phases']['total_unique']} unique")

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(exports, f, indent=2)

    print(f"\n✓ Exported to {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Export Summary")
    print("=" * 60)
    print(f"Exercise names: {exports['exercise_names']['total_unique']}")
    print(f"Unmapped exercises: {exports['unmapped_exercises']['total_unique']}")
    print(f"Tags: {exports['tags']['total_unique']}")
    print(f"Goals: {exports['goals']['total_unique']}")
    print(f"Equipment: {exports['equipment']['total_unique']}")
    print(f"Phases: {exports['phases']['total_unique']}")

    print("\nTop 10 unmapped exercises:")
    for item in exports['unmapped_exercises']['items'][:10]:
        print(f"  • {item['name']}: {item['freq']}x")

    print("\n" + "=" * 60)
    print("Next steps:")
    print("  1. Review: cat data/normalization/raw_tags.json")
    print("  2. Create mappings: vi data/normalization/mappings.yaml")
    print("  3. Apply: python scripts/apply_normalization.py")
    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
