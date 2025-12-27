"""
Normalization utilities for workout data.

Internal Codename: SKYNET-READER
Clean and normalize messy workout data.
"""

import re
from typing import List, Optional


# Patterns that indicate this is NOT an exercise
NON_EXERCISE_PATTERNS = [
    r'^Sets?:\s*\d+',  # "Sets: 3", "Set: 1"
    r'^Reps?:\s*\d+',  # "Reps: 10", "Rep: 5"
    r'^Load:',  # "Load: 100lb sandbag"
    r'^Duration:',  # "Duration: 3:00"
    r'^Notes?:',  # "Notes: ..."
    r'^Steps?:',  # "Steps: 50 per set"
    r'^---+$',  # Markdown separator
    r'^\*\*.*cooldown.*\*\*',  # "**No structured cooldown recorded.**"
    r'^\*\*.*stretching.*\*\*',  # "**Stretching Sequence:**"
    r'^\*\*.*rest.*\*\*',  # "**(Rest ~90 Seconds Between Sets)**"
    r'^\*\*.*mobility.*\*\*',  # "**Dynamic Mobility**:"
    r'^\*\*.*warmup.*\*\*',  # "**Warmup:**"
    r'^.*→.*→.*$',  # Sequence indicators "A → B → C"
    r'^\d+:\d+$',  # Just duration "3:00"
    r'^bodyweight$',  # Just "bodyweight"
    r'^Equipment put away\.',  # Notes
    r'^\*\*.*recorded.*\*\*$',  # "**No X recorded.**"
    r'^Alternate::?$',  # "Alternate::" or "Alternate:"
    r'.*::$',  # Anything ending with "::"
    r'.* per (set|side|rep)',  # "50 per set", "5 per side"
    r'^(Arm|Leg|Hip|Shoulder) (swings?|circles?|rotations?) \(',  # "Arm swings (30 sec)"
    r'^\d+ (seconds?|sec|mins?|minutes?) ',  # "30 seconds rest"
]


def is_non_exercise(name: str) -> bool:
    """
    Determine if this is NOT an actual exercise.

    Returns True if this should be filtered out.
    """
    name = name.strip()

    # Check against patterns
    for pattern in NON_EXERCISE_PATTERNS:
        if re.match(pattern, name, re.IGNORECASE):
            return True

    # Too short
    if len(name) < 3:
        return True

    # Just punctuation/symbols
    if re.match(r'^[\W_]+$', name):
        return True

    # Starts with number only (likely reps/sets)
    if re.match(r'^\d+\s*$', name):
        return True

    return False


def normalize_exercise_name_for_matching(name: str) -> str:
    """
    Normalize exercise name for fuzzy matching to canonical exercises.

    Steps:
    - Lowercase
    - Remove parentheticals and weight indicators
    - Remove special characters
    - Strip whitespace
    - Singularize common plurals
    """
    # Remove parentheticals (includes reps like "(5/side)" and durations like "(30 sec)")
    name = re.sub(r'\([^)]*\)', '', name)

    # Remove weight indicators
    name = re.sub(r'\d+\s*(lb|kg|lbs|kgs)', '', name, flags=re.IGNORECASE)

    # Remove "weighted" prefix
    name = re.sub(r'^\s*weighted\s+', '', name, flags=re.IGNORECASE)

    # Remove "with" clauses
    name = re.sub(r'\s+with\s+.*', '', name, flags=re.IGNORECASE)

    # Remove static/dynamic descriptors
    name = re.sub(r'\s+(static|dynamic|isometric)', '', name, flags=re.IGNORECASE)

    # Lowercase
    name = name.lower()

    # Remove leading/trailing special chars (including trailing periods and colons)
    name = re.sub(r'^[\W_]+|[\W_]+$', '', name)

    # Replace multiple spaces/special chars with single space
    name = re.sub(r'[\s\-_]+', ' ', name)

    # Strip
    name = name.strip()

    # Common plurals to singular
    if name.endswith('s') and not name.endswith('ss'):
        singular = name[:-1]
        # But keep if it's a common plural form
        if not any(x in name for x in ['press', 'swiss', 'cross']):
            name = singular

    return name


# Common exercise name mappings
# Maps normalized exercise names to canonical Exercise IDs (without "EXERCISE:" prefix)
COMMON_EXERCISE_MAPPINGS = {
    # Deadlifts (using free-exercise-db IDs)
    "trap bar deadlift": "Deficit_Deadlift",  # Close match
    "conventional deadlift": "Deficit_Deadlift",
    "deadlift": "Deficit_Deadlift",
    "romanian deadlift": "Deficit_Deadlift",
    "rdl": "Deficit_Deadlift",

    # Squats
    "bulgarian split squat": "BULGARIAN_SPLIT_SQUAT",  # Custom exercise
    "goblet squat": "GOBLET_SQUAT",  # Custom exercise
    "front squat": "Barbell_Front_Squat",
    "back squat": "Barbell_Back_Squat",

    # Pull-ups (using actual IDs from free-exercise-db)
    "pull up": "Pullups",
    "pullup": "Pullups",
    "chin up": "Chin-Up",

    # Presses
    "overhead press": "Dumbbell_Shoulder_Press",
    "shoulder press": "Dumbbell_Shoulder_Press",
    "seated overhead press": "Seated_Dumbbell_Press",
    "bench press": "Barbell_Bench_Press_-_Medium_Grip",

    # Rows
    "renegade row": "RENEGADE_ROW",  # Custom exercise
    "bent over row": "Bent_Over_Barbell_Row",
    "dumbbell row": "One-Arm_Dumbbell_Row",
    "barbell row": "Bent_Over_Barbell_Row",

    # Kettlebell
    "kb swing": "Kettlebell_Swing",
    "kettlebell swing": "Kettlebell_Swing",
    "turkish get up": "Kettlebell_Turkish_Get-Up_Lunge_style",

    # Carries
    "farmer carry": "Farmers_Walk",
    "farmers carry": "Farmers_Walk",
    "sandbag carry": "SANDBAG_CARRY",  # Custom exercise
    "zercher carry": "ZERCHER_CARRY",  # Custom exercise
    "bear hug carry": "SANDBAG_CARRY",
    "sandbag bear hug carry": "SANDBAG_CARRY",

    # Core
    "plank": "Plank",
    "side plank": "Side_Bridge",
    "dead bug": "Dead_Bug",
    "deadbug": "Dead_Bug",

    # Lunges
    "lunge": "Barbell_Lunge",
    "spiderman lunge": "SPIDERMAN_LUNGE",  # Custom exercise
    "reverse lunge": "Reverse_Lunge",
    "walking lunge": "Barbell_Walking_Lunge",

    # Other
    "face pull": "Face_Pull",
    "hip thrust": "Barbell_Glute_Bridge",

    # Sandbag exercises
    "sandbag shoulder": "SANDBAG_SHOULDERING",  # Custom exercise
    "sandbag shouldering": "SANDBAG_SHOULDERING",
    "sandbag overhead hold": "SANDBAG_CARRY",
    "sandbag clean": "SANDBAG_CARRY",
}


def find_canonical_exercise_id(normalized_name: str) -> Optional[str]:
    """
    Map normalized exercise name to canonical exercise ID.

    Returns:
        exercise_id if match found, None otherwise
    """
    # Direct mapping
    if normalized_name in COMMON_EXERCISE_MAPPINGS:
        return f"EXERCISE:{COMMON_EXERCISE_MAPPINGS[normalized_name]}"

    # Partial match
    for key, value in COMMON_EXERCISE_MAPPINGS.items():
        if key in normalized_name or normalized_name in key:
            return f"EXERCISE:{value}"

    return None
