"""
HRR Feature Extraction - Type Definitions

Dataclasses and configuration for HRR feature extraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml


# =============================================================================
# Configuration
# =============================================================================

def load_config_yaml() -> Dict[str, Any]:
    """Load configuration from YAML file, return empty dict if not found."""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'hrr_extraction.yaml'
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
    late_stage_sec: int = 240  # After this, use looser flutter tolerance
    late_stage_tolerance_bpm: int = 6  # Looser tolerance for near-baseline oscillation

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
            kwargs['late_stage_sec'] = ri.get('late_stage_sec', 240)
            kwargs['late_stage_tolerance_bpm'] = ri.get('late_stage_tolerance_bpm', 6)

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
    Canonical naming: hr_Xs for HR at time X, hrrX_abs for absolute drop.
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

    # Normalized HRR metrics
    recovery_ratio: Optional[float] = None  # total_drop / hr_reserve
    peak_pct_max: Optional[float] = None  # peak / estimated_max_hr

    # Exponential decay model: HR(t) = asymptote + amplitude * exp(-t/tau)
    tau_seconds: Optional[float] = None
    tau_fit_r2: Optional[float] = None
    fit_amplitude: Optional[float] = None  # DB: fit_amplitude (was tau_amplitude)
    fit_asymptote: Optional[float] = None  # DB: fit_asymptote (was tau_baseline)

    # Segment R² values (for window-specific quality)
    r2_0_30: Optional[float] = None   # First 30s segment. <0.5 = double_peak reject
    r2_15_45: Optional[float] = None  # Centered window - diagnostic for edge artifacts
    r2_30_60: Optional[float] = None  # Second 30s segment - <0.75 = hard reject (validates HRR60)
    r2_0_60: Optional[float] = None   # Validates HRR60
    r2_30_90: Optional[float] = None  # Diagnostic only - validates HRR120 (NOT a reject gate)
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
