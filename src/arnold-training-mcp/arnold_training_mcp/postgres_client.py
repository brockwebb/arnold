"""Postgres client for Arnold training/workout operations.

Per ADR-002: Executed workouts live in Postgres (facts/measurements).
Plans stay in Neo4j (intentions/relationships).

Updated Jan 2026 (Issue 013, ADR-007): Uses simplified schema:
- workouts → blocks → sets
- Clean three-table design with nullable columns for different modalities.
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
        
        Creates: workouts → blocks → sets
        
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
            Dict with workout_id, block_id, set_count
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
                INSERT INTO workouts (
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
                INSERT INTO blocks (
                    workout_id, seq, modality, duration_seconds,
                    planned_segment_id, extra
                ) VALUES (
                    %(workout_id)s, 1, 'strength', %(duration_seconds)s,
                    %(plan_id)s, %(extra)s
                )
                RETURNING block_id
            """, {
                'workout_id': workout_id,
                'duration_seconds': duration_seconds,
                'plan_id': plan_id,
                'extra': psycopg2.extras.Json(segment_extra)
            })
            
            block_id = cursor.fetchone()['block_id']
            
            # 3. Insert sets
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
                    
                    # Convert planned_set_id to UUID if it's a string like "PLANSET:..."
                    planned_set_id = s.get('planned_set_id')
                    if planned_set_id and isinstance(planned_set_id, str):
                        # Extract UUID from "PLANSET:uuid" format
                        if planned_set_id.startswith('PLANSET:'):
                            planned_set_id = planned_set_id.replace('PLANSET:', '')

                    set_values.append((
                        block_id,
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
                        psycopg2.extras.Json(set_extra) if set_extra else None,
                        planned_set_id  # FK to planned_sets (Phase 6b)
                    ))

                execute_values(cursor, """
                    INSERT INTO sets (
                        block_id, seq, exercise_id, exercise_name,
                        reps, load, load_unit, rpe,
                        rest_seconds, failed, pain_scale, is_warmup,
                        tempo_code, notes, extra, planned_set_id
                    ) VALUES %s
                """, set_values)
            
            self.conn.commit()
            
            return {
                'session_id': str(workout_id),  # For backward compat
                'workout_id': str(workout_id),
                'block_id': str(block_id),
                'set_count': len(sets),
                'date': session_date
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error logging strength session: {e}")
            raise

    def log_workout_session(
        self,
        session_date: str,
        name: str,
        blocks: List[Dict[str, Any]],
        sport_type: str = 'strength',
        duration_minutes: int = None,
        notes: str = None,
        session_rpe: int = None,
        source: str = 'logged',
        plan_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Log a workout session with proper block structure per ADR-007.

        Creates: 1 workout → N blocks → M sets per block

        This is the unified method for logging workouts of any modality.
        Block type (warmup/main/finisher) is orthogonal to modality (strength/running).

        Args:
            session_date: YYYY-MM-DD
            name: Session name
            blocks: List of block dicts, each with:
                - name: Block name ("Warmup", "Main Work", etc.)
                - block_type: warmup/main/accessory/finisher/cooldown
                - modality: Optional override (defaults to sport_type)
                - sets: List of set dicts
            sport_type: Workout-level modality (strength, running, cycling, etc.)
            duration_minutes: Total duration
            notes: Session notes
            session_rpe: Overall RPE
            source: 'logged', 'from_plan', 'imported'
            plan_id: Neo4j PlannedWorkout ID (if from plan)
            user_id: User UUID

        Returns:
            Dict with workout_id, block_count, block_ids, set_count, total_volume
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        user_id = user_id or DEFAULT_USER_ID

        try:
            # Parse date
            if isinstance(session_date, str):
                parsed_date = datetime.strptime(session_date, '%Y-%m-%d').date()
            else:
                parsed_date = session_date

            start_time = datetime.combine(parsed_date, time(9, 0))
            duration_seconds = int(duration_minutes * 60) if duration_minutes else None

            # 1. Insert workout
            cursor.execute("""
                INSERT INTO workouts (
                    user_id, start_time, duration_seconds, rpe, notes,
                    sport_type, source, source_fidelity
                ) VALUES (
                    %(user_id)s, %(start_time)s, %(duration_seconds)s, %(rpe)s, %(notes)s,
                    %(sport_type)s, %(source)s, %(source_fidelity)s
                )
                RETURNING workout_id
            """, {
                'user_id': user_id,
                'start_time': start_time,
                'duration_seconds': duration_seconds,
                'rpe': session_rpe,
                'notes': notes,
                'sport_type': sport_type,
                'source': source,
                'source_fidelity': 4 if source == 'logged' else 3
            })

            workout_id = cursor.fetchone()['workout_id']

            total_sets = 0
            total_volume = 0
            block_ids = []

            # 2. Insert each block
            for block_seq, block in enumerate(blocks, start=1):
                block_extra = {'name': block.get('name', f'Block {block_seq}')}
                if plan_id:
                    block_extra['plan_id'] = plan_id

                # Block modality: use override if provided, else inherit from workout
                block_modality = block.get('modality') or sport_type

                cursor.execute("""
                    INSERT INTO blocks (
                        workout_id, seq, modality, block_type, extra
                    ) VALUES (
                        %(workout_id)s, %(seq)s, %(modality)s, %(block_type)s, %(extra)s
                    )
                    RETURNING block_id
                """, {
                    'workout_id': workout_id,
                    'seq': block_seq,
                    'modality': block_modality,
                    'block_type': block.get('block_type', 'main'),
                    'extra': psycopg2.extras.Json(block_extra)
                })

                block_id = cursor.fetchone()['block_id']
                block_ids.append(block_id)

                # 3. Insert sets for this block
                block_sets = block.get('sets', [])
                if block_sets:
                    set_values = []
                    for set_seq, s in enumerate(block_sets, start=1):
                        exercise_id = s.get('exercise_id')
                        exercise_name = s.get('exercise_name') or s.get('name')

                        # Resolve exercise name if missing
                        if not exercise_name and exercise_id:
                            exercise_name = exercise_id  # Fallback to ID

                        reps = s.get('reps') or s.get('actual_reps')
                        load = s.get('load_lbs') or s.get('load') or s.get('actual_load_lbs')
                        rpe = s.get('rpe') or s.get('actual_rpe')

                        # Calculate volume contribution
                        if reps and load:
                            total_volume += (reps * load)

                        set_extra = {}
                        if s.get('notes'):
                            set_extra['notes'] = s['notes']
                        if s.get('duration_seconds'):
                            set_extra['duration_seconds'] = s['duration_seconds']

                        # Strip PLANSET: prefix for Postgres UUID column
                        planned_set_id = s.get('planned_set_id')
                        if planned_set_id and isinstance(planned_set_id, str) and planned_set_id.startswith('PLANSET:'):
                            planned_set_id = planned_set_id.replace('PLANSET:', '')

                        set_values.append((
                            block_id,
                            set_seq,
                            exercise_id,
                            exercise_name or 'Unknown',
                            reps,
                            load,
                            'lb' if load else None,
                            rpe,
                            s.get('rest_seconds'),
                            False,  # failed
                            None,   # pain_scale
                            block.get('block_type') == 'warmup',  # is_warmup
                            s.get('tempo_code') or s.get('tempo'),
                            s.get('notes'),
                            psycopg2.extras.Json(set_extra) if set_extra else None,
                            planned_set_id  # FK to planned_sets (UUID, prefix stripped)
                        ))

                    execute_values(cursor, """
                        INSERT INTO sets (
                            block_id, seq, exercise_id, exercise_name,
                            reps, load, load_unit, rpe,
                            rest_seconds, failed, pain_scale, is_warmup,
                            tempo_code, notes, extra, planned_set_id
                        ) VALUES %s
                    """, set_values)

                    total_sets += len(block_sets)

            self.conn.commit()

            return {
                'session_id': str(workout_id),
                'workout_id': str(workout_id),
                'block_count': len(blocks),
                'block_ids': [str(bid) for bid in block_ids],
                'set_count': total_sets,
                'total_volume': total_volume,
                'date': session_date
            }

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error logging workout session: {e}")
            raise

    # Alias for backward compatibility
    def log_strength_session_with_blocks(self, *args, **kwargs):
        """Deprecated: Use log_workout_session instead."""
        return self.log_workout_session(*args, **kwargs)

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
        
        Creates: workouts → blocks → sets

        NOTE: Endurance tables (v2_*_intervals) are deprecated. This function
        will need updating to use the unified sets table with endurance columns.
        
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
            Dict with workout_id, block_id, sport, distance_miles
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
                INSERT INTO workouts (
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
                INSERT INTO blocks (
                    workout_id, seq, modality, duration_seconds, extra
                ) VALUES (
                    %(workout_id)s, 1, %(sport)s, %(duration_seconds)s, %(extra)s
                )
                RETURNING block_id
            """, {
                'workout_id': workout_id,
                'sport': sport,
                'duration_seconds': duration_seconds,
                'extra': psycopg2.extras.Json(extra) if extra else None
            })
            
            block_id = cursor.fetchone()['block_id']
            
            # 3. Insert sport-specific interval
            interval_extra = {}
            if name:
                interval_extra['name'] = name
            
            if sport == 'running':
                cursor.execute("""
                    INSERT INTO v2_running_intervals (
                        block_id, seq, distance_m, duration_seconds,
                        avg_pace_per_km, avg_hr, max_hr, avg_cadence,
                        elevation_gain_m, extra
                    ) VALUES (
                        %(block_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_pace)s, %(avg_hr)s, %(max_hr)s, %(avg_cadence)s,
                        %(elevation_gain_m)s, %(extra)s
                    )
                    RETURNING interval_id
                """, {
                    'block_id': block_id,
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
                        block_id, seq, distance_m, duration_seconds,
                        avg_hr, max_hr, extra
                    ) VALUES (
                        %(block_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_hr)s, %(max_hr)s, %(extra)s
                    )
                    RETURNING interval_id
                """, {
                    'block_id': block_id,
                    'distance_m': distance_m,
                    'duration_seconds': duration_seconds,
                    'avg_hr': avg_hr,
                    'max_hr': max_hr,
                    'extra': psycopg2.extras.Json(interval_extra) if interval_extra else None
                })
                
            elif sport == 'cycling':
                cursor.execute("""
                    INSERT INTO v2_cycling_intervals (
                        block_id, seq, distance_m, duration_seconds,
                        avg_hr, max_hr, avg_cadence, elevation_gain_m, extra
                    ) VALUES (
                        %(block_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_hr)s, %(max_hr)s, %(avg_cadence)s, %(elevation_gain_m)s, %(extra)s
                    )
                    RETURNING interval_id
                """, {
                    'block_id': block_id,
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
                        block_id, seq, distance_m, duration_seconds,
                        avg_hr, extra
                    ) VALUES (
                        %(block_id)s, 1, %(distance_m)s, %(duration_seconds)s,
                        %(avg_hr)s, %(extra)s
                    )
                    RETURNING lap_id
                """, {
                    'block_id': block_id,
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
                            block_id, seq, metric_name, metric_value, metric_unit, source
                        ) VALUES (
                            %(block_id)s, 1, 'distance_m', %(distance_m)s, 'm', %(source)s
                        )
                    """, {
                        'block_id': block_id,
                        'distance_m': distance_m,
                        'source': source
                    })
            
            self.conn.commit()
            
            return {
                'session_id': str(workout_id),  # Backward compat
                'workout_id': str(workout_id),
                'block_id': str(block_id),
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
                UPDATE blocks 
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
        Get workout(s) for a date with ALL blocks and sets.

        Returns the most recent workout if multiple exist.
        Properly handles multi-block workouts (warmup, main, finisher, etc.)
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # 1. Get the workout (not joined to blocks yet)
        cursor.execute("""
            SELECT
                workout_id, start_time::date as session_date,
                duration_seconds, rpe as session_rpe, notes, source, sport_type
            FROM workouts
            WHERE start_time::date = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (session_date,))

        workout = cursor.fetchone()
        if not workout:
            return None

        workout_id = workout['workout_id']

        result = {
            'session': self._convert_decimals(dict(workout)),
            'blocks': [],
            'sets': [],        # Flat list of all sets (for backward compat)
            'intervals': []
        }

        # 2. Get ALL blocks for this workout
        cursor.execute("""
            SELECT
                block_id, seq, modality, block_type, duration_seconds,
                extra as block_extra
            FROM blocks
            WHERE workout_id = %s
            ORDER BY seq
        """, (workout_id,))

        blocks = cursor.fetchall()

        # 3. Get sets for each block
        total_volume = 0
        total_sets = 0
        total_reps = 0

        for block in blocks:
            block_dict = self._convert_decimals(dict(block))
            block_id = block['block_id']
            modality = block['modality'] or 'strength'

            if modality == 'strength' or modality is None:
                cursor.execute("""
                    SELECT
                        set_id as id, seq as set_order, exercise_id, exercise_name,
                        reps, load as load_lbs, rpe, rest_seconds,
                        is_warmup, failed, notes, extra
                    FROM sets
                    WHERE block_id = %s
                    ORDER BY seq
                """, (block_id,))

                block_sets = [self._convert_decimals(dict(s)) for s in cursor.fetchall()]
                block_dict['sets'] = block_sets

                # Accumulate to flat list for backward compat
                result['sets'].extend(block_sets)

                # Accumulate totals
                for s in block_sets:
                    reps = s.get('reps') or 0
                    load = s.get('load_lbs') or 0
                    total_volume += reps * load
                    total_sets += 1
                    total_reps += reps

            elif modality == 'running':
                cursor.execute("""
                    SELECT
                        interval_id as id, seq, distance_m, duration_seconds,
                        avg_pace_per_km, avg_hr, max_hr, avg_cadence,
                        elevation_gain_m, elevation_loss_m, extra
                    FROM v2_running_intervals
                    WHERE block_id = %s
                    ORDER BY seq
                """, (block_id,))
                block_dict['intervals'] = [self._convert_decimals(dict(i)) for i in cursor.fetchall()]
                result['intervals'].extend(block_dict['intervals'])

            elif modality == 'rowing':
                cursor.execute("""
                    SELECT
                        interval_id as id, seq, distance_m, duration_seconds,
                        avg_500m_pace_seconds, stroke_rate, avg_hr, max_hr, extra
                    FROM v2_rowing_intervals
                    WHERE block_id = %s
                    ORDER BY seq
                """, (block_id,))
                block_dict['intervals'] = [self._convert_decimals(dict(i)) for i in cursor.fetchall()]
                result['intervals'].extend(block_dict['intervals'])

            result['blocks'].append(block_dict)

        # Add totals to session
        result['session']['total_volume_lbs'] = total_volume
        result['session']['total_sets'] = total_sets
        result['session']['total_reps'] = total_reps
        result['session']['block_count'] = len(blocks)

        return result

    def get_recent_sessions(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get workouts from the last N days (one row per workout, aggregated across blocks)."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # Aggregate across ALL blocks per workout
        cursor.execute("""
            SELECT
                w.workout_id as id,
                w.start_time::date as session_date,
                w.sport_type as modality,
                COALESCE(w.notes, w.sport_type || ' session') as name,
                w.duration_seconds / 60 as duration_minutes,
                w.rpe as session_rpe,
                w.source,
                (SELECT COUNT(*) FROM blocks WHERE workout_id = w.workout_id) as block_count,
                (SELECT COUNT(*) FROM sets s
                 JOIN blocks b ON s.block_id = b.block_id
                 WHERE b.workout_id = w.workout_id) as total_sets,
                (SELECT COALESCE(SUM(s.reps * s.load), 0) FROM sets s
                 JOIN blocks b ON s.block_id = b.block_id
                 WHERE b.workout_id = w.workout_id) as total_volume_lbs
            FROM workouts w
            WHERE w.start_time >= CURRENT_DATE - %s
            ORDER BY w.start_time DESC
        """, (days,))

        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_sessions_for_briefing(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get sessions formatted for coach briefing.

        Returns lightweight summaries with pattern info (one row per workout).
        """
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # Aggregate across ALL blocks per workout
        cursor.execute("""
            SELECT
                w.workout_id as id,
                w.start_time::date as date,
                w.sport_type as type,
                COALESCE(w.notes, w.sport_type) as name,
                w.rpe as session_rpe,
                (SELECT COUNT(*) FROM sets s
                 JOIN blocks b ON s.block_id = b.block_id
                 WHERE b.workout_id = w.workout_id) as sets,
                (SELECT COALESCE(SUM(s.reps * s.load), 0) FROM sets s
                 JOIN blocks b ON s.block_id = b.block_id
                 WHERE b.workout_id = w.workout_id) as volume,
                (SELECT ARRAY_AGG(DISTINCT s.exercise_name) FROM sets s
                 JOIN blocks b ON s.block_id = b.block_id
                 WHERE b.workout_id = w.workout_id) as exercises
            FROM workouts w
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
            SELECT COUNT(*) FROM workouts
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
            FROM sets ss
            JOIN blocks b ON ss.block_id = b.block_id
            JOIN workouts w ON b.workout_id = w.workout_id
            WHERE ss.exercise_id = %s
              AND w.start_time >= CURRENT_DATE - %s
            ORDER BY w.start_time DESC, ss.seq
        """, (exercise_id, days))
        
        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    def get_exercise_pr(self, exercise_id: str) -> List[Dict[str, Any]]:
        """Get personal records for an exercise."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # Get max load per rep range
        cursor.execute("""
            SELECT
                ss.reps,
                MAX(ss.load) as max_load,
                MAX(ss.reps * ss.load) as max_volume
            FROM sets ss
            JOIN blocks b ON ss.block_id = b.block_id
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
        """Get weekly volume summary."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                date_trunc('week', w.start_time)::date as week_start,
                COUNT(DISTINCT w.workout_id) as workout_count,
                SUM(ss.reps * ss.load) as total_volume,
                COUNT(ss.set_id) as total_sets
            FROM workouts w
            JOIN blocks b ON w.workout_id = b.workout_id
            LEFT JOIN sets ss ON b.block_id = ss.block_id
            WHERE b.modality = 'strength'
              AND w.start_time >= CURRENT_DATE - (%s * 7)
            GROUP BY date_trunc('week', w.start_time)
            ORDER BY week_start DESC
            LIMIT %s
        """, (weeks, weeks))

        return [self._convert_decimals(dict(r)) for r in cursor.fetchall()]

    # =========================================================================
    # PLANNED SETS (Phase 6b - mirror from Neo4j for FK joins)
    # =========================================================================

    def insert_planned_sets(self, plan_id: str, blocks: List[Dict[str, Any]]) -> int:
        """
        Mirror planned sets from Neo4j to Postgres for FK joins.

        Called after create_planned_workout in Neo4j to enable
        execution_vs_plan view with proper FK relationships.

        Args:
            plan_id: Neo4j PlannedWorkout ID
            blocks: List of block dicts with 'sets' containing planned set data

        Returns:
            Number of rows inserted
        """
        cursor = self.conn.cursor()

        try:
            rows = []
            for block_idx, block in enumerate(blocks):
                for set_idx, set_data in enumerate(block.get('sets', [])):
                    # Extract UUID from "PLANSET:uuid" format
                    set_id = set_data.get('id')
                    if set_id and isinstance(set_id, str) and set_id.startswith('PLANSET:'):
                        set_id = set_id.replace('PLANSET:', '')

                    rows.append((
                        set_id,  # Same UUID as Neo4j PlannedSet
                        plan_id,
                        block_idx + 1,  # block_seq
                        set_idx + 1,    # set_seq
                        set_data.get('exercise_id'),
                        set_data.get('exercise_name') or set_data.get('name') or 'Unknown',
                        set_data.get('prescribed_reps') or set_data.get('reps'),
                        set_data.get('prescribed_load_lbs') or set_data.get('load_lbs'),
                        set_data.get('prescribed_rpe') or set_data.get('rpe'),
                        set_data.get('intensity_zone'),
                        block.get('name'),
                        block.get('block_type'),
                        set_data.get('notes')
                    ))

            if rows:
                execute_values(cursor, """
                    INSERT INTO planned_sets (
                        id, plan_id, block_seq, set_seq,
                        exercise_id, exercise_name,
                        prescribed_reps, prescribed_load_lbs, prescribed_rpe,
                        intensity_zone, block_name, block_type, notes
                    ) VALUES %s
                    ON CONFLICT (id) DO UPDATE SET
                        prescribed_reps = EXCLUDED.prescribed_reps,
                        prescribed_load_lbs = EXCLUDED.prescribed_load_lbs,
                        prescribed_rpe = EXCLUDED.prescribed_rpe
                """, rows)

                self.conn.commit()
                return len(rows)

            return 0

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error inserting planned sets: {e}")
            raise

    def get_planned_sets_for_plan(self, plan_id: str) -> List[Dict[str, Any]]:
        """Get planned sets for a plan, for matching during workout completion."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                id, plan_id, block_seq, set_seq,
                exercise_id, exercise_name,
                prescribed_reps, prescribed_load_lbs, prescribed_rpe,
                block_name, block_type
            FROM planned_sets
            WHERE plan_id = %s
            ORDER BY block_seq, set_seq
        """, (plan_id,))

        return [dict(r) for r in cursor.fetchall()]
