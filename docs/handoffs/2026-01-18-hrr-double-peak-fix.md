# Handoff: Fix HRR Double-Peak Re-Anchoring

**Date:** 2026-01-18  
**Priority:** HIGH - Pipeline broken  
**Status:** Ready for new thread

---

## The Problem

Session 71 interval 3 is being **rejected as `double_peak`** when it should be **automatically re-anchored** to the true peak and pass.

The re-anchoring logic EXISTS in the code but isn't working. Either:
- It's not running
- It's running but the result isn't being used
- Some thread broke it

## Expected Behavior

When `r2_0_30 < 0.5` (plateau/double-peak detected):

1. `find_true_peak_plateau()` runs - finds offset to true peak
2. If offset > 5s: re-create interval from new anchor point
3. Recompute all R² values on new interval
4. If new `r2_0_30 >= 0.5`: USE the re-anchored interval, add `PLATEAU_RESOLVED` flag
5. ONLY if re-anchor fails: reject as `double_peak`

## Current (Broken) Behavior

Interval rejected as `double_peak` without successful re-anchor.

## File to Fix

`/scripts/hrr_feature_extraction.py`

## Relevant Code Sections

### 1. Plateau detection in `extract_features()` (~line 900)

```python
# Plateau detection: if r2_0_30 < threshold, try to find true peak
if interval.r2_0_30 is not None and interval.r2_0_30 < config.gate_r2_0_30_threshold:
    # ... re-anchoring logic here
```

This block should:
- Detect plateau
- Call `find_true_peak_plateau()`
- Re-create interval if offset found
- Recompute features
- Replace original interval with re-anchored one

### 2. Hard reject in `assess_quality()` (~line 1050)

```python
# Gate 10: r2_0_30 < 0.5 = double-peak detection
if interval.r2_0_30 is not None and interval.r2_0_30 < 0.5:
    hard_reject = True
    reject_reason = 'double_peak'
```

This runs AFTER `extract_features()` returns. If re-anchoring worked, `r2_0_30` should be >= 0.5 and this gate won't trigger.

## Debug Steps

1. Add logging to see what's happening:
```python
logger.info(f"Interval {interval_order}: r2_0_30={interval.r2_0_30}, checking plateau...")
```

2. After `find_true_peak_plateau()`:
```python
logger.info(f"Plateau offset={plateau_offset}, confidence={plateau_confidence}")
```

3. After re-anchor attempt:
```python
logger.info(f"Re-anchor result: r2_0_30 {old_r2} -> {new_interval.r2_0_30}")
```

4. Run: `python scripts/hrr_feature_extraction.py --session-id 71`

5. Find interval 3 in output - trace why re-anchor failed or wasn't used

## Test Case

**Session 71, Interval 3:**
- Currently: rejected as `double_peak`
- Expected: pass with `PLATEAU_RESOLVED` flag, or clear log showing why re-anchor didn't help

## Do NOT

- Add new columns to the database
- Add new metrics or features
- Change any thresholds
- Add "nice to have" improvements

Fix THIS bug only.

## Verification

After fix:
```bash
python scripts/hrr_feature_extraction.py --session-id 71
```

Interval 3 should either:
- Show `pass` status with `PLATEAU_RESOLVED` flag
- Show clear log explaining why re-anchor didn't improve R²

---

## Context Files

- `/scripts/hrr_feature_extraction.py` - the extraction pipeline
- `/config/hrr_extraction.yaml` - threshold configuration
- `/docs/hrr_quality_gates.md` - quality gate documentation
