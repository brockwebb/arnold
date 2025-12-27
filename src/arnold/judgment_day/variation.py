"""
Exercise Variation Suggester

Internal Codename: JUDGMENT-DAY
Suggests exercise variations based on muscle targets, equipment, and novelty.
"""

from typing import List, Dict, Optional, Set
from datetime import date, timedelta


class ExerciseVariationSuggester:
    """
    Suggests exercise variations and alternatives.

    Selection criteria:
    - Same muscle group targets
    - Available equipment
    - Novelty (not done recently)
    - Progression/regression variants
    - Injury constraint compliance
    """

    def __init__(self, graph):
        """
        Initialize variation suggester.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph

    def suggest_variations(
        self,
        exercise_name: str,
        limit: int = 5,
        equipment_only: Optional[List[str]] = None,
        exclude_recent_days: int = 14
    ) -> List[Dict]:
        """
        Suggest variations for an exercise.

        Args:
            exercise_name: Exercise to find variations for
            limit: Maximum number of suggestions
            equipment_only: List of equipment IDs to filter by (None = user's equipment)
            exclude_recent_days: Don't suggest exercises done in last N days

        Returns:
            List of exercise variation dictionaries
        """
        # Get target exercise details
        query = """
        MATCH (e:Exercise)
        WHERE toLower(e.name) CONTAINS toLower($exercise_name)
        RETURN
            e.id as id,
            e.name as name,
            e.primary_muscles as muscles,
            e.equipment as equipment,
            e.category as category
        LIMIT 1
        """

        result = self.graph.execute_query(query, {'exercise_name': exercise_name})

        if not result:
            return []

        target = result[0]
        target_muscles = target.get('muscles', [])
        target_category = target.get('category')

        # Get recently performed exercises to exclude
        recent_exercises = self._get_recent_exercises(exclude_recent_days)

        # Find variations targeting same muscles
        query = """
        MATCH (e:Exercise)
        WHERE
            e.id <> $target_id
            AND ANY(muscle IN $target_muscles WHERE muscle IN e.primary_muscles)
            AND NOT e.id IN $recent_exercises
        OPTIONAL MATCH (u:User)-[:HAS_EQUIPMENT]->(eq:Equipment)
        WHERE e.equipment = eq.name OR e.equipment = 'Body Only'
        WITH e, count(eq) as equipment_available
        WHERE equipment_available > 0 OR e.equipment = 'Body Only'
        RETURN
            e.id as id,
            e.name as name,
            e.primary_muscles as muscles,
            e.secondary_muscles as secondary_muscles,
            e.equipment as equipment,
            e.category as category,
            e.level as level
        LIMIT $limit
        """

        variations = self.graph.execute_query(query, {
            'target_id': target['id'],
            'target_muscles': target_muscles,
            'recent_exercises': list(recent_exercises),
            'limit': limit * 2  # Get extra to filter
        })

        # Calculate relevance score for each variation
        scored_variations = []
        for v in variations:
            score = self._calculate_relevance_score(
                target_muscles,
                v['muscles'],
                v.get('secondary_muscles', []),
                target_category,
                v.get('category')
            )

            scored_variations.append({
                **v,
                'relevance_score': score
            })

        # Sort by relevance and return top N
        scored_variations.sort(key=lambda x: x['relevance_score'], reverse=True)

        return scored_variations[:limit]

    def _calculate_relevance_score(
        self,
        target_muscles: List[str],
        candidate_primary: List[str],
        candidate_secondary: List[str],
        target_category: str,
        candidate_category: str
    ) -> float:
        """Calculate relevance score for a variation candidate."""
        score = 0.0

        # Primary muscle overlap (most important)
        if target_muscles and candidate_primary:
            overlap = len(set(target_muscles) & set(candidate_primary))
            score += (overlap / len(target_muscles)) * 10

        # Secondary muscle bonus
        if target_muscles and candidate_secondary:
            overlap = len(set(target_muscles) & set(candidate_secondary))
            score += (overlap / len(target_muscles)) * 3

        # Same category bonus
        if target_category and candidate_category == target_category:
            score += 2

        return score

    def _get_recent_exercises(self, days: int = 14) -> Set[str]:
        """Get set of exercise IDs performed recently."""
        query = """
        MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e:Exercise)
        WHERE w.date >= date() - duration({days: $days})
        RETURN DISTINCT e.id as exercise_id
        """

        results = self.graph.execute_query(query, {'days': days})

        return {r['exercise_id'] for r in results}

    def suggest_progressions(
        self,
        exercise_name: str,
        direction: str = 'harder',
        limit: int = 3
    ) -> List[Dict]:
        """
        Suggest progressions (harder) or regressions (easier) of an exercise.

        Args:
            exercise_name: Exercise to progress/regress
            direction: 'harder' or 'easier'
            limit: Maximum number of suggestions

        Returns:
            List of progression/regression exercises
        """
        # Get target exercise level
        query = """
        MATCH (e:Exercise)
        WHERE toLower(e.name) CONTAINS toLower($exercise_name)
        RETURN
            e.id as id,
            e.name as name,
            e.level as level,
            e.primary_muscles as muscles,
            e.equipment as equipment
        LIMIT 1
        """

        result = self.graph.execute_query(query, {'exercise_name': exercise_name})

        if not result:
            return []

        target = result[0]
        current_level = target.get('level', 'Intermediate')

        # Define level progressions
        level_map = {
            'Beginner': 0,
            'Intermediate': 1,
            'Expert': 2
        }

        current_level_num = level_map.get(current_level, 1)

        if direction == 'harder':
            target_levels = [k for k, v in level_map.items() if v > current_level_num]
        else:  # easier
            target_levels = [k for k, v in level_map.items() if v < current_level_num]

        if not target_levels:
            return []

        # Find exercises at target level with same muscles
        query = """
        MATCH (e:Exercise)
        WHERE
            e.id <> $target_id
            AND e.level IN $target_levels
            AND ANY(muscle IN $muscles WHERE muscle IN e.primary_muscles)
        RETURN
            e.id as id,
            e.name as name,
            e.level as level,
            e.primary_muscles as muscles,
            e.equipment as equipment
        LIMIT $limit
        """

        progressions = self.graph.execute_query(query, {
            'target_id': target['id'],
            'target_levels': target_levels,
            'muscles': target.get('muscles', []),
            'limit': limit
        })

        return progressions

    def suggest_by_muscle_group(
        self,
        muscle_group: str,
        limit: int = 10,
        exclude_recent_days: int = 7
    ) -> List[Dict]:
        """
        Suggest exercises targeting a specific muscle group.

        Args:
            muscle_group: Muscle group name (e.g., 'Quadriceps', 'Chest')
            limit: Maximum number of suggestions
            exclude_recent_days: Don't suggest exercises done in last N days

        Returns:
            List of exercises targeting the muscle group
        """
        recent_exercises = self._get_recent_exercises(exclude_recent_days)

        query = """
        MATCH (e:Exercise)
        WHERE
            ANY(muscle IN e.primary_muscles WHERE toLower(muscle) CONTAINS toLower($muscle_group))
            AND NOT e.id IN $recent_exercises
        OPTIONAL MATCH (u:User)-[:HAS_EQUIPMENT]->(eq:Equipment)
        WHERE e.equipment = eq.name OR e.equipment = 'Body Only'
        WITH e, count(eq) as equipment_available
        WHERE equipment_available > 0 OR e.equipment = 'Body Only'
        RETURN
            e.id as id,
            e.name as name,
            e.primary_muscles as muscles,
            e.equipment as equipment,
            e.category as category,
            e.level as level
        LIMIT $limit
        """

        exercises = self.graph.execute_query(query, {
            'muscle_group': muscle_group,
            'recent_exercises': list(recent_exercises),
            'limit': limit
        })

        return exercises

    def suggest_for_equipment(
        self,
        equipment_name: str,
        limit: int = 10,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        Suggest exercises using specific equipment.

        Args:
            equipment_name: Equipment name
            limit: Maximum number of suggestions
            category: Optional category filter (e.g., 'Strength')

        Returns:
            List of exercises using the equipment
        """
        query = """
        MATCH (e:Exercise)
        WHERE toLower(e.equipment) CONTAINS toLower($equipment_name)
        """

        if category:
            query += " AND toLower(e.category) = toLower($category)"

        query += """
        RETURN
            e.id as id,
            e.name as name,
            e.primary_muscles as muscles,
            e.equipment as equipment,
            e.category as category,
            e.level as level
        LIMIT $limit
        """

        params = {
            'equipment_name': equipment_name,
            'limit': limit
        }

        if category:
            params['category'] = category

        exercises = self.graph.execute_query(query, params)

        return exercises

    def get_novelty_score(self, exercise_id: str, days: int = 30) -> float:
        """
        Calculate novelty score for an exercise (0-10).

        Higher score = not done recently (more novel)

        Args:
            exercise_id: Exercise ID
            days: Days to look back

        Returns:
            Novelty score (0-10)
        """
        query = """
        MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e:Exercise {id: $exercise_id})
        WHERE w.date >= date() - duration({days: $days})
        WITH w.date as last_date
        ORDER BY last_date DESC
        LIMIT 1
        RETURN last_date
        """

        result = self.graph.execute_query(query, {
            'exercise_id': exercise_id,
            'days': days
        })

        if not result or not result[0]['last_date']:
            return 10.0  # Never done = maximum novelty

        last_date_str = result[0]['last_date']
        last_date = date.fromisoformat(last_date_str) if isinstance(last_date_str, str) else last_date_str

        days_since = (date.today() - last_date).days

        # Score: 0 if done today, 10 if done 30+ days ago
        score = min(10.0, (days_since / days) * 10)

        return score
