#!/usr/bin/env python3
"""
Analyze which exercises are being marked as novel
to see if they should actually be variations
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()


def analyze_novel_exercises():
    """Analyze novel exercise classifications"""

    graph = ArnoldGraph()

    try:
        # Get sample novel exercises
        result = graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE ex.is_novel = true
            RETURN ex.name as name
            ORDER BY ex.name
            LIMIT 50
        """)

        print(f"\n{'='*70}")
        print(f"SAMPLE NOVEL EXERCISES (50 of 699)")
        print(f"{'='*70}\n")

        for r in result:
            print(f"  • {r['name']}")

        # Get statistics
        result = graph.execute_query("""
            MATCH (ex:Exercise)
            WHERE ex.is_novel = true
            OPTIONAL MATCH (ex)-[:TARGETS]->(m)
            RETURN
                count(DISTINCT ex) as novel_count,
                count(DISTINCT m) as muscles_targeted
        """)

        print(f"\n{'='*70}")
        print("STATISTICS")
        print(f"{'='*70}\n")
        print(f"  Novel exercises: {result[0]['novel_count']}")
        print(f"  Muscles they target: {result[0]['muscles_targeted']}")

        # Check for common patterns that might be variations
        print(f"\n{'='*70}")
        print("POTENTIAL MISCLASSIFICATIONS (should be variations?)")
        print(f"{'='*70}\n")

        # Look for exercises with common variation indicators
        patterns = [
            ("(", ")"),  # Has parentheses (equipment/modifier)
            ("-", ""),   # Has hyphen (compound name)
        ]

        for pattern, _ in patterns:
            result = graph.execute_query("""
                MATCH (ex:Exercise)
                WHERE ex.is_novel = true
                  AND ex.name CONTAINS $pattern
                RETURN count(ex) as count
            """, parameters={'pattern': pattern})

            if result:
                print(f"  Exercises containing '{pattern}': {result[0]['count']}")

    finally:
        graph.close()


if __name__ == "__main__":
    analyze_novel_exercises()
