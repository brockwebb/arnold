#!/usr/bin/env python3
"""
HRR Feature Extraction Pipeline

Detects recovery intervals from per-second HR streams and computes
comprehensive HRR features for FR-004.

Usage:
    python scripts/hrr_feature_extraction.py --session-id 1 --source endurance
    python scripts/hrr_feature_extraction.py --all --dry-run
    python scripts/hrr_feature_extraction.py --all

This is a shim that imports from the modular hrr/ package.
"""

from hrr.cli import main

if __name__ == "__main__":
    main()
