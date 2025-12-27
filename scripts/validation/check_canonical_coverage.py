#!/usr/bin/env python3
"""
Check if canonical exercises exist for common novel exercise patterns
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()


def check_canonical_coverage():
    """Check canonical coverage"""

    graph = ArnoldGraph()

    try:
        # Check for specific exercises
        test_cases = [
            "Pull-Up",
            "Bulgarian Split Squat",
            "Bird Dog",
            "Face Pull",
            "Shoulder Dislocate",
            "Step-Up",
            "Deadhang",
            "Bear Crawl"
        ]

        print(f"\n{'='*70}")
        print("CHECKING CANONICAL EXERCISE COVERAGE")
        print(f"{'='*70}\n")

        for test in test_cases:
            result = graph.execute_query("""
                MATCH (ex:Exercise)
                WHERE ex.is_canonical = true
                  AND (toLower(ex.name) CONTAINS toLower($name)
                       OR toLower($name) CONTAINS toLower(ex.name))
                RETURN ex.name as name
                LIMIT 5
            """, parameters={'name': test})

            if result:
                matches = [r['name'] for r in result]
                print(f"  ✓ '{test}' → Found: {', '.join(matches[:3])}")
            else:
                print(f"  ✗ '{test}' → NOT FOUND in canonical")

        # Count total canonical exercises
        result = graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN count(ex) as count
        """)

        print(f"\n  Total canonical exercises: {result[0]['count']}")

        # Sample canonical names
        result = graph.execute_query("""
            MATCH (ex:Exercise WHERE ex.is_canonical = true)
            RETURN ex.name as name
            ORDER BY ex.name
            LIMIT 30
        """)

        print(f"\n  Sample canonical exercises:")
        for r in result:
            print(f"    • {r['name']}")

    finally:
        graph.close()


if __name__ == "__main__":
    check_canonical_coverage()
