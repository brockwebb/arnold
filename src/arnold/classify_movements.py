"""
LLM-Powered Movement Pattern Classification

Uses OpenAI gpt-5-mini to classify exercises into biomechanical movement patterns.
Enables injury-aware programming for custom and unconventional exercises.

Codename: PATTERN-RECOGNITION-ALPHA
"""

import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI


class MovementClassifier:
    """
    Classify exercises into movement patterns using LLM reasoning.

    Uses OpenAI gpt-5-mini (MoE model) with biomechanical expertise to map
    exercises to fundamental movement patterns based on joint actions.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize movement classifier.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self.model = "gpt-5-mini"  # MoE model - no temperature settings

    def classify_exercise(
        self,
        exercise_name: str,
        category: str,
        equipment: Optional[str],
        movement_taxonomy: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Classify exercise into movement patterns using LLM.

        Args:
            exercise_name: Name of exercise (e.g., "Tire Flip")
            category: Exercise category (e.g., "strength", "custom")
            equipment: Equipment used (e.g., "tire", "barbell")
            movement_taxonomy: List of available movement patterns

        Returns:
            {
                "exercise": "Tire Flip",
                "movements": ["HINGE", "PUSH"],
                "reasoning": "Tire flip involves...",
                "primary_muscles": ["glutes", "hamstrings"],
                "joint_actions": [...],
                "confidence": 0.85
            }
        """
        prompt = self._build_classification_prompt(
            exercise_name,
            category,
            equipment,
            movement_taxonomy
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Validate and normalize
            return self._validate_classification(result, exercise_name)

        except Exception as e:
            print(f"Error classifying {exercise_name}: {e}")
            return {
                "exercise": exercise_name,
                "movements": [],
                "reasoning": f"Classification failed: {str(e)}",
                "confidence": 0.0,
                "error": str(e)
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for movement classification."""
        return """You are a biomechanics expert specializing in exercise science and functional movement patterns.

Your task: Classify exercises into movement patterns based on joint actions and muscle recruitment.

Key principles:
- Movement patterns describe HOW the body moves, not WHAT muscles are targeted
- Many exercises involve MULTIPLE patterns (compound movements)
- Consider the PRIMARY joint actions first, then secondary stabilization requirements
- Be precise about planes of motion (sagittal, frontal, transverse)
- PUSH and PULL can be horizontal OR vertical (overhead press is vertical PUSH)
- CARRY includes loaded walking/marching with various load positions
- ANTI_ROTATION is isometric core stabilization against rotational forces

Return ONLY valid JSON. No markdown, no explanations outside the JSON."""

    def _build_classification_prompt(
        self,
        exercise: str,
        category: str,
        equipment: Optional[str],
        taxonomy: List[Dict]
    ) -> str:
        """Build classification prompt with context."""

        # Format taxonomy for prompt
        taxonomy_str = "\n".join([
            f"- {m['name'].upper()}: {m.get('description', 'Fundamental movement pattern')}"
            for m in taxonomy
        ])

        return f"""Classify this exercise into movement patterns.

EXERCISE: {exercise}
CATEGORY: {category}
EQUIPMENT: {equipment or 'bodyweight/unknown'}

AVAILABLE MOVEMENT PATTERNS:
{taxonomy_str}

CLASSIFICATION INSTRUCTIONS:

1. Identify PRIMARY joint actions:
   - Which joints move? (hip, knee, ankle, shoulder, elbow, spine)
   - What type of movement? (flexion, extension, abduction, rotation)
   - What plane? (sagittal, frontal, transverse)

2. Match to movement patterns:
   - Use 1-3 patterns (most exercises are 1-2, complex movements may be 3)
   - Prioritize PRIMARY movers over stabilizers
   - If the exercise involves rotation/anti-rotation, always include it
   - Carries (loaded walking/marching) should include CARRY
   - Asymmetric loads require ANTI_ROTATION (suitcase carry, single-arm work)

3. Biomechanical reasoning:
   - Explain which muscles produce the movement
   - Describe the joint actions
   - Note any stabilization requirements

4. Confidence score:
   - 1.0: Textbook exercise (e.g., barbell back squat = SQUAT)
   - 0.9: Clear pattern, minor variation (e.g., goblet squat = SQUAT)
   - 0.8: Compound movement, multiple clear patterns (e.g., deadlift = HINGE + PULL)
   - 0.7: Unconventional but clear mechanics (e.g., sandbag shouldering = HINGE)
   - 0.5: Unconventional exercise, pattern inferred (e.g., tire flip)
   - <0.5: Flag for manual review (cannot determine pattern)

REQUIRED JSON SCHEMA:

{{
  "exercise": "{exercise}",
  "movements": ["PATTERN1", "PATTERN2"],
  "reasoning": "This exercise involves... The primary joint action is... Stabilization requires...",
  "primary_muscles": ["muscle1", "muscle2", "muscle3"],
  "joint_actions": [
    {{"joint": "hip", "action": "extension", "plane": "sagittal"}},
    {{"joint": "knee", "action": "extension", "plane": "sagittal"}}
  ],
  "confidence": 0.85,
  "notes": "Any special considerations or variations"
}}

EXAMPLES FOR REFERENCE:

1. Barbell Back Squat:
   - movements: ["SQUAT"]
   - reasoning: "Hip and knee flexion/extension in sagittal plane with vertical torso. Quadriceps, glutes, hamstrings produce movement."
   - confidence: 1.0

2. Deadlift:
   - movements: ["HINGE", "PULL"]
   - reasoning: "Primary hip extension (hinge) with secondary scapular retraction and elbow flexion (pull). Glutes/hamstrings dominant, lats/traps stabilize."
   - confidence: 0.95

3. Suitcase Carry:
   - movements: ["CARRY", "ANTI_ROTATION"]
   - reasoning: "Loaded walking (carry) with asymmetric load requiring lateral spinal stabilization (anti-rotation). Core prevents lateral flexion, glutes/obliques work isometrically."
   - confidence: 0.9

4. Tire Flip:
   - movements: ["HINGE", "PUSH"]
   - reasoning: "Initiates as deadlift (hinge), transitions to overhead press finish (vertical push). Primarily posterior chain (glutes/hamstrings/low back), secondary triceps/delts."
   - confidence: 0.75

5. Bearhug March:
   - movements: ["CARRY", "ANTI_ROTATION"]
   - reasoning: "Loaded walking with anterior load position (bear hug). Hip flexors/extensors produce gait, core stabilizes spine against anterior load and prevents flexion. Anti-rotation from asymmetric loading during single-leg stance."
   - confidence: 0.85

Return ONLY the JSON object. Be thorough but concise in reasoning.
"""

    def _validate_classification(
        self,
        result: Dict[str, Any],
        exercise_name: str
    ) -> Dict[str, Any]:
        """
        Validate and normalize classification result.

        Args:
            result: Raw LLM output
            exercise_name: Original exercise name

        Returns:
            Validated classification dict
        """
        # Ensure required fields
        validated = {
            'exercise': result.get('exercise', exercise_name),
            'movements': result.get('movements', []),
            'reasoning': result.get('reasoning', 'No reasoning provided'),
            'confidence': result.get('confidence', 0.5),
            'primary_muscles': result.get('primary_muscles', []),
            'joint_actions': result.get('joint_actions', []),
            'notes': result.get('notes', '')
        }

        # Normalize movement names (uppercase)
        validated['movements'] = [m.upper().replace(' ', '_') for m in validated['movements']]

        # Ensure confidence is float
        try:
            validated['confidence'] = float(validated['confidence'])
        except (ValueError, TypeError):
            validated['confidence'] = 0.5

        # Limit to 3 movements
        if len(validated['movements']) > 3:
            validated['movements'] = validated['movements'][:3]
            validated['notes'] += " [Truncated to top 3 movements]"

        return validated


def classify_batch(
    exercises: List[Dict[str, str]],
    movement_taxonomy: List[Dict[str, str]],
    api_key: Optional[str] = None,
    delay: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Classify a batch of exercises.

    Args:
        exercises: List of exercise dicts with 'name', 'category', 'equipment'
        movement_taxonomy: Available movement patterns
        api_key: OpenAI API key
        delay: Seconds to wait between API calls (rate limiting)

    Returns:
        List of classification results
    """
    import time
    from tqdm import tqdm

    classifier = MovementClassifier(api_key=api_key)
    results = []

    for exercise in tqdm(exercises, desc="Classifying exercises"):
        classification = classifier.classify_exercise(
            exercise['name'],
            exercise.get('category', 'unknown'),
            exercise.get('equipment'),
            movement_taxonomy
        )

        results.append(classification)
        time.sleep(delay)  # Rate limit protection

    return results


# Example usage
if __name__ == "__main__":
    # Test on a single exercise
    classifier = MovementClassifier()

    test_taxonomy = [
        {"name": "SQUAT", "description": "Hip and knee flexion/extension"},
        {"name": "HINGE", "description": "Hip flexion/extension with stable spine"},
        {"name": "PUSH", "description": "Pressing movements (horizontal or vertical)"},
        {"name": "PULL", "description": "Pulling movements (horizontal or vertical)"},
        {"name": "CARRY", "description": "Loaded walking/marching"},
        {"name": "ANTI_ROTATION", "description": "Core stabilization against rotation"},
    ]

    result = classifier.classify_exercise(
        "Bearhug March",
        "strongman/conditioning",
        "sandbag",
        test_taxonomy
    )

    print(json.dumps(result, indent=2))
