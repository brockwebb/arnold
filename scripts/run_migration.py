#!/usr/bin/env python3
"""Run a SQL migration file against arnold_analytics."""
import sys
from pathlib import Path
import psycopg2

DB_CONFIG = {
    "dbname": "arnold_analytics",
    "user": "postgres", 
    "host": "localhost",
    "port": 5432,
}

def run_migration(sql_file: Path):
    sql = sql_file.read_text()
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute(sql)
        conn.commit()
        print(f"Migration {sql_file.name} completed successfully")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_migration.py migration_file.sql")
        sys.exit(1)
    run_migration(Path(sys.argv[1]))
