# HRR Quality Control System

Human verification layer for HRR interval detection algorithm decisions.

## Purpose

The HRR QC system provides:
- Structured human review of algorithm-detected recovery intervals
- Stable locators that survive algorithm re-runs
- Delta-based review workflow when algorithm changes
- Reason code taxonomy for consistent reject/override decisions

## Schema Overview

### Core Tables

| Table | Purpose |
|-------|---------|
| `hrr_algorithm_versions` | Tracks algo configs: detection params, R² thresholds, gate settings |
| `hrr_algo_runs` | Each execution of a version on a session - intervals belong here |
| `hrr_qc_reason_codes` | Standardized codes for reject/override decisions |
| `hrr_qc_judgments` | Human decisions with stable locators (interval_start_ts) |
| `hrr_session_reviews` | Batch confirmation tracking |

### Key Design Decision

**Uses `start_time` as stable locator, not `interval_id`.**

When the algorithm is re-run (new version, parameter tuning), interval IDs change but timestamps are stable. This allows human judgments to survive algorithm drift.

The `v_hrr_algo_change_impact` view detects conflicts:
```sql
-- Find human overrides that may need re-review after algo change
SELECT * FROM v_hrr_algo_change_impact
WHERE old_status != new_status;
```

## CLI Tool

`scripts/hrr_qc_review.py` - Keyboard-driven review workflow.

### Commands

```bash
# List sessions
hrr_qc_review.py sessions           # All sessions
hrr_qc_review.py sessions -u        # Unverified only
hrr_qc_review.py sessions -r        # Needs review only

# Review specific session
hrr_qc_review.py review -s 71

# Visualization (separate terminal)
hrr_qc_review.py viz 71

# Statistics
hrr_qc_review.py stats

# Batch confirm multiple sessions
hrr_qc_review.py batch-confirm 71 72 73
```

### Review Workflow

**Setup (two terminals):**
```bash
# Terminal 1: Visualization
python scripts/hrr_qc_review.py viz 71

# Terminal 2: Review interface
python scripts/hrr_qc_review.py review -s 71
```

**Session-level decision:**
- `A` = All Good (confirm all intervals, skip to next session)
- `R` = Review individually

**Interval-level decision:**
- `Enter` = Confirm (accept algorithm decision)
- `R` = Reject (shows reason code menu)
- `O` = Override rejection (shows override code menu)

## Reason Codes

### Reject Passed Interval

| Key | Code | Description |
|-----|------|-------------|
| 1 | `peak_misplaced` | Peak not at true maximum |
| 2 | `double_peak_undetected` | Double peak not detected |
| 3 | `early_termination` | Recovery cut too short |
| 4 | `late_onset` | Peak detection started late |
| 5 | `no_true_recovery` | Not a true recovery |
| 6 | `signal_artifact` | Noise/artifact |
| 7 | `sub_threshold` | Below activation threshold |
| o | `other` | Other (prompts for notes) |

### Override Rejection

| Key | Code | Description |
|-----|------|-------------|
| 1 | `false_positive_double` | False double peak detection |
| 2 | `acceptable_r2` | R² acceptable for analysis |
| 3 | `known_context` | Contextual knowledge (notes required) |
| 4 | `peak_shift_fixes` | Peak shift makes it valid |
| 5 | `hiit_expected` | Expected for HIIT pattern |
| o | `other` | Other (prompts for notes) |

## Delta Workflow (Algorithm Changes)

When the detection algorithm changes:

1. **Create new algorithm version**
   ```sql
   INSERT INTO hrr_algorithm_versions (version_tag, config_hash, ...)
   VALUES ('v2.1-plateau-fix', 'abc123', ...);
   ```

2. **Re-run detection**
   ```bash
   python scripts/hrr_feature_extraction.py --all --reprocess
   ```

3. **Query impact view**
   ```sql
   SELECT session_id, interval_start_ts,
          old_status, new_status,
          human_judgment, judgment_reason
   FROM v_hrr_algo_change_impact
   WHERE old_status != new_status
     AND human_judgment IS NOT NULL;
   ```

4. **Review only conflicts**
   - Human overrides where algo now agrees → likely remove override
   - Human confirms where algo now rejects → re-evaluate
   - New intervals → standard review

## Files

| File | Purpose |
|------|---------|
| `scripts/hrr_qc_review.py` | CLI review tool |
| `scripts/hrr_qc_viz.py` | Visualization helper |
| `scripts/hrr_qc.py` | Core QC functions |

## Design Principles

1. **Speed**: Enter = accept default, one-key reason codes
2. **Batch efficiency**: Session-level "all good" for clean sessions
3. **Stability**: Timestamp locators survive algo drift
4. **Traceability**: Every judgment has reason code + optional notes
5. **Delta review**: Only re-review conflicts, not everything
