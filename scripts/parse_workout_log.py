#!/usr/bin/env python3
"""
Parse a single workout log file.

Internal Codename: SKYNET-READER
Parse and understand workout logs.

Usage:
    python scripts/parse_workout_log.py <path_to_workout.md>
    python scripts/parse_workout_log.py <path_to_workout.md> --json
"""

import sys
import json
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.parser import parse_workout_file


def main():
    parser = argparse.ArgumentParser(description="Parse workout log file")
    parser.add_argument(
        "file",
        type=str,
        help="Path to workout markdown file"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print output"
    )
    args = parser.parse_args()

    filepath = Path(args.file)

    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    print(f"[SKYNET-READER] Parsing {filepath.name}...")

    try:
        parsed = parse_workout_file(filepath)

        if args.json:
            indent = 2 if args.pretty else None
            print(json.dumps(parsed, indent=indent, default=str))
        else:
            # Human-readable output
            print("\n" + "=" * 60)
            print(f"Workout: {parsed['filename']}")
            print("=" * 60)

            # Frontmatter summary
            fm = parsed['frontmatter']
            print(f"\nDate: {fm.get('date', 'N/A')}")
            print(f"Type: {fm.get('type', 'N/A')}")
            print(f"Sport: {fm.get('sport', 'N/A')}")
            if fm.get('periodization_phase'):
                print(f"Phase: {fm['periodization_phase']}")
            if fm.get('tags'):
                print(f"Tags: {', '.join(fm['tags'][:5])}{' ...' if len(fm['tags']) > 5 else ''}")

            # Sections and exercises
            print(f"\nSections: {parsed['metadata']['total_sections']}")
            print(f"Exercises: {parsed['metadata']['total_exercises']}")
            print(f"Sets: {parsed['metadata']['total_sets']}")

            print("\n" + "-" * 60)
            for section in parsed['sections']:
                print(f"\n{section['name']}:")
                for ex in section['exercises']:
                    print(f"  • {ex['name_raw']}")
                    if ex.get('sets'):
                        print(f"    Sets: {len(ex['sets'])}")
                    if ex.get('weight'):
                        print(f"    Weight: {ex['weight']} {ex.get('weight_unit', 'lb')}")

            print("\n" + "=" * 60)
            print("✓ Parse complete")

    except Exception as e:
        print(f"❌ Parse failed: {e}")
        if args.pretty:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
