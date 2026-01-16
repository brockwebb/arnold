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
from typing import Optional, List, Tuple
import numpy as np
from scipy import signal
from scipy.optimize import curve_fit
import psycopg2
from psycopg2.extras import execute_values
import os
from pathlib import Path

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

@dataclass
class HRRConfig:
    """Configuration for HRR detection and feature extraction."""
    
    # Peak detection
    min_elevation_bpm: int = 25  # Peak must be this far above RHR to count
    min_sustained_effort_sec: int = 20  # Must be elevated for this long before peak
    peak_prominence: int = 10  # scipy.signal.find_peaks prominence
    
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
    onset_max_delay: int = 45  # max seconds for max-HR method (sliding window searches full interval)
    
    # Estimated max HR (can be overridden per-athlete)
    default_max_hr: int = 180  # Conservative default
    

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
    """Detected recovery interval with computed features."""
    
    # Timing
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    interval_order: int
    
    # Raw HR values
    hr_peak: int
    hr_30s: Optional[int] = None
    hr_60s: Optional[int] = None
    hr_90s: Optional[int] = None
    hr_120s: Optional[int] = None
    hr_180s: Optional[int] = None
    hr_240s: Optional[int] = None
    hr_300s: Optional[int] = None
    hr_nadir: Optional[int] = None
    rhr_baseline: Optional[int] = None
    
    # Absolute metrics
    hrr30_abs: Optional[int] = None
    hrr60_abs: Optional[int] = None
    hrr90_abs: Optional[int] = None
    hrr120_abs: Optional[int] = None
    hrr180_abs: Optional[int] = None
    hrr240_abs: Optional[int] = None
    hrr300_abs: Optional[int] = None
    total_drop: Optional[int] = None
    
    # Normalized metrics
    hr_reserve: Optional[int] = None
    hrr30_frac: Optional[float] = None
    hrr60_frac: Optional[float] = None
    hrr90_frac: Optional[float] = None
    hrr120_frac: Optional[float] = None
    recovery_ratio: Optional[float] = None
    peak_pct_max: Optional[float] = None
    
    # Decay dynamics
    tau_seconds: Optional[float] = None
    tau_fit_r2: Optional[float] = None
    decline_slope_30s: Optional[float] = None
    decline_slope_60s: Optional[float] = None
    time_to_50pct_sec: Optional[int] = None
    auc_60s: Optional[float] = None
    
    # Pre-peak context
    sustained_effort_sec: Optional[int] = None
    effort_avg_hr: Optional[int] = None
    
    # Delayed onset (catch-breath detection)
    onset_delay_sec: Optional[int] = None  # seconds from peak to real decline start
    adjusted_peak_hr: Optional[int] = None  # HR at onset (may differ from hr_peak)
    onset_confidence: Optional[str] = None  # 'high', 'medium', 'low' - agreement between methods
    
    # Quality
    sample_count: int = 0
    expected_sample_count: int = 0
    sample_completeness: float = 0.0
    is_clean: bool = True
    is_low_signal: bool = False
    
    # Session context
    session_elapsed_min: Optional[int] = None
    
    # === NEW: Segment R² metrics (validated 2026-01-15) ===
    r2_0_30: Optional[float] = None
    r2_30_60: Optional[float] = None
    r2_30_90: Optional[float] = None  # Transition zone (30-90s)
    r2_delta: Optional[float] = None  # r2_0_30 - r2_30_60
    
    # === Full-interval R² at each timepoint (validates HRR at that timepoint) ===
    r2_0_60: Optional[float] = None   # Validates HRR60
    r2_0_90: Optional[float] = None   # Validates HRR90
    r2_0_120: Optional[float] = None  # Validates HRR120
    r2_0_180: Optional[float] = None  # Validates HRR180
    r2_0_240: Optional[float] = None  # Validates HRR240
    r2_0_300: Optional[float] = None  # Validates HRR300
    
    # === Detected segment metrics (organic interval, not standard endpoint) ===
    r2_detected: Optional[float] = None  # R² for 0 to detected_duration
    hr_detected: Optional[int] = None    # HR at detected_duration
    hrr_detected: Optional[int] = None   # HRR drop at detected_duration (if r2_detected passes)
    
    # === NEW: Late slope (for HRR120 intervals) ===
    slope_90_120: Optional[float] = None  # bpm/sec
    slope_90_120_r2: Optional[float] = None
    
    # === NEW: Fit parameters (for reproducibility) ===
    fit_amplitude: Optional[float] = None  # A in A*exp(-t/tau) + C
    fit_asymptote: Optional[float] = None  # C
    
    # === NEW: Detection flags ===
    peak_detected: bool = False
    valley_detected: bool = False
    peak_count: int = 0
    valley_count: int = 0
    
    # === NEW: Quality assessment ===
    quality_status: str = 'pending'  # pending, pass, flagged, rejected
    quality_flags: List[str] = field(default_factory=list)
    quality_score: Optional[float] = None  # 0-1 confidence
    auto_reject_reason: Optional[str] = None
    
    # === NEW: Peak identification ===
    peak_label: Optional[str] = None  # e.g., "S71:p03"
    peak_sample_idx: Optional[int] = None
    
    # === Review workflow (defaults for new intervals) ===
    needs_review: bool = True
    review_priority: int = 3  # 1=high, 2=medium, 3=low
    
    # Raw samples (not stored, used for computation)
    samples: List[HRSample] = field(default_factory=list)
    r2_samples: List[HRSample] = field(default_factory=list)  # Extended samples for R² computation


# =============================================================================
# Quality Filtering
# =============================================================================

def filter_quality_intervals(intervals: List[RecoveryInterval], 
                             config: HRRConfig) -> Tuple[List[RecoveryInterval], List[RecoveryInterval], List[RecoveryInterval]]:
    """
    Filter intervals by quality using computed features.
    Returns (valid_intervals, noise_intervals, rejected_intervals).
    
    Uses simple threshold gates on pre-computed features:
    1. Sufficient samples
    2. Sufficient signal (hr_reserve)
    3. Must have hr_60s measurement
    4. Onset quality
    5. Minimum absolute drop (hrr60_abs)
    6. Persistence check
    7. Valid decay curve (tau or recovery_ratio)
    8. Segment R² quality (30-60s and 30-90s must be >= 0.75)
    """
    valid = []
    noise = []  # Floor effect - can't measure recovery meaningfully
    rejected = []  # Had potential but didn't pass validation
    
    for interval in intervals:
        # Gate 1: Sufficient samples
        if not interval.samples or len(interval.samples) < 30:
            interval._reject_reason = f"INSUFFICIENT_SAMPLES: {len(interval.samples) if interval.samples else 0}"
            rejected.append(interval)
            logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
            continue
        
        # Gate 2: Low signal (floor effect)
        if interval.hr_reserve is not None and interval.hr_reserve < config.low_signal_threshold_bpm:
            interval._reject_reason = f"LOW_SIGNAL: hr_reserve={interval.hr_reserve} < {config.low_signal_threshold_bpm}"
            noise.append(interval)
            logger.debug(f"Noise interval #{interval.interval_order}: {interval._reject_reason}")
            continue
        
        # Gate 3: Must have hr_60s measurement
        if interval.hr_60s is None:
            onset = interval.onset_delay_sec or 0
            available = interval.duration_seconds - onset
            interval._reject_reason = f"NO_HR60: need 60s from onset, have {available}s"
            rejected.append(interval)
            logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
            continue
        
        # Gate 4: Onset quality - long onset with low confidence = unreliable
        onset = interval.onset_delay_sec or 0
        onset_conf = interval.onset_confidence
        if onset > 60 and onset_conf == 'low':
            interval._reject_reason = f"UNRELIABLE_ONSET: onset={onset}s with low confidence"
            rejected.append(interval)
            logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
            continue
        
        # Gate 5: Minimum absolute drop (from onset-adjusted peak)
        if interval.hrr60_abs is None or interval.hrr60_abs < config.min_hrr60_abs:
            interval._reject_reason = f"LOW_DROP: hrr60_abs={interval.hrr60_abs} < {config.min_hrr60_abs}"
            rejected.append(interval)
            logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
            continue
        
        # Gate 6: Persistence - hr_60s should be near nadir, not climbing back up
        # If hr_60s is way above nadir, we caught the interval too late
        # BUT: Only apply to short intervals (<=120s) where nadir should occur within 60s
        # For longer intervals, nadir naturally occurs later - hr_60s above nadir is expected
        if interval.hr_nadir is not None and interval.duration_seconds <= 120:
            hr_above_nadir = interval.hr_60s - interval.hr_nadir
            if hr_above_nadir > 15:  # hr_60s more than 15 bpm above nadir
                interval._reject_reason = f"NOT_SUSTAINED: hr_60s={interval.hr_60s} is {hr_above_nadir}bpm above nadir={interval.hr_nadir}"
                rejected.append(interval)
                logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
                continue
        
        # Gate 7: Valid decay curve - need BOTH reasonable tau AND ratio
        # tau=300 (capped) means flat curve - not real exponential recovery
        has_valid_tau = (interval.tau_seconds is not None and 
                        interval.tau_seconds < 200 and 
                        interval.tau_fit_r2 is not None and 
                        interval.tau_fit_r2 >= 0.5)
        has_valid_ratio = (interval.recovery_ratio is not None and 
                          interval.recovery_ratio >= config.min_recovery_ratio)
        
        # If tau is capped (300s = flat), require much higher ratio to pass
        tau_is_flat = (interval.tau_seconds is not None and interval.tau_seconds >= 200)
        
        if tau_is_flat:
            # Flat curve - need strong ratio evidence (>= 25%)
            if interval.recovery_ratio is None or interval.recovery_ratio < 0.25:
                tau_str = f"tau={interval.tau_seconds:.0f}s(flat)"
                ratio_str = f"ratio={interval.recovery_ratio:.0%}" if interval.recovery_ratio else "ratio=None"
                interval._reject_reason = f"FLAT_DECAY: {tau_str}, {ratio_str} < 25%"
                rejected.append(interval)
                logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
                continue
        elif not has_valid_tau and not has_valid_ratio:
            tau_str = f"tau={interval.tau_seconds:.0f}s,r2={interval.tau_fit_r2:.2f}" if interval.tau_seconds else "tau=None"
            ratio_str = f"ratio={interval.recovery_ratio:.0%}" if interval.recovery_ratio else "ratio=None"
            interval._reject_reason = f"NO_VALID_DECAY: {tau_str}, {ratio_str}"
            rejected.append(interval)
            logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
            continue
        
        # Gate 8: Segment R² quality - catches disrupted recovery patterns
        # The 30-60s segment must show good exponential fit (not plateau/rebound)
        # The 30-90s "transition zone" catches issues the 30-60s might miss
        segment_r2_threshold = 0.75
        
        # 8a: Check r2_30_60 (required for HRR60 validity)
        if interval.r2_0_30 is not None:  # If we could fit 0-30, we should have 30-60
            if interval.r2_30_60 is None:
                interval._reject_reason = f"SEGMENT_FIT_FAILED: r2_0_30={interval.r2_0_30:.3f} but r2_30_60 fit failed"
                rejected.append(interval)
                logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
                continue
            elif interval.r2_30_60 < segment_r2_threshold:
                interval._reject_reason = f"SEGMENT_QUALITY_FAILED: r2_30_60={interval.r2_30_60:.3f} < {segment_r2_threshold} (disrupted 30-60s)"
                rejected.append(interval)
                logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
                continue
        
        # 8b: Check r2_30_90 for intervals >= 90s (transition zone quality)
        if interval.duration_seconds >= 90 and interval.r2_30_90 is not None:
            if interval.r2_30_90 < segment_r2_threshold:
                interval._reject_reason = f"TRANSITION_QUALITY_FAILED: r2_30_90={interval.r2_30_90:.3f} < {segment_r2_threshold} (disrupted 30-90s)"
                rejected.append(interval)
                logger.debug(f"Rejected interval #{interval.interval_order}: {interval._reject_reason}")
                continue
        
        # Passed all gates
        interval._reject_reason = None
        valid.append(interval)
    
    return valid, noise, rejected


# =============================================================================
# Database Functions
# =============================================================================

def get_db_connection():
    """Get database connection from environment."""
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def get_hr_samples(conn, session_id: int, source: str) -> List[HRSample]:
    """Load HR samples for a session."""
    
    if source == 'endurance':
        query = """
            SELECT sample_time, hr_value
            FROM hr_samples
            WHERE endurance_session_id = %s
            ORDER BY sample_time
        """
    else:  # polar
        query = """
            SELECT sample_time, hr_value
            FROM hr_samples
            WHERE session_id = %s
            ORDER BY sample_time
        """
    
    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()
    
    return [HRSample(timestamp=row[0], hr_value=row[1]) for row in rows]


def get_rhr_for_date(conn, date: datetime) -> Optional[int]:
    """Get resting HR for a specific date."""
    query = """
        SELECT value FROM biometric_readings
        WHERE metric_type = 'resting_hr'
        AND reading_date = %s::date
    """
    with conn.cursor() as cur:
        cur.execute(query, (date,))
        row = cur.fetchone()
    
    if row:
        return int(row[0])
    
    # Fall back to 7-day average
    query = """
        SELECT AVG(value) FROM biometric_readings
        WHERE metric_type = 'resting_hr'
        AND reading_date BETWEEN %s::date - INTERVAL '7 days' AND %s::date
    """
    with conn.cursor() as cur:
        cur.execute(query, (date, date))
        row = cur.fetchone()
    
    if row and row[0]:
        return int(row[0])
    
    return None


def get_sessions_to_process(conn, source: str) -> List[Tuple[int, datetime]]:
    """Get list of sessions that haven't been processed yet."""
    
    if source == 'endurance':
        query = """
            SELECT DISTINCT es.id, MIN(h.sample_time) as session_start
            FROM endurance_sessions es
            JOIN hr_samples h ON h.endurance_session_id = es.id
            LEFT JOIN hr_recovery_intervals ri ON ri.endurance_session_id = es.id
            WHERE ri.id IS NULL
            GROUP BY es.id
            ORDER BY session_start
        """
    else:  # polar
        query = """
            SELECT DISTINCT ps.id, MIN(h.sample_time) as session_start
            FROM polar_sessions ps
            JOIN hr_samples h ON h.session_id = ps.id
            LEFT JOIN hr_recovery_intervals ri ON ri.polar_session_id = ps.id
            WHERE ri.id IS NULL
            GROUP BY ps.id
            ORDER BY session_start
        """
    
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def get_all_sessions(conn, source: str) -> List[Tuple[int, datetime]]:
    """Get ALL sessions with HR data (for reprocessing)."""
    
    if source == 'endurance':
        query = """
            SELECT DISTINCT es.id, MIN(h.sample_time) as session_start
            FROM endurance_sessions es
            JOIN hr_samples h ON h.endurance_session_id = es.id
            GROUP BY es.id
            ORDER BY session_start
        """
    else:  # polar
        query = """
            SELECT DISTINCT ps.id, MIN(h.sample_time) as session_start
            FROM polar_sessions ps
            JOIN hr_samples h ON h.session_id = ps.id
            GROUP BY ps.id
            ORDER BY session_start
        """
    
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def _to_native(val):
    """Convert numpy types to Python native types for psycopg2."""
    if val is None:
        return None
    if isinstance(val, (np.floating, np.float64, np.float32)):
        return float(val)
    if isinstance(val, (np.integer, np.int64, np.int32)):
        return int(val)
    if isinstance(val, np.bool_):
        return bool(val)
    return val


def save_intervals(conn, intervals: List[RecoveryInterval], 
                   session_id: int, source: str, dry_run: bool = False):
    """Save detected intervals to database."""
    
    if not intervals:
        logger.info("No intervals to save")
        return
    
    if dry_run:
        logger.info(f"DRY RUN: Would save {len(intervals)} intervals")
        for i, interval in enumerate(intervals):
            tau_str = f"tau={interval.tau_seconds:.1f}s" if interval.tau_seconds and interval.tau_seconds < 300 else "tau=FLAT"
            pre_str = f"pre_avg={interval.effort_avg_hr}" if interval.effort_avg_hr else "pre_avg=?"
            frac_str = f"frac={interval.hrr60_frac:.2f}" if interval.hrr60_frac else ""
            onset_str = f"onset={interval.onset_delay_sec}s({interval.onset_confidence})" if interval.onset_delay_sec else ""
            logger.info(f"  [{i+1}] peak={interval.hr_peak}, {pre_str}, hrr60_abs={interval.hrr60_abs}, {frac_str}, {tau_str} {onset_str}")
        return
    
    # Build insert data
    columns = [
        'polar_session_id' if source == 'polar' else 'endurance_session_id',
        'start_time', 'end_time', 'duration_seconds', 'interval_order',
        'hr_peak', 'hr_30s', 'hr_60s', 'hr_90s', 'hr_120s', 'hr_180s', 'hr_240s', 'hr_300s', 'hr_nadir', 'rhr_baseline',
        'hrr30_abs', 'hrr60_abs', 'hrr90_abs', 'hrr120_abs', 'hrr180_abs', 'hrr240_abs', 'hrr300_abs', 'total_drop',
        'hr_reserve', 'hrr30_frac', 'hrr60_frac', 'hrr90_frac', 'hrr120_frac',
        'recovery_ratio', 'peak_pct_max',
        'tau_seconds', 'tau_fit_r2', 'decline_slope_30s', 'decline_slope_60s',
        'time_to_50pct_sec', 'auc_60s',
        'sustained_effort_sec', 'effort_avg_hr', 'session_elapsed_min',
        'sample_count', 'expected_sample_count', 'sample_completeness',
        'is_clean', 'is_low_signal',
        # New columns (2026-01-15)
        'r2_0_30', 'r2_30_60', 'r2_30_90', 'r2_delta',
        # Full-interval R² at each timepoint (2026-01-16)
        'r2_0_60', 'r2_0_90', 'r2_0_120', 'r2_0_180', 'r2_0_240', 'r2_0_300',
        'slope_90_120', 'slope_90_120_r2',
        'fit_amplitude', 'fit_asymptote',
        'quality_status', 'quality_flags', 'quality_score',
        'peak_label', 'needs_review', 'review_priority'
    ]
    
    values = []
    for interval in intervals:
        values.append(tuple(_to_native(v) for v in (
            session_id,
            interval.start_time, interval.end_time, interval.duration_seconds, interval.interval_order,
            interval.hr_peak, interval.hr_30s, interval.hr_60s, interval.hr_90s, interval.hr_120s,
            interval.hr_180s, interval.hr_240s, interval.hr_300s,
            interval.hr_nadir, interval.rhr_baseline,
            interval.hrr30_abs, interval.hrr60_abs, interval.hrr90_abs, interval.hrr120_abs,
            interval.hrr180_abs, interval.hrr240_abs, interval.hrr300_abs,
            interval.total_drop,
            interval.hr_reserve, interval.hrr30_frac, interval.hrr60_frac, interval.hrr90_frac,
            interval.hrr120_frac, interval.recovery_ratio, interval.peak_pct_max,
            interval.tau_seconds, interval.tau_fit_r2, interval.decline_slope_30s,
            interval.decline_slope_60s, interval.time_to_50pct_sec, interval.auc_60s,
            interval.sustained_effort_sec, interval.effort_avg_hr, interval.session_elapsed_min,
            interval.sample_count, interval.expected_sample_count, interval.sample_completeness,
            interval.is_clean, interval.is_low_signal,
            # New values
            interval.r2_0_30, interval.r2_30_60, interval.r2_30_90, interval.r2_delta,
            # Full-interval R² at each timepoint
            interval.r2_0_60, interval.r2_0_90, interval.r2_0_120,
            interval.r2_0_180, interval.r2_0_240, interval.r2_0_300,
            interval.slope_90_120, interval.slope_90_120_r2,
            interval.fit_amplitude, interval.fit_asymptote,
            interval.quality_status, interval.quality_flags, interval.quality_score,
            interval.peak_label, interval.needs_review, interval.review_priority
        )))
    
    query = f"""
        INSERT INTO hr_recovery_intervals ({', '.join(columns)})
        VALUES %s
    """
    
    with conn.cursor() as cur:
        execute_values(cur, query, values)
    conn.commit()
    
    logger.info(f"Saved {len(intervals)} intervals for session {session_id}")


# =============================================================================
# Detection Algorithm
# =============================================================================

def preprocess_samples(samples: List[HRSample], window: int = 3) -> np.ndarray:
    """Apply median filter to smooth HR stream."""
    hr_values = np.array([s.hr_value for s in samples])
    return signal.medfilt(hr_values, kernel_size=window)


def find_peaks_in_session(hr_smoothed: np.ndarray, config: HRRConfig) -> List[int]:
    """Find local maxima that could be set completions."""
    peaks, properties = signal.find_peaks(
        hr_smoothed,
        prominence=config.peak_prominence,
        distance=30  # At least 30 seconds between peaks
    )
    return peaks.tolist()


def detect_sustained_effort(samples: List[HRSample], peak_idx: int, 
                            rhr: int, config: HRRConfig) -> Tuple[int, int]:
    """
    Look backward from peak to find sustained effort period.
    Returns (duration_sec, avg_hr).
    """
    if peak_idx < 10:
        return 0, 0
    
    threshold = rhr + config.min_elevation_bpm
    
    # Scan backward from peak
    start_idx = peak_idx
    for i in range(peak_idx - 1, -1, -1):
        if samples[i].hr_value < threshold:
            break
        start_idx = i
    
    duration = (samples[peak_idx].timestamp - samples[start_idx].timestamp).total_seconds()
    
    if duration >= config.min_sustained_effort_sec:
        hr_values = [samples[j].hr_value for j in range(start_idx, peak_idx + 1)]
        return int(duration), int(np.mean(hr_values))
    
    return 0, 0


def compute_trailing_slope(samples: List[HRSample], current_idx: int, 
                           peak_idx: int, window_sec: int = 60) -> Optional[float]:
    """
    Compute trailing slope (bpm/sec) over the last window_sec seconds.
    Returns None if insufficient data in window.
    
    Negative slope = HR still declining (good, extend interval)
    Zero slope = HR stable (good, extend interval)  
    Positive slope = HR rising (activity resumed, stop)
    """
    if current_idx <= peak_idx:
        return None
    
    current_time = samples[current_idx].timestamp
    
    # Collect samples within trailing window
    t_list = []
    hr_list = []
    
    for i in range(current_idx, peak_idx, -1):  # Walk backward
        elapsed = (current_time - samples[i].timestamp).total_seconds()
        if elapsed > window_sec:
            break
        t_list.append(-elapsed)  # Negative because we're going backward
        hr_list.append(samples[i].hr_value)
    
    if len(t_list) < 10:  # Need sufficient points for reliable slope
        return None
    
    # Linear regression for slope
    t = np.array(t_list)
    hr = np.array(hr_list)
    
    try:
        coeffs = np.polyfit(t, hr, 1)
        return coeffs[0]  # slope in bpm/sec
    except Exception:
        return None


def detect_decline_interval(samples: List[HRSample], peak_idx: int,
                            config: HRRConfig) -> Optional[Tuple[int, int]]:
    """
    Scan forward from peak to find recovery interval.
    
    Two-phase detection:
    1. Find initial nadir (lowest HR point)
    2. Extend beyond nadir if HR shows stable/declining trend (slope ≤ 0)
    
    Terminates when:
    - Sustained positive slope detected (activity resumption)
    - Max duration (300s) reached
    
    Returns (end_idx, duration_sec) or None if no valid interval.
    """
    if peak_idx >= len(samples) - 30:
        return None
    
    peak_hr = samples[peak_idx].hr_value
    peak_time = samples[peak_idx].timestamp
    
    # Configuration for slope-based extension
    trailing_window_sec = 60  # Slope calculation window
    extension_slope_threshold = 0.05  # bpm/sec - slight positive OK (noise tolerance)
    min_consecutive_positive = 10  # seconds of sustained rise to terminate
    
    # Phase 1: Find initial nadir
    nadir_hr = peak_hr
    nadir_idx = peak_idx
    phase1_break_idx = None  # Where phase 1 would have stopped
    
    for i in range(peak_idx + 1, len(samples)):
        elapsed = (samples[i].timestamp - peak_time).total_seconds()
        
        if elapsed > config.max_interval_duration_sec:
            phase1_break_idx = i
            break
        
        hr = samples[i].hr_value
        
        # Track the lowest point
        if hr < nadir_hr:
            nadir_hr = hr
            nadir_idx = i
        
        # Original break condition - note where it would trigger
        if hr > nadir_hr + config.decline_tolerance_bpm:
            phase1_break_idx = i
            break
    
    # If we hit max duration without breaking, phase1_break_idx is at the limit
    if phase1_break_idx is None:
        phase1_break_idx = min(len(samples) - 1, 
                              peak_idx + config.max_interval_duration_sec)
    
    # Phase 2: Extend beyond nadir if HR is stable/declining
    # Start from nadir and continue scanning
    end_idx = nadir_idx
    consecutive_positive = 0
    
    for i in range(nadir_idx + 1, len(samples)):
        elapsed = (samples[i].timestamp - peak_time).total_seconds()
        
        if elapsed > config.max_interval_duration_sec:
            # Reached max duration - use current position as end
            end_idx = i - 1
            logger.debug(f"Interval extension: hit max_duration at {elapsed:.0f}s")
            break
        
        hr = samples[i].hr_value
        
        # Update nadir if HR drops further during extension
        if hr < nadir_hr:
            nadir_hr = hr
            nadir_idx = i
            end_idx = i
            consecutive_positive = 0
            continue
        
        # Compute trailing slope to detect activity resumption
        slope = compute_trailing_slope(samples, i, peak_idx, trailing_window_sec)
        
        if slope is not None and slope > extension_slope_threshold:
            consecutive_positive += 1
            if consecutive_positive >= min_consecutive_positive:
                # Sustained positive slope - activity resumed
                # End at the point before the rise started
                end_idx = i - consecutive_positive
                logger.debug(f"Interval extension: activity resumed at {elapsed:.0f}s "
                           f"(slope={slope:.3f} bpm/s for {consecutive_positive}s)")
                break
        else:
            # Slope is flat or negative - recovery continues
            consecutive_positive = 0
            end_idx = i
    
    # If we exited loop without breaking, end_idx is already set to last valid point
    
    duration = (samples[end_idx].timestamp - peak_time).total_seconds()
    
    # Log extension if we went beyond the original nadir
    original_duration = (samples[nadir_idx].timestamp - peak_time).total_seconds()
    if duration > original_duration + 5:  # More than 5s extension
        logger.debug(f"Interval extended: {original_duration:.0f}s -> {duration:.0f}s "
                    f"(+{duration - original_duration:.0f}s beyond nadir)")
    
    if duration >= config.min_decline_duration_sec:
        return end_idx, int(duration)
    
    return None


def detect_decline_onset(samples: List[HRSample], config: HRRConfig) -> Tuple[int, int, str]:
    """
    Detect where sustained decline actually begins (after catch-breath phase).
    
    Uses two methods and checks agreement:
    1. Max HR method - find highest HR within onset window
    2. Sliding window method - find 60s window with maximum drop
    
    When methods agree (within 5s), high confidence.
    When they disagree, use sliding window (more robust) but flag lower confidence.
    
    Returns (onset_delay_sec, onset_hr, confidence) where confidence is 'high'/'medium'/'low'.
    """
    if len(samples) < 10:
        return 0, samples[0].hr_value, 'low'
    
    t0 = samples[0].timestamp
    initial_hr = samples[0].hr_value
    
    # Build time-indexed lookup for quick access
    hr_at_sec = {}
    for s in samples:
        sec = int((s.timestamp - t0).total_seconds())
        hr_at_sec[sec] = s.hr_value
    
    # ==========================================================================
    # Method 1: Max HR within onset window
    # ==========================================================================
    max_hr = initial_hr
    max_hr_idx = 0
    
    for i, s in enumerate(samples):
        elapsed = (s.timestamp - t0).total_seconds()
        if elapsed > config.onset_max_delay:
            break
        if s.hr_value >= max_hr:
            max_hr = s.hr_value
            max_hr_idx = i
    
    onset_max_hr_sec = int((samples[max_hr_idx].timestamp - t0).total_seconds()) if max_hr_idx > 0 else 0
    
    # ==========================================================================
    # Method 2: Sliding window - find start that maximizes HRR60
    # Search entire interval (not limited to onset_max_delay)
    # ==========================================================================
    best_hrr60 = 0
    best_start_sec = 0
    best_start_hr = initial_hr
    
    # Get max searchable time (need 60s after start point)
    max_sample_time = max(hr_at_sec.keys()) if hr_at_sec else 0
    max_search_sec = max(0, max_sample_time - 60)
    
    # Slide window from t=0 to max_search_sec
    for start_sec in range(0, max_search_sec + 1):
        end_sec = start_sec + 60
        
        # Need both points
        if start_sec not in hr_at_sec or end_sec not in hr_at_sec:
            continue
        
        hrr60 = hr_at_sec[start_sec] - hr_at_sec[end_sec]
        
        if hrr60 > best_hrr60:
            best_hrr60 = hrr60
            best_start_sec = start_sec
            best_start_hr = hr_at_sec[start_sec]
    
    onset_sliding_sec = best_start_sec
    
    # ==========================================================================
    # Compare methods and determine confidence
    # ==========================================================================
    delta = abs(onset_max_hr_sec - onset_sliding_sec)
    
    if delta <= 5:
        confidence = 'high'
        # Use average when they agree
        onset_sec = (onset_max_hr_sec + onset_sliding_sec) // 2
        onset_hr = hr_at_sec.get(onset_sec, best_start_hr)
    elif delta <= 15:
        confidence = 'medium'
        # Prefer sliding window method (more robust)
        onset_sec = onset_sliding_sec
        onset_hr = best_start_hr
    else:
        confidence = 'low'
        # Use sliding window but flag disagreement
        onset_sec = onset_sliding_sec
        onset_hr = best_start_hr
    
    if onset_sec > 0:
        logger.debug(f"Onset: max_hr={onset_max_hr_sec}s, sliding={onset_sliding_sec}s, "
                    f"delta={delta}s, confidence={confidence}, using={onset_sec}s")
    
    return onset_sec, onset_hr, confidence


def detect_recovery_intervals(samples: List[HRSample], rhr: int, 
                              config: HRRConfig) -> List[RecoveryInterval]:
    """
    Main detection function: find all recovery intervals in a session.
    """
    if len(samples) < 60:
        logger.warning(f"Session too short ({len(samples)} samples)")
        return []
    
    # Preprocess
    hr_smoothed = preprocess_samples(samples)
    session_start = samples[0].timestamp
    
    # Find peaks
    peak_indices = find_peaks_in_session(hr_smoothed, config)
    logger.debug(f"Found {len(peak_indices)} candidate peaks")
    
    intervals = []
    interval_order = 0
    last_end_idx = 0
    
    for peak_idx in peak_indices:
        # Skip if this peak is within a previous interval
        if peak_idx <= last_end_idx:
            continue
        
        peak_hr = int(hr_smoothed[peak_idx])
        
        # Check elevation above RHR
        if peak_hr < rhr + config.min_elevation_bpm:
            continue
        
        # Check for sustained effort before peak
        effort_sec, effort_avg = detect_sustained_effort(samples, peak_idx, rhr, config)
        if effort_sec < config.min_sustained_effort_sec:
            continue
        
        # Detect decline interval
        decline_result = detect_decline_interval(samples, peak_idx, config)
        if decline_result is None:
            continue
        
        end_idx, duration = decline_result
        interval_order += 1
        last_end_idx = end_idx
        
        # Extract samples for this interval
        # For HRR computation, use samples within the detected interval
        interval_samples = samples[peak_idx:end_idx + 1]
        
        # For R² validation, we need samples BEYOND the interval boundary
        # so we can compute r2_0_120 even if interval ended at 114s
        # Include up to 300s from peak (max possible window)
        # For R² computation, extend BEYOND detected interval to account for onset_delay
        # Max onset_delay ~60s, so collect up to 360s from peak to ensure 300s from onset
        max_r2_idx = min(len(samples) - 1, peak_idx + 360)
        r2_samples = samples[peak_idx:max_r2_idx + 1]
        
        # Create interval object
        interval = RecoveryInterval(
            start_time=samples[peak_idx].timestamp,
            end_time=samples[end_idx].timestamp,
            duration_seconds=duration,
            interval_order=interval_order,
            hr_peak=peak_hr,
            rhr_baseline=rhr,
            sustained_effort_sec=effort_sec,
            effort_avg_hr=effort_avg,
            session_elapsed_min=int((samples[peak_idx].timestamp - session_start).total_seconds() / 60),
            samples=interval_samples,
            r2_samples=r2_samples,  # Extended samples for R² validation
            sample_count=len(interval_samples),
            expected_sample_count=duration,  # Assuming 1Hz
            sample_completeness=len(interval_samples) / duration if duration > 0 else 0
        )
        
        intervals.append(interval)
    
    logger.info(f"Detected {len(intervals)} valid recovery intervals")
    return intervals


# =============================================================================
# Feature Computation
# =============================================================================

def exponential_decay(t: np.ndarray, a: float, tau: float, c: float) -> np.ndarray:
    """Exponential decay function: HR(t) = a * exp(-t/tau) + c"""
    return a * np.exp(-t / tau) + c


@dataclass
class ExpFitResult:
    """Results from exponential decay fit."""
    tau: Optional[float] = None
    r2: Optional[float] = None
    amplitude: Optional[float] = None
    asymptote: Optional[float] = None
    success: bool = False


def fit_exponential_decay(samples: List[HRSample], config: HRRConfig) -> ExpFitResult:
    """
    Fit exponential decay to HR samples.
    Returns ExpFitResult with tau, r2, amplitude, asymptote.
    """
    result = ExpFitResult()
    
    if len(samples) < config.tau_min_points:
        return result
    
    # Prepare data
    t0 = samples[0].timestamp
    t = np.array([(s.timestamp - t0).total_seconds() for s in samples])
    hr = np.array([s.hr_value for s in samples])
    
    # Initial guesses
    a0 = hr[0] - hr[-1]  # Amplitude
    tau0 = 60.0  # 60 seconds
    c0 = hr[-1]  # Asymptote
    
    try:
        popt, _ = curve_fit(
            exponential_decay,
            t, hr,
            p0=[a0, tau0, c0],
            bounds=([0, 1, 30], [200, config.tau_max_seconds, 200]),
            maxfev=1000
        )
        
        a, tau, c = popt
        
        # Calculate R²
        hr_pred = exponential_decay(t, a, tau, c)
        ss_res = np.sum((hr - hr_pred) ** 2)
        ss_tot = np.sum((hr - np.mean(hr)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        result.amplitude = a
        result.asymptote = c
        result.r2 = r2
        
        if r2 >= config.tau_min_r2:
            result.tau = tau
            result.success = True
        
        return result
            
    except Exception as e:
        logger.debug(f"Exponential fit failed: {e}")
        return result


# =============================================================================
# IMPUTATION AND R² COMPUTATION
# =============================================================================

R2_THRESHOLD = 0.75  # Minimum R² to trust HRR value


def impute_hr_series(samples: List[HRSample], max_seconds: int = 300) -> Tuple[np.ndarray, int]:
    """
    Create a complete second-by-second HR array with gaps filled via linear interpolation.
    
    Args:
        samples: List of HRSample objects with timestamp and hr_value
        max_seconds: Maximum seconds to include (default 300 = 5 minutes)
    
    Returns:
        (hr_array, actual_length) where:
        - hr_array[i] = HR value at second i (0-indexed from first sample)
        - actual_length = how many seconds of real data we have
    """
    if not samples:
        return np.array([]), 0
    
    t0 = samples[0].timestamp
    
    # Build sparse dict of known values
    hr_at_sec = {}
    max_sec_seen = 0
    
    for s in samples:
        sec = int((s.timestamp - t0).total_seconds())
        if sec <= max_seconds:
            hr_at_sec[sec] = s.hr_value
            max_sec_seen = max(max_sec_seen, sec)
    
    if not hr_at_sec:
        return np.array([]), 0
    
    # Create output array
    length = min(max_sec_seen + 1, max_seconds + 1)
    hr_array = np.zeros(length, dtype=float)
    
    # Fill known values
    for sec, hr in hr_at_sec.items():
        if sec < length:
            hr_array[sec] = hr
    
    # Impute gaps via linear interpolation
    known_secs = sorted(hr_at_sec.keys())
    
    for i in range(len(known_secs) - 1):
        start_sec = known_secs[i]
        end_sec = known_secs[i + 1]
        
        if end_sec - start_sec > 1:  # There's a gap
            start_hr = hr_at_sec[start_sec]
            end_hr = hr_at_sec[end_sec]
            
            # Linear interpolation
            for sec in range(start_sec + 1, end_sec):
                if sec < length:
                    frac = (sec - start_sec) / (end_sec - start_sec)
                    hr_array[sec] = start_hr + frac * (end_hr - start_hr)
    
    return hr_array, max_sec_seen


def fit_window_r2(hr_array: np.ndarray, start_sec: int, end_sec: int) -> Optional[float]:
    """
    Fit exponential to hr_array[start_sec:end_sec+1] and return R².
    
    Uses min(end_sec, len(hr_array)-1) as actual end.
    Returns None only if insufficient data. Always returns R² if data exists.
    """
    # Adjust end to available data
    actual_end = min(end_sec, len(hr_array) - 1)
    
    if start_sec >= actual_end or actual_end - start_sec < 10:
        return None
    
    # Extract segment
    t = np.arange(0, actual_end - start_sec + 1, dtype=float)
    hr = hr_array[start_sec:actual_end + 1].copy()
    
    if len(hr) < 10:
        return None
    
    # Multiple attempts with different strategies
    strategies = [
        # Strategy 1: Standard initial guess
        {'p0': [max(hr[0] - hr[-1], 1.0), 30.0, hr[-1]], 'maxfev': 2000},
        # Strategy 2: Longer tau guess
        {'p0': [max(hr[0] - hr[-1], 1.0), 60.0, hr[-1]], 'maxfev': 2000},
        # Strategy 3: Use median for asymptote
        {'p0': [max(hr[0] - np.median(hr), 1.0), 45.0, np.median(hr)], 'maxfev': 2000},
        # Strategy 4: Very conservative
        {'p0': [20.0, 40.0, hr[-1]], 'maxfev': 3000},
    ]
    
    for strategy in strategies:
        try:
            popt, _ = curve_fit(
                exponential_decay,
                t, hr,
                p0=strategy['p0'],
                bounds=([0, 1, 30], [200, 300, 200]),
                maxfev=strategy['maxfev'],
                method='trf'  # Trust Region Reflective - more robust
            )
            
            hr_pred = exponential_decay(t, *popt)
            ss_res = np.sum((hr - hr_pred) ** 2)
            ss_tot = np.sum((hr - np.mean(hr)) ** 2)
            
            if ss_tot == 0:
                return 0.0  # Flat line
            
            return 1 - (ss_res / ss_tot)
            
        except (RuntimeError, ValueError):
            continue  # Try next strategy
    
    # All strategies failed - compute R² using fixed parameters as last resort
    # This ensures we ALWAYS return a value if data exists
    try:
        # Use simple heuristic: tau=30, asymptote=min(hr), amplitude=hr[0]-asymptote
        c_guess = np.min(hr)
        a_guess = hr[0] - c_guess
        tau_guess = 30.0
        
        hr_pred = exponential_decay(t, a_guess, tau_guess, c_guess)
        ss_res = np.sum((hr - hr_pred) ** 2)
        ss_tot = np.sum((hr - np.mean(hr)) ** 2)
        
        if ss_tot == 0:
            return 0.0
        
        r2 = 1 - (ss_res / ss_tot)
        # R² can be negative if model is worse than mean
        return r2
        
    except Exception:
        # Absolute last resort - data exists but nothing works
        return 0.0


def fit_segment_r2(samples: List[HRSample], start_sec: int, end_sec: int, 
                   config: HRRConfig) -> Optional[float]:
    """
    LEGACY WRAPPER: Fit exponential to a segment and return R².
    Now delegates to impute_hr_series + fit_window_r2 for consistency.
    """
    hr_array, actual_length = impute_hr_series(samples, max_seconds=end_sec + 10)
    if actual_length < start_sec:
        return None
    return fit_window_r2(hr_array, start_sec, end_sec)


def compute_late_slope(samples: List[HRSample], start_sec: int = 90, 
                       end_sec: int = 120) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute linear slope for late recovery (90-120s).
    Returns (slope_bpm_per_sec, r2).
    
    Uses 70% threshold - computes if we have at least 70% of window.
    """
    if len(samples) < 5:
        return None, None
    
    t0 = samples[0].timestamp
    max_sample_time = max((s.timestamp - t0).total_seconds() for s in samples)
    
    # Need 70% of window to compute
    window_size = end_sec - start_sec
    min_required = start_sec + window_size * 0.70
    if max_sample_time < min_required:
        return None, None
    
    # Actual end is min of requested and available
    actual_end = min(end_sec, int(max_sample_time))
    
    # Filter samples to segment
    t_list = []
    hr_list = []
    for s in samples:
        elapsed = (s.timestamp - t0).total_seconds()
        if start_sec <= elapsed <= actual_end:
            t_list.append(elapsed)
            hr_list.append(s.hr_value)
    
    # Need at least 70% coverage
    expected_points = actual_end - start_sec + 1
    if len(t_list) < expected_points * 0.70 or len(t_list) < 10:
        return None, None
    
    t = np.array(t_list)
    hr = np.array(hr_list)
    
    # Linear fit
    try:
        coeffs = np.polyfit(t, hr, 1)
        slope = coeffs[0]
        
        # R² for linear fit
        hr_pred = np.polyval(coeffs, t)
        ss_res = np.sum((hr - hr_pred) ** 2)
        ss_tot = np.sum((hr - np.mean(hr)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return slope, r2
        
    except Exception:
        return None, None


def compute_features(interval: RecoveryInterval, config: HRRConfig, 
                     estimated_max_hr: int = 180,
                     session_id: Optional[int] = None) -> RecoveryInterval:
    """Compute all features for a recovery interval."""
    
    # Generate peak label (e.g., "S71:p03")
    if session_id is not None:
        interval.peak_label = f"S{session_id}:p{interval.interval_order:02d}"
    
    samples = interval.samples
    if not samples:
        return interval
    
    # Detect delayed onset (catch-breath phase)
    onset_delay, onset_hr, onset_conf = detect_decline_onset(samples, config)
    interval.onset_delay_sec = onset_delay if onset_delay > 0 else None
    interval.adjusted_peak_hr = onset_hr if onset_delay > 0 else None
    interval.onset_confidence = onset_conf if onset_delay > 0 else None
    
    # Use adjusted peak for HRR calculations if onset was delayed
    effective_peak = onset_hr if onset_delay > 0 else interval.hr_peak
    
    # Build time-indexed HR lookup (from original peak, not onset)
    # NOTE: This is used for pre-R² calculations. The imputed array in R² section
    # will override hr_Xs values with extended data.
    t0 = samples[0].timestamp
    hr_at_time = {}
    for s in samples:
        elapsed = int((s.timestamp - t0).total_seconds())
        hr_at_time[elapsed] = s.hr_value
    
    # Debug: log interval details
    max_time = max(hr_at_time.keys()) if hr_at_time else 0
    logger.debug(f"Interval #{interval.interval_order}: duration={interval.duration_seconds}s, "
                f"onset={onset_delay}s, max_t={max_time}")
    
    # Normalized metrics and flags (computed here, HRR values computed in R² section)
    if interval.rhr_baseline:
        interval.hr_reserve = effective_peak - interval.rhr_baseline
        interval.is_low_signal = interval.hr_reserve < config.low_signal_threshold_bpm
    
    # Peak as % of max
    interval.peak_pct_max = effective_peak / estimated_max_hr
    
    # Exponential decay fit (from onset point, not original peak)
    # Use interval samples for tau/amplitude fit
    if onset_delay > 0 and onset_delay < len(samples):
        onset_samples = samples[onset_delay:]
    else:
        onset_samples = samples
    
    fit_result = fit_exponential_decay(onset_samples, config)
    interval.tau_seconds = fit_result.tau
    interval.tau_fit_r2 = fit_result.r2
    interval.fit_amplitude = fit_result.amplitude
    interval.fit_asymptote = fit_result.asymptote
    
    # === R² COMPUTATION (ALL WINDOWS, UNCONDITIONALLY) ===
    # Compute R² for every window where data exists. No cascade, no gating.
    # The threshold only determines which HRR DROPS to trust, not what to compute.
    
    # Get extended samples adjusted for onset
    r2_samples = interval.r2_samples if interval.r2_samples else samples
    if onset_delay > 0 and onset_delay < len(r2_samples):
        onset_r2_samples = r2_samples[onset_delay:]
    else:
        onset_r2_samples = r2_samples
    
    # DEBUG: Log sample counts
    logger.debug(f"Interval #{interval.interval_order}: samples={len(samples)}, "
                f"r2_samples={len(r2_samples)}, onset_delay={onset_delay}, "
                f"onset_r2_samples={len(onset_r2_samples)}")
    
    # Impute the full HR series ONCE (linear interpolation)
    hr_array, actual_length = impute_hr_series(onset_r2_samples, max_seconds=300)
    
    logger.debug(f"Interval #{interval.interval_order}: hr_array length={len(hr_array)}, "
                f"actual_length={actual_length}")
    
    if actual_length < 30:
        logger.debug(f"Interval #{interval.interval_order}: insufficient data after onset ({actual_length}s)")
        return interval
    
    # === HR VALUES FROM IMPUTED ARRAY ===
    def get_hr_at(sec):
        if sec < len(hr_array):
            return int(round(hr_array[sec]))
        return None
    
    interval.hr_30s = get_hr_at(30)
    interval.hr_60s = get_hr_at(60)
    interval.hr_90s = get_hr_at(90)
    interval.hr_120s = get_hr_at(120)
    interval.hr_180s = get_hr_at(180)
    interval.hr_240s = get_hr_at(240)
    interval.hr_300s = get_hr_at(300)
    interval.hr_nadir = int(np.min(hr_array[:actual_length+1])) if actual_length > 0 else None
    
    # === R² FOR ALL WINDOWS (no cascade, compute everything) ===
    interval.r2_0_30 = fit_window_r2(hr_array, 0, 30)
    interval.r2_30_60 = fit_window_r2(hr_array, 30, 60)
    interval.r2_30_90 = fit_window_r2(hr_array, 30, 90)
    interval.r2_0_60 = fit_window_r2(hr_array, 0, 60)
    interval.r2_0_120 = fit_window_r2(hr_array, 0, 120)
    interval.r2_0_180 = fit_window_r2(hr_array, 0, 180)
    interval.r2_0_240 = fit_window_r2(hr_array, 0, 240)
    interval.r2_0_300 = fit_window_r2(hr_array, 0, 300)
    
    if interval.r2_0_30 is not None and interval.r2_30_60 is not None:
        interval.r2_delta = interval.r2_0_30 - interval.r2_30_60
    
    # === DETECTED SEGMENT R² ===
    detected_duration = interval.duration_seconds - onset_delay
    if detected_duration > 30 and detected_duration <= actual_length:
        interval.r2_detected = fit_window_r2(hr_array, 0, detected_duration)
        if detected_duration < len(hr_array):
            interval.hr_detected = int(round(hr_array[detected_duration]))
            if interval.r2_detected is not None and interval.r2_detected >= R2_THRESHOLD:
                interval.hrr_detected = effective_peak - interval.hr_detected
    
    # === 90-120 SLOPE ===
    slope, slope_r2 = compute_late_slope(onset_r2_samples, 90, 120)
    interval.slope_90_120 = slope
    interval.slope_90_120_r2 = slope_r2
    
    # === HRR DROPS (R²-gated) ===
    # Compute HRR only where corresponding R² >= 0.75
    
    if interval.hr_60s is not None and interval.r2_0_60 is not None and interval.r2_0_60 >= R2_THRESHOLD:
        interval.hrr60_abs = effective_peak - interval.hr_60s
    
    if interval.hr_120s is not None and interval.r2_0_120 is not None and interval.r2_0_120 >= R2_THRESHOLD:
        interval.hrr120_abs = effective_peak - interval.hr_120s
    
    if interval.hr_180s is not None and interval.r2_0_180 is not None and interval.r2_0_180 >= R2_THRESHOLD:
        interval.hrr180_abs = effective_peak - interval.hr_180s
    
    if interval.hr_240s is not None and interval.r2_0_240 is not None and interval.r2_0_240 >= R2_THRESHOLD:
        interval.hrr240_abs = effective_peak - interval.hr_240s
    
    if interval.hr_300s is not None and interval.r2_0_300 is not None and interval.r2_0_300 >= R2_THRESHOLD:
        interval.hrr300_abs = effective_peak - interval.hr_300s
    
    # HRR30/HRR90 gated by r2_0_60 (no dedicated window)
    if interval.r2_0_60 is not None and interval.r2_0_60 >= R2_THRESHOLD:
        if interval.hr_30s is not None:
            interval.hrr30_abs = effective_peak - interval.hr_30s
        if interval.hr_90s is not None:
            interval.hrr90_abs = effective_peak - interval.hr_90s
    
    # Total drop (not gated - always useful)
    if interval.hr_nadir is not None:
        interval.total_drop = effective_peak - interval.hr_nadir
    
    # === FRACTIONAL HRR (only compute if absolute was set) ===
    if interval.hr_reserve and interval.hr_reserve > 0:
        if interval.hrr30_abs is not None:
            interval.hrr30_frac = interval.hrr30_abs / interval.hr_reserve
        if interval.hrr60_abs is not None:
            interval.hrr60_frac = interval.hrr60_abs / interval.hr_reserve
        if interval.hrr90_abs is not None:
            interval.hrr90_frac = interval.hrr90_abs / interval.hr_reserve
        if interval.hrr120_abs is not None:
            interval.hrr120_frac = interval.hrr120_abs / interval.hr_reserve
        
        # Recovery ratio (total_drop / reserve) - always compute
        if interval.total_drop is not None:
            interval.recovery_ratio = interval.total_drop / interval.hr_reserve
    
    # Linear slopes
    hr_values = np.array([s.hr_value for s in samples])
    times = np.array([(s.timestamp - t0).total_seconds() for s in samples])
    
    # Slope for first 30s
    mask_30 = times <= 30
    if np.sum(mask_30) >= 5:
        slope, _ = np.polyfit(times[mask_30], hr_values[mask_30], 1)
        interval.decline_slope_30s = slope
    
    # Slope for first 60s
    mask_60 = times <= 60
    if np.sum(mask_60) >= 10:
        slope, _ = np.polyfit(times[mask_60], hr_values[mask_60], 1)
        interval.decline_slope_60s = slope
    
    # Time to 50% recovery
    if interval.hr_reserve and interval.hr_reserve > 0:
        target_hr = interval.hr_peak - (interval.hr_reserve * 0.5)
        for i, s in enumerate(samples):
            if s.hr_value <= target_hr:
                interval.time_to_50pct_sec = int((s.timestamp - t0).total_seconds())
                break
    
    # Area under curve (first 60s)
    mask_60 = times <= 60
    if np.sum(mask_60) >= 10:
        interval.auc_60s = np.trapezoid(hr_values[mask_60], times[mask_60])
    
    # Sample quality
    interval.sample_completeness = len(samples) / interval.duration_seconds if interval.duration_seconds > 0 else 0
    interval.is_clean = interval.sample_completeness >= config.min_sample_completeness
    
    # === Quality assessment (multi-factor) ===
    interval.quality_flags = []
    interval.quality_status = 'pending'
    
    # Check segment R² quality - large delta suggests disrupted recovery
    if interval.r2_delta is not None and interval.r2_delta > 0.3:
        interval.quality_flags.append('HIGH_R2_DELTA')
    
    # Check late slope - ANY positive slope in 90-120s suggests early resumption
    # HR should still be declining or flat at this point in recovery
    if interval.slope_90_120 is not None and interval.slope_90_120 > 0:
        interval.quality_flags.append('LATE_RISE')
    
    # Low overall R² despite being saved
    if interval.tau_fit_r2 is not None and interval.tau_fit_r2 < 0.7:
        interval.quality_flags.append('LOW_R2')
    
    # Onset disagreement
    if interval.onset_confidence == 'low':
        interval.quality_flags.append('ONSET_DISAGREEMENT')
    
    # Low signal (already tracked but add to flags)
    if interval.is_low_signal:
        interval.quality_flags.append('LOW_SIGNAL')
    
    # Compute quality score (0-1)
    # Start at 1.0, deduct for issues
    score = 1.0
    if interval.tau_fit_r2:
        score *= interval.tau_fit_r2  # Weight by fit quality
    if interval.quality_flags:
        score -= 0.1 * len(interval.quality_flags)  # Penalty per flag
    interval.quality_score = max(0.0, min(1.0, score))
    
    # Set review priority based on flags
    if len(interval.quality_flags) >= 2:
        interval.review_priority = 1  # High - multiple issues
        interval.needs_review = True
    elif interval.quality_flags:
        interval.review_priority = 2  # Medium - single issue
        interval.needs_review = True
    else:
        interval.review_priority = 3  # Low - looks clean
        interval.needs_review = False  # Auto-pass if clean
    
    # Set status based on assessment
    if not interval.quality_flags:
        interval.quality_status = 'pass'
    elif any(f in interval.quality_flags for f in ['HIGH_R2_DELTA', 'LATE_RISE']):
        interval.quality_status = 'flagged'  # Needs review
    else:
        interval.quality_status = 'flagged'  # Minor issues
    
    return interval


# =============================================================================
# Summary Output
# =============================================================================

def print_summary_tables(intervals: List[RecoveryInterval], session_id: int):
    """
    Print three summary tables for quick review after processing.
    
    TABLE 1: Peaks (Identity + Context)
    TABLE 2: R² by Window (Cascade)
    TABLE 3: HRR Drops (Absolute bpm)
    """
    if not intervals:
        print("\nNo intervals to display.")
        return
    
    # Helper to format float or None
    def fmt(val, decimals=3):
        if val is None:
            return '-'
        return f"{val:.{decimals}f}"
    
    def fmt_int(val):
        if val is None:
            return '-'
        return str(int(val))
    
    # Separator
    print(f"\n{'='*80}")
    print(f"SESSION {session_id} - HRR SUMMARY ({len(intervals)} intervals)")
    print(f"{'='*80}")
    
    # TABLE 1: Peaks
    print(f"\n--- TABLE 1: Peaks ---")
    print(f"{'Ord':>3} {'Label':>10} {'Peak':>4} {'Dur':>4} {'Onset':>5} {'Conf':>6} {'Status':>8}")
    print(f"{'-'*3:>3} {'-'*10:>10} {'-'*4:>4} {'-'*4:>4} {'-'*5:>5} {'-'*6:>6} {'-'*8:>8}")
    for i in intervals:
        onset = fmt_int(i.onset_delay_sec) if i.onset_delay_sec else '-'
        conf = i.onset_confidence[:3] if i.onset_confidence else '-'
        print(f"{i.interval_order:>3} {i.peak_label:>10} {i.hr_peak:>4} {i.duration_seconds:>4} {onset:>5} {conf:>6} {i.quality_status:>8}")
    
    # TABLE 2: R² by Window
    print(f"\n--- TABLE 2: R² by Window ---")
    print(f"{'Ord':>3} {'0-30':>6} {'0-60':>6} {'30-90':>6} {'slp90':>7} {'0-120':>6} {'0-180':>6} {'0-240':>6} {'0-300':>6} {'Det':>6}")
    print(f"{'-'*3:>3} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*7:>7} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6}")
    for i in intervals:
        # Mark failures with * if < 0.75
        def mark(val):
            if val is None:
                return '-'
            s = f"{val:.3f}"
            if val < 0.75:
                return s + '*'
            return s
        
        def fmt_slope(val):
            if val is None:
                return '-'
            return f"{val:+.3f}"  # Show sign
        
        print(f"{i.interval_order:>3} {mark(i.r2_0_30):>6} {mark(i.r2_0_60):>6} {mark(i.r2_30_90):>6} {fmt_slope(i.slope_90_120):>7} {mark(i.r2_0_120):>6} {mark(i.r2_0_180):>6} {mark(i.r2_0_240):>6} {mark(i.r2_0_300):>6} {mark(i.r2_detected):>6}")
    print(f"  (* = below 0.75, slp90 = 90-120s slope bpm/sec, Det = detected segment R²)")
    
    # TABLE 3: HRR Drops
    print(f"\n--- TABLE 3: HRR Drops (bpm) ---")
    print(f"{'Ord':>3} {'Peak':>4} {'HRR60':>6} {'HRR120':>6} {'HRR180':>6} {'HRR240':>6} {'HRR300':>6} {'HRRdet':>6} {'Total':>6}")
    print(f"{'-'*3:>3} {'-'*4:>4} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*6:>6}")
    for i in intervals:
        print(f"{i.interval_order:>3} {i.hr_peak:>4} {fmt_int(i.hrr60_abs):>6} {fmt_int(i.hrr120_abs):>6} {fmt_int(i.hrr180_abs):>6} {fmt_int(i.hrr240_abs):>6} {fmt_int(i.hrr300_abs):>6} {fmt_int(i.hrr_detected):>6} {fmt_int(i.total_drop):>6}")
    
    print(f"{'='*80}\n")


# =============================================================================
# Main Pipeline
# =============================================================================

def process_session(conn, session_id: int, source: str, 
                    config: HRRConfig, dry_run: bool = False,
                    include_rejected: bool = False) -> int:
    """Process a single session, return number of intervals detected."""
    
    logger.info(f"Processing {source} session {session_id}")
    
    # Load samples
    samples = get_hr_samples(conn, session_id, source)
    if not samples:
        logger.warning(f"No HR samples found for session {session_id}")
        return 0
    
    logger.info(f"Loaded {len(samples)} HR samples")
    
    # Get RHR for session date
    session_date = samples[0].timestamp
    rhr = get_rhr_for_date(conn, session_date)
    if rhr is None:
        rhr = 60  # Default fallback
        logger.warning(f"No RHR found for {session_date.date()}, using default {rhr}")
    else:
        logger.info(f"Using RHR={rhr} for {session_date.date()}")
    
    # Detect intervals
    intervals = detect_recovery_intervals(samples, rhr, config)
    
    # Compute features for each interval
    for interval in intervals:
        compute_features(interval, config, session_id=session_id)
    
    # Filter by quality
    valid_intervals, noise_intervals, rejected_intervals = filter_quality_intervals(intervals, config)
    
    logger.info(f"Classification: {len(intervals)} raw -> {len(valid_intervals)} valid, {len(noise_intervals)} noise, {len(rejected_intervals)} rejected")
    
    # Decide which to save (valid only by default)
    intervals_to_save = valid_intervals
    if include_rejected:
        intervals_to_save = intervals  # Save all for analysis
    
    # Save to database
    save_intervals(conn, intervals_to_save, session_id, source, dry_run)
    
    # Print summary tables (always, unless dry_run)
    if not dry_run:
        print_summary_tables(intervals_to_save, session_id)
    
    # Log summary
    if valid_intervals:
        hrr60_values = [i.hrr60_abs for i in valid_intervals if i.hrr60_abs is not None]
        tau_values = [i.tau_seconds for i in valid_intervals if i.tau_seconds is not None and i.tau_seconds < 300]
        
        logger.info(f"Valid intervals summary:")
        logger.info(f"  Count: {len(valid_intervals)}")
        if hrr60_values:
            logger.info(f"  HRR60_abs: mean={np.mean(hrr60_values):.1f}, range={min(hrr60_values)}-{max(hrr60_values)}")
        if tau_values:
            logger.info(f"  Tau (valid fits): mean={np.mean(tau_values):.1f}s, range={min(tau_values):.1f}-{max(tau_values):.1f}")
        
        low_signal = sum(1 for i in valid_intervals if i.is_low_signal)
        if low_signal:
            logger.info(f"  Low signal intervals: {low_signal}")
    
    if dry_run:
        if noise_intervals:
            logger.info(f"Noise intervals (floor effect, would not be saved):")
            for interval in noise_intervals:
                logger.info(f"  - #{interval.interval_order}: peak={interval.hr_peak}, reserve={interval.hr_reserve}, {interval._reject_reason}")
        
        if rejected_intervals:
            logger.info(f"Rejected intervals (insufficient recovery, would not be saved):")
            for interval in rejected_intervals:
                ratio_str = f'{interval.recovery_ratio:.0%}' if interval.recovery_ratio else 'N/A'
                logger.info(f"  - #{interval.interval_order}: peak={interval.hr_peak}, hrr60={interval.hrr60_abs}, ratio={ratio_str}, {interval._reject_reason}")
    
    return len(valid_intervals)


def process_session_for_export(conn, session_id: int, source: str, 
                                config: HRRConfig) -> Tuple[List[RecoveryInterval], List[RecoveryInterval], List[RecoveryInterval], List[RecoveryInterval]]:
    """
    Process session and return interval lists (for CSV export).
    Returns (all_intervals, valid, noise, rejected).
    """
    logger.debug(f"Processing {source} session {session_id} for export")
    
    # Load samples
    samples = get_hr_samples(conn, session_id, source)
    if not samples:
        logger.warning(f"No HR samples found for session {session_id}")
        return [], [], [], []
    
    # Get RHR for session date
    session_date = samples[0].timestamp
    rhr = get_rhr_for_date(conn, session_date)
    if rhr is None:
        rhr = 60  # Default fallback
    
    # Detect intervals
    intervals = detect_recovery_intervals(samples, rhr, config)
    
    # Compute features for each interval
    for interval in intervals:
        compute_features(interval, config, session_id=session_id)
    
    # Filter by quality
    valid, noise, rejected = filter_quality_intervals(intervals, config)
    
    logger.debug(f"Session {session_id}: {len(intervals)} raw -> {len(valid)} valid, {len(noise)} noise, {len(rejected)} rejected")
    
    return intervals, valid, noise, rejected


def export_intervals_to_csv(all_intervals: List[Tuple[int, str, RecoveryInterval, str]], 
                            output_path: str):
    """Export all intervals to CSV for analysis.
    
    all_intervals: List of (session_id, source, interval, classification) tuples
    classification: 'valid', 'noise', or 'rejected'
    """
    import csv
    
    fieldnames = [
        'session_id', 'source', 'classification', 'reject_reason',
        'peak_label', 'interval_order', 'start_time', 'duration_seconds',
        'hr_peak', 'hr_60s', 'hr_nadir', 'rhr_baseline',
        'hrr60_abs', 'hrr60_frac', 'total_drop', 'hr_reserve', 'recovery_ratio',
        'tau_seconds', 'tau_fit_r2', 'fit_amplitude', 'fit_asymptote',
        'r2_0_30', 'r2_30_60', 'r2_delta',
        'slope_90_120', 'slope_90_120_r2',
        'onset_delay_sec', 'onset_confidence',
        'quality_status', 'quality_flags', 'quality_score', 'review_priority',
        'sustained_effort_sec', 'effort_avg_hr', 'session_elapsed_min',
        'sample_completeness', 'is_clean', 'is_low_signal'
    ]
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for session_id, source, interval, classification in all_intervals:
            row = {
                'session_id': session_id,
                'source': source,
                'classification': classification,
                'reject_reason': getattr(interval, '_reject_reason', None),
                'peak_label': interval.peak_label,
                'interval_order': interval.interval_order,
                'start_time': interval.start_time.isoformat() if interval.start_time else None,
                'duration_seconds': interval.duration_seconds,
                'hr_peak': interval.hr_peak,
                'hr_60s': interval.hr_60s,
                'hr_nadir': interval.hr_nadir,
                'rhr_baseline': interval.rhr_baseline,
                'hrr60_abs': interval.hrr60_abs,
                'hrr60_frac': round(interval.hrr60_frac, 4) if interval.hrr60_frac else None,
                'total_drop': interval.total_drop,
                'hr_reserve': interval.hr_reserve,
                'recovery_ratio': round(interval.recovery_ratio, 4) if interval.recovery_ratio else None,
                'tau_seconds': round(interval.tau_seconds, 1) if interval.tau_seconds else None,
                'tau_fit_r2': round(interval.tau_fit_r2, 4) if interval.tau_fit_r2 else None,
                'fit_amplitude': round(interval.fit_amplitude, 2) if interval.fit_amplitude else None,
                'fit_asymptote': round(interval.fit_asymptote, 2) if interval.fit_asymptote else None,
                'r2_0_30': round(interval.r2_0_30, 4) if interval.r2_0_30 else None,
                'r2_30_60': round(interval.r2_30_60, 4) if interval.r2_30_60 else None,
                'r2_delta': round(interval.r2_delta, 4) if interval.r2_delta else None,
                'slope_90_120': round(interval.slope_90_120, 4) if interval.slope_90_120 else None,
                'slope_90_120_r2': round(interval.slope_90_120_r2, 4) if interval.slope_90_120_r2 else None,
                'onset_delay_sec': interval.onset_delay_sec,
                'onset_confidence': interval.onset_confidence,
                'quality_status': interval.quality_status,
                'quality_flags': '|'.join(interval.quality_flags) if interval.quality_flags else None,
                'quality_score': round(interval.quality_score, 4) if interval.quality_score else None,
                'review_priority': interval.review_priority,
                'sustained_effort_sec': interval.sustained_effort_sec,
                'effort_avg_hr': interval.effort_avg_hr,
                'session_elapsed_min': interval.session_elapsed_min,
                'sample_completeness': round(interval.sample_completeness, 4) if interval.sample_completeness else None,
                'is_clean': interval.is_clean,
                'is_low_signal': interval.is_low_signal
            }
            writer.writerow(row)
    
    logger.info(f"Exported {len(all_intervals)} intervals to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Extract HRR features from HR samples')
    parser.add_argument('--session-id', type=int, help='Process specific session')
    parser.add_argument('--source', choices=['endurance', 'polar'], default='endurance',
                        help='Session source type')
    parser.add_argument('--all', action='store_true', help='Process all unprocessed sessions')
    parser.add_argument('--reprocess', action='store_true', help='Reprocess all sessions (including already processed)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--export-csv', type=str, metavar='PATH',
                        help='Export all intervals to CSV (includes rejected for analysis)')
    parser.add_argument('--include-rejected', action='store_true', 
                        help='Include rejected intervals in output (for analysis)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    config = HRRConfig()
    
    conn = get_db_connection()
    
    # For CSV export, collect all intervals
    all_intervals_for_export = []  # (session_id, source, interval, classification)
    
    try:
        total_intervals = 0
        total_raw = 0
        
        if args.session_id:
            # Process single session
            if args.export_csv:
                # Run extraction and collect for CSV
                intervals, valid, noise, rejected = process_session_for_export(
                    conn, args.session_id, args.source, config)
                for i in valid:
                    all_intervals_for_export.append((args.session_id, args.source, i, 'valid'))
                for i in noise:
                    all_intervals_for_export.append((args.session_id, args.source, i, 'noise'))
                for i in rejected:
                    all_intervals_for_export.append((args.session_id, args.source, i, 'rejected'))
                total_intervals = len(valid)
                total_raw = len(intervals)
            else:
                total_intervals = process_session(conn, args.session_id, args.source, 
                                                  config, args.dry_run, args.include_rejected)
        
        elif args.all or args.reprocess:
            # Process sessions for both sources
            for source in ['endurance', 'polar']:
                if args.reprocess:
                    sessions = get_all_sessions(conn, source)
                    logger.info(f"Found {len(sessions)} total {source} sessions (reprocess mode)")
                else:
                    sessions = get_sessions_to_process(conn, source)
                    logger.info(f"Found {len(sessions)} unprocessed {source} sessions")
                
                for session_id, session_start in sessions:
                    if args.export_csv:
                        intervals, valid, noise, rejected = process_session_for_export(
                            conn, session_id, source, config)
                        for i in valid:
                            all_intervals_for_export.append((session_id, source, i, 'valid'))
                        for i in noise:
                            all_intervals_for_export.append((session_id, source, i, 'noise'))
                        for i in rejected:
                            all_intervals_for_export.append((session_id, source, i, 'rejected'))
                        total_intervals += len(valid)
                        total_raw += len(intervals)
                    else:
                        n = process_session(conn, session_id, source, config, 
                                           args.dry_run, args.include_rejected)
                        total_intervals += n
        
        else:
            parser.print_help()
            return
        
        # Export to CSV if requested
        if args.export_csv:
            export_intervals_to_csv(all_intervals_for_export, args.export_csv)
            logger.info(f"Summary: {total_raw} raw intervals -> {total_intervals} valid")
            logger.info(f"Classification breakdown:")
            valid_count = sum(1 for x in all_intervals_for_export if x[3] == 'valid')
            noise_count = sum(1 for x in all_intervals_for_export if x[3] == 'noise')
            rejected_count = sum(1 for x in all_intervals_for_export if x[3] == 'rejected')
            logger.info(f"  Valid: {valid_count}")
            logger.info(f"  Noise: {noise_count}")
            logger.info(f"  Rejected: {rejected_count}")
        else:
            logger.info(f"Total valid intervals detected: {total_intervals}")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
