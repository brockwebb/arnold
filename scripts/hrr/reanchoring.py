"""
HRR Feature Extraction - Plateau Detection and Re-anchoring

Functions for detecting plateaus and re-anchoring intervals when
double-peak patterns are detected (Issue #020).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Dict, Any, TYPE_CHECKING

import numpy as np

from .types import HRSample, RecoveryInterval, HRRConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Plateau Detection Methods
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
# Re-anchoring Logic
# =============================================================================

def attempt_plateau_reanchor(
    samples: List[HRSample],
    interval: RecoveryInterval,
    interval_samples: List[HRSample],
    adjusted_start_idx: int,
    end_idx: int,
    interval_order: int,
    resting_hr: int,
    config: HRRConfig
) -> Tuple[bool, Optional[RecoveryInterval], Optional[List[HRSample]], int, str]:
    """
    Attempt to re-anchor interval when plateau/double-peak detected (r2_0_30 < threshold).

    Uses guard clauses pattern - each check returns early with failure reason if not met.
    This replaces the previous deeply-nested if statements that silently fell through.

    Args:
        samples: Full session HR samples
        interval: Original interval with bad r2_0_30
        interval_samples: Samples for the original interval
        adjusted_start_idx: Current onset-adjusted start index
        end_idx: Current end index
        interval_order: Interval number for logging
        resting_hr: Resting heart rate
        config: HRR configuration

    Returns:
        (success, new_interval, new_samples, new_end_idx, reason)
        - success: True if re-anchor improved r2_0_30 above threshold
        - new_interval: Re-anchored interval (or None if failed)
        - new_samples: Samples for re-anchored interval (or None if failed)
        - new_end_idx: New end index (or original if failed)
        - reason: Description of outcome for logging
    """
    # Import here to avoid circular imports
    from .detection import find_recovery_end, create_recovery_interval
    from .metrics import fit_exponential_decay, compute_all_segment_r2

    hr_values = np.array([s.hr_value for s in interval_samples])
    nadir_idx = interval.nadir_time_sec or len(hr_values) - 1

    # Run plateau detection algorithms
    plateau_offset, plateau_confidence, debug_info = find_true_peak_plateau(
        hr_values, nadir_idx, config
    )

    logger.info(
        f"Interval {interval_order}: plateau detection - "
        f"r2_0_30={interval.r2_0_30:.3f}, offset={plateau_offset}s, confidence={plateau_confidence}, "
        f"slope={debug_info['slope_offset']}s/{debug_info['slope_status']}, "
        f"geom={debug_info['geom_offset']}s/{debug_info['geom_status']}"
    )

    # Guard 1: Did plateau detection fail entirely?
    if plateau_confidence == 'failed':
        return False, None, None, end_idx, f"plateau detection failed: {debug_info['slope_status']}, {debug_info['geom_status']}"

    # Guard 2: Is offset meaningful? (>5 seconds)
    if plateau_offset <= 5:
        return False, None, None, end_idx, f"offset too small: {plateau_offset}s <= 5s threshold"

    # Guard 3: Will we have enough data after shifting?
    new_start_idx = adjusted_start_idx + plateau_offset
    if new_start_idx >= end_idx - config.min_decline_duration_sec:
        return False, None, None, end_idx, f"insufficient data after shift: new_start={new_start_idx}, end={end_idx}, min_duration={config.min_decline_duration_sec}"

    # Guard 4: Can we find a valid recovery end from new start?
    new_end_idx = find_recovery_end(samples, new_start_idx, config)
    if new_end_idx is None:
        return False, None, None, end_idx, "find_recovery_end returned None for new start"

    # Guard 5: Is new interval long enough?
    if new_end_idx <= new_start_idx + config.min_decline_duration_sec:
        return False, None, None, end_idx, f"new interval too short: {new_end_idx - new_start_idx}s < {config.min_decline_duration_sec}s"

    # Guard 6: Can we create the interval?
    new_interval = create_recovery_interval(
        samples, new_start_idx, new_end_idx, interval_order, resting_hr, config
    )
    if new_interval is None:
        return False, None, None, end_idx, "create_recovery_interval returned None"

    # Guard 7: Do we have enough samples after onset adjustment?
    new_onset_offset = new_interval.onset_delay_sec or 0
    new_adjusted_start = new_start_idx + new_onset_offset
    new_interval_samples = samples[new_adjusted_start:new_end_idx + 1]

    if len(new_interval_samples) < config.min_decline_duration_sec:
        return False, None, None, end_idx, f"new samples too few after onset: {len(new_interval_samples)} < {config.min_decline_duration_sec}"

    # Recompute features on re-anchored interval
    new_interval = fit_exponential_decay(new_interval_samples, new_interval, config)
    new_interval = compute_all_segment_r2(new_interval_samples, new_interval)

    # Guard 8: Did we get a valid r2_0_30?
    if new_interval.r2_0_30 is None:
        return False, None, None, end_idx, "r2_0_30 is None after recompute"

    # Guard 9: Did r2_0_30 actually improve above threshold?
    if new_interval.r2_0_30 < config.gate_r2_0_30_threshold:
        return False, None, None, end_idx, f"r2_0_30 still below threshold: {new_interval.r2_0_30:.3f} < {config.gate_r2_0_30_threshold}"

    # Success! Add flag and return
    if 'PLATEAU_RESOLVED' not in new_interval.quality_flags:
        new_interval.quality_flags.append('PLATEAU_RESOLVED')

    return True, new_interval, new_interval_samples, new_end_idx, f"resolved: r2_0_30 {interval.r2_0_30:.3f} -> {new_interval.r2_0_30:.3f}, shifted +{plateau_offset}s"
