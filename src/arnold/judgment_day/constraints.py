"""
Constraint-Aware Programming

Internal Codename: JUDGMENT-DAY
Enforces injury constraints and validates exercise selections.
"""

from typing import List, Set, Dict, Optional
from dataclasses import dataclass
import sys
from pathlib import Path

# Import biomechanical data
sys.path.insert(0, str(Path(__file__).parent.parent))
from biomechanics import (
    INJURY_CONTRAINDICATIONS,
    get_movement_patterns_for_exercise,
    check_exercise_injury_compatibility
)


@dataclass
class InjuryConstraint:
    """Represents an injury-based training constraint."""
    injury_id: str
    injury_name: str
    location: str
    constraint_type: str
    description: str
    forbidden_patterns: List[str]


class ConstraintChecker:
    """
    Validates workout plans against injury constraints.

    Ensures generated workouts:
    - Avoid exercises that stress injured areas
    - Respect movement pattern restrictions
    - Maintain training safety
    """

    def __init__(self, graph):
        """
        Initialize constraint checker.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph
        self._constraints_cache = None
        self._forbidden_exercises_cache = None

    def load_constraints(self) -> List[InjuryConstraint]:
        """
        Load all active injury constraints from graph.

        Returns:
            List of InjuryConstraint objects
        """
        if self._constraints_cache is not None:
            return self._constraints_cache

        query = """
        MATCH (i:Injury)-[:HAS_CONSTRAINT]->(c:Constraint)
        RETURN
            i.id as injury_id,
            i.name as injury_name,
            i.location as location,
            c.type as constraint_type,
            c.description as description
        """

        results = self.graph.execute_query(query)

        constraints = []
        for r in results:
            # Parse forbidden patterns from description
            forbidden = self._extract_forbidden_patterns(r['description'])

            constraint = InjuryConstraint(
                injury_id=r['injury_id'],
                injury_name=r['injury_name'],
                location=r['location'],
                constraint_type=r['constraint_type'],
                description=r['description'],
                forbidden_patterns=forbidden
            )
            constraints.append(constraint)

        self._constraints_cache = constraints
        return constraints

    def _extract_forbidden_patterns(self, description: str) -> List[str]:
        """
        Extract movement patterns to avoid from constraint description.

        Args:
            description: Constraint description text

        Returns:
            List of forbidden patterns
        """
        patterns = []

        # Common pattern keywords
        pattern_keywords = {
            'deep flexion': 'deep_flexion',
            'rotation under load': 'rotation_under_load',
            'impact': 'high_impact',
            'jumping': 'plyometric',
            'overhead': 'overhead_pressing',
            'heavy loading': 'maximal_loading',
            'ballistic': 'ballistic_movement',
        }

        description_lower = description.lower()
        for keyword, pattern in pattern_keywords.items():
            if keyword in description_lower:
                patterns.append(pattern)

        return patterns

    def _get_biomechanically_forbidden_exercises(self) -> Set[str]:
        """
        Get exercises forbidden based on biomechanical contraindications.

        Uses Movement patterns and JointActions from the graph to determine
        which exercises involve contraindicated movements for known injuries.

        Returns:
            Set of exercise IDs that are biomechanically incompatible
        """
        forbidden = set()

        # Get active injuries from graph
        query = """
        MATCH (i:Injury)
        RETURN i.name as injury_name, i.location as location
        """

        injuries = self.graph.execute_query(query)

        for injury in injuries:
            injury_name = injury['injury_name'].lower()

            # Check if we have contraindication data for this injury
            matching_contraindication = None
            for known_injury, contraindication in INJURY_CONTRAINDICATIONS.items():
                if known_injury.lower() in injury_name or injury_name in known_injury.lower():
                    matching_contraindication = contraindication
                    break

            if not matching_contraindication:
                continue

            avoid_actions = matching_contraindication.get('avoid_actions', [])
            avoid_positions = matching_contraindication.get('avoid_positions', [])

            # Query exercises that involve contraindicated joint actions
            if avoid_actions:
                query = """
                MATCH (e:Exercise)-[:INVOLVES]->(m:Movement)-[:REQUIRES_ACTION]->(ja:JointAction)
                WHERE ja.id IN $action_ids
                RETURN DISTINCT e.id as exercise_id, e.name as exercise_name
                """

                action_ids = [f"JOINT_ACTION:{action.name}" for action in avoid_actions]
                results = self.graph.execute_query(query, {'action_ids': action_ids})

                for r in results:
                    forbidden.add(r['exercise_id'])

            # Query exercises with contraindicated positions
            if avoid_positions:
                for position in avoid_positions:
                    position_query = """
                    MATCH (e:Exercise)
                    WHERE toLower(e.name) CONTAINS $position
                    RETURN e.id as exercise_id
                    """

                    results = self.graph.execute_query(position_query, {
                        'position': position.replace('_', ' ')
                    })

                    for r in results:
                        forbidden.add(r['exercise_id'])

        return forbidden

    def get_forbidden_exercises(self) -> Set[str]:
        """
        Get set of exercise IDs that violate constraints.

        Uses biomechanical movement patterns and joint actions for accurate filtering.

        Returns:
            Set of forbidden exercise IDs
        """
        if self._forbidden_exercises_cache is not None:
            return self._forbidden_exercises_cache

        constraints = self.load_constraints()
        forbidden = set()

        # Method 1: Use biomechanical contraindications
        forbidden.update(self._get_biomechanically_forbidden_exercises())

        # Method 2: Traditional pattern-based filtering (fallback)
        for constraint in constraints:
            # Query exercises that match forbidden patterns
            query = """
            MATCH (e:Exercise)
            WHERE
                toLower(e.name) CONTAINS $location
                OR toLower(e.category) IN $patterns
                OR ANY(muscle IN e.primary_muscles WHERE toLower(muscle) CONTAINS $location)
            RETURN e.id as exercise_id
            """

            location_keywords = constraint.location.lower().split('_')

            results = self.graph.execute_query(query, {
                'location': location_keywords[0] if location_keywords else '',
                'patterns': constraint.forbidden_patterns
            })

            for r in results:
                forbidden.add(r['exercise_id'])

        self._forbidden_exercises_cache = forbidden
        return forbidden

    def is_exercise_allowed(self, exercise_id: str) -> bool:
        """
        Check if an exercise is allowed under current constraints.

        Args:
            exercise_id: Exercise ID to check

        Returns:
            True if allowed, False if forbidden
        """
        forbidden = self.get_forbidden_exercises()
        return exercise_id not in forbidden

    def validate_plan(self, exercise_ids: List[str]) -> Dict[str, List[str]]:
        """
        Validate a workout plan against constraints.

        Args:
            exercise_ids: List of exercise IDs in the plan

        Returns:
            Dictionary with 'allowed' and 'forbidden' exercise lists
        """
        forbidden_set = self.get_forbidden_exercises()

        result = {
            'allowed': [],
            'forbidden': []
        }

        for exercise_id in exercise_ids:
            if exercise_id in forbidden_set:
                result['forbidden'].append(exercise_id)
            else:
                result['allowed'].append(exercise_id)

        return result

    def get_constraint_violations(self, exercise_id: str) -> List[InjuryConstraint]:
        """
        Get all constraints violated by an exercise.

        Args:
            exercise_id: Exercise ID to check

        Returns:
            List of violated constraints
        """
        constraints = self.load_constraints()
        violations = []

        # Get exercise details
        query = """
        MATCH (e:Exercise {id: $exercise_id})
        RETURN e.name as name, e.category as category, e.primary_muscles as muscles
        """

        result = self.graph.execute_query(query, {'exercise_id': exercise_id})

        if not result:
            return violations

        exercise = result[0]

        # Check each constraint
        for constraint in constraints:
            # Simple pattern matching
            name_lower = (exercise.get('name') or '').lower()
            category_lower = (exercise.get('category') or '').lower()
            muscles = exercise.get('muscles', [])

            location_match = any(
                constraint.location.lower() in (muscle or '').lower()
                for muscle in muscles
            )

            pattern_match = any(
                pattern in category_lower
                for pattern in constraint.forbidden_patterns
            )

            if location_match or pattern_match:
                violations.append(constraint)

        return violations

    def check_exercise_biomechanics(self, exercise_id: str) -> Dict:
        """
        Check if an exercise is biomechanically compatible with user injuries.

        Args:
            exercise_id: Exercise ID to check

        Returns:
            Dictionary with compatibility info and warnings
        """
        # Get exercise name for biomechanical lookup
        query = """
        MATCH (e:Exercise {id: $exercise_id})
        RETURN e.name as name
        """

        result = self.graph.execute_query(query, {'exercise_id': exercise_id})

        if not result:
            return {'compatible': True, 'warnings': [], 'reason': 'Exercise not found'}

        exercise_name = result[0]['name']

        # Get movement patterns for this exercise
        movement_patterns = get_movement_patterns_for_exercise(exercise_name)

        if not movement_patterns:
            return {'compatible': True, 'warnings': [], 'reason': 'No movement patterns mapped'}

        # Get active injuries
        injury_query = """
        MATCH (i:Injury)
        RETURN i.name as injury_name
        """

        injuries = self.graph.execute_query(injury_query)

        # Check against each injury
        all_warnings = []
        is_compatible = True

        for injury in injuries:
            injury_name = injury['injury_name'].lower()

            # Find matching contraindication
            for known_injury in INJURY_CONTRAINDICATIONS.keys():
                if known_injury.lower() in injury_name or injury_name in known_injury.lower():
                    compatibility = check_exercise_injury_compatibility(
                        movement_patterns,
                        known_injury
                    )

                    if not compatibility['compatible']:
                        is_compatible = False
                        all_warnings.extend(compatibility.get('warnings', []))

        return {
            'compatible': is_compatible,
            'warnings': all_warnings,
            'movement_patterns': [p.value for p in movement_patterns]
        }

    def suggest_alternatives(self, forbidden_exercise_id: str, limit: int = 5) -> List[Dict]:
        """
        Suggest alternative exercises that respect constraints.

        Uses biomechanical compatibility checking to ensure alternatives
        target the same muscles but use different movement patterns.

        Args:
            forbidden_exercise_id: Exercise ID that violates constraints
            limit: Maximum number of alternatives to return

        Returns:
            List of alternative exercise dictionaries with compatibility info
        """
        # Get target muscles and movement patterns of forbidden exercise
        query = """
        MATCH (e:Exercise {id: $exercise_id})
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        RETURN
            e.name as name,
            e.primary_muscles as target_muscles,
            e.equipment as equipment,
            collect(m.name) as movement_patterns
        """

        result = self.graph.execute_query(query, {'exercise_id': forbidden_exercise_id})

        if not result:
            return []

        target_muscles = result[0].get('target_muscles', [])
        equipment = result[0].get('equipment')
        original_patterns = set(result[0].get('movement_patterns', []))

        # Find alternatives targeting same muscles but different movements
        query = """
        MATCH (e:Exercise)
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        WHERE
            ANY(muscle IN $target_muscles WHERE muscle IN e.primary_muscles)
            AND e.id <> $forbidden_id
        WITH e, collect(m.name) as movements
        RETURN
            e.id as id,
            e.name as name,
            e.primary_muscles as muscles,
            e.equipment as equipment,
            movements
        LIMIT $search_limit
        """

        alternatives = self.graph.execute_query(query, {
            'target_muscles': target_muscles,
            'forbidden_id': forbidden_exercise_id,
            'search_limit': limit * 3  # Get extra to filter
        })

        # Score and filter alternatives
        scored_alternatives = []
        forbidden_set = self.get_forbidden_exercises()

        for alt in alternatives:
            # Skip if forbidden
            if alt['id'] in forbidden_set:
                continue

            # Check biomechanical compatibility
            biomech_check = self.check_exercise_biomechanics(alt['id'])

            if not biomech_check['compatible']:
                continue

            # Calculate preference score
            alt_patterns = set(alt.get('movements', []))

            # Prefer exercises with different movement patterns
            pattern_difference = len(alt_patterns - original_patterns)
            equipment_match = 1.0 if alt['equipment'] == equipment else 0.5

            score = pattern_difference * 2 + equipment_match

            scored_alternatives.append({
                **alt,
                'score': score,
                'movement_patterns': list(alt_patterns),
                'biomech_warnings': biomech_check.get('warnings', [])
            })

        # Sort by score and return top N
        scored_alternatives.sort(key=lambda x: x['score'], reverse=True)

        return scored_alternatives[:limit]

    def clear_cache(self):
        """Clear cached constraints (call after injury updates)."""
        self._constraints_cache = None
        self._forbidden_exercises_cache = None
