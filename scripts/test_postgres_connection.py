#!/usr/bin/env python3
"""Quick test of Postgres connection from memory MCP perspective."""

import os
import sys

# Set the same env as the MCP
os.environ['DATABASE_URI'] = 'postgresql://brock@localhost:5432/arnold_analytics'

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

def test_connection():
    """Test direct connection."""
    dsn = os.environ.get(
        "POSTGRES_DSN",
        os.environ.get(
            "DATABASE_URI",
            "postgresql://brock@localhost:5432/arnold_analytics"
        )
    )
    
    print(f"DSN: {dsn}")
    
    try:
        conn = psycopg2.connect(dsn)
        print(f"Connection: OK, closed={conn.closed}")
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Test basic connection
        cur.execute("SELECT 1 as test")
        result = cur.fetchone()
        print(f"Test query: {result}")
        
        # Test workout_summaries view
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
        
        print(f"\nQuerying workout_summaries from {start_date} to {end_date}")
        
        cur.execute("""
            SELECT 
                COUNT(*) as workouts,
                COALESCE(SUM(set_count), 0) as total_sets,
                COALESCE(SUM(total_volume_lbs), 0) as total_volume
            FROM workout_summaries
            WHERE workout_date BETWEEN %s AND %s
        """, [start_date, end_date])
        summary = cur.fetchone()
        print(f"Result: {summary}")
        
        # Check row count in view
        cur.execute("SELECT COUNT(*) FROM workout_summaries")
        total = cur.fetchone()
        print(f"Total rows in view: {total}")
        
        # Check recent rows
        cur.execute("""
            SELECT workout_date, set_count 
            FROM workout_summaries 
            ORDER BY workout_date DESC 
            LIMIT 5
        """)
        recent = cur.fetchall()
        print(f"Recent workouts: {recent}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
