"""
JUDGMENT-DAY: Coaching Intelligence Layer

Internal Codename: JUDGMENT-DAY
"Judgment Day: The day the workout is decided."

This module contains the AI-powered coaching logic that generates
personalized, periodized workout plans based on:
- Historical training data
- Current periodization phase
- Injury constraints
- Equipment availability
- Goal alignment
- Progressive overload principles
"""

from .periodization import PeriodizationEngine
from .constraints import ConstraintChecker
from .analytics import ProgressionAnalyzer
from .variation import ExerciseVariationSuggester
from .planner import WorkoutPlanner

__all__ = [
    'PeriodizationEngine',
    'ConstraintChecker',
    'ProgressionAnalyzer',
    'ExerciseVariationSuggester',
    'WorkoutPlanner',
]
