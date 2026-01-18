"""
HRR Feature Extraction Package

Detects recovery intervals from per-second HR streams and computes
comprehensive HRR features for FR-004.

Usage:
    python scripts/hrr_feature_extraction.py --session-id 1 --source endurance
    python scripts/hrr_feature_extraction.py --all --dry-run
    python scripts/hrr_feature_extraction.py --all

Public API:
    - process_session: Process a single session
    - RecoveryInterval: Dataclass for detected recovery intervals
    - HRRConfig: Configuration for HRR detection and feature extraction
"""

from .types import HRRConfig, HRSample, RecoveryInterval
from .cli import process_session, process_all_sessions, main

__all__ = [
    # Primary API
    'process_session',
    'process_all_sessions',
    'main',
    # Types
    'RecoveryInterval',
    'HRRConfig',
    'HRSample',
]
