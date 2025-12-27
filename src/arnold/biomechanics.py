"""
Biomechanical Data Model

Defines movement patterns, joint actions, and anatomical planes for exercise analysis.
"""

from typing import List, Dict, Set
from enum import Enum


class AnatomicalPlane(Enum):
    """Anatomical planes of motion."""
    SAGITTAL = "sagittal"      # Divides body into left/right (flexion/extension)
    FRONTAL = "frontal"        # Divides body into front/back (abduction/adduction)
    TRANSVERSE = "transverse"  # Divides body into top/bottom (rotation)


class JointAction(Enum):
    """Joint actions and movements."""
    # Sagittal plane
    FLEXION = "flexion"
    EXTENSION = "extension"
    DORSIFLEXION = "dorsiflexion"
    PLANTARFLEXION = "plantarflexion"

    # Frontal plane
    ABDUCTION = "abduction"
    ADDUCTION = "adduction"
    LATERAL_FLEXION = "lateral_flexion"
    ELEVATION = "elevation"
    DEPRESSION = "depression"

    # Transverse plane
    INTERNAL_ROTATION = "internal_rotation"
    EXTERNAL_ROTATION = "external_rotation"
    HORIZONTAL_ABDUCTION = "horizontal_abduction"
    HORIZONTAL_ADDUCTION = "horizontal_adduction"
    PRONATION = "pronation"
    SUPINATION = "supination"

    # Special
    CIRCUMDUCTION = "circumduction"
    PROTRACTION = "protraction"
    RETRACTION = "retraction"


class MovementPattern(Enum):
    """Fundamental movement patterns."""
    SQUAT = "squat"
    HINGE = "hinge"
    LUNGE = "lunge"
    PUSH = "push"
    PULL = "pull"
    CARRY = "carry"
    ROTATION = "rotation"
    ANTI_ROTATION = "anti_rotation"
    LOCOMOTION = "locomotion"


# Exercise to movement pattern mappings
EXERCISE_MOVEMENT_PATTERNS = {
    # Squats
    "squat": [MovementPattern.SQUAT],
    "goblet squat": [MovementPattern.SQUAT],
    "front squat": [MovementPattern.SQUAT],
    "back squat": [MovementPattern.SQUAT],
    "bulgarian split squat": [MovementPattern.LUNGE, MovementPattern.SQUAT],

    # Hinges
    "deadlift": [MovementPattern.HINGE],
    "romanian deadlift": [MovementPattern.HINGE],
    "good morning": [MovementPattern.HINGE],
    "hip thrust": [MovementPattern.HINGE],

    # Lunges
    "lunge": [MovementPattern.LUNGE],
    "walking lunge": [MovementPattern.LUNGE, MovementPattern.LOCOMOTION],
    "reverse lunge": [MovementPattern.LUNGE],
    "lateral lunge": [MovementPattern.LUNGE],

    # Push
    "bench press": [MovementPattern.PUSH],
    "overhead press": [MovementPattern.PUSH],
    "push up": [MovementPattern.PUSH],
    "dip": [MovementPattern.PUSH],

    # Pull
    "pull up": [MovementPattern.PULL],
    "pullup": [MovementPattern.PULL],
    "row": [MovementPattern.PULL],
    "lat pulldown": [MovementPattern.PULL],

    # Carries
    "farmer carry": [MovementPattern.CARRY, MovementPattern.LOCOMOTION],
    "farmers walk": [MovementPattern.CARRY, MovementPattern.LOCOMOTION],
    "sandbag carry": [MovementPattern.CARRY, MovementPattern.LOCOMOTION],
    "zercher carry": [MovementPattern.CARRY, MovementPattern.LOCOMOTION],

    # Rotation/Anti-rotation
    "plank": [MovementPattern.ANTI_ROTATION],
    "dead bug": [MovementPattern.ANTI_ROTATION],
    "bird dog": [MovementPattern.ANTI_ROTATION],
    "pallof press": [MovementPattern.ANTI_ROTATION],
    "russian twist": [MovementPattern.ROTATION],
}


# Movement pattern to joint action mappings
MOVEMENT_JOINT_ACTIONS = {
    MovementPattern.SQUAT: {
        "hip": [JointAction.FLEXION, JointAction.EXTENSION],
        "knee": [JointAction.FLEXION, JointAction.EXTENSION],
        "ankle": [JointAction.DORSIFLEXION, JointAction.PLANTARFLEXION],
    },
    MovementPattern.HINGE: {
        "hip": [JointAction.FLEXION, JointAction.EXTENSION],
        "spine": [JointAction.EXTENSION],  # Maintaining neutral
    },
    MovementPattern.LUNGE: {
        "hip": [JointAction.FLEXION, JointAction.EXTENSION],
        "knee": [JointAction.FLEXION, JointAction.EXTENSION],
        "ankle": [JointAction.DORSIFLEXION],
    },
    MovementPattern.PUSH: {
        "shoulder": [JointAction.FLEXION, JointAction.HORIZONTAL_ADDUCTION],
        "elbow": [JointAction.EXTENSION],
        "scapula": [JointAction.PROTRACTION],
    },
    MovementPattern.PULL: {
        "shoulder": [JointAction.EXTENSION, JointAction.ADDUCTION],
        "elbow": [JointAction.FLEXION],
        "scapula": [JointAction.RETRACTION],
    },
    MovementPattern.CARRY: {
        "shoulder": [JointAction.ELEVATION],
        "scapula": [JointAction.ELEVATION],
    },
}


# Injury-incompatible joint actions
INJURY_CONTRAINDICATIONS = {
    "shoulder impingement": {
        "avoid_actions": [JointAction.ELEVATION, JointAction.INTERNAL_ROTATION],
        "avoid_positions": ["overhead", "behind_neck"],
    },
    "knee meniscus": {
        "avoid_actions": [JointAction.FLEXION],  # Deep flexion
        "depth_limit": "90_degrees",
    },
    "lower back strain": {
        "avoid_actions": [JointAction.FLEXION, JointAction.INTERNAL_ROTATION, JointAction.EXTERNAL_ROTATION],
        "avoid_positions": ["flexed_under_load"],
    },
    "tennis elbow": {
        "avoid_actions": [JointAction.EXTENSION],  # Resisted extension
        "limit_grips": ["pronated"],
    },
}


def get_movement_patterns_for_exercise(exercise_name: str) -> List[MovementPattern]:
    """
    Get movement patterns for an exercise based on name matching.

    Args:
        exercise_name: Exercise name

    Returns:
        List of MovementPattern enums
    """
    exercise_lower = exercise_name.lower()

    # Direct lookup
    if exercise_lower in EXERCISE_MOVEMENT_PATTERNS:
        return EXERCISE_MOVEMENT_PATTERNS[exercise_lower]

    # Fuzzy matching
    patterns = []
    for key, value in EXERCISE_MOVEMENT_PATTERNS.items():
        if key in exercise_lower or exercise_lower in key:
            patterns.extend(value)

    return list(set(patterns))


def get_joint_actions_for_movement(pattern: MovementPattern) -> Dict[str, List[JointAction]]:
    """
    Get joint actions involved in a movement pattern.

    Args:
        pattern: MovementPattern enum

    Returns:
        Dictionary of joint: [actions]
    """
    return MOVEMENT_JOINT_ACTIONS.get(pattern, {})


def check_exercise_injury_compatibility(
    movement_patterns: List[MovementPattern],
    injury_type: str
) -> Dict[str, any]:
    """
    Check if exercise movement patterns are compatible with an injury.

    Args:
        movement_patterns: List of MovementPattern enums
        injury_type: Type of injury

    Returns:
        Compatibility analysis
    """
    if injury_type not in INJURY_CONTRAINDICATIONS:
        return {"compatible": True, "warnings": []}

    contraindications = INJURY_CONTRAINDICATIONS[injury_type]
    avoid_actions = set(contraindications.get("avoid_actions", []))

    # Check if any movement pattern involves contraindicated actions
    incompatible_actions = []
    for pattern in movement_patterns:
        joint_actions = get_joint_actions_for_movement(pattern)
        for joint, actions in joint_actions.items():
            for action in actions:
                if action in avoid_actions:
                    incompatible_actions.append((pattern, joint, action))

    if incompatible_actions:
        return {
            "compatible": False,
            "reason": f"Involves contraindicated actions for {injury_type}",
            "incompatible_actions": incompatible_actions,
            "warnings": [
                f"{pattern.value} involves {joint} {action.value}"
                for pattern, joint, action in incompatible_actions
            ]
        }

    return {"compatible": True, "warnings": []}


def get_exercise_complexity_score(
    movement_patterns: List[MovementPattern],
    equipment: str,
    num_muscles: int
) -> int:
    """
    Calculate exercise complexity score (1-10).

    Higher score = more complex

    Args:
        movement_patterns: Movement patterns involved
        equipment: Equipment required
        num_muscles: Number of muscles targeted

    Returns:
        Complexity score 1-10
    """
    score = 0

    # Base on movement patterns
    score += len(movement_patterns) * 2

    # Multi-planar movements are more complex
    complex_patterns = {
        MovementPattern.ROTATION,
        MovementPattern.LOCOMOTION,
        MovementPattern.CARRY
    }
    if any(p in complex_patterns for p in movement_patterns):
        score += 2

    # Equipment complexity
    equipment_complexity = {
        "Body Only": 0,
        "Dumbbell": 1,
        "Kettlebell": 1,
        "Barbell": 2,
        "Machine": -1,  # Machines reduce complexity
        "Other": 2,
    }
    score += equipment_complexity.get(equipment, 0)

    # Muscle recruitment
    score += min(num_muscles // 2, 3)

    return max(1, min(10, score))
