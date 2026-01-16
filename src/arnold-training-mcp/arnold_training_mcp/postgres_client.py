"""Postgres client for Arnold training/workout operations.

Per ADR-002: Executed workouts live in Postgres (facts/measurements).
Plans stay in Neo4j (intentions/relationships).

Updated Jan 2026 (Issue 013): Uses unified segment-based schema:
- workouts_v2 → segments → sport-specific child tables
- v2_strength_sets, v2_running_intervals, v2_rowing_intervals, etc.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime, time
from decimal import Decimal
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Default user_id from profile
DEFAULT_USER_ID = "73d17934-4397-4498-ba15-52e19b2ce08f"


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
    # WORKOUT LOGGING (v2 schema - Issue 013)
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
        plan_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Log a strength training session to v2 schema.
        
        Creates: workouts_v2 → segments → v2_strength_sets
        
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
                - tempo, rest_seconds
            duration_minutes: Total duration
            notes: Session notes
            tags: Tags for categorization (stored in extra JSONB)
            session_rpe: Overall session RPE
            source: 'logged', 'from_plan', 'imported'
            block_id: Neo4j Block ID (training phase)
            plan_id: Neo4j PlannedWorkout ID (if from plan)
            user_id: User UUID (defaults to profile)
            
        Returns:
            Dict with workout_id, segment_id, set_count
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        user_id = user_id or DEFAULT_USER_ID
        
        try:
            # Parse date and create start_time
            if isinstance(session_date, str):
                parsed_date = datetime.strptime(session_date, '%Y-%m-%d').date()
            else:
                parsed_date = session_date
            
            # Default to 9am if no time specified
            start_time = datetime.combine(parsed_date, time(9, 0))
            
            # Duration in seconds
            duration_seconds = int(duration_minutes * 60) if duration_minutes else None
            
            # Build extra JSONB
            extra = {}
            if tags:
                extra['tags'] = tags
            if block_id:
                extra['block_id'] = block_id
            if name:
                extra['name'] = name
            
            # 1. Insert workout
            cursor.execute("""
                INSERT INTO workouts_v2 (
                    user_id, start_time, duration_seconds, rpe, notes,
                    source, source_fidelity
                ) VALUES (
                    %(user_id)s, %(start_time)s, %(duration_seconds)s, %(rpe)s, %(notes)s,
                    %(source)s, %(source_fidelity)s
                )
                RETURNING workout_id
            """, {
                'user_id': user_id,
                'start_time': start_time,
                'duration_seconds': duration_seconds,
                'rpe': session_rpe,
                'notes': notes,
                'source': source,
                'source_fidelity': 4 if source == 'logged' else 3
            })
            
            workout_id = cursor.fetchone()['workout_id']
            
            # 2. Insert segment (single strength segment)
            segment_extra = extra.copy()
            cursor.execute("""
                INSERT INTO segments (
                    workout_id, seq, sport_type, duration_seconds, 
                    planned_segment_id, extra
                ) VALUES (
                    %(workout_id)s, 1, 'strength', %(duration_seconds)s,
                    %(plan_id)s, %(extra)s
                )
                RETURNING segment_id
            """, {
                'workout_id': workout_id,
                'duration_seconds': duration_seconds,
                'plan_id': plan_id,
                'extra': psycopg2.extras.Json(segment_extra)
            })
            
            segment_id = cursor.fetchone()['segment_id']
            
            # 3. Insert sets into v2_strength_sets
            if sets:
                set_values = []
                for i, s in enumerate(sets):
                    # Use actual values if available, fall back to prescribed
                    reps = s.get('actual_reps') or s.get('reps') or s.get('prescribed_reps')
                    load = s.get('actual_load_lbs') or s.get('load_lbs') or s.get('prescribed_load_lbs')
                    rpe = s.get('actual_rpe') or s.get('rpe') or s.get('prescribed_rpe')
                    
                    # Build set extra
                    set_extra = {}
                    if s.get('prescribed_reps'):
                        set_extra['prescribed_reps'] = s['prescribed_reps']
                    if s.get('prescribed_load_lbs'):
                        set_extra['prescribed_load'] = s['prescribed_load_lbs']
                    if s.get('prescribed_rpe'):
                        set_extra['prescribed_rpe'] = s['prescribed_rpe']
                    if s.get('is_deviation'):
                        set_extra['is_deviation'] = True
                        set_extra['deviation_reason'] = s.get('deviation_reason')
                    if s.get('block_name'):
                        set_extra['block_name'] = s['block_name']
                    if s.get('block_type'):
                        set_extra['block_type'] = s['block_type']
                    
                    set_values.append((
                        segment_id,
                        s.get('set_order', i + 1),
                        s.get('exercise_id'),
                        s.get('exercise_name') or s.get('name') or 'Unknown',
                        reps,
                        load,
                        'lb',
                        rpe,
                        s.get('rest_seconds'),
                        False,  # failed
                        None,   # pain_scale
                        s.get('set_type') == 'warmup' or s.get('is_warmup', False),
                        s.get('tempo') or s.get('tempo_code'),
                        s.get('notes'),
                        psycopg2.extras.Json(set_extra) if set_extra else None
                    ))
                
                execute_values(cursor, """
                    INSERT INTO v2_strength_sets (
                        segment_id, seq, exercise_id, exercise_name,
                        reps, load, load_unit, rpe,
                        rest_seconds, failed, pain_scale, is_warmup,
                        tempo_code, notes, extra
                    ) VALUES %s
                """, set_values)
            
            self.conn.commit()
            
            return {
                'session_id': str(workout_id),  # For backward compat
                'workout_id': str(workout_id),
                'segment_id': str(segment_id),
                'set_count': len(sets),
                'date': session_date
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error logging strength session: {e}")
            raise

    def log_endurance_session(
        self,
        session_date: str,
        name: str = None,
        sport: str = 'running',
        distance_miles: float = None,
        duration_minutes: float = None,
        avg_pace: str = None,
        avg_hr: int = None,
        max_hr: int = None,
        elevation_gain_m: int = None,
        rpe: int = None,
        notes: str = None,
        tags: List[str] = None,
        source: str = 'logged',
        tss: float = None,
        avg_cadence: int = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Log an endurance session to v2 schema.
        
        Creates: workouts_v2 → segments → sport-specific interval table
        
        Routes to: v2_running_intervals, v2_rowing_intervals, v2_cycling_intervals, etc.
        
        Args:
            session_date: YYYY-MM-DD
            name: Session name (e.g., "Easy run", "Tempo")
            sport: Type of activity (running, cycling, hiking, swimming, rowing)
            distance_miles: Distance in miles
            duration_minutes: Duration in minutes
            avg_pace: Pace string (e.g., "9:30")
            avg_hr: Average heart rate
            max_hr: Maximum heart rate
            elevation_gain_m: Elevation gain in meters
            rpe: Session RPE (1-10)
            notes: Session notes
            tags: Tags for categorization
            source: 'logged', 'from_plan', 'imported'
            tss: Training Stress Score (if calculated)
            avg_cadence: Cadence (steps/strokes per minute)
            user_id: User UUID
            
        Returns:
            Dict with workout_id, segment_id, sport, distance_miles
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        user_id = user_id or DEFAULT_USER_ID
        
        try:
            # Parse date and create start_time
            if isinstance(session_date, str):
                parsed_date = datetime.strptime(session_date, '%Y-%m-%d').date()
            else:
                parsed_date = session_date
            
            start_time = datetime.combine(parsed_date, time(9, 0))
            duration_seconds = int(duration_minutes * 60) if duration_minutes else None
            
            # Convert distance to meters
            distance_m = float(distance_miles) * 1609.344 if distance_miles else None
            
            # Build extra
            extra = {}
            if tags:
                extra['tags'] = tags
            if name:
                extra['name'] = name
            if tss:
                extra['tss'] = tss
            
            # 1. Insert workout
            cursor.execute("""
                INSERT INTO workouts_v2 (
                    user_id, start_time, duration_seconds, rpe, notes,
                    source, source_fidelity
                ) VALUES (
                    %(user_id)s, %(start_time)s, %(duration_seconds)s, %(rpe)s, %(notes)s,
                    %(source)s, %(source_fidelity)s
                )
                RETURNING workout_id
            """, {
                'user_id': user_id,
                'start_time': start_time,
                'duration_seconds': duration_seconds,
                'rpe': rpe,
                'notes': notes,
                'source': source,
                'source_fidelity': 4 if source == 'logged' else 3
            })
            
            workout_id = cursor.fetchone()['workout_id']
            
            # 2. Insert segment
            cursor.execute("""
                INSERT INTO segments (
                    workout_id, seq, sport_type, duration_seconds, extra
                ) VALUES (
                    %(workout_id)s, 1, %(sport)s, %(duration_seconds)s, %(extra)s
                )
                RETURNING segment_id
            """, {
                'workout_id': workout_id,
                'sport': sport,
                'duration_seconds': duration_seconds,
                'extra': psycopg2.extras.Json(extra) if extra else None
            })
            
            segment_id = cursor.fetchone()['segment_id']
            
            # 3. Insert sport-specific interval
            interval_extra = {}
            if name:
                interval_extra['name'] = name
            
            if sport == 'running':
                cursor.execute("""
                    INSERT INTO v2_running_intervals (
                        segment_id, seq, distance_m, duration_seconds,
                        avg_pace_per_km, avg_hr, max_hr, avg_cadence,
                        elevation_gain_m, extra
                    ) VALUES (
                        %(segment_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_pace)s, %(avg_hr)s, %(max_hr)s, %(avg_cadence)s,
                        %(elevation_gain_m)s, %(extra)s
                    )
                    RETURNING interval_id
                """, {
                    'segment_id': segment_id,
                    'distance_m': distance_m,
                    'duration_seconds': duration_seconds,
                    'avg_pace': avg_pace,
                    'avg_hr': avg_hr,
                    'max_hr': max_hr,
                    'avg_cadence': avg_cadence,
                    'elevation_gain_m': elevation_gain_m,
                    'extra': psycopg2.extras.Json(interval_extra) if interval_extra else None
                })
                
            elif sport == 'rowing':
                cursor.execute("""
                    INSERT INTO v2_rowing_intervals (
                        segment_id, seq, distance_m, duration_seconds,
                        avg_hr, max_hr, extra
                    ) VALUES (
                        %(segment_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_hr)s, %(max_hr)s, %(extra)s
                    )
                    RETURNING interval_id
                """, {
                    'segment_id': segment_id,
                    'distance_m': distance_m,
                    'duration_seconds': duration_seconds,
                    'avg_hr': avg_hr,
                    'max_hr': max_hr,
                    'extra': psycopg2.extras.Json(interval_extra) if interval_extra else None
                })
                
            elif sport == 'cycling':
                cursor.execute("""
                    INSERT INTO v2_cycling_intervals (
                        segment_id, seq, distance_m, duration_seconds,
                        avg_hr, max_hr, avg_cadence, elevation_gain_m, extra
                    ) VALUES (
                        %(segment_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_hr)s, %(max_hr)s, %(avg_cadence)s, %(elevation_gain_m)s, %(extra)s
                    )
                    RETURNING interval_id
                """, {
                    'segment_id': segment_id,
                    'distance_m': distance_m,
                    'duration_seconds': duration_seconds,
                    'avg_hr': avg_hr,
                    'max_hr': max_hr,
                    'avg_cadence': avg_cadence,
                    'elevation_gain_m': elevation_gain_m,
                    'extra': psycopg2.extras.Json(interval_extra) if interval_extra else None
                })
                
            elif sport == 'swimming':
                cursor.execute("""
                    INSERT INTO v2_swimming_laps (
                        segment_id, seq, distance_m, duration_seconds,
                        avg_hr, extra
                    ) VALUES (
                        %(segment_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_hr)s, %(extra)s
                    )
                    RETURNING lap_id
                """, {
                    'segment_id': segment_id,
                    'distance_m': distance_m,
                    'duration_seconds': duration_seconds,
                    'avg_hr': avg_hr,
                    'extra': psycopg2.extras.Json(interval_extra) if interval_extra else None
                })
            else:
                # Generic fallback for hiking, walking, etc.
                if distance_m:
                    cursor.execute("""
                        INSERT INTO v2_segment_events_generic (
                            segment_id, seq, metric_name, metric_value, metric_unit, source
                        ) VALUES (
                            %(segment_id)s, 1, 'distance_m', %(distance_m)s, 'm', %(source)s
                        )
                    """, {
                        'segment_id': segment_id,
                        'distance_m': distance_m,
                        'source': source
                    })
            
            self.conn.commit()
            
            return {
                'session_id': str(workout_id),  # Backward compat
                'workout_id': str(workout_id),
                'segment_id': str(segment_id),
                'sport': sport,
                'distance_miles': distance_miles,
                'date': session_date
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error logging endurance session: {e}")
            raise

    def update_session_neo4j_id(self, session_id: str, neo4j_id: str) -> bool:
        """Update workout with Neo4j reference node ID (stored in extra JSONB)."""
        cursor = self.conn.cursor()
        try:
            # session_id is now workout_id (UUID)
            cursor.execute("""
                UPDATE segments 
                SET extra = COALESCE(extra, '{}'::jsonb) || jsonb_build_object('neo4j_id', %s)
                WHERE workout_id = %s::uuid
            """, (neo4j_id, session_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error updating neo4j_id: {e}")
            return False

    def update_endurance_session_neo4j_id(self, session_id: str, neo4j_id: str) -> bool:
        """Alias for update_session_neo4j_id - same in v2 schema."""
        return self.update_session_neo4j_id(session_id, neo4j_id)

    # =========================================================================
    # WORKOUT QUERIES (v2 schema)
    # =========================================================================

    def get_session_by_date(self, session_date: str) -> Optional[Dict[str, Any]]:
        """
        Get workout(s) for a date with all sets/intervals.
        
        Returns the most recent workout if multiple exist.
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get workout + segment
        cursor.execute("""
            SELECT 
                w.workout_id, w.start_time::date as session_date,
                w.duration_seconds, w.rpe as session_rpe, w.notes, w.source,
                s.segment_id, s.sport_type, s.extra as segment_extra
            FROM workouts_v2 w
            JOIN segments s ON w.workout_id = s.workout_id
            WHERE w.start_time::date = %s
            ORDER BY w.created_at DESC
            LIMIT 1
        """, (session_date,))
        
        workout = cursor.fetchone()
        if not workout:
            return None
        
        result = {
            'session': self._convert_decimals(dict(workout)),
            'sets': [],
            'intervals': []
        }
        
        # Get sport-specific data
        sport = workout['sport_type']
        segment_id = workout['segment_id']
        
        if sport == 'strength':
            cursor.execute("""
                SELECT 
                    set_id as id, seq as set_order, exercise_id, exercise_name,
                    reps, load as load_lbs, rpe, rest_seconds,
                    is_warmup, failed, notes, extra
                FROM v2_strength_sets
                WHERE segment_id = %s
                ORDER BY seq
            """, (segment_id,))
            result['sets'] = [self._convert_decimals(dict(s)) for s in cursor.fetchall()]
            
            # Calculate totals
            total_volume = sum(
                (s.get('reps') or 0) * (s.get('load_lbs') or 0) 
                for s in result['sets']
            )
            result['session']['total_volume_lbs'] = total_volume
            result['session']['total_sets'] = len(result['sets'])
            result['session']['total_reps'] = sum(s.get('reps') or 0 for s in result['sets'])
            
        elif sport == 'running':
            cursor.execute("""
                SELECT 
                    interval_id as id, seq, distance_m, duration_seconds,
                    avg_pace_per_km, avg_hr, max_hr, avg_cadence,
                    elevation_gain_m, elevation_loss_m, extra
                FROM v2_running_intervals
                WHERE segment_id = %s
                ORDER BY seq
            """, (segment_id,))
            result['intervals'] = [self._convert_decimals(dict(i)) for i in cursor.fetchall()]
            
        elif sport == 'rowing':
            cursor.execute("""
                SELECT 
                    interval_id as id, seq, distance_m, duration_seconds,
                    avg_500m_pace_seconds, stroke_rate, avg_hr, max_hr, extra
                FROM v2_rowing_intervals
                WHERE segment_id = %s
                ORDER BY seq
            """, (segment_id,))
            result['intervals'] = [self._convert_decimals(dict(i)) for i in cursor.fetchall()]
        
        return result

    def get_recent_sessions(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get workouts from the last N days."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                w.workout_id as id,
                w.start_time::date as session_date,
                s.sport_type,
                COALESCE(s.extra->>'name', s.sport_type || ' session') as name,
                w.duration_seconds / 60 as duration_minutes,
                w.rpe as session_rpe,
                w.source,
                s.extra->>'neo4j_id' as neo4j_id,
                -- Strength totals
                CASE WHEN s.sport_type = 'strength' THEN (
                    SELECT COUNT(*) FROM v2_strength_sets WHERE segment_id = s.segment_id
                ) ELSE 0 END as total_sets,
                CASE WHEN s.sport_type = 'strength' THEN (
                    SELECT COALESCE(SUM(reps * load), 0) FROM v2_strength_sets WHERE segment_id = s.segment_id
                ) ELSE 0 END as total_volume_lbs
            FROM workouts_v2 w
            JOIN segments s ON w.workout_id = s.workout_id
            WHERE w.start_time >= CURRENT_DATE - %s
            ORDER BY w.start_time DESC
        """, (days,))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_sessions_for_briefing(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get sessions formatted for coach briefing.
        
        Returns lightweight summaries with pattern info.
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                w.workout_id as id,
                w.start_time::date as date,
                s.sport_type as type,
                COALESCE(s.extra->>'name', s.sport_type) as name,
                w.rpe as session_rpe,
                CASE WHEN s.sport_type = 'strength' THEN (
                    SELECT COUNT(*) FROM v2_strength_sets WHERE segment_id = s.segment_id
                ) ELSE 0 END as sets,
                CASE WHEN s.sport_type = 'strength' THEN (
                    SELECT COALESCE(SUM(reps * load), 0) FROM v2_strength_sets WHERE segment_id = s.segment_id
                ) ELSE NULL END as volume,
                CASE WHEN s.sport_type = 'strength' THEN (
                    SELECT ARRAY_AGG(DISTINCT exercise_name) 
                    FROM v2_strength_sets WHERE segment_id = s.segment_id
                ) ELSE NULL END as exercises
            FROM workouts_v2 w
            JOIN segments s ON w.workout_id = s.workout_id
            WHERE w.start_time >= CURRENT_DATE - %s
            ORDER BY w.start_time DESC
            LIMIT 5
        """, (days,))
        
        results = []
        for row in cursor.fetchall():
            row_dict = self._convert_decimals(dict(row))
            # Infer patterns from exercises
            patterns = self._infer_patterns(row_dict.get('exercises') or [])
            row_dict['patterns'] = patterns
            results.append(row_dict)
        
        return results

    def get_workouts_this_week(self) -> int:
        """Get count of workouts this week (Mon-Sun)."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM workouts_v2
            WHERE start_time >= date_trunc('week', CURRENT_DATE)
        """)
        
        return cursor.fetchone()[0]

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
        return list(patterns)[:3]

    def _convert_decimals(self, d: Dict) -> Dict:
        """Convert Decimal types to float for JSON serialization."""
        result = {}
        for k, v in d.items():
            if isinstance(v, Decimal):
                result[k] = float(v)
            elif isinstance(v, uuid.UUID):
                result[k] = str(v)
            else:
                result[k] = v
        return result

    # =========================================================================
    # EXERCISE HISTORY (v2 schema)
    # =========================================================================

    def get_exercise_history(
        self, 
        exercise_id: str, 
        days: int = 180
    ) -> List[Dict[str, Any]]:
        """Get progression history for an exercise from v2 schema."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                w.start_time::date as session_date,
                ss.reps,
                ss.load as load_lbs,
                ss.rpe,
                (ss.reps * ss.load) as volume
            FROM v2_strength_sets ss
            JOIN segments s ON ss.segment_id = s.segment_id
            JOIN workouts_v2 w ON s.workout_id = w.workout_id
            WHERE ss.exercise_id = %s
              AND w.start_time >= CURRENT_DATE - %s
            ORDER BY w.start_time DESC, ss.seq
        """, (exercise_id, days))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_exercise_pr(self, exercise_id: str) -> List[Dict[str, Any]]:
        """Get personal records for an exercise from v2 schema."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get max load per rep range
        cursor.execute("""
            SELECT 
                ss.reps,
                MAX(ss.load) as max_load,
                MAX(ss.reps * ss.load) as max_volume
            FROM v2_strength_sets ss
            JOIN segments s ON ss.segment_id = s.segment_id
            WHERE ss.exercise_id = %s
              AND ss.reps IS NOT NULL
              AND ss.load IS NOT NULL
            GROUP BY ss.reps
            ORDER BY ss.reps
        """, (exercise_id,))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    # =========================================================================
    # WEEKLY STATS (v2 schema)
    # =========================================================================

    def get_weekly_volume(self, weeks: int = 4) -> List[Dict[str, Any]]:
        """Get weekly volume summary from v2 schema."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                date_trunc('week', w.start_time)::date as week_start,
                COUNT(DISTINCT w.workout_id) as workout_count,
                SUM(ss.reps * ss.load) as total_volume,
                COUNT(ss.set_id) as total_sets
            FROM workouts_v2 w
            JOIN segments s ON w.workout_id = s.workout_id
            LEFT JOIN v2_strength_sets ss ON s.segment_id = ss.segment_id
            WHERE s.sport_type = 'strength'
              AND w.start_time >= CURRENT_DATE - (%s * 7)
            GROUP BY date_trunc('week', w.start_time)
            ORDER BY week_start DESC
            LIMIT %s
        """, (weeks, weeks))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]
