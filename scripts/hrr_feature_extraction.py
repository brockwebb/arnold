#!/usr/bin/env python3
from __future__ import annotations
"""
HRR Feature Extraction Pipeline

Detects recovery intervals from per-second HR streams and computes
comprehensive HRR features for FR-004.

Usage:
    python scripts/hrr_feature_extraction.py --session-id 1 --source endurance
    python scripts/hrr_feature_extraction.py --all --dry-run
    python scripts/hrr_feature_extraction.py --all
"""

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
import numpy as np
from scipy import signal
from scipy.optimize import curve_fit
import psycopg2
from psycopg2.extras import execute_values
import os
from pathlib import Path
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


# =============================================================================
# Configuration
# =============================================================================

def load_config_yaml() -> Dict[str, Any]:
    """Load configuration from YAML file, return empty dict if not found."""
    config_path = Path(__file__).parent.parent / 'config' / 'hrr_extraction.yaml'
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


@dataclass
class HRRConfig:
    """Configuration for HRR detection and feature extraction.
    
    Loads from config/hrr_extraction.yaml if available, else uses defaults.
    """
    
    # Peak detection
    min_elevation_bpm: int = 25  # Peak must be this far above RHR to count
    min_sustained_effort_sec: int = 20  # Must be elevated for this long before peak
    peak_prominence: int = 10  # scipy.signal.find_peaks prominence
    peak_distance_sec: int = 5  # Minimum seconds between peaks (permissive)
    
    # Recovery interval
    min_decline_duration_sec: int = 30  # Minimum recovery duration to record
    max_interval_duration_sec: int = 300  # Cap at 5 minutes
    decline_tolerance_bpm: int = 3  # Allow small rises within this range
    
    # Quality thresholds
    low_signal_threshold_bpm: int = 25  # hr_reserve below this = low_signal
    min_sample_completeness: float = 0.8  # Require 80% of expected samples
    min_hrr60_abs: int = 5  # Minimum absolute drop to count as real recovery
    min_recovery_ratio: float = 0.10  # At least 10% of available drop
    
    # Tau fitting
    tau_min_points: int = 20  # Need at least this many points for fit
    tau_max_seconds: float = 300.0  # Cap tau at 5 minutes
    tau_min_r2: float = 0.5  # Minimum R² to trust the fit
    
    # Delayed onset detection (catch-breath phase)
    onset_min_slope: float = -0.15  # bpm/sec - sustained decline threshold
    onset_min_consecutive: int = 5  # consecutive seconds meeting slope threshold
    onset_max_delay: int = 45  # max seconds for max-HR method
    
    # Estimated max HR (can be overridden per-athlete)
    default_max_hr: int = 180  # Conservative default
    
    # Valley detection (Issue #020)
    valley_lookback_sec: int = 120  # How far back to search for peak before valley
    valley_min_drop_bpm: int = 12   # Minimum HR drop from peak to valley
    valley_prominence: int = 10     # Prominence for finding valleys
    valley_distance_sec: int = 60   # Minimum seconds between valleys
    valley_local_peak_prominence: int = 5   # Prominence for local peaks in lookback
    valley_local_peak_distance: int = 10    # Distance between local peaks
    
    # Gate thresholds (from YAML)
    gate_r2_0_30_threshold: float = 0.5   # double_peak detection
    gate_r2_30_60_threshold: float = 0.75
    gate_r2_30_90_threshold: float = 0.75
    gate_best_r2_threshold: float = 0.75
    gate_slope_90_120_threshold: float = 0.1
    
    # Flag configuration (from YAML)
    flags_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls) -> 'HRRConfig':
        """Load config from YAML file."""
        yaml_config = load_config_yaml()
        
        kwargs = {}
        
        # Peak detection
        if 'peak_detection' in yaml_config:
            pd = yaml_config['peak_detection']
            kwargs['min_elevation_bpm'] = pd.get('min_elevation_bpm', 25)
            kwargs['min_sustained_effort_sec'] = pd.get('min_sustained_effort_sec', 20)
            kwargs['peak_prominence'] = pd.get('peak_prominence', 10)
            kwargs['peak_distance_sec'] = pd.get('peak_distance_sec', 5)
        
        # Recovery interval
        if 'recovery_interval' in yaml_config:
            ri = yaml_config['recovery_interval']
            kwargs['min_decline_duration_sec'] = ri.get('min_decline_duration_sec', 30)
            kwargs['max_interval_duration_sec'] = ri.get('max_interval_duration_sec', 300)
            kwargs['decline_tolerance_bpm'] = ri.get('decline_tolerance_bpm', 3)
        
        # Quality thresholds
        if 'quality' in yaml_config:
            q = yaml_config['quality']
            kwargs['low_signal_threshold_bpm'] = q.get('low_signal_threshold_bpm', 25)
            kwargs['min_sample_completeness'] = q.get('min_sample_completeness', 0.8)
            kwargs['min_hrr60_abs'] = q.get('min_hrr60_abs', 5)
            kwargs['min_recovery_ratio'] = q.get('min_recovery_ratio', 0.10)
        
        # Tau fitting
        if 'tau_fitting' in yaml_config:
            tf = yaml_config['tau_fitting']
            kwargs['tau_min_points'] = tf.get('tau_min_points', 20)
            kwargs['tau_max_seconds'] = tf.get('tau_max_seconds', 300.0)
            kwargs['tau_min_r2'] = tf.get('tau_min_r2', 0.5)
        
        # Onset detection
        if 'onset_detection' in yaml_config:
            od = yaml_config['onset_detection']
            kwargs['onset_min_slope'] = od.get('onset_min_slope', -0.15)
            kwargs['onset_min_consecutive'] = od.get('onset_min_consecutive', 5)
            kwargs['onset_max_delay'] = od.get('onset_max_delay', 45)
        
        # Athlete defaults
        if 'athlete_defaults' in yaml_config:
            ad = yaml_config['athlete_defaults']
            kwargs['default_max_hr'] = ad.get('default_max_hr', 180)
        
        # Valley detection (Issue #020)
        if 'valley_detection' in yaml_config:
            vd = yaml_config['valley_detection']
            kwargs['valley_lookback_sec'] = vd.get('lookback_window_sec', 120)
            kwargs['valley_min_drop_bpm'] = vd.get('min_drop_bpm', 12)
            kwargs['valley_prominence'] = vd.get('valley_prominence', 10)
            kwargs['valley_distance_sec'] = vd.get('valley_distance_sec', 60)
            kwargs['valley_local_peak_prominence'] = vd.get('local_peak_prominence', 5)
            kwargs['valley_local_peak_distance'] = vd.get('local_peak_distance_sec', 10)
        
        # Gate thresholds
        if 'gates' in yaml_config:
            gates = yaml_config['gates']
            if 'double_peak' in gates:
                kwargs['gate_r2_0_30_threshold'] = gates['double_peak'].get('threshold', 0.5)
            if 'r2_30_60' in gates:
                kwargs['gate_r2_30_60_threshold'] = gates['r2_30_60'].get('threshold', 0.75)
            if 'r2_30_90' in gates:
                kwargs['gate_r2_30_90_threshold'] = gates['r2_30_90'].get('threshold', 0.75)
            if 'poor_fit' in gates:
                kwargs['gate_best_r2_threshold'] = gates['poor_fit'].get('threshold', 0.75)
            if 'activity_resumed' in gates:
                kwargs['gate_slope_90_120_threshold'] = gates['activity_resumed'].get('threshold', 0.1)
        
        # Flag configuration
        kwargs['flags_config'] = yaml_config.get('flags', {})
        
        return cls(**kwargs)
    
    def is_flag_enabled(self, flag_name: str) -> bool:
        """Check if a flag is enabled in config."""
        if flag_name in self.flags_config:
            return self.flags_config[flag_name].get('enabled', True)
        return True  # Default to enabled
    
    def flag_triggers_review(self, flag_name: str) -> bool:
        """Check if a flag should trigger human review."""
        if flag_name in self.flags_config:
            return self.flags_config[flag_name].get('triggers_review', True)
        return True  # Default to triggering review
    

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class HRSample:
    """Single HR sample."""
    timestamp: datetime
    hr_value: int


@dataclass
class RecoveryInterval:
    """Detected recovery interval with computed features.
    
    Field names match database schema (migration 013 + 017).
    Canonical naming: hr_Xs for HR at time X, hrrX_abs for absolute drop,
    hrrX_frac for fraction of available drop (0-1 scale).
    """
    
    # Timing
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    interval_order: int
    
    # Raw HR values (DB: hr_30s, hr_60s, etc.)
    hr_peak: int
    hr_nadir: int
    hr_30s: Optional[int] = None
    hr_60s: Optional[int] = None
    hr_90s: Optional[int] = None
    hr_120s: Optional[int] = None
    hr_180s: Optional[int] = None
    hr_240s: Optional[int] = None
    hr_300s: Optional[int] = None
    rhr_baseline: Optional[int] = None  # Morning RHR for that day
    hr_reserve: Optional[int] = None  # peak - rhr_baseline
    
    # HRR metrics - absolute drops (DB: hrr30_abs, hrr60_abs, etc.)
    hrr30_abs: Optional[int] = None
    hrr60_abs: Optional[int] = None
    hrr90_abs: Optional[int] = None
    hrr120_abs: Optional[int] = None
    hrr180_abs: Optional[int] = None
    hrr240_abs: Optional[int] = None
    hrr300_abs: Optional[int] = None
    total_drop: Optional[int] = None  # peak - nadir
    
    # Normalized HRR - fraction of available drop (DB: hrr30_frac, etc.)
    # Scale: 0.0 to 1.0 (NOT percentage)
    hrr30_frac: Optional[float] = None
    hrr60_frac: Optional[float] = None
    hrr90_frac: Optional[float] = None
    hrr120_frac: Optional[float] = None
    recovery_ratio: Optional[float] = None  # total_drop / hr_reserve
    peak_pct_max: Optional[float] = None  # peak / estimated_max_hr
    
    # Exponential decay model: HR(t) = asymptote + amplitude * exp(-t/tau)
    tau_seconds: Optional[float] = None
    tau_fit_r2: Optional[float] = None
    fit_amplitude: Optional[float] = None  # DB: fit_amplitude (was tau_amplitude)
    fit_asymptote: Optional[float] = None  # DB: fit_asymptote (was tau_baseline)
    
    # Segment R² values (for window-specific quality)
    r2_0_30: Optional[float] = None   # First 30s segment
    r2_30_60: Optional[float] = None  # Second 30s segment - CRITICAL for HRR60 quality
    r2_0_60: Optional[float] = None   # Validates HRR60
    r2_30_90: Optional[float] = None  # Transition zone
    r2_0_90: Optional[float] = None   # Validates HRR90
    r2_0_120: Optional[float] = None  # Validates HRR120
    r2_0_180: Optional[float] = None  # Validates HRR180
    r2_0_240: Optional[float] = None  # Validates HRR240
    r2_0_300: Optional[float] = None  # Validates HRR300
    r2_detected: Optional[float] = None  # R² for actual detected window
    r2_delta: Optional[float] = None  # r2_0_30 - r2_30_60 (disruption indicator)
    
    # Nadir analysis
    nadir_time_sec: Optional[int] = None  # Time from peak to nadir
    
    # Late slope (activity resumption detection)
    slope_90_120: Optional[float] = None  # bpm/sec - positive = rising
    slope_90_120_r2: Optional[float] = None
    
    # Decay dynamics (from migration 013)
    decline_slope_30s: Optional[float] = None  # bpm/sec (negative)
    decline_slope_60s: Optional[float] = None
    time_to_50pct_sec: Optional[int] = None
    auc_60s: Optional[float] = None  # Area under curve, first 60s
    
    # Pre-peak context
    sustained_effort_sec: Optional[int] = None
    effort_avg_hr: Optional[int] = None
    session_elapsed_min: Optional[int] = None
    
    # Quality indicators
    quality_status: str = 'pending'  # pending, pass, flagged, rejected
    quality_flags: List[str] = field(default_factory=list)
    auto_reject_reason: Optional[str] = None  # Why it was rejected (if rejected)
    review_priority: int = 3  # 1=high, 2=medium, 3=low
    needs_review: bool = False
    is_clean: bool = True
    is_low_signal: bool = False
    sample_completeness: float = 1.0
    sample_count: Optional[int] = None
    expected_sample_count: Optional[int] = None
    
    # Onset detection
    onset_delay_sec: Optional[int] = None  # seconds from interval start to max HR
    onset_confidence: str = 'unknown'  # high, medium, low
    
    # Context
    peak_label: str = ''  # e.g., "S71:p1", "Peak 1"
    

# =============================================================================
# Database Operations
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
        # Normalized HRR (fractions 0-1)
        'hr_reserve', 'hrr30_frac', 'hrr60_frac', 'hrr90_frac', 'hrr120_frac',
        'recovery_ratio', 'peak_pct_max',
        # Decay model
        'tau_seconds', 'tau_fit_r2', 'fit_amplitude', 'fit_asymptote',
        # Segment R² values
        'r2_0_30', 'r2_30_60', 'r2_0_60', 'r2_30_90', 'r2_0_90',
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
            interval.hr_reserve, interval.hrr30_frac, interval.hrr60_frac, interval.hrr90_frac, interval.hrr120_frac,
            interval.recovery_ratio, interval.peak_pct_max,
            # Decay model
            interval.tau_seconds, interval.tau_fit_r2, interval.fit_amplitude, interval.fit_asymptote,
            # Segment R²
            interval.r2_0_30, interval.r2_30_60, interval.r2_0_60, interval.r2_30_90, interval.r2_0_90,
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


# =============================================================================
# Peak Detection
# =============================================================================

def detect_peaks(samples: List[HRSample], config: HRRConfig) -> List[int]:
    """
    Detect HR peaks using scipy.signal.find_peaks.
    Returns indices of peak samples.
    """
    if len(samples) < config.min_sustained_effort_sec:
        return []
    
    hr_values = np.array([s.hr_value for s in samples])
    
    # Smooth the signal slightly to reduce noise
    if len(hr_values) > 5:
        kernel_size = 5
        kernel = np.ones(kernel_size) / kernel_size
        hr_smoothed = np.convolve(hr_values, kernel, mode='same')
    else:
        hr_smoothed = hr_values
    
    # Find peaks with prominence requirement
    peaks, properties = signal.find_peaks(
        hr_smoothed,
        prominence=config.peak_prominence,
        distance=config.peak_distance_sec  # Permissive - let quality gates filter
    )
    
    return peaks.tolist()


def validate_peak(samples: List[HRSample], peak_idx: int, resting_hr: int, config: HRRConfig) -> bool:
    """
    Validate that a peak represents genuine elevated effort.
    """
    if peak_idx >= len(samples):
        return False
    
    peak_hr = samples[peak_idx].hr_value
    elevation = peak_hr - resting_hr
    
    # Must be sufficiently elevated above resting
    if elevation < config.min_elevation_bpm:
        return False
    
    # Check for sustained effort before peak
    if peak_idx < config.min_sustained_effort_sec:
        return False
    
    # Verify HR was elevated for minimum duration before peak
    pre_peak_samples = samples[max(0, peak_idx - config.min_sustained_effort_sec):peak_idx]
    elevated_count = sum(1 for s in pre_peak_samples if s.hr_value > resting_hr + 15)
    
    if elevated_count < config.min_sustained_effort_sec * 0.7:  # 70% must be elevated
        return False
    
    return True


# =============================================================================
# Valley-Based Peak Discovery (Issue #020)
# =============================================================================

def detect_valley_peaks(samples: List[HRSample], resting_hr: int, config: HRRConfig) -> List[int]:
    """
    Discover recovery intervals by finding valleys (local minima) in HR,
    then looking back to find the corresponding peak.
    
    This complements scipy peak detection by catching plateau-to-decline
    patterns that lack prominence but represent real recoveries.
    
    Returns list of peak indices (to feed into same pipeline as detect_peaks).
    """
    if len(samples) < 120:  # Need enough data for meaningful valleys
        return []
    
    hr_values = np.array([s.hr_value for s in samples])
    
    # Smooth to reduce noise
    kernel = np.ones(5) / 5
    hr_smooth = np.convolve(hr_values, kernel, mode='same')
    
    # Find valleys (invert signal, find peaks)
    valleys, _ = signal.find_peaks(
        -hr_smooth, 
        prominence=config.valley_prominence, 
        distance=config.valley_distance_sec
    )
    
    peak_indices = []
    
    for valley_idx in valleys:
        valley_hr = hr_values[valley_idx]
        
        # Look back to find the MOST RECENT peak before this valley
        # (Not absolute max - that finds older, irrelevant peaks)
        lookback = min(valley_idx, config.valley_lookback_sec)
        search_start = valley_idx - lookback
        search_window = hr_smooth[search_start:valley_idx]
        
        if len(search_window) < 30:
            continue
        
        # Find local peaks in the search window
        local_peaks, _ = signal.find_peaks(
            search_window, 
            prominence=config.valley_local_peak_prominence, 
            distance=config.valley_local_peak_distance
        )
        
        if len(local_peaks) == 0:
            # No prominent peaks - fall back to simple max
            local_max_idx = np.argmax(search_window)
            max_idx = search_start + local_max_idx
        else:
            # Use the LAST (most recent) local peak before the valley
            last_peak = local_peaks[-1]
            max_idx = search_start + last_peak
        
        max_hr = hr_values[max_idx]
        drop = max_hr - valley_hr
        
        # Validate: must be elevated and have real drop
        if max_hr < resting_hr + config.min_elevation_bpm:
            continue
        if drop < config.valley_min_drop_bpm:
            continue
        
        peak_indices.append(max_idx)
    
    return peak_indices


def merge_peak_candidates(
    peak_detected: List[int],
    valley_detected: List[int],
    samples: List[HRSample],
    config: HRRConfig
) -> List[int]:
    """
    Merge peak-detected and valley-detected candidates.
    
    Rules:
    1. Peak detection takes priority (proven method)
    2. Valley candidates are added only if not near existing peak
    3. Final list is sorted by time
    4. Measurement window constraint enforced in extract_features loop
    """
    # Start with peak-detected (priority)
    all_candidates = set(peak_detected)
    
    # Add valley-detected if not within 30s of any peak-detected
    for valley_peak in valley_detected:
        is_duplicate = False
        for peak in peak_detected:
            if abs(valley_peak - peak) <= 30:
                is_duplicate = True
                break
        if not is_duplicate:
            all_candidates.add(valley_peak)
    
    # Sort by time
    return sorted(all_candidates)


# =============================================================================
# Recovery Interval Detection
# =============================================================================

def find_recovery_end(samples: List[HRSample], start_idx: int, config: HRRConfig) -> Optional[int]:
    """
    Find the end of a recovery interval starting from a peak.
    Returns the index where recovery ends (either plateau, rise, or max duration).
    """
    if start_idx >= len(samples) - 1:
        return None
    
    peak_hr = samples[start_idx].hr_value
    current_min = peak_hr
    consecutive_rises = 0
    
    for i in range(start_idx + 1, min(start_idx + config.max_interval_duration_sec + 1, len(samples))):
        hr = samples[i].hr_value
        
        if hr < current_min:
            current_min = hr
            consecutive_rises = 0
        elif hr > current_min + config.decline_tolerance_bpm:
            consecutive_rises += 1
            if consecutive_rises >= 5:  # 5 consecutive seconds of rising
                return i - 5  # Return point before rise started
        else:
            consecutive_rises = 0
    
    # Reached max duration or end of samples
    end_idx = min(start_idx + config.max_interval_duration_sec, len(samples) - 1)
    
    # Ensure minimum duration
    if end_idx - start_idx < config.min_decline_duration_sec:
        return None
    
    return end_idx


def detect_onset_maxhr(samples: List[HRSample], start_idx: int, end_idx: int, config: HRRConfig) -> Tuple[int, int]:
    """
    Detect recovery onset using max HR method.
    Returns (onset_delay_seconds, max_hr_index).
    """
    if end_idx <= start_idx:
        return 0, start_idx
    
    interval_samples = samples[start_idx:end_idx + 1]
    hr_values = [s.hr_value for s in interval_samples]
    
    # Find max HR within the interval (may not be at start due to catch-breath)
    # Use LAST occurrence of max to find end of plateau (Issue #015)
    # np.argmax returns first occurrence, but we want end of flat/rising section
    max_hr = max(hr_values)
    max_indices = [i for i, hr in enumerate(hr_values) if hr == max_hr]
    max_hr_idx = max_indices[-1] if max_indices else 0
    onset_delay = max_hr_idx  # seconds from interval start
    
    # Cap the delay
    if onset_delay > config.onset_max_delay:
        onset_delay = 0
        max_hr_idx = 0
    
    return onset_delay, start_idx + max_hr_idx


def detect_onset_slope(samples: List[HRSample], start_idx: int, end_idx: int, config: HRRConfig) -> Tuple[int, str]:
    """
    Detect recovery onset using slope method.
    Returns (onset_delay_seconds, confidence).
    """
    if end_idx <= start_idx:
        return 0, 'low'
    
    interval_samples = samples[start_idx:end_idx + 1]
    hr_values = np.array([s.hr_value for s in interval_samples])
    
    # Calculate rolling slope (5-second window)
    window = 5
    if len(hr_values) < window + config.onset_min_consecutive:
        return 0, 'low'
    
    slopes = []
    for i in range(len(hr_values) - window):
        slope = (hr_values[i + window] - hr_values[i]) / window
        slopes.append(slope)
    
    # Find first point of sustained decline
    consecutive_decline = 0
    onset_idx = 0
    
    for i, slope in enumerate(slopes):
        if slope <= config.onset_min_slope:
            consecutive_decline += 1
            if consecutive_decline >= config.onset_min_consecutive:
                onset_idx = max(0, i - config.onset_min_consecutive + 1)
                break
        else:
            consecutive_decline = 0
    
    # Determine confidence
    if consecutive_decline >= config.onset_min_consecutive * 2:
        confidence = 'high'
    elif consecutive_decline >= config.onset_min_consecutive:
        confidence = 'medium'
    else:
        confidence = 'low'
    
    return onset_idx, confidence


def create_recovery_interval(
    samples: List[HRSample],
    start_idx: int,
    end_idx: int,
    interval_order: int,
    resting_hr: int,
    config: HRRConfig
) -> Optional[RecoveryInterval]:
    """
    Create a RecoveryInterval from detected peak to end.
    """
    if end_idx <= start_idx:
        return None
    
    interval_samples = samples[start_idx:end_idx + 1]
    duration = end_idx - start_idx
    
    if duration < config.min_decline_duration_sec:
        return None
    
    # Detect onset using both methods
    onset_maxhr, max_hr_idx = detect_onset_maxhr(samples, start_idx, end_idx, config)
    onset_slope, slope_confidence = detect_onset_slope(samples, start_idx, end_idx, config)
    
    # Use max HR onset as primary (more reliable for catch-breath detection)
    effective_start_idx = max_hr_idx
    effective_samples = samples[effective_start_idx:end_idx + 1]
    
    if len(effective_samples) < config.min_decline_duration_sec:
        effective_start_idx = start_idx
        effective_samples = interval_samples
    
    hr_values = [s.hr_value for s in effective_samples]
    hr_peak = max(hr_values)
    hr_nadir = min(hr_values)
    
    # Find nadir time
    nadir_idx = hr_values.index(hr_nadir)
    nadir_time_sec = nadir_idx
    
    # Calculate HR at specific times (from effective start) - canonical naming hr_Xs
    hr_30s = hr_values[30] if len(hr_values) > 30 else None
    hr_60s = hr_values[60] if len(hr_values) > 60 else None
    hr_90s = hr_values[90] if len(hr_values) > 90 else None
    hr_120s = hr_values[120] if len(hr_values) > 120 else None
    hr_180s = hr_values[180] if len(hr_values) > 180 else None
    hr_240s = hr_values[240] if len(hr_values) > 240 else None
    hr_300s = hr_values[300] if len(hr_values) > 300 else None
    
    # Calculate HRR values - absolute drops (canonical: hrrX_abs)
    hrr30_abs = hr_peak - hr_30s if hr_30s else None
    hrr60_abs = hr_peak - hr_60s if hr_60s else None
    hrr90_abs = hr_peak - hr_90s if hr_90s else None
    hrr120_abs = hr_peak - hr_120s if hr_120s else None
    hrr180_abs = hr_peak - hr_180s if hr_180s else None
    hrr240_abs = hr_peak - hr_240s if hr_240s else None
    hrr300_abs = hr_peak - hr_300s if hr_300s else None
    total_drop = hr_peak - hr_nadir
    
    # HR reserve (peak - resting)
    hr_reserve = hr_peak - resting_hr
    
    # Calculate normalized HRR - fractions 0-1 (canonical: hrrX_frac)
    hrr30_frac = (hrr30_abs / hr_reserve) if hrr30_abs and hr_reserve > 0 else None
    hrr60_frac = (hrr60_abs / hr_reserve) if hrr60_abs and hr_reserve > 0 else None
    hrr90_frac = (hrr90_abs / hr_reserve) if hrr90_abs and hr_reserve > 0 else None
    hrr120_frac = (hrr120_abs / hr_reserve) if hrr120_abs and hr_reserve > 0 else None
    recovery_ratio = (total_drop / hr_reserve) if total_drop and hr_reserve > 0 else None
    peak_pct_max = hr_peak / config.default_max_hr if hr_peak else None
    
    # Determine onset confidence
    if abs(onset_maxhr - onset_slope) <= 5:
        onset_confidence = 'high'
    elif abs(onset_maxhr - onset_slope) <= 15:
        onset_confidence = 'medium'
    else:
        onset_confidence = 'low'
    
    # Check for low signal
    is_low_signal = hr_reserve < config.low_signal_threshold_bpm
    
    # Sample counts
    sample_count = len(effective_samples)
    expected_sample_count = len(effective_samples)  # 1Hz = 1 sample per second expected
    
    interval = RecoveryInterval(
        start_time=effective_samples[0].timestamp,
        end_time=effective_samples[-1].timestamp,
        duration_seconds=len(effective_samples) - 1,
        interval_order=interval_order,
        hr_peak=hr_peak,
        hr_nadir=hr_nadir,
        hr_30s=hr_30s,
        hr_60s=hr_60s,
        hr_90s=hr_90s,
        hr_120s=hr_120s,
        hr_180s=hr_180s,
        hr_240s=hr_240s,
        hr_300s=hr_300s,
        rhr_baseline=resting_hr,
        hr_reserve=hr_reserve,
        hrr30_abs=hrr30_abs,
        hrr60_abs=hrr60_abs,
        hrr90_abs=hrr90_abs,
        hrr120_abs=hrr120_abs,
        hrr180_abs=hrr180_abs,
        hrr240_abs=hrr240_abs,
        hrr300_abs=hrr300_abs,
        total_drop=total_drop,
        hrr30_frac=hrr30_frac,
        hrr60_frac=hrr60_frac,
        hrr90_frac=hrr90_frac,
        hrr120_frac=hrr120_frac,
        recovery_ratio=recovery_ratio,
        peak_pct_max=peak_pct_max,
        nadir_time_sec=nadir_time_sec,
        onset_delay_sec=onset_maxhr,
        onset_confidence=onset_confidence,
        is_low_signal=is_low_signal,
        sample_count=sample_count,
        expected_sample_count=expected_sample_count,
        peak_label=f"Peak {interval_order}"
    )
    
    return interval


# =============================================================================
# Exponential Decay Fitting
# =============================================================================

def exp_decay(t, baseline, amplitude, tau):
    """Exponential decay model: HR(t) = baseline + amplitude * exp(-t/tau)"""
    return baseline + amplitude * np.exp(-t / tau)


def fit_exponential_decay(
    samples: List[HRSample],
    interval: RecoveryInterval,
    config: HRRConfig
) -> RecoveryInterval:
    """
    Fit exponential decay model to recovery interval.
    Updates interval with tau, R², and other fit parameters.
    """
    if interval.duration_seconds < config.tau_min_points:
        return interval
    
    # Get HR values as numpy array
    hr_values = np.array([s.hr_value for s in samples[:interval.duration_seconds + 1]])
    t = np.arange(len(hr_values))
    
    if len(hr_values) < config.tau_min_points:
        return interval
    
    # Initial parameter estimates
    amplitude_init = hr_values[0] - hr_values[-1]
    baseline_init = hr_values[-1]
    tau_init = interval.duration_seconds / 3  # Rough estimate
    
    try:
        # Fit the model
        popt, pcov = curve_fit(
            exp_decay,
            t,
            hr_values,
            p0=[baseline_init, amplitude_init, tau_init],
            bounds=(
                [0, 0, 1],  # Lower bounds
                [200, 100, config.tau_max_seconds]  # Upper bounds
            ),
            maxfev=5000
        )
        
        baseline, amplitude, tau = popt
        
        # Calculate R²
        predicted = exp_decay(t, baseline, amplitude, tau)
        ss_res = np.sum((hr_values - predicted) ** 2)
        ss_tot = np.sum((hr_values - np.mean(hr_values)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Update interval - canonical field names
        interval.tau_seconds = round(tau, 2)
        interval.tau_fit_r2 = round(r2, 4)
        interval.fit_amplitude = round(amplitude, 2)
        interval.fit_asymptote = round(baseline, 2)
        
    except (RuntimeError, ValueError) as e:
        logger.debug(f"Exponential fit failed: {e}")
        # Leave tau fields as None
    
    return interval


# =============================================================================
# Segment R² Computation
# =============================================================================

def compute_segment_r2(hr_values: np.ndarray, start_sec: int, end_sec: int) -> Optional[float]:
    """
    Compute R² for exponential fit on a specific time segment.
    
    Returns:
        R² value (0-1) if fit succeeds
        -1.0 if fit fails (triggers rejection via <0.75 check)
        None if insufficient data (no samples in window)
    """
    if end_sec > len(hr_values) or end_sec - start_sec < 10:
        return None
    
    segment = hr_values[start_sec:end_sec]
    t = np.arange(len(segment))
    
    if len(segment) < 10:
        return None
    
    # Initial estimates
    amplitude_init = segment[0] - segment[-1]
    baseline_init = segment[-1]
    tau_init = len(segment) / 3
    
    try:
        popt, _ = curve_fit(
            exp_decay,
            t,
            segment,
            p0=[baseline_init, amplitude_init, tau_init],
            bounds=([0, 0, 1], [200, 100, 300]),
            maxfev=2000
        )
        
        predicted = exp_decay(t, *popt)
        ss_res = np.sum((segment - predicted) ** 2)
        ss_tot = np.sum((segment - np.mean(segment)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return round(r2, 4)
        
    except (RuntimeError, ValueError):
        # Fit failed - no data
        return None


def compute_all_segment_r2(
    samples: List[HRSample],
    interval: RecoveryInterval
) -> RecoveryInterval:
    """
    Compute R² for all standard segments.
    
    Philosophy: compute all windows where data exists (≥10 samples).
    NULL = "no data", -1.0 = "skipped/failed", value = "computed".
    
    Early-exit: if a critical segment fails (r2 < 0.75), downstream
    segments are marked -1.0 (skipped) rather than computed.
    
    Key segments for quality validation:
    - r2_0_30 + r2_30_60 validate HRR60 measurement quality
    - r2_0_60 + r2_30_90 validate HRR90 quality  
    - r2_delta = r2_0_30 - r2_30_60 catches disrupted recovery (double-bounce)
    """
    hr_values = np.array([s.hr_value for s in samples[:interval.duration_seconds + 1]])
    
    # === First 30s - critical for detecting plateau/double-peak ===
    interval.r2_0_30 = compute_segment_r2(hr_values, 0, 30)
    
    # === 30-60s - CRITICAL for HRR60 quality ===
    interval.r2_30_60 = compute_segment_r2(hr_values, 30, 60)
    
    # === 0-60s - validates HRR60 ===
    interval.r2_0_60 = compute_segment_r2(hr_values, 0, 60)
    
    # Early exit check: if 30-60 is garbage, skip longer windows
    if interval.r2_30_60 is not None and interval.r2_30_60 < 0.75:
        # Mid-interval failed - longer windows are meaningless
        interval.r2_30_90 = None
        interval.r2_0_90 = None
        interval.r2_0_120 = None
        interval.r2_0_180 = None
        interval.r2_0_240 = None
        interval.r2_0_300 = None
        interval.r2_detected = compute_segment_r2(hr_values, 0, min(interval.duration_seconds, len(hr_values)))
        return interval
    
    # === 30-90s - transition zone, validates HRR90/120 ===
    interval.r2_30_90 = compute_segment_r2(hr_values, 30, 90)
    interval.r2_0_90 = compute_segment_r2(hr_values, 0, 90)
    
    # Early exit check: if 30-90 is garbage, skip even longer windows
    if interval.r2_30_90 is not None and interval.r2_30_90 < 0.75:
        interval.r2_0_120 = None
        interval.r2_0_180 = None
        interval.r2_0_240 = None
        interval.r2_0_300 = None
        interval.r2_detected = compute_segment_r2(hr_values, 0, min(interval.duration_seconds, len(hr_values)))
        return interval
    
    # === Longer windows ===
    interval.r2_0_120 = compute_segment_r2(hr_values, 0, 120)
    interval.r2_0_180 = compute_segment_r2(hr_values, 0, 180)
    interval.r2_0_240 = compute_segment_r2(hr_values, 0, 240)
    interval.r2_0_300 = compute_segment_r2(hr_values, 0, 300)
    
    # R² for detected window
    interval.r2_detected = compute_segment_r2(hr_values, 0, min(interval.duration_seconds, len(hr_values)))
    
    return interval


# =============================================================================
# Late Slope Analysis
# =============================================================================

def compute_late_slope(
    samples: List[HRSample],
    interval: RecoveryInterval,
    start_sec: int = 90,
    end_sec: int = 120
) -> RecoveryInterval:
    """
    Compute slope in the 90-120 second window to detect early activity resumption.
    Positive slope suggests the person started moving again.
    """
    if interval.duration_seconds < end_sec:
        return interval
    
    hr_values = np.array([s.hr_value for s in samples[start_sec:end_sec + 1]])
    t = np.arange(len(hr_values))
    
    if len(hr_values) < 10:
        return interval
    
    # Linear regression for slope
    try:
        coeffs = np.polyfit(t, hr_values, 1)
        slope = coeffs[0]  # bpm per second
        
        # R² for the linear fit
        predicted = np.polyval(coeffs, t)
        ss_res = np.sum((hr_values - predicted) ** 2)
        ss_tot = np.sum((hr_values - np.mean(hr_values)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        interval.slope_90_120 = round(slope, 4)
        interval.slope_90_120_r2 = round(r2, 4)
        
    except (np.linalg.LinAlgError, ValueError):
        pass
    
    return interval


# =============================================================================
# Plateau Detection (Issue #020 - double_peak re-anchoring)
# =============================================================================

def find_peak_by_slope(
    hr_values: np.ndarray,
    window: int = 5,
    threshold: float = -0.3,
    consecutive: int = 5
) -> Tuple[int, str]:
    """
    Method 1: Find where sustained negative slope begins.
    
    Slides through the HR values looking for the point where slope
    becomes consistently negative (true decline starts).
    
    Args:
        hr_values: Array of HR values from interval start
        window: Size of slope calculation window (seconds)
        threshold: Slope threshold in bpm/sec (negative = declining)
        consecutive: Number of consecutive windows that must meet threshold
    
    Returns:
        (offset, confidence): Offset in seconds to true peak, confidence level
    """
    if len(hr_values) < window + consecutive + 10:
        return 0, 'insufficient_data'
    
    # Scan through looking for sustained decline
    for i in range(len(hr_values) - window - consecutive):
        all_negative = True
        
        # Check if slope is negative for N consecutive windows
        for j in range(consecutive):
            if i + j + window >= len(hr_values):
                all_negative = False
                break
            slope = (hr_values[i + j + window] - hr_values[i + j]) / window
            if slope > threshold:  # Not steep enough or positive
                all_negative = False
                break
        
        if all_negative:
            # Found sustained decline - this is the true peak
            return i, 'slope_found'
    
    return 0, 'no_sustained_decline'


def find_peak_by_geometry(
    hr_values: np.ndarray,
    nadir_idx: int
) -> Tuple[int, str]:
    """
    Method 2: Binary search for inflection point using projected line.
    
    Uses the initial slope to project a line, then binary searches
    to find where the actual HR curve crosses this projection.
    That crossing point is the inflection (true peak).
    
    Args:
        hr_values: Array of HR values from interval start
        nadir_idx: Index of the lowest point (nadir) in the interval
    
    Returns:
        (offset, confidence): Offset in seconds to true peak, confidence level
    """
    if len(hr_values) < 10 or nadir_idx < 10:
        return 0, 'insufficient_data'
    
    # Compute median slope from first 5-6 points
    initial_diffs = np.diff(hr_values[:6])
    if len(initial_diffs) == 0:
        return 0, 'insufficient_data'
    
    initial_slope = np.median(initial_diffs)
    
    # If initial slope is already strongly negative, no plateau
    if initial_slope < -0.5:
        return 0, 'already_declining'
    
    # Project line: hr_projected[i] = hr_values[0] + initial_slope * i
    def projected(i):
        return hr_values[0] + initial_slope * i
    
    def delta(i):
        if i >= len(hr_values):
            return None
        return hr_values[i] - projected(i)
    
    # Binary search for where actual crosses projection
    left, right = 0, min(nadir_idx, len(hr_values) - 1)
    
    # Need at least some range to search
    if right - left < 5:
        return 0, 'range_too_small'
    
    iterations = 0
    max_iterations = 20  # Prevent infinite loops
    
    while right - left > 1 and iterations < max_iterations:
        iterations += 1
        mid = (left + right) // 2
        d = delta(mid)
        
        if d is None:
            right = mid
            continue
        
        if d > 0:  # Actual HR above projection, go right
            left = mid
        else:  # Actual HR below projection, go left
            right = mid
    
    if iterations >= max_iterations:
        return left, 'max_iterations'
    
    return left, 'geometry_found'


def find_true_peak_plateau(
    hr_values: np.ndarray,
    nadir_idx: int,
    config: 'HRRConfig'
) -> Tuple[int, str, Dict[str, Any]]:
    """
    Find true peak when plateau is detected (r2_0_30 < threshold).
    
    Runs both methods (slope and geometry) and compares results.
    If they agree (within 3 seconds), high confidence.
    If they disagree, take average and flag for review.
    
    Args:
        hr_values: Array of HR values from interval start
        nadir_idx: Index of the nadir (lowest point)
        config: HRR configuration
    
    Returns:
        (offset, confidence, debug_info): 
            - offset: Seconds to shift from detected peak to true peak
            - confidence: 'high', 'medium', 'low'
            - debug_info: Dict with method results for logging
    """
    # Run both methods
    offset_slope, slope_status = find_peak_by_slope(hr_values)
    offset_geom, geom_status = find_peak_by_geometry(hr_values, nadir_idx)
    
    debug_info = {
        'slope_offset': offset_slope,
        'slope_status': slope_status,
        'geom_offset': offset_geom,
        'geom_status': geom_status,
    }
    
    # Handle edge cases where one method failed
    if slope_status in ('insufficient_data', 'no_sustained_decline') and \
       geom_status in ('insufficient_data', 'range_too_small', 'already_declining'):
        # Both failed - can't resolve
        return 0, 'failed', debug_info
    
    if slope_status in ('insufficient_data', 'no_sustained_decline'):
        # Only geometry worked
        return offset_geom, 'low', debug_info
    
    if geom_status in ('insufficient_data', 'range_too_small', 'already_declining'):
        # Only slope worked
        return offset_slope, 'low', debug_info
    
    # Both methods produced results - compare
    diff = abs(offset_slope - offset_geom)
    debug_info['method_diff'] = diff
    
    if diff <= 3:
        # Agreement within 3 seconds - high confidence, use slope (more direct)
        return offset_slope, 'high', debug_info
    elif diff <= 10:
        # Moderate disagreement - take average, medium confidence
        avg_offset = (offset_slope + offset_geom) // 2
        return avg_offset, 'medium', debug_info
    else:
        # Large disagreement - take average, low confidence
        avg_offset = (offset_slope + offset_geom) // 2
        return avg_offset, 'low', debug_info


# =============================================================================
# Feature Extraction Pipeline
# =============================================================================

def extract_features(
    samples: List[HRSample],
    resting_hr: int,
    config: HRRConfig = None,
    peak_adjustments: Dict[int, int] = None
) -> List[RecoveryInterval]:
    """
    Main feature extraction pipeline.
    Detects recovery intervals and computes all features.
    
    Args:
        samples: List of HR samples
        resting_hr: Resting heart rate for this session
        config: HRR configuration
        peak_adjustments: Dict mapping interval_order -> shift_seconds for manual overrides
    """
    if config is None:
        config = HRRConfig()
    
    if len(samples) < config.min_decline_duration_sec:
        logger.warning(f"Insufficient samples: {len(samples)}")
        return []
    
    # Detect peaks (primary method)
    peak_indices = detect_peaks(samples, config)
    logger.info(f"Found {len(peak_indices)} candidate peaks (scipy)")
    
    # Detect valley-based peaks (Issue #020 - catches plateau-to-decline)
    valley_peaks = detect_valley_peaks(samples, resting_hr, config)
    logger.info(f"Found {len(valley_peaks)} candidate peaks (valley)")
    
    # Merge candidates (peak detection takes priority)
    all_candidates = merge_peak_candidates(peak_indices, valley_peaks, samples, config)
    logger.info(f"Merged to {len(all_candidates)} unique candidates")
    
    # Filter valid peaks
    valid_peaks = [
        idx for idx in all_candidates
        if validate_peak(samples, idx, resting_hr, config)
    ]
    logger.info(f"Validated {len(valid_peaks)} peaks")
    
    intervals = []
    interval_order = 1
    last_interval_end = -1  # Track end of previous interval for measurement window constraint
    
    for peak_idx in valid_peaks:
        # Apply manual peak adjustment if one exists for this interval_order
        if peak_adjustments and interval_order in peak_adjustments:
            shift = peak_adjustments[interval_order]
            original_peak_idx = peak_idx
            peak_idx = peak_idx + shift
            logger.info(f"Applied manual adjustment: peak {interval_order} shifted by {shift}s (index {original_peak_idx} -> {peak_idx})")
            
            # Validate new peak is within bounds
            if peak_idx < 0 or peak_idx >= len(samples):
                logger.warning(f"Adjusted peak {interval_order} out of bounds, skipping")
                interval_order += 1
                continue
            
            # Flag to add later to indicate manual adjustment
            manual_adjustment_applied = True
        else:
            manual_adjustment_applied = False
        
        # Measurement window constraint: new peak can't start within previous interval
        if peak_idx <= last_interval_end:
            continue
        
        # Find recovery end
        end_idx = find_recovery_end(samples, peak_idx, config)
        if end_idx is None:
            continue
        
        # Create interval
        interval = create_recovery_interval(
            samples, peak_idx, end_idx, interval_order, resting_hr, config
        )
        
        if interval is None:
            continue
        
        # Get samples for this interval - use onset-adjusted start (Issue #015)
        # The interval already has onset_delay_sec computed by create_recovery_interval()
        # This ensures R² is computed from the true max HR, not scipy's detection point
        onset_offset = interval.onset_delay_sec or 0
        adjusted_start_idx = peak_idx + onset_offset
        interval_samples = samples[adjusted_start_idx:end_idx + 1]
        
        # Fit exponential decay
        interval = fit_exponential_decay(interval_samples, interval, config)
        
        # Compute segment R² values
        interval = compute_all_segment_r2(interval_samples, interval)
        
        # Plateau detection: if r2_0_30 < threshold, try to find true peak
        # This catches double-peak patterns where scipy detected the wrong peak
        if interval.r2_0_30 is not None and interval.r2_0_30 < config.gate_r2_0_30_threshold:
            hr_values = np.array([s.hr_value for s in interval_samples])
            nadir_idx = interval.nadir_time_sec or len(hr_values) - 1
            
            # Try to find true peak using both methods
            plateau_offset, plateau_confidence, debug_info = find_true_peak_plateau(
                hr_values, nadir_idx, config
            )
            
            logger.info(
                f"Plateau detected at interval {interval_order}: r2_0_30={interval.r2_0_30:.3f}, "
                f"offset={plateau_offset}s, confidence={plateau_confidence}, "
                f"slope={debug_info['slope_offset']}s/{debug_info['slope_status']}, "
                f"geom={debug_info['geom_offset']}s/{debug_info['geom_status']}"
            )
            
            # Only re-anchor if we found a meaningful offset (>5 seconds)
            if plateau_offset > 5 and plateau_confidence != 'failed':
                # Calculate new start index
                new_start_idx = adjusted_start_idx + plateau_offset
                
                # Make sure we still have enough data after the new start
                if new_start_idx < end_idx - config.min_decline_duration_sec:
                    # Find new recovery end from new peak
                    new_end_idx = find_recovery_end(samples, new_start_idx, config)
                    
                    if new_end_idx is not None and new_end_idx > new_start_idx + config.min_decline_duration_sec:
                        # Recreate interval from new anchor point
                        new_interval = create_recovery_interval(
                            samples, new_start_idx, new_end_idx, interval_order, resting_hr, config
                        )
                        
                        if new_interval is not None:
                            # Get new interval samples
                            new_onset_offset = new_interval.onset_delay_sec or 0
                            new_adjusted_start = new_start_idx + new_onset_offset
                            new_interval_samples = samples[new_adjusted_start:new_end_idx + 1]
                            
                            if len(new_interval_samples) >= config.min_decline_duration_sec:
                                # Recompute exponential fit
                                new_interval = fit_exponential_decay(new_interval_samples, new_interval, config)
                                
                                # Recompute segment R²
                                new_interval = compute_all_segment_r2(new_interval_samples, new_interval)
                                
                                # Check if re-anchor improved r2_0_30
                                if new_interval.r2_0_30 is not None and new_interval.r2_0_30 >= config.gate_r2_0_30_threshold:
                                    logger.info(
                                        f"Plateau resolved: r2_0_30 {interval.r2_0_30:.3f} -> {new_interval.r2_0_30:.3f}, "
                                        f"shifted +{plateau_offset}s"
                                    )
                                    # Use the re-anchored interval
                                    interval = new_interval
                                    interval_samples = new_interval_samples
                                    end_idx = new_end_idx
                                    
                                    # Add flag to indicate plateau was resolved
                                    if 'PLATEAU_RESOLVED' not in interval.quality_flags:
                                        interval.quality_flags.append('PLATEAU_RESOLVED')
                                else:
                                    logger.info(
                                        f"Plateau re-anchor did not improve r2_0_30: "
                                        f"{interval.r2_0_30:.3f} -> {new_interval.r2_0_30 if new_interval.r2_0_30 else 'None'}"
                                    )
        
        # Compute late slope
        interval = compute_late_slope(interval_samples, interval)
        
        # Quality assessment
        interval = assess_quality(interval, config)
        
        # Add manual adjustment flag if applicable
        if manual_adjustment_applied:
            if 'MANUAL_ADJUSTED' not in interval.quality_flags:
                interval.quality_flags.append('MANUAL_ADJUSTED')
        
        intervals.append(interval)
        interval_order += 1
        
        # Update measurement window constraint tracker
        last_interval_end = end_idx
    
    # Overlap detection (Issue #015)
    # If interval N's window overlaps interval N+1's, reject N as duplicate
    # This catches cases where onset adjustment collapses one peak onto the next
    for i in range(len(intervals) - 1):
        curr = intervals[i]
        next_int = intervals[i + 1]
        
        # Check if current interval's end overlaps next interval's start
        # Or if current's adjusted start >= next's adjusted start (collapsed past it)
        if curr.start_time >= next_int.start_time:
            # Current interval collapsed onto next one - reject as duplicate
            curr.quality_status = 'rejected'
            curr.auto_reject_reason = 'overlap_duplicate'
            curr.needs_review = False
            curr.review_priority = 0
            if 'OVERLAP' not in curr.quality_flags:
                curr.quality_flags.append('OVERLAP')
    
    logger.info(f"Extracted {len(intervals)} valid recovery intervals")
    return intervals


# =============================================================================
# Quality Assessment
# =============================================================================

def assess_quality(interval: RecoveryInterval, config: HRRConfig) -> RecoveryInterval:
    """
    Assess interval quality and set flags/status.
    
    Quality rules:
    - slope_90_120 > 0.1: HARD REJECT (definite activity resumption)
    - r2 < 0.75 for best window: HARD REJECT (statistically validated threshold)
    - Everything else with concerns: FLAG for human review
    """
    # Sample quality
    interval.quality_flags = []
    interval.quality_status = 'pending'
    hard_reject = False
    reject_reason = None
    
    # === HARD REJECT CRITERIA ===
    
    # 0. Insufficient duration - can't compute HRR60
    if interval.r2_0_60 is None:
        hard_reject = True
        reject_reason = 'insufficient_duration'
    
    # 1. Late slope > 0.1 bpm/sec = definite activity resumption
    if interval.slope_90_120 is not None and interval.slope_90_120 > 0.1:
        hard_reject = True
        reject_reason = 'activity_resumed'
    
    # 2. Best segment R² < 0.75 = statistically validated junk threshold
    # Find best R² across valid windows (exclude r2_0_30 - too short for HRR60)
    r2_values = {
        'r2_0_60': interval.r2_0_60,
        'r2_0_120': interval.r2_0_120,
        'r2_0_180': interval.r2_0_180,
        'r2_0_240': interval.r2_0_240,
        'r2_0_300': interval.r2_0_300,
    }
    valid_r2 = {k: v for k, v in r2_values.items() if v is not None}
    best_r2 = max(valid_r2.values()) if valid_r2 else None
    
    if best_r2 is None:
        # No valid windows to evaluate - too short or all fits failed
        hard_reject = True
        reject_reason = 'no_valid_r2_windows'
    elif best_r2 < 0.75:
        hard_reject = True
        reject_reason = 'poor_fit_quality'
    
    # 3. Gate 8: Segment quality check (r2_30_60 validates HRR60 measurement)
    # Threshold is 0.75 - same as other R² gates
    # None means no data (too short, fit failed, or skipped)
    if interval.r2_30_60 is not None and interval.r2_30_60 < 0.75:
        hard_reject = True
        reject_reason = 'r2_30_60_below_0.75'
    
    # 4. Gate 9: r2_30_90 validates HRR120 measurement
    # Mid-interval bounce destroys the 120s window even if 0-120 R² looks OK
    if interval.r2_30_90 is not None and interval.r2_30_90 < 0.75:
        hard_reject = True
        reject_reason = 'r2_30_90_below_0.75'
    
    # 5. Gate 10: r2_0_30 < 0.5 = double-peak detection (Issue #015)
    # If first 30s doesn't fit exponential decay, we caught a false start
    # (plateau or rise before the real recovery began)
    if interval.r2_0_30 is not None and interval.r2_0_30 < 0.5:
        hard_reject = True
        reject_reason = 'double_peak'
    
    # === FLAG CRITERIA (for human review, not auto-reject) ===
    
    # Minor late rise (0 < slope <= 0.1) - could be noise or minor fidgeting
    if interval.slope_90_120 is not None and 0 < interval.slope_90_120 <= 0.1:
        interval.quality_flags.append('LATE_RISE')
    

    
    # Onset disagreement - methods disagree on when recovery started
    if interval.onset_confidence == 'low':
        interval.quality_flags.append('ONSET_DISAGREEMENT')
    
    # Low signal - peak wasn't very high above resting
    if interval.is_low_signal:
        interval.quality_flags.append('LOW_SIGNAL')
    
    # ONSET_ADJUSTED flag - onset was adjusted from scipy detection point (Issue #015)
    # Only flag if adjustment > 15 seconds (small adjustments are normal)
    if config.is_flag_enabled('ONSET_ADJUSTED'):
        if interval.onset_delay_sec and interval.onset_delay_sec > 15:
            interval.quality_flags.append('ONSET_ADJUSTED')
    
    # Store reject reason
    if hard_reject:
        interval.auto_reject_reason = reject_reason
    
    # === SET REVIEW PRIORITY ===
    if hard_reject:
        interval.review_priority = 0  # Auto-rejected
        interval.needs_review = False
    elif 'HIGH_R2_DELTA' in interval.quality_flags or 'LATE_RISE' in interval.quality_flags:
        interval.review_priority = 1  # High - concerning flags
        interval.needs_review = True
    elif interval.quality_flags:
        interval.review_priority = 2  # Medium - minor issues
        interval.needs_review = True
    else:
        interval.review_priority = 3  # Low - clean
        interval.needs_review = False
    
    # === SET STATUS ===
    if hard_reject:
        interval.quality_status = 'rejected'
    elif not interval.quality_flags:
        interval.quality_status = 'pass'
    else:
        interval.quality_status = 'flagged'
    
    # Sample completeness
    # (This is computed elsewhere but ensure it's set)
    if not hasattr(interval, 'sample_completeness') or interval.sample_completeness is None:
        interval.sample_completeness = 1.0
    interval.is_clean = interval.sample_completeness >= config.min_sample_completeness
    
    return interval


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
# Main Entry Point
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


if __name__ == '__main__':
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
