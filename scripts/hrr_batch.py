#!/usr/bin/env python3
"""
HRR Batch Processor - Extract all intervals across all sessions

Outputs comprehensive DataFrame with:
- Session metadata (id, date, duration)
- Interval features (peak_hr, nadir_hr, HRR30/60/120)
- Derived ratios (HRR30/HRR60, HRR60/HRR120, etc.)
- Fit quality (R², tau)
- Normalized metrics (HRR as % of peak, recovery rate)

Usage:
    python scripts/hrr_batch.py --output /tmp/hrr_all.csv
    python scripts/hrr_batch.py --output /tmp/hrr_all.csv --plot-beeswarm
    python scripts/hrr_batch.py --write-db --clear-existing  # Full backfill to Postgres
"""

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy.signal import find_peaks
from scipy.ndimage import median_filter
from scipy.optimize import curve_fit

import sys
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Add src to path for imports
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

try:
    from arnold.hrr.detect import compute_confidence, compute_weighted_value, detect_ewma_alerts, detect_cusum_alerts
    HAS_DETECT = True
except ImportError:
    HAS_DETECT = False
    def compute_confidence(*args, **kwargs): return None
    def compute_weighted_value(*args, **kwargs): return None
    def detect_ewma_alerts(*args, **kwargs): return None, []
    def detect_cusum_alerts(*args, **kwargs): return None, []

# Load HRR defaults config
HRR_CONFIG_PATH = PROJECT_ROOT / 'config' / 'hrr_defaults.json'
HRR_DEFAULTS = {}
if HRR_CONFIG_PATH.exists():
    with open(HRR_CONFIG_PATH) as f:
        HRR_DEFAULTS = json.load(f)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class Config:
    smooth_kernel: int = 5
    peak_prominence: float = 5.0
    peak_distance: int = 10
    
    # Initial descent test
    descent_window: int = 15
    descent_min_r2: float = 0.5
    
    # Extension
    max_rise_from_nadir: float = 3.0
    max_plateau_sec: int = 5
    
    # Quality gates (from config)
    min_hrr60: float = HRR_DEFAULTS.get('min_effort_bpm', 9.0)
    min_r2_60: float = 0.7  # For "high quality" flag
    min_tau_r2: float = HRR_DEFAULTS.get('min_tau_r2', 0.6)
    tau_cap: float = HRR_DEFAULTS.get('tau_cap_seconds', 300)
    
    # Effort filtering
    min_effort_bpm: float = HRR_DEFAULTS.get('min_effort_bpm', 5.0)
    use_local_baseline: bool = HRR_DEFAULTS.get('use_local_baseline', True)
    fallback_to_session_min: bool = HRR_DEFAULTS.get('fallback_to_session_min', True)
    
    # Actionable thresholds
    single_event_actionable_bpm: float = HRR_DEFAULTS.get('single_event_actionable_bpm', 13.0)
    exceptional_bpm: float = HRR_DEFAULTS.get('exceptional_bpm', 18.0)
    hrr_frac_actionable: float = HRR_DEFAULTS.get('hrr_frac_actionable', 0.3)
    
    # Window requirements
    min_window_seconds: int = HRR_DEFAULTS.get('min_window_seconds', 120)
    include_truncated_windows: bool = HRR_DEFAULTS.get('defaults', {}).get('include_truncated_windows', False)


@dataclass
class HRRInterval:
    """Comprehensive HRR interval with all metrics."""
    # Session context
    session_id: int
    session_date: datetime
    session_duration_min: float
    
    # Interval timing
    peak_idx: int
    peak_time_sec: float
    peak_time_min: float
    duration_sec: int
    end_reason: str
    
    # Raw HR values
    peak_hr: float
    nadir_hr: float
    nadir_idx: int
    
    # Fields with defaults below
    sport_type: str = 'UNKNOWN'  # For stratification
    hr_at_30: Optional[float] = None
    hr_at_60: Optional[float] = None
    hr_at_120: Optional[float] = None
    hr_at_180: Optional[float] = None
    hr_at_240: Optional[float] = None
    hr_at_300: Optional[float] = None
    
    # Baseline/resting context
    session_min_hr: Optional[float] = None      # Minimum HR in session (5th percentile)
    local_baseline_hr: Optional[float] = None   # Median HR from -180s to -60s before peak
    peak_minus_session_min: Optional[float] = None   # peak_hr - session_min_hr
    peak_minus_local: Optional[float] = None    # peak_hr - local_baseline_hr (preferred)
    
    # Absolute HRR values
    hrr30: Optional[float] = None
    hrr60: Optional[float] = None
    hrr120: Optional[float] = None
    hrr180: Optional[float] = None
    hrr240: Optional[float] = None
    hrr300: Optional[float] = None
    total_drop: Optional[float] = None  # peak - nadir
    
    # Ratios (literature-standard)
    ratio_30_60: Optional[float] = None      # HRR30/HRR60 - fast phase proportion
    ratio_60_120: Optional[float] = None     # HRR60/HRR120 - sustained recovery
    ratio_30_total: Optional[float] = None   # HRR30/total_drop - early recovery %
    ratio_60_total: Optional[float] = None   # HRR60/total_drop - mid recovery %
    
    # Normalized metrics
    hrr60_pct_peak: Optional[float] = None   # HRR60 as % of peak HR
    hrr_frac: Optional[float] = None         # HRR60 / effort - normalized recovery signal
    recovery_rate_30: Optional[float] = None  # bpm/sec over first 30s
    recovery_rate_60: Optional[float] = None  # bpm/sec over first 60s
    early_slope: Optional[float] = None       # Linear slope over first 15s (bpm/sec, negative = good)
    auc_0_60: Optional[float] = None          # Area under curve 0-60s (bpm·sec above nadir)
    
    # Exponential fit
    tau: Optional[float] = None              # Time constant
    tau_censored: bool = False               # True if tau hit upper bound (600s)
    r2_30: Optional[float] = None
    r2_60: Optional[float] = None
    r2_120: Optional[float] = None
    r2_180: Optional[float] = None
    r2_240: Optional[float] = None
    r2_300: Optional[float] = None
    
    # Half-recovery time (T50)
    t50: Optional[float] = None              # Seconds to reach 50% of total drop
    
    # Confidence & weighting (for trend detection)
    confidence: Optional[float] = None       # 0-1 score based on effort, fit, window
    weighted_value: Optional[float] = None   # HRR60 * confidence (for EWMA/CUSUM)
    
    # Quality flags
    valid: bool = False
    high_quality: bool = False  # R² >= 0.7 AND HRR60 >= 9
    truncated_window: bool = False  # Recovery window ended before full decay (duration < 120 and not reached_120)


# =============================================================================
# Database and Loading
# =============================================================================

def get_db_connection():
    dsn = os.getenv('POSTGRES_DSN', 'postgresql://brock@localhost:5432/arnold_analytics')
    return psycopg2.connect(dsn)


def classify_stratum(sport_type: str) -> str:
    """Classify sport type into stratum for per-context baselines."""
    s = str(sport_type).upper()
    if 'RUN' in s or 'WALK' in s:
        return 'ENDURANCE'
    elif 'STRENGTH' in s or 'CROSS' in s or 'CIRCUIT' in s:
        return 'STRENGTH'
    else:
        return 'OTHER'


def write_intervals_to_db(df: pd.DataFrame, conn, clear_existing: bool = False, session_ids: List[int] = None) -> int:
    """
    Write HRR intervals to hr_recovery_intervals table.
    
    If session_ids provided with clear_existing, only clears those sessions.
    Returns number of rows inserted.
    """
    if len(df) == 0:
        return 0
    
    cur = conn.cursor()
    
    if clear_existing:
        if session_ids:
            # Only clear specified sessions
            cur.execute("DELETE FROM hr_recovery_intervals WHERE polar_session_id = ANY(%s)", (session_ids,))
            print(f"Cleared existing rows for session(s) {session_ids}")
        else:
            cur.execute("DELETE FROM hr_recovery_intervals")
            print(f"Cleared ALL existing rows from hr_recovery_intervals")
    
    # Prepare data with new columns
    inserted = 0
    
    for _, row in df.iterrows():
        # Compute stratum
        stratum = classify_stratum(row.get('sport_type', 'UNKNOWN'))
        
        # Compute actionable flag (R² >= 0.75)
        r2_60 = row.get('r2_60')
        actionable = r2_60 is not None and r2_60 >= 0.75
        
        # Get session date as start_time
        session_date = row.get('session_date')
        peak_idx = row.get('peak_idx', 0)
        
        # Calculate start_time from session_date + peak_idx seconds
        if isinstance(session_date, str):
            session_date = pd.to_datetime(session_date)
        start_time = session_date + pd.Timedelta(seconds=peak_idx)
        end_time = start_time + pd.Timedelta(seconds=row.get('duration_sec', 60))
        
        # Insert row
        cur.execute("""
            INSERT INTO hr_recovery_intervals (
                polar_session_id,
                start_time,
                end_time,
                duration_seconds,
                interval_order,
                hr_peak,
                hr_30s,
                hr_60s,
                hr_120s,
                hr_180s,
                hr_240s,
                hr_300s,
                hr_nadir,
                hrr30_abs,
                hrr60_abs,
                hrr120_abs,
                hrr180_abs,
                hrr240_abs,
                hrr300_abs,
                total_drop,
                hrr60_frac,
                tau_seconds,
                tau_fit_r2,
                tau_censored,
                r2_180,
                r2_240,
                r2_300,
                decline_slope_60s,
                auc_60s,
                session_type,
                is_clean,
                is_low_signal,
                -- New columns from migration 014
                confidence,
                weighted_hrr60,
                actionable,
                recovery_posture,
                protocol_type,
                stratum,
                local_baseline_hr,
                peak_minus_local,
                early_slope
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            row.get('session_id'),
            start_time,
            end_time,
            row.get('duration_sec'),
            None,  # interval_order - could compute later
            int(row['peak_hr']) if pd.notna(row.get('peak_hr')) else None,
            int(row['hr_at_30']) if pd.notna(row.get('hr_at_30')) else None,
            int(row['hr_at_60']) if pd.notna(row.get('hr_at_60')) else None,
            int(row['hr_at_120']) if pd.notna(row.get('hr_at_120')) else None,
            int(row['hr_at_180']) if pd.notna(row.get('hr_at_180')) else None,
            int(row['hr_at_240']) if pd.notna(row.get('hr_at_240')) else None,
            int(row['hr_at_300']) if pd.notna(row.get('hr_at_300')) else None,
            int(row['nadir_hr']) if pd.notna(row.get('nadir_hr')) else None,
            int(row['hrr30']) if pd.notna(row.get('hrr30')) else None,
            int(row['hrr60']) if pd.notna(row.get('hrr60')) else None,
            int(row['hrr120']) if pd.notna(row.get('hrr120')) else None,
            int(row['hrr180']) if pd.notna(row.get('hrr180')) else None,
            int(row['hrr240']) if pd.notna(row.get('hrr240')) else None,
            int(row['hrr300']) if pd.notna(row.get('hrr300')) else None,
            int(row['total_drop']) if pd.notna(row.get('total_drop')) else None,
            float(row['hrr_frac']) if pd.notna(row.get('hrr_frac')) else None,
            float(row['tau']) if pd.notna(row.get('tau')) else None,
            float(row['r2_60']) if pd.notna(row.get('r2_60')) else None,
            row.get('tau_censored', False),
            float(row['r2_180']) if pd.notna(row.get('r2_180')) else None,
            float(row['r2_240']) if pd.notna(row.get('r2_240')) else None,
            float(row['r2_300']) if pd.notna(row.get('r2_300')) else None,
            float(row['recovery_rate_60']) if pd.notna(row.get('recovery_rate_60')) else None,
            float(row['auc_0_60']) if pd.notna(row.get('auc_0_60')) else None,
            row.get('sport_type', 'UNKNOWN'),
            row.get('high_quality', False),  # is_clean
            row.get('peak_minus_local', 100) < 25 if pd.notna(row.get('peak_minus_local')) else False,  # is_low_signal
            # New columns
            float(row['confidence']) if pd.notna(row.get('confidence')) else None,
            float(row['weighted_value']) if pd.notna(row.get('weighted_value')) else None,
            actionable,
            'standing',  # Default for inter-set recovery
            'inter_set',  # Default protocol type
            stratum,
            int(row['local_baseline_hr']) if pd.notna(row.get('local_baseline_hr')) else None,
            int(row['peak_minus_local']) if pd.notna(row.get('peak_minus_local')) else None,
            float(row['early_slope']) if pd.notna(row.get('early_slope')) else None,
        ))
        inserted += 1
    
    conn.commit()
    cur.close()
    
    return inserted


def get_all_sessions(conn) -> List[dict]:
    """Get all sessions with HR data."""
    query = """
        SELECT 
            hs.session_id,
            MIN(hs.sample_time) as start_time,
            MAX(hs.sample_time) as end_time,
            COUNT(*) as sample_count,
            EXTRACT(EPOCH FROM (MAX(hs.sample_time) - MIN(hs.sample_time)))/60 as duration_min,
            ps.sport_type
        FROM hr_samples hs
        LEFT JOIN polar_sessions ps ON ps.id = hs.session_id
        WHERE hs.session_id IS NOT NULL
        GROUP BY hs.session_id, ps.sport_type
        HAVING COUNT(*) >= 300  -- At least 5 minutes of data
        ORDER BY MIN(hs.sample_time)
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    
    return [
        {
            'session_id': r[0],
            'start_time': r[1],
            'end_time': r[2],
            'sample_count': r[3],
            'duration_min': r[4],
            'sport_type': r[5] or 'UNKNOWN'
        }
        for r in rows
    ]


def load_session(conn, session_id: int) -> Tuple[np.ndarray, np.ndarray, list, datetime]:
    """Load HR samples for a session."""
    query = """
        SELECT sample_time, hr_value
        FROM hr_samples
        WHERE session_id = %s
        ORDER BY sample_time
    """
    with conn.cursor() as cur:
        cur.execute(query, (session_id,))
        rows = cur.fetchall()
    
    if not rows:
        return None, None, None, None
    
    datetimes = [r[0] for r in rows]
    hr = np.array([r[1] for r in rows], dtype=float)
    t0 = datetimes[0]
    ts = np.array([(dt - t0).total_seconds() for dt in datetimes])
    
    return ts, hr, datetimes, t0


# =============================================================================
# Signal Processing
# =============================================================================

def smooth(hr: np.ndarray, k: int = 5) -> np.ndarray:
    if len(hr) < k:
        return hr.copy()
    med = median_filter(hr, size=k, mode='nearest')
    kernel = np.ones(k) / k
    return np.convolve(med, kernel, mode='same')


def exp_decay(t, hr_final, delta_hr, tau):
    """HR(t) = hr_final + delta_hr * exp(-t/tau)"""
    return hr_final + delta_hr * np.exp(-t / tau)


def fit_exponential(hr_window: np.ndarray) -> Tuple[float, float, bool]:
    """
    Fit exponential decay to HR window.
    Returns (r2, tau, censored)
    
    censored=True if tau hit upper bound (600s), indicating incomplete recovery.
    """
    TAU_UPPER_BOUND = 600  # Cap value (extended for 5-min windows)
    
    n = len(hr_window)
    if n < 10:
        return 0.0, None, False
    
    t = np.arange(n)
    hr_peak = hr_window[0]
    hr_final = hr_window[-1]
    
    if hr_final >= hr_peak:
        return 0.0, None, False
    
    try:
        delta_hr_guess = hr_peak - hr_final
        tau_guess = n / 3
        
        popt, _ = curve_fit(
            exp_decay, t, hr_window,
            p0=[hr_final, delta_hr_guess, tau_guess],
            bounds=(
                [0, 0, 5],
                [hr_peak, 100, TAU_UPPER_BOUND]
            ),
            maxfev=1000
        )
        
        predicted = exp_decay(t, *popt)
        ss_res = np.sum((hr_window - predicted) ** 2)
        ss_tot = np.sum((hr_window - np.mean(hr_window)) ** 2)
        
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        tau = popt[2]
        
        # Check if tau hit the ceiling (censored)
        censored = tau >= (TAU_UPPER_BOUND - 1)  # Allow small margin
        
        return r2, tau, censored
        
    except Exception:
        return 0.0, None, False


def test_initial_descent(hr: np.ndarray, peak_idx: int, cfg: Config) -> bool:
    """15-second linear fit test for initial descent."""
    n = len(hr)
    end = min(peak_idx + cfg.descent_window, n - 1)
    
    if end - peak_idx < 10:
        return False
    
    window = hr[peak_idx:end + 1]
    t = np.arange(len(window))
    
    slope, intercept = np.polyfit(t, window, 1)
    predicted = slope * t + intercept
    
    ss_res = np.sum((window - predicted) ** 2)
    ss_tot = np.sum((window - np.mean(window)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    return slope < 0 and r2 >= cfg.descent_min_r2


def find_t50(hr_window: np.ndarray) -> Optional[float]:
    """Find time to 50% recovery (half-recovery time)."""
    if len(hr_window) < 10:
        return None
    
    hr_peak = hr_window[0]
    hr_final = hr_window[-1]
    total_drop = hr_peak - hr_final
    
    if total_drop <= 0:
        return None
    
    target = hr_peak - (total_drop * 0.5)
    
    # Find first crossing
    for i, hr in enumerate(hr_window):
        if hr <= target:
            return float(i)
    
    return None


# =============================================================================
# Interval Detection and Feature Extraction
# =============================================================================

def extend_interval(hr: np.ndarray, peak_idx: int, cfg: Config) -> Tuple[int, int, float, str]:
    """Extend from peak, tracking nadir, until plateau or 300s (5 minutes)."""
    n = len(hr)
    nadir = hr[peak_idx]
    nadir_idx = peak_idx
    seconds_above = 0
    
    for t in range(peak_idx + 1, min(peak_idx + 301, n)):
        if hr[t] < nadir:
            nadir = hr[t]
            nadir_idx = t
            seconds_above = 0
        else:
            rise = hr[t] - nadir
            if rise > cfg.max_rise_from_nadir:
                seconds_above += 1
                if seconds_above > cfg.max_plateau_sec:
                    return t, nadir_idx, nadir, f"plateau@{t-peak_idx}s"
            else:
                seconds_above = 0
    
    end_idx = min(peak_idx + 300, n - 1)
    if peak_idx + 300 <= n:
        return end_idx, nadir_idx, nadir, "reached_300"
    else:
        return end_idx, nadir_idx, nadir, "end_of_data"


def extract_interval_features(
    hr: np.ndarray,
    peak_idx: int,
    session_id: int,
    session_date: datetime,
    session_duration_min: float,
    session_min_hr: float,
    sport_type: str,
    cfg: Config
) -> Optional[HRRInterval]:
    """Extract all features for a single interval."""
    
    n = len(hr)
    
    # Extend interval
    end_idx, nadir_idx, nadir_hr, end_reason = extend_interval(hr, peak_idx, cfg)
    duration = end_idx - peak_idx
    
    if duration < 30:
        return None
    
    peak_hr = hr[peak_idx]
    total_drop = peak_hr - nadir_hr
    
    # Create interval
    interval = HRRInterval(
        session_id=session_id,
        session_date=session_date,
        session_duration_min=session_duration_min,
        sport_type=sport_type,
        peak_idx=peak_idx,
        peak_time_sec=float(peak_idx),
        peak_time_min=peak_idx / 60,
        duration_sec=duration,
        end_reason=end_reason,
        peak_hr=peak_hr,
        nadir_hr=nadir_hr,
        nadir_idx=nadir_idx,
        total_drop=total_drop,
        session_min_hr=session_min_hr,
        peak_minus_session_min=peak_hr - session_min_hr if session_min_hr else None,
    )
    
    # Early slope: linear fit over first 15s (robust, short-window friendly)
    # Negative slope = HR dropping = good recovery
    if peak_idx + 15 < n:
        slope_window = hr[peak_idx:peak_idx + 16]
        t = np.arange(len(slope_window))
        slope, _ = np.polyfit(t, slope_window, 1)
        interval.early_slope = round(slope, 3)  # bpm/sec
    
    # Calculate local pre-peak baseline (median HR from -180s to -60s before peak)
    # This is the preferred effort proxy for each interval
    local_start = max(0, peak_idx - 180)
    local_end = max(0, peak_idx - 60)
    if local_end > local_start:
        local_window = hr[local_start:local_end]
        if len(local_window) >= 10:
            interval.local_baseline_hr = float(np.median(local_window))
            interval.peak_minus_local = peak_hr - interval.local_baseline_hr
    
    # HRR at fixed timepoints
    if peak_idx + 30 < n:
        interval.hr_at_30 = hr[peak_idx + 30]
        interval.hrr30 = peak_hr - hr[peak_idx + 30]
        interval.recovery_rate_30 = interval.hrr30 / 30
        
        # R² at 30s
        window_30 = hr[peak_idx:peak_idx + 31]
        r2_30, _, _ = fit_exponential(window_30)
        interval.r2_30 = round(r2_30, 3)
    
    if peak_idx + 60 < n:
        interval.hr_at_60 = hr[peak_idx + 60]
        interval.hrr60 = peak_hr - hr[peak_idx + 60]
        interval.recovery_rate_60 = interval.hrr60 / 60
        interval.hrr60_pct_peak = (interval.hrr60 / peak_hr) * 100 if peak_hr > 0 else None
        
        # AUC_0_60: trapezoidal area between HR curve and nadir over 0-60s
        # Higher AUC = slower recovery (HR stayed elevated longer)
        hr_window_60 = hr[peak_idx:peak_idx + 61]
        # Area above nadir (baseline)
        interval.auc_0_60 = round(np.trapz(hr_window_60 - nadir_hr), 1)  # bpm·sec
        
        # HRR_frac: normalized recovery signal (HRR60 / effort)
        # Useful for low-effort intervals where absolute HRR60 is misleadingly small
        effort = interval.peak_minus_local or interval.peak_minus_session_min
        if effort and effort > 0:
            interval.hrr_frac = round(interval.hrr60 / effort, 3)
        
        # R² and tau at 60s
        window_60 = hr[peak_idx:peak_idx + 61]
        r2_60, tau, tau_censored = fit_exponential(window_60)
        interval.r2_60 = round(r2_60, 3)
        interval.tau = round(tau, 1) if tau else None
        interval.tau_censored = tau_censored
    
    if peak_idx + 120 < n:
        interval.hr_at_120 = hr[peak_idx + 120]
        interval.hrr120 = peak_hr - hr[peak_idx + 120]
        
        # R² at 120s
        window_120 = hr[peak_idx:peak_idx + 121]
        r2_120, _, _ = fit_exponential(window_120)
        interval.r2_120 = round(r2_120, 3)
    
    # Extended timepoints (180s, 240s, 300s) for 5-minute recovery windows
    if peak_idx + 180 < n:
        interval.hr_at_180 = hr[peak_idx + 180]
        interval.hrr180 = peak_hr - hr[peak_idx + 180]
        
        # R² at 180s
        window_180 = hr[peak_idx:peak_idx + 181]
        r2_180, _, _ = fit_exponential(window_180)
        interval.r2_180 = round(r2_180, 3)
    
    if peak_idx + 240 < n:
        interval.hr_at_240 = hr[peak_idx + 240]
        interval.hrr240 = peak_hr - hr[peak_idx + 240]
        
        # R² at 240s
        window_240 = hr[peak_idx:peak_idx + 241]
        r2_240, _, _ = fit_exponential(window_240)
        interval.r2_240 = round(r2_240, 3)
    
    if peak_idx + 300 < n:
        interval.hr_at_300 = hr[peak_idx + 300]
        interval.hrr300 = peak_hr - hr[peak_idx + 300]
        
        # R² at 300s
        window_300 = hr[peak_idx:peak_idx + 301]
        r2_300, _, _ = fit_exponential(window_300)
        interval.r2_300 = round(r2_300, 3)
    
    # Ratios
    if interval.hrr30 and interval.hrr60 and interval.hrr60 > 0:
        interval.ratio_30_60 = round(interval.hrr30 / interval.hrr60, 3)
    
    if interval.hrr60 and interval.hrr120 and interval.hrr120 > 0:
        interval.ratio_60_120 = round(interval.hrr60 / interval.hrr120, 3)
    
    if interval.hrr30 and total_drop > 0:
        interval.ratio_30_total = round(interval.hrr30 / total_drop, 3)
    
    if interval.hrr60 and total_drop > 0:
        interval.ratio_60_total = round(interval.hrr60 / total_drop, 3)
    
    # T50 (half-recovery time)
    if duration >= 60:
        window = hr[peak_idx:peak_idx + min(duration, 120) + 1]
        interval.t50 = find_t50(window)
    
    # Quality flags
    if interval.hrr60 and interval.hrr60 >= cfg.min_hrr60:
        interval.valid = True
        if interval.r2_60 and interval.r2_60 >= cfg.min_r2_60:
            interval.high_quality = True
    
    # Mark truncated windows (recovery likely incomplete)
    # For 5-min windows, truncated if <300s and didn't reach full window
    if duration < 300 and end_reason != "reached_300":
        interval.truncated_window = True
    
    # Compute confidence score for trend weighting
    if HAS_DETECT:
        interval.confidence = compute_confidence(
            peak_minus_local=interval.peak_minus_local or interval.peak_minus_session_min,
            hrr_frac=interval.hrr_frac,
            r2_60=interval.r2_60,
            truncated_window=interval.truncated_window,
            duration_sec=duration,
            single_event_actionable_bpm=cfg.single_event_actionable_bpm,
            hrr_frac_actionable=cfg.hrr_frac_actionable,
        )
        interval.weighted_value = compute_weighted_value(
            hrr60=interval.hrr60,
            hrr30=interval.hrr30,
            confidence=interval.confidence or 0.5,
        )
    
    return interval


def process_session(
    conn,
    session_info: dict,
    cfg: Config
) -> List[HRRInterval]:
    """Process a single session, return all valid intervals."""
    
    session_id = session_info['session_id']
    ts, hr, dts, start_time = load_session(conn, session_id)
    
    if hr is None or len(hr) < 300:
        return []
    
    hr_smooth = smooth(hr, cfg.smooth_kernel)
    
    # Calculate session minimum HR (proxy for resting)
    # Use 5th percentile to avoid noise/outliers
    session_min_hr = float(np.percentile(hr_smooth, 5))
    
    # Find peaks
    peaks, _ = find_peaks(hr_smooth, prominence=cfg.peak_prominence, distance=cfg.peak_distance)
    
    intervals = []
    used_until = 0
    
    for peak_idx in peaks:
        if peak_idx < used_until:
            continue
        
        if peak_idx >= len(hr_smooth) - 60:
            continue
        
        # Initial descent test
        if not test_initial_descent(hr_smooth, peak_idx, cfg):
            continue
        
        # Extract features
        interval = extract_interval_features(
            hr_smooth,
            peak_idx,
            session_id,
            start_time,
            session_info['duration_min'],
            session_min_hr,
            session_info.get('sport_type', 'UNKNOWN'),
            cfg
        )
        
        if interval and interval.valid:
            intervals.append(interval)
            # Mark interval as used
            if interval.hrr120:
                used_until = peak_idx + 120
            else:
                used_until = peak_idx + 60
    
    return intervals


# =============================================================================
# Batch Processing
# =============================================================================

def process_all_sessions(cfg: Config, progress: bool = True, session_ids: List[int] = None) -> pd.DataFrame:
    """Process all sessions (or specific ones if session_ids provided) and return aggregate DataFrame."""
    
    conn = get_db_connection()
    sessions = get_all_sessions(conn)
    
    # Filter to specific sessions if requested
    if session_ids:
        sessions = [s for s in sessions if s['session_id'] in session_ids]
        print(f"Processing {len(sessions)} specified session(s): {session_ids}")
    else:
        print(f"Found {len(sessions)} sessions with sufficient data")
    
    all_intervals = []
    
    for i, session_info in enumerate(sessions):
        if progress and (i + 1) % 10 == 0:
            print(f"  Processing session {i+1}/{len(sessions)}...")
        
        try:
            intervals = process_session(conn, session_info, cfg)
            all_intervals.extend(intervals)
        except Exception as e:
            print(f"  Error processing session {session_info['session_id']}: {e}")
    
    conn.close()
    
    print(f"\nExtracted {len(all_intervals)} valid intervals from {len(sessions)} sessions")
    
    # Convert to DataFrame
    if not all_intervals:
        return pd.DataFrame()
    
    records = [asdict(i) for i in all_intervals]
    df = pd.DataFrame(records)
    
    return df


# =============================================================================
# Visualization
# =============================================================================

def plot_beeswarm(df: pd.DataFrame, output_path: str, age: int = 50, min_peak_hr: float = None, stratified: bool = False):
    """Generate bee swarm visualization of HRR intervals."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    # Calculate threshold
    hr_max = 208 - (0.7 * age)
    threshold_research = 0.70 * hr_max
    
    # Filter to high quality
    hq = df[df['high_quality'] == True].copy()
    
    print(f"\nBee swarm: {len(hq)} high-quality intervals (of {len(df)} total)")
    
    if len(hq) < 5:
        print("Not enough high-quality intervals for visualization")
        return
    
    # Add stratum classification
    def classify_sport(s):
        s = str(s).upper()
        if 'RUN' in s or 'WALK' in s:
            return 'ENDURANCE'
        elif 'STRENGTH' in s or 'CROSS' in s or 'CIRCUIT' in s:
            return 'STRENGTH'
        else:
            return 'OTHER'
    
    hq['stratum'] = hq['sport_type'].apply(classify_sport)
    
    if stratified:
        _plot_beeswarm_stratified(hq, output_path, age, min_peak_hr, hr_max, threshold_research)
    else:
        _plot_beeswarm_combined(hq, output_path, age, min_peak_hr, hr_max, threshold_research)


def _plot_beeswarm_combined(hq: pd.DataFrame, output_path: str, age: int, min_peak_hr: float, hr_max: float, threshold_research: float):
    """Original combined beeswarm plot."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Build title
    title = f'HRR Analysis: {len(hq)} High-Quality Intervals from {hq["session_id"].nunique()} Sessions'
    if min_peak_hr:
        title += f'\n(Peak HR ≥ {min_peak_hr:.0f} bpm, {min_peak_hr/hr_max*100:.0f}% of HRmax)'
    
    # 1. HRR60 distribution
    ax1 = axes[0, 0]
    sns.stripplot(y=hq['hrr60'], ax=ax1, jitter=0.3, alpha=0.6, size=8)
    ax1.axhline(y=hq['hrr60'].mean(), color='red', linestyle='--', label=f"Mean: {hq['hrr60'].mean():.1f}")
    ax1.axhline(y=hq['hrr60'].median(), color='blue', linestyle='-', linewidth=2, label=f"Median: {hq['hrr60'].median():.1f}")
    ax1.axhline(y=hq['hrr60'].mean() + 2*hq['hrr60'].std(), color='orange', linestyle=':', alpha=0.7, label='±2σ')
    ax1.axhline(y=hq['hrr60'].mean() - 2*hq['hrr60'].std(), color='orange', linestyle=':', alpha=0.7)
    ax1.set_ylabel('HRR60 (bpm)')
    ax1.set_title(f'HRR60 Distribution (n={len(hq)})')
    ax1.legend(loc='upper right', fontsize=8)
    
    # 2. Peak HR vs HRR60
    ax2 = axes[0, 1]
    scatter = ax2.scatter(hq['peak_hr'], hq['hrr60'], c=hq['r2_60'], cmap='viridis', 
                          alpha=0.7, s=50, edgecolors='black', linewidth=0.5)
    ax2.axvline(x=threshold_research, color='blue', linestyle='-', linewidth=2, alpha=0.7,
                label=f'70% HRmax ({threshold_research:.0f})')
    ax2.axvline(x=hr_max, color='red', linestyle='-', linewidth=1.5, alpha=0.5,
                label=f'HRmax ({hr_max:.0f})')
    plt.colorbar(scatter, ax=ax2, label='R² at 60s')
    ax2.set_xlabel('Peak HR (bpm)')
    ax2.set_ylabel('HRR60 (bpm)')
    ax2.set_title('Peak HR vs HRR60')
    ax2.legend(loc='lower right')
    ax2.grid(True, alpha=0.3)
    
    # 3. Ratio 30/60 distribution
    ax3 = axes[1, 0]
    valid_ratios = hq['ratio_30_60'].dropna()
    if len(valid_ratios) > 5:
        sns.histplot(valid_ratios, ax=ax3, bins=20, kde=True)
        ax3.axvline(x=valid_ratios.mean(), color='red', linestyle='--', 
                   label=f"Mean: {valid_ratios.mean():.2f}")
        ax3.axvline(x=valid_ratios.median(), color='blue', linestyle='-', linewidth=2,
                   label=f"Median: {valid_ratios.median():.2f}")
        ax3.set_xlabel('HRR30/HRR60 Ratio')
        ax3.set_ylabel('Count')
        ax3.set_title('Fast Phase Proportion (HRR30/HRR60)')
        ax3.legend(fontsize=8)
    
    # 4. Tau distribution (excluding censored)
    ax4 = axes[1, 1]
    if 'tau_censored' in hq.columns:
        uncensored_tau = hq[hq['tau_censored'] == False]['tau'].dropna()
        censored_count = hq['tau_censored'].sum()
    else:
        uncensored_tau = hq['tau'].dropna()
        censored_count = 0
    
    if len(uncensored_tau) > 5:
        sns.histplot(uncensored_tau, ax=ax4, bins=20, kde=True)
        ax4.axvline(x=uncensored_tau.mean(), color='red', linestyle='--',
                   label=f"Mean: {uncensored_tau.mean():.1f}s")
        ax4.axvline(x=uncensored_tau.median(), color='blue', linestyle='-', linewidth=2,
                   label=f"Median: {uncensored_tau.median():.1f}s")
        ax4.set_xlabel('Tau (time constant, seconds)')
        ax4.set_ylabel('Count')
        title_suffix = f' (excl. {censored_count} censored)' if censored_count > 0 else ''
        ax4.set_title(f'Recovery Time Constant{title_suffix}')
        ax4.legend(fontsize=8)
    
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved bee swarm: {output_path}")
    plt.show()
    plt.close()


def _plot_beeswarm_stratified(hq: pd.DataFrame, output_path: str, age: int, min_peak_hr: float, hr_max: float, threshold_research: float):
    """Stratified beeswarm plot by activity type."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    # Color palette for strata
    palette = {'STRENGTH': '#e74c3c', 'ENDURANCE': '#3498db', 'OTHER': '#95a5a6'}
    
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    
    # Build title
    title = f'HRR Analysis by Activity Type: {len(hq)} Intervals'
    if min_peak_hr:
        title += f'\n(Peak HR ≥ {min_peak_hr:.0f} bpm)'
    
    # 1. HRR60 by stratum (swarm)
    ax1 = axes[0, 0]
    sns.stripplot(data=hq, x='stratum', y='hrr60', hue='stratum', ax=ax1, 
                  palette=palette, alpha=0.6, size=6, jitter=0.3,
                  order=['STRENGTH', 'ENDURANCE', 'OTHER'], legend=False)
    # Add means
    for i, stratum in enumerate(['STRENGTH', 'ENDURANCE', 'OTHER']):
        subset = hq[hq['stratum'] == stratum]['hrr60']
        if len(subset) > 0:
            ax1.hlines(subset.mean(), i-0.3, i+0.3, colors='black', linewidths=2)
            ax1.hlines(subset.median(), i-0.3, i+0.3, colors='white', linewidths=2, linestyles='--')
    ax1.set_ylabel('HRR60 (bpm)')
    ax1.set_xlabel('')
    ax1.set_title('HRR60 by Activity Type')
    ax1.axhline(y=13, color='orange', linestyle=':', alpha=0.7, label='Actionable (13)')
    ax1.axhline(y=18, color='green', linestyle=':', alpha=0.7, label='Exceptional (18)')
    ax1.legend(fontsize=8)
    
    # 2. HRR_frac by stratum
    ax2 = axes[0, 1]
    sns.stripplot(data=hq, x='stratum', y='hrr_frac', hue='stratum', ax=ax2,
                  palette=palette, alpha=0.6, size=6, jitter=0.3,
                  order=['STRENGTH', 'ENDURANCE', 'OTHER'], legend=False)
    ax2.axhline(y=0.3, color='green', linestyle=':', alpha=0.7, label='Good (0.3)')
    ax2.set_ylabel('HRR_frac (HRR60/effort)')
    ax2.set_xlabel('')
    ax2.set_title('Normalized Recovery by Activity')
    ax2.legend(fontsize=8)
    
    # 3. Early slope by stratum
    ax3 = axes[0, 2]
    sns.stripplot(data=hq, x='stratum', y='early_slope', hue='stratum', ax=ax3,
                  palette=palette, alpha=0.6, size=6, jitter=0.3,
                  order=['STRENGTH', 'ENDURANCE', 'OTHER'], legend=False)
    ax3.axhline(y=0, color='red', linestyle='-', alpha=0.5)
    ax3.set_ylabel('Early Slope (bpm/sec)')
    ax3.set_xlabel('')
    ax3.set_title('Initial Recovery Rate (more negative = better)')
    
    # 4. Box plot comparison
    ax4 = axes[1, 0]
    sns.boxplot(data=hq, x='stratum', y='hrr60', hue='stratum', ax=ax4,
                palette=palette, order=['STRENGTH', 'ENDURANCE', 'OTHER'], legend=False)
    ax4.set_ylabel('HRR60 (bpm)')
    ax4.set_xlabel('')
    ax4.set_title('HRR60 Distribution Comparison')
    
    # 5. Peak HR vs HRR60 colored by stratum
    ax5 = axes[1, 1]
    for stratum in ['STRENGTH', 'ENDURANCE', 'OTHER']:
        subset = hq[hq['stratum'] == stratum]
        if len(subset) > 0:
            ax5.scatter(subset['peak_hr'], subset['hrr60'], 
                       c=palette[stratum], alpha=0.6, s=40, label=f"{stratum} (n={len(subset)})")
    ax5.axvline(x=threshold_research, color='blue', linestyle='-', linewidth=2, alpha=0.5)
    ax5.set_xlabel('Peak HR (bpm)')
    ax5.set_ylabel('HRR60 (bpm)')
    ax5.set_title('Peak HR vs HRR60')
    ax5.legend(fontsize=8)
    ax5.grid(True, alpha=0.3)
    
    # 6. Summary table as text
    ax6 = axes[1, 2]
    ax6.axis('off')
    
    summary_text = "Per-Stratum Summary\n" + "="*30 + "\n\n"
    for stratum in ['STRENGTH', 'ENDURANCE', 'OTHER']:
        subset = hq[hq['stratum'] == stratum]
        if len(subset) >= 5:
            n_sess = subset['session_id'].nunique()
            hrr60_mean = subset['hrr60'].mean()
            hrr60_sd = subset['hrr60'].std()
            
            # Calculate TE/SDD if enough sessions
            if n_sess >= 3:
                sess_means = subset.groupby('session_id')['hrr60'].mean()
                te = sess_means.std() / np.sqrt(2)
                sdd = 2.77 * te
                summary_text += f"{stratum}:\n"
                summary_text += f"  n={len(subset)} intervals, {n_sess} sessions\n"
                summary_text += f"  HRR60: {hrr60_mean:.1f} ± {hrr60_sd:.1f} bpm\n"
                summary_text += f"  TE: {te:.1f} | SDD: {sdd:.1f} bpm\n\n"
            else:
                summary_text += f"{stratum}:\n"
                summary_text += f"  n={len(subset)} intervals, {n_sess} sessions\n"
                summary_text += f"  HRR60: {hrr60_mean:.1f} ± {hrr60_sd:.1f} bpm\n\n"
    
    ax6.text(0.1, 0.9, summary_text, transform=ax6.transAxes, fontsize=10,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    # Save stratified version
    strat_path = output_path.replace('.png', '_stratified.png')
    plt.savefig(strat_path, dpi=150, bbox_inches='tight')
    print(f"Saved stratified bee swarm: {strat_path}")
    plt.show()
    plt.close()


def print_summary_stats(df: pd.DataFrame, age: int = 50, min_peak_hr: float = None, cfg: Config = None):
    """Print summary statistics for SQC."""
    
    if cfg is None:
        cfg = Config()
    
    hr_max = 208 - (0.7 * age)
    threshold = 0.70 * hr_max
    
    hq = df[df['high_quality'] == True]
    
    print(f"\n{'='*80}")
    print("HRR SUMMARY STATISTICS")
    if min_peak_hr:
        print(f"(Filtered to peak HR ≥ {min_peak_hr:.0f} bpm)")
    print(f"{'='*80}")
    
    print(f"\nConfig: {HRR_CONFIG_PATH}")
    print(f"  Actionable threshold: {cfg.single_event_actionable_bpm:.0f} bpm")
    print(f"  Exceptional threshold: {cfg.exceptional_bpm:.0f} bpm")
    print(f"  HRR_frac actionable: {cfg.hrr_frac_actionable:.2f}")
    
    print(f"\nTotal intervals: {len(df)}")
    print(f"High quality (R²≥0.7 & HRR60≥9): {len(hq)}")
    print(f"Sessions with data: {df['session_id'].nunique()}")
    print(f"Date range: {df['session_date'].min()} to {df['session_date'].max()}")
    
    # Window quality
    if 'truncated_window' in df.columns:
        truncated_count = df['truncated_window'].sum()
        print(f"Truncated windows (<120s, recovery incomplete): {truncated_count} ({truncated_count/len(df)*100:.1f}%)")
    
    if 'tau_censored' in df.columns:
        censored_count = df['tau_censored'].sum()
        print(f"Censored τ (hit 300s cap): {censored_count} ({censored_count/len(df)*100:.1f}%)")
    
    print(f"\nAge-predicted values (age={age}):")
    print(f"  HRmax: {hr_max:.0f} bpm")
    print(f"  Research threshold (70%): {threshold:.0f} bpm")
    
    if len(hq) > 0:
        print(f"\n--- High-Quality Intervals (n={len(hq)}) ---")
        
        print(f"\nHRR60:")
        print(f"  Mean ± SD: {hq['hrr60'].mean():.1f} ± {hq['hrr60'].std():.1f} bpm")
        print(f"  Median [IQR]: {hq['hrr60'].median():.1f} [{hq['hrr60'].quantile(0.25):.1f}-{hq['hrr60'].quantile(0.75):.1f}]")
        print(f"  Range: {hq['hrr60'].min():.1f} - {hq['hrr60'].max():.1f}")
        print(f"  Control limits (±2σ): {hq['hrr60'].mean() - 2*hq['hrr60'].std():.1f} - {hq['hrr60'].mean() + 2*hq['hrr60'].std():.1f}")
        
        print(f"\nPeak HR:")
        print(f"  Mean ± SD: {hq['peak_hr'].mean():.1f} ± {hq['peak_hr'].std():.1f} bpm")
        print(f"  Median [IQR]: {hq['peak_hr'].median():.1f} [{hq['peak_hr'].quantile(0.25):.1f}-{hq['peak_hr'].quantile(0.75):.1f}]")
        print(f"  Range: {hq['peak_hr'].min():.1f} - {hq['peak_hr'].max():.1f}")
        empirical_threshold = hq['peak_hr'].min()
        print(f"  Empirical threshold: {empirical_threshold:.0f} bpm ({empirical_threshold/hr_max*100:.0f}% of max)")
        
        valid_ratios = hq['ratio_30_60'].dropna()
        if len(valid_ratios) > 0:
            print(f"\nHRR30/HRR60 Ratio (fast phase proportion):")
            print(f"  Mean ± SD: {valid_ratios.mean():.3f} ± {valid_ratios.std():.3f}")
            print(f"  Median [IQR]: {valid_ratios.median():.3f} [{valid_ratios.quantile(0.25):.3f}-{valid_ratios.quantile(0.75):.3f}]")
            print(f"  Range: {valid_ratios.min():.3f} - {valid_ratios.max():.3f}")
        
        valid_frac = hq['hrr_frac'].dropna()
        if len(valid_frac) > 0:
            print(f"\nHRR_frac (HRR60 / effort, normalized signal):")
            print(f"  Mean ± SD: {valid_frac.mean():.3f} ± {valid_frac.std():.3f}")
            print(f"  Median [IQR]: {valid_frac.median():.3f} [{valid_frac.quantile(0.25):.3f}-{valid_frac.quantile(0.75):.3f}]")
            print(f"  Note: Values > 0.3 indicate good recovery even for low-effort intervals")
        
        valid_slope = hq['early_slope'].dropna()
        if len(valid_slope) > 0:
            print(f"\nEarly Slope (first 15s, bpm/sec):")
            print(f"  Mean ± SD: {valid_slope.mean():.3f} ± {valid_slope.std():.3f}")
            print(f"  Median [IQR]: {valid_slope.median():.3f} [{valid_slope.quantile(0.25):.3f}-{valid_slope.quantile(0.75):.3f}]")
            print(f"  Note: More negative = faster initial recovery")
        
        valid_auc = hq['auc_0_60'].dropna()
        if len(valid_auc) > 0:
            print(f"\nAUC 0-60s (bpm·sec above nadir):")
            print(f"  Mean ± SD: {valid_auc.mean():.0f} ± {valid_auc.std():.0f}")
            print(f"  Median [IQR]: {valid_auc.median():.0f} [{valid_auc.quantile(0.25):.0f}-{valid_auc.quantile(0.75):.0f}]")
            print(f"  Note: Lower AUC = faster recovery (less time elevated)")
        
        valid_tau = hq['tau'].dropna()
        censored_count = hq['tau_censored'].sum() if 'tau_censored' in hq.columns else 0
        uncensored_tau = hq[hq['tau_censored'] == False]['tau'].dropna() if 'tau_censored' in hq.columns else valid_tau
        
        if len(valid_tau) > 0:
            print(f"\nTau (time constant):")
            print(f"  All values (n={len(valid_tau)}):")
            print(f"    Mean ± SD: {valid_tau.mean():.1f} ± {valid_tau.std():.1f} sec")
            print(f"    Median [IQR]: {valid_tau.median():.1f} [{valid_tau.quantile(0.25):.1f}-{valid_tau.quantile(0.75):.1f}]")
            print(f"  Censored at cap (τ≥299s): {censored_count} ({censored_count/len(valid_tau)*100:.1f}%)")
            if len(uncensored_tau) > 0 and censored_count > 0:
                print(f"  Uncensored only (n={len(uncensored_tau)}):")
                print(f"    Mean ± SD: {uncensored_tau.mean():.1f} ± {uncensored_tau.std():.1f} sec")
                print(f"    Median [IQR]: {uncensored_tau.median():.1f} [{uncensored_tau.quantile(0.25):.1f}-{uncensored_tau.quantile(0.75):.1f}]")
                print(f"    Range: {uncensored_tau.min():.1f} - {uncensored_tau.max():.1f}")
        
        valid_t50 = hq['t50'].dropna()
        if len(valid_t50) > 0:
            print(f"\nT50 (half-recovery time):")
            print(f"  Mean ± SD: {valid_t50.mean():.1f} ± {valid_t50.std():.1f} sec")
            print(f"  Median [IQR]: {valid_t50.median():.1f} [{valid_t50.quantile(0.25):.1f}-{valid_t50.quantile(0.75):.1f}]")
            print(f"  Range: {valid_t50.min():.1f} - {valid_t50.max():.1f}")
        
        print(f"\nR² at 60s:")
        print(f"  Mean ± SD: {hq['r2_60'].mean():.3f} ± {hq['r2_60'].std():.3f}")
        print(f"  Median [IQR]: {hq['r2_60'].median():.3f} [{hq['r2_60'].quantile(0.25):.3f}-{hq['r2_60'].quantile(0.75):.3f}]")
        print(f"  Range: {hq['r2_60'].min():.3f} - {hq['r2_60'].max():.3f}")
        
        # Event classification
        print(f"\n--- Event Classification (config thresholds) ---")
        below_actionable = len(hq[hq['hrr60'] < cfg.single_event_actionable_bpm])
        actionable = len(hq[(hq['hrr60'] >= cfg.single_event_actionable_bpm) & (hq['hrr60'] < cfg.exceptional_bpm)])
        exceptional = len(hq[hq['hrr60'] >= cfg.exceptional_bpm])
        
        print(f"  Below actionable (<{cfg.single_event_actionable_bpm:.0f} bpm): {below_actionable} ({below_actionable/len(hq)*100:.1f}%)")
        print(f"  Actionable ({cfg.single_event_actionable_bpm:.0f}-{cfg.exceptional_bpm:.0f} bpm): {actionable} ({actionable/len(hq)*100:.1f}%)")
        print(f"  Exceptional (≥{cfg.exceptional_bpm:.0f} bpm): {exceptional} ({exceptional/len(hq)*100:.1f}%)")
        
        # HRR_frac classification (for low-effort intervals)
        if 'hrr_frac' in hq.columns:
            low_effort = hq[hq['peak_minus_local'].fillna(hq['peak_minus_session_min']) < 30]
            if len(low_effort) > 0:
                good_frac = len(low_effort[low_effort['hrr_frac'] >= cfg.hrr_frac_actionable])
                print(f"\n  Low-effort intervals (<30 bpm elevation): {len(low_effort)}")
                print(f"    With good HRR_frac (≥{cfg.hrr_frac_actionable}): {good_frac} (keep as normalized signal)")
        
        # Effort proxies (both baselines)
        print(f"\nEffort Proxies:")
        
        valid_local = hq['peak_minus_local'].dropna()
        if len(valid_local) > 0:
            print(f"  Peak minus Local Baseline (preferred, -180s to -60s):")
            print(f"    Mean ± SD: {valid_local.mean():.1f} ± {valid_local.std():.1f} bpm")
            print(f"    Median [IQR]: {valid_local.median():.1f} [{valid_local.quantile(0.25):.1f}-{valid_local.quantile(0.75):.1f}]")
        
        valid_session = hq['peak_minus_session_min'].dropna()
        if len(valid_session) > 0:
            print(f"  Peak minus Session Min (5th percentile):")
            print(f"    Mean ± SD: {valid_session.mean():.1f} ± {valid_session.std():.1f} bpm")
            print(f"    Median [IQR]: {valid_session.median():.1f} [{valid_session.quantile(0.25):.1f}-{valid_session.quantile(0.75):.1f}]")
        
        # Within-subject reliability (if enough sessions)
        n_sessions = hq['session_id'].nunique()
        if n_sessions >= 5:
            print(f"\n--- Within-Subject Reliability (n={n_sessions} sessions) ---")
            
            # Calculate per-session mean HRR60
            session_means = hq.groupby('session_id')['hrr60'].mean()
            
            # Typical Error (TE) = SD of session means / sqrt(2)
            # This estimates measurement noise between sessions
            te = session_means.std() / np.sqrt(2)
            
            # Smallest Detectable Difference (SDD) = 1.96 * sqrt(2) * TE
            # = 2.77 * TE (for 95% CI)
            sdd = 2.77 * te
            
            # Coefficient of Variation
            cv = (session_means.std() / session_means.mean()) * 100
            
            print(f"  Session mean HRR60: {session_means.mean():.1f} ± {session_means.std():.1f} bpm")
            print(f"  Typical Error (TE): {te:.1f} bpm")
            print(f"  Smallest Detectable Difference (SDD): {sdd:.1f} bpm")
            print(f"  Coefficient of Variation: {cv:.1f}%")
            print(f"  \n  Interpretation:")
            print(f"    - Changes < {sdd:.1f} bpm likely noise")
            print(f"    - Changes > {sdd:.1f} bpm likely real")
            print(f"    - Suggested alert threshold: {session_means.mean() - 1.5*session_means.std():.1f} bpm")
        
        # Per-stratum reliability (if sport_type available)
        if 'sport_type' in hq.columns:
            print(f"\n--- Per-Stratum Analysis ---")
            
            # Create simplified strata
            def classify_sport(s):
                s = str(s).upper()
                if 'RUN' in s or 'WALK' in s:
                    return 'ENDURANCE'
                elif 'STRENGTH' in s or 'CROSS' in s or 'CIRCUIT' in s:
                    return 'STRENGTH'
                else:
                    return 'OTHER'
            
            hq_copy = hq.copy()
            hq_copy['stratum'] = hq_copy['sport_type'].apply(classify_sport)
            
            for stratum in ['STRENGTH', 'ENDURANCE', 'OTHER']:
                stratum_data = hq_copy[hq_copy['stratum'] == stratum]
                if len(stratum_data) < 10:
                    continue
                    
                n_sess = stratum_data['session_id'].nunique()
                print(f"\n  {stratum} (n={len(stratum_data)} intervals, {n_sess} sessions):")
                print(f"    HRR60: {stratum_data['hrr60'].mean():.1f} ± {stratum_data['hrr60'].std():.1f} bpm")
                print(f"    Median: {stratum_data['hrr60'].median():.1f} bpm")
                
                if n_sess >= 5:
                    sess_means = stratum_data.groupby('session_id')['hrr60'].mean()
                    te_s = sess_means.std() / np.sqrt(2)
                    sdd_s = 2.77 * te_s
                    print(f"    TE: {te_s:.1f} bpm | SDD: {sdd_s:.1f} bpm")
                    print(f"    Alert threshold: {sess_means.mean() - 1.5*sess_means.std():.1f} bpm")


def run_ewma_report(df: pd.DataFrame, output_path: str):
    """
    Run EWMA/CUSUM trend detection on extracted intervals.
    
    Groups intervals by session date (one value per session = session mean HRR60),
    then runs detectors to find concerning trends.
    """
    if not HAS_DETECT:
        print("\nWarning: Could not import arnold.hrr.detect module. EWMA/CUSUM not available.")
        return
    
    # Get high-quality intervals
    hq = df[df['high_quality'] == True].copy()
    
    if len(hq) < 10:
        print("\nNot enough high-quality intervals for trend detection (need ≥10)")
        return
    
    # Add stratum
    def classify_sport(s):
        s = str(s).upper()
        if 'RUN' in s or 'WALK' in s:
            return 'ENDURANCE'
        elif 'STRENGTH' in s or 'CROSS' in s or 'CIRCUIT' in s:
            return 'STRENGTH'
        else:
            return 'OTHER'
    
    hq['stratum'] = hq['sport_type'].apply(classify_sport)
    
    print(f"\n{'='*80}")
    print("EWMA/CUSUM TREND DETECTION")
    print(f"{'='*80}")
    
    # Get config values
    ewma_cfg = HRR_DEFAULTS.get('ewma', {})
    cusum_cfg = HRR_DEFAULTS.get('cusum', {})
    lam = ewma_cfg.get('lambda', 0.20)
    min_events = ewma_cfg.get('min_events', 5)
    warning_mult = ewma_cfg.get('warning_sdd_multiplier', 1.0)
    action_mult = ewma_cfg.get('action_sdd_multiplier', 2.0)
    k_mult = cusum_cfg.get('k_multiplier', 0.5)
    h_mult = cusum_cfg.get('h_multiplier', 4.0)
    
    print(f"\nConfig:")
    print(f"  EWMA λ={lam}, min_events={min_events}, warning={warning_mult}×SDD, action={action_mult}×SDD")
    print(f"  CUSUM k={k_mult}×SDD, h={h_mult}×SDD")
    
    # Run per-stratum
    for stratum in ['STRENGTH', 'ENDURANCE', 'OTHER']:
        stratum_data = hq[hq['stratum'] == stratum]
        n_sess = stratum_data['session_id'].nunique()
        
        if n_sess < 5:
            continue
        
        print(f"\n--- {stratum} ({n_sess} sessions) ---")
        
        # Aggregate to session-level (one value per session)
        # Use session mean of weighted_value if available, else HRR60
        if 'weighted_value' in stratum_data.columns and stratum_data['weighted_value'].notna().any():
            session_values = stratum_data.groupby(['session_id', 'session_date']).agg({
                'weighted_value': 'mean',
                'hrr60': 'mean',
                'confidence': 'mean'
            }).reset_index()
            value_col = 'weighted_value'
            print(f"  Using confidence-weighted values (mean confidence: {session_values['confidence'].mean():.2f})")
        else:
            session_values = stratum_data.groupby(['session_id', 'session_date']).agg({
                'hrr60': 'mean'
            }).reset_index()
            value_col = 'hrr60'
            print(f"  Using raw HRR60 values (no confidence weighting)")
        
        # Sort by date
        session_values = session_values.sort_values('session_date')
        
        # Get timestamps and values
        # Handle timezone-aware datetimes by converting to UTC
        ts = pd.to_datetime(session_values['session_date'], utc=True)
        x = session_values[value_col].values
        
        # Calculate baseline and SDD from this stratum
        baseline = float(np.mean(x))
        sess_means = stratum_data.groupby('session_id')['hrr60'].mean()
        te = sess_means.std() / np.sqrt(2)
        sdd = 2.77 * te
        
        print(f"  Baseline: {baseline:.1f} bpm, SDD: {sdd:.1f} bpm")
        print(f"  Warning threshold: baseline − 1.0×SDD = {baseline - warning_mult*sdd:.1f} bpm (drop ≈ {warning_mult*sdd:.1f} bpm)")
        print(f"  Action threshold: baseline − 2.0×SDD = {baseline - action_mult*sdd:.1f} bpm (drop ≈ {action_mult*sdd:.1f} bpm)")
        
        # Run EWMA
        ewma_z, ewma_alerts = detect_ewma_alerts(
            ts, x, baseline=baseline, SDD=sdd,
            lam=lam, gap_seconds=3600*48,  # 48hr gap = reset
            min_events=min_events,
            warning_mult=warning_mult,
            action_mult=action_mult
        )
        
        # Run CUSUM
        cusum_s, cusum_alerts = detect_cusum_alerts(
            ts, x, baseline=baseline, SDD=sdd,
            gap_seconds=3600*48,
            k_mult=k_mult,
            h_mult=h_mult,
            reset_on_recovery_n=3
        )
        
        # Report alerts
        if ewma_alerts:
            print(f"\n  EWMA Alerts ({len(ewma_alerts)}):")
            for alert in ewma_alerts[-5:]:  # Show last 5
                print(f"    {alert.timestamp.strftime('%Y-%m-%d')}: {alert.level.upper()} - EWMA={alert.value:.1f}")
        else:
            print(f"\n  EWMA: No alerts (all within thresholds)")
        
        if cusum_alerts:
            print(f"\n  CUSUM Alerts ({len(cusum_alerts)}):")
            for alert in cusum_alerts[-5:]:
                print(f"    {alert.timestamp.strftime('%Y-%m-%d')}: {alert.level.upper()} - CUSUM={alert.value:.1f}")
        else:
            print(f"  CUSUM: No alerts")
        
        # Current status
        if len(ewma_z) > 0:
            current_ewma = ewma_z.iloc[-1]
            current_date = ts.iloc[-1]
            status = "OK"
            if current_ewma <= baseline - action_mult * sdd:
                status = "⚠️ ACTION"
            elif current_ewma <= baseline - warning_mult * sdd:
                status = "⚡ WARNING"
            print(f"\n  Current ({current_date.strftime('%Y-%m-%d')}): EWMA={current_ewma:.1f} bpm [{status}]")
    
    print(f"\n{'='*80}")

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='HRR Batch Processor')
    parser.add_argument('--output', type=str, default='data/raw/HRR_data/hrr_all.csv',
                       help='Output CSV path')
    parser.add_argument('--plot-beeswarm', action='store_true',
                       help='Generate bee swarm visualization')
    parser.add_argument('--stratified', action='store_true',
                       help='Generate stratified plot by activity type (STRENGTH/ENDURANCE/OTHER)')
    parser.add_argument('--age', type=int, default=50,
                       help='Age for threshold calculations')
    parser.add_argument('--min-hrr60', type=float, default=9.0)
    parser.add_argument('--min-r2', type=float, default=0.7)
    parser.add_argument('--min-peak-hr', type=str, default=None,
                       help='Filter to intervals starting above this HR (e.g., 150). '
                            'Use "z4" for 80%% HRmax, "z5" for 90%% HRmax, or a number.')
    parser.add_argument('--min-effort', type=float, default=5.0,
                       help='Min effort = peak HR minus local baseline (bpm). '
                            'Default 5 (include most). Use 20-30 for work sets, 50+ for aggressive filtering. '
                            'Uses local pre-peak baseline (-180s to -60s), falls back to session min.')
    parser.add_argument('--report-ewma', action='store_true',
                       help='Run EWMA/CUSUM trend detection on extracted intervals and report alerts')
    parser.add_argument('--write-db', action='store_true',
                       help='Write intervals to hr_recovery_intervals table in Postgres')
    parser.add_argument('--clear-existing', action='store_true',
                       help='Clear existing rows before writing (use with --write-db)')
    parser.add_argument('--session-id', type=int, nargs='+',
                       help='Process only these session ID(s). With --write-db, only clears/writes these sessions.')
    
    args = parser.parse_args()
    
    # Calculate age-based thresholds
    hr_max = 208 - (0.7 * args.age)
    
    # Parse min-peak-hr (can be number or zone shortcut)
    min_peak_hr = None
    if args.min_peak_hr:
        arg_str = str(args.min_peak_hr).lower()
        if arg_str == 'z4':
            min_peak_hr = 0.80 * hr_max
            print(f"Filter: Z4+ intervals (≥80% HRmax = {min_peak_hr:.0f} bpm)")
        elif arg_str == 'z5':
            min_peak_hr = 0.90 * hr_max
            print(f"Filter: Z5+ intervals (≥90% HRmax = {min_peak_hr:.0f} bpm)")
        elif arg_str == 'threshold' or arg_str == 'vt1':
            min_peak_hr = 0.70 * hr_max
            print(f"Filter: Above research threshold (≥70% HRmax = {min_peak_hr:.0f} bpm)")
        else:
            try:
                min_peak_hr = float(args.min_peak_hr)
                pct = (min_peak_hr / hr_max) * 100
                print(f"Filter: Peak HR ≥ {min_peak_hr:.0f} bpm ({pct:.0f}% of HRmax)")
            except ValueError:
                print(f"Warning: Could not parse --min-peak-hr '{args.min_peak_hr}', ignoring")
                min_peak_hr = None
    
    cfg = Config(
        min_hrr60=args.min_hrr60,
        min_r2_60=args.min_r2,
    )
    
    print("HRR Batch Processor")
    print("=" * 40)
    
    df = process_all_sessions(cfg, session_ids=args.session_id)
    
    if len(df) == 0:
        print("No intervals found!")
        return
    
    # Apply peak HR filter if specified
    if min_peak_hr:
        before_count = len(df)
        df = df[df['peak_hr'] >= min_peak_hr].copy()
        print(f"Filtered: {len(df)} intervals with peak HR ≥ {min_peak_hr:.0f} (dropped {before_count - len(df)})")
        
        if len(df) == 0:
            print("No intervals remain after filtering!")
            return
    
    # Apply effort filter (uses local baseline, falls back to session min)
    if args.min_effort and args.min_effort > 0:
        before_count = len(df)
        # Prefer local baseline, fall back to session min
        effort_col = df['peak_minus_local'].fillna(df['peak_minus_session_min'])
        df = df[effort_col >= args.min_effort].copy()
        print(f"Effort filter: {len(df)} intervals with effort ≥ {args.min_effort:.0f} bpm (dropped {before_count - len(df)})")
        
        if len(df) == 0:
            print("No intervals remain after effort filtering!")
            return
    
    # Save to CSV
    df.to_csv(args.output, index=False)
    print(f"\nSaved to {args.output}")
    
    # Print summary
    print_summary_stats(df, args.age, min_peak_hr)
    
    # Generate visualization
    if args.plot_beeswarm:
        plot_path = args.output.replace('.csv', '_beeswarm.png')
        plot_beeswarm(df, plot_path, args.age, min_peak_hr, stratified=args.stratified)
    
    # Run EWMA/CUSUM trend detection
    if args.report_ewma:
        run_ewma_report(df, args.output)
    
    # Write to database
    if args.write_db:
        print(f"\nWriting {len(df)} intervals to hr_recovery_intervals...")
        conn = get_db_connection()
        inserted = write_intervals_to_db(df, conn, clear_existing=args.clear_existing, session_ids=args.session_id)
        conn.close()
        print(f"Inserted {inserted} rows into hr_recovery_intervals")


if __name__ == '__main__':
    main()
