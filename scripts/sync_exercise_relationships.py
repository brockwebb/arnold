#!/usr/bin/env python3
"""
Sync exercise relationship data from Neo4j to Postgres cache tables.

This script syncs two relationship types:
1. INVOLVES: Exercise → MovementPattern (for pattern tracking)
2. TARGETS: Exercise → Muscle/MuscleGroup (for volume tracking)

Architecture (per ADR-001):
- Neo4j is SOURCE OF TRUTH for relationships
- Postgres cache tables are READ-ONLY copies for analytics joins
- One-way sync only; never write back to Neo4j

Run: python scripts/sync_exercise_relationships.py

QC output helps validate sync quality and identifies coverage gaps.
"""

import os
import sys
from datetime import datetime
from neo4j import GraphDatabase
import psycopg2
from psycopg2.extras import execute_values

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

# Postgres connection
PG_URI = os.getenv("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def ensure_cache_tables(conn):
    """Create cache tables if they don't exist."""
    cur = conn.cursor()
    
    # Pattern cache (already exists, but ensure it's correct)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS neo4j_cache_exercise_patterns (
            exercise_id TEXT NOT NULL,
            exercise_name TEXT NOT NULL,
            pattern_name TEXT NOT NULL,
            confidence FLOAT,
            synced_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (exercise_id, pattern_name)
        );
        
        CREATE INDEX IF NOT EXISTS idx_cache_patterns_exercise 
            ON neo4j_cache_exercise_patterns(exercise_id);
        CREATE INDEX IF NOT EXISTS idx_cache_patterns_pattern 
            ON neo4j_cache_exercise_patterns(pattern_name);
    """)
    
    # Muscle targets cache (new)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS neo4j_cache_exercise_muscles (
            exercise_id TEXT NOT NULL,
            exercise_name TEXT NOT NULL,
            muscle_name TEXT NOT NULL,
            muscle_type TEXT NOT NULL,  -- 'Muscle' or 'MuscleGroup'
            role TEXT NOT NULL DEFAULT 'unknown',  -- 'primary', 'secondary', or 'unknown'
            confidence FLOAT,
            synced_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (exercise_id, muscle_name, role)
        );
        
        CREATE INDEX IF NOT EXISTS idx_cache_muscles_exercise 
            ON neo4j_cache_exercise_muscles(exercise_id);
        CREATE INDEX IF NOT EXISTS idx_cache_muscles_muscle 
            ON neo4j_cache_exercise_muscles(muscle_name);
        CREATE INDEX IF NOT EXISTS idx_cache_muscles_role 
            ON neo4j_cache_exercise_muscles(role);
    """)
    
    conn.commit()
    cur.close()
    print("✓ Cache tables verified/created")


def get_pattern_relationships():
    """Extract INVOLVES relationships from Neo4j."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    MATCH (e:Exercise)-[r:INVOLVES]->(mp:MovementPattern)
    RETURN 
        e.id as exercise_id,
        e.name as exercise_name,
        mp.name as pattern_name,
        r.confidence as confidence,
        coalesce(r.human_verified, false) as human_verified
    ORDER BY e.id, mp.name
    """
    
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        data = [dict(r) for r in result]
    
    driver.close()
    return data


def get_muscle_relationships():
    """Extract TARGETS relationships from Neo4j."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    MATCH (e:Exercise)-[r:TARGETS]->(m)
    WHERE m:Muscle OR m:MuscleGroup
    RETURN 
        e.id as exercise_id,
        e.name as exercise_name,
        m.name as muscle_name,
        labels(m)[0] as muscle_type,
        r.role as role,
        r.confidence as confidence,
        coalesce(r.human_verified, false) as human_verified
    ORDER BY e.id, m.name
    """
    
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        data = [dict(r) for r in result]
    
    driver.close()
    return data


def sync_patterns(conn, data):
    """Sync pattern relationships to Postgres."""
    cur = conn.cursor()
    
    # Truncate and reload (full sync)
    cur.execute("TRUNCATE neo4j_cache_exercise_patterns")
    
    rows = [
        (d['exercise_id'], d['exercise_name'], d['pattern_name'], d['confidence'], d['human_verified'])
        for d in data
    ]
    
    sql = """
        INSERT INTO neo4j_cache_exercise_patterns 
            (exercise_id, exercise_name, pattern_name, confidence, human_verified)
        VALUES %s
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    cur.close()
    
    return len(rows)


def sync_muscles(conn, data):
    """Sync muscle relationships to Postgres."""
    cur = conn.cursor()
    
    # Truncate and reload (full sync)
    cur.execute("TRUNCATE neo4j_cache_exercise_muscles")
    
    # Dedupe: same exercise + muscle + role can appear twice if targeting both Muscle and MuscleGroup
    # Keep Muscle over MuscleGroup (more specific)
    seen = {}
    for d in data:
        key = (d['exercise_id'], d['muscle_name'], d['role'] or 'unknown')
        if key not in seen:
            seen[key] = d
        elif d['muscle_type'] == 'Muscle':  # Prefer Muscle over MuscleGroup
            seen[key] = d
    
    rows = [
        (d['exercise_id'], d['exercise_name'], d['muscle_name'], 
         d['muscle_type'], d['role'] or 'unknown', d['confidence'], d['human_verified'])
        for d in seen.values()
    ]
    
    sql = """
        INSERT INTO neo4j_cache_exercise_muscles 
            (exercise_id, exercise_name, muscle_name, muscle_type, role, confidence, human_verified)
        VALUES %s
    """
    
    execute_values(cur, sql, rows)
    conn.commit()
    cur.close()
    
    return len(rows)


def run_qc(conn):
    """Run quality control checks and return results."""
    cur = conn.cursor()
    qc_results = {}
    
    # 1. Pattern cache stats
    cur.execute("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT exercise_id) as unique_exercises,
            COUNT(DISTINCT pattern_name) as unique_patterns,
            COUNT(CASE WHEN human_verified THEN 1 END) as verified_count,
            MIN(synced_at) as sync_time
        FROM neo4j_cache_exercise_patterns
    """)
    row = cur.fetchone()
    qc_results['patterns'] = {
        'total_rows': row[0],
        'unique_exercises': row[1],
        'unique_patterns': row[2],
        'verified_count': row[3],
        'sync_time': row[4]
    }
    
    # 2. Muscle cache stats
    cur.execute("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT exercise_id) as unique_exercises,
            COUNT(DISTINCT muscle_name) as unique_muscles,
            COUNT(CASE WHEN role = 'primary' THEN 1 END) as primary_count,
            COUNT(CASE WHEN role = 'secondary' THEN 1 END) as secondary_count,
            COUNT(CASE WHEN human_verified THEN 1 END) as verified_count,
            MIN(synced_at) as sync_time
        FROM neo4j_cache_exercise_muscles
    """)
    row = cur.fetchone()
    qc_results['muscles'] = {
        'total_rows': row[0],
        'unique_exercises': row[1],
        'unique_muscles': row[2],
        'primary_count': row[3],
        'secondary_count': row[4],
        'verified_count': row[5],
        'sync_time': row[6]
    }
    
    # 3. Coverage: exercises in strength_sets that have cache data
    cur.execute("""
        WITH workout_exercises AS (
            SELECT DISTINCT exercise_id FROM strength_sets
        )
        SELECT 
            COUNT(*) as total_workout_exercises,
            COUNT(CASE WHEN p.exercise_id IS NOT NULL THEN 1 END) as with_patterns,
            COUNT(CASE WHEN m.exercise_id IS NOT NULL THEN 1 END) as with_muscles
        FROM workout_exercises we
        LEFT JOIN (SELECT DISTINCT exercise_id FROM neo4j_cache_exercise_patterns) p 
            ON we.exercise_id = p.exercise_id
        LEFT JOIN (SELECT DISTINCT exercise_id FROM neo4j_cache_exercise_muscles) m 
            ON we.exercise_id = m.exercise_id
    """)
    row = cur.fetchone()
    qc_results['coverage'] = {
        'total_workout_exercises': row[0],
        'with_patterns': row[1],
        'with_muscles': row[2],
        'pattern_coverage_pct': round(100 * row[1] / row[0], 1) if row[0] > 0 else 0,
        'muscle_coverage_pct': round(100 * row[2] / row[0], 1) if row[0] > 0 else 0
    }
    
    # 4. Missing exercises (in workouts but not in cache)
    cur.execute("""
        WITH workout_exercises AS (
            SELECT DISTINCT exercise_id, exercise_name FROM strength_sets
        )
        SELECT we.exercise_id, we.exercise_name
        FROM workout_exercises we
        LEFT JOIN (SELECT DISTINCT exercise_id FROM neo4j_cache_exercise_patterns) p 
            ON we.exercise_id = p.exercise_id
        WHERE p.exercise_id IS NULL
        ORDER BY we.exercise_name
        LIMIT 20
    """)
    qc_results['missing_exercises'] = [
        {'exercise_id': row[0], 'exercise_name': row[1]} 
        for row in cur.fetchall()
    ]
    
    # 5. Pattern distribution
    cur.execute("""
        SELECT pattern_name, COUNT(*) as exercise_count
        FROM neo4j_cache_exercise_patterns
        GROUP BY pattern_name
        ORDER BY exercise_count DESC
    """)
    qc_results['pattern_distribution'] = [
        {'pattern': row[0], 'count': row[1]} 
        for row in cur.fetchall()
    ]
    
    # 6. Top muscles by exercise count
    cur.execute("""
        SELECT muscle_name, role, COUNT(*) as exercise_count
        FROM neo4j_cache_exercise_muscles
        WHERE role = 'primary'
        GROUP BY muscle_name, role
        ORDER BY exercise_count DESC
        LIMIT 15
    """)
    qc_results['top_primary_muscles'] = [
        {'muscle': row[0], 'count': row[2]} 
        for row in cur.fetchall()
    ]
    
    cur.close()
    return qc_results


def print_qc_report(qc):
    """Print formatted QC report."""
    print("\n" + "="*60)
    print("QC REPORT: Neo4j → Postgres Relationship Sync")
    print("="*60)
    
    print("\n📊 PATTERN CACHE")
    p = qc['patterns']
    print(f"   Total rows:        {p['total_rows']:,}")
    print(f"   Unique exercises:  {p['unique_exercises']:,}")
    print(f"   Unique patterns:   {p['unique_patterns']}")
    print(f"   Human verified:    {p['verified_count']:,} ({100*p['verified_count']/p['total_rows']:.1f}%)" if p['total_rows'] > 0 else "   Human verified:    0")
    print(f"   Synced at:         {p['sync_time']}")
    
    print("\n💪 MUSCLE CACHE")
    m = qc['muscles']
    print(f"   Total rows:        {m['total_rows']:,}")
    print(f"   Unique exercises:  {m['unique_exercises']:,}")
    print(f"   Unique muscles:    {m['unique_muscles']}")
    print(f"   Primary targets:   {m['primary_count']:,}")
    print(f"   Secondary targets: {m['secondary_count']:,}")
    print(f"   Human verified:    {m['verified_count']:,} ({100*m['verified_count']/m['total_rows']:.1f}%)" if m['total_rows'] > 0 else "   Human verified:    0")
    print(f"   Synced at:         {m['sync_time']}")
    
    print("\n🎯 WORKOUT COVERAGE")
    c = qc['coverage']
    print(f"   Exercises in workouts: {c['total_workout_exercises']}")
    print(f"   With patterns:         {c['with_patterns']} ({c['pattern_coverage_pct']}%)")
    print(f"   With muscles:          {c['with_muscles']} ({c['muscle_coverage_pct']}%)")
    
    if qc['missing_exercises']:
        print("\n⚠️  MISSING FROM CACHE (first 20)")
        for ex in qc['missing_exercises'][:10]:
            print(f"   - {ex['exercise_name']} ({ex['exercise_id']})")
        if len(qc['missing_exercises']) > 10:
            print(f"   ... and {len(qc['missing_exercises']) - 10} more")
    
    print("\n📈 PATTERN DISTRIBUTION")
    for p in qc['pattern_distribution'][:10]:
        bar = "█" * min(50, p['count'] // 20)
        print(f"   {p['pattern']:<20} {p['count']:>4} {bar}")
    
    print("\n🏋️ TOP PRIMARY MUSCLES")
    for m in qc['top_primary_muscles'][:10]:
        bar = "█" * min(50, m['count'] // 20)
        print(f"   {m['muscle']:<25} {m['count']:>4} {bar}")
    
    print("\n" + "="*60)


def main():
    print(f"Neo4j → Postgres Relationship Sync")
    print(f"Started: {datetime.now().isoformat()}")
    print("-" * 40)
    
    # Connect to Postgres
    print("\n1. Connecting to Postgres...")
    conn = psycopg2.connect(PG_URI)
    
    # Ensure tables exist
    print("2. Ensuring cache tables exist...")
    ensure_cache_tables(conn)
    
    # Extract from Neo4j
    print("3. Extracting INVOLVES relationships from Neo4j...")
    pattern_data = get_pattern_relationships()
    print(f"   Found {len(pattern_data):,} pattern relationships")
    
    print("4. Extracting TARGETS relationships from Neo4j...")
    muscle_data = get_muscle_relationships()
    print(f"   Found {len(muscle_data):,} muscle relationships")
    
    # Sync to Postgres
    print("5. Syncing patterns to Postgres...")
    pattern_count = sync_patterns(conn, pattern_data)
    print(f"   Synced {pattern_count:,} rows")
    
    print("6. Syncing muscles to Postgres...")
    muscle_count = sync_muscles(conn, muscle_data)
    print(f"   Synced {muscle_count:,} rows")
    
    # Run QC
    print("7. Running QC checks...")
    qc_results = run_qc(conn)
    
    conn.close()
    
    # Print report
    print_qc_report(qc_results)
    
    # Return exit code based on coverage
    coverage = qc_results['coverage']
    if coverage['pattern_coverage_pct'] < 80 or coverage['muscle_coverage_pct'] < 80:
        print("\n⚠️  WARNING: Coverage below 80% - review missing exercises")
        return 1
    
    print("\n✅ Sync completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
