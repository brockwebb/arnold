#!/usr/bin/env python3
"""
Migrate CUSTOM exercises based on normalization review decisions.

Reads: data/enrichment/exercise_normalization_review.csv
Writes: Neo4j Exercise nodes, Postgres strength_sets

Actions supported:
- MERGE_TO_CANONICAL: Update refs to canonical, transfer muscle data if better, add alias, delete CUSTOM
- PROMOTE_TO_CANONICAL: Change ID from CUSTOM:X to CANONICAL:ARNOLD:X
- KEEP_SEPARATE: Promote to CANONICAL:ARNOLD:X (they're legitimate new exercises)
- MERGE_TO_KICKBOXING: Merge into Kickboxing (after it's promoted)
- PROTOCOL_NOT_EXERCISE: Log only, skip migration (needs separate protocol modeling)

Usage:
    python scripts/migrate_custom_exercises.py --dry-run           # Preview ALL changes
    python scripts/migrate_custom_exercises.py --limit 5 --dry-run # Preview first 5
    python scripts/migrate_custom_exercises.py --limit 5           # Execute first 5 (TEST BATCH)
    python scripts/migrate_custom_exercises.py                     # Execute ALL (after testing)
    python scripts/migrate_custom_exercises.py --validate          # Just run validation queries

Post-migration:
    python scripts/sync_exercise_relationships.py            # Update Postgres cache
"""

import os
import sys
import csv
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from neo4j import GraphDatabase
import psycopg2

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
REVIEW_CSV = PROJECT_ROOT / "data" / "enrichment" / "exercise_normalization_review.csv"

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "i'llbeback")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

# Postgres connection
PG_URI = os.getenv("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


@dataclass
class MigrationRow:
    """Parsed row from the review CSV."""
    custom_id: str
    custom_name: str
    set_count: int
    custom_muscles: int
    custom_source: str
    canonical_id: str
    canonical_name: str
    canonical_muscles: int
    canonical_source: str
    action: str
    notes: str


def load_review_csv(filepath: Path) -> list[MigrationRow]:
    """Load and parse the review CSV file."""
    rows = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(MigrationRow(
                custom_id=row['custom_id'],
                custom_name=row['custom_name'],
                set_count=int(row['set_count']) if row['set_count'] else 0,
                custom_muscles=int(row['custom_muscles']) if row['custom_muscles'] else 0,
                custom_source=row['custom_source'],
                canonical_id=row['canonical_id'],
                canonical_name=row['canonical_name'],
                canonical_muscles=int(row['canonical_muscles']) if row['canonical_muscles'] else 0,
                canonical_source=row['canonical_source'],
                action=row['action'],
                notes=row['notes']
            ))
    return rows


class MigrationStats:
    """Track migration statistics."""
    def __init__(self):
        self.merged = 0
        self.promoted = 0
        self.kept_separate = 0
        self.kickboxing_merged = 0
        self.protocols_skipped = 0
        self.postgres_updates = 0
        self.aliases_added = 0
        self.muscles_transferred = 0
        self.nodes_deleted = 0
        self.nodes_renamed = 0
        self.errors = []
        self.processed_ids = []  # Track what we processed for validation
    
    def summary(self) -> str:
        lines = [
            "="*60,
            "MIGRATION SUMMARY",
            "="*60,
            f"  Merged to canonical:    {self.merged}",
            f"  Promoted to canonical:  {self.promoted}",
            f"  Kept separate:          {self.kept_separate}",
            f"  Kickboxing merged:      {self.kickboxing_merged}",
            f"  Protocols skipped:      {self.protocols_skipped}",
            "-"*40,
            f"  Postgres rows updated:  {self.postgres_updates}",
            f"  Neo4j nodes renamed:    {self.nodes_renamed}",
            f"  Neo4j nodes deleted:    {self.nodes_deleted}",
            f"  Aliases added:          {self.aliases_added}",
            f"  Muscle data transferred:{self.muscles_transferred}",
        ]
        if self.errors:
            lines.append("-"*40)
            lines.append(f"  ERRORS:                 {len(self.errors)}")
            for err in self.errors[:5]:
                lines.append(f"    - {err}")
            if len(self.errors) > 5:
                lines.append(f"    ... and {len(self.errors) - 5} more")
        lines.append("="*60)
        return "\n".join(lines)


class ExerciseMigrator:
    """Handle exercise migration operations."""
    
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.stats = MigrationStats()
        
        # Connect to databases
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.pg_conn = psycopg2.connect(PG_URI)
    
    def close(self):
        """Close database connections."""
        self.neo4j_driver.close()
        self.pg_conn.close()
    
    def log(self, message: str, verbose_only: bool = False):
        """Print log message."""
        if verbose_only and not self.verbose:
            return
        prefix = "[DRY-RUN] " if self.dry_run else ""
        print(f"{prefix}{message}")
    
    # -------------------------------------------------------------------------
    # Neo4j Operations
    # -------------------------------------------------------------------------
    
    def neo4j_get_exercise(self, exercise_id: str) -> Optional[dict]:
        """Get exercise node data."""
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (e:Exercise {id: $id})
                RETURN e.id as id, e.name as name, e.aliases as aliases, e.source as source
            """, id=exercise_id)
            record = result.single()
            return dict(record) if record else None
    
    def neo4j_get_muscle_count(self, exercise_id: str) -> int:
        """Get count of TARGETS relationships for an exercise."""
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (e:Exercise {id: $id})-[r:TARGETS]->(m)
                RETURN count(r) as count
            """, id=exercise_id)
            return result.single()['count']
    
    def neo4j_add_alias(self, exercise_id: str, alias: str):
        """Add an alias to an exercise's aliases array."""
        if self.dry_run:
            self.log(f"    Would add alias '{alias}' to {exercise_id}", verbose_only=True)
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
        self.stats.aliases_added += 1
    
    def neo4j_transfer_muscles(self, from_id: str, to_id: str):
        """Transfer TARGETS relationships from one exercise to another."""
        if self.dry_run:
            self.log(f"    Would transfer muscle data from {from_id} to {to_id}", verbose_only=True)
            return
        
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            # First delete existing relationships on target (they're inferior)
            session.run("""
                MATCH (e:Exercise {id: $to_id})-[r:TARGETS]->()
                DELETE r
            """, to_id=to_id)
            
            # Copy relationships from source to target
            session.run("""
                MATCH (src:Exercise {id: $from_id})-[r:TARGETS]->(m)
                MATCH (dst:Exercise {id: $to_id})
                MERGE (dst)-[r2:TARGETS]->(m)
                SET r2.role = r.role,
                    r2.source = r.source,
                    r2.confidence = r.confidence,
                    r2.human_verified = coalesce(r.human_verified, false),
                    r2.transferred_from = $from_id,
                    r2.transferred_at = datetime()
            """, from_id=from_id, to_id=to_id)
        self.stats.muscles_transferred += 1
    
    def neo4j_delete_exercise(self, exercise_id: str):
        """Delete an exercise node and all its relationships."""
        if self.dry_run:
            self.log(f"    Would delete node {exercise_id}", verbose_only=True)
            return
        
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            session.run("""
                MATCH (e:Exercise {id: $id})
                DETACH DELETE e
            """, id=exercise_id)
        self.stats.nodes_deleted += 1
    
    def neo4j_rename_exercise_id(self, old_id: str, new_id: str):
        """Change an exercise's ID."""
        if self.dry_run:
            self.log(f"    Would rename {old_id} → {new_id}", verbose_only=True)
            return
        
        with self.neo4j_driver.session(database=NEO4J_DATABASE) as session:
            session.run("""
                MATCH (e:Exercise {id: $old_id})
                SET e.id = $new_id,
                    e.source = 'arnold_promoted',
                    e.promoted_at = datetime(),
                    e.promoted_from = $old_id
            """, old_id=old_id, new_id=new_id)
        self.stats.nodes_renamed += 1
    
    # -------------------------------------------------------------------------
    # Postgres Operations
    # -------------------------------------------------------------------------
    
    def pg_update_exercise_refs(self, old_id: str, new_id: str) -> int:
        """Update exercise_id references in strength_sets."""
        if self.dry_run:
            # Still count how many would be affected
            cur = self.pg_conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM strength_sets WHERE exercise_id = %s
            """, (old_id,))
            count = cur.fetchone()[0]
            cur.close()
            self.log(f"    Would update {count} rows in strength_sets", verbose_only=True)
            return count
        
        cur = self.pg_conn.cursor()
        cur.execute("""
            UPDATE strength_sets 
            SET exercise_id = %s 
            WHERE exercise_id = %s
        """, (new_id, old_id))
        count = cur.rowcount
        self.pg_conn.commit()
        cur.close()
        self.stats.postgres_updates += count
        return count
    
    def pg_get_set_count(self, exercise_id: str) -> int:
        """Get count of sets referencing an exercise."""
        cur = self.pg_conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM strength_sets WHERE exercise_id = %s
        """, (exercise_id,))
        count = cur.fetchone()[0]
        cur.close()
        return count
    
    # -------------------------------------------------------------------------
    # Migration Actions
    # -------------------------------------------------------------------------
    
    def migrate_merge_to_canonical(self, row: MigrationRow):
        """
        MERGE_TO_CANONICAL action:
        1. Update Postgres refs from CUSTOM to canonical
        2. Add CUSTOM name as alias on canonical
        3. Transfer muscle data if CUSTOM has more
        4. Delete CUSTOM node
        """
        self.log(f"\n  MERGE: {row.custom_name} → {row.canonical_name} ({row.canonical_id})")
        
        # Check canonical exists
        canonical = self.neo4j_get_exercise(row.canonical_id)
        if not canonical:
            self.stats.errors.append(f"Canonical not found: {row.canonical_id}")
            self.log(f"    ERROR: Canonical not found!")
            return
        
        # 1. Update Postgres references
        count = self.pg_update_exercise_refs(row.custom_id, row.canonical_id)
        self.log(f"    Postgres: {count} rows updated")
        
        # 2. Add alias
        self.neo4j_add_alias(row.canonical_id, row.custom_name)
        self.log(f"    Neo4j: Added alias '{row.custom_name}'", verbose_only=True)
        
        # 3. Transfer muscles if CUSTOM has better data
        if row.custom_muscles > row.canonical_muscles and row.custom_source == 'google_ai_overview':
            self.log(f"    Neo4j: Transferring muscle data ({row.custom_muscles} > {row.canonical_muscles})")
            self.neo4j_transfer_muscles(row.custom_id, row.canonical_id)
        
        # 4. Delete CUSTOM node
        self.neo4j_delete_exercise(row.custom_id)
        self.log(f"    Neo4j: Deleted {row.custom_id}", verbose_only=True)
        
        self.stats.merged += 1
        self.stats.processed_ids.append((row.custom_id, row.canonical_id, 'MERGE'))
    
    def migrate_promote_to_canonical(self, row: MigrationRow) -> str:
        """
        PROMOTE_TO_CANONICAL action:
        1. Generate new canonical ID
        2. Update Postgres refs
        3. Rename exercise node in Neo4j
        
        Returns the new ID (needed for MERGE_TO_KICKBOXING ordering)
        """
        # Generate canonical ID from custom name
        name_part = row.custom_name.upper().replace(' ', '_').replace('-', '_')
        new_id = f"CANONICAL:ARNOLD:{name_part}"
        
        self.log(f"\n  PROMOTE: {row.custom_id} → {new_id}")
        
        # 1. Update Postgres references
        count = self.pg_update_exercise_refs(row.custom_id, new_id)
        self.log(f"    Postgres: {count} rows updated")
        
        # 2. Rename in Neo4j
        self.neo4j_rename_exercise_id(row.custom_id, new_id)
        self.log(f"    Neo4j: Renamed node", verbose_only=True)
        
        self.stats.promoted += 1
        self.stats.processed_ids.append((row.custom_id, new_id, 'PROMOTE'))
        
        return new_id
    
    def migrate_keep_separate(self, row: MigrationRow):
        """
        KEEP_SEPARATE action: Same as PROMOTE, these are legitimate new exercises.
        """
        self.log(f"\n  KEEP SEPARATE: {row.custom_name}")
        self.migrate_promote_to_canonical(row)
        self.stats.kept_separate += 1
        self.stats.promoted -= 1  # Don't double count
    
    def migrate_merge_to_kickboxing(self, row: MigrationRow, kickboxing_id: str):
        """
        MERGE_TO_KICKBOXING action: Merge into Kickboxing exercise.
        
        Args:
            row: The migration row
            kickboxing_id: The ID of Kickboxing (could be CUSTOM: or CANONICAL:ARNOLD:)
        """
        self.log(f"\n  MERGE TO KICKBOXING: {row.custom_name} → {kickboxing_id}")
        
        # Update refs to canonical Kickboxing
        count = self.pg_update_exercise_refs(row.custom_id, kickboxing_id)
        self.log(f"    Postgres: {count} rows updated")
        
        # Add alias to Kickboxing
        self.neo4j_add_alias(kickboxing_id, row.custom_name)
        self.log(f"    Neo4j: Added alias", verbose_only=True)
        
        # Delete the node
        self.neo4j_delete_exercise(row.custom_id)
        self.log(f"    Neo4j: Deleted {row.custom_id}", verbose_only=True)
        
        self.stats.kickboxing_merged += 1
        self.stats.processed_ids.append((row.custom_id, kickboxing_id, 'MERGE_KICKBOXING'))
    
    def migrate_protocol_not_exercise(self, row: MigrationRow):
        """
        PROTOCOL_NOT_EXERCISE action: Log and skip.
        These need separate protocol modeling.
        """
        self.log(f"\n  PROTOCOL (skipped): {row.custom_name}")
        
        # Check how many sets reference this
        count = self.pg_get_set_count(row.custom_id)
        if count > 0:
            self.log(f"    WARNING: {count} sets reference this protocol")
        
        self.stats.protocols_skipped += 1
    
    # -------------------------------------------------------------------------
    # Main Migration
    # -------------------------------------------------------------------------
    
    def run(self, rows: list[MigrationRow]):
        """Execute migration for all rows."""
        self.log(f"Processing {len(rows)} exercises...")
        
        # Group by action for summary
        action_counts = {}
        for row in rows:
            action_counts[row.action] = action_counts.get(row.action, 0) + 1
        
        self.log("\nActions to perform:")
        for action, count in sorted(action_counts.items()):
            self.log(f"  {action}: {count}")
        
        # Track Kickboxing ID (it might get promoted before MERGE_TO_KICKBOXING runs)
        kickboxing_id = 'CUSTOM:Kickboxing'  # Default
        
        # Process each row
        for row in rows:
            try:
                if row.action == 'MERGE_TO_CANONICAL':
                    self.migrate_merge_to_canonical(row)
                    
                elif row.action == 'PROMOTE_TO_CANONICAL':
                    new_id = self.migrate_promote_to_canonical(row)
                    # Track if this is Kickboxing being promoted
                    if row.custom_id == 'CUSTOM:Kickboxing':
                        kickboxing_id = new_id
                        self.log(f"    (Kickboxing now at {kickboxing_id})")
                        
                elif row.action == 'KEEP_SEPARATE':
                    self.migrate_keep_separate(row)
                    
                elif row.action == 'MERGE_TO_KICKBOXING':
                    self.migrate_merge_to_kickboxing(row, kickboxing_id)
                    
                elif row.action == 'PROTOCOL_NOT_EXERCISE':
                    self.migrate_protocol_not_exercise(row)
                    
                else:
                    self.stats.errors.append(f"Unknown action: {row.action} for {row.custom_id}")
                    
            except Exception as e:
                self.stats.errors.append(f"{row.custom_id}: {str(e)}")
                self.log(f"  ERROR: {e}")
        
        return self.stats


def run_validation(neo4j_driver, pg_conn, specific_ids: list = None):
    """Run validation queries to check data consistency."""
    print("\n" + "="*60)
    print("VALIDATION QUERIES")
    print("="*60)
    
    # 1. Count CUSTOM exercises in Neo4j
    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CUSTOM:'
            RETURN count(e) as count
        """)
        neo4j_custom = result.single()['count']
        print(f"\nNeo4j CUSTOM exercises: {neo4j_custom}")
        
        # List them
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CUSTOM:'
            RETURN e.id as id, e.name as name
            ORDER BY e.name
            LIMIT 20
        """)
        for r in result:
            print(f"  - {r['name']} ({r['id']})")
    
    # 2. Count CUSTOM refs in Postgres
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT exercise_id) as unique_ids, COUNT(*) as total_sets
        FROM strength_sets 
        WHERE exercise_id LIKE 'CUSTOM:%'
    """)
    row = cur.fetchone()
    print(f"\nPostgres CUSTOM refs: {row[0]} unique IDs, {row[1]} total sets")
    
    # List top ones
    cur.execute("""
        SELECT exercise_id, exercise_name, COUNT(*) as sets
        FROM strength_sets
        WHERE exercise_id LIKE 'CUSTOM:%'
        GROUP BY exercise_id, exercise_name
        ORDER BY sets DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  - {row[1]}: {row[2]} sets ({row[0]})")
    
    # 3. Count CANONICAL:ARNOLD exercises
    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (e:Exercise) WHERE e.id STARTS WITH 'CANONICAL:ARNOLD:'
            RETURN count(e) as count
        """)
        arnold_count = result.single()['count']
        print(f"\nNeo4j CANONICAL:ARNOLD exercises: {arnold_count}")
    
    # 4. Check specific IDs if provided
    if specific_ids:
        print(f"\n--- Checking {len(specific_ids)} specific migrations ---")
        for old_id, new_id, action in specific_ids:
            print(f"\n  {action}: {old_id} → {new_id}")
            
            # Check Neo4j old ID gone
            with neo4j_driver.session(database=NEO4J_DATABASE) as session:
                result = session.run("""
                    MATCH (e:Exercise {id: $id}) RETURN e.name as name
                """, id=old_id)
                record = result.single()
                if record:
                    print(f"    ❌ Neo4j: OLD ID still exists!")
                else:
                    print(f"    ✓ Neo4j: Old ID removed")
            
            # Check Neo4j new ID exists
            with neo4j_driver.session(database=NEO4J_DATABASE) as session:
                result = session.run("""
                    MATCH (e:Exercise {id: $id}) 
                    RETURN e.name as name, e.aliases as aliases
                """, id=new_id)
                record = result.single()
                if record:
                    print(f"    ✓ Neo4j: New ID exists ({record['name']})")
                    if record['aliases']:
                        print(f"      Aliases: {record['aliases']}")
                else:
                    print(f"    ❌ Neo4j: NEW ID not found!")
            
            # Check Postgres refs point to new ID
            cur.execute("""
                SELECT COUNT(*) FROM strength_sets WHERE exercise_id = %s
            """, (old_id,))
            old_count = cur.fetchone()[0]
            
            cur.execute("""
                SELECT COUNT(*) FROM strength_sets WHERE exercise_id = %s
            """, (new_id,))
            new_count = cur.fetchone()[0]
            
            if old_count > 0:
                print(f"    ❌ Postgres: {old_count} rows still reference OLD ID!")
            else:
                print(f"    ✓ Postgres: No refs to old ID")
            print(f"    ✓ Postgres: {new_count} rows reference new ID")
    
    # 5. Check for orphaned refs (Postgres IDs with no Neo4j node)
    print("\n--- Checking for orphaned Postgres refs ---")
    cur.execute("""
        SELECT DISTINCT exercise_id 
        FROM strength_sets 
        WHERE exercise_id LIKE 'CUSTOM:%' OR exercise_id LIKE 'CANONICAL:ARNOLD:%'
    """)
    pg_ids = [row[0] for row in cur.fetchall()]
    
    orphaned = []
    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        for pg_id in pg_ids[:50]:  # Limit to first 50
            result = session.run("""
                MATCH (e:Exercise {id: $id}) RETURN e.id
            """, id=pg_id)
            if not result.single():
                orphaned.append(pg_id)
    
    if orphaned:
        print(f"  ❌ Found {len(orphaned)} orphaned refs:")
        for oid in orphaned[:10]:
            print(f"    - {oid}")
    else:
        print(f"  ✓ No orphaned refs found (checked {len(pg_ids)} IDs)")
    
    cur.close()
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(description='Migrate CUSTOM exercises based on review decisions')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--verbose', '-v', action='store_true', help='Detailed logging')
    parser.add_argument('--limit', type=int, help='Only process first N rows (for testing)')
    parser.add_argument('--validate', action='store_true', help='Only run validation queries')
    args = parser.parse_args()
    
    print("="*60)
    print("EXERCISE MIGRATION")
    print(f"Started: {datetime.now().isoformat()}")
    if args.dry_run:
        print("MODE: DRY RUN - No changes will be made")
    if args.limit:
        print(f"MODE: LIMITED - Only processing first {args.limit} rows")
    if args.validate:
        print("MODE: VALIDATE ONLY")
    print("="*60)
    
    # Initialize connections
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    pg_conn = psycopg2.connect(PG_URI)
    
    try:
        # Validate-only mode
        if args.validate:
            run_validation(neo4j_driver, pg_conn)
            return
        
        # Load review CSV
        print(f"\nLoading review CSV from {REVIEW_CSV}...")
        if not REVIEW_CSV.exists():
            print(f"ERROR: Review CSV not found: {REVIEW_CSV}")
            sys.exit(1)
        
        rows = load_review_csv(REVIEW_CSV)
        print(f"Loaded {len(rows)} rows")
        
        # Apply limit if specified
        if args.limit:
            rows = rows[:args.limit]
            print(f"Limited to first {args.limit} rows")
        
        # Initialize migrator
        migrator = ExerciseMigrator(dry_run=args.dry_run, verbose=args.verbose)
        migrator.neo4j_driver = neo4j_driver
        migrator.pg_conn = pg_conn
        
        # Run pre-migration validation
        print("\n--- PRE-MIGRATION STATE ---")
        run_validation(neo4j_driver, pg_conn)
        
        # Run migration
        print("\n" + "-"*60)
        print("EXECUTING MIGRATION")
        print("-"*60)
        stats = migrator.run(rows)
        
        # Print summary
        print("\n" + stats.summary())
        
        # Run post-migration validation
        if not args.dry_run:
            print("\n--- POST-MIGRATION STATE ---")
            run_validation(neo4j_driver, pg_conn, stats.processed_ids)
        
        if args.dry_run:
            print("\n⚠️  DRY RUN - No changes were made")
            print("Run without --dry-run to execute migration")
        else:
            print("\n✅ Migration complete")
            print("\nNext steps:")
            print("  1. Review validation output above")
            print("  2. If OK, run full migration without --limit")
            print("  3. Then: python scripts/sync_exercise_relationships.py")
        
    finally:
        neo4j_driver.close()
        pg_conn.close()


if __name__ == '__main__':
    main()
