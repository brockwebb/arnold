# HRR R² Computation Handoff

**Date:** 2026-01-16  
**From:** Session implementing R²-gated HRR drops  
**To:** Next thread  
**Status:** Implementation complete, needs documentation update

---

## What Was Done

Implemented robust R² computation for all HRR windows in `/scripts/hrr_feature_extraction.py`:

1. **Upfront HR imputation** - `impute_hr_series()` creates complete second-by-second array via linear interpolation before any R² computation

2. **Extended sample collection** - `r2_samples` extends up to 360s from peak (to ensure 300s from onset even with 60s onset delay)

3. **Robust exponential fitting** - `fit_window_r2()` tries 4 fitting strategies with 'trf' method, falls back to heuristic if all fail. **Never returns None if ≥10 samples exist.**

4. **R²-gated HRR drops** - HRR values only populated where corresponding R² ≥ 0.75 (`R2_THRESHOLD`)

5. **Detected segment metrics** - Added `r2_detected`, `hr_detected`, `hrr_detected` for organic interval duration (not just standard 60/120/180/240/300 endpoints)

---

## Key Decision: Compute All R² Values Unconditionally

**We decided NOT to cascade (stop computing after first failure).**

### Rationale:

1. **Calculations are cheap** - A few extra curve_fit calls per interval is negligible

2. **Prevents silent failures** - Previously, curve_fit exceptions returned None, hiding whether data existed or fit failed. Now you always see a value.

3. **Longer windows can recover** - Example from session 71:
   ```
   Row 10: 0-60 = 0.538* (FAIL) but 0-120 = 0.843 (PASS)
   ```
   A cascade would have missed this valid 120s window.

4. **No blank cells philosophy** - Every cell should communicate something:
   - `NULL` = insufficient data (<10 samples in window)
   - `0.002*` = computed, exponential explains nothing (data exists but doesn't fit model)
   - `0.843` = computed, good fit
   - `-0.000*` = computed, model worse than mean (HR rising, not falling)

### What the values mean:

| Value | Meaning |
|-------|---------|
| `-` (NULL) | Insufficient data - window extends beyond available samples |
| `-0.000*` to `0.050*` | Data exists but doesn't follow exponential decay |
| `0.75+` | Good exponential fit, HRR drop is trustworthy |

---

## Files Modified

- `/scripts/hrr_feature_extraction.py`:
  - `fit_window_r2()` - Robust multi-strategy fitting, never returns None if data exists
  - `impute_hr_series()` - Upfront gap filling
  - `compute_features()` - Computes ALL R² windows unconditionally
  - `print_summary_tables()` - Added 0-30 column, renamed slope to slp90

- RecoveryInterval dataclass additions:
  - `r2_detected`, `hr_detected`, `hrr_detected`

---

## Action Required: Update Issue Documentation

**Please update the GitHub issue tracking HRR feature extraction with:**

1. **Architecture Decision Record (ADR):**
   - Title: "Compute All R² Windows Unconditionally"
   - Context: Originally considered cascading (stop after first R² failure)
   - Decision: Compute all windows where data exists
   - Consequences: 
     - Slightly noisier summary table (low R² values visible instead of NULL)
     - No silent failures
     - Longer windows can recover validity even if shorter windows fail
     - Aligns with "no blank cells" data philosophy

2. **Update the R² interpretation guide:**
   ```
   NULL (-) = Insufficient data in window
   Value with * = Below 0.75 threshold (HRR drop not computed)
   Value without * = Passes threshold (HRR drop is trustworthy)
   ```

3. **Note on valid count change:**
   - Valid interval count may decrease because quality filter now sees low R² values that were previously NULL
   - This is correct behavior - filter is now seeing real data quality
   - If old valid counts are desired, adjust filter thresholds (separate concern)

---

## Test Command

```bash
psql arnold_analytics -c "DELETE FROM hr_recovery_intervals WHERE polar_session_id = 71"
python scripts/hrr_feature_extraction.py --session-id 71 --source polar --include-rejected
```

Expected: All R² cells populated (no `-` except where data genuinely doesn't extend to that window).

---

## Sample Output (Session 71)

```
--- TABLE 2: R² by Window ---
Ord   0-30   0-60  30-90   slp90  0-120  0-180  0-240  0-300    Det
--- ------ ------ ------ ------- ------ ------ ------ ------ ------
  1  0.843  0.933 0.002*  +0.323 0.013* -0.000* -0.000* -0.000* 0.343*
  4  0.956  0.964  0.875  -0.067  0.977  0.924 0.545* 0.246*  0.858
 14  0.993  0.997  0.995  -0.118  0.995  0.996  0.993  0.986  0.993
```

Row 1 shows the pattern: good early fit (0-30, 0-60), but 30-90 and beyond don't follow exponential (activity resumed). The near-zero values are **information**, not failures.

---

## Transcript Location

Full session transcript: `/mnt/transcripts/2026-01-16-18-17-51-hrr-imputation-r2-gating.txt`
