#!/usr/bin/env python3
"""
HRR QC Review Workflow

Systematic review of HRR intervals for algorithm validation.

Usage:
    # See review queue (sessions needing review)
    python scripts/hrr_qc_review.py --queue
    
    # Export all intervals to CSV for manual judgment
    python scripts/hrr_qc_review.py --export-all
    
    # Export single session for review
    python scripts/hrr_qc_review.py --export --session-id 71
    
    # Review a session (viz + export + mark in progress)
    python scripts/hrr_qc_review.py --review --session-id 71
    
    # Review next unreviewed session
    python scripts/hrr_qc_review.py --review --next
    
    # Import judgments from CSV
    python scripts/hrr_qc_review.py --import-judgments data/qc/hrr_judgments.csv
    
    # Calculate precision/recall stats
    python scripts/hrr_qc_review.py --stats
    
    # Mark session as reviewed
    python scripts/hrr_qc_review.py --mark-reviewed --session-id 71
"""

import argparse
import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# QC output directory
QC_DIR = PROJECT_ROOT / 'data' / 'qc'
JUDGMENTS_FILE = QC_DIR / 'hrr_judgments.csv'
REVIEW_STATE_FILE = QC_DIR / 'review_state.json'


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def ensure_qc_dir():
    """Create QC directory if it doesn't exist."""
    QC_DIR.mkdir(parents=True, exist_ok=True)


def load_review_state() -> dict:
    """Load review state from JSON file."""
    if REVIEW_STATE_FILE.exists():
        with open(REVIEW_STATE_FILE) as f:
            return json.load(f)
    return {'reviewed_sessions': [], 'in_progress': []}


def save_review_state(state: dict):
    """Save review state to JSON file."""
    ensure_qc_dir()
    with open(REVIEW_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def get_all_sessions(conn) -> List[dict]:
    """Get all sessions with HRR intervals."""
    query = """
        SELECT 
            hri.polar_session_id as session_id,
            ps.start_time,
            ps.sport_type,
            COUNT(*) as total_intervals,
            SUM(CASE WHEN hri.quality_status = 'pass' THEN 1 ELSE 0 END) as pass_ct,
            SUM(CASE WHEN hri.quality_status = 'flagged' THEN 1 ELSE 0 END) as flagged_ct,
            SUM(CASE WHEN hri.quality_status = 'rejected' THEN 1 ELSE 0 END) as rejected_ct
        FROM hr_recovery_intervals hri
        JOIN polar_sessions ps ON ps.id = hri.polar_session_id
        GROUP BY hri.polar_session_id, ps.start_time, ps.sport_type
        ORDER BY ps.start_time
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    
    return [
        {
            'session_id': r[0],
            'start_time': r[1],
            'sport_type': r[2],
            'total_intervals': r[3],
            'pass_ct': r[4],
            'flagged_ct': r[5],
            'rejected_ct': r[6],
        }
        for r in rows
    ]


def get_intervals_for_export(conn, session_id: Optional[int] = None) -> List[dict]:
    """Get intervals formatted for QC export."""
    query = """
        SELECT 
            hri.polar_session_id as session_id,
            ps.start_time as session_date,
            ps.sport_type,
            hri.interval_order,
            hri.id as interval_id,
            hri.start_time as interval_start,
            hri.hr_peak,
            hri.duration_seconds,
            hri.hrr60_abs,
            hri.hrr120_abs,
            hri.hrr300_abs,
            hri.quality_status,
            hri.quality_flags,
            hri.auto_reject_reason,
            hri.r2_0_60,
            hri.r2_0_120,
            hri.tau_seconds
        FROM hr_recovery_intervals hri
        JOIN polar_sessions ps ON ps.id = hri.polar_session_id
        WHERE (%s IS NULL OR hri.polar_session_id = %s)
        ORDER BY ps.start_time, hri.interval_order
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id, session_id))
        rows = cur.fetchall()
    
    intervals = []
    for r in rows:
        intervals.append({
            'session_id': r[0],
            'session_date': r[1].strftime('%Y-%m-%d') if r[1] else '',
            'sport_type': r[2],
            'interval_order': r[3],
            'interval_id': r[4],
            'interval_start': r[5].strftime('%H:%M:%S') if r[5] else '',
            'peak_label': f"S{r[0]}:p{r[3]:02d}" if r[3] else f"S{r[0]}:p??",
            'hr_peak': r[6],
            'duration_sec': r[7],
            'hrr60': r[8],
            'hrr120': r[9],
            'hrr300': r[10],
            'algo_status': r[11],
            'quality_flags': r[12] if r[12] else '',
            'reject_reason': r[13] if r[13] else '',
            'r2_60': f"{r[14]:.3f}" if r[14] else '',
            'r2_120': f"{r[15]:.3f}" if r[15] else '',
            'tau': f"{r[16]:.1f}" if r[16] else '',
        })
    
    return intervals


def show_queue(conn):
    """Show sessions needing review."""
    sessions = get_all_sessions(conn)
    state = load_review_state()
    reviewed = set(state.get('reviewed_sessions', []))
    in_progress = set(state.get('in_progress', []))
    
    print(f"\n{'='*100}")
    print("HRR QC REVIEW QUEUE")
    print(f"{'='*100}")
    print(f"\n{'ID':>4} | {'Date':^12} | {'Sport':<20} | {'Tot':>4} | {'Pass':>4} | {'Flag':>4} | {'Rej':>4} | {'Status':<12}")
    print(f"{'-'*100}")
    
    pending = 0
    for s in sessions:
        sid = s['session_id']
        if sid in reviewed:
            status = '✓ reviewed'
        elif sid in in_progress:
            status = '→ in progress'
        else:
            status = 'pending'
            pending += 1
        
        print(f"{sid:>4} | {s['start_time'].strftime('%Y-%m-%d'):^12} | {s['sport_type'][:20]:<20} | {s['total_intervals']:>4} | {s['pass_ct']:>4} | {s['flagged_ct']:>4} | {s['rejected_ct']:>4} | {status:<12}")
    
    print(f"\n{len(sessions)} sessions total | {len(reviewed)} reviewed | {len(in_progress)} in progress | {pending} pending")
    print()


def export_intervals(conn, session_id: Optional[int] = None, output_path: Optional[str] = None):
    """Export intervals to CSV for manual review."""
    intervals = get_intervals_for_export(conn, session_id)
    
    if not intervals:
        print("No intervals found.")
        return
    
    ensure_qc_dir()
    
    if output_path:
        out_file = Path(output_path)
    elif session_id:
        out_file = QC_DIR / f'hrr_qc_session_{session_id}.csv'
    else:
        out_file = QC_DIR / 'hrr_qc_all_intervals.csv'
    
    # CSV columns
    fieldnames = [
        'session_id', 'session_date', 'sport_type', 'interval_order', 'interval_id',
        'peak_label', 'interval_start', 'hr_peak', 'duration_sec',
        'hrr60', 'hrr120', 'hrr300', 'r2_60', 'r2_120', 'tau',
        'algo_status', 'reject_reason', 'quality_flags',
        # Human judgment columns (to be filled in)
        'human_judgment', 'peak_correct', 'notes'
    ]
    
    with open(out_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for i in intervals:
            # Add empty judgment columns
            i['human_judgment'] = ''
            i['peak_correct'] = ''
            i['notes'] = ''
            writer.writerow(i)
    
    print(f"Exported {len(intervals)} intervals to: {out_file}")
    print(f"\nJudgment column values:")
    print(f"  human_judgment: TP, FP, TN, FN_REJECTED, FN_MISSED, SKIP")
    print(f"  peak_correct:   yes, no, shifted (if peak location is wrong)")
    print(f"  notes:          free text explanation")
    print()


def import_judgments(csv_path: str):
    """Import judgments from CSV and store."""
    judgments_path = Path(csv_path)
    if not judgments_path.exists():
        print(f"File not found: {csv_path}")
        return
    
    ensure_qc_dir()
    
    # Read judgments
    judgments = []
    with open(judgments_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('human_judgment'):  # Only rows with judgments
                judgments.append({
                    'session_id': int(row['session_id']),
                    'interval_id': int(row['interval_id']),
                    'interval_order': int(row['interval_order']) if row.get('interval_order') else None,
                    'peak_label': row.get('peak_label', ''),
                    'algo_status': row.get('algo_status', ''),
                    'human_judgment': row['human_judgment'].strip().upper(),
                    'peak_correct': row.get('peak_correct', '').strip().lower(),
                    'notes': row.get('notes', ''),
                    'judged_at': datetime.now().isoformat(),
                })
    
    if not judgments:
        print("No judgments found in file.")
        return
    
    # Append to master judgments file
    existing = []
    if JUDGMENTS_FILE.exists():
        with open(JUDGMENTS_FILE, newline='') as f:
            existing = list(csv.DictReader(f))
    
    # Merge: update existing, add new
    existing_keys = {(j['session_id'], j['interval_id']) for j in existing}
    
    fieldnames = ['session_id', 'interval_id', 'interval_order', 'peak_label', 
                  'algo_status', 'human_judgment', 'peak_correct', 'notes', 'judged_at']
    
    # Convert existing to same format
    existing_dict = {(int(j['session_id']), int(j['interval_id'])): j for j in existing}
    
    # Update/add
    for j in judgments:
        key = (j['session_id'], j['interval_id'])
        existing_dict[key] = j
    
    # Write back
    with open(JUDGMENTS_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for j in sorted(existing_dict.values(), key=lambda x: (x['session_id'], x.get('interval_order', 0))):
            writer.writerow({k: j.get(k, '') for k in fieldnames})
    
    print(f"Imported {len(judgments)} judgments to: {JUDGMENTS_FILE}")
    
    # Update review state
    sessions_judged = set(j['session_id'] for j in judgments)
    state = load_review_state()
    for sid in sessions_judged:
        if sid not in state['reviewed_sessions']:
            if sid not in state['in_progress']:
                state['in_progress'].append(sid)
    save_review_state(state)
    print(f"Updated review state for sessions: {sorted(sessions_judged)}")


def calculate_stats():
    """Calculate precision/recall from judgments."""
    if not JUDGMENTS_FILE.exists():
        print(f"No judgments file found: {JUDGMENTS_FILE}")
        print("Run --import-judgments first.")
        return
    
    with open(JUDGMENTS_FILE, newline='') as f:
        judgments = list(csv.DictReader(f))
    
    if not judgments:
        print("No judgments found.")
        return
    
    # Count by judgment type
    counts = {'TP': 0, 'FP': 0, 'TN': 0, 'FN_REJECTED': 0, 'FN_MISSED': 0, 'SKIP': 0, 'UNKNOWN': 0}
    by_session = {}
    
    for j in judgments:
        judgment = j.get('human_judgment', '').strip().upper()
        if judgment in counts:
            counts[judgment] += 1
        else:
            counts['UNKNOWN'] += 1
        
        sid = j['session_id']
        if sid not in by_session:
            by_session[sid] = {'TP': 0, 'FP': 0, 'TN': 0, 'FN_REJECTED': 0, 'FN_MISSED': 0}
        if judgment in by_session[sid]:
            by_session[sid][judgment] += 1
    
    # Calculate metrics
    tp = counts['TP']
    fp = counts['FP']
    tn = counts['TN']
    fn = counts['FN_REJECTED'] + counts['FN_MISSED']
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    # Detection metrics (did algorithm find the peak at all?)
    detection_tp = tp + counts['FN_REJECTED']  # Found peak (even if rejected)
    detection_fn = counts['FN_MISSED']  # Missed entirely
    detection_recall = detection_tp / (detection_tp + detection_fn) if (detection_tp + detection_fn) > 0 else 0
    
    # Rejection accuracy (of rejected intervals, how many should have been rejected?)
    rejection_correct = tn
    rejection_incorrect = counts['FN_REJECTED']
    rejection_accuracy = rejection_correct / (rejection_correct + rejection_incorrect) if (rejection_correct + rejection_incorrect) > 0 else 0
    
    print(f"\n{'='*70}")
    print("HRR ALGORITHM VALIDATION STATS")
    print(f"{'='*70}")
    print(f"\nTotal judgments: {sum(counts.values())}")
    print(f"Sessions with judgments: {len(by_session)}")
    print(f"\nCounts:")
    print(f"  TP (correct detections):     {tp:>4}")
    print(f"  FP (false detections):       {fp:>4}")
    print(f"  TN (correct rejections):     {tn:>4}")
    print(f"  FN_REJECTED (wrong reject):  {counts['FN_REJECTED']:>4}")
    print(f"  FN_MISSED (missed peaks):    {counts['FN_MISSED']:>4}")
    print(f"  SKIP:                        {counts['SKIP']:>4}")
    
    print(f"\n--- Classification Metrics (Pass/Reject decision) ---")
    print(f"  Precision:  {precision:.3f}  (of intervals marked 'pass', how many are real?)")
    print(f"  Recall:     {recall:.3f}  (of real peaks, how many marked 'pass'?)")
    print(f"  F1 Score:   {f1:.3f}")
    
    print(f"\n--- Detection Metrics (Finding peaks at all) ---")
    print(f"  Detection Recall: {detection_recall:.3f}  (of real peaks, how many detected?)")
    print(f"    (TP + FN_REJECTED) / (TP + FN_REJECTED + FN_MISSED)")
    
    print(f"\n--- Rejection Accuracy ---")
    print(f"  Rejection Accuracy: {rejection_accuracy:.3f}  (of rejected, how many should be?)")
    print(f"    TN / (TN + FN_REJECTED)")
    
    # Per-session breakdown
    print(f"\n--- Per-Session Breakdown ---")
    print(f"{'Session':>8} | {'TP':>3} | {'FP':>3} | {'TN':>3} | {'FN_R':>4} | {'FN_M':>4} | {'Prec':>5} | {'Recall':>6}")
    print(f"{'-'*60}")
    
    for sid in sorted(by_session.keys(), key=int):
        s = by_session[sid]
        s_tp = s['TP']
        s_fp = s['FP']
        s_fn = s['FN_REJECTED'] + s['FN_MISSED']
        s_prec = s_tp / (s_tp + s_fp) if (s_tp + s_fp) > 0 else 0
        s_recall = s_tp / (s_tp + s_fn) if (s_tp + s_fn) > 0 else 0
        
        print(f"{sid:>8} | {s['TP']:>3} | {s['FP']:>3} | {s['TN']:>3} | {s['FN_REJECTED']:>4} | {s['FN_MISSED']:>4} | {s_prec:>5.2f} | {s_recall:>6.2f}")
    
    print()


def mark_reviewed(session_id: int):
    """Mark a session as reviewed."""
    state = load_review_state()
    
    if session_id not in state['reviewed_sessions']:
        state['reviewed_sessions'].append(session_id)
    
    if session_id in state['in_progress']:
        state['in_progress'].remove(session_id)
    
    save_review_state(state)
    print(f"Session {session_id} marked as reviewed.")


def review_session(conn, session_id: int, output_dir: str, age: int, rhr: int):
    """Review a single session: viz + export + mark in progress."""
    # Mark in progress
    state = load_review_state()
    if session_id not in state['in_progress'] and session_id not in state['reviewed_sessions']:
        state['in_progress'].append(session_id)
        save_review_state(state)
    
    # Export CSV for this session
    export_intervals(conn, session_id)
    
    # Run viz
    viz_script = PROJECT_ROOT / 'scripts' / 'hrr_qc_viz.py'
    cmd = [
        'python', str(viz_script),
        '--session-id', str(session_id),
        '--output-dir', output_dir,
        '--age', str(age),
        '--rhr', str(rhr),
    ]
    print(f"\nRunning: {' '.join(cmd)}\n")
    subprocess.run(cmd)


def get_next_unreviewed(conn) -> Optional[int]:
    """Get the next unreviewed session ID."""
    sessions = get_all_sessions(conn)
    state = load_review_state()
    reviewed = set(state.get('reviewed_sessions', []))
    in_progress = set(state.get('in_progress', []))
    
    for s in sessions:
        if s['session_id'] not in reviewed and s['session_id'] not in in_progress:
            return s['session_id']
    
    # If all are reviewed or in progress, return first in progress
    for s in sessions:
        if s['session_id'] in in_progress:
            return s['session_id']
    
    return None


def main():
    parser = argparse.ArgumentParser(description='HRR QC Review Workflow')
    
    # Modes
    parser.add_argument('--queue', action='store_true', help='Show review queue')
    parser.add_argument('--export-all', action='store_true', help='Export all intervals to CSV')
    parser.add_argument('--export', action='store_true', help='Export session intervals to CSV')
    parser.add_argument('--review', action='store_true', help='Review a session (viz + export)')
    parser.add_argument('--import-judgments', type=str, metavar='CSV', help='Import judgments from CSV')
    parser.add_argument('--stats', action='store_true', help='Calculate precision/recall stats')
    parser.add_argument('--mark-reviewed', action='store_true', help='Mark session as reviewed')
    
    # Options
    parser.add_argument('--session-id', type=int, help='Session ID')
    parser.add_argument('--next', action='store_true', help='Use next unreviewed session')
    parser.add_argument('--output-dir', default='/tmp', help='Output directory for viz')
    parser.add_argument('--age', type=int, default=50, help='Age for zone calculation')
    parser.add_argument('--rhr', type=int, default=60, help='RHR for zone calculation')
    
    args = parser.parse_args()
    
    conn = get_db_connection()
    
    try:
        if args.queue:
            show_queue(conn)
        
        elif args.export_all:
            export_intervals(conn, session_id=None)
        
        elif args.export:
            if not args.session_id:
                parser.error("--export requires --session-id")
            export_intervals(conn, args.session_id)
        
        elif args.review:
            session_id = args.session_id
            if args.next:
                session_id = get_next_unreviewed(conn)
                if session_id is None:
                    print("All sessions reviewed or in progress!")
                    return
                print(f"Next unreviewed session: {session_id}")
            
            if not session_id:
                parser.error("--review requires --session-id or --next")
            
            review_session(conn, session_id, args.output_dir, args.age, args.rhr)
        
        elif args.import_judgments:
            import_judgments(args.import_judgments)
        
        elif args.stats:
            calculate_stats()
        
        elif args.mark_reviewed:
            if not args.session_id:
                parser.error("--mark-reviewed requires --session-id")
            mark_reviewed(args.session_id)
        
        else:
            parser.print_help()
    
    finally:
        conn.close()


if __name__ == '__main__':
    main()
