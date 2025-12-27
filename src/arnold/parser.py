"""
Workout log parsing utilities.

Internal Codename: SKYNET-READER
"I'll read everything. I'll learn your patterns. I'll be back... with insights."
"""

import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import date
import yaml


def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """
    Extract YAML frontmatter and body from markdown content.

    Returns:
        (frontmatter_dict, body_content)
    """
    # Match YAML frontmatter between ---
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = match.group(2)

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        return frontmatter or {}, body
    except yaml.YAMLError as e:
        print(f"Warning: Failed to parse YAML frontmatter: {e}")
        return {}, body


def parse_set_notation(sets_text: str) -> List[Dict[str, Any]]:
    """
    Parse various set notation formats.

    Examples:
        "135×1, 225×1, 315×2" → [{"weight": 135, "reps": 1}, ...]
        "3×5" → [{"sets": 3, "reps": 5}]
        "3/side" → [{"reps": "3/side", "unilateral": True}]
        "3:00" → [{"duration": "3:00", "duration_seconds": 180}]
        "12" → [{"reps": 12, "weight": "bodyweight"}]
    """
    results = []

    # Clean up whitespace
    sets_text = sets_text.strip()

    # Duration pattern (MM:SS)
    duration_match = re.match(r'^(\d+):(\d+)$', sets_text)
    if duration_match:
        minutes = int(duration_match.group(1))
        seconds = int(duration_match.group(2))
        return [{
            "duration": sets_text,
            "duration_seconds": minutes * 60 + seconds
        }]

    # Per side pattern
    per_side_match = re.match(r'^(\d+)\s*/\s*side', sets_text, re.IGNORECASE)
    if per_side_match:
        return [{
            "reps": f"{per_side_match.group(1)}/side",
            "unilateral": True
        }]

    # Split by commas for multiple sets
    set_parts = [s.strip() for s in sets_text.split(',')]

    for part in set_parts:
        # Weight × Reps (e.g., "135×1", "225x5")
        weight_reps_match = re.match(r'(\d+(?:\.\d+)?)\s*[×x]\s*(\d+)', part)
        if weight_reps_match:
            results.append({
                "weight": float(weight_reps_match.group(1)),
                "reps": int(weight_reps_match.group(2))
            })
            continue

        # Sets × Reps (e.g., "3×5")
        sets_reps_match = re.match(r'^(\d+)\s*[×x]\s*(\d+)$', part)
        if sets_reps_match:
            sets_count = int(sets_reps_match.group(1))
            reps_count = int(sets_reps_match.group(2))
            # Expand into multiple sets
            for _ in range(sets_count):
                results.append({"reps": reps_count, "weight": "bodyweight"})
            continue

        # Just a number (reps only)
        reps_only_match = re.match(r'^\d+$', part)
        if reps_only_match:
            results.append({
                "reps": int(part),
                "weight": "bodyweight"
            })
            continue

    return results if results else [{"raw": sets_text}]


def extract_weight_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract weight from exercise name or description.

    Examples:
        "KB Swings (60 lb)" → {"weight": 60, "unit": "lb"}
        "sandbag_100lb" → {"weight": 100, "unit": "lb"}
        "Deadlift (straight bar)" → None
    """
    # Pattern for weight in parentheses: (60 lb)
    paren_match = re.search(r'\((\d+(?:\.\d+)?)\s*(lb|kg)\)', text, re.IGNORECASE)
    if paren_match:
        return {
            "weight": float(paren_match.group(1)),
            "unit": paren_match.group(2).lower()
        }

    # Pattern for weight with underscore: sandbag_100lb
    underscore_match = re.search(r'_(\d+(?:\.\d+)?)(lb|kg)', text, re.IGNORECASE)
    if underscore_match:
        return {
            "weight": float(underscore_match.group(1)),
            "unit": underscore_match.group(2).lower()
        }

    return None


def parse_exercise_from_text(text: str) -> Dict[str, Any]:
    """
    Parse exercise information from a text line.

    Handles various formats from workout logs.
    """
    exercise = {
        "name_raw": text.strip(),
        "notes": None,
        "sets": [],
        "weight": None
    }

    # Extract weight from exercise name
    weight_info = extract_weight_from_text(text)
    if weight_info:
        exercise["weight"] = weight_info["weight"]
        exercise["weight_unit"] = weight_info["unit"]

    return exercise


def parse_workout_section(section_text: str, section_name: str) -> List[Dict[str, Any]]:
    """
    Parse a workout section (Warm-Up, Main, Cooldown, etc.).

    Returns list of exercises found in the section.
    """
    exercises = []
    lines = section_text.strip().split('\n')

    current_exercise = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Numbered list item (exercise)
        numbered_match = re.match(r'^\d+\.\s+\*\*(.+?)\*\*', line)
        if numbered_match:
            if current_exercise:
                exercises.append(current_exercise)
            current_exercise = parse_exercise_from_text(numbered_match.group(1))
            current_exercise["order"] = len(exercises) + 1
            continue

        # Bullet point (sub-item or exercise detail)
        if line.startswith('-') or line.startswith('*'):
            # Remove leading dash/asterisk
            content = re.sub(r'^[-*]\s+', '', line)

            # Check if it's a detail line (Reps:, Load:, Notes:, Duration:)
            detail_match = re.match(r'\*\*(.+?):\*\*\s*(.+)', content)
            if detail_match and current_exercise:
                key = detail_match.group(1).lower().strip()
                value = detail_match.group(2).strip()

                if key == 'reps':
                    current_exercise["sets"] = parse_set_notation(value)
                elif key == 'load':
                    # Extract weight from load description
                    weight_info = extract_weight_from_text(value)
                    if weight_info:
                        current_exercise["weight"] = weight_info["weight"]
                        current_exercise["weight_unit"] = weight_info["unit"]
                    else:
                        current_exercise["load"] = value
                elif key == 'duration':
                    duration_sets = parse_set_notation(value)
                    if duration_sets:
                        current_exercise["sets"] = duration_sets
                elif key == 'notes':
                    current_exercise["notes"] = value
            else:
                # It's a standalone exercise
                if current_exercise:
                    exercises.append(current_exercise)
                current_exercise = parse_exercise_from_text(content)
                current_exercise["order"] = len(exercises) + 1

    # Add last exercise
    if current_exercise:
        exercises.append(current_exercise)

    return exercises


def parse_workout_body(body: str) -> List[Dict[str, Any]]:
    """
    Parse the markdown body to extract workout sections and exercises.

    Returns list of sections with their exercises.
    """
    sections = []

    # Split by ## headers (sections)
    section_pattern = r'\*\*(.+?):\*\*\s*\n(.*?)(?=\n\*\*[^:]+:\*\*|\Z)'
    matches = re.findall(section_pattern, body, re.DOTALL)

    for section_name, section_content in matches:
        section_name = section_name.strip()

        # Skip meta sections
        if section_name.lower() in ['overview', 'perceived effort', 'summary / day notes', 'day notes']:
            continue

        exercises = parse_workout_section(section_content, section_name)

        if exercises:
            sections.append({
                "name": section_name,
                "exercises": exercises
            })

    return sections


def parse_workout_file(filepath: Path) -> Dict[str, Any]:
    """
    Parse a complete workout markdown file.

    Args:
        filepath: Path to workout .md file

    Returns:
        Dictionary with parsed workout data
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)
    sections = parse_workout_body(body)

    # Calculate totals
    total_exercises = sum(len(s["exercises"]) for s in sections)
    total_sets = sum(
        len(ex.get("sets", []))
        for s in sections
        for ex in s["exercises"]
    )

    return {
        "filepath": str(filepath),
        "filename": filepath.name,
        "frontmatter": frontmatter,
        "sections": sections,
        "metadata": {
            "total_sections": len(sections),
            "total_exercises": total_exercises,
            "total_sets": total_sets
        }
    }


def normalize_exercise_name(name: str) -> str:
    """
    Normalize exercise name for matching.

    - Lowercase
    - Remove parentheticals
    - Strip whitespace
    - Replace multiple spaces with single space
    """
    # Remove parentheticals
    name = re.sub(r'\([^)]*\)', '', name)

    # Lowercase and strip
    name = name.lower().strip()

    # Replace multiple spaces
    name = re.sub(r'\s+', ' ', name)

    return name
