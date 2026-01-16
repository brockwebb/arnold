#!/usr/bin/env python3
"""
Diagnostic script to check HRR interval data quality.
Run: python scripts/hrr_diag.py --session-id 71
"""

import argparse
import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)

def diagnose_session(session_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check R² columns exist and have values
    cur.execute('''
        SELECT 
            interval_order, duration_seconds, 
            r2_0_60, r2_0_120, r2_0_180, r2_0_240, r2_0_300,
            hrr60_abs, hrr120_abs, hrr180_abs, hrr240_abs, hrr300_abs,
            quality_status, quality_flags, slope_90_120
        FROM hr_recovery_intervals 
        WHERE polar_session_id = %s 
        ORDER BY interval_order
    ''', (session_id,))
    rows = cur.fetchall()
    
    if not rows:
        print(f"No intervals found for session {session_id}")
        conn.close()
        return
    
    print(f"\n=== SESSION {session_id} DIAGNOSTIC ({len(rows)} intervals) ===\n")
    
    # Check 1: R² values
    print("--- R² VALUES ---")
    print(f"{'Ord':>3} | {'Dur':>4} | {'R²_60':>7} | {'R²_120':>7} | {'R²_180':>7} | {'R²_240':>7} | {'R²_300':>7}")
    print("-" * 60)
    for r in rows:
        def fmt(v): return f"{v:.3f}" if v is not None else "   -   "
        print(f"{r[0]:>3} | {r[1]:>4} | {fmt(r[2]):>7} | {fmt(r[3]):>7} | {fmt(r[4]):>7} | {fmt(r[5]):>7} | {fmt(r[6]):>7}")
    
    # Check null counts
    null_r2_60 = sum(1 for r in rows if r[2] is None)
    null_r2_120 = sum(1 for r in rows if r[3] is None)
    null_r2_180 = sum(1 for r in rows if r[4] is None)
    null_r2_240 = sum(1 for r in rows if r[5] is None)
    null_r2_300 = sum(1 for r in rows if r[6] is None)
    
    print(f"\nNULL counts: R²_60={null_r2_60}, R²_120={null_r2_120}, R²_180={null_r2_180}, R²_240={null_r2_240}, R²_300={null_r2_300}")
    
    # Check 2: HRR values
    print("\n--- HRR VALUES ---")
    print(f"{'Ord':>3} | {'Dur':>4} | {'HRR60':>6} | {'HRR120':>6} | {'HRR180':>6} | {'HRR240':>6} | {'HRR300':>6}")
    print("-" * 55)
    for r in rows:
        def fmt(v): return f"{v:>6}" if v is not None else "     -"
        print(f"{r[0]:>3} | {r[1]:>4} | {fmt(r[7]):>6} | {fmt(r[8]):>6} | {fmt(r[9]):>6} | {fmt(r[10]):>6} | {fmt(r[11]):>6}")
    
    # Check 3: Quality status
    print("\n--- QUALITY STATUS ---")
    print(f"{'Ord':>3} | {'Status':<10} | {'Slope 90-120':>12} | Flags")
    print("-" * 70)
    for r in rows:
        slope = f"{r[14]:.4f}" if r[14] is not None else "-"
        flags = '|'.join(r[13]) if r[13] else 'none'
        print(f"{r[0]:>3} | {r[12]:<10} | {slope:>12} | {flags}")
    
    # Summary
    flagged = sum(1 for r in rows if r[12] == 'flagged')
    passed = sum(1 for r in rows if r[12] == 'pass')
    with_late_rise = sum(1 for r in rows if r[13] and 'LATE_RISE' in r[13])
    
    print(f"\n--- SUMMARY ---")
    print(f"Total: {len(rows)}, Passed: {passed}, Flagged: {flagged}")
    print(f"With LATE_RISE flag: {with_late_rise}")
    
    # Check R² >= 0.75 counts per window
    valid_60 = sum(1 for r in rows if r[2] is not None and r[2] >= 0.75)
    valid_120 = sum(1 for r in rows if r[3] is not None and r[3] >= 0.75)
    valid_180 = sum(1 for r in rows if r[4] is not None and r[4] >= 0.75)
    valid_240 = sum(1 for r in rows if r[5] is not None and r[5] >= 0.75)
    valid_300 = sum(1 for r in rows if r[6] is not None and r[6] >= 0.75)
    
    print(f"\nValid (R² >= 0.75) per window:")
    print(f"  R²_60: {valid_60}/{len(rows)}")
    print(f"  R²_120: {valid_120}/{len(rows)}")
    print(f"  R²_180: {valid_180}/{len(rows)}")
    print(f"  R²_240: {valid_240}/{len(rows)}")
    print(f"  R²_300: {valid_300}/{len(rows)}")
    
    conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-id', type=int, default=71)
    args = parser.parse_args()
    diagnose_session(args.session_id)
