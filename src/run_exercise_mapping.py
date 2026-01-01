#!/usr/bin/env python3
"""Map exercises from December 26 workout."""

from map_exercises import map_exercises

# Exercises from 2025-12-26 workout that need mapping
exercises_to_map = [
    ("Light Boxing", "e78206b2-16e6-4a71-8891-acdf8088fccc"),
    ("Sandbag Shoulder (Alternating)", "3dbc4158-7aeb-4f0c-a779-1513d5a3c9ba"),
    ("Seated Quad Extension", "53adfea4-8f9f-4bf6-926d-75602f12ca81"),
    ("Barbell Bench Press", "CANONICAL:FFDB:158"),
    ("Bear Hug Carry", "79b1a81b-3675-4974-a13a-ccea198eb7b5"),
    ("Turkish Get-Up", "fd08129e-deb7-44d8-8be5-10178aeb4453"),
    ("Hanging Knee to Chest Raise", "9549445a-ed18-4ed6-bd7e-de4b8a1d4ffa"),
    ("Ab Wheel Rollout", "a69c2f80-0ebe-4bb6-a3dd-5a127af5a1ed")
]

if __name__ == "__main__":
    print("=" * 80)
    print("MAPPING EXERCISES FROM DECEMBER 26, 2025 WORKOUT")
    print("=" * 80)
    print("\nThis will:")
    print("1. Search 5,000+ canonical exercises for matches")
    print("2. Use LLM to analyze exercise relationships")
    print("3. Create knowledge graph relationships")
    print("4. Inherit muscle group mappings")
    print("\n" + "=" * 80 + "\n")
    
    results = map_exercises(exercise_names=exercises_to_map)
    
    print("\n" + "=" * 80)
    print("✅ EXERCISE MAPPING COMPLETE")
    print("=" * 80)
    print("\nYour workout now has intelligent muscle tracking!")
