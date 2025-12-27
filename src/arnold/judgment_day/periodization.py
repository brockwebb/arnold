"""
Periodization Logic Engine

Internal Codename: JUDGMENT-DAY
Implements training periodization cycles and phase management.
"""

from datetime import date, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum


class PeriodizationPhase(Enum):
    """Training phases in a 4-week microcycle."""
    ACCUMULATION = "Accumulation"      # Week 1-2: Higher volume, moderate intensity
    INTENSIFICATION = "Intensification"  # Week 3: Lower volume, higher intensity
    REALIZATION = "Realization"         # Week 4: Peak performance
    DELOAD = "Deload"                   # Week 4 (alt): Recovery and adaptation


class PhaseCharacteristics:
    """Training characteristics for each periodization phase."""

    PHASES = {
        PeriodizationPhase.ACCUMULATION: {
            "volume_multiplier": 1.0,      # 100% of baseline volume
            "intensity_range": (0.65, 0.75),  # 65-75% of max
            "rpe_range": (6, 7),            # RPE 6-7
            "sets_per_exercise": (3, 5),
            "reps_per_set": (8, 12),
            "rest_seconds": 90,
            "focus": "Volume accumulation and hypertrophy"
        },
        PeriodizationPhase.INTENSIFICATION: {
            "volume_multiplier": 0.75,     # 75% of baseline volume
            "intensity_range": (0.75, 0.85),  # 75-85% of max
            "rpe_range": (7, 8),
            "sets_per_exercise": (3, 4),
            "reps_per_set": (5, 8),
            "rest_seconds": 120,
            "focus": "Strength building and neural adaptation"
        },
        PeriodizationPhase.REALIZATION: {
            "volume_multiplier": 0.6,      # 60% of baseline volume
            "intensity_range": (0.85, 0.95),  # 85-95% of max
            "rpe_range": (8, 9),
            "sets_per_exercise": (2, 3),
            "reps_per_set": (3, 5),
            "rest_seconds": 180,
            "focus": "Peak performance and strength expression"
        },
        PeriodizationPhase.DELOAD: {
            "volume_multiplier": 0.5,      # 50% of baseline volume
            "intensity_range": (0.50, 0.65),  # 50-65% of max
            "rpe_range": (5, 6),
            "sets_per_exercise": (2, 3),
            "reps_per_set": (6, 10),
            "rest_seconds": 90,
            "focus": "Recovery and technique refinement"
        }
    }

    @classmethod
    def get(cls, phase: PeriodizationPhase) -> dict:
        """Get characteristics for a phase."""
        return cls.PHASES[phase]


class PeriodizationEngine:
    """
    Manages training periodization cycles.

    Implements a 4-week microcycle:
    - Week 1-2: Accumulation (volume focus)
    - Week 3: Intensification (intensity focus)
    - Week 4: Realization OR Deload (depending on fatigue)
    """

    def __init__(self, graph):
        """
        Initialize periodization engine.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph

    def get_current_phase(self) -> Tuple[PeriodizationPhase, int, date]:
        """
        Get current periodization phase based on recent training.

        Returns:
            Tuple of (phase, week_in_cycle, cycle_start_date)
        """
        # Query for most recent workout with periodization phase
        query = """
        MATCH (w:Workout)
        WHERE w.periodization_phase IS NOT NULL
        RETURN w.periodization_phase as phase, w.date as date
        ORDER BY w.date DESC
        LIMIT 1
        """

        result = self.graph.execute_query(query)

        if not result:
            # No phase set - start new cycle
            return PeriodizationPhase.ACCUMULATION, 1, date.today()

        last_phase = result[0]['phase']
        last_date = date.fromisoformat(result[0]['date']) if isinstance(result[0]['date'], str) else result[0]['date']

        # Calculate days since last phase
        days_since = (date.today() - last_date).days

        # Determine current phase based on progression
        phase_map = {
            "Accumulation": PeriodizationPhase.ACCUMULATION,
            "Intensification": PeriodizationPhase.INTENSIFICATION,
            "Realization": PeriodizationPhase.REALIZATION,
            "Deload": PeriodizationPhase.DELOAD,
        }

        current_phase = phase_map.get(last_phase, PeriodizationPhase.ACCUMULATION)

        # If it's been more than 7 days, advance phase
        if days_since > 7:
            current_phase = self._advance_phase(current_phase)
            week_in_cycle = self._get_week_number(current_phase)
        else:
            week_in_cycle = self._get_week_number(current_phase)

        return current_phase, week_in_cycle, last_date

    def _advance_phase(self, current_phase: PeriodizationPhase) -> PeriodizationPhase:
        """Advance to next phase in cycle."""
        progression = [
            PeriodizationPhase.ACCUMULATION,
            PeriodizationPhase.ACCUMULATION,  # Week 2 also accumulation
            PeriodizationPhase.INTENSIFICATION,
            PeriodizationPhase.REALIZATION,
        ]

        try:
            idx = progression.index(current_phase)
            if idx < len(progression) - 1:
                return progression[idx + 1]
            else:
                # Cycle complete, decide deload or restart
                return self._should_deload()
        except ValueError:
            return PeriodizationPhase.ACCUMULATION

    def _should_deload(self) -> PeriodizationPhase:
        """
        Determine if deload is needed based on fatigue signals.

        Checks:
        - Recent subjective intensity ratings
        - Deviation frequency
        - Session adherence
        """
        query = """
        MATCH (w:Workout)
        WHERE w.date >= date() - duration({weeks: 4})
        RETURN
            avg(w.perceived_intensity) as avg_intensity,
            count(CASE WHEN size(w.deviations) > 0 THEN 1 END) as deviations,
            count(w) as total_sessions
        """

        result = self.graph.execute_query(query)

        if result:
            r = result[0]
            avg_intensity = r.get('avg_intensity', 5)
            deviation_rate = r.get('deviations', 0) / max(r.get('total_sessions', 1), 1)

            # Deload if high fatigue signals
            if avg_intensity and avg_intensity > 7.5:
                return PeriodizationPhase.DELOAD
            if deviation_rate > 0.3:  # More than 30% deviations
                return PeriodizationPhase.DELOAD

        # Otherwise start new cycle
        return PeriodizationPhase.ACCUMULATION

    def _get_week_number(self, phase: PeriodizationPhase) -> int:
        """Get week number in 4-week cycle for phase."""
        week_map = {
            PeriodizationPhase.ACCUMULATION: 1,  # Weeks 1-2
            PeriodizationPhase.INTENSIFICATION: 3,
            PeriodizationPhase.REALIZATION: 4,
            PeriodizationPhase.DELOAD: 4,
        }
        return week_map.get(phase, 1)

    def get_phase_targets(self, phase: Optional[PeriodizationPhase] = None) -> dict:
        """
        Get training targets for a specific phase.

        Args:
            phase: Periodization phase (uses current if None)

        Returns:
            Dictionary of phase characteristics
        """
        if phase is None:
            phase, _, _ = self.get_current_phase()

        return PhaseCharacteristics.get(phase)

    def record_phase_transition(self, workout_id: str, new_phase: PeriodizationPhase):
        """
        Record phase transition in a workout.

        Args:
            workout_id: Workout node ID
            new_phase: New periodization phase
        """
        query = """
        MATCH (w:Workout {id: $workout_id})
        SET w.periodization_phase = $phase
        """

        self.graph.execute_write(query, {
            'workout_id': workout_id,
            'phase': new_phase.value
        })

    def get_adherence_rate(self, weeks: int = 4) -> float:
        """
        Calculate adherence rate (sessions completed vs planned).

        Args:
            weeks: Number of weeks to analyze

        Returns:
            Adherence rate as percentage (0-100)
        """
        query = """
        MATCH (w:Workout)
        WHERE w.date >= date() - duration({weeks: $weeks})
        RETURN count(w) as completed
        """

        result = self.graph.execute_query(query, {'weeks': weeks})

        if result:
            completed = result[0]['completed']
            # Assume 4 sessions per week as baseline
            planned = weeks * 4
            return (completed / planned) * 100 if planned > 0 else 0

        return 0
