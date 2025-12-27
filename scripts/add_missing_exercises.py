#!/usr/bin/env python3
"""
Add missing common exercises to CYBERDYNE-CORE.

Internal Codename: SKYNET-READER
Create Exercise nodes for common exercises not in free-exercise-db.

Usage:
    python scripts/add_missing_exercises.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph


# Common exercises missing from free-exercise-db
MISSING_EXERCISES = [
    {
        "id": "EXERCISE:BULGARIAN_SPLIT_SQUAT",
        "name": "Bulgarian Split Squat",
        "category": "Strength",
        "force_type": "Push",
        "level": "Intermediate",
        "mechanic": "Compound",
        "equipment": "Dumbbell",
        "primary_muscles": ["Quadriceps"],
        "secondary_muscles": ["Glutes", "Hamstrings"],
        "instructions": ["Step one foot back onto a bench", "Lower into lunge position", "Drive through front heel to stand"]
    },
    {
        "id": "EXERCISE:SPIDERMAN_LUNGE",
        "name": "Spiderman Lunge",
        "category": "Stretching",
        "level": "Beginner",
        "mechanic": "Compound",
        "equipment": "Body Only",
        "primary_muscles": ["Quadriceps", "Hip Flexors"],
        "instructions": ["Start in push-up position", "Bring one foot to outside of same-side hand", "Return and repeat other side"]
    },
    {
        "id": "EXERCISE:SANDBAG_CARRY",
        "name": "Sandbag Carry",
        "category": "Strongman",
        "force_type": "Pull",
        "level": "Intermediate",
        "mechanic": "Compound",
        "equipment": "Other",
        "primary_muscles": ["Forearms", "Trapezius"],
        "secondary_muscles": ["Core", "Legs"],
        "instructions": ["Pick up sandbag", "Walk forward maintaining upright posture", "Keep core tight throughout"]
    },
    {
        "id": "EXERCISE:SANDBAG_SHOULDERING",
        "name": "Sandbag Shouldering",
        "category": "Strongman",
        "force_type": "Pull",
        "level": "Intermediate",
        "mechanic": "Compound",
        "equipment": "Other",
        "primary_muscles": ["Trapezius", "Shoulders"],
        "secondary_muscles": ["Core", "Legs"],
        "instructions": ["Start with sandbag on ground", "Explosively lift to one shoulder", "Lower and repeat"]
    },
    {
        "id": "EXERCISE:ZERCHER_CARRY",
        "name": "Zercher Carry",
        "category": "Strongman",
        "force_type": "Pull",
        "level": "Intermediate",
        "mechanic": "Compound",
        "equipment": "Barbell",
        "primary_muscles": ["Forearms", "Core"],
        "secondary_muscles": ["Quadriceps", "Upper Back"],
        "instructions": ["Hold barbell in crook of elbows", "Walk forward", "Maintain upright posture"]
    },
    {
        "id": "EXERCISE:GOBLET_SQUAT",
        "name": "Goblet Squat",
        "category": "Strength",
        "force_type": "Push",
        "level": "Beginner",
        "mechanic": "Compound",
        "equipment": "Kettlebell",
        "primary_muscles": ["Quadriceps"],
        "secondary_muscles": ["Glutes", "Core"],
        "instructions": ["Hold kettlebell at chest", "Squat down keeping chest up", "Drive through heels to stand"]
    },
    {
        "id": "EXERCISE:RENEGADE_ROW",
        "name": "Renegade Row",
        "category": "Strength",
        "force_type": "Pull",
        "level": "Intermediate",
        "mechanic": "Compound",
        "equipment": "Dumbbell",
        "primary_muscles": ["Lats", "Core"],
        "secondary_muscles": ["Rhomboids", "Shoulders"],
        "instructions": ["Start in push-up position with hands on dumbbells", "Row one dumbbell to hip", "Alternate sides maintaining plank"]
    },
]


def add_exercise(graph: ArnoldGraph, exercise: dict) -> bool:
    """Add a single exercise to the graph."""

    # Check if already exists
    result = graph.execute_query(
        "MATCH (e:Exercise {id: $id}) RETURN count(e) as count",
        {"id": exercise["id"]}
    )

    if result and result[0]["count"] > 0:
        return False  # Already exists

    # Create node
    query = """
    CREATE (e:Exercise {
        id: $id,
        name: $name,
        category: $category,
        level: $level,
        mechanic: $mechanic,
        equipment: $equipment,
        primary_muscles: $primary_muscles,
        secondary_muscles: $secondary_muscles,
        instructions: $instructions
    })
    """

    params = {
        "id": exercise["id"],
        "name": exercise["name"],
        "category": exercise.get("category"),
        "level": exercise.get("level"),
        "mechanic": exercise.get("mechanic"),
        "equipment": exercise.get("equipment"),
        "primary_muscles": exercise.get("primary_muscles", []),
        "secondary_muscles": exercise.get("secondary_muscles", []),
        "instructions": exercise.get("instructions", [])
    }

    if "force_type" in exercise:
        query = query.replace("instructions: $instructions",
                              "instructions: $instructions, force_type: $force_type")
        params["force_type"] = exercise["force_type"]

    graph.execute_write(query, params)

    return True


def main():
    print("=" * 60)
    print("SKYNET-READER: Add Missing Exercises")
    print("=" * 60)

    # Connect to graph
    print("\nConnecting to CYBERDYNE-CORE...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Add exercises
    print(f"\nAdding {len(MISSING_EXERCISES)} missing exercises...")

    added = 0
    skipped = 0

    for ex in MISSING_EXERCISES:
        if add_exercise(graph, ex):
            print(f"  ✓ Added: {ex['name']}")
            added += 1
        else:
            print(f"  ⊘ Skipped (exists): {ex['name']}")
            skipped += 1

    print("\n" + "=" * 60)
    print(f"Added: {added}")
    print(f"Skipped: {skipped}")
    print("=" * 60)

    graph.close()


if __name__ == "__main__":
    main()
