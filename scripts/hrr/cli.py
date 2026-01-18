"""
HRR Feature Extraction - CLI Interface

Command-line interface and session processing.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import List

from .types import HRRConfig, RecoveryInterval
from .persistence import (
    get_db_connection, get_hr_samples, get_resting_hr, save_intervals,
    get_peak_adjustments, mark_adjustments_applied,
    get_quality_overrides, mark_overrides_applied, apply_quality_overrides
)
from .detection import extract_features
from .metrics import assess_quality

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Summary Output
# =============================================================================

def print_summary_tables(intervals: List[RecoveryInterval], session_id: int, session_start: datetime = None):
    """Print formatted summary tables for detected intervals."""

    if not intervals:
        print(f"\nNo recovery intervals detected for session {session_id}")
        return

    print(f"\n{'='*80}")
    print(f"HRR Feature Extraction Summary - Session {session_id}")
    print(f"{'='*80}")

    # Use first interval's start as session start if not provided
    if session_start is None and intervals:
        session_start = intervals[0].start_time

    # Table 1: Basic metrics
    print(f"\n{'Interval Summary':^80}")
    print("-" * 80)
    print(f"{'#':>3} {'Elapsed':>8} {'Peak':>4} {'Dur':>4} {'Onset':>5} {'Conf':>6} {'Status':>8}")
    print("-" * 80)

    for i in intervals:
        onset = i.onset_delay_sec if i.onset_delay_sec else 0
        conf = i.onset_confidence[:3] if i.onset_confidence else '?'
        # Format elapsed time as MM:SS from session start
        if session_start and i.start_time:
            elapsed_sec = int((i.start_time - session_start).total_seconds())
            elapsed_min = elapsed_sec // 60
            elapsed_s = elapsed_sec % 60
            elapsed_str = f"{elapsed_min:02d}:{elapsed_s:02d}"
        else:
            elapsed_str = '?'
        print(f"{i.interval_order:>3} {elapsed_str:>8} {i.hr_peak:>4} {i.duration_seconds:>4} {onset:>5} {conf:>6} {i.quality_status:>8}")

    # Table 2: HRR values (all intervals)
    print(f"\n{'HRR Values (absolute drop in bpm)':^80}")
    print("-" * 80)
    print(f"{'#':>3} {'HRR30':>6} {'HRR60':>6} {'HRR120':>7} {'HRR180':>7} {'HRR240':>7} {'HRR300':>7} {'Tau':>6} {'R²':>5}")
    print("-" * 80)

    for i in intervals:
        # Don't display values for rejected intervals - they're garbage
        if i.quality_status == 'rejected':
            print(f"{i.interval_order:>3} {'-':>6} {'-':>6} {'-':>7} {'-':>7} {'-':>7} {'-':>7} {'-':>6} {'-':>5}")
            continue
        hrr30 = f"{i.hrr30_abs}" if i.hrr30_abs else "-"
        hrr60 = f"{i.hrr60_abs}" if i.hrr60_abs else "-"
        hrr120 = f"{i.hrr120_abs}" if i.hrr120_abs else "-"
        hrr180 = f"{i.hrr180_abs}" if i.hrr180_abs else "-"
        hrr240 = f"{i.hrr240_abs}" if i.hrr240_abs else "-"
        hrr300 = f"{i.hrr300_abs}" if i.hrr300_abs else "-"
        tau = f"{i.tau_seconds:.0f}" if i.tau_seconds else "-"
        r2 = f"{i.tau_fit_r2:.2f}" if i.tau_fit_r2 else "-"
        print(f"{i.interval_order:>3} {hrr30:>6} {hrr60:>6} {hrr120:>7} {hrr180:>7} {hrr240:>7} {hrr300:>7} {tau:>6} {r2:>5}")

    # Table 3: Segment R² values (all intervals)
    print(f"\n{'Segment R² Values':^95}")
    print("-" * 95)
    print(f"{'#':>3} {'0-30':>6} {'30-60':>6} {'0-60':>6} {'30-90':>6} {'Slope':>7} {'0-120':>7} {'0-180':>7} {'0-240':>7} {'0-300':>7}")
    print("-" * 95)

    def mark(v):
        if v is None:
            return "-"
        elif v >= 0.75:
            return f"{v:.2f}"
        else:
            return f"{v:.2f}*"

    def fmt_slope(v):
        if v is None:
            return "-"
        elif v > 0.1:
            return f"{v:.3f}!"
        elif v > 0:
            return f"{v:.3f}?"
        else:
            return f"{v:.3f}"

    for i in intervals:
        print(f"{i.interval_order:>3} {mark(i.r2_0_30):>6} {mark(i.r2_30_60):>6} {mark(i.r2_0_60):>6} {mark(i.r2_30_90):>6} {fmt_slope(i.slope_90_120):>7} {mark(i.r2_0_120):>7} {mark(i.r2_0_180):>7} {mark(i.r2_0_240):>7} {mark(i.r2_0_300):>7}")

    # Table 4: Quality flags
    print(f"\n{'Quality Assessment':^80}")
    print("-" * 80)
    print(f"{'#':>3} {'Status':>8} {'Reason/Flags':<50}")
    print("-" * 80)

    for i in intervals:
        if i.quality_status == 'rejected':
            reason = i.auto_reject_reason or 'unknown'
            print(f"{i.interval_order:>3} {'REJECTED':>8} {reason:<50}")
        else:
            flags = ', '.join(i.quality_flags) if i.quality_flags else 'clean'
            print(f"{i.interval_order:>3} {i.quality_status:>8} {flags:<50}")

    print("=" * 80)

    # Summary stats
    passed = sum(1 for i in intervals if i.quality_status == 'pass')
    flagged = sum(1 for i in intervals if i.quality_status == 'flagged')
    rejected = sum(1 for i in intervals if i.quality_status == 'rejected')
    print(f"\nTotal: {len(intervals)} intervals | Pass: {passed} | Flagged: {flagged} | Rejected: {rejected}")


# =============================================================================
# Session Processing
# =============================================================================

def process_session(session_id: int, source: str = 'polar', dry_run: bool = False, quiet: bool = False):
    """Process a single session."""

    logger.info(f"Processing session {session_id} (source: {source})")

    conn = get_db_connection()

    try:
        # Get HR samples
        samples = get_hr_samples(conn, session_id, source)
        if not samples:
            logger.warning(f"No HR samples found for session {session_id}")
            return

        logger.info(f"Loaded {len(samples)} HR samples")

        # Get resting HR
        session_date = samples[0].timestamp
        resting_hr = get_resting_hr(conn, session_date)

        if resting_hr is None:
            # Use estimated resting HR
            resting_hr = 55  # Default for athlete
            logger.info(f"Using default resting HR: {resting_hr}")
        else:
            logger.info(f"Using recorded resting HR: {resting_hr}")

        # Load manual peak adjustments
        peak_adjustments = get_peak_adjustments(conn, session_id, source)
        if peak_adjustments:
            logger.info(f"Loaded {len(peak_adjustments)} peak adjustments: {peak_adjustments}")

        # Extract features - load config from YAML
        config = HRRConfig.from_yaml()
        intervals = extract_features(samples, resting_hr, config, peak_adjustments)

        # Load and apply human quality overrides
        quality_overrides = get_quality_overrides(conn, session_id, source)
        if quality_overrides:
            logger.info(f"Loaded {len(quality_overrides)} quality overrides")
            intervals = apply_quality_overrides(intervals, quality_overrides)

        # Print summary
        if not quiet:
            session_start = samples[0].timestamp if samples else None
            print_summary_tables(intervals, session_id, session_start)

        # Save to database
        if not dry_run and intervals:
            save_intervals(conn, intervals, session_id, source)
            logger.info(f"Saved {len(intervals)} intervals to database")

            # Mark peak adjustments as applied
            if peak_adjustments:
                mark_adjustments_applied(conn, session_id, source)
                conn.commit()
                logger.info(f"Marked {len(peak_adjustments)} peak adjustments as applied")

            # Mark quality overrides as applied
            if quality_overrides:
                mark_overrides_applied(conn, session_id, source)
                conn.commit()
                logger.info(f"Marked {len(quality_overrides)} quality overrides as applied")
        elif dry_run:
            logger.info("Dry run - not saving to database")

    finally:
        conn.close()


def process_all_sessions(source: str = 'polar', dry_run: bool = False, reprocess: bool = False, quiet: bool = False):
    """Process all sessions that need HRR extraction."""

    conn = get_db_connection()

    try:
        # hr_samples uses session_id for polar, endurance_session_id for endurance
        # hr_recovery_intervals uses polar_session_id and endurance_session_id
        if source == 'polar':
            if reprocess:
                # Reprocess all sessions with HR data
                query = """
                    SELECT DISTINCT session_id
                    FROM hr_samples
                    WHERE session_id IS NOT NULL
                    ORDER BY session_id
                """
            else:
                # Only sessions without existing intervals
                query = """
                    SELECT DISTINCT s.session_id
                    FROM hr_samples s
                    LEFT JOIN hr_recovery_intervals i ON s.session_id = i.polar_session_id
                    WHERE s.session_id IS NOT NULL
                      AND i.polar_session_id IS NULL
                    ORDER BY s.session_id
                """
        else:
            if reprocess:
                query = """
                    SELECT DISTINCT endurance_session_id
                    FROM hr_samples
                    WHERE endurance_session_id IS NOT NULL
                    ORDER BY endurance_session_id
                """
            else:
                query = """
                    SELECT DISTINCT s.endurance_session_id
                    FROM hr_samples s
                    LEFT JOIN hr_recovery_intervals i ON s.endurance_session_id = i.endurance_session_id
                    WHERE s.endurance_session_id IS NOT NULL
                      AND i.endurance_session_id IS NULL
                    ORDER BY s.endurance_session_id
                """

        with conn.cursor() as cur:
            cur.execute(query)
            session_ids = [row[0] for row in cur.fetchall()]

        logger.info(f"Found {len(session_ids)} sessions to process")

        for session_id in session_ids:
            try:
                process_session(session_id, source, dry_run, quiet)
            except Exception as e:
                logger.error(f"Error processing session {session_id}: {e}")
                continue

    finally:
        conn.close()


def recompute_quality_only(source: str = 'polar'):
    """
    Recompute quality flags/status for existing intervals without re-extracting.
    Useful when flagging logic changes.
    """
    conn = get_db_connection()
    config = HRRConfig.from_yaml()

    try:
        # Load all intervals
        if source == 'polar':
            query = """
                SELECT
                    polar_session_id, interval_order,
                    r2_0_60, r2_0_120, r2_0_180, r2_0_240, r2_0_300,
                    r2_delta, slope_90_120, onset_confidence, is_low_signal,
                    sample_completeness
                FROM hr_recovery_intervals
                WHERE polar_session_id IS NOT NULL
                ORDER BY polar_session_id, interval_order
            """
        else:
            return  # Not implemented for endurance

        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        logger.info(f"Recomputing quality for {len(rows)} intervals")

        updates = []
        for row in rows:
            session_id, interval_order = row[0], row[1]
            r2_0_60, r2_0_120, r2_0_180, r2_0_240, r2_0_300 = row[2:7]
            r2_delta, slope_90_120, onset_confidence, is_low_signal = row[7:11]
            sample_completeness = row[11] if row[11] else 1.0

            # Create minimal interval for quality assessment
            interval = RecoveryInterval(
                start_time=datetime.now(),  # Placeholder
                end_time=datetime.now(),
                duration_seconds=300,  # Placeholder
                interval_order=interval_order,
                hr_peak=0,
                hr_nadir=0,
            )
            interval.r2_0_60 = r2_0_60
            interval.r2_0_120 = r2_0_120
            interval.r2_0_180 = r2_0_180
            interval.r2_0_240 = r2_0_240
            interval.r2_0_300 = r2_0_300
            interval.r2_delta = r2_delta
            interval.slope_90_120 = slope_90_120
            interval.onset_confidence = onset_confidence or 'unknown'
            interval.is_low_signal = is_low_signal or False
            interval.sample_completeness = sample_completeness

            # Assess quality
            interval = assess_quality(interval, config)

            # Prepare update
            flags_str = '|'.join(interval.quality_flags) if interval.quality_flags else None
            updates.append((
                interval.quality_status,
                flags_str,
                interval.auto_reject_reason,
                interval.review_priority,
                interval.needs_review,
                session_id,
                interval_order
            ))

        # Batch update
        update_query = """
            UPDATE hr_recovery_intervals
            SET quality_status = %s,
                quality_flags = %s,
                auto_reject_reason = %s,
                review_priority = %s,
                needs_review = %s
            WHERE polar_session_id = %s AND interval_order = %s
        """

        with conn.cursor() as cur:
            cur.executemany(update_query, updates)

        conn.commit()

        # Summary
        statuses = {}
        for u in updates:
            status = u[0]
            statuses[status] = statuses.get(status, 0) + 1

        logger.info(f"Updated {len(updates)} intervals: {statuses}")

    finally:
        conn.close()


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description='HRR Feature Extraction Pipeline')
    parser.add_argument('--session-id', type=int, help='Process specific session')
    parser.add_argument('--source', choices=['polar', 'endurance'], default='polar',
                        help='Data source (default: polar)')
    parser.add_argument('--all', action='store_true', help='Process all sessions')
    parser.add_argument('--dry-run', action='store_true', help='Do not save to database')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress table output')
    parser.add_argument('--reprocess', action='store_true', help='Reprocess existing intervals')
    parser.add_argument('--recompute-quality', action='store_true',
                        help='Recompute quality flags only (no re-extraction)')

    args = parser.parse_args()

    if args.recompute_quality:
        recompute_quality_only(args.source)
    elif args.session_id:
        process_session(args.session_id, args.source, args.dry_run, args.quiet)
    elif args.all:
        process_all_sessions(args.source, args.dry_run, args.reprocess, args.quiet)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
