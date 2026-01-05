#!/usr/bin/env python3
"""
Sync Annotations from Neo4j to Postgres

Neo4j is source of truth for annotations (rich relationships).
Postgres is analytics layer (time-series queries, materialized views).

This script exports annotations from Neo4j and upserts into Postgres.
"""

import os
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Neo4j connection
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

# Postgres connection
PG_CONN = "postgresql://brock@localhost:5432/arnold_analytics"


def fetch_annotations_from_neo4j() -> list:
    """Fetch all active annotations from Neo4j with relationship context."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    MATCH (p:Person)-[:HAS_ANNOTATION]->(a:Annotation)
    WHERE a.is_active = true
    OPTIONAL MATCH (a)-[r:EXPLAINS]->(target)
    RETURN 
        a.id as id,
        toString(a.annotation_date) as annotation_date,
        toString(a.date_range_end) as date_range_end,
        a.target_type as target_type,
        a.target_metric as target_metric,
        // Build target_id from relationship if exists
        CASE 
            WHEN target IS NOT NULL THEN labels(target)[0] + ':' + coalesce(target.id, target.name)
            ELSE null
        END as target_id,
        a.reason_code as reason_code,
        a.explanation as explanation,
        a.tags as tags,
        a.created_by as created_by,
        a.is_active as is_active
    ORDER BY a.annotation_date DESC
    """
    
    annotations = []
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            annotations.append(dict(record))
    
    driver.close()
    return annotations


def upsert_to_postgres(annotations: list):
    """Upsert annotations into Postgres data_annotations table."""
    if not annotations:
        print("No annotations to sync")
        return 0
    
    conn = psycopg2.connect(PG_CONN)
    cur = conn.cursor()
    
    # Clear existing and insert fresh (simpler than true upsert for this case)
    # We track by Neo4j ID to allow updates
    cur.execute("DELETE FROM data_annotations WHERE created_by != 'postgres_only'")
    
    insert_sql = """
        INSERT INTO data_annotations 
            (annotation_date, date_range_end, target_type, target_metric, target_id, 
             reason_code, explanation, tags, created_by, is_active)
        VALUES %s
    """
    
    values = []
    for a in annotations:
        values.append((
            a['annotation_date'],
            a['date_range_end'],
            a['target_type'],
            a['target_metric'],
            a['target_id'],
            a['reason_code'],
            a['explanation'],
            a['tags'] if a['tags'] else [],
            a.get('created_by', 'neo4j'),
            a.get('is_active', True)
        ))
    
    execute_values(cur, insert_sql, values)
    
    conn.commit()
    count = len(values)
    conn.close()
    
    return count


def main():
    print(f"[{datetime.now().isoformat()}] Syncing annotations Neo4j → Postgres")
    
    # Fetch from Neo4j
    annotations = fetch_annotations_from_neo4j()
    print(f"  Found {len(annotations)} active annotations in Neo4j")
    
    # Upsert to Postgres
    count = upsert_to_postgres(annotations)
    print(f"  Synced {count} annotations to Postgres")
    
    # Show summary
    for a in annotations:
        status = "ongoing" if not a['date_range_end'] else f"→ {a['date_range_end']}"
        print(f"    [{a['reason_code']}] {a['target_metric']}: {a['annotation_date']} {status}")


if __name__ == "__main__":
    main()
