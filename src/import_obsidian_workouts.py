#!/usr/bin/env python3
"""
Import Brock's Obsidian workout logs into Neo4j.
Handles his narrative workout card format with circuits, complexes, and varied notation.
"""

import os
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('/Users/brock/Documents/GitHub/arnold/.env')

# Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")


class ObsidianWorkoutImporter:
    """Import Brock's workout logs to Neo4j."""
    
    def __init__(self, workout_dir: Path):
        self.workout_dir = Path(workout_dir)
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.stats = {
            'files_found': 0,
            'files_parsed': 0,
            'files_skipped': 0,
            'workouts_created': 0,
            'exercises_matched': 0,
            'exercises_unmatched': 0
        }
        
    def find_workout_files(self) -> List[Path]:
        """Find all workout markdown files."""
        if not self.workout_dir.exists():
            print(f"❌ Workout directory not found: {self.workout_dir}")
            return []
        
        # Look for .md files with dates in the filename
        files = [f for f in self.workout_dir.glob("*.md") 
                if re.match(r'\d{4}-\d{2}-\d{2}', f.name)]
        self.stats['files_found'] = len(files)
        return sorted(files)
    
    def parse_obsidian_workout(self, filepath: Path) -> Optional[Dict]:
        """
        Parse Brock's workout formats (both YAML and Markdown).

        Format 1 (Pure YAML):
        date: 2025-04-08
        main_workout:
          - exercise_name:
              sets: [...]

        Format 2 (YAML Frontmatter + Markdown):
        ---
        date: 2025-11-10
        type: strength
        ---
        ### 1) Deadlift
        - **135×1**, **225×1**
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Detect format
            if content.startswith('---'):
                # Format 2: YAML frontmatter + Markdown
                return self._parse_markdown_format(content, filepath)
            else:
                # Format 1: Pure YAML
                return self._parse_yaml_format(content, filepath)

        except Exception as e:
            print(f"Error parsing {filepath.name}: {e}")
            return None

    def _parse_markdown_format(self, content: str, filepath: Path) -> Optional[Dict]:
        """Parse Format 2: YAML frontmatter + Markdown body."""

        # CRITICAL: Extract date from FILENAME, not YAML (YAML may have wrong dates from ChatGPT)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
        if not date_match:
            return None
        workout_date = date_match.group(1)

        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        frontmatter = yaml.safe_load(parts[1])
        body = parts[2].strip()

        # Remove additional --- separator that sometimes appears after frontmatter
        if body.startswith('---'):
            body = body[3:].strip()

        # Parse exercises from markdown
        exercises = self._parse_exercises(body)

        if not exercises:
            return None

        return {
            'date': str(workout_date),
            'type': frontmatter.get('type', 'strength'),
            'duration_minutes': frontmatter.get('total_time_min'),
            'notes': str(frontmatter.get('deviations', '')),
            'tags': frontmatter.get('tags', []),
            'equipment': frontmatter.get('equipment_used', []),
            'exercises': exercises
        }

    def _parse_yaml_format(self, content: str, filepath: Path) -> Optional[Dict]:
        """Parse Format 1: Pure YAML structure."""

        # CRITICAL: Extract date from FILENAME, not YAML (YAML may have wrong dates from ChatGPT)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
        if not date_match:
            return None
        workout_date = date_match.group(1)

        # Pre-process to fix common YAML issues
        # Fix Obsidian hashtags in flow sequences: [#tag, ...] -> ["tag", ...]
        # Match #word or #word-word and replace with quoted version
        content = re.sub(r'#([\w-]+)', r'"\1"', content)

        data = yaml.safe_load(content)

        if not data or not isinstance(data, dict):
            return None

        # Extract exercises from main_workout, warmup, finisher sections
        exercises = []

        for section_name in ['warmup', 'main_workout', 'finisher']:
            section = data.get(section_name)
            if section and isinstance(section, list):
                exercises.extend(self._parse_yaml_exercises(section))

        if not exercises:
            return None

        return {
            'date': str(workout_date),
            'type': data.get('type', 'workout'),
            'duration_minutes': data.get('total_time_min'),
            'notes': data.get('goal', ''),
            'tags': data.get('tags', []),
            'equipment': [],
            'exercises': exercises
        }

    def _parse_yaml_exercises(self, section: List) -> List[Dict]:
        """Parse exercises from YAML structure."""
        exercises = []

        for item in section:
            if isinstance(item, dict):
                # Each item is {exercise_name: {sets: [...], reps: ..., weight: ...}}
                for ex_name, ex_data in item.items():
                    if isinstance(ex_data, dict):
                        sets = self._parse_yaml_sets(ex_data)
                        if sets:
                            exercises.append({
                                'exercise_name': ex_name.replace('_', ' ').title(),
                                'sets': sets
                            })
            elif isinstance(item, str):
                # Simple string like "spiderman_lunges: 5/side"
                if ':' in item:
                    parts = item.split(':', 1)
                    ex_name = parts[0].strip()
                    # Parse the value as a set
                    set_data = self._parse_set_notation(parts[1].strip())
                    if set_data:
                        exercises.append({
                            'exercise_name': ex_name.replace('_', ' ').title(),
                            'sets': [set_data]
                        })

        return exercises

    def _parse_yaml_sets(self, ex_data: Dict) -> List[Dict]:
        """Parse sets from YAML exercise data."""
        sets = []

        # Check for explicit 'sets' array
        if 'sets' in ex_data:
            sets_data = ex_data['sets']

            if isinstance(sets_data, list):
                # Format: sets: ["5/side @ 100lbs", "4/side @ 130lbs"]
                for set_item in sets_data:
                    if isinstance(set_item, str):
                        set_data = self._parse_set_notation(set_item)
                        if set_data:
                            sets.append(set_data)
                    elif isinstance(set_item, dict):
                        # Already structured
                        sets.append(set_item)
            elif isinstance(sets_data, (int, str)):
                # Format: sets: 3, reps: 8, weight: 35lb
                num_sets = int(sets_data) if isinstance(sets_data, int) else 1

                # Build set from other fields
                base_set = {
                    'reps': None,
                    'load_lbs': None,
                    'duration_seconds': None,
                    'distance_miles': None,
                    'notes': None
                }

                # Extract reps
                if 'reps' in ex_data:
                    base_set['reps'] = int(ex_data['reps'])
                elif 'reps_per_side' in ex_data:
                    base_set['reps'] = int(ex_data['reps_per_side'])
                    base_set['notes'] = 'per side'

                # Extract load
                if 'weight' in ex_data:
                    weight_str = str(ex_data['weight'])
                    load = self._extract_load(weight_str)
                    if load:
                        base_set['load_lbs'] = load

                # Extract duration
                if 'duration' in ex_data:
                    duration_str = str(ex_data['duration'])
                    seconds = self._extract_duration(duration_str)
                    if seconds:
                        base_set['duration_seconds'] = seconds
                elif 'weighted_duration' in ex_data:
                    duration_str = str(ex_data['weighted_duration'])
                    seconds = self._extract_duration(duration_str)
                    if seconds:
                        base_set['duration_seconds'] = seconds

                # Extract distance
                if 'steps' in ex_data:
                    base_set['reps'] = int(ex_data['steps'])
                    base_set['notes'] = 'steps'

                # Create sets
                for _ in range(num_sets):
                    sets.append(base_set.copy())

        return sets

    def _extract_load(self, weight_str: str) -> Optional[float]:
        """Extract load in pounds from weight string."""
        # Match patterns like "100lbs", "35lb dumbbells", "50lbs"
        match = re.search(r'([\d.]+)\s*lbs?', weight_str, re.IGNORECASE)
        if match:
            return float(match.group(1))

        # Match just numbers
        match = re.search(r'^([\d.]+)$', weight_str)
        if match:
            return float(match.group(1))

        return None

    def _extract_duration(self, duration_str: str) -> Optional[int]:
        """Extract duration in seconds from duration string."""
        # Match "1 min @ 50lbs" or "30 sec"
        match = re.search(r'([\d.]+)\s*min', duration_str, re.IGNORECASE)
        if match:
            return int(float(match.group(1)) * 60)

        match = re.search(r'([\d.]+)\s*sec', duration_str, re.IGNORECASE)
        if match:
            return int(float(match.group(1)))

        return None
    
    def _parse_exercises(self, body: str) -> List[Dict]:
        """Parse exercises from narrative workout card."""
        exercises = []
        current_exercise = None
        current_sets = []
        
        lines = body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for exercise header
            exercise_name = self._extract_exercise_name(line)
            
            if exercise_name:
                # Save previous exercise
                if current_exercise and current_sets:
                    exercises.append({
                        'exercise_name': current_exercise,
                        'sets': current_sets
                    })
                
                # Start new exercise
                current_exercise = exercise_name
                current_sets = []
                
                # Check if sets are on the same line
                inline_sets = self._extract_inline_sets(line)
                if inline_sets:
                    current_sets.extend(inline_sets)
                
                continue
            
            # Parse set lines
            if current_exercise:
                set_list = self._parse_set_line(line)
                if set_list:
                    current_sets.extend(set_list)
        
        # Save last exercise
        if current_exercise and current_sets:
            exercises.append({
                'exercise_name': current_exercise,
                'sets': current_sets
            })
        
        return exercises
    
    def _extract_exercise_name(self, line: str) -> Optional[str]:
        """Extract exercise name from various header formats."""
        # Pattern 1: ### 1) Exercise Name (stuff)
        match = re.search(r'###\s*\d*\)?\s*(.+?)(?:\s*\(|$)', line)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: 1. **Exercise Name**
        match = re.search(r'^\d+\.\s*\*\*(.+?)\*\*', line)
        if match:
            return match.group(1).strip()
        
        # Pattern 3: **Exercise Name:**
        match = re.search(r'^\*\*(.+?)\*\*:', line)
        if match:
            return match.group(1).strip()
        
        return None
    
    def _extract_inline_sets(self, line: str) -> List[Dict]:
        """Extract sets from same line as exercise header."""
        sets = []
        
        # Look for bold notation: **135×1**, **225×1**
        if '**' in line and '×' in line:
            bold_items = re.findall(r'\*\*([^*]+?)\*\*', line)
            for item in bold_items:
                if '×' in item:
                    set_data = self._parse_set_notation(item)
                    if set_data:
                        sets.append(set_data)
        
        return sets
    
    def _parse_set_line(self, line: str) -> List[Dict]:
        """Parse a line that contains set information."""
        sets = []
        
        # Remove leading dash if present
        if line.startswith('-'):
            line = line[1:].strip()
        
        # Check for inline bold sets: **135×1**, **225×1**
        if '**' in line:
            bold_items = re.findall(r'\*\*([^*]+?)\*\*', line)
            for item in bold_items:
                set_data = self._parse_set_notation(item)
                if set_data:
                    sets.append(set_data)
        
        # Check for arrow-separated progressions: 100 lb × 3/side → 130 lb × 3/side
        elif '→' in line:
            parts = line.split('→')
            for part in parts:
                set_data = self._parse_set_notation(part.strip())
                if set_data:
                    sets.append(set_data)
        
        # Regular set notation
        else:
            set_data = self._parse_set_notation(line)
            if set_data:
                sets.append(set_data)
        
        return sets
    
    def _parse_set_notation(self, notation: str) -> Optional[Dict]:
        """
        Parse Brock's set notation.
        
        Formats:
        - 135×1 (load × reps)
        - 100 lb × 3/side
        - BW × 10
        - 40 steps
        - 3:00 (duration)
        """
        set_data = {
            'reps': None,
            'load_lbs': None,
            'duration_seconds': None,
            'distance_miles': None,
            'notes': None
        }
        
        notation = notation.strip()
        
        # Pattern: 135×1 or 135 × 1
        match = re.search(r'([\d.]+)\s*[×x]\s*([\d.]+)(?:/side)?', notation, re.IGNORECASE)
        if match:
            load = float(match.group(1))
            reps = float(match.group(2))
            set_data['load_lbs'] = load
            set_data['reps'] = int(reps)
            if '/side' in notation.lower():
                set_data['notes'] = 'per side'
            return set_data
        
        # Pattern: 100 lb × 3/side
        match = re.search(r'([\d.]+)\s*lbs?\s*[×x]\s*([\d.]+)(?:/side)?', notation, re.IGNORECASE)
        if match:
            load = float(match.group(1))
            reps = float(match.group(2))
            set_data['load_lbs'] = load
            set_data['reps'] = int(reps)
            if '/side' in notation.lower():
                set_data['notes'] = 'per side'
            return set_data
        
        # Pattern: BW × 10
        match = re.search(r'BW\s*[×x]\s*([\d.]+)', notation, re.IGNORECASE)
        if match:
            set_data['reps'] = int(float(match.group(1)))
            return set_data
        
        # Pattern: 40 steps
        match = re.search(r'([\d.]+)\s*steps?', notation, re.IGNORECASE)
        if match:
            set_data['reps'] = int(float(match.group(1)))
            set_data['notes'] = 'steps'
            return set_data
        
        # Pattern: 3:00 or 3 min
        match = re.search(r'([\d.]+):(\d+)', notation)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            set_data['duration_seconds'] = minutes * 60 + seconds
            return set_data
        
        match = re.search(r'([\d.]+)\s*min', notation, re.IGNORECASE)
        if match:
            set_data['duration_seconds'] = int(float(match.group(1)) * 60)
            return set_data
        
        return None
    
    def match_exercise_to_variant(self, exercise_name: str) -> Optional[str]:
        """Match exercise to ExerciseVariant or Activity."""
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # Clean exercise name (remove parenthetical notes)
            clean_name = re.sub(r'\([^)]+\)', '', exercise_name).strip()
            
            # Try exact match
            result = session.run("""
                MATCH (v:ExerciseVariant)
                WHERE toLower(v.name) = toLower($name)
                RETURN v.id as id
                LIMIT 1
            """, name=clean_name)
            
            record = result.single()
            if record:
                return record['id']
            
            # Try fuzzy match
            result = session.run("""
                MATCH (v:ExerciseVariant)
                WHERE toLower(v.name) CONTAINS toLower($name)
                   OR toLower($name) CONTAINS toLower(v.name)
                RETURN v.id as id, v.name as name
                LIMIT 1
            """, name=clean_name)
            
            record = result.single()
            if record:
                return record['id']
            
            # Try Activity
            result = session.run("""
                MATCH (a:Activity)
                WHERE toLower(a.name) = toLower($name)
                   OR toLower($name) CONTAINS toLower(a.name)
                RETURN a.id as id
                LIMIT 1
            """, name=clean_name)
            
            record = result.single()
            if record:
                return record['id']
            
            return None
    
    def create_or_get_exercise(self, exercise_name: str) -> str:
        """Create user exercise or get existing one."""
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MERGE (ex:Exercise {name: $name, source: 'user'})
                ON CREATE SET ex.id = randomUUID(), ex.created_at = datetime()
                RETURN ex.id as id
            """, name=exercise_name)
            
            return result.single()['id']
    
    def import_workout(self, workout_data: Dict) -> bool:
        """Import workout to Neo4j."""
        try:
            with self.driver.session(database=NEO4J_DATABASE) as session:
                # Check if exists
                exists = session.run("""
                    MATCH (w:Workout {date: date($date)})
                    RETURN count(w) > 0 as exists
                """, date=workout_data['date']).single()['exists']
                
                if exists:
                    self.stats['files_skipped'] += 1
                    return False
                
                # Create workout
                workout_id = session.run("""
                    CREATE (w:Workout {
                        id: randomUUID(),
                        date: date($date),
                        type: $type,
                        duration_minutes: $duration,
                        notes: $notes,
                        source: 'obsidian_import',
                        imported_at: datetime()
                    })
                    RETURN w.id as id
                """, 
                    date=workout_data['date'],
                    type=workout_data['type'],
                    duration=workout_data['duration_minutes'],
                    notes=str(workout_data['notes'])
                ).single()['id']
                
                # Process exercises
                for ex_data in workout_data['exercises']:
                    exercise_name = ex_data['exercise_name']
                    variant_id = self.match_exercise_to_variant(exercise_name)
                    
                    if variant_id:
                        self.stats['exercises_matched'] += 1
                        exercise_id = self.create_or_get_exercise(exercise_name)
                        
                        # Create MAPS_TO
                        session.run("""
                            MATCH (ex:Exercise {id: $ex_id})
                            MATCH (v {id: $variant_id})
                            MERGE (ex)-[r:MAPS_TO]->(v)
                            ON CREATE SET r.confidence = 0.8, r.match_type = 'AUTO'
                        """, ex_id=exercise_id, variant_id=variant_id)
                    else:
                        self.stats['exercises_unmatched'] += 1
                        exercise_id = self.create_or_get_exercise(exercise_name)
                    
                    # Create sets
                    for idx, set_data in enumerate(ex_data['sets'], 1):
                        session.run("""
                            MATCH (w:Workout {id: $workout_id})
                            MATCH (ex:Exercise {id: $exercise_id})
                            CREATE (s:Set {
                                id: randomUUID(),
                                set_number: $set_number,
                                reps: $reps,
                                load_lbs: $load_lbs,
                                duration_seconds: $duration_seconds,
                                distance_miles: $distance_miles,
                                notes: $notes
                            })
                            CREATE (w)-[:CONTAINS]->(s)
                            CREATE (s)-[:OF_EXERCISE]->(ex)
                        """,
                            workout_id=workout_id,
                            exercise_id=exercise_id,
                            set_number=idx,
                            **set_data
                        )
                
                self.stats['workouts_created'] += 1
                return True
                
        except Exception as e:
            print(f"  ❌ Error importing: {e}")
            return False
    
    def run_import(self, limit: Optional[int] = None, dry_run: bool = False):
        """Run import process."""
        print("=" * 80)
        print("OBSIDIAN WORKOUT IMPORT")
        print("=" * 80)
        print(f"\nScanning: {self.workout_dir}")
        
        files = self.find_workout_files()
        
        if not files:
            print("\n❌ No workout files found")
            return
        
        print(f"Found {len(files)} workout files")
        
        if dry_run:
            print("\n🔍 DRY RUN - Parsing first file as example:\n")
            if files:
                workout = self.parse_obsidian_workout(files[0])
                if workout:
                    import json
                    print(json.dumps(workout, indent=2, default=str))
                else:
                    print("❌ Failed to parse")
            return
        
        if limit:
            files = files[:limit]
            print(f"Limiting to first {limit} files")
        
        print("\nImporting...\n")
        
        for filepath in tqdm(files, desc="Processing"):
            workout_data = self.parse_obsidian_workout(filepath)
            
            if workout_data:
                self.stats['files_parsed'] += 1
                self.import_workout(workout_data)
            else:
                self.stats['files_skipped'] += 1
        
        self.print_summary()
    
    def print_summary(self):
        """Print summary."""
        print("\n" + "=" * 80)
        print("IMPORT SUMMARY")
        print("=" * 80)
        print(f"\nFiles found:       {self.stats['files_found']}")
        print(f"Files parsed:      {self.stats['files_parsed']}")
        print(f"Files skipped:     {self.stats['files_skipped']}")
        print(f"Workouts created:  {self.stats['workouts_created']}")
        print(f"\nExercises matched:   {self.stats['exercises_matched']}")
        print(f"Exercises unmatched: {self.stats['exercises_unmatched']}")
        
        if self.stats['exercises_unmatched'] > 0:
            print("\n⚠️  Run exercise matcher to map unmatched exercises:")
            print("   python map_exercises.py")
    
    def close(self):
        """Close Neo4j connection."""
        self.driver.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Import Obsidian workouts')
    parser.add_argument('--dir', required=True, help='Workout directory')
    parser.add_argument('--limit', type=int, help='Limit number of files')
    parser.add_argument('--dry-run', action='store_true', help='Parse without importing')
    
    args = parser.parse_args()
    
    importer = ObsidianWorkoutImporter(workout_dir=args.dir)
    
    try:
        importer.run_import(limit=args.limit, dry_run=args.dry_run)
    finally:
        importer.close()


if __name__ == "__main__":
    main()
