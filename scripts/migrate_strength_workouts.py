#!/usr/bin/env python3
"""
Migrate strength workouts from Neo4j to Postgres.

This script implements ADR-002: moves executed workout data from Neo4j
to Postgres while preserving Neo4j references for relationship queries.

Usage:
    python migrate_strength_workouts.py --dry-run   # Preview without changes
    python migrate_strength_workouts.py             # Run migration
    python migrate_strength_workouts.py --force     # Re-run even if already migrated
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, date
from typing import Optional, Dict, List, Any

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j connection for reading workout data."""
    
    def __init__(self):
        self.uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.environ.get("NEO4J_USER", "neo4j")
        self.password = os.environ.get("NEO4J_PASSWORD", "password")
        self.database = os.environ.get("NEO4J_DATABASE", "arnold")
        self._driver = None
    
    def connect(self):
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self
    
    def close(self):
        if self._driver:
            self._driver.close()
    
    def query(self, cypher: str, params: dict = None) -> List[Dict]:
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]


class PostgresClient:
    """Postgres connection for writing workout data."""
    
    def __init__(self):
        self.dsn = os.environ.get(
            "POSTGRES_DSN",
            "postgresql://brock@localhost:5432/arnold_analytics"
        )
        self._conn = None
    
    def connect(self):
        self._conn = psycopg2.connect(self.dsn)
        return self
    
    def close(self):
        if self._conn:
            self._conn.close()
    
    @property
    def conn(self):
        return self._conn


def extract_workouts(neo4j: Neo4jClient) -> List[Dict]:
    """Extract all workouts with their blocks and sets from Neo4j."""
    
    logger.info("Extracting workouts from Neo4j...")
    
    # Get all workouts with metadata
    workouts_query = """
    MATCH (p:Person)-[:PERFORMED]->(w:Workout)
    RETURN w.id as id,
           toString(w.date) as date,
           w.name as name,
           w.type as type,
           w.duration_minutes as duration_minutes,
           w.notes as notes,
           w.source as source
    ORDER BY w.date
    """
    
    workouts = neo4j.query(workouts_query)
    logger.info(f"Found {len(workouts)} workouts")
    
    # Get all sets with block and exercise info
    sets_query = """
    MATCH (w:Workout)-[:HAS_BLOCK]->(wb:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
    RETURN w.id as workout_id,
           wb.name as block_name,
           wb.phase as block_type,
           wb.order as block_order,
           s.id as set_id,
           s.order as set_order,
           s.set_number as set_number,
           s.reps as reps,
           s.load_lbs as load_lbs,
           s.rpe as rpe,
           s.duration_seconds as duration_seconds,
           s.notes as notes,
           e.id as exercise_id,
           e.name as exercise_name
    ORDER BY w.id, wb.order, s.order
    """
    
    all_sets = neo4j.query(sets_query)
    logger.info(f"Found {len(all_sets)} sets across all workouts")
    
    # Group sets by workout
    sets_by_workout = {}
    for s in all_sets:
        wid = s['workout_id']
        if wid not in sets_by_workout:
            sets_by_workout[wid] = []
        sets_by_workout[wid].append(s)
    
    # Combine
    for w in workouts:
        w['sets'] = sets_by_workout.get(w['id'], [])
    
    return workouts


def infer_block_type(block_name: str, block_phase: Optional[str]) -> Optional[str]:
    """Infer block_type from name or phase."""
    if block_phase:
        phase_lower = block_phase.lower()
        if 'warm' in phase_lower:
            return 'warmup'
        if 'main' in phase_lower or 'work' in phase_lower:
            return 'main'
        if 'access' in phase_lower or 'aux' in phase_lower:
            return 'accessory'
        if 'finish' in phase_lower or 'metcon' in phase_lower:
            return 'finisher'
        if 'cool' in phase_lower:
            return 'cooldown'
    
    if block_name:
        name_lower = block_name.lower()
        if 'warm' in name_lower:
            return 'warmup'
        if 'main' in name_lower or 'work' in name_lower:
            return 'main'
        if 'access' in name_lower or 'aux' in name_lower:
            return 'accessory'
        if 'finish' in name_lower or 'metcon' in name_lower or 'circuit' in name_lower:
            return 'finisher'
        if 'cool' in name_lower:
            return 'cooldown'
    
    return 'main'  # Default


def transform_workout(workout: Dict, set_order_start: int = 1) -> tuple:
    """Transform a Neo4j workout into Postgres session + sets."""
    
    # Parse date
    date_str = workout.get('date')
    if date_str:
        session_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        session_date = None
    
    # Build session record
    session = {
        'session_date': session_date,
        'name': workout.get('name') or workout.get('type') or 'Workout',
        'duration_minutes': workout.get('duration_minutes'),
        'notes': workout.get('notes'),
        'source': 'migrated',
        'status': 'completed',
        'legacy_neo4j_id': workout['id'],
    }
    
    # Build set records
    sets = []
    global_set_order = set_order_start
    
    for s in workout.get('sets', []):
        # Skip sets without exercise
        if not s.get('exercise_id'):
            continue
        
        block_type = infer_block_type(s.get('block_name'), s.get('block_type'))
        
        set_record = {
            'block_name': s.get('block_name'),
            'block_type': block_type,
            'set_order': global_set_order,
            'exercise_id': s['exercise_id'],
            'exercise_name': s.get('exercise_name') or 'Unknown',
            'actual_reps': s.get('reps'),
            'actual_load_lbs': s.get('load_lbs'),
            'actual_rpe': s.get('rpe'),
            'notes': s.get('notes'),
            'legacy_neo4j_id': s.get('set_id'),
        }
        
        sets.append(set_record)
        global_set_order += 1
    
    return session, sets


def load_to_postgres(pg: PostgresClient, workouts: List[Dict], dry_run: bool = False):
    """Load transformed workouts into Postgres."""
    
    logger.info(f"Loading {len(workouts)} workouts to Postgres (dry_run={dry_run})...")
    
    if dry_run:
        # Just show what would happen
        for w in workouts[:5]:
            session, sets = transform_workout(w)
            logger.info(f"  Would insert: {session['session_date']} - {session['name']} ({len(sets)} sets)")
        if len(workouts) > 5:
            logger.info(f"  ... and {len(workouts) - 5} more")
        return 0, 0
    
    cursor = pg.conn.cursor()
    sessions_inserted = 0
    sets_inserted = 0
    
    try:
        for w in workouts:
            session, sets = transform_workout(w)
            
            # Skip if no date
            if not session['session_date']:
                logger.warning(f"Skipping workout {w['id']} - no date")
                continue
            
            # Insert session
            cursor.execute("""
                INSERT INTO strength_sessions (
                    session_date, name, duration_minutes, notes, 
                    source, status, legacy_neo4j_id
                ) VALUES (
                    %(session_date)s, %(name)s, %(duration_minutes)s, %(notes)s,
                    %(source)s, %(status)s, %(legacy_neo4j_id)s
                )
                ON CONFLICT (session_date, name) DO UPDATE SET
                    duration_minutes = EXCLUDED.duration_minutes,
                    notes = EXCLUDED.notes,
                    legacy_neo4j_id = EXCLUDED.legacy_neo4j_id
                RETURNING id
            """, session)
            
            session_id = cursor.fetchone()[0]
            sessions_inserted += 1
            
            # Delete existing sets for this session (in case of re-run)
            cursor.execute("DELETE FROM strength_sets WHERE session_id = %s", (session_id,))
            
            # Insert sets
            if sets:
                set_values = []
                for s in sets:
                    set_values.append((
                        session_id,
                        s['block_name'],
                        s['block_type'],
                        s['set_order'],
                        s['exercise_id'],
                        s['exercise_name'],
                        s['actual_reps'],
                        s['actual_load_lbs'],
                        s['actual_rpe'],
                        s['notes'],
                        s['legacy_neo4j_id']
                    ))
                
                execute_values(cursor, """
                    INSERT INTO strength_sets (
                        session_id, block_name, block_type, set_order,
                        exercise_id, exercise_name,
                        actual_reps, actual_load_lbs, actual_rpe,
                        notes, legacy_neo4j_id
                    ) VALUES %s
                """, set_values)
                
                sets_inserted += len(sets)
            
            # Update session totals
            cursor.execute("SELECT update_session_totals(%s)", (session_id,))
        
        pg.conn.commit()
        logger.info(f"Inserted {sessions_inserted} sessions, {sets_inserted} sets")
        
        # Update migration status
        cursor.execute("""
            UPDATE _migration_status 
            SET completed_at = NOW(), 
                records_migrated = %s,
                notes = 'Migration completed successfully'
            WHERE migration_name = '010_strength_workouts'
        """, (sessions_inserted,))
        pg.conn.commit()
        
        return sessions_inserted, sets_inserted
        
    except Exception as e:
        pg.conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise


def create_neo4j_references(neo4j: Neo4jClient, pg: PostgresClient, dry_run: bool = False):
    """Create lightweight StrengthWorkout reference nodes in Neo4j."""
    
    logger.info("Creating Neo4j reference nodes...")
    
    # Get migrated sessions with their legacy IDs
    cursor = pg.conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT id, session_date, name, legacy_neo4j_id, total_volume_lbs, total_sets
        FROM strength_sessions
        WHERE legacy_neo4j_id IS NOT NULL
    """)
    sessions = cursor.fetchall()
    
    if dry_run:
        logger.info(f"Would create {len(sessions)} StrengthWorkout reference nodes")
        return 0
    
    created = 0
    for s in sessions:
        # Create StrengthWorkout reference node
        cypher = """
        MATCH (p:Person {name: 'Brock Webb'})
        MATCH (w:Workout {id: $legacy_id})
        
        // Create new reference node
        MERGE (sw:StrengthWorkout {postgres_id: $postgres_id})
        SET sw.id = randomUUID(),
            sw.date = date($date),
            sw.name = $name,
            sw.total_volume_lbs = $volume,
            sw.total_sets = $sets,
            sw.created_at = datetime()
        
        // Copy PERFORMED relationship
        MERGE (p)-[:PERFORMED]->(sw)
        
        // Link to original for traceability
        MERGE (sw)-[:MIGRATED_FROM]->(w)
        
        RETURN sw.id as id
        """
        
        try:
            result = neo4j.query(cypher, {
                'legacy_id': s['legacy_neo4j_id'],
                'postgres_id': s['id'],
                'date': str(s['session_date']),
                'name': s['name'],
                'volume': float(s['total_volume_lbs']) if s['total_volume_lbs'] else 0,
                'sets': s['total_sets'] or 0
            })
            
            if result:
                # Update Postgres with Neo4j ID
                neo4j_id = result[0]['id']
                cursor.execute(
                    "UPDATE strength_sessions SET neo4j_id = %s WHERE id = %s",
                    (neo4j_id, s['id'])
                )
                created += 1
                
        except Exception as e:
            logger.warning(f"Failed to create ref for session {s['id']}: {e}")
    
    pg.conn.commit()
    logger.info(f"Created {created} StrengthWorkout reference nodes")
    return created


def verify_migration(pg: PostgresClient):
    """Verify migration completed successfully."""
    
    cursor = pg.conn.cursor(cursor_factory=RealDictCursor)
    
    # Count records
    cursor.execute("SELECT COUNT(*) as count FROM strength_sessions")
    sessions = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM strength_sets")
    sets = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM strength_sessions 
        WHERE neo4j_id IS NOT NULL
    """)
    with_refs = cursor.fetchone()['count']
    
    # Sample data
    cursor.execute("""
        SELECT session_date, name, total_sets, total_volume_lbs
        FROM strength_sessions
        ORDER BY session_date DESC
        LIMIT 5
    """)
    recent = cursor.fetchall()
    
    logger.info("=== Migration Verification ===")
    logger.info(f"Sessions: {sessions}")
    logger.info(f"Sets: {sets}")
    logger.info(f"With Neo4j refs: {with_refs}")
    logger.info("")
    logger.info("Recent sessions:")
    for r in recent:
        logger.info(f"  {r['session_date']} - {r['name']}: {r['total_sets']} sets, {r['total_volume_lbs']} lbs")


def main():
    parser = argparse.ArgumentParser(description='Migrate strength workouts from Neo4j to Postgres')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--force', action='store_true', help='Re-run even if already migrated')
    parser.add_argument('--skip-refs', action='store_true', help='Skip Neo4j reference creation')
    parser.add_argument('--verify-only', action='store_true', help='Only verify existing migration')
    args = parser.parse_args()
    
    # Connect to databases
    neo4j = Neo4jClient().connect()
    pg = PostgresClient().connect()
    
    try:
        if args.verify_only:
            verify_migration(pg)
            return
        
        # Check if already migrated
        cursor = pg.conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT completed_at, records_migrated 
            FROM _migration_status 
            WHERE migration_name = '010_strength_workouts'
        """)
        status = cursor.fetchone()
        
        if status and status['completed_at'] and not args.force:
            logger.info(f"Migration already completed at {status['completed_at']}")
            logger.info(f"Records migrated: {status['records_migrated']}")
            logger.info("Use --force to re-run")
            verify_migration(pg)
            return
        
        # Extract from Neo4j
        workouts = extract_workouts(neo4j)
        
        # Load to Postgres
        sessions, sets = load_to_postgres(pg, workouts, dry_run=args.dry_run)
        
        # Create Neo4j references
        if not args.dry_run and not args.skip_refs:
            create_neo4j_references(neo4j, pg, dry_run=args.dry_run)
        
        # Verify
        if not args.dry_run:
            verify_migration(pg)
        
    finally:
        neo4j.close()
        pg.close()


if __name__ == "__main__":
    main()
