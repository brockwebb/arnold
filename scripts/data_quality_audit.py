#!/usr/bin/env python3
"""
Arnold Data Quality Audit

Run standalone to check database health. Flags issues for investigation.

Usage:
    python scripts/data_quality_audit.py          # Full audit
    python scripts/data_quality_audit.py --quick  # Skip slow checks

Checks:
    1. Duplicate Detection (biometrics, workouts)
    2. Orphan Detection (exercises without relationships)
    3. Data Completeness (gaps, missing data)
    4. Source Conflicts (same metric from multiple sources)
    5. Value Anomalies (out-of-range values)
    6. Sync Health (Neo4j ↔ Postgres alignment)
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Database configs - with fallbacks
PG_CONFIG = {
    "dbname": os.environ.get("POSTGRES_DB", "arnold_analytics"),
    "user": os.environ.get("POSTGRES_USER", "brock"),
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "port": int(os.environ.get("POSTGRES_PORT", 5432)),
}

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")  # Required from .env
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "arnold")


class AuditResult:
    def __init__(self, name: str):
        self.name = name
        self.status = "PASS"  # PASS, WARN, FAIL
        self.message = ""
        self.details = []
    
    def warn(self, message: str, details: list = None):
        self.status = "WARN"
        self.message = message
        if details:
            self.details = details[:10]
    
    def fail(self, message: str, details: list = None):
        self.status = "FAIL"
        self.message = message
        if details:
            self.details = details[:10]
    
    def ok(self, message: str = ""):
        self.status = "PASS"
        self.message = message


def print_result(result: AuditResult):
    icons = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}
    colors = {"PASS": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m"}
    reset = "\033[0m"
    
    icon = icons[result.status]
    color = colors[result.status]
    
    print(f"{color}{icon} {result.name}: {result.status}{reset}")
    if result.message:
        print(f"    {result.message}")
    for detail in result.details:
        print(f"      - {detail}")


# =============================================================================
# POSTGRES CHECKS
# =============================================================================

def check_biometric_duplicates(cur) -> AuditResult:
    """Check for duplicate biometric readings."""
    result = AuditResult("Biometric Duplicates")
    
    cur.execute("""
        SELECT reading_date, metric_type, source, COUNT(*) as cnt
        FROM biometric_readings
        GROUP BY reading_date, metric_type, source
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)
    dupes = cur.fetchall()
    
    if dupes:
        result.fail(
            f"Found {len(dupes)} duplicate combinations",
            [f"{d[0]} / {d[1]} / {d[2]}: {d[3]} rows" for d in dupes]
        )
    else:
        result.ok("No duplicates")
    
    return result


def check_hrv_source_conflict(cur) -> AuditResult:
    """Check for HRV data from multiple sources on same date (informational)."""
    result = AuditResult("HRV Source Coverage")
    
    cur.execute("""
        SELECT reading_date, array_agg(DISTINCT source) as sources, COUNT(DISTINCT source) as cnt
        FROM biometric_readings
        WHERE metric_type ILIKE '%hrv%'
        GROUP BY reading_date
        HAVING COUNT(DISTINCT source) > 1
        ORDER BY reading_date DESC
        LIMIT 20
    """)
    conflicts = cur.fetchall()
    
    if conflicts:
        # This is expected - Apple Health syncs from Ultrahuman, both kept as distinct streams
        result.ok(f"{len(conflicts)} dates have HRV from multiple sources (expected)")
    else:
        result.ok("Single source per date")
    
    return result


def check_biometric_gaps(cur, days_back: int = 30) -> AuditResult:
    """Check for gaps in daily biometric data."""
    result = AuditResult("Biometric Data Gaps")
    
    cur.execute("""
        WITH date_series AS (
            SELECT generate_series(
                CURRENT_DATE - INTERVAL '%s days',
                CURRENT_DATE - INTERVAL '1 day',
                '1 day'
            )::date as dt
        ),
        daily_metrics AS (
            SELECT DISTINCT reading_date, metric_type
            FROM biometric_readings
            WHERE reading_date >= CURRENT_DATE - INTERVAL '%s days'
        )
        SELECT ds.dt, 
               NOT EXISTS (SELECT 1 FROM daily_metrics dm WHERE dm.reading_date = ds.dt AND dm.metric_type ILIKE '%%hrv%%') as missing_hrv,
               NOT EXISTS (SELECT 1 FROM daily_metrics dm WHERE dm.reading_date = ds.dt AND dm.metric_type ILIKE '%%sleep%%') as missing_sleep
        FROM date_series ds
        WHERE NOT EXISTS (SELECT 1 FROM daily_metrics dm WHERE dm.reading_date = ds.dt AND dm.metric_type ILIKE '%%hrv%%')
           OR NOT EXISTS (SELECT 1 FROM daily_metrics dm WHERE dm.reading_date = ds.dt AND dm.metric_type ILIKE '%%sleep%%')
        ORDER BY ds.dt
    """, (days_back, days_back))
    gaps = cur.fetchall()
    
    if gaps:
        result.warn(
            f"Found {len(gaps)} days with missing HRV or sleep data",
            [f"{g[0]}: {'missing HRV' if g[1] else ''} {'missing sleep' if g[2] else ''}" for g in gaps[:10]]
        )
    else:
        result.ok(f"No gaps in last {days_back} days")
    
    return result


def check_biometric_anomalies(cur) -> AuditResult:
    """Check for biometric values outside reasonable ranges."""
    result = AuditResult("Biometric Value Anomalies")
    
    ranges = {
        'hrv': (5, 200),
        'resting_hr': (30, 100),
        'sleep_total': (0, 720),
        'steps': (0, 50000),
    }
    
    anomalies = []
    
    for metric_pattern, (min_val, max_val) in ranges.items():
        cur.execute("""
            SELECT reading_date, metric_type, value, source
            FROM biometric_readings
            WHERE metric_type ILIKE %s
              AND (value < %s OR value > %s)
            ORDER BY reading_date DESC
            LIMIT 5
        """, (f'%{metric_pattern}%', min_val, max_val))
        
        for row in cur.fetchall():
            anomalies.append(f"{row[0]} {row[1]}: {row[2]} ({row[3]})")
    
    if anomalies:
        result.warn(f"Found {len(anomalies)} out-of-range values", anomalies)
    else:
        result.ok("All values within expected ranges")
    
    return result


def check_workout_integrity(cur) -> AuditResult:
    """Check workout data integrity."""
    result = AuditResult("Workout Data Integrity")
    
    issues = []
    
    # Check which tables exist
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_name IN ('workout_summaries', 'strength_sets')
    """)
    tables = {r[0] for r in cur.fetchall()}
    
    if 'workout_summaries' in tables:
        # Check for duplicates on date
        cur.execute("""
            SELECT workout_date, COUNT(*) as cnt
            FROM workout_summaries
            GROUP BY workout_date
            HAVING COUNT(*) > 1
        """)
        dupe_dates = cur.fetchall()
        if dupe_dates:
            issues.extend([f"Multiple workouts on {d[0]}: {d[1]}x" for d in dupe_dates])
        
        # Check for null dates
        cur.execute("SELECT COUNT(*) FROM workout_summaries WHERE workout_date IS NULL")
        null_dates = cur.fetchone()[0]
        if null_dates > 0:
            issues.append(f"{null_dates} workout summaries with NULL date")
    
    if 'strength_sets' in tables:
        cur.execute("SELECT COUNT(*) FROM strength_sets WHERE exercise_id IS NULL")
        null_ex = cur.fetchone()[0]
        if null_ex > 0:
            issues.append(f"{null_ex} strength_sets with NULL exercise_id")
    
    if not tables:
        result.ok("No workout tables found (Neo4j is source of truth)")
        return result
    
    if issues:
        result.warn(f"Found {len(issues)} issues", issues)
    else:
        result.ok(f"Workout data clean (tables: {', '.join(tables)})")
    
    return result


def check_sync_history(cur) -> AuditResult:
    """Check recent sync history for failures."""
    result = AuditResult("Sync History")
    
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'sync_history'
        )
    """)
    if not cur.fetchone()[0]:
        result.ok("No sync_history table (manual syncs only)")
        return result
    
    cur.execute("""
        SELECT id, started_at, completed_at, status, error_message
        FROM sync_history
        ORDER BY started_at DESC
        LIMIT 10
    """)
    syncs = cur.fetchall()
    
    if not syncs:
        result.warn("No sync history found")
        return result
    
    failures = [s for s in syncs if s[3] == 'failed']
    last_sync = syncs[0]
    
    if failures:
        result.warn(
            f"Last 10 syncs: {len(failures)} failures",
            [f"Sync #{f[0]} at {f[1]}: {f[4]}" for f in failures]
        )
    else:
        age = datetime.now() - last_sync[1].replace(tzinfo=None) if last_sync[1] else timedelta(days=999)
        if age > timedelta(hours=24):
            result.warn(f"Last sync was {age.days}d {age.seconds//3600}h ago")
        else:
            result.ok(f"Last sync: {last_sync[1]} ({last_sync[3]})")
    
    return result


# =============================================================================
# NEO4J CHECKS
# =============================================================================

def check_neo4j_orphan_exercises(session) -> AuditResult:
    """Check for exercises without TARGETS or INVOLVES relationships."""
    result = AuditResult("Neo4j Orphan Exercises")
    
    res = session.run("""
        MATCH (e:Exercise)
        WHERE NOT (e)-[:TARGETS]->() AND NOT (e)-[:INVOLVES]->()
        RETURN e.name, e.id, e.source
        LIMIT 20
    """)
    orphans = [(r['e.name'], r['e.id'], r['e.source']) for r in res]
    
    if orphans:
        result.warn(
            f"Found {len(orphans)} exercises without relationships",
            [f"{o[0]} ({o[2]})" for o in orphans]
        )
    else:
        result.ok("All exercises have relationships")
    
    return result


def check_neo4j_dangling_refs(session) -> AuditResult:
    """Check for relationships pointing to wrong node types."""
    result = AuditResult("Neo4j Dangling References")
    
    issues = []
    
    # OF_EXERCISE should point to Exercise or ExerciseVariant
    res = session.run("""
        MATCH (s:Set)-[r:OF_EXERCISE]->(e)
        WHERE NOT e:Exercise AND NOT e:ExerciseVariant
        RETURN COUNT(r) as cnt
    """)
    bad_refs = res.single()['cnt']
    if bad_refs > 0:
        issues.append(f"{bad_refs} OF_EXERCISE to non-Exercise nodes")
    
    # TARGETS should point to Muscle or MuscleGroup
    res = session.run("""
        MATCH (e:Exercise)-[r:TARGETS]->(m)
        WHERE NOT m:Muscle AND NOT m:MuscleGroup
        RETURN COUNT(r) as cnt
    """)
    bad_targets = res.single()['cnt']
    if bad_targets > 0:
        issues.append(f"{bad_targets} TARGETS to non-Muscle nodes")
    
    # INVOLVES should point to MovementPattern or Movement
    res = session.run("""
        MATCH (e:Exercise)-[r:INVOLVES]->(mp)
        WHERE NOT mp:MovementPattern AND NOT mp:Movement
        RETURN COUNT(r) as cnt
    """)
    bad_involves = res.single()['cnt']
    if bad_involves > 0:
        issues.append(f"{bad_involves} INVOLVES to non-MovementPattern nodes")
    
    if issues:
        result.fail("Found dangling references", issues)
    else:
        result.ok("No dangling references")
    
    return result


def check_neo4j_workout_counts(session, pg_cur) -> AuditResult:
    """Check Neo4j vs Postgres workout counts."""
    result = AuditResult("Neo4j ↔ Postgres Workout Sync")
    
    # Neo4j count (Workout label)
    res = session.run("MATCH (w:Workout) RETURN COUNT(w) as cnt")
    neo4j_count = res.single()['cnt']
    
    # Postgres count
    pg_cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'workout_summaries'
        )
    """)
    if pg_cur.fetchone()[0]:
        pg_cur.execute("SELECT COUNT(*) FROM workout_summaries")
        pg_count = pg_cur.fetchone()[0]
    else:
        result.ok(f"Neo4j: {neo4j_count} workouts (no Postgres table)")
        return result
    
    diff = abs(neo4j_count - pg_count)
    
    if diff > 5:
        result.warn(f"Count mismatch: Neo4j={neo4j_count}, Postgres={pg_count} (diff: {diff})")
    elif diff > 0:
        result.ok(f"Minor diff: Neo4j={neo4j_count}, Postgres={pg_count}")
    else:
        result.ok(f"Counts match: {neo4j_count}")
    
    return result


def check_neo4j_exercise_counts(session) -> AuditResult:
    """Check Neo4j exercise counts."""
    result = AuditResult("Neo4j Exercise Counts")
    
    res = session.run("""
        MATCH (e:Exercise) RETURN COUNT(e) as total,
        SUM(CASE WHEN (e)-[:TARGETS]->() THEN 1 ELSE 0 END) as with_targets,
        SUM(CASE WHEN (e)-[:INVOLVES]->() THEN 1 ELSE 0 END) as with_involves
    """)
    r = res.single()
    total = r['total']
    with_targets = r['with_targets']
    with_involves = r['with_involves']
    
    coverage_targets = (with_targets / total * 100) if total > 0 else 0
    coverage_involves = (with_involves / total * 100) if total > 0 else 0
    
    if coverage_targets < 90 or coverage_involves < 90:
        result.warn(
            f"{total} exercises: {coverage_targets:.0f}% have TARGETS, {coverage_involves:.0f}% have INVOLVES"
        )
    else:
        result.ok(f"{total} exercises: {coverage_targets:.0f}% TARGETS, {coverage_involves:.0f}% INVOLVES")
    
    return result


def check_schema_inventory(session, pg_cur) -> AuditResult:
    """Report what exists in both databases."""
    result = AuditResult("Schema Inventory")
    
    inventory = []
    
    # Postgres tables
    pg_cur.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    pg_tables = [r[0] for r in pg_cur.fetchall()]
    inventory.append(f"Postgres: {len(pg_tables)} tables")
    
    # Neo4j counts for key labels
    res = session.run("""
        MATCH (n) 
        WITH labels(n)[0] as label, count(*) as cnt
        RETURN label, cnt ORDER BY cnt DESC LIMIT 10
    """)
    counts = [(r['label'], r['cnt']) for r in res]
    
    inventory.append(f"Neo4j top labels:")
    for label, cnt in counts:
        inventory.append(f"  {label}: {cnt}")
    
    result.ok("Schema discovered")
    result.details = inventory
    return result


# =============================================================================
# MAIN
# =============================================================================

def run_audit(quick: bool = False):
    results = []
    
    print("=" * 60)
    print("Arnold Data Quality Audit")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Connect to Postgres
    print("\n--- Postgres Checks ---")
    pg_conn = None
    pg_cur = None
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        pg_conn.autocommit = True
        pg_cur = pg_conn.cursor()
        
        results.append(check_biometric_duplicates(pg_cur))
        results.append(check_hrv_source_conflict(pg_cur))
        results.append(check_biometric_anomalies(pg_cur))
        results.append(check_workout_integrity(pg_cur))
        results.append(check_sync_history(pg_cur))
        
        if not quick:
            results.append(check_biometric_gaps(pg_cur))
        
    except Exception as e:
        r = AuditResult("Postgres Connection")
        r.fail(str(e))
        results.append(r)
    
    # Connect to Neo4j
    print("\n--- Neo4j Checks ---")
    driver = None
    try:
        if not NEO4J_PASSWORD:
            raise ValueError("NEO4J_PASSWORD not set in environment. Check .env file.")
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        
        with driver.session(database=NEO4J_DATABASE) as session:
            results.append(check_neo4j_orphan_exercises(session))
            results.append(check_neo4j_dangling_refs(session))
            results.append(check_neo4j_exercise_counts(session))
            
            if pg_cur:
                results.append(check_neo4j_workout_counts(session, pg_cur))
                results.append(check_schema_inventory(session, pg_cur))
        
        driver.close()
        
    except Exception as e:
        r = AuditResult("Neo4j Connection")
        r.fail(str(e))
        results.append(r)
    
    # Cleanup
    if pg_conn:
        pg_conn.close()
    
    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60 + "\n")
    
    for r in results:
        print_result(r)
        print()
    
    # Summary
    passes = sum(1 for r in results if r.status == "PASS")
    warns = sum(1 for r in results if r.status == "WARN")
    fails = sum(1 for r in results if r.status == "FAIL")
    
    print("=" * 60)
    print(f"Summary: {passes} passed, {warns} warnings, {fails} failures")
    print("=" * 60)
    
    return 0 if fails == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Arnold Data Quality Audit")
    parser.add_argument("--quick", action="store_true", help="Skip slow checks")
    args = parser.parse_args()
    
    sys.exit(run_audit(quick=args.quick))


if __name__ == "__main__":
    main()
