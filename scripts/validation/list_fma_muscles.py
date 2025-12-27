#!/usr/bin/env python3
"""
List all FMA muscles we have imported to understand how to create muscle groups
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()


def list_muscles():
    """List all muscles with their FMA IDs and names"""

    graph = ArnoldGraph()

    try:
        result = graph.execute_query("""
            MATCH (m:Muscle)
            WHERE m.fma_id IS NOT NULL
            RETURN m.fma_id as fma_id,
                   m.name as name,
                   m.common_name as common_name
            ORDER BY m.common_name, m.name
        """)

        print(f"\n{'='*70}")
        print(f"FMA MUSCLES ({len(result)} total)")
        print(f"{'='*70}\n")

        for r in result:
            common = r['common_name'] or '(no common name)'
            print(f"  {common:20s} → {r['name']:40s} ({r['fma_id']})")

    finally:
        graph.close()


if __name__ == "__main__":
    list_muscles()
