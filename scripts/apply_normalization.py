#!/usr/bin/env python3
"""
Apply normalization to CYBERDYNE-CORE graph database.

Internal Codename: SKYNET-READER
Clean and normalize exercise instances, tags, goals, and equipment.

Usage:
    python scripts/apply_normalization.py
    python scripts/apply_normalization.py --dry-run  # Preview changes without applying
"""

import sys
from pathlib import Path
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph
from arnold.normalizer import (
    is_non_exercise,
    normalize_exercise_name_for_matching,
    find_canonical_exercise_id
)


def cleanup_non_exercises(graph: ArnoldGraph, dry_run: bool = False) -> dict:
    """
    Remove ExerciseInstance nodes that are not actual exercises.

    Returns:
        Statistics about cleanup
    """
    print("\n[Step 1] Identifying non-exercise entries...")

    # Get all exercise instances
    query = """
    MATCH (ei:ExerciseInstance)
    RETURN ei.id as id, ei.exercise_name_raw as name
    """
    results = graph.execute_query(query)

    to_delete = []
    for r in results:
        if is_non_exercise(r['name']):
            to_delete.append(r['id'])

    print(f"  Found {len(to_delete)} non-exercise entries to remove")

    if to_delete and not dry_run:
        # Delete in batches
        batch_size = 100
        deleted = 0

        for i in range(0, len(to_delete), batch_size):
            batch = to_delete[i:i + batch_size]
            query = """
            MATCH (ei:ExerciseInstance)
            WHERE ei.id IN $ids
            DETACH DELETE ei
            """
            graph.execute_write(query, {'ids': batch})
            deleted += len(batch)

            if deleted % 200 == 0:
                print(f"    Deleted {deleted}/{len(to_delete)}...")

        print(f"  ✓ Deleted {deleted} non-exercise entries")

    return {
        'identified': len(to_delete),
        'deleted': len(to_delete) if not dry_run else 0
    }


def normalize_exercise_instances(graph: ArnoldGraph, dry_run: bool = False) -> dict:
    """
    Normalize exercise instance names and link to canonical Exercise nodes.

    Returns:
        Statistics about normalization
    """
    print("\n[Step 2] Normalizing exercise instances...")

    # Get unmapped instances
    query = """
    MATCH (ei:ExerciseInstance)
    WHERE NOT (ei)-[:INSTANCE_OF]->(:Exercise)
    RETURN ei.id as id, ei.exercise_name_raw as raw_name
    """
    results = graph.execute_query(query)

    print(f"  Found {len(results)} unmapped exercise instances")

    stats = {
        'total_unmapped': len(results),
        'matched': 0,
        'still_unmapped': 0
    }

    matched_pairs = []

    for r in results:
        raw_name = r['raw_name']
        normalized = normalize_exercise_name_for_matching(raw_name)
        exercise_id = find_canonical_exercise_id(normalized)

        if exercise_id:
            matched_pairs.append({
                'instance_id': r['id'],
                'exercise_id': exercise_id,
                'raw_name': raw_name
            })
            stats['matched'] += 1
        else:
            stats['still_unmapped'] += 1

    print(f"  Matched {stats['matched']} instances to canonical exercises")

    if matched_pairs and not dry_run:
        # Create relationships in batches
        batch_size = 100
        linked = 0

        for i in range(0, len(matched_pairs), batch_size):
            batch = matched_pairs[i:i + batch_size]

            for pair in batch:
                query = """
                MATCH (ei:ExerciseInstance {id: $instance_id})
                MATCH (e:Exercise {id: $exercise_id})
                MERGE (ei)-[:INSTANCE_OF]->(e)
                """
                graph.execute_write(query, {
                    'instance_id': pair['instance_id'],
                    'exercise_id': pair['exercise_id']
                })
                linked += 1

            if linked % 200 == 0:
                print(f"    Linked {linked}/{len(matched_pairs)}...")

        print(f"  ✓ Linked {linked} instances to Exercise nodes")

    return stats


def normalize_workout_tags(graph: ArnoldGraph, dry_run: bool = False) -> dict:
    """
    Create CanonicalTag nodes and link workouts to them.

    Returns:
        Statistics about tag normalization
    """
    print("\n[Step 3] Normalizing workout tags...")

    # Get all unique tags
    query = """
    MATCH (w:Workout)
    UNWIND w.tags_raw as tag
    RETURN DISTINCT tag, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    print(f"  Found {len(results)} unique tags")

    if not dry_run:
        # Create CanonicalTag nodes
        for r in results:
            tag = r['tag']
            tag_id = f"TAG:{tag.upper().replace(' ', '_')}"

            query = """
            MERGE (t:CanonicalTag {id: $id})
            SET t.name = $name,
                t.category = 'workout_tag'
            """
            graph.execute_write(query, {'id': tag_id, 'name': tag})

        # Link workouts to tags
        query = """
        MATCH (w:Workout)
        UNWIND w.tags_raw as tag
        WITH w, tag
        MATCH (t:CanonicalTag)
        WHERE toLower(t.name) = toLower(tag)
        MERGE (w)-[:HAS_TAG]->(t)
        """
        graph.execute_write(query)

        print(f"  ✓ Created {len(results)} CanonicalTag nodes and linked to workouts")

    return {
        'tags_created': len(results) if not dry_run else 0
    }


def normalize_goals(graph: ArnoldGraph, dry_run: bool = False) -> dict:
    """
    Create CanonicalGoal nodes and link workouts to them.

    Returns:
        Statistics about goal normalization
    """
    print("\n[Step 4] Normalizing workout goals...")

    # Get all unique goals
    query = """
    MATCH (w:Workout)
    UNWIND w.goals_raw as goal
    RETURN DISTINCT goal, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    print(f"  Found {len(results)} unique goals")

    if not dry_run:
        # Create CanonicalGoal nodes
        for r in results:
            goal = r['goal']
            goal_id = f"GOAL:{goal.upper().replace(' ', '_')}"

            query = """
            MERGE (g:CanonicalGoal {id: $id})
            SET g.name = $name
            """
            graph.execute_write(query, {'id': goal_id, 'name': goal})

        # Link workouts to goals
        query = """
        MATCH (w:Workout)
        UNWIND w.goals_raw as goal
        WITH w, goal
        MATCH (g:CanonicalGoal)
        WHERE toLower(g.name) = toLower(goal)
        MERGE (w)-[:HAS_GOAL]->(g)
        """
        graph.execute_write(query)

        print(f"  ✓ Created {len(results)} CanonicalGoal nodes and linked to workouts")

    return {
        'goals_created': len(results) if not dry_run else 0
    }


def normalize_equipment(graph: ArnoldGraph, dry_run: bool = False) -> dict:
    """
    Create Equipment nodes and link workouts to them.

    Returns:
        Statistics about equipment normalization
    """
    print("\n[Step 5] Normalizing equipment...")

    # Get all unique equipment
    query = """
    MATCH (w:Workout)
    UNWIND w.equipment_raw as equip
    RETURN DISTINCT equip, count(*) as freq
    ORDER BY freq DESC
    """
    results = graph.execute_query(query)

    print(f"  Found {len(results)} unique equipment items")

    if not dry_run:
        # Many equipment items already exist from user profile
        # Merge to avoid duplicates
        for r in results:
            equip = r['equip']
            equip_id = f"EQUIPMENT:{equip.upper().replace(' ', '_')}"

            query = """
            MERGE (eq:Equipment {id: $id})
            SET eq.name = $name
            """
            graph.execute_write(query, {'id': equip_id, 'name': equip})

        # Link workouts to equipment
        query = """
        MATCH (w:Workout)
        UNWIND w.equipment_raw as equip
        WITH w, equip
        MATCH (eq:Equipment)
        WHERE toLower(eq.name) = toLower(equip)
        MERGE (w)-[:USED_EQUIPMENT]->(eq)
        """
        graph.execute_write(query)

        print(f"  ✓ Created/merged {len(results)} Equipment nodes and linked to workouts")

    return {
        'equipment_created': len(results) if not dry_run else 0
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Apply normalization to graph")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SKYNET-READER: Apply Normalization")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Get baseline stats
    print("\n[Baseline] Current state:")
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
        print(f"  Linked: {r['linked']}")
        print(f"  Match rate: {r['match_rate_pct']}%")

    # Apply normalization steps
    stats = {}

    stats['cleanup'] = cleanup_non_exercises(graph, dry_run=args.dry_run)
    stats['exercises'] = normalize_exercise_instances(graph, dry_run=args.dry_run)
    stats['tags'] = normalize_workout_tags(graph, dry_run=args.dry_run)
    stats['goals'] = normalize_goals(graph, dry_run=args.dry_run)
    stats['equipment'] = normalize_equipment(graph, dry_run=args.dry_run)

    # Get final stats
    if not args.dry_run:
        print("\n[Final] After normalization:")
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
            print(f"  Linked: {r['linked']}")
            print(f"  Match rate: {r['match_rate_pct']}%")

    # Summary
    print("\n" + "=" * 60)
    print("Normalization Summary")
    print("=" * 60)
    print(f"Non-exercises removed: {stats['cleanup']['deleted']}")
    print(f"Exercise instances matched: {stats['exercises']['matched']}")
    print(f"Canonical tags created: {stats['tags']['tags_created']}")
    print(f"Canonical goals created: {stats['goals']['goals_created']}")
    print(f"Equipment items processed: {stats['equipment']['equipment_created']}")

    if args.dry_run:
        print("\n⚠️  DRY RUN - No changes were applied")
        print("Run without --dry-run to apply normalization")
    else:
        print("\n✓ Normalization complete")

    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
