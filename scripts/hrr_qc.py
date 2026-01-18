#!/usr/bin/env python3
"""
HRR QC Review - Interactive Session

ONE COMMAND: python scripts/hrr_qc.py

For each interval, the algorithm made a PASS or REJECT decision.
You judge: Was that decision CORRECT or WRONG?

Judgment codes:
  y = Yes, algorithm was correct (PASS was right, or REJECT was right)
  n = No, algorithm was wrong (should have been opposite)
  s = Skip (can't tell)
  p = Peak is shifted (detection found wrong spot)
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def get_queue(conn) -> List[dict]:
    """Get sessions needing review."""
    query = """
        SELECT 
            hri.polar_session_id as session_id,
            ps.start_time::date as session_date,
            ps.sport_type,
            ps.hrr_qc_status,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE hri.quality_status = 'pass') as pass_ct,
            COUNT(*) FILTER (WHERE hri.quality_status = 'rejected') as rejected_ct
        FROM hr_recovery_intervals hri
        JOIN polar_sessions ps ON ps.id = hri.polar_session_id
        GROUP BY hri.polar_session_id, ps.start_time, ps.sport_type, ps.hrr_qc_status
        ORDER BY ps.start_time
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    
    return [
        {
            'session_id': r[0],
            'date': r[1],
            'sport': r[2],
            'status': r[3] or 'pending',
            'total': r[4],
            'pass_ct': r[5],
            'rejected_ct': r[6],
        }
        for r in rows
    ]


def show_queue(sessions: List[dict]):
    """Display the review queue."""
    print_header("HRR QC REVIEW QUEUE")
    
    pending = [s for s in sessions if s['status'] == 'pending']
    in_progress = [s for s in sessions if s['status'] == 'in_progress']
    reviewed = [s for s in sessions if s['status'] == 'reviewed']
    
    print(f"{'#':>3} {'ID':>4} | {'Date':^12} | {'Sport':<18} | {'Tot':>3} | {'Pass':>4} | {'Rej':>3} | Status")
    print(f"{'-'*80}")
    
    for idx, s in enumerate(sessions, 1):
        status_icon = {'pending': '○', 'in_progress': '◐', 'reviewed': '●'}.get(s['status'], '?')
        print(f"{idx:>3} {s['session_id']:>4} | {s['date'].strftime('%Y-%m-%d'):^12} | {s['sport'][:18]:<18} | {s['total']:>3} | {s['pass_ct']:>4} | {s['rejected_ct']:>3} | {status_icon} {s['status']}")
    
    print(f"\n○ pending: {len(pending)} | ◐ in progress: {len(in_progress)} | ● reviewed: {len(reviewed)}")


def get_intervals(conn, session_id: int) -> List[dict]:
    """Get intervals for a session."""
    query = """
        SELECT 
            interval_order,
            hr_peak,
            duration_seconds,
            hrr60_abs,
            hrr120_abs,
            hrr300_abs,
            quality_status,
            auto_reject_reason,
            quality_flags,
            r2_0_60,
            r2_0_120
        FROM hr_recovery_intervals
        WHERE polar_session_id = %s
        ORDER BY interval_order
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()
    
    return [
        {
            'order': r[0],
            'peak': r[1],
            'duration': r[2],
            'hrr60': r[3],
            'hrr120': r[4],
            'hrr300': r[5],
            'status': r[6],
            'reject_reason': r[7],
            'flags': r[8],
            'r2_60': r[9],
            'r2_120': r[10],
        }
        for r in rows
    ]


def get_existing_judgment(conn, session_id: int, interval_order: int) -> Optional[dict]:
    """Check if judgment already exists."""
    query = """
        SELECT judgment, peak_correct, notes FROM hrr_qc_judgments 
        WHERE polar_session_id = %s AND interval_order = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id, interval_order))
        row = cur.fetchone()
    if row:
        return {'judgment': row[0], 'peak_correct': row[1], 'notes': row[2]}
    return None


def save_judgment(conn, session_id: int, interval_order: int, judgment: str, 
                  algo_status: str, algo_reason: str, peak_correct: str = None, notes: str = None):
    """Save or update a judgment."""
    query = """
        INSERT INTO hrr_qc_judgments 
            (polar_session_id, interval_order, judgment, algo_status, algo_reject_reason, peak_correct, notes, judged_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (polar_session_id, interval_order) 
        DO UPDATE SET 
            judgment = EXCLUDED.judgment,
            algo_status = EXCLUDED.algo_status,
            algo_reject_reason = EXCLUDED.algo_reject_reason,
            peak_correct = EXCLUDED.peak_correct,
            notes = EXCLUDED.notes,
            judged_at = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id, interval_order, judgment, algo_status, algo_reason, peak_correct, notes))
    conn.commit()


def update_session_status(conn, session_id: int, status: str):
    """Update session QC status."""
    query = """
        UPDATE polar_sessions 
        SET hrr_qc_status = %s,
            hrr_qc_reviewed_at = CASE WHEN %s = 'reviewed' THEN NOW() ELSE hrr_qc_reviewed_at END
        WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (status, status, session_id))
    conn.commit()


def show_stats(conn):
    """Show current validation stats."""
    query = """
        SELECT 
            tp, fp, tn, fn_rejected, fn_missed, total,
            precision, recall, f1, detection_recall, rejection_accuracy
        FROM hrr_qc_stats
    """
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
    except Exception as e:
        print(f"\nStats view not available: {e}")
        print("Run migration 022 first: psql -d arnold_analytics -f scripts/migrations/022_hrr_qc_validation.sql")
        return
    
    if not row or row[5] == 0:
        print("\nNo judgments yet. Review some sessions first!")
        return
    
    tp, fp, tn, fn_rej, fn_miss, total, prec, recall, f1, det_recall, rej_acc = row
    
    print_header("ALGORITHM VALIDATION STATS")
    
    print(f"Total judgments: {total}\n")
    print(f"  Correct PASS decisions:     {tp:>4}  (TP)")
    print(f"  Wrong PASS decisions:       {fp:>4}  (FP - should have rejected)")
    print(f"  Correct REJECT decisions:   {tn:>4}  (TN)")
    print(f"  Wrong REJECT decisions:     {fn_rej:>4}  (FN - should have passed)")
    print(f"  Missed peaks entirely:      {fn_miss:>4}")
    
    print(f"\n--- Metrics ---")
    print(f"  Precision:         {prec or 0:.3f}  (of passes, how many were correct?)")
    print(f"  Recall:            {recall or 0:.3f}  (of real peaks, how many passed?)")
    print(f"  F1 Score:          {f1 or 0:.3f}")


def open_viz(session_id: int, output_dir: str = '/tmp') -> str:
    """Generate viz and open in Preview (non-blocking). Returns image path."""
    viz_script = PROJECT_ROOT / 'scripts' / 'hrr_qc_viz.py'
    output_path = f"{output_dir}/hrr_qc_{session_id}.png"
    
    # Generate viz (don't show, just save)
    cmd = ['python', str(viz_script), '--session-id', str(session_id), 
           '--output-dir', output_dir, '--no-show']
    subprocess.run(cmd, capture_output=True)
    
    # Open in Preview (macOS) - non-blocking
    if sys.platform == 'darwin':
        subprocess.Popen(['open', output_path])
    elif sys.platform == 'linux':
        subprocess.Popen(['xdg-open', output_path])
    else:
        print(f"Open manually: {output_path}")
    
    return output_path


def map_judgment(response: str, algo_status: str) -> tuple:
    """
    Map y/n response to TP/FP/TN/FN based on what algorithm decided.
    
    Returns: (judgment_code, peak_correct, notes)
    """
    response = response.strip().lower()
    parts = response.split(maxsplit=1)
    answer = parts[0] if parts else ''
    notes = parts[1] if len(parts) > 1 else None
    
    peak_correct = 'yes'  # default
    
    if answer in ('y', 'yes'):
        # Algorithm was correct
        if algo_status == 'pass':
            return ('TP', peak_correct, notes)  # Correct pass
        else:
            return ('TN', peak_correct, notes)  # Correct reject
    
    elif answer in ('n', 'no'):
        # Algorithm was wrong
        if algo_status == 'pass':
            return ('FP', peak_correct, notes)  # Wrong pass (should have rejected)
        else:
            return ('FN_REJECTED', peak_correct, notes)  # Wrong reject (should have passed)
    
    elif answer in ('s', 'skip'):
        return ('SKIP', None, notes)
    
    elif answer in ('p', 'peak', 'shifted'):
        # Peak location is wrong - still need pass/fail judgment
        return (None, 'shifted', notes)  # Signal to ask follow-up
    
    return (None, None, None)  # Invalid


def review_session(conn, session_id: int):
    """Interactive review of a single session."""
    intervals = get_intervals(conn, session_id)
    
    if not intervals:
        print(f"No intervals found for session {session_id}")
        return
    
    # Mark as in progress
    update_session_status(conn, session_id, 'in_progress')
    
    print_header(f"REVIEWING SESSION {session_id}")
    print(f"Found {len(intervals)} intervals\n")
    
    # Show summary
    print(f"{'#':>2} {'Peak':>4} {'Dur':>4} {'HRR60':>5} {'HRR120':>6} {'HRR300':>6} {'Status':>8} {'Reason':<25}")
    print(f"{'-'*80}")
    for i in intervals:
        reason = (i['reject_reason'] or '-')[:25]
        hrr60 = i['hrr60'] if i['hrr60'] else '-'
        hrr120 = i['hrr120'] if i['hrr120'] else '-'
        hrr300 = i['hrr300'] if i['hrr300'] else '-'
        print(f"{i['order']:>2} {i['peak'] or 0:>4} {i['duration'] or 0:>4} {hrr60:>5} {hrr120:>6} {hrr300:>6} {i['status']:>8} {reason:<25}")
    
    # Open viz in Preview (stays open)
    print(f"\n→ Opening visualization in Preview...")
    viz_path = open_viz(session_id)
    print(f"  Image: {viz_path}")
    
    print(f"""
{'='*70}
JUDGMENT TIME - Look at the viz, judge each interval
{'='*70}

For each interval, the algorithm made a PASS or REJECT decision.
You answer: Was that correct?

  y = Yes, correct decision
  n = No, wrong decision (should be opposite)
  s = Skip (can't tell)
  p = Peak location is shifted/wrong

Add notes after: "n artifact" or "y" or "p 5sec late"

Commands:
  q = quit and save progress
  r = refresh viz
  stats = show current stats
""")
    
    for interval in intervals:
        order = interval['order']
        existing = get_existing_judgment(conn, session_id, order)
        
        # Build prompt
        status = interval['status'].upper()
        dur = interval['duration'] or 0
        reason = f" ({interval['reject_reason']})" if interval['reject_reason'] else ""
        
        if status == 'PASS':
            prompt_text = f"PASSED as valid {dur}s recovery"
        else:
            prompt_text = f"REJECTED{reason}"
        
        existing_str = ""
        if existing:
            existing_str = f" [was: {existing['judgment']}"
            if existing.get('peak_correct') == 'shifted':
                existing_str += ", peak shifted"
            existing_str += "]"
        
        prompt = f"\np{order:02d}: Algorithm {prompt_text}{existing_str}\n    Correct? (y/n/s/p) > "
        
        while True:
            response = input(prompt).strip()
            
            if not response:
                if existing:
                    print(f"    → Keeping: {existing['judgment']}")
                    break
                print("    Enter y/n/s/p or 'q' to quit")
                continue
            
            if response.lower() == 'q':
                print("\n→ Progress saved. Session marked as in_progress.")
                return
            
            if response.lower() == 'r':
                open_viz(session_id)
                print("    → Viz refreshed")
                continue
            
            if response.lower() == 'stats':
                show_stats(conn)
                continue
            
            judgment, peak_correct, notes = map_judgment(response, interval['status'])
            
            if judgment is None and peak_correct == 'shifted':
                # Peak is shifted - ask for pass/fail judgment too
                followup = input("    Peak shifted. Was the PASS/REJECT decision still correct? (y/n) > ").strip().lower()
                if followup in ('y', 'yes'):
                    judgment = 'TP' if interval['status'] == 'pass' else 'TN'
                elif followup in ('n', 'no'):
                    judgment = 'FP' if interval['status'] == 'pass' else 'FN_REJECTED'
                else:
                    judgment = 'SKIP'
            
            if judgment is None:
                print("    Invalid. Use: y, n, s, p")
                continue
            
            # Save
            save_judgment(
                conn, session_id, order, judgment,
                interval['status'], interval['reject_reason'],
                peak_correct, notes
            )
            
            # Friendly confirmation
            if judgment == 'TP':
                conf = "✓ Correct PASS"
            elif judgment == 'TN':
                conf = "✓ Correct REJECT"
            elif judgment == 'FP':
                conf = "✗ Wrong PASS (should reject)"
            elif judgment == 'FN_REJECTED':
                conf = "✗ Wrong REJECT (should pass)"
            else:
                conf = f"→ {judgment}"
            
            extra = ""
            if peak_correct == 'shifted':
                extra = " [peak shifted]"
            if notes:
                extra += f" - {notes}"
            
            print(f"    {conf}{extra}")
            break
    
    # Mark as reviewed
    update_session_status(conn, session_id, 'reviewed')
    print(f"\n✓ Session {session_id} marked as REVIEWED")
    
    show_stats(conn)


def get_next_unreviewed(sessions: List[dict]) -> Optional[int]:
    """Get the next unreviewed session ID."""
    for s in sessions:
        if s['status'] == 'pending':
            return s['session_id']
    for s in sessions:
        if s['status'] == 'in_progress':
            return s['session_id']
    return None


def main():
    conn = get_db_connection()
    
    try:
        while True:
            os.system('clear' if os.name != 'nt' else 'cls')
            sessions = get_queue(conn)
            show_queue(sessions)
            
            print(f"""
{'='*70}
  [number]  Review by queue # (e.g., "5")
  [id]      Review by session ID (e.g., "71")  
  n         Next pending session
  s         Show stats
  q         Quit
{'='*70}
""")
            
            choice = input("> ").strip().lower()
            
            if choice == 'q':
                print("\nGoodbye!")
                break
            
            if choice == 's':
                show_stats(conn)
                input("\nPress Enter to continue...")
                continue
            
            if choice == 'n':
                session_id = get_next_unreviewed(sessions)
                if session_id is None:
                    print("\nAll sessions reviewed or in progress!")
                    input("Press Enter to continue...")
                    continue
            else:
                try:
                    num = int(choice)
                    if 1 <= num <= len(sessions):
                        session_id = sessions[num - 1]['session_id']
                    else:
                        session_id = num
                        if not any(s['session_id'] == session_id for s in sessions):
                            print(f"\nSession {session_id} not found")
                            input("Press Enter to continue...")
                            continue
                except ValueError:
                    print(f"\nInvalid: {choice}")
                    input("Press Enter to continue...")
                    continue
            
            review_session(conn, session_id)
            input("\nPress Enter to continue...")
    
    finally:
        conn.close()


if __name__ == '__main__':
    main()
