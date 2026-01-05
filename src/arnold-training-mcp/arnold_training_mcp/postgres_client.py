"""Postgres client for Arnold training/workout operations.

Per ADR-002: Executed workouts live in Postgres (facts/measurements).
Plans stay in Neo4j (intentions/relationships).
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PostgresTrainingClient:
    """Postgres client for executed workout operations."""

    def __init__(self):
        """Initialize Postgres connection."""
        self.dsn = os.environ.get(
            "POSTGRES_DSN",
            "postgresql://brock@localhost:5432/arnold_analytics"
        )
        self._conn = None

    @property
    def conn(self):
        """Lazy connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
        return self._conn

    def close(self):
        """Close connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    # =========================================================================
    # WORKOUT LOGGING
    # =========================================================================

    def log_strength_session(
        self,
        session_date: str,
        name: str,
        sets: List[Dict[str, Any]],
        duration_minutes: int = None,
        notes: str = None,
        tags: List[str] = None,
        session_rpe: int = None,
        source: str = 'logged',
        block_id: str = None,
        plan_id: str = None
    ) -> Dict[str, Any]:
        """
        Log a strength training session with all sets.
        
        Args:
            session_date: YYYY-MM-DD
            name: Session name/goal
            sets: List of set dicts with:
                - exercise_id: Neo4j exercise ID
                - exercise_name: For convenience
                - block_name: "Warm-Up", "Main Work", etc.
                - block_type: warmup/main/accessory/finisher
                - set_order: Position in workout
                - actual_reps, actual_load_lbs, actual_rpe (for executed)
                - prescribed_reps, prescribed_load_lbs, prescribed_rpe (if from plan)
                - notes, is_deviation, deviation_reason
            duration_minutes: Total duration
            notes: Session notes
            tags: Tags for categorization
            session_rpe: Overall session RPE
            source: 'logged', 'from_plan', 'imported'
            block_id: Neo4j Block ID (training phase)
            plan_id: Neo4j PlannedWorkout ID (if from plan)
            
        Returns:
            Dict with session_id, neo4j_id (placeholder), set_count
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Insert session
            cursor.execute("""
                INSERT INTO strength_sessions (
                    session_date, name, duration_minutes, notes, tags,
                    session_rpe, source, block_id, plan_id, status
                ) VALUES (
                    %(session_date)s, %(name)s, %(duration_minutes)s, %(notes)s, %(tags)s,
                    %(session_rpe)s, %(source)s, %(block_id)s, %(plan_id)s, 'completed'
                )
                RETURNING id
            """, {
                'session_date': session_date,
                'name': name,
                'duration_minutes': duration_minutes,
                'notes': notes,
                'tags': tags,
                'session_rpe': session_rpe,
                'source': source,
                'block_id': block_id,
                'plan_id': plan_id
            })
            
            session_id = cursor.fetchone()['id']
            
            # Insert sets
            if sets:
                set_values = []
                for i, s in enumerate(sets):
                    set_values.append((
                        session_id,
                        s.get('block_name'),
                        s.get('block_type', 'main'),
                        s.get('set_order', i + 1),
                        s['exercise_id'],
                        s.get('exercise_name', 'Unknown'),
                        s.get('prescribed_reps'),
                        s.get('prescribed_load_lbs'),
                        s.get('prescribed_rpe'),
                        s.get('actual_reps'),
                        s.get('actual_load_lbs'),
                        s.get('actual_rpe'),
                        s.get('set_type'),
                        s.get('tempo'),
                        s.get('rest_seconds'),
                        s.get('is_deviation', False),
                        s.get('deviation_reason'),
                        s.get('notes')
                    ))
                
                execute_values(cursor, """
                    INSERT INTO strength_sets (
                        session_id, block_name, block_type, set_order,
                        exercise_id, exercise_name,
                        prescribed_reps, prescribed_load_lbs, prescribed_rpe,
                        actual_reps, actual_load_lbs, actual_rpe,
                        set_type, tempo, rest_seconds,
                        is_deviation, deviation_reason, notes
                    ) VALUES %s
                """, set_values)
            
            # Update session totals
            cursor.execute("SELECT update_session_totals(%s)", (session_id,))
            
            self.conn.commit()
            
            return {
                'session_id': session_id,
                'set_count': len(sets),
                'date': session_date
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error logging session: {e}")
            raise

    def update_session_neo4j_id(self, session_id: int, neo4j_id: str) -> bool:
        """Update session with Neo4j reference node ID."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "UPDATE strength_sessions SET neo4j_id = %s WHERE id = %s",
                (neo4j_id, session_id)
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error updating neo4j_id: {e}")
            return False

    # =========================================================================
    # WORKOUT QUERIES
    # =========================================================================

    def get_session_by_date(self, session_date: str) -> Optional[Dict[str, Any]]:
        """
        Get strength session(s) for a date with all sets.
        
        Returns the most recent session if multiple exist.
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get session
        cursor.execute("""
            SELECT id, session_date, name, duration_minutes, 
                   total_volume_lbs, total_sets, total_reps,
                   session_rpe, avg_rpe, max_rpe,
                   notes, tags, status, source,
                   neo4j_id, plan_id, block_id
            FROM strength_sessions
            WHERE session_date = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (session_date,))
        
        session = cursor.fetchone()
        if not session:
            return None
        
        # Get sets
        cursor.execute("""
            SELECT id, set_order, block_name, block_type,
                   exercise_id, exercise_name,
                   reps, load_lbs, rpe, volume_lbs,
                   prescribed_reps, prescribed_load_lbs, prescribed_rpe,
                   is_deviation, deviation_reason, notes
            FROM strength_sets
            WHERE session_id = %s
            ORDER BY set_order
        """, (session['id'],))
        
        sets = cursor.fetchall()
        
        return {
            'session': self._convert_decimals(dict(session)),
            'sets': [self._convert_decimals(dict(s)) for s in sets]
        }

    def get_recent_sessions(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get strength sessions from the last N days."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, session_date, name, duration_minutes,
                   total_volume_lbs, total_sets, total_reps,
                   session_rpe, avg_rpe, status, source, neo4j_id
            FROM strength_sessions
            WHERE session_date >= CURRENT_DATE - %s
            ORDER BY session_date DESC
        """, (days,))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_session_with_patterns(self, session_id: int) -> Dict[str, Any]:
        """
        Get session with movement pattern summary.
        
        Note: Patterns come from Neo4j exercise relationships,
        but we can approximate from exercise names for common patterns.
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get session
        cursor.execute("""
            SELECT * FROM strength_sessions WHERE id = %s
        """, (session_id,))
        session = cursor.fetchone()
        
        if not session:
            return None
        
        # Get exercise names for pattern inference
        cursor.execute("""
            SELECT DISTINCT exercise_name, exercise_id
            FROM strength_sets
            WHERE session_id = %s
        """, (session_id,))
        
        exercises = cursor.fetchall()
        
        # Infer patterns from exercise names (simple heuristic)
        patterns = set()
        for ex in exercises:
            name_lower = ex['exercise_name'].lower()
            if any(k in name_lower for k in ['deadlift', 'rdl', 'hip hinge', 'swing']):
                patterns.add('Hip Hinge')
            if any(k in name_lower for k in ['squat', 'lunge', 'leg press']):
                patterns.add('Squat')
            if any(k in name_lower for k in ['press', 'push', 'bench', 'dip']):
                patterns.add('Push')
            if any(k in name_lower for k in ['row', 'pull', 'chin', 'lat']):
                patterns.add('Pull')
            if any(k in name_lower for k in ['carry', 'hold', 'walk']):
                patterns.add('Carry')
        
        return {
            'session': self._convert_decimals(dict(session)),
            'exercises': [dict(e) for e in exercises],
            'patterns': list(patterns)
        }

    def get_sessions_for_briefing(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get sessions formatted for coach briefing.
        
        Returns lightweight summaries with pattern info.
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                ss.id,
                ss.session_date as date,
                ss.name as type,
                ss.total_sets as sets,
                ss.total_volume_lbs as volume,
                ss.session_rpe,
                ARRAY_AGG(DISTINCT st.exercise_name) as exercises
            FROM strength_sessions ss
            LEFT JOIN strength_sets st ON ss.id = st.session_id
            WHERE ss.session_date >= CURRENT_DATE - %s
            GROUP BY ss.id, ss.session_date, ss.name, ss.total_sets, 
                     ss.total_volume_lbs, ss.session_rpe
            ORDER BY ss.session_date DESC
            LIMIT 5
        """, (days,))
        
        results = []
        for row in cursor.fetchall():
            row_dict = self._convert_decimals(dict(row))
            # Infer patterns from exercises
            patterns = self._infer_patterns(row_dict.get('exercises', []))
            row_dict['patterns'] = patterns
            results.append(row_dict)
        
        return results

    def _infer_patterns(self, exercise_names: List[str]) -> List[str]:
        """Infer movement patterns from exercise names."""
        patterns = set()
        for name in (exercise_names or []):
            if not name:
                continue
            name_lower = name.lower()
            if any(k in name_lower for k in ['deadlift', 'rdl', 'hip hinge', 'swing', 'good morning']):
                patterns.add('Hip Hinge')
            if any(k in name_lower for k in ['squat', 'lunge', 'leg press', 'step']):
                patterns.add('Squat')
            if any(k in name_lower for k in ['bench', 'push-up', 'dip', 'shoulder press', 'overhead']):
                patterns.add('Horizontal Push')
            if any(k in name_lower for k in ['row', 'pull-up', 'chin', 'lat']):
                patterns.add('Pull')
            if any(k in name_lower for k in ['carry', 'farmer', 'suitcase', 'march']):
                patterns.add('Carry')
            if any(k in name_lower for k in ['curl', 'extension', 'fly', 'raise']):
                patterns.add('Isolation')
        return list(patterns)[:3]  # Limit to top 3

    def _convert_decimals(self, d: Dict) -> Dict:
        """Convert Decimal types to float for JSON serialization."""
        return {
            k: float(v) if isinstance(v, Decimal) else v
            for k, v in d.items()
        }

    # =========================================================================
    # EXERCISE HISTORY
    # =========================================================================

    def get_exercise_history(
        self, 
        exercise_id: str, 
        days: int = 180
    ) -> List[Dict[str, Any]]:
        """Get progression history for an exercise."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT * FROM exercise_history(%s, %s)
        """, (exercise_id, days))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_exercise_pr(self, exercise_id: str) -> List[Dict[str, Any]]:
        """Get personal records for an exercise."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT * FROM exercise_pr(%s)
        """, (exercise_id,))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    # =========================================================================
    # WEEKLY STATS
    # =========================================================================

    def get_weekly_volume(self, weeks: int = 4) -> List[Dict[str, Any]]:
        """Get weekly volume summary."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT * FROM weekly_strength_volume
            LIMIT %s
        """, (weeks,))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_workouts_this_week(self) -> int:
        """Get count of workouts this week (Mon-Sun)."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM strength_sessions
            WHERE session_date >= date_trunc('week', CURRENT_DATE)
        """)
        
        return cursor.fetchone()[0]
