"""
HRR Feature Extraction - Database Persistence

Database operations for loading HR samples and saving recovery intervals.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from .types import HRSample, RecoveryInterval

# Load environment
load_dotenv(Path(__file__).parent.parent.parent / '.env')

logger = logging.getLogger(__name__)


# =============================================================================
# Database Connection
# =============================================================================

def get_db_connection():
    """Get connection to arnold_analytics database."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'arnold_analytics'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '')
    )


# =============================================================================
# Data Loading
# =============================================================================

def get_hr_samples(conn, session_id: int, source: str = 'polar') -> List[HRSample]:
    """Fetch HR samples for a session from unified hr_samples table."""

    # hr_samples schema: id, session_id, sample_time, hr_value, source, endurance_session_id
    if source == 'polar':
        query = """
            SELECT sample_time, hr_value
            FROM hr_samples
            WHERE session_id = %s
            ORDER BY sample_time
        """
    elif source == 'endurance':
        query = """
            SELECT sample_time, hr_value
            FROM hr_samples
            WHERE endurance_session_id = %s
            ORDER BY sample_time
        """
    else:
        raise ValueError(f"Unknown source: {source}")

    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()

    return [HRSample(timestamp=row[0], hr_value=row[1]) for row in rows]


def get_resting_hr(conn, session_date: datetime) -> Optional[int]:
    """Get resting HR for the session date from biometric_readings (EAV table)."""
    query = """
        SELECT value
        FROM biometric_readings
        WHERE reading_date = %s::date
          AND metric_type = 'resting_hr'
        ORDER BY imported_at DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_date,))
        row = cur.fetchone()
    return int(row[0]) if row else None


# =============================================================================
# Data Saving
# =============================================================================

def save_intervals(conn, intervals: List[RecoveryInterval], session_id: int, source: str = 'polar'):
    """Save detected intervals to database.

    Column names match migration 013 + 017 schema exactly.
    """

    if not intervals:
        logger.info("No intervals to save")
        return

    # Delete existing intervals for this session
    delete_query = """
        DELETE FROM hr_recovery_intervals
        WHERE polar_session_id = %s
    """ if source == 'polar' else """
        DELETE FROM hr_recovery_intervals
        WHERE endurance_session_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(delete_query, (session_id,))
        deleted = cur.rowcount
        if deleted:
            logger.info(f"Deleted {deleted} existing intervals")

    # Insert new intervals - column names match DB schema exactly
    columns = [
        'polar_session_id' if source == 'polar' else 'endurance_session_id',
        'interval_order', 'start_time', 'end_time', 'duration_seconds',
        # HR values
        'hr_peak', 'hr_30s', 'hr_60s', 'hr_90s', 'hr_120s',
        'hr_180s', 'hr_240s', 'hr_300s', 'hr_nadir', 'rhr_baseline',
        # Absolute HRR
        'hrr30_abs', 'hrr60_abs', 'hrr90_abs', 'hrr120_abs',
        'hrr180_abs', 'hrr240_abs', 'hrr300_abs', 'total_drop',
        # Normalized HRR
        'hr_reserve', 'recovery_ratio', 'peak_pct_max',
        # Decay model
        'tau_seconds', 'tau_fit_r2', 'fit_amplitude', 'fit_asymptote',
        # Segment R² values
        'r2_0_30', 'r2_15_45', 'r2_30_60', 'r2_0_60', 'r2_30_90', 'r2_0_90',
        'r2_0_120', 'r2_0_180', 'r2_0_240', 'r2_0_300', 'r2_delta',
        # Nadir and slopes
        'nadir_time_sec', 'slope_90_120', 'slope_90_120_r2',
        'decline_slope_30s', 'decline_slope_60s', 'time_to_50pct_sec', 'auc_60s',
        # Pre-peak context
        'sustained_effort_sec', 'effort_avg_hr', 'session_elapsed_min',
        # Quality
        'quality_status', 'quality_flags', 'auto_reject_reason',
        'review_priority', 'needs_review', 'is_clean', 'is_low_signal',
        'sample_count', 'expected_sample_count', 'sample_completeness',
        # Onset
        'onset_delay_sec', 'onset_confidence',
        # Context
        'peak_label'
    ]

    values = []
    for interval in intervals:
        values.append((
            session_id,
            interval.interval_order, interval.start_time, interval.end_time, interval.duration_seconds,
            # HR values
            interval.hr_peak, interval.hr_30s, interval.hr_60s, interval.hr_90s, interval.hr_120s,
            interval.hr_180s, interval.hr_240s, interval.hr_300s, interval.hr_nadir, interval.rhr_baseline,
            # Absolute HRR
            interval.hrr30_abs, interval.hrr60_abs, interval.hrr90_abs, interval.hrr120_abs,
            interval.hrr180_abs, interval.hrr240_abs, interval.hrr300_abs, interval.total_drop,
            # Normalized HRR
            interval.hr_reserve, interval.recovery_ratio, interval.peak_pct_max,
            # Decay model
            interval.tau_seconds, interval.tau_fit_r2, interval.fit_amplitude, interval.fit_asymptote,
            # Segment R²
            interval.r2_0_30, interval.r2_15_45, interval.r2_30_60, interval.r2_0_60, interval.r2_30_90, interval.r2_0_90,
            interval.r2_0_120, interval.r2_0_180, interval.r2_0_240, interval.r2_0_300, interval.r2_delta,
            # Nadir and slopes
            interval.nadir_time_sec, interval.slope_90_120, interval.slope_90_120_r2,
            interval.decline_slope_30s, interval.decline_slope_60s, interval.time_to_50pct_sec, interval.auc_60s,
            # Pre-peak context
            interval.sustained_effort_sec, interval.effort_avg_hr, interval.session_elapsed_min,
            # Quality
            interval.quality_status, interval.quality_flags, interval.auto_reject_reason,
            interval.review_priority, interval.needs_review, interval.is_clean, interval.is_low_signal,
            interval.sample_count, interval.expected_sample_count, interval.sample_completeness,
            # Onset
            interval.onset_delay_sec, interval.onset_confidence,
            # Context
            interval.peak_label
        ))

    insert_query = f"""
        INSERT INTO hr_recovery_intervals ({', '.join(columns)})
        VALUES %s
    """

    # Convert quality_flags list to pipe-delimited string for storage
    # Find the index of quality_flags in columns
    quality_flags_idx = columns.index('quality_flags')

    # Convert numpy types to Python native types
    def convert_numpy(val):
        if val is None:
            return None
        if hasattr(val, 'item'):  # numpy scalar
            return val.item()
        return val

    converted_values = []
    for v in values:
        v_list = [convert_numpy(x) for x in v]
        if v_list[quality_flags_idx] and isinstance(v_list[quality_flags_idx], list):
            # Convert to postgres array format: {val1,val2}
            v_list[quality_flags_idx] = '{' + ','.join(v_list[quality_flags_idx]) + '}' if v_list[quality_flags_idx] else None
        elif v_list[quality_flags_idx] and isinstance(v_list[quality_flags_idx], str):
            # Already a string but not array format
            v_list[quality_flags_idx] = '{' + v_list[quality_flags_idx] + '}'
        converted_values.append(tuple(v_list))

    with conn.cursor() as cur:
        execute_values(cur, insert_query, converted_values)
        logger.info(f"Saved {len(intervals)} intervals")

    conn.commit()


# =============================================================================
# Peak Adjustments
# =============================================================================

def get_peak_adjustments(conn, session_id: int, source: str = 'polar') -> Dict[int, int]:
    """
    Load manual peak adjustments from database.

    Returns dict mapping interval_order -> shift_seconds.
    Positive shift = move peak later (right) in time.
    """
    if source == 'polar':
        query = """
            SELECT interval_order, shift_seconds
            FROM peak_adjustments
            WHERE polar_session_id = %s
        """
    else:
        query = """
            SELECT interval_order, shift_seconds
            FROM peak_adjustments
            WHERE endurance_session_id = %s
        """

    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()

    return {row[0]: row[1] for row in rows}


def mark_adjustments_applied(conn, session_id: int, source: str = 'polar'):
    """Mark peak adjustments as applied."""
    if source == 'polar':
        query = """
            UPDATE peak_adjustments
            SET applied_at = NOW()
            WHERE polar_session_id = %s
        """
    else:
        query = """
            UPDATE peak_adjustments
            SET applied_at = NOW()
            WHERE endurance_session_id = %s
        """

    with conn.cursor() as cur:
        cur.execute(query, (session_id,))


# =============================================================================
# Quality Overrides
# =============================================================================

def get_quality_overrides(conn, session_id: int, source: str = 'polar') -> Dict[int, Dict[str, Any]]:
    """
    Load human quality overrides from database.

    Returns dict mapping interval_order -> {override_action, reason}.
    These override the automated quality assessment.

    override_action values:
    - 'force_pass': Accept interval despite auto-reject
    - 'force_reject': Reject interval despite auto-pass
    """
    if source == 'polar':
        query = """
            SELECT interval_order, override_action, reason
            FROM hrr_quality_overrides
            WHERE polar_session_id = %s
        """
    else:
        query = """
            SELECT interval_order, override_action, reason
            FROM hrr_quality_overrides
            WHERE endurance_session_id = %s
        """

    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()

    return {
        row[0]: {'override_action': row[1], 'reason': row[2]}
        for row in rows
    }


def mark_overrides_applied(conn, session_id: int, source: str = 'polar'):
    """Mark quality overrides as applied."""
    if source == 'polar':
        query = """
            UPDATE hrr_quality_overrides
            SET applied_at = NOW()
            WHERE polar_session_id = %s
        """
    else:
        query = """
            UPDATE hrr_quality_overrides
            SET applied_at = NOW()
            WHERE endurance_session_id = %s
        """

    with conn.cursor() as cur:
        cur.execute(query, (session_id,))


def apply_quality_overrides(
    intervals: List[RecoveryInterval],
    overrides: Dict[int, Dict[str, Any]]
) -> List[RecoveryInterval]:
    """
    Apply human quality overrides to intervals.

    This runs AFTER assess_quality() and overrides the automated decisions.
    Adds HUMAN_OVERRIDE flag to indicate the interval was manually reviewed.
    """
    if not overrides:
        return intervals

    for interval in intervals:
        if interval.interval_order in overrides:
            override = overrides[interval.interval_order]
            action = override['override_action']
            reason = override.get('reason', 'Human reviewed')

            if action == 'force_pass':
                # Override rejection -> pass
                logger.info(
                    f"Applying override: interval {interval.interval_order} "
                    f"force_pass (was: {interval.quality_status}, reason: {interval.auto_reject_reason})"
                )
                interval.quality_status = 'pass'
                interval.auto_reject_reason = None
                interval.needs_review = False
                interval.review_priority = 3
                if 'HUMAN_OVERRIDE' not in interval.quality_flags:
                    interval.quality_flags.append('HUMAN_OVERRIDE')

            elif action == 'force_reject':
                # Override pass -> rejected
                logger.info(
                    f"Applying override: interval {interval.interval_order} "
                    f"force_reject (was: {interval.quality_status})"
                )
                interval.quality_status = 'rejected'
                interval.auto_reject_reason = f'human_override: {reason}'
                interval.needs_review = False
                interval.review_priority = 0
                if 'HUMAN_OVERRIDE' not in interval.quality_flags:
                    interval.quality_flags.append('HUMAN_OVERRIDE')

    return intervals
