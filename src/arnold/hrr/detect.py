"""
HRR Trend Detection: EWMA and CUSUM with gap-aware reset logic.

EWMA (Exponentially Weighted Moving Average):
- Smooths noisy HRR signals while tracking gradual trends
- Resets on session gaps to avoid stale state contamination
- Warning/action levels based on SDD (Smallest Detectable Difference)

CUSUM (Cumulative Sum):
- Detects persistent shifts faster than EWMA for sustained drops
- Accumulates deviation from baseline; triggers on threshold breach
- Resets on gaps and after consecutive recovery observations

Usage:
    from arnold.hrr.detect import detect_ewma_alerts, detect_cusum_alerts
    
    ewma_z, ewma_alerts = detect_ewma_alerts(
        ts=df.index, 
        x=df['hrr60'].values,
        baseline=17.0,  # historical mean
        SDD=6.7,        # from TE calculation
    )
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class AlertEvent:
    """Single alert from trend detector."""
    timestamp: pd.Timestamp
    value: float
    level: str  # 'warning' or 'action'
    detector: str  # 'ewma' or 'cusum'
    context: Optional[str] = None


def compute_ewma_with_gaps(
    ts: pd.DatetimeIndex,
    x: np.ndarray,
    lam: float,
    gap_seconds: int,
    baseline: float
) -> pd.Series:
    """
    EWMA with gap-aware reset.
    
    When gap between consecutive events exceeds gap_seconds, 
    EWMA state resets to baseline to prevent stale carryover.
    
    Args:
        ts: DatetimeIndex of event timestamps
        x: Array of values (e.g., HRR60 or weighted_value)
        lam: Smoothing factor (0.2 typical; higher = more reactive)
        gap_seconds: Reset threshold in seconds (3600 = 1 hour)
        baseline: Value to reset to on gaps (historical mean)
    
    Returns:
        Series of EWMA values indexed by timestamp
    """
    z = np.empty(len(x), dtype=float)
    z[:] = np.nan
    prev_ts = None
    z_prev = baseline
    
    for i, t in enumerate(ts):
        if prev_ts is None:
            gap = 0
        else:
            gap = (t - prev_ts).total_seconds()
        
        # Reset on large gap (new session)
        if gap > gap_seconds:
            z_prev = baseline
        
        # EWMA update: z_t = λ * x_t + (1-λ) * z_{t-1}
        z_prev = lam * x[i] + (1.0 - lam) * z_prev
        z[i] = z_prev
        prev_ts = t
    
    return pd.Series(z, index=ts)


def detect_ewma_alerts(
    ts: pd.DatetimeIndex,
    x: np.ndarray,
    baseline: float,
    SDD: float,
    lam: float = 0.2,
    gap_seconds: int = 3600,
    min_events: int = 5,
    warning_mult: float = 1.0,
    action_mult: float = 2.0
) -> Tuple[pd.Series, List[AlertEvent]]:
    """
    Detect trend alerts using EWMA.
    
    Triggers warning when EWMA drops below baseline - warning_mult*SDD,
    and action when below baseline - action_mult*SDD.
    
    Args:
        ts: DatetimeIndex of event timestamps
        x: Array of HRR values (higher = better recovery)
        baseline: Historical mean HRR (stratum-specific)
        SDD: Smallest Detectable Difference (2.77 * TE)
        lam: EWMA smoothing factor (default 0.2)
        gap_seconds: Reset on gaps > this (default 3600 = 1hr)
        min_events: Require this many events since reset before alerting
        warning_mult: SDD multiplier for warning threshold (default 1.0)
        action_mult: SDD multiplier for action threshold (default 2.0)
    
    Returns:
        (ewma_series, list of AlertEvent)
    """
    z = compute_ewma_with_gaps(ts, x, lam, gap_seconds, baseline)
    alerts = []
    last_reset_idx = 0
    
    warning_threshold = baseline - warning_mult * SDD
    action_threshold = baseline - action_mult * SDD
    
    for i in range(len(z)):
        # Track resets
        if i > 0 and (ts[i] - ts[i-1]).total_seconds() > gap_seconds:
            last_reset_idx = i
        
        # Require minimum events since last reset
        n_since = i - last_reset_idx + 1
        if n_since < min_events:
            continue
        
        zt = z.iloc[i]
        
        if zt <= action_threshold:
            alerts.append(AlertEvent(
                timestamp=ts[i],
                value=float(zt),
                level='action',
                detector='ewma',
                context=f'EWMA {zt:.1f} < {action_threshold:.1f} (baseline-{action_mult}×SDD)'
            ))
        elif zt <= warning_threshold:
            alerts.append(AlertEvent(
                timestamp=ts[i],
                value=float(zt),
                level='warning',
                detector='ewma',
                context=f'EWMA {zt:.1f} < {warning_threshold:.1f} (baseline-{warning_mult}×SDD)'
            ))
    
    return z, alerts


def detect_cusum_alerts(
    ts: pd.DatetimeIndex,
    x: np.ndarray,
    baseline: float,
    SDD: float,
    gap_seconds: int = 3600,
    k_mult: float = 0.5,
    h_mult: float = 4.0,
    reset_on_recovery_n: int = 3
) -> Tuple[pd.Series, List[AlertEvent]]:
    """
    One-sided downward CUSUM for detecting persistent HRR decline.
    
    Accumulates deviation below baseline; triggers when accumulation
    exceeds threshold h. More sensitive to sustained shifts than EWMA.
    
    Args:
        ts: DatetimeIndex of event timestamps
        x: Array of HRR values
        baseline: Target/historical mean
        SDD: Smallest Detectable Difference
        gap_seconds: Reset on gaps > this
        k_mult: Reference value = k_mult * SDD (slack/allowance)
        h_mult: Threshold = h_mult * SDD (trigger level)
        reset_on_recovery_n: Reset after N consecutive values near baseline
    
    Returns:
        (cusum_series, list of AlertEvent)
    
    CUSUM formula:
        s_t = max(0, s_{t-1} + (baseline - x_t) - k)
        Alert when s_t >= h
    """
    k = k_mult * SDD  # allowance for normal variation
    h = h_mult * SDD  # decision threshold
    
    s = np.zeros(len(x))
    alerts = []
    consec_recover = 0
    
    recovery_threshold = baseline - 0.5 * SDD  # values above this = recovering
    
    for i in range(len(x)):
        # Reset on session gap
        if i > 0 and (ts[i] - ts[i-1]).total_seconds() > gap_seconds:
            s[i] = 0.0
            consec_recover = 0
            continue
        
        # CUSUM increment: how much below (baseline - k)?
        incr = (baseline - x[i]) - k
        s[i] = max(0.0, (s[i-1] if i > 0 else 0.0) + incr)
        
        # Recovery reset logic
        if x[i] >= recovery_threshold:
            consec_recover += 1
        else:
            consec_recover = 0
        
        if consec_recover >= reset_on_recovery_n:
            s[i] = 0.0
            consec_recover = 0
        
        # Check threshold
        if s[i] >= h:
            alerts.append(AlertEvent(
                timestamp=ts[i],
                value=float(s[i]),
                level='action',
                detector='cusum',
                context=f'CUSUM {s[i]:.1f} >= {h:.1f} (h={h_mult}×SDD)'
            ))
            # Reset after alert to avoid repeated triggers
            s[i] = 0.0
    
    return pd.Series(s, index=ts), alerts


def compute_confidence(
    peak_minus_local: float,
    hrr_frac: Optional[float],
    r2_60: Optional[float],
    truncated_window: bool,
    duration_sec: int,
    single_event_actionable_bpm: float = 13.0,
    hrr_frac_actionable: float = 0.3,
    weights: Optional[dict] = None
) -> float:
    """
    Compute confidence score for a single HRR interval.
    
    Higher confidence = more reliable measurement, should weight
    more heavily in trend detection.
    
    Components:
        - mag_score: Effort magnitude (peak_minus_local / actionable)
        - frac_score: Normalized recovery (hrr_frac / actionable)
        - fit_score: Exponential fit quality (R²)
        - window_score: Recovery window completeness
    
    Args:
        peak_minus_local: Effort proxy (bpm)
        hrr_frac: HRR60 / effort (or None)
        r2_60: R² of exponential fit at 60s (or None)
        truncated_window: True if recovery window was cut short
        duration_sec: Actual recovery window duration
        single_event_actionable_bpm: Threshold for "real" effort
        hrr_frac_actionable: Threshold for "good" normalized recovery
        weights: Optional dict with 'mag', 'frac', 'fit', 'window' weights
    
    Returns:
        Confidence score 0.0 to 1.0
    """
    if weights is None:
        weights = {'mag': 0.4, 'frac': 0.25, 'fit': 0.25, 'window': 0.1}
    
    # Magnitude score: was this a real effort?
    if peak_minus_local and peak_minus_local > 0:
        mag_score = min(1.0, peak_minus_local / single_event_actionable_bpm)
    else:
        mag_score = 0.0
    
    # Fraction score: good recovery relative to effort?
    if hrr_frac is not None and hrr_frac > 0:
        frac_score = min(1.0, hrr_frac / hrr_frac_actionable)
    else:
        frac_score = 0.5  # neutral if unavailable
    
    # Fit score: how well does exponential model fit?
    if r2_60 is not None:
        fit_score = max(0.0, min(1.0, r2_60))
    else:
        fit_score = 0.5  # neutral if unavailable
    
    # Window score: was recovery fully captured?
    if not truncated_window and duration_sec >= 60:
        window_score = 1.0
    elif duration_sec >= 45:
        window_score = 0.7
    elif duration_sec >= 30:
        window_score = 0.5
    else:
        window_score = 0.2
    
    # Weighted combination
    confidence = (
        weights['mag'] * mag_score +
        weights['frac'] * frac_score +
        weights['fit'] * fit_score +
        weights['window'] * window_score
    )
    
    return round(min(1.0, max(0.0, confidence)), 3)


def compute_weighted_value(
    hrr60: Optional[float],
    hrr30: Optional[float],
    confidence: float
) -> Optional[float]:
    """
    Compute confidence-weighted HRR value for trend detection.
    
    Uses HRR60 if available, falls back to HRR30.
    
    Args:
        hrr60: HRR at 60 seconds (or None)
        hrr30: HRR at 30 seconds (or None)
        confidence: Confidence score 0-1
    
    Returns:
        weighted_value = HRR * confidence, or None if no HRR available
    """
    value = hrr60 if hrr60 is not None else hrr30
    if value is None:
        return None
    return round(value * confidence, 2)


# =============================================================================
# Test utilities
# =============================================================================

def run_synthetic_test():
    """
    Run synthetic test demonstrating EWMA and CUSUM behavior.
    
    Creates 3 sessions with:
    - Session 1: Normal variation around baseline
    - Session 2: Gradual decline (simulating overtraining)
    - Session 3: Sudden drop (simulating acute issue)
    """
    from datetime import datetime, timedelta
    
    rng = np.random.default_rng(12345)
    baseline = 17.0  # typical HRR60
    SDD = 6.7  # typical SDD
    
    # Build synthetic data
    rows = []
    start = datetime(2026, 1, 1, 8, 0, 0)
    
    for session in range(3):
        for j in range(20):
            ts = start + timedelta(minutes=5 * j)
            val = float(rng.normal(baseline, 2.0))
            rows.append((ts, val))
        start = start + timedelta(days=2)  # 2-day gap between sessions
    
    df = pd.DataFrame(rows, columns=['ts', 'x']).set_index('ts')
    
    # Session 2: gradual decline (events 25-32)
    session2_idx = list(df.index)[20:40]
    for i, k in enumerate(session2_idx):
        if 5 <= i <= 12:
            df.loc[k, 'x'] -= 4.0 * (i - 4) / 8.0  # up to ~4 bpm decline
    
    # Session 3: sudden drop (events 46-49)
    session3_idx = list(df.index)[40:60]
    for i, k in enumerate(session3_idx):
        if 6 <= i <= 9:
            df.loc[k, 'x'] -= 10.0  # sudden -10 drop
    
    ts = df.index
    x = df['x'].to_numpy()
    
    # Run detectors
    ewma_z, ewma_alerts = detect_ewma_alerts(
        ts, x, baseline=baseline, SDD=SDD,
        lam=0.2, gap_seconds=3600, min_events=5,
        warning_mult=1.0, action_mult=2.0
    )
    
    cusum_s, cusum_alerts = detect_cusum_alerts(
        ts, x, baseline=baseline, SDD=SDD,
        gap_seconds=3600, k_mult=0.5, h_mult=4.0,
        reset_on_recovery_n=3
    )
    
    print("=" * 60)
    print("SYNTHETIC TEST: EWMA + CUSUM Detection")
    print("=" * 60)
    print(f"\nBaseline: {baseline:.1f} bpm, SDD: {SDD:.1f} bpm")
    print(f"EWMA thresholds: warning < {baseline - SDD:.1f}, action < {baseline - 2*SDD:.1f}")
    print(f"CUSUM threshold: h = {4.0 * SDD:.1f}")
    
    print(f"\nEWMA Alerts ({len(ewma_alerts)}):")
    for a in ewma_alerts:
        print(f"  {a.timestamp}: {a.level.upper()} - {a.context}")
    
    print(f"\nCUSUM Alerts ({len(cusum_alerts)}):")
    for a in cusum_alerts:
        print(f"  {a.timestamp}: {a.level.upper()} - {a.context}")
    
    return df, ewma_z, cusum_s, ewma_alerts, cusum_alerts


if __name__ == '__main__':
    run_synthetic_test()
