"""
Workout Plan Generator

Internal Codename: JUDGMENT-DAY
"Judgment Day: The day the workout is decided."

Generates intelligent, periodized workout plans.
"""

from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
import random

from .periodization import PeriodizationEngine, PeriodizationPhase
from .constraints import ConstraintChecker
from .analytics import ProgressionAnalyzer
from .variation import ExerciseVariationSuggester


class WorkoutPlanner:
    """
    Generates complete workout plans.

    Integrates:
    - Periodization (volume/intensity targets)
    - Constraints (injury avoidance)
    - Exercise selection (variation, equipment)
    - Progressive overload
    """

    def __init__(self, graph):
        """
        Initialize workout planner.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph
        self.periodization = PeriodizationEngine(graph)
        self.constraints = ConstraintChecker(graph)
        self.analytics = ProgressionAnalyzer(graph)
        self.variation = ExerciseVariationSuggester(graph)

    def generate_daily_plan(
        self,
        plan_date: Optional[date] = None,
        focus: Optional[str] = None,
        workout_type: str = 'strength'
    ) -> Dict:
        """
        Generate a complete workout plan for a specific date.

        Args:
            plan_date: Date to plan for (default: tomorrow)
            focus: Optional focus (e.g., "Upper Push", "Lower Pull")
            workout_type: Type of workout ('strength', 'conditioning', 'skill')

        Returns:
            Complete workout plan dictionary
        """
        if plan_date is None:
            plan_date = date.today() + timedelta(days=1)

        # Get current periodization phase
        phase, week, cycle_start = self.periodization.get_current_phase()
        phase_targets = self.periodization.get_phase_targets(phase)

        # Get recent workouts to avoid repetition
        recent_workouts = self.analytics.get_recent_workouts(limit=7)

        # Determine focus if not specified
        if focus is None:
            focus = self._determine_focus(recent_workouts)

        # Generate exercise selection
        exercises = self._select_exercises(
            focus=focus,
            phase=phase,
            phase_targets=phase_targets,
            workout_type=workout_type
        )

        # Build warmup
        warmup = self._generate_warmup(focus)

        # Build cooldown
        cooldown = self._generate_cooldown()

        # Get alternatives for main exercises
        alternatives = self._get_alternatives(exercises)

        plan = {
            "date": str(plan_date),
            "focus": focus,
            "workout_type": workout_type,
            "periodization_phase": f"{phase.value} Week {week}",
            "phase_characteristics": {
                "volume_multiplier": phase_targets["volume_multiplier"],
                "intensity_range": f"{int(phase_targets['intensity_range'][0]*100)}-{int(phase_targets['intensity_range'][1]*100)}%",
                "rpe_target": f"{phase_targets['rpe_range'][0]}-{phase_targets['rpe_range'][1]}",
                "focus": phase_targets["focus"]
            },
            "exercises": exercises,
            "warmup": warmup,
            "cooldown": cooldown,
            "alternatives": alternatives,
            "notes": self._generate_notes(phase, focus)
        }

        return plan

    def _determine_focus(self, recent_workouts: List[Dict]) -> str:
        """
        Determine workout focus based on recent training.

        Args:
            recent_workouts: Recent workout records

        Returns:
            Focus string (e.g., "Upper Push")
        """
        # Extract recent focus areas from tags
        recent_tags = []
        for w in recent_workouts[:3]:  # Last 3 workouts
            tags = w.get('tags', [])
            recent_tags.extend(tags)

        # Define focus rotation
        focus_options = [
            "Upper Push",
            "Upper Pull",
            "Lower Body",
            "Full Body",
            "Core & Accessory"
        ]

        # Simple rotation - avoid repeating last focus
        last_workout_type = (recent_workouts[0].get('type') or '').lower() if recent_workouts else ''

        # Check tags for hints
        recent_tags_str = ' '.join(str(tag) for tag in recent_tags if tag).lower()
        if 'upper' in recent_tags_str:
            return random.choice(["Lower Body", "Full Body"])
        elif 'lower' in recent_tags_str:
            return random.choice(["Upper Push", "Upper Pull"])
        else:
            return random.choice(focus_options)

    def _select_exercises(
        self,
        focus: str,
        phase: PeriodizationPhase,
        phase_targets: Dict,
        workout_type: str
    ) -> List[Dict]:
        """
        Select exercises for the workout.

        Args:
            focus: Workout focus
            phase: Current periodization phase
            phase_targets: Phase training targets
            workout_type: Workout type

        Returns:
            List of exercise dictionaries
        """
        exercises = []

        # Get muscle groups for focus
        muscle_groups = self._get_muscle_groups_for_focus(focus)

        # Determine exercise count based on phase
        if phase == PeriodizationPhase.ACCUMULATION:
            exercise_count = random.randint(5, 7)
        elif phase == PeriodizationPhase.INTENSIFICATION:
            exercise_count = random.randint(4, 6)
        else:  # Realization or Deload
            exercise_count = random.randint(3, 5)

        # Get forbidden exercises
        forbidden = self.constraints.get_forbidden_exercises()

        # Select main compound movements first
        for i, muscle_group in enumerate(muscle_groups[:exercise_count]):
            # Get exercise suggestions
            suggestions = self.variation.suggest_by_muscle_group(
                muscle_group=muscle_group,
                limit=10,
                exclude_recent_days=7
            )

            # Filter out forbidden
            allowed_suggestions = [
                s for s in suggestions
                if s['id'] not in forbidden
            ]

            if not allowed_suggestions:
                continue

            # Pick one (prefer compound movements for first exercises)
            if i == 0:
                # First exercise - pick compound movement
                compound = [s for s in allowed_suggestions if s.get('category') == 'Strength']
                exercise = compound[0] if compound else allowed_suggestions[0]
            else:
                exercise = allowed_suggestions[0]

            # Determine sets/reps based on phase
            sets_range = phase_targets['sets_per_exercise']
            reps_range = phase_targets['reps_per_set']

            sets = random.randint(sets_range[0], sets_range[1])
            reps_low = reps_range[0]
            reps_high = reps_range[1]

            exercise_prescription = {
                "name": exercise['name'],
                "exercise_id": exercise['id'],
                "sets": sets,
                "reps": f"{reps_low}-{reps_high}" if reps_low != reps_high else str(reps_low),
                "intensity": f"RPE {phase_targets['rpe_range'][0]}-{phase_targets['rpe_range'][1]}",
                "rest": f"{phase_targets['rest_seconds']}s",
                "equipment": exercise.get('equipment'),
                "muscles": exercise.get('muscles', []),
                "notes": self._generate_exercise_notes(exercise, i)
            }

            exercises.append(exercise_prescription)

        return exercises

    def _get_muscle_groups_for_focus(self, focus: str) -> List[str]:
        """Get muscle groups to target for a focus."""
        focus_map = {
            "Upper Push": ["Chest", "Shoulders", "Triceps"],
            "Upper Pull": ["Lats", "Middle Back", "Biceps"],
            "Lower Body": ["Quadriceps", "Hamstrings", "Glutes"],
            "Full Body": ["Quadriceps", "Chest", "Lats", "Shoulders"],
            "Core & Accessory": ["Abdominals", "Lower Back", "Forearms"]
        }

        return focus_map.get(focus, ["Chest", "Lats", "Quadriceps"])

    def _generate_warmup(self, focus: str) -> List[Dict]:
        """Generate warmup sequence."""
        warmup = [
            {
                "name": "General Movement",
                "description": "5 minutes light cardio (walking, cycling, rowing)",
                "duration": "5:00"
            },
            {
                "name": "Dynamic Mobility",
                "description": self._get_mobility_for_focus(focus),
                "duration": "3:00"
            },
            {
                "name": "Specific Warmup",
                "description": "2-3 sets of first exercise at 40-60% intensity",
                "sets": "2-3"
            }
        ]

        return warmup

    def _get_mobility_for_focus(self, focus: str) -> str:
        """Get mobility work for focus."""
        mobility_map = {
            "Upper Push": "Shoulder circles, arm swings, wall slides, band pull-aparts",
            "Upper Pull": "Arm circles, scapular retractions, thoracic rotations",
            "Lower Body": "Leg swings, hip circles, glute bridges, bodyweight squats",
            "Full Body": "World's greatest stretch, inchworms, hip openers",
            "Core & Accessory": "Cat-cow, bird dogs, dead bugs, plank holds"
        }

        return mobility_map.get(focus, "General dynamic stretching")

    def _generate_cooldown(self) -> List[Dict]:
        """Generate cooldown sequence."""
        cooldown = [
            {
                "name": "Active Recovery",
                "description": "3-5 minutes light movement (walking, easy cycling)",
                "duration": "3-5:00"
            },
            {
                "name": "Static Stretching",
                "description": "Hold each stretch 30-60s, focus on muscles worked",
                "duration": "5-10:00"
            }
        ]

        return cooldown

    def _generate_exercise_notes(self, exercise: Dict, position: int) -> str:
        """Generate notes for an exercise."""
        notes = []

        if position == 0:
            notes.append("Main lift - prioritize form and progression")

        level = exercise.get('level')
        if level == 'Expert':
            notes.append("Advanced exercise - ensure proper technique")

        return "; ".join(notes) if notes else ""

    def _get_alternatives(self, exercises: List[Dict]) -> Dict[str, List[str]]:
        """Get alternative exercises for each main exercise."""
        alternatives = {}

        for ex in exercises[:3]:  # Get alternatives for first 3 exercises
            variations = self.variation.suggest_variations(
                exercise_name=ex['name'],
                limit=3,
                exclude_recent_days=7
            )

            alternatives[ex['name']] = [v['name'] for v in variations]

        return alternatives

    def _generate_notes(self, phase: PeriodizationPhase, focus: str) -> List[str]:
        """Generate workout notes and coaching cues."""
        notes = [
            f"Phase: {phase.value} - {self.periodization.get_phase_targets(phase)['focus']}",
            f"Focus: {focus}",
        ]

        # Phase-specific notes
        if phase == PeriodizationPhase.ACCUMULATION:
            notes.append("Emphasis on volume and hypertrophy")
            notes.append("Control tempo, feel the muscle working")
        elif phase == PeriodizationPhase.INTENSIFICATION:
            notes.append("Emphasis on strength and neural adaptation")
            notes.append("Focus on moving heavier weights with good form")
        elif phase == PeriodizationPhase.REALIZATION:
            notes.append("Peak performance week - test your limits")
            notes.append("Longer rest periods, maximum effort sets")
        else:  # Deload
            notes.append("Recovery week - reduce weight and volume")
            notes.append("Focus on technique and mobility")

        # Check for overtraining signals
        overtraining = self.analytics.detect_overtraining(weeks=4)
        if overtraining['overtraining_risk'] in ['moderate', 'high']:
            notes.append(f"⚠️  {overtraining['recommendation']}")

        return notes

    def format_plan_text(self, plan: Dict) -> str:
        """
        Format workout plan as readable text.

        Args:
            plan: Workout plan dictionary

        Returns:
            Formatted text string
        """
        lines = []

        lines.append("=" * 60)
        lines.append(f"JUDGMENT-DAY: Workout Plan")
        lines.append("=" * 60)
        lines.append(f"\nDate: {plan['date']}")
        lines.append(f"Focus: {plan['focus']}")
        lines.append(f"Type: {plan['workout_type'].title()}")
        lines.append(f"Phase: {plan['periodization_phase']}")

        # Phase characteristics
        lines.append(f"\nPhase Targets:")
        chars = plan['phase_characteristics']
        lines.append(f"  Intensity: {chars['intensity_range']}")
        lines.append(f"  RPE: {chars['rpe_target']}")
        lines.append(f"  Volume: {int(chars['volume_multiplier']*100)}% of baseline")

        # Warmup
        lines.append(f"\n{'─' * 60}")
        lines.append("WARMUP")
        lines.append('─' * 60)
        for w in plan['warmup']:
            lines.append(f"\n{w['name']}:")
            lines.append(f"  {w['description']}")
            if 'duration' in w:
                lines.append(f"  Duration: {w['duration']}")
            if 'sets' in w:
                lines.append(f"  Sets: {w['sets']}")

        # Main exercises
        lines.append(f"\n{'─' * 60}")
        lines.append("MAIN WORKOUT")
        lines.append('─' * 60)
        for i, ex in enumerate(plan['exercises'], 1):
            lines.append(f"\n{i}. {ex['name']}")
            lines.append(f"   Sets: {ex['sets']} x {ex['reps']} reps")
            lines.append(f"   Intensity: {ex['intensity']}")
            lines.append(f"   Rest: {ex['rest']}")
            lines.append(f"   Equipment: {ex['equipment']}")

            if ex.get('notes'):
                lines.append(f"   Notes: {ex['notes']}")

            # Show alternatives
            if ex['name'] in plan.get('alternatives', {}):
                alts = plan['alternatives'][ex['name']]
                if alts:
                    lines.append(f"   Alternatives: {', '.join(alts)}")

        # Cooldown
        lines.append(f"\n{'─' * 60}")
        lines.append("COOLDOWN")
        lines.append('─' * 60)
        for c in plan['cooldown']:
            lines.append(f"\n{c['name']}:")
            lines.append(f"  {c['description']}")
            if 'duration' in c:
                lines.append(f"  Duration: {c['duration']}")

        # Notes
        if plan.get('notes'):
            lines.append(f"\n{'─' * 60}")
            lines.append("NOTES")
            lines.append('─' * 60)
            for note in plan['notes']:
                lines.append(f"  • {note}")

        lines.append(f"\n{'=' * 60}")
        lines.append('"Your workout has been decided."')
        lines.append('=' * 60)

        return '\n'.join(lines)
