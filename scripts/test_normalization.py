#!/usr/bin/env python3
"""Test normalization on specific exercise names."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.normalizer import (
    normalize_exercise_name_for_matching,
    find_canonical_exercise_id,
    is_non_exercise
)

# Test cases from validation
test_cases = [
    "Sandbag Shouldering",
    "Renegade Rows",
    "Weighted Pull-Ups",
    "Spiderman lunges (5/side).",
    "Bulgarian Split Squats",
    "Face Pulls",
    "Trap Bar Deadlifts",
    "**Dynamic Mobility**:",
    "Arm swings (30 sec).",
    "Steps: 50 per set",
]

print("Testing normalization:")
print("=" * 80)

for name in test_cases:
    is_non = is_non_exercise(name)
    if is_non:
        print(f"\n❌ NON-EXERCISE: {name}")
        continue

    normalized = normalize_exercise_name_for_matching(name)
    exercise_id = find_canonical_exercise_id(normalized)

    print(f"\n✓ Original: {name}")
    print(f"  Normalized: {normalized}")
    print(f"  Exercise ID: {exercise_id or 'UNMAPPED'}")
