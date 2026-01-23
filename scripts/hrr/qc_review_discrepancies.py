#!/usr/bin/env python3
"""
HRR QC Discrepancy Review Tool

Batch review of intervals where human QC judgments conflict with algorithm output.

Usage:
    python scripts/hrr/qc_review_discrepancies.py                    # Show first 5 discrepancies
    python scripts/hrr/qc_review_discrepancies.py --batch-size 10    # Show 10 at a time
    python scripts/hrr/qc_review_discrepancies.py --offset 5         # Skip first 5
    python scripts/hrr/qc_review_discrepancies.py --show-viz-commands # Print viz commands
    python scripts/hrr/qc_review_discrepancies.py --low-hrr          # Show HRR60 < 10 review list
"""

import argparse
import os
from pathlib import Path
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')


def get_db_connection():
    """Get connection to arnold_analytics database."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'arnold_analytics'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        cursor_factory=RealDictCursor
    )


def get_discrepancies(conn, batch_size: int, offset: int) -> tuple[List[dict], int]:
    """
    Query intervals where human QC judgments conflict with algorithm output.

    Discrepancies are:
    - judgment = 'reject_passed' AND quality_status = 'pass' (human rejected algo pass)
    - judgment = 'confirm_rejection' AND quality_status = 'pass' (human confirmed rejection but algo shows pass)
    - judgment = 'override_accept' AND quality_status = 'rejected' (human accepted but algo rejected)

    Returns (list of discrepancies, total count)
    """
    # Count total discrepancies
    count_query = """
        SELECT COUNT(*) as total
        FROM hrr_qc_judgments j
        JOIN hr_recovery_intervals i ON (
            (j.polar_session_id = i.polar_session_id AND j.interval_order = i.interval_order)
            OR (j.endurance_session_id = i.endurance_session_id AND j.interval_order = i.interval_order)
        )
        WHERE j.judgment IN ('reject_passed', 'confirm_rejection', 'override_accept')
          AND (
            (j.judgment = 'reject_passed' AND i.quality_status = 'pass')
            OR (j.judgment = 'confirm_rejection' AND i.quality_status = 'pass')
            OR (j.judgment = 'override_accept' AND i.quality_status = 'rejected')
          )
    """

    with conn.cursor() as cur:
        cur.execute(count_query)
        total = cur.fetchone()['total']

    # Get batch of discrepancies
    query = """
        SELECT
            j.polar_session_id,
            j.endurance_session_id,
            j.interval_order,
            j.judgment,
            j.judged_at,
            j.notes,
            i.quality_status,
            i.hrr60_abs,
            i.hrr120_abs,
            i.r2_0_30,
            i.r2_30_60,
            i.auto_reject_reason
        FROM hrr_qc_judgments j
        JOIN hr_recovery_intervals i ON (
            (j.polar_session_id = i.polar_session_id AND j.interval_order = i.interval_order)
            OR (j.endurance_session_id = i.endurance_session_id AND j.interval_order = i.interval_order)
        )
        WHERE j.judgment IN ('reject_passed', 'confirm_rejection', 'override_accept')
          AND (
            (j.judgment = 'reject_passed' AND i.quality_status = 'pass')
            OR (j.judgment = 'confirm_rejection' AND i.quality_status = 'pass')
            OR (j.judgment = 'override_accept' AND i.quality_status = 'rejected')
          )
        ORDER BY j.judged_at DESC
        LIMIT %s OFFSET %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (batch_size, offset))
        rows = cur.fetchall()

    return list(rows), total


def get_low_hrr_intervals(conn, batch_size: int, offset: int) -> tuple[List[dict], int]:
    """
    Query intervals with HRR60 < 10 that are pass/flagged (potential quality issues).

    Returns (list of intervals, total count)
    """
    count_query = """
        SELECT COUNT(*) as total
        FROM hr_recovery_intervals i
        LEFT JOIN hrr_qc_judgments j ON (
            (j.polar_session_id = i.polar_session_id AND j.interval_order = i.interval_order)
            OR (j.endurance_session_id = i.endurance_session_id AND j.interval_order = i.interval_order)
        )
        WHERE i.hrr60_abs < 10
          AND i.hrr60_abs IS NOT NULL
          AND i.quality_status IN ('pass', 'flagged')
    """

    with conn.cursor() as cur:
        cur.execute(count_query)
        total = cur.fetchone()['total']

    query = """
        SELECT
            i.polar_session_id,
            i.endurance_session_id,
            i.interval_order,
            j.judgment,
            j.judged_at,
            j.notes as judgment_notes,
            i.quality_status,
            i.hrr60_abs,
            i.hrr120_abs,
            i.r2_0_30,
            i.r2_30_60,
            i.auto_reject_reason
        FROM hr_recovery_intervals i
        LEFT JOIN hrr_qc_judgments j ON (
            (j.polar_session_id = i.polar_session_id AND j.interval_order = i.interval_order)
            OR (j.endurance_session_id = i.endurance_session_id AND j.interval_order = i.interval_order)
        )
        WHERE i.hrr60_abs < 10
          AND i.hrr60_abs IS NOT NULL
          AND i.quality_status IN ('pass', 'flagged')
        ORDER BY i.hrr60_abs ASC, i.polar_session_id, i.interval_order
        LIMIT %s OFFSET %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (batch_size, offset))
        rows = cur.fetchall()

    return list(rows), total


def format_session_label(row: dict) -> str:
    """Format session/interval label like S22:I8 or E1:I8."""
    if row.get('polar_session_id'):
        return f"S{row['polar_session_id']}:I{row['interval_order']}"
    elif row.get('endurance_session_id'):
        return f"E{row['endurance_session_id']}:I{row['interval_order']}"
    return f"?:I{row['interval_order']}"


def format_viz_command(row: dict) -> str:
    """Generate the viz command for this interval."""
    if row.get('polar_session_id'):
        return f"python scripts/hrr_qc_viz.py --session-id {row['polar_session_id']}"
    elif row.get('endurance_session_id'):
        return f"python scripts/hrr_qc_viz.py --session-id {row['endurance_session_id']} --source endurance"
    return "# Unknown session type"


def format_value(val, decimals: int = 2) -> str:
    """Format a numeric value or return '-' if None."""
    if val is None:
        return '-'
    if isinstance(val, float):
        return f"{val:.{decimals}f}"
    return str(val)


def print_discrepancy(row: dict, index: int, total_in_batch: int, show_viz: bool = False):
    """Print a single discrepancy in the specified format."""
    label = format_session_label(row)
    judgment = row.get('judgment', '?')
    judged_at = row.get('judged_at')
    judged_date = judged_at.strftime('%Y-%m-%d') if judged_at else '?'
    notes = row.get('notes') or row.get('judgment_notes') or ''

    status = row.get('quality_status', '?')
    hrr60 = format_value(row.get('hrr60_abs'), 0)
    r2_0_30 = format_value(row.get('r2_0_30'))
    r2_30_60 = format_value(row.get('r2_30_60'))

    print(f"[{index}/{total_in_batch}] {label}")
    print(f"Judgment: {judgment} ({judged_date})")
    if notes:
        print(f'Notes: "{notes}"')
    print(f"Current: {status} | HRR60={hrr60} | r2_0_30={r2_0_30} | r2_30_60={r2_30_60}")

    if show_viz:
        viz_cmd = format_viz_command(row)
        print(f"Viz: {viz_cmd}")

    print()


def print_low_hrr_interval(row: dict, index: int, total_in_batch: int, show_viz: bool = False):
    """Print a single low-HRR interval for review."""
    label = format_session_label(row)
    judgment = row.get('judgment')
    judged_at = row.get('judged_at')

    status = row.get('quality_status', '?')
    hrr60 = format_value(row.get('hrr60_abs'), 0)
    hrr120 = format_value(row.get('hrr120_abs'), 0)
    r2_0_30 = format_value(row.get('r2_0_30'))
    r2_30_60 = format_value(row.get('r2_30_60'))

    print(f"[{index}/{total_in_batch}] {label}")
    print(f"Status: {status} | HRR60={hrr60} | HRR120={hrr120} | r2_0_30={r2_0_30} | r2_30_60={r2_30_60}")

    if judgment:
        judged_date = judged_at.strftime('%Y-%m-%d') if judged_at else '?'
        print(f"Previous judgment: {judgment} ({judged_date})")
    else:
        print("No previous judgment")

    if show_viz:
        viz_cmd = format_viz_command(row)
        print(f"Viz: {viz_cmd}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Batch review of HRR QC discrepancies'
    )
    parser.add_argument('--batch-size', type=int, default=5,
                        help='Number of discrepancies to show (default: 5)')
    parser.add_argument('--offset', type=int, default=0,
                        help='Skip first N discrepancies (default: 0)')
    parser.add_argument('--show-viz-commands', action='store_true',
                        help='Print hrr_qc_viz.py commands for each interval')
    parser.add_argument('--low-hrr', action='store_true',
                        help='Show HRR60 < 10 review list instead of discrepancies')

    args = parser.parse_args()

    conn = get_db_connection()

    try:
        if args.low_hrr:
            rows, total = get_low_hrr_intervals(conn, args.batch_size, args.offset)
            list_type = "low HRR60 intervals"
            print_fn = print_low_hrr_interval
        else:
            rows, total = get_discrepancies(conn, args.batch_size, args.offset)
            list_type = "discrepancies"
            print_fn = print_discrepancy

        if not rows:
            print(f"No {list_type} found.")
            return

        print(f"\n{'='*60}")
        print(f"HRR QC Review - {list_type.title()}")
        print(f"{'='*60}\n")

        for i, row in enumerate(rows, start=1):
            print_fn(row, i, len(rows), args.show_viz_commands)

        # Summary
        print(f"{'='*60}")
        reviewed_end = args.offset + len(rows)
        print(f"Reviewed {args.offset + 1}-{reviewed_end} of {total} total {list_type}")

        if reviewed_end < total:
            next_offset = args.offset + args.batch_size
            mode_flag = "--low-hrr " if args.low_hrr else ""
            print(f"Next batch: python scripts/hrr/qc_review_discrepancies.py {mode_flag}--offset {next_offset}")
        else:
            print("All items reviewed.")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
