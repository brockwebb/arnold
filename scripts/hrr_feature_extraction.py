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


def filter_quality_intervals(intervals: List[RecoveryInterval], 
                             config: HRRConfig) -> Tuple[List[RecoveryInterval], List[RecoveryInterval], List[RecoveryInterval]]:
    """
    Filter intervals by quality using computed features.
    Returns (valid_intervals, noise_intervals, rejected_intervals).
    
    Uses simple threshold gates on pre-computed features:
    1. Sufficient samples
    2. Sufficient signal (hr_reserve)
    3. Sufficient drop (hrr60_abs)
    4. Valid decay curve (tau or recovery_ratio)
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
        if interval.hr_nadir is not None:
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
        
        # Passed all gates
        interval._reject_reason = None
        valid.append(interval)
    
    return valid, noise, rejected


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
    hr_nadir: Optional[int] = None
    rhr_baseline: Optional[int] = None
    
    # Absolute metrics
    hrr30_abs: Optional[int] = None
    hrr60_abs: Optional[int] = None
    hrr90_abs: Optional[int] = None
    hrr120_abs: Optional[int] = None
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
    
    # Raw samples (not stored, used for computation)
    samples: List[HRSample] = field(default_factory=list)


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
        'hr_peak', 'hr_30s', 'hr_60s', 'hr_90s', 'hr_120s', 'hr_nadir', 'rhr_baseline',
        'hrr30_abs', 'hrr60_abs', 'hrr90_abs', 'hrr120_abs', 'total_drop',
        'hr_reserve', 'hrr30_frac', 'hrr60_frac', 'hrr90_frac', 'hrr120_frac',
        'recovery_ratio', 'peak_pct_max',
        'tau_seconds', 'tau_fit_r2', 'decline_slope_30s', 'decline_slope_60s',
        'time_to_50pct_sec', 'auc_60s',
        'sustained_effort_sec', 'effort_avg_hr', 'session_elapsed_min',
        'sample_count', 'expected_sample_count', 'sample_completeness',
        'is_clean', 'is_low_signal'
    ]
    
    values = []
    for interval in intervals:
        values.append((
            session_id,
            interval.start_time, interval.end_time, interval.duration_seconds, interval.interval_order,
            interval.hr_peak, interval.hr_30s, interval.hr_60s, interval.hr_90s, interval.hr_120s,
            interval.hr_nadir, interval.rhr_baseline,
            interval.hrr30_abs, interval.hrr60_abs, interval.hrr90_abs, interval.hrr120_abs,
            interval.total_drop,
            interval.hr_reserve, interval.hrr30_frac, interval.hrr60_frac, interval.hrr90_frac,
            interval.hrr120_frac, interval.recovery_ratio, interval.peak_pct_max,
            interval.tau_seconds, interval.tau_fit_r2, interval.decline_slope_30s,
            interval.decline_slope_60s, interval.time_to_50pct_sec, interval.auc_60s,
            interval.sustained_effort_sec, interval.effort_avg_hr, interval.session_elapsed_min,
            interval.sample_count, interval.expected_sample_count, interval.sample_completeness,
            interval.is_clean, interval.is_low_signal
        ))
    
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


def detect_decline_interval(samples: List[HRSample], peak_idx: int,
                            config: HRRConfig) -> Optional[Tuple[int, int]]:
    """
    Scan forward from peak to find recovery interval.
    Ends at nadir (lowest point), not after HR starts rising.
    Returns (end_idx, duration_sec) or None if no valid interval.
    """
    if peak_idx >= len(samples) - 30:
        return None
    
    peak_hr = samples[peak_idx].hr_value
    peak_time = samples[peak_idx].timestamp
    
    # Find nadir within max window
    nadir_hr = peak_hr
    nadir_idx = peak_idx
    
    for i in range(peak_idx + 1, len(samples)):
        elapsed = (samples[i].timestamp - peak_time).total_seconds()
        
        if elapsed > config.max_interval_duration_sec:
            break
        
        hr = samples[i].hr_value
        
        # Track the lowest point
        if hr < nadir_hr:
            nadir_hr = hr
            nadir_idx = i
        
        # If HR rises significantly above nadir, we've passed the recovery
        # Stop searching but use nadir_idx as the end
        if hr > nadir_hr + config.decline_tolerance_bpm:
            break
    
    # End at nadir, not at the point where we detected the rise
    end_idx = nadir_idx
    duration = (samples[end_idx].timestamp - peak_time).total_seconds()
    
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
        interval_samples = samples[peak_idx:end_idx + 1]
        
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


def fit_exponential_decay(samples: List[HRSample], config: HRRConfig) -> Tuple[Optional[float], Optional[float]]:
    """
    Fit exponential decay to HR samples.
    Returns (tau, r_squared) or (None, None) if fit fails.
    """
    if len(samples) < config.tau_min_points:
        return None, None
    
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
        
        if r2 >= config.tau_min_r2:
            return tau, r2
        else:
            return None, r2
            
    except Exception as e:
        logger.debug(f"Exponential fit failed: {e}")
        return None, None


def compute_features(interval: RecoveryInterval, config: HRRConfig, 
                     estimated_max_hr: int = 180) -> RecoveryInterval:
    """Compute all features for a recovery interval."""
    
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
    t0 = samples[0].timestamp
    hr_at_time = {}
    for s in samples:
        elapsed = int((s.timestamp - t0).total_seconds())
        hr_at_time[elapsed] = s.hr_value
    
    # HR at specific timepoints (adjusted for onset delay)
    # If onset_delay=15s, then "60s of recovery" means t=75s from peak
    target_60s = 60 + onset_delay
    interval.hr_30s = hr_at_time.get(30 + onset_delay)
    interval.hr_60s = hr_at_time.get(target_60s)
    interval.hr_90s = hr_at_time.get(90 + onset_delay)
    interval.hr_120s = hr_at_time.get(120 + onset_delay)
    interval.hr_nadir = min(s.hr_value for s in samples)
    
    # Debug: log interval details
    max_time = max(hr_at_time.keys()) if hr_at_time else 0
    logger.debug(f"Interval #{interval.interval_order}: duration={interval.duration_seconds}s, "
                f"onset={onset_delay}s, target_60s=t{target_60s}, max_t={max_time}, "
                f"hr_60s={interval.hr_60s}, nadir={interval.hr_nadir}")
    
    # Absolute drops (from effective peak, accounting for onset)
    if interval.hr_30s:
        interval.hrr30_abs = effective_peak - interval.hr_30s
    if interval.hr_60s:
        interval.hrr60_abs = effective_peak - interval.hr_60s
    if interval.hr_90s:
        interval.hrr90_abs = effective_peak - interval.hr_90s
    if interval.hr_120s:
        interval.hrr120_abs = effective_peak - interval.hr_120s
    
    interval.total_drop = effective_peak - interval.hr_nadir
    
    # Normalized metrics (use effective peak for reserve calculation)
    if interval.rhr_baseline:
        interval.hr_reserve = effective_peak - interval.rhr_baseline
        
        if interval.hr_reserve > 0:
            if interval.hrr30_abs:
                interval.hrr30_frac = interval.hrr30_abs / interval.hr_reserve
            if interval.hrr60_abs:
                interval.hrr60_frac = interval.hrr60_abs / interval.hr_reserve
            if interval.hrr90_abs:
                interval.hrr90_frac = interval.hrr90_abs / interval.hr_reserve
            if interval.hrr120_abs:
                interval.hrr120_frac = interval.hrr120_abs / interval.hr_reserve
            
            interval.recovery_ratio = interval.total_drop / interval.hr_reserve
        
        # Low signal flag
        interval.is_low_signal = interval.hr_reserve < config.low_signal_threshold_bpm
    
    # Peak as % of max
    interval.peak_pct_max = effective_peak / estimated_max_hr
    
    # Exponential decay fit (from onset point, not original peak)
    if onset_delay > 0 and onset_delay < len(samples):
        onset_samples = samples[onset_delay:]
    else:
        onset_samples = samples
    
    tau, r2 = fit_exponential_decay(onset_samples, config)
    interval.tau_seconds = tau
    interval.tau_fit_r2 = r2
    
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
    
    # Quality assessment
    interval.sample_completeness = len(samples) / interval.duration_seconds if interval.duration_seconds > 0 else 0
    interval.is_clean = interval.sample_completeness >= config.min_sample_completeness
    
    return interval


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
        compute_features(interval, config)
    
    # Filter by quality
    valid_intervals, noise_intervals, rejected_intervals = filter_quality_intervals(intervals, config)
    
    logger.info(f"Classification: {len(intervals)} raw -> {len(valid_intervals)} valid, {len(noise_intervals)} noise, {len(rejected_intervals)} rejected")
    
    # Decide which to save (valid only by default)
    intervals_to_save = valid_intervals
    if include_rejected:
        intervals_to_save = intervals  # Save all for analysis
    
    # Save to database
    save_intervals(conn, intervals_to_save, session_id, source, dry_run)
    
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


def main():
    parser = argparse.ArgumentParser(description='Extract HRR features from HR samples')
    parser.add_argument('--session-id', type=int, help='Process specific session')
    parser.add_argument('--source', choices=['endurance', 'polar'], default='endurance',
                        help='Session source type')
    parser.add_argument('--all', action='store_true', help='Process all unprocessed sessions')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--include-rejected', action='store_true', 
                        help='Include rejected intervals in output (for analysis)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    config = HRRConfig()
    
    conn = get_db_connection()
    
    try:
        total_intervals = 0
        
        if args.session_id:
            # Process single session
            total_intervals = process_session(conn, args.session_id, args.source, 
                                              config, args.dry_run, args.include_rejected)
        
        elif args.all:
            # Process all unprocessed sessions for both sources
            for source in ['endurance', 'polar']:
                sessions = get_sessions_to_process(conn, source)
                logger.info(f"Found {len(sessions)} unprocessed {source} sessions")
                
                for session_id, session_start in sessions:
                    n = process_session(conn, session_id, source, config, 
                                       args.dry_run, args.include_rejected)
                    total_intervals += n
        
        else:
            parser.print_help()
            return
        
        logger.info(f"Total valid intervals detected: {total_intervals}")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
