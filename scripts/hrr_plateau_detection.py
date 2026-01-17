#!/usr/bin/env python3
"""
Plateau-to-Decline Detection for HRR Feature Extraction

Issue #020: Detect recovery intervals from sustained high HR followed by decline,
complementing scipy's peak detection which requires prominence.

Design:
- Peak detection asks: "How much higher is this point than neighbors?"
- Plateau detection asks: "Where does sustained decline begin?"

Algorithm:
1. Compute rolling slope across session
2. Find points where slope becomes and stays negative (decline onset)
3. Verify decline continues (not just a brief dip)
4. Look back from decline onset to find plateau max
5. Validate: max elevated above RHR, sustained effort before, sufficient drop FROM MAX
6. Deduplicate against peak-detected intervals
"""

from typing import List, Tuple, Optional, Set
import numpy as np
from dataclasses import dataclass


@dataclass
class PlateauConfig:
    """Configuration for plateau detection."""
    
    # Decline detection - tuned to avoid false positives from running fluctuations
    slope_threshold: float = -0.4       # bpm/sec - must be clearly declining
    min_consecutive_sec: int = 12       # seconds of decline to confirm onset
    slope_window_sec: int = 7           # rolling window for slope calculation
    max_noise_samples: int = 2          # allow brief noise in decline window
    
    # Decline verification - distinguish real recovery from brief dips
    verify_at_sec: int = 30             # check HR this many seconds after onset
    min_drop_at_verify: int = 10        # must have dropped at least this much by verify point
    
    # Lookback for plateau max
    lookback_window_sec: int = 60       # how far back to search for max HR
    min_plateau_duration_sec: int = 15  # minimum time at elevated HR before decline
    
    # Validation (same as peak detection)
    min_elevation_bpm: int = 25         # max must be this far above RHR
    min_sustained_effort_sec: int = 20  # must be elevated before max
    min_drop_from_max: int = 12         # HR must drop at least this much from max within 90s
    
    # Deduplication
    dedup_window_sec: int = 30          # intervals within this window are duplicates
    internal_dedup_window: int = 60     # dedupe within plateau detection itself


def compute_rolling_slope(hr_values: np.ndarray, window: int = 7) -> np.ndarray:
    """
    Compute rolling slope (bpm/sec) using linear regression over window.
    
    Returns array of slopes, same length as input (padded with NaN at edges).
    """
    n = len(hr_values)
    slopes = np.full(n, np.nan)
    
    half_window = window // 2
    
    for i in range(half_window, n - half_window):
        segment = hr_values[i - half_window:i + half_window + 1]
        t = np.arange(len(segment))
        
        # Linear regression: slope = covariance(t, hr) / variance(t)
        t_mean = t.mean()
        hr_mean = segment.mean()
        slope = np.sum((t - t_mean) * (segment - hr_mean)) / np.sum((t - t_mean) ** 2)
        slopes[i] = slope
    
    return slopes


def find_decline_onsets(
    slopes: np.ndarray,
    hr_values: np.ndarray,
    config: PlateauConfig
) -> List[int]:
    """
    Find indices where sustained decline begins.
    
    A decline onset must:
    1. Have slope <= threshold for min_consecutive_sec
    2. Result in actual HR drop (verified at verify_at_sec)
    """
    onsets = []
    n = len(slopes)
    i = 0
    
    while i < n - config.min_consecutive_sec - config.verify_at_sec:
        # Skip if not declining or NaN
        if np.isnan(slopes[i]) or slopes[i] > config.slope_threshold:
            i += 1
            continue
        
        # Check window for sustained decline (with noise tolerance)
        window_size = config.min_consecutive_sec + config.max_noise_samples
        declining_count = 0
        noise_count = 0
        
        for j in range(i, min(i + window_size, n)):
            if np.isnan(slopes[j]):
                noise_count += 1
            elif slopes[j] <= config.slope_threshold:
                declining_count += 1
            else:
                noise_count += 1
            
            if noise_count > config.max_noise_samples:
                break
        
        # Check 1: Enough declining samples?
        if declining_count < config.min_consecutive_sec:
            i += 1
            continue
        
        # Check 2: Verify decline continues - HR should be lower at verify point
        verify_idx = i + config.verify_at_sec
        if verify_idx < n:
            hr_at_onset = hr_values[i]
            hr_at_verify = hr_values[verify_idx]
            actual_drop = hr_at_onset - hr_at_verify
            
            if actual_drop < config.min_drop_at_verify:
                # Brief dip, not real recovery - skip
                i += 1
                continue
        
        # Passed all checks - this is a real decline onset
        onsets.append(i)
        
        # Skip well past this region to avoid duplicates
        i += config.verify_at_sec + config.min_consecutive_sec
    
    return onsets


def find_plateau_max(
    hr_values: np.ndarray,
    decline_onset_idx: int,
    config: PlateauConfig
) -> Tuple[int, int]:
    """
    Look back from decline onset to find the plateau maximum.
    
    Returns (max_idx, max_hr).
    """
    start_idx = max(0, decline_onset_idx - config.lookback_window_sec)
    search_window = hr_values[start_idx:decline_onset_idx + 1]
    
    if len(search_window) == 0:
        return decline_onset_idx, hr_values[decline_onset_idx]
    
    # Find max in the lookback window
    local_max_idx = np.argmax(search_window)
    absolute_max_idx = start_idx + local_max_idx
    max_hr = search_window[local_max_idx]
    
    return absolute_max_idx, int(max_hr)


def validate_plateau_recovery(
    hr_values: np.ndarray,
    max_idx: int,
    max_hr: int,
    resting_hr: int,
    config: PlateauConfig
) -> bool:
    """
    Validate that a plateau recovery represents genuine elevated effort
    AND that a real decline follows the max.
    """
    # Must be sufficiently elevated above resting
    elevation = max_hr - resting_hr
    if elevation < config.min_elevation_bpm:
        return False
    
    # Check for sustained effort before max
    if max_idx < config.min_sustained_effort_sec:
        return False
    
    pre_max_samples = hr_values[max(0, max_idx - config.min_sustained_effort_sec):max_idx]
    elevated_count = np.sum(pre_max_samples > resting_hr + 15)
    
    if elevated_count < config.min_sustained_effort_sec * 0.7:
        return False
    
    # KEY CHECK: Verify HR actually drops significantly from the MAX
    # Check HR at 90s after max - should see real decline
    n = len(hr_values)
    check_idx = min(max_idx + 90, n - 1)
    hr_at_90 = hr_values[check_idx]
    drop_from_max = max_hr - hr_at_90
    
    if drop_from_max < config.min_drop_from_max:
        return False
    
    return True


def detect_plateau_recoveries(
    hr_values: np.ndarray,
    resting_hr: int,
    config: PlateauConfig = None
) -> List[Tuple[int, int]]:
    """
    Detect recovery intervals using plateau-to-decline method.
    
    Returns list of (peak_idx, max_hr) tuples representing recovery start points.
    These can be fed into the same find_recovery_end() and create_recovery_interval()
    as peak-detected intervals.
    """
    if config is None:
        config = PlateauConfig()
    
    min_samples = config.min_sustained_effort_sec + config.min_consecutive_sec + config.verify_at_sec
    if len(hr_values) < min_samples:
        return []
    
    # Step 1: Compute rolling slope
    slopes = compute_rolling_slope(hr_values, config.slope_window_sec)
    
    # Step 2: Find decline onsets (with verification)
    decline_onsets = find_decline_onsets(slopes, hr_values, config)
    
    # Step 3: For each decline, find plateau max and validate
    recoveries = []
    seen_max_indices: Set[int] = set()  # For internal deduplication
    
    for onset_idx in decline_onsets:
        max_idx, max_hr = find_plateau_max(hr_values, onset_idx, config)
        
        # Internal deduplication: skip if we've already found a recovery near this max
        is_dup = False
        for seen_idx in seen_max_indices:
            if abs(max_idx - seen_idx) < config.internal_dedup_window:
                is_dup = True
                break
        
        if is_dup:
            continue
        
        if validate_plateau_recovery(hr_values, max_idx, max_hr, resting_hr, config):
            recoveries.append((max_idx, max_hr))
            seen_max_indices.add(max_idx)
    
    return recoveries


def deduplicate_detections(
    peak_indices: List[int],
    plateau_indices: List[int],
    dedup_window_sec: int = 30
) -> List[Tuple[int, str]]:
    """
    Merge peak-detected and plateau-detected indices, removing duplicates.
    
    Returns list of (index, source) where source is 'peak' or 'plateau'.
    Peak detections take priority when there's overlap.
    """
    # Mark all with source
    all_detections = [(idx, 'peak') for idx in peak_indices]
    
    for plateau_idx in plateau_indices:
        # Check if this overlaps with any peak detection
        is_duplicate = False
        for peak_idx in peak_indices:
            if abs(plateau_idx - peak_idx) <= dedup_window_sec:
                is_duplicate = True
                break
        
        if not is_duplicate:
            all_detections.append((plateau_idx, 'plateau'))
    
    # Sort by index
    all_detections.sort(key=lambda x: x[0])
    
    return all_detections


# =============================================================================
# Test harness
# =============================================================================

def test_on_session(session_id: int = 51):
    """Test plateau detection on a specific session."""
    import psycopg2
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    
    load_dotenv(Path(__file__).parent.parent / '.env')
    
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'arnold_analytics'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '')
    )
    
    # Load HR samples
    with conn.cursor() as cur:
        cur.execute("""
            SELECT hr_value 
            FROM hr_samples 
            WHERE session_id = %s 
            ORDER BY sample_time
        """, (session_id,))
        rows = cur.fetchall()
    
    hr_values = np.array([r[0] for r in rows])
    resting_hr = 55  # Default
    
    print(f"Session {session_id}: {len(hr_values)} samples ({len(hr_values)/60:.1f} min)")
    print(f"HR range: {hr_values.min()} - {hr_values.max()}, avg: {hr_values.mean():.0f}")
    
    # Detect plateaus
    config = PlateauConfig()
    recoveries = detect_plateau_recoveries(hr_values, resting_hr, config)
    
    print(f"\nPlateau-detected recoveries: {len(recoveries)}")
    for idx, hr in recoveries:
        minute = idx // 60
        sec = idx % 60
        hr_90s_later = hr_values[idx + 90] if idx + 90 < len(hr_values) else 0
        drop = hr - hr_90s_later
        print(f"  {minute:02d}:{sec:02d} - HR {hr} → {hr_90s_later} at +90s (drop {drop})")
    
    # Compare to existing intervals
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                extract(epoch from start_time - (SELECT min(sample_time) FROM hr_samples WHERE session_id = %s))::int as start_sec,
                hr_peak
            FROM hr_recovery_intervals
            WHERE polar_session_id = %s
            ORDER BY start_time
        """, (session_id, session_id))
        existing = cur.fetchall()
    
    print(f"\nExisting peak-detected intervals: {len(existing)}")
    for start_sec, hr_peak in existing:
        minute = start_sec // 60
        sec = start_sec % 60
        print(f"  {minute:02d}:{sec:02d} - HR {hr_peak}")
    
    # Deduplicate
    peak_indices = [e[0] for e in existing]
    plateau_indices = [r[0] for r in recoveries]
    merged = deduplicate_detections(peak_indices, plateau_indices)
    
    new_detections = [m for m in merged if m[1] == 'plateau']
    print(f"\nNEW plateau-only detections: {len(new_detections)}")
    for idx, source in new_detections:
        minute = idx // 60
        sec = idx % 60
        hr_at_point = hr_values[idx] if idx < len(hr_values) else 0
        hr_90s = hr_values[idx + 90] if idx + 90 < len(hr_values) else 0
        print(f"  {minute:02d}:{sec:02d} - HR {hr_at_point} → {hr_90s} at +90s (drop {hr_at_point - hr_90s})")
    
    conn.close()


if __name__ == '__main__':
    import sys
    session_id = int(sys.argv[1]) if len(sys.argv) > 1 else 51
    test_on_session(session_id)
