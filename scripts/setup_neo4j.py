#!/usr/bin/env python3
"""
Initialize Neo4j database schema for Arnold.

This script:
1. Verifies Neo4j connection
2. Creates all constraints and indexes
3. Displays current graph statistics

Usage:
    python scripts/setup_neo4j.py
    python scripts/setup_neo4j.py --clear  # WARNING: Deletes all data
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph, print_stats


def main():
    parser = argparse.ArgumentParser(description="Initialize Arnold Neo4j database")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all existing data (DESTRUCTIVE!)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Arnold Graph Database Setup")
    print("Cyberdyne Systems Model 101")
    print("=" * 60)

    # Initialize connection
    print("\n[1/4] Connecting to Neo4j...")
    try:
        graph = ArnoldGraph()
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure to:")
        print("  1. Create .env file from .env.example")
        print("  2. Set NEO4J_PASSWORD in .env")
        print("  3. Start Neo4j (e.g., via Docker)")
        sys.exit(1)

    if not graph.verify_connectivity():
        print("\n❌ Could not connect to Neo4j")
        print("\nMake sure Neo4j is running:")
        print("  docker run -p 7687:7687 -p 7474:7474 \\")
        print("    -e NEO4J_AUTH=neo4j/your_password \\")
        print("    neo4j:latest")
        sys.exit(1)

    print("✓ Connected successfully")

    # Clear database if requested
    if args.clear:
        print("\n[2/4] Clearing existing data...")
        response = input("⚠️  This will delete ALL data. Type 'yes' to confirm: ")
        if response.lower() == 'yes':
            graph.clear_database(confirm=True)
            print("✓ Database cleared")
        else:
            print("Skipping clear")
    else:
        print("\n[2/4] Skipping clear (use --clear to wipe database)")

    # Create schema
    print("\n[3/4] Creating constraints and indexes...")
    graph.create_constraints()
    print("✓ Schema initialized")

    # Display statistics
    print("\n[4/4] Gathering statistics...")
    stats = graph.get_stats()
    print_stats(stats)

    # Success message
    print("\n" + "=" * 60)
    if stats["total_nodes"] == 0:
        print("✓ Database initialized and ready for data import")
        print("\nNext steps:")
        print("  1. python scripts/import_uberon.py")
        print("  2. python scripts/import_exercises.py")
        print("  3. python scripts/import_user_profile.py")
    else:
        print("✓ Database schema updated")
        print(f"  {stats['total_nodes']} nodes, {stats['total_relationships']} relationships")

    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
