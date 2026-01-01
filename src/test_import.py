#!/usr/bin/env python3
"""Test the Obsidian import with Brock's actual workout format."""

import sys
import os

# Add src to path
sys.path.insert(0, '/Users/brock/Documents/GitHub/arnold/src')

from import_obsidian_workouts import ObsidianWorkoutImporter
from pathlib import Path

# Brock's workout directory
WORKOUT_DIR = Path("/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise")

def main():
    print("Testing Obsidian import parser...")
    print(f"Directory: {WORKOUT_DIR}\n")
    
    importer = ObsidianWorkoutImporter(workout_dir=WORKOUT_DIR)
    
    try:
        # Dry run - parse first file
        importer.run_import(limit=1, dry_run=True)
    finally:
        importer.close()

if __name__ == "__main__":
    main()
