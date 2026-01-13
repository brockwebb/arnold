# Issue: Integrate HRR extraction into unified HR sync pipeline

## Context

HRR backfill complete (365 intervals from 61 sessions). Need to integrate incremental HRR extraction into the sync pipeline so new sessions automatically populate `hr_recovery_intervals`.

## Current State

- `hrr_batch.py` has full extraction logic with `--write-db` flag
- Table `hr_recovery_intervals` has all ADR-005 columns populated
- `hrr_actionable` view working

## Requirements

1. **Incremental extraction** - Only process sessions not already in `hr_recovery_intervals`
2. **Multi-source HR data** - Handle Polar, Apple Health, potentially Ultrahuman
3. **Pipeline integration** - Hook into `sync_pipeline.py` or create dedicated step
4. **Idempotency** - Safe to re-run without duplicates

## Approach Options

A. Add `--incremental` flag to `hrr_batch.py` that checks existing session IDs
B. Create dedicated `sync_hrr.py` that calls extraction functions
C. Integrate into existing Polar sync as post-processing step

## Acceptance Criteria

- [ ] New Polar sessions automatically get HRR intervals extracted
- [ ] No duplicate intervals on re-run
- [ ] Logging of sessions processed vs skipped
- [ ] Works with `make sync` or equivalent

## References

- ADR-005: HRR Pipeline Architecture
- Migration 014: HRR pipeline extensions
- `scripts/hrr_batch.py`: Extraction logic
