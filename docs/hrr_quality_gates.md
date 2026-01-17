# HRR Quality Gates

## Overview

Quality gates filter recovery intervals to ensure only physiologically valid data enters analytics. Gates run in sequence; first failure triggers rejection.

## Hard Reject Criteria

| Gate | Metric | Threshold | Reject Reason | Rationale |
|------|--------|-----------|---------------|-----------|
| 1 | `slope_90_120` | > 0.1 bpm/sec | `activity_resumed` | HR rising = athlete moved |
| 2 | `best_r2` (0-60 through 0-300) | None | `no_valid_r2_windows` | Too short for validation |
| 3 | `best_r2` | < 0.75 | `poor_fit_quality` | Exponential decay doesn't fit |
| 4 | `r2_30_60` | < 0.75 | `r2_30_60_below_0.75` | HRR60 unreliable (mid-recovery disruption) |
| 5 | `r2_30_90` | < 0.75 | `r2_30_90_below_0.75` | HRR120 unreliable |

## Flag Criteria (Review, Not Reject)

| Flag | Condition | Meaning |
|------|-----------|---------|
| `LATE_RISE` | 0 < slope_90_120 ≤ 0.1 | Minor fidgeting, probably OK |
| `ONSET_DISAGREEMENT` | onset_confidence == 'low' | Detection methods disagree on start |
| `LOW_SIGNAL` | hr_reserve < 25 bpm | Floor effect - small signal |

## Segment R² Windows

| Window | Validates | Notes |
|--------|-----------|-------|
| r2_0_60 | Overall decay | First phase gate |
| r2_30_60 | HRR60 | Catches double-bounce after initial drop |
| r2_30_90 | HRR120 | Mid-interval quality |
| r2_0_120+ | Longer HRR | Extended windows |

## Implementation Notes

- `r2_0_30` computed but **not** used for gating (too noise-prone from catch-breath)
- Fit failures return `-1.0` (triggers < 0.75 rejection)
- `best_r2` uses r2_0_60 through r2_0_300 only (not r2_0_30)
- Rejected intervals stored with `auto_reject_reason` for audit trail

## Database Fields
```sql
quality_status: 'pass' | 'rejected' | 'flagged'
quality_flags: TEXT[]  -- e.g., {'LATE_RISE', 'LOW_SIGNAL'}
auto_reject_reason: TEXT  -- e.g., 'r2_30_60_below_0.75'
```
