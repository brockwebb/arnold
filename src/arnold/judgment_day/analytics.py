"""
Progression Analysis

Internal Codename: JUDGMENT-DAY
Analyzes training history and tracks progression metrics.
"""

from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
from collections import defaultdict


class ProgressionAnalyzer:
    """
    Analyzes training progression and provides insights.

    Tracks:
    - Volume trends (tonnage over time)
    - Exercise-specific progression (weight, reps, estimated 1RM)
    - Muscle group balance
    - Stagnation detection
    - Overtraining signals
    """

    def __init__(self, graph):
        """
        Initialize progression analyzer.

        Args:
            graph: ArnoldGraph instance
        """
        self.graph = graph

    def get_volume_trend(self, weeks: int = 12) -> List[Dict]:
        """
        Get weekly training volume trend.

        Args:
            weeks: Number of weeks to analyze

        Returns:
            List of {week, tonnage, sets} dictionaries
        """
        query = """
        MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)
        WHERE w.date >= date() - duration({weeks: $weeks})
        WITH date.truncate('week', w.date) as week,
             sum(COALESCE(ei.max_weight, 0) * COALESCE(ei.total_reps, 0)) as tonnage,
             sum(COALESCE(ei.total_sets, 0)) as sets
        RETURN week, tonnage, sets
        ORDER BY week
        """

        results = self.graph.execute_query(query, {'weeks': weeks})

        return [
            {
                'week': r['week'],
                'tonnage': r['tonnage'],
                'sets': r['sets']
            }
            for r in results
        ]

    def get_exercise_progression(
        self,
        exercise_name: str,
        weeks: int = 12
    ) -> List[Dict]:
        """
        Get progression data for a specific exercise.

        Args:
            exercise_name: Exercise name (fuzzy matched)
            weeks: Number of weeks to analyze

        Returns:
            List of workout records with date, weight, reps, sets, RPE
        """
        query = """
        MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)
        WHERE toLower(ei.exercise_name_raw) CONTAINS toLower($exercise_name)
          AND w.date >= date() - duration({weeks: $weeks})
        OPTIONAL MATCH (ei)-[:INSTANCE_OF]->(e:Exercise)
        RETURN
            w.date as date,
            ei.exercise_name_raw as name,
            e.name as canonical_name,
            ei.max_weight as weight,
            ei.total_reps as reps,
            ei.total_sets as sets,
            w.perceived_intensity as rpe
        ORDER BY w.date
        """

        results = self.graph.execute_query(query, {'exercise_name': exercise_name, 'weeks': weeks})

        progression = []
        for r in results:
            # Calculate estimated 1RM using Epley formula
            weight = r.get('weight', 0)
            reps = r.get('reps', 0)
            sets = r.get('sets', 0)

            if weight and reps:
                # Assume reps = total_reps / total_sets
                reps_per_set = reps / sets if sets > 0 else reps
                estimated_1rm = weight * (1 + reps_per_set / 30)
            else:
                estimated_1rm = None

            progression.append({
                'date': r['date'],
                'name': r['name'],
                'canonical_name': r.get('canonical_name'),
                'weight': weight,
                'reps': reps,
                'sets': sets,
                'rpe': r.get('rpe'),
                'estimated_1rm': estimated_1rm
            })

        return progression

    def get_muscle_group_balance(self, weeks: int = 4) -> Dict[str, float]:
        """
        Analyze volume distribution across muscle groups.

        Args:
            weeks: Number of weeks to analyze

        Returns:
            Dictionary of {muscle_group: volume_percentage}
        """
        query = """
        MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)-[:INSTANCE_OF]->(e:Exercise)
        WHERE w.date >= date() - duration({weeks: $weeks})
        UNWIND e.primary_muscles as muscle
        WITH muscle,
             sum(COALESCE(ei.max_weight, 0) * COALESCE(ei.total_reps, 0)) as volume
        RETURN muscle, volume
        ORDER BY volume DESC
        """

        results = self.graph.execute_query(query, {'weeks': weeks})

        if not results:
            return {}

        # Calculate total volume
        total_volume = sum(r['volume'] for r in results)

        if total_volume == 0:
            return {}

        # Calculate percentages
        balance = {
            r['muscle']: (r['volume'] / total_volume) * 100
            for r in results
        }

        return balance

    def detect_stagnation(
        self,
        exercise_name: str,
        weeks: int = 4
    ) -> Dict[str, any]:
        """
        Detect if an exercise has stagnated (no PR).

        Args:
            exercise_name: Exercise name
            weeks: Number of weeks to check

        Returns:
            Dictionary with stagnation analysis
        """
        progression = self.get_exercise_progression(exercise_name, weeks)

        if not progression:
            return {
                'stagnant': False,
                'reason': 'No data available',
                'recommendation': 'Start tracking this exercise'
            }

        # Check for improvement in any metric
        weights = [p['weight'] for p in progression if p['weight']]
        estimated_1rms = [p['estimated_1rm'] for p in progression if p['estimated_1rm']]

        if not weights:
            return {
                'stagnant': False,
                'reason': 'Insufficient weight data',
                'recommendation': 'Continue training and track weights'
            }

        # Compare recent performance to earlier
        mid_point = len(weights) // 2
        early_max = max(weights[:mid_point]) if mid_point > 0 else 0
        recent_max = max(weights[mid_point:])

        improvement = ((recent_max - early_max) / early_max * 100) if early_max > 0 else 0

        if improvement < 2:  # Less than 2% improvement
            return {
                'stagnant': True,
                'reason': f'Less than 2% improvement in {weeks} weeks',
                'early_max': early_max,
                'recent_max': recent_max,
                'improvement_pct': improvement,
                'recommendation': 'Consider deload or variation'
            }

        return {
            'stagnant': False,
            'improvement_pct': improvement,
            'early_max': early_max,
            'recent_max': recent_max,
            'recommendation': 'Keep progressing'
        }

    def detect_overtraining(self, weeks: int = 4) -> Dict[str, any]:
        """
        Detect overtraining signals.

        Checks for:
        - High deviation frequency
        - Consistently high RPE
        - Decreasing performance despite high effort

        Args:
            weeks: Number of weeks to analyze

        Returns:
            Dictionary with overtraining analysis
        """
        query = """
        MATCH (w:Workout)
        WHERE w.date >= date() - duration({weeks: $weeks})
        RETURN
            count(w) as total_workouts,
            avg(w.perceived_intensity) as avg_rpe,
            sum(CASE WHEN size(w.deviations) > 0 THEN 1 ELSE 0 END) as deviation_count,
            collect(w.perceived_intensity) as rpe_values
        """

        result = self.graph.execute_query(query, {'weeks': weeks})

        if not result:
            return {'overtraining_risk': 'low', 'signals': []}

        r = result[0]
        total = r['total_workouts']
        avg_rpe = r.get('avg_rpe', 0)
        deviation_count = r.get('deviation_count', 0)
        rpe_values = r.get('rpe_values', [])

        # Filter out None values
        rpe_values = [rpe for rpe in rpe_values if rpe is not None]

        signals = []

        # Check 1: High average RPE
        if avg_rpe and avg_rpe > 7.5:
            signals.append(f'High average RPE: {avg_rpe:.1f}')

        # Check 2: High deviation rate
        if total > 0:
            deviation_rate = deviation_count / total
            if deviation_rate > 0.25:  # More than 25% deviations
                signals.append(f'High deviation rate: {deviation_rate*100:.0f}%')

        # Check 3: Increasing RPE trend
        if len(rpe_values) >= 4:
            mid = len(rpe_values) // 2
            early_avg = sum(rpe_values[:mid]) / mid
            recent_avg = sum(rpe_values[mid:]) / (len(rpe_values) - mid)

            if recent_avg > early_avg + 0.5:
                signals.append(f'Increasing RPE trend: {early_avg:.1f} → {recent_avg:.1f}')

        # Determine risk level
        if len(signals) >= 2:
            risk = 'high'
        elif len(signals) == 1:
            risk = 'moderate'
        else:
            risk = 'low'

        return {
            'overtraining_risk': risk,
            'signals': signals,
            'avg_rpe': avg_rpe,
            'deviation_rate': (deviation_count / total * 100) if total > 0 else 0,
            'recommendation': self._get_overtraining_recommendation(risk)
        }

    def _get_overtraining_recommendation(self, risk: str) -> str:
        """Get recommendation based on overtraining risk."""
        recommendations = {
            'low': 'Continue training as planned',
            'moderate': 'Consider reducing volume by 10-20% next week',
            'high': 'Take a deload week - reduce volume by 50% and intensity by 20%'
        }
        return recommendations.get(risk, 'Monitor training load')

    def get_recent_workouts(self, limit: int = 10) -> List[Dict]:
        """
        Get recent workout summaries.

        Args:
            limit: Number of workouts to return

        Returns:
            List of workout summaries
        """
        query = """
        MATCH (w:Workout)
        OPTIONAL MATCH (w)-[:CONTAINS]->(ei:ExerciseInstance)
        WITH w, count(ei) as exercise_count
        RETURN
            w.id as id,
            w.date as date,
            w.type as type,
            w.periodization_phase as phase,
            w.perceived_intensity as rpe,
            w.tags_raw as tags,
            exercise_count
        ORDER BY w.date DESC
        LIMIT $limit
        """

        results = self.graph.execute_query(query, {'limit': limit})

        return [
            {
                'id': r['id'],
                'date': r['date'],
                'type': r['type'],
                'phase': r.get('phase'),
                'rpe': r.get('rpe'),
                'tags': r.get('tags', []),
                'exercise_count': r['exercise_count']
            }
            for r in results
        ]

    def get_summary_stats(self, weeks: int = 4) -> Dict:
        """
        Get summary statistics for recent training.

        Args:
            weeks: Number of weeks to analyze

        Returns:
            Dictionary of summary statistics
        """
        query = """
        MATCH (w:Workout)
        WHERE w.date >= date() - duration({weeks: $weeks})
        OPTIONAL MATCH (w)-[:CONTAINS]->(ei:ExerciseInstance)
        RETURN
            count(DISTINCT w) as total_workouts,
            count(ei) as total_exercises,
            sum(ei.total_sets) as total_sets,
            avg(w.perceived_intensity) as avg_rpe,
            sum(ei.max_weight * ei.total_reps) as total_tonnage
        """

        result = self.graph.execute_query(query, {'weeks': weeks})

        if not result:
            return {}

        return {
            'weeks': weeks,
            'total_workouts': result[0]['total_workouts'],
            'total_exercises': result[0]['total_exercises'],
            'total_sets': result[0]['total_sets'],
            'avg_rpe': result[0].get('avg_rpe'),
            'total_tonnage': result[0].get('total_tonnage', 0)
        }
