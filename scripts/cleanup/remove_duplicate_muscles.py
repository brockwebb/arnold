#!/usr/bin/env python3
"""
Remove duplicate muscle nodes that don't have FMA IDs
These are from old imports using common names instead of FMA anatomical terms
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()


def cleanup_duplicate_muscles():
    """Remove muscle nodes without FMA IDs (duplicates from old imports)"""

    print(f"\n{'='*70}")
    print("DUPLICATE MUSCLE CLEANUP")
    print(f"{'='*70}\n")

    graph = ArnoldGraph()

    try:
        # First, check what we're about to delete
        print("Checking for duplicate muscles...")
        result = graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.fma_id IS NULL
            RETURN count(m) as count, collect(m.name)[0..20] as sample_names
        """)

        duplicate_count = result[0]['count']
        sample_names = result[0]['sample_names']

        if duplicate_count == 0:
            print("  ✓ No duplicate muscles found!")
            return

        print(f"  Found {duplicate_count} duplicate muscles without FMA IDs")
        print(f"  Sample names: {', '.join(sample_names[:10])}")

        # Check if any have relationships
        print("\nChecking for relationships to duplicate muscles...")
        result = graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.fma_id IS NULL
            OPTIONAL MATCH (m)-[r]-()
            RETURN count(DISTINCT r) as rel_count
        """)

        rel_count = result[0]['rel_count']
        print(f"  Relationships to duplicates: {rel_count}")

        if rel_count > 0:
            print(f"\n  ⚠️  WARNING: {rel_count} relationships will be deleted")
            print("  These are likely from the old import and should be replaced")
            print("  with FMA-based relationships.\n")

        # Delete duplicates
        print("\nDeleting duplicate muscle nodes...")
        result = graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.fma_id IS NULL
            DETACH DELETE m
            RETURN count(m) as deleted
        """)

        # Note: The above query won't return the count correctly after DELETE
        # So we'll verify instead
        print(f"  ✓ Deleted {duplicate_count} duplicate muscles\n")

        # Verify cleanup
        print("Verifying cleanup...")
        result = graph.execute_query("""
            MATCH (m:Muscle)
            RETURN
                count(m) as total_muscles,
                count(CASE WHEN m.fma_id IS NOT NULL THEN 1 END) as with_fma_id,
                count(CASE WHEN m.fma_id IS NULL THEN 1 END) as without_fma_id
        """)

        print(f"  Total muscles remaining: {result[0]['total_muscles']}")
        print(f"  With FMA ID: {result[0]['with_fma_id']}")
        print(f"  Without FMA ID: {result[0]['without_fma_id']}")

        if result[0]['without_fma_id'] == 0:
            print("\n  ✅ All duplicate muscles successfully removed!")
        else:
            print(f"\n  ⚠️  Still {result[0]['without_fma_id']} muscles without FMA ID")

    finally:
        graph.close()

    print(f"\n{'='*70}")
    print("✓ CLEANUP COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    cleanup_duplicate_muscles()
