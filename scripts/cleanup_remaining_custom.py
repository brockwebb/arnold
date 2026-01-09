#!/usr/bin/env python3
"""
Cleanup remaining 11 CUSTOM exercises after main migration.

These were MERGE_TO_CANONICAL in the CSV but their target IDs didn't exist.
This script uses the CORRECT target IDs found by manual lookup.

Mappings:
  MERGE (6):
    - Glute Bridges → CANONICAL:FFDB:13 (Bodyweight Glute Bridge)
    - Hollow Hold → CANONICAL:FFDB:70 (Bodyweight Hollow Body Hold)  
    - Side-Lying Clamshells → CANONICAL:FFDB:3238 (Bodyweight Side Lying Clamshell)
    - Standing Hamstring Stretch → EXERCISE:Hamstring_Stretch
    - Standing Quad Stretch → EXERCISE:Quad_Stretch
    - V-Up → CANONICAL:FFDB:1841 (Bodyweight V Up)

  PROMOTE (5) - no generic equivalent exists:
    - Jumping Jack → CANONICAL:ARNOLD:JUMPING_JACK
    - Suitcase Carry → CANONICAL:ARNOLD:SUITCASE_CARRY
    - Turkish Get-Up → CANONICAL:ARNOLD:TURKISH_GET_UP
    - Weighted Plank → CANONICAL:ARNOLD:WEIGHTED_PLANK
    - Weighted Push-Ups → CANONICAL:ARNOLD:WEIGHTED_PUSH_UPS

Usage:
    python scripts/cleanup_remaining_custom.py --dry-run    # Preview
    python scripts/cleanup_remaining_custom.py              # Execute
    python scripts/cleanup_remaining_custom.py --validate   # Check state
"""

import os
import sys
import argparse
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from neo4j import GraphDatabase
import psycopg2

# Connection settings
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")
PG_URI = os.getenv("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


@dataclass
class MergeMapping:
    """CUSTOM exercise to merge into existing canonical."""
    custom_id: str
    custom_name: str
    target_id: str
    target_name: str


@dataclass  
class PromoteMapping:
    """CUSTOM exercise to promote (no equivalent exists)."""
    custom_id: str
    custom_name: str
    new_id: str


# Hardcoded mappings based on manual analysis
MERGE_MAPPINGS = [
    MergeMapping(
        custom_id='CUSTOM:Glute_Bridges',
        custom_name='Glute Bridges',
        target_id='CANONICAL:FFDB:13',
        target_name='Bodyweight Glute Bridge'
    ),
    MergeMapping(
        custom_id='CUSTOM:Hollow_Hold',
        custom_name='Hollow Hold',
        target_id='CANONICAL:FFDB:70',
        target_name='Bodyweight Hollow Body Hold'
    ),
    MergeMapping(
        custom_id='CUSTOM:Side-Lying_Clamshells',
        custom_name='Side-Lying Clamshells',
        target_id='CANONICAL:FFDB:3238',
        target_name='Bodyweight Side Lying Clamshell'
    ),
    MergeMapping(
        custom_id='CUSTOM:Standing_Hamstring_Stretch',
        custom_name='Standing Hamstring Stretch',
        target_id='EXERCISE:Hamstring_Stretch',
        target_name='Hamstring Stretch'
    ),
    MergeMapping(
        custom_id='CUSTOM:Standing_Quad_Stretch',
        custom_name='Standing Quad Stretch',
        target_id='EXERCISE:Quad_Stretch',
        target_name='Quad Stretch'
    ),
    MergeMapping(
        custom_id='CUSTOM:V-Up',
        custom_name='V-Up',
        target_id='CANONICAL:FFDB:1841',
        target_name='Bodyweight V Up'
    ),
]

PROMOTE_MAPPINGS = [
    PromoteMapping(
        custom_id='CUSTOM:Jumping_Jack',
        custom_name='Jumping Jack',
        new_id='CANONICAL:ARNOLD:JUMPING_JACK'
    ),
    PromoteMapping(
        custom_id='CUSTOM:Suitcase_Carry',
        custom_name='Suitcase Carry',
        new_id='CANONICAL:ARNOLD:SUITCASE_CARRY'
    ),
    PromoteMapping(
        custom_id='CUSTOM:Turkish_Get-Up',
        custom_name='Turkish Get-Up',
        new_id='CANONICAL:ARNOLD:TURKISH_GET_UP'
    ),
    PromoteMapping(
        custom_id='CUSTOM:Weighted_Plank',
        custom_name='Weighted Plank',
        new_id='CANONICAL:ARNOLD:WEIGHTED_PLANK'
    ),
    PromoteMapping(
        custom_id='CUSTOM:Weighted_Push-Ups',
        custom_name='Weighted Push-Ups',
        new_id='CANONICAL:ARNOLD:WEIGHTED_PUSH_UPS'
    ),
]


class CleanupMigrator:
    """Handle the cleanup migration."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.pg_conn = psycopg2.connect(PG_URI)
        
        # Stats
        self.merged = 0
        self.promoted = 0
        self.pg_updated = 0
        self.aliases_added = 0
        self.nodes_deleted = 0
        self.muscles_transferred = 0
        self.errors = []
    
    def close(self):
        self.neo4j_driver.close()
        self.pg_conn.close()
    
    def log(self, msg: str):
        prefix = "[DRY-RUN] " if self.dry_run else ""
        print(f"{prefix}{msg}")
    
    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------
    
    def neo4j_exercise_exists(self, exercise_id: str) -> bool:
        """Check if exercise exists in Neo4j."""
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.id",
                id=exercise_id
            )
            return result.single() is not None
    
    def neo4j_get_muscle_count(self, exercise_id: str) -> int:
        """Get TARGETS relationship count."""
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Exercise {id: $id})-[r:TARGETS]->() RETURN count(r) as cnt",
                id=exercise_id
            )
            return result.single()['cnt']
    
    def pg_get_set_count(self, exercise_id: str) -> int:
        """Get count of sets referencing this exercise."""
        cur = self.pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM strength_sets WHERE exercise_id = %s", (exercise_id,))
        count = cur.fetchone()[0]
        cur.close()
        return count
    
    # -------------------------------------------------------------------------
    # Neo4j operations
    # -------------------------------------------------------------------------
    
    def neo4j_add_alias(self, exercise_id: str, alias: str):
        """Add alias to exercise."""
        if self.dry_run:
            return
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            session.run("""
                MATCH (e:Exercise {id: $id})
                SET e.aliases = CASE 
                    WHEN e.aliases IS NULL THEN [$alias]
                    WHEN NOT $alias IN e.aliases THEN e.aliases + $alias
                    ELSE e.aliases
                END
            """, id=exercise_id, alias=alias)
        self.aliases_added += 1
    
    def neo4j_transfer_muscles(self, from_id: str, to_id: str):
        """Transfer TARGETS relationships if source has more."""
        from_count = self.neo4j_get_muscle_count(from_id)
        to_count = self.neo4j_get_muscle_count(to_id)
        
        if from_count <= to_count:
            return False
        
        self.log(f"    Transferring muscle data ({from_count} > {to_count})")
        
        if self.dry_run:
            return True
            
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            # Delete existing on target
            session.run(
                "MATCH (e:Exercise {id: $id})-[r:TARGETS]->() DELETE r",
                id=to_id
            )
            # Copy from source
            session.run("""
                MATCH (src:Exercise {id: $from_id})-[r:TARGETS]->(m)
                MATCH (dst:Exercise {id: $to_id})
                MERGE (dst)-[r2:TARGETS]->(m)
                SET r2.role = r.role,
                    r2.source = r.source,
                    r2.confidence = r.confidence,
                    r2.transferred_from = $from_id,
                    r2.transferred_at = datetime()
            """, from_id=from_id, to_id=to_id)
        
        self.muscles_transferred += 1
        return True
    
    def neo4j_delete_exercise(self, exercise_id: str):
        """Delete exercise node."""
        if self.dry_run:
            return
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                "MATCH (e:Exercise {id: $id}) DETACH DELETE e",
                id=exercise_id
            )
        self.nodes_deleted += 1
    
    def neo4j_rename_exercise(self, old_id: str, new_id: str):
        """Rename exercise ID (promote)."""
        if self.dry_run:
            return
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            session.run("""
                MATCH (e:Exercise {id: $old_id})
                SET e.id = $new_id,
                    e.source = 'arnold_promoted',
                    e.promoted_at = datetime(),
                    e.promoted_from = $old_id
            """, old_id=old_id, new_id=new_id)
    
    # -------------------------------------------------------------------------
    # Postgres operations
    # -------------------------------------------------------------------------
    
    def pg_update_refs(self, old_id: str, new_id: str) -> int:
        """Update exercise_id in strength_sets."""
        if self.dry_run:
            return self.pg_get_set_count(old_id)
        
        cur = self.pg_conn.cursor()
        cur.execute(
            "UPDATE strength_sets SET exercise_id = %s WHERE exercise_id = %s",
            (new_id, old_id)
        )
        count = cur.rowcount
        self.pg_conn.commit()
        cur.close()
        self.pg_updated += count
        return count
    
    # -------------------------------------------------------------------------
    # Migration actions
    # -------------------------------------------------------------------------
    
    def do_merge(self, m: MergeMapping):
        """Execute a MERGE operation."""
        self.log(f"\n  MERGE: {m.custom_name} → {m.target_name}")
        self.log(f"         {m.custom_id} → {m.target_id}")
        
        # Validate target exists
        if not self.neo4j_exercise_exists(m.target_id):
            self.errors.append(f"Target not found: {m.target_id}")
            self.log(f"    ❌ ERROR: Target {m.target_id} not found!")
            return
        
        # Validate source exists
        if not self.neo4j_exercise_exists(m.custom_id):
            self.errors.append(f"Source not found: {m.custom_id}")
            self.log(f"    ❌ ERROR: Source {m.custom_id} not found!")
            return
        
        # 1. Update Postgres refs
        count = self.pg_update_refs(m.custom_id, m.target_id)
        self.log(f"    Postgres: {count} rows updated")
        
        # 2. Add alias
        self.neo4j_add_alias(m.target_id, m.custom_name)
        self.log(f"    Neo4j: Added alias '{m.custom_name}'")
        
        # 3. Transfer muscles if CUSTOM has better data
        self.neo4j_transfer_muscles(m.custom_id, m.target_id)
        
        # 4. Delete CUSTOM node
        self.neo4j_delete_exercise(m.custom_id)
        self.log(f"    Neo4j: Deleted {m.custom_id}")
        
        self.merged += 1
    
    def do_promote(self, p: PromoteMapping):
        """Execute a PROMOTE operation."""
        self.log(f"\n  PROMOTE: {p.custom_name}")
        self.log(f"           {p.custom_id} → {p.new_id}")
        
        # Validate source exists
        if not self.neo4j_exercise_exists(p.custom_id):
            self.errors.append(f"Source not found: {p.custom_id}")
            self.log(f"    ❌ ERROR: Source {p.custom_id} not found!")
            return
        
        # Check new ID doesn't already exist
        if self.neo4j_exercise_exists(p.new_id):
            self.errors.append(f"Target already exists: {p.new_id}")
            self.log(f"    ❌ ERROR: {p.new_id} already exists!")
            return
        
        # 1. Update Postgres refs
        count = self.pg_update_refs(p.custom_id, p.new_id)
        self.log(f"    Postgres: {count} rows updated")
        
        # 2. Rename in Neo4j
        self.neo4j_rename_exercise(p.custom_id, p.new_id)
        self.log(f"    Neo4j: Renamed node")
        
        self.promoted += 1
    
    # -------------------------------------------------------------------------
    # Main
    # -------------------------------------------------------------------------
    
    def run(self):
        """Execute all migrations."""
        self.log("="*60)
        self.log("MERGES (6 exercises → existing canonicals)")
        self.log("="*60)
        
        for m in MERGE_MAPPINGS:
            try:
                self.do_merge(m)
            except Exception as e:
                self.errors.append(f"{m.custom_id}: {e}")
                self.log(f"    ❌ ERROR: {e}")
        
        self.log("\n" + "="*60)
        self.log("PROMOTES (5 exercises → new CANONICAL:ARNOLD)")
        self.log("="*60)
        
        for p in PROMOTE_MAPPINGS:
            try:
                self.do_promote(p)
            except Exception as e:
                self.errors.append(f"{p.custom_id}: {e}")
                self.log(f"    ❌ ERROR: {e}")
        
        return self.summary()
    
    def summary(self) -> str:
        lines = [
            "",
            "="*60,
            "SUMMARY",
            "="*60,
            f"  Merged:              {self.merged}",
            f"  Promoted:            {self.promoted}",
            f"  Postgres updated:    {self.pg_updated}",
            f"  Aliases added:       {self.aliases_added}",
            f"  Muscles transferred: {self.muscles_transferred}",
            f"  Nodes deleted:       {self.nodes_deleted}",
        ]
        if self.errors:
            lines.append(f"  ERRORS:              {len(self.errors)}")
            for e in self.errors:
                lines.append(f"    - {e}")
        lines.append("="*60)
        return "\n".join(lines)


def run_validation(neo4j_driver, pg_conn):
    """Check current state."""
    print("\n" + "="*60)
    print("VALIDATION")
    print("="*60)
    
    # Count CUSTOM in Neo4j
    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CUSTOM:'
            RETURN e.id as id, e.name as name
            ORDER BY e.name
        """)
        customs = [dict(r) for r in result]
    
    print(f"\nNeo4j CUSTOM exercises: {len(customs)}")
    for c in customs:
        print(f"  - {c['name']} ({c['id']})")
    
    # Count CUSTOM refs in Postgres
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT exercise_id, COUNT(*) as sets
        FROM strength_sets
        WHERE exercise_id LIKE 'CUSTOM:%'
        GROUP BY exercise_id
        ORDER BY sets DESC
    """)
    pg_customs = cur.fetchall()
    
    total_sets = sum(r[1] for r in pg_customs)
    print(f"\nPostgres CUSTOM refs: {len(pg_customs)} IDs, {total_sets} total sets")
    for r in pg_customs:
        print(f"  - {r[0]}: {r[1]} sets")
    
    # Check merge targets exist
    print("\n--- Checking merge targets ---")
    for m in MERGE_MAPPINGS:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.name as name",
                id=m.target_id
            )
            record = result.single()
            if record:
                print(f"  ✓ {m.target_id} exists ({record['name']})")
            else:
                print(f"  ❌ {m.target_id} NOT FOUND!")
    
    # Check promote targets don't exist yet
    print("\n--- Checking promote targets (should NOT exist) ---")
    for p in PROMOTE_MAPPINGS:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.name as name",
                id=p.new_id
            )
            record = result.single()
            if record:
                print(f"  ⚠️  {p.new_id} already exists ({record['name']})")
            else:
                print(f"  ✓ {p.new_id} available")
    
    cur.close()
    print("\n" + "="*60)


def run_post_validation(neo4j_driver, pg_conn):
    """Verify results after migration."""
    print("\n" + "="*60)
    print("POST-MIGRATION VALIDATION")
    print("="*60)
    
    # Check CUSTOM count
    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CUSTOM:'
            RETURN e.id as id, e.name as name
        """)
        customs = [dict(r) for r in result]
    
    print(f"\nNeo4j CUSTOM remaining: {len(customs)}")
    for c in customs:
        print(f"  - {c['name']} ({c['id']})")
    
    if len(customs) == 1 and customs[0]['id'] == 'CUSTOM:Tabata_Drill':
        print("  ✓ Only Tabata_Drill (protocol) remains - correct!")
    elif len(customs) == 0:
        print("  ⚠️  No CUSTOM remaining (Tabata_Drill was removed?)")
    else:
        print(f"  ⚠️  Expected only Tabata_Drill to remain")
    
    # Check Postgres CUSTOM refs
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT exercise_id, COUNT(*) as sets
        FROM strength_sets
        WHERE exercise_id LIKE 'CUSTOM:%'
        GROUP BY exercise_id
    """)
    pg_customs = cur.fetchall()
    
    total_sets = sum(r[1] for r in pg_customs)
    print(f"\nPostgres CUSTOM refs: {len(pg_customs)} IDs, {total_sets} sets")
    for r in pg_customs:
        print(f"  - {r[0]}: {r[1]} sets")
    
    # Check aliases were added
    print("\n--- Checking aliases on merge targets ---")
    for m in MERGE_MAPPINGS:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.aliases as aliases",
                id=m.target_id
            )
            record = result.single()
            if record and record['aliases'] and m.custom_name in record['aliases']:
                print(f"  ✓ {m.target_id} has alias '{m.custom_name}'")
            else:
                print(f"  ❌ {m.target_id} missing alias '{m.custom_name}'")
    
    # Check promoted exercises exist
    print("\n--- Checking promoted exercises ---")
    for p in PROMOTE_MAPPINGS:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.name as name, e.promoted_from as promoted_from",
                id=p.new_id
            )
            record = result.single()
            if record:
                print(f"  ✓ {p.new_id} exists (from {record['promoted_from']})")
            else:
                print(f"  ❌ {p.new_id} NOT FOUND!")
    
    # Check for orphaned Postgres refs
    print("\n--- Checking for orphaned Postgres refs ---")
    cur.execute("""
        SELECT DISTINCT exercise_id 
        FROM strength_sets 
        WHERE exercise_id LIKE 'CUSTOM:%' 
           OR exercise_id LIKE 'CANONICAL:ARNOLD:%'
    """)
    pg_ids = [r[0] for r in cur.fetchall()]
    
    orphaned = []
    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        for pg_id in pg_ids:
            result = session.run(
                "MATCH (e:Exercise {id: $id}) RETURN e.id",
                id=pg_id
            )
            if not result.single():
                orphaned.append(pg_id)
    
    if orphaned:
        print(f"  ❌ Found {len(orphaned)} orphaned refs:")
        for o in orphaned:
            print(f"    - {o}")
    else:
        print(f"  ✓ No orphaned refs (checked {len(pg_ids)} IDs)")
    
    cur.close()
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(description='Cleanup remaining CUSTOM exercises')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--validate', action='store_true', help='Only check current state')
    args = parser.parse_args()
    
    print("="*60)
    print("CUSTOM EXERCISE CLEANUP")
    print(f"Started: {datetime.now().isoformat()}")
    if args.dry_run:
        print("MODE: DRY RUN")
    if args.validate:
        print("MODE: VALIDATE ONLY")
    print("="*60)
    
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    pg_conn = psycopg2.connect(PG_URI)
    
    try:
        if args.validate:
            run_validation(neo4j_driver, pg_conn)
            return
        
        # Pre-validation
        run_validation(neo4j_driver, pg_conn)
        
        # Run migration
        migrator = CleanupMigrator(dry_run=args.dry_run)
        migrator.neo4j_driver = neo4j_driver
        migrator.pg_conn = pg_conn
        
        summary = migrator.run()
        print(summary)
        
        # Post-validation
        if not args.dry_run:
            run_post_validation(neo4j_driver, pg_conn)
            print("\n✅ Cleanup complete")
            print("\nNext: python scripts/sync_exercise_relationships.py")
        else:
            print("\n⚠️  DRY RUN - no changes made")
            print("Run without --dry-run to execute")
    
    finally:
        neo4j_driver.close()
        pg_conn.close()


if __name__ == '__main__':
    main()
