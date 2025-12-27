"""
LLM-Powered Workout Ingestion

Uses OpenAI API to intelligently parse workout logs into structured data.
No regex. No fuzzy matching libraries. Just AI doing what it does best.

Internal Codename: SKYNET-READER 2.0
"I'll read everything. I'll understand context. I'll be back... with perfect data."
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import date
import time

from openai import OpenAI


class LLMWorkoutParser:
    """
    Intelligent workout parser using OpenAI's reasoning models.

    Handles:
    - Free-form exercise notation
    - Compound exercise lines
    - Combat/custom exercises
    - Context-aware exercise matching
    - Set/rep/weight extraction
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize LLM parser.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self.model = "gpt-5-mini"  # MoE model - no temperature settings

    def parse_workout(
        self,
        workout_markdown: str,
        exercise_database: List[Dict[str, str]],
        workout_filename: str = ""
    ) -> Dict[str, Any]:
        """
        Parse workout markdown into structured JSON using LLM.

        Args:
            workout_markdown: Raw markdown content from workout file
            exercise_database: List of canonical exercises for matching
            workout_filename: Original filename for context

        Returns:
            Structured workout data with exercises, sets, metadata
        """

        # Build comprehensive prompt
        prompt = self._build_parsing_prompt(
            workout_markdown,
            exercise_database,
            workout_filename
        )

        # Call OpenAI API with structured output
        # NOTE: gpt-5-mini is MoE - NO temperature parameter!
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"}
            )

            # Parse response
            parsed_json = json.loads(response.choices[0].message.content)

            # Validate and post-process
            validated = self._validate_parsed_data(parsed_json)

            return validated

        except Exception as e:
            print(f"Error parsing workout: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """Get system prompt for workout parsing."""
        return """You are an expert workout log parser with deep knowledge of strength training, combat sports, and exercise science.

Your task: Parse workout logs into perfectly structured JSON data.

Key skills:
- Recognize exercise name variations (e.g., "KB swings" → "Kettlebell Swing")
- Match exercises to canonical database (fuzzy matching)
- Extract sets, reps, weight from various notations (3×15, 135×5, 8/side, 4 min)
- Split compound exercise lines (multiple exercises in one bullet)
- Identify custom/combat exercises not in standard databases
- Infer missing data (e.g., "bodyweight squats" → weight: "bodyweight")
- Calculate total volume (weight × reps × sets)
- Preserve all context and notes

Return ONLY valid JSON. No markdown, no explanations."""

    def _build_parsing_prompt(
        self,
        workout_markdown: str,
        exercise_database: List[Dict[str, str]],
        filename: str
    ) -> str:
        """Build the parsing prompt with context."""

        # Sample a subset of exercise database for context
        db_sample = exercise_database[:100] if len(exercise_database) > 100 else exercise_database

        prompt = f"""Parse this workout log into structured JSON.

WORKOUT FILE: {filename}

WORKOUT LOG:
```markdown
{workout_markdown}
```

CANONICAL EXERCISE DATABASE (sample of {len(exercise_database)} total):
```json
{json.dumps(db_sample, indent=2)}
```

PARSING INSTRUCTIONS:

1. Extract YAML frontmatter:
   - date (YYYY-MM-DD format)
   - tags (list)
   - goals (list)
   - periodization_phase
   - equipment_used
   - muscle_focus
   - deviations
   - perceived_intensity
   - any other metadata

2. Extract ALL exercises from the workout body:
   - Parse exercise name from markdown (usually bold: **Exercise Name**)
   - Match to canonical exercise DB (fuzzy match if needed, use exercise ID)
   - If compound line (multiple exercises), SPLIT into separate exercises
   - If combat/mobility move not in DB, mark as custom exercise
   - Extract weight (with units: lbs, kg, bodyweight)
   - Extract sets and reps (handle formats: 3×15, 135×5, 8/side, 4 min, 50 steps)
   - Create Set objects for EACH set with weight/reps/volume
   - Calculate volume per set: weight × reps (if weight is numeric)

3. Handle special formats:
   - Circuits: Identify circuit structure and order
   - Rounds: Extract round count
   - Time-based: Store duration instead of reps
   - Distance: Store distance (steps, meters)
   - Unilateral: Mark as /side
   - Warmup/Cooldown: Tag appropriately

4. Volume calculations:
   - Per set: weight × reps
   - Per exercise: sum of all set volumes
   - Total workout: sum of all exercise volumes

5. Exercise matching rules:
   - Exact match first (case-insensitive)
   - Fuzzy match if close (e.g., "KB swings" → "Kettlebell Swing")
   - If no match and clearly a combat/mobility/custom move, create custom entry
   - Use movement pattern inference (e.g., if mentions "squat", likely a squat variant)

REQUIRED JSON SCHEMA:

{{
  "date": "YYYY-MM-DD",
  "source_file": "filename.md",
  "metadata": {{
    "tags": ["tag1", "tag2"],
    "goals": ["goal1", "goal2"],
    "periodization_phase": "build_week_2",
    "equipment_used": ["equipment1"],
    "muscle_focus": ["muscle1"],
    "energy_systems": ["aerobic"],
    "deviations": ["deviation1"],
    "perceived_intensity": "moderate",
    "intended_intensity": "moderate"
  }},
  "exercises": [
    {{
      "name": "Kettlebell Swing",
      "canonical_id": "EXERCISE:Kettlebell_Swing",  // Use ID from database
      "canonical_name": "Kettlebell Swing",  // Matched name
      "is_custom": false,  // true if not in database
      "category": "strength",  // from DB or inferred
      "equipment": "kettlebell",
      "order_in_workout": 1,
      "sets": [
        {{
          "set_number": 1,
          "weight": 35,
          "weight_unit": "lbs",
          "reps": 15,
          "volume": 525,  // weight × reps
          "rpe": null,  // if available
          "notes": ""
        }},
        {{
          "set_number": 2,
          "weight": 35,
          "weight_unit": "lbs",
          "reps": 15,
          "volume": 525
        }},
        {{
          "set_number": 3,
          "weight": 35,
          "weight_unit": "lbs",
          "reps": 15,
          "volume": 525
        }}
      ],
      "total_sets": 3,
      "total_reps": 45,
      "total_volume": 1575,
      "notes": "Felt strong"
    }},
    {{
      "name": "Jab-Cross Combo",
      "canonical_id": null,  // Not in DB
      "canonical_name": null,
      "is_custom": true,
      "category": "combat",
      "equipment": "punching_bag",
      "order_in_workout": 2,
      "sets": [
        {{
          "set_number": 1,
          "duration_seconds": 240,  // 4 minutes
          "duration_display": "4 min",
          "notes": "Technical focus"
        }}
      ],
      "total_sets": 1,
      "is_time_based": true,
      "notes": "Combat drill"
    }}
  ],
  "workout_structure": {{
    "warmup": ["exercise names"],
    "main_work": ["exercise names"],
    "finisher": ["exercise names"],
    "cooldown": ["exercise names"],
    "circuit_structure": null  // or circuit details if applicable
  }},
  "summary": {{
    "total_exercises": 5,
    "total_sets": 15,
    "total_volume": 5000,  // sum of all exercise volumes (lbs)
    "duration_minutes": 60,  // if available
    "perceived_effort": "moderate-high"
  }},
  "notes": "Recovery session. Left side weaker in dead bugs.",
  "parsing_metadata": {{
    "exercises_matched_to_db": 3,
    "custom_exercises_created": 2,
    "parsing_warnings": ["Could not determine reps for Jump Rope"]
  }}
}}

IMPORTANT:
- For compound exercise lines (multiple exercises in one bullet), CREATE SEPARATE EXERCISE OBJECTS
- Expand all sets (e.g., "3×15" → create 3 set objects)
- Calculate volume for ALL sets with numeric weight
- Match exercise names intelligently (typos, abbreviations, synonyms)
- Preserve ALL context in notes fields

Return ONLY the JSON object. No markdown code blocks, no explanations.
"""
        return prompt

    def _validate_parsed_data(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean parsed data.

        Args:
            parsed: Raw parsed JSON from LLM

        Returns:
            Validated and cleaned data
        """
        # Ensure required fields
        if 'date' not in parsed:
            raise ValueError("Missing required field: date")

        if 'exercises' not in parsed:
            parsed['exercises'] = []

        # Validate date format
        try:
            date.fromisoformat(parsed['date'])
        except ValueError:
            raise ValueError(f"Invalid date format: {parsed['date']}")

        # Ensure metadata structure
        if 'metadata' not in parsed:
            parsed['metadata'] = {}

        # Ensure summary structure
        if 'summary' not in parsed:
            parsed['summary'] = {
                'total_exercises': len(parsed.get('exercises', [])),
                'total_sets': 0,
                'total_volume': 0
            }

        # Calculate totals if missing
        total_volume = 0
        total_sets = 0

        for exercise in parsed.get('exercises', []):
            # Ensure sets array exists
            if 'sets' not in exercise:
                exercise['sets'] = []

            # Calculate exercise totals (handle None values)
            exercise_volume = sum(s.get('volume', 0) or 0 for s in exercise['sets'])
            exercise['total_volume'] = exercise_volume
            exercise['total_sets'] = len(exercise['sets'])

            total_volume += exercise_volume
            total_sets += len(exercise['sets'])

        parsed['summary']['total_volume'] = total_volume
        parsed['summary']['total_sets'] = total_sets

        return parsed

    def parse_workout_file(
        self,
        file_path: Path,
        exercise_database: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Parse a workout file.

        Args:
            file_path: Path to workout markdown file
            exercise_database: Canonical exercise database

        Returns:
            Parsed workout data
        """
        # Read file
        content = file_path.read_text(encoding='utf-8')

        # Parse with LLM
        parsed = self.parse_workout(
            content,
            exercise_database,
            file_path.name
        )

        # Add source file to metadata
        parsed['source_file'] = file_path.name

        return parsed


def get_exercise_database_from_graph(graph) -> List[Dict[str, str]]:
    """
    Fetch exercise database from Neo4j for LLM context.

    Args:
        graph: ArnoldGraph instance

    Returns:
        List of exercise dictionaries with id, name, category
    """
    query = """
    MATCH (e:Exercise)
    RETURN
        e.id as id,
        e.name as name,
        e.category as category,
        e.force_type as force_type,
        e.mechanic as mechanic
    ORDER BY e.name
    """

    exercises = graph.execute_query(query)
    return exercises


# Example usage
if __name__ == "__main__":
    # Test parsing
    from arnold.graph import ArnoldGraph

    # Get exercise database
    graph = ArnoldGraph()
    exercise_db = get_exercise_database_from_graph(graph)

    print(f"Loaded {len(exercise_db)} exercises from database")

    # Parse a sample workout
    parser = LLMWorkoutParser()

    sample_file = Path("/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise/2024-12-16_workout.md")

    if sample_file.exists():
        print(f"\nParsing: {sample_file.name}")
        parsed = parser.parse_workout_file(sample_file, exercise_db)

        print("\nParsed data:")
        print(json.dumps(parsed, indent=2))

        print(f"\nSummary:")
        print(f"  Exercises: {parsed['summary']['total_exercises']}")
        print(f"  Sets: {parsed['summary']['total_sets']}")
        print(f"  Volume: {parsed['summary']['total_volume']:,} lbs")

    graph.close()
