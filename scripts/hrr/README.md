# HRR Feature Extraction Module

Detects recovery intervals from per-second HR streams and computes HRR features.

## Module Structure

```
scripts/hrr/
├── __init__.py      # Public API exports
├── types.py         # Dataclasses: HRRConfig, HRSample, RecoveryInterval
├── detection.py     # Peak/valley detection, extract_features pipeline
├── metrics.py       # R² calculations, exponential decay fitting, quality assessment
├── persistence.py   # Database operations: load samples, save intervals
├── reanchoring.py   # Plateau detection and interval re-anchoring (Issue #020)
└── cli.py           # CLI entry point, session processing, summary output
```

## File Responsibilities

| File | Purpose |
|------|---------|
| `types.py` | Configuration and data structures. No external dependencies. |
| `detection.py` | Peak detection (scipy + valley-based), backward search, interval creation, main `extract_features()` pipeline. |
| `metrics.py` | Segment R² computation, tau fitting, `assess_quality()` with flag/status logic. |
| `persistence.py` | All database I/O: samples, intervals, peak adjustments, quality overrides. |
| `reanchoring.py` | Forward re-anchoring when r2_0_30 OR r2_15_45 < threshold (plateau detection). |
| `cli.py` | Argument parsing, `process_session()`, summary table formatting. |

## Backward Compatibility

`scripts/hrr_feature_extraction.py` is a shim that imports from this package:

```python
from hrr.cli import main
if __name__ == "__main__":
    main()
```

All existing CLI usage continues to work unchanged.

## Peak Detection Enhancements (Issue #43)

**Backward Peak Search**: When scipy detects a peak at the end of a gradual deceleration plateau, searches backward (up to `backward_lookback_sec`, default 30s) for the true maximum HR. Adds `BACKWARD_SHIFTED` flag.

**Forward Re-anchoring Triggers**: Now triggers on EITHER:
- `r2_0_30 < 0.5` — Immediate plateau in first 30 seconds
- `r2_15_45 < 0.5` — Delayed plateau pattern

**Method Conflict Resolution**: When slope and geometry methods disagree significantly (>10s), slope method is trusted (geometry fails on long declining plateaus).

**Enhanced Rejection Reasons**: Duration now included for debugging:
- `insufficient_duration_45s` instead of `insufficient_duration`
- `no_valid_r2_windows_52s` instead of `no_valid_r2_windows`

## Quality Flags

**Warning flags** (demote status to "flagged"):
- `LATE_RISE` - Positive slope in 90-120s window
- `ONSET_DISAGREEMENT` - Max-HR and slope methods disagree on onset
- `LOW_SIGNAL` - HR reserve below threshold
- `HIGH_R2_DELTA` - Large difference between r2_0_30 and r2_30_60

**Informational flags** (preserve "pass" status):
- `PLATEAU_RESOLVED` - Forward re-anchoring successfully fixed plateau
- `BACKWARD_SHIFTED` - Backward search found true peak earlier than scipy detection
- `MANUAL_ADJUSTED` - Peak position manually adjusted via peak_adjustments table
- `ONSET_ADJUSTED` - Onset delay > 15s (informational only)
- `HUMAN_OVERRIDE` - Quality status overridden via hrr_quality_overrides table
