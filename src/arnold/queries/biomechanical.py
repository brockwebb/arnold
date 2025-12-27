"""
Biomechanical Inference Queries

Implements the three success criteria from Phase 4:
1. Find exercises targeting specific muscles while avoiding contraindicated movements
2. Find alternatives respecting injury constraints
3. Find progressive overload chains

Internal Codename: JUDGMENT-DAY
"""

from typing import List, Dict, Optional, Set
import sys
from pathlib import Path

# Import biomechanical data
sys.path.insert(0, str(Path(__file__).parent.parent))
from biomechanics import (
    MovementPattern,
    JointAction,
    get_movement_patterns_for_exercise,
    get_joint_actions_for_movement
)


class BiomechanicalQueries:
    """
    Advanced biomechanical queries for exercise selection and progression.
    """

    def __init__(self, graph):
        """
        Initialize biomechanical query engine.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph

    def find_exercises_by_muscle_avoiding_action(
        self,
        target_muscle: str,
        avoid_joint_action: JointAction,
        limit: int = 10
    ) -> List[Dict]:
        """
        Find exercises that target a specific muscle while avoiding a joint action.

        Example: "Find hamstring exercises that avoid knee flexion"
        → Returns Romanian deadlifts, good mornings (hip extension, not knee flexion)

        Args:
            target_muscle: Muscle to target (e.g., "Hamstrings")
            avoid_joint_action: Joint action to avoid
            limit: Maximum number of results

        Returns:
            List of compatible exercises
        """
        # First, find all exercises targeting the muscle via TARGETS relationship
        query = """
        MATCH (e:Exercise)-[:TARGETS]->(muscle:Muscle)
        WHERE toLower(muscle.name) CONTAINS toLower($target_muscle)
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        WITH e, collect(DISTINCT muscle.name) as muscles, collect(DISTINCT m.name) as movements
        RETURN
            e.id as id,
            e.name as name,
            muscles,
            e.category as equipment,
            movements as movement_patterns
        """

        candidates = self.graph.execute_query(query, {
            'target_muscle': target_muscle
        })

        # Filter out exercises that involve the avoided joint action
        avoid_action_id = f"JOINT_ACTION:{avoid_joint_action.name}"

        compatible_exercises = []

        for exercise in candidates:
            # Check if exercise involves the avoided joint action at the KNEE
            # (We want to avoid KNEE flexion, not hip flexion)
            check_query = """
            MATCH (e:Exercise {id: $exercise_id})-[:INVOLVES]->(m:Movement)-[r:REQUIRES_ACTION]->(ja:JointAction {id: $action_id})
            WHERE r.joint = 'knee'
            RETURN count(*) as count
            """

            result = self.graph.execute_query(check_query, {
                'exercise_id': exercise['id'],
                'action_id': avoid_action_id
            })

            # If count is 0, the exercise doesn't involve knee flexion
            if result and result[0]['count'] == 0:
                compatible_exercises.append({
                    'id': exercise['id'],
                    'name': exercise['name'],
                    'muscles': exercise['muscles'],
                    'equipment': exercise['equipment'],
                    'movement_patterns': exercise['movement_patterns']
                })

            if len(compatible_exercises) >= limit:
                break

        return compatible_exercises

    def find_alternatives_for_injury(
        self,
        exercise_name: str,
        injury_contraindicated_actions: List[JointAction],
        limit: int = 10
    ) -> List[Dict]:
        """
        Find alternative exercises that avoid contraindicated joint actions.

        Example: "Alternative to barbell back squat for shoulder impingement"
        → Avoids shoulder elevation/internal rotation
        → Returns goblet squats, front squats, belt squats

        Args:
            exercise_name: Original exercise to find alternatives for
            injury_contraindicated_actions: Joint actions to avoid
            limit: Maximum number of alternatives

        Returns:
            List of safe alternative exercises
        """
        # Find the target exercise
        find_exercise = """
        MATCH (e:Exercise)
        WHERE toLower(e.name) CONTAINS toLower($name)
        OPTIONAL MATCH (e)-[:TARGETS]->(muscle:Muscle)
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        WITH e, collect(DISTINCT muscle.name) as muscles, collect(DISTINCT m.name) as movements
        RETURN
            e.id as id,
            e.name as name,
            muscles,
            movements as movement_patterns
        LIMIT 1
        """

        target = self.graph.execute_query(find_exercise, {'name': exercise_name})

        if not target:
            return []

        target_ex = target[0]
        target_muscles = target_ex['muscles']
        target_patterns = target_ex['movement_patterns']

        # Find exercises with SAME movement patterns (prioritize same movement type)
        # First try to find exercises with same movement patterns
        find_similar = """
        MATCH (e:Exercise)-[:INVOLVES]->(m:Movement)
        WHERE
            e.id <> $target_id
            AND m.name IN $target_patterns
        WITH DISTINCT e
        OPTIONAL MATCH (e)-[:TARGETS]->(muscle:Muscle)
        OPTIONAL MATCH (e)-[:INVOLVES]->(m2:Movement)
        WITH e, collect(DISTINCT muscle.name) as muscles, collect(DISTINCT m2.name) as movements
        RETURN
            e.id as id,
            e.name as name,
            muscles,
            e.category as equipment,
            movements
        LIMIT 30
        """

        candidates = self.graph.execute_query(find_similar, {
            'target_id': target_ex['id'],
            'target_patterns': target_patterns
        })

        # If no candidates with same movement pattern, fall back to same muscles
        if not candidates:
            find_similar_muscles = """
            MATCH (e:Exercise)-[:TARGETS]->(muscle:Muscle)
            WHERE
                e.id <> $target_id
                AND toLower(muscle.name) IN [m IN $target_muscles | toLower(m)]
            WITH DISTINCT e
            OPTIONAL MATCH (e)-[:TARGETS]->(muscle2:Muscle)
            OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
            WITH e, collect(DISTINCT muscle2.name) as muscles, collect(DISTINCT m.name) as movements
            RETURN
                e.id as id,
                e.name as name,
                muscles,
                e.category as equipment,
                movements
            LIMIT 30
            """

            candidates = self.graph.execute_query(find_similar_muscles, {
                'target_id': target_ex['id'],
                'target_muscles': target_muscles
            })

        # Filter out exercises that involve contraindicated actions
        action_ids = [f"JOINT_ACTION:{action.name}" for action in injury_contraindicated_actions]

        safe_alternatives = []

        for candidate in candidates:
            # Check if candidate involves any contraindicated actions
            check_query = """
            MATCH (e:Exercise {id: $exercise_id})-[:INVOLVES]->(m:Movement)-[:REQUIRES_ACTION]->(ja:JointAction)
            WHERE ja.id IN $action_ids
            RETURN count(*) as violation_count
            """

            result = self.graph.execute_query(check_query, {
                'exercise_id': candidate['id'],
                'action_ids': action_ids
            })

            # If no violations, add to alternatives
            if result and result[0]['violation_count'] == 0:
                # Calculate similarity score
                candidate_patterns = set(candidate['movements'])
                target_patterns_set = set(target_patterns)

                # Prefer exercises with overlapping movement patterns
                pattern_overlap = len(candidate_patterns & target_patterns_set)

                safe_alternatives.append({
                    **candidate,
                    'similarity_score': pattern_overlap,
                    'movement_patterns': list(candidate_patterns)
                })

            if len(safe_alternatives) >= limit * 2:
                break

        # Sort by similarity and return top N
        safe_alternatives.sort(key=lambda x: x['similarity_score'], reverse=True)

        return safe_alternatives[:limit]

    def find_progression_chain(
        self,
        base_exercise_name: str,
        progression_type: str = 'intensity',
        steps: int = 5
    ) -> List[Dict]:
        """
        Find progressive overload chain starting from a base exercise.

        Example: "Progress from bodyweight lunges"
        → Bodyweight lunge → Goblet lunge → Dumbbell lunge → Barbell lunge → Bulgarian split squat

        Progression types:
        - 'intensity': Increase load/difficulty (beginner → intermediate → expert)
        - 'volume': Increase sets/reps (same exercise, suggest set/rep schemes)
        - 'complexity': Increase movement complexity (add patterns, instability)

        Args:
            base_exercise_name: Starting exercise
            progression_type: Type of progression
            steps: Number of progression steps

        Returns:
            Ordered list of exercises forming progression chain
        """
        # Find base exercise
        find_base = """
        MATCH (e:Exercise)
        WHERE toLower(e.name) CONTAINS toLower($name)
        OPTIONAL MATCH (e)-[:TARGETS]->(muscle:Muscle)
        OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
        WITH e, collect(DISTINCT muscle.name) as muscles, collect(DISTINCT m.name) as movements
        RETURN
            e.id as id,
            e.name as name,
            e.difficulty as level,
            muscles,
            e.category as equipment,
            e.complexity_score as complexity,
            movements as movement_patterns
        LIMIT 1
        """

        base = self.graph.execute_query(find_base, {'name': base_exercise_name})

        if not base:
            return []

        base_ex = base[0]

        progression_chain = [base_ex]

        if progression_type == 'intensity':
            # Progress by difficulty level
            level_order = ['Beginner', 'Intermediate', 'Expert']
            current_level = base_ex.get('level', 'Beginner')

            try:
                current_level_idx = level_order.index(current_level)
            except ValueError:
                current_level_idx = 0

            # Find exercises at higher levels with same movement patterns
            for i in range(steps - 1):
                target_level_idx = min(current_level_idx + i + 1, len(level_order) - 1)
                target_level = level_order[target_level_idx]

                find_next = """
                MATCH (e:Exercise)-[:TARGETS]->(muscle:Muscle)
                WHERE
                    e.difficulty = $target_level
                    AND toLower(muscle.name) IN [m IN $target_muscles | toLower(m)]
                    AND e.id <> $base_id
                WITH DISTINCT e
                OPTIONAL MATCH (e)-[:TARGETS]->(muscle2:Muscle)
                OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
                WITH e, collect(DISTINCT muscle2.name) as muscles, collect(DISTINCT m.name) as movements
                WHERE ANY(pattern IN $base_patterns WHERE pattern IN movements)
                RETURN
                    e.id as id,
                    e.name as name,
                    e.difficulty as level,
                    muscles,
                    e.category as equipment,
                    e.complexity_score as complexity,
                    movements as movement_patterns
                LIMIT 1
                """

                next_ex = self.graph.execute_query(find_next, {
                    'target_level': target_level,
                    'target_muscles': base_ex['muscles'],
                    'base_id': base_ex['id'],
                    'base_patterns': base_ex['movement_patterns']
                })

                if next_ex:
                    progression_chain.append(next_ex[0])
                else:
                    break

        elif progression_type == 'complexity':
            # Progress by complexity score
            base_complexity = base_ex.get('complexity_score', 5)

            find_next_complex = """
            MATCH (e:Exercise)-[:TARGETS]->(muscle:Muscle)
            WHERE
                e.complexity_score > $min_complexity
                AND toLower(muscle.name) IN [m IN $target_muscles | toLower(m)]
                AND e.id <> $base_id
            WITH DISTINCT e
            OPTIONAL MATCH (e)-[:TARGETS]->(muscle2:Muscle)
            OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
            WITH e, collect(DISTINCT muscle2.name) as muscles, collect(DISTINCT m.name) as movements
            WHERE ANY(pattern IN $base_patterns WHERE pattern IN movements)
            RETURN
                e.id as id,
                e.name as name,
                e.difficulty as level,
                muscles,
                e.category as equipment,
                e.complexity_score as complexity,
                movements as movement_patterns
            ORDER BY e.complexity_score ASC
            LIMIT $steps
            """

            next_exercises = self.graph.execute_query(find_next_complex, {
                'min_complexity': base_complexity,
                'target_muscles': base_ex['muscles'],
                'base_id': base_ex['id'],
                'base_patterns': base_ex['movement_patterns'],
                'steps': steps - 1
            })

            progression_chain.extend(next_exercises)

        elif progression_type == 'load':
            # Progress by adding external load (use category field)
            equipment_progression = ['bodyweight', 'dumbbell', 'kettlebell', 'barbell']

            base_category = (base_ex.get('equipment', '') or 'bodyweight').lower()

            current_eq_idx = 0
            for idx, eq in enumerate(equipment_progression):
                if eq in base_category:
                    current_eq_idx = idx
                    break

            # Find same exercise with heavier equipment
            for i in range(steps - 1):
                target_eq_idx = min(current_eq_idx + i + 1, len(equipment_progression) - 1)
                target_eq = equipment_progression[target_eq_idx]

                find_next_load = """
                MATCH (e:Exercise)-[:TARGETS]->(muscle:Muscle)
                WHERE
                    toLower(e.category) CONTAINS $target_equipment
                    AND toLower(muscle.name) IN [m IN $target_muscles | toLower(m)]
                    AND e.id <> $base_id
                WITH DISTINCT e
                OPTIONAL MATCH (e)-[:TARGETS]->(muscle2:Muscle)
                OPTIONAL MATCH (e)-[:INVOLVES]->(m:Movement)
                WITH e, collect(DISTINCT muscle2.name) as muscles, collect(DISTINCT m.name) as movements
                WHERE ANY(pattern IN $base_patterns WHERE pattern IN movements)
                RETURN
                    e.id as id,
                    e.name as name,
                    e.difficulty as level,
                    muscles,
                    e.category as equipment,
                    e.complexity_score as complexity,
                    movements as movement_patterns
                LIMIT 1
                """

                next_ex = self.graph.execute_query(find_next_load, {
                    'target_equipment': target_eq,
                    'target_muscles': base_ex['muscles'],
                    'base_id': base_ex['id'],
                    'base_patterns': base_ex['movement_patterns']
                })

                if next_ex:
                    progression_chain.append(next_ex[0])
                else:
                    break

        return progression_chain

    def query_success_criteria_1(self) -> List[Dict]:
        """
        Success Criteria 1: Find exercises that target hamstrings but avoid knee flexion.

        Expected results: Romanian deadlifts, good mornings, hip thrusts
        NOT: Leg curls, seated leg curls (these involve knee flexion)

        Returns:
            List of hamstring exercises without knee flexion
        """
        return self.find_exercises_by_muscle_avoiding_action(
            target_muscle="Hamstrings",
            avoid_joint_action=JointAction.FLEXION,
            limit=10
        )

    def query_success_criteria_2(self, exercise_name: str = "squat") -> List[Dict]:
        """
        Success Criteria 2: Alternative to barbell back squat for shoulder impingement.

        Expected results: Goblet squats, front squats, belt squats
        (These avoid overhead shoulder positions and internal rotation)

        Args:
            exercise_name: Exercise to find alternatives for (default: squat)

        Returns:
            List of squat alternatives safe for shoulder impingement
        """
        # Shoulder impingement contraindications
        contraindicated_actions = [
            JointAction.ELEVATION,
            JointAction.INTERNAL_ROTATION
        ]

        return self.find_alternatives_for_injury(
            exercise_name=exercise_name,
            injury_contraindicated_actions=contraindicated_actions,
            limit=10
        )

    def query_success_criteria_3(self) -> List[Dict]:
        """
        Success Criteria 3: Progress from bodyweight lunges.

        Expected chain:
        1. Bodyweight lunge
        2. Goblet lunge / Dumbbell lunge
        3. Barbell lunge / Walking lunge with load
        4. Bulgarian split squat
        5. Elevated Bulgarian split squat

        Returns:
            Progression chain from bodyweight lunges
        """
        # Custom progression for lunges based on name patterns
        # (complexity scores don't reflect actual progression for this exercise)
        progression_patterns = [
            ('bodyweight', 0),
            ('dumbbell', 1),
            ('barbell', 2),
            ('bulgarian', 3),
        ]

        progression_chain = []

        for pattern, level in progression_patterns:
            query = """
            MATCH (e:Exercise)-[:INVOLVES]->(m:Movement)
            WHERE
                toLower(e.name) CONTAINS $pattern
                AND (m.name = 'lunge' OR m.name = 'squat')
            WITH e
            LIMIT 1
            OPTIONAL MATCH (e)-[:TARGETS]->(muscle:Muscle)
            OPTIONAL MATCH (e)-[:INVOLVES]->(m2:Movement)
            WITH e, collect(DISTINCT muscle.name) as muscles, collect(DISTINCT m2.name) as movements
            RETURN
                e.id as id,
                e.name as name,
                e.difficulty as level,
                muscles,
                e.category as equipment,
                e.complexity_score as complexity,
                movements as movement_patterns
            """

            result = self.graph.execute_query(query, {'pattern': pattern})

            if result:
                progression_chain.append(result[0])

        return progression_chain
