# Issue #021: QC Viz Shows Flagged Intervals as Rejected

**Created:** 2026-01-17  
**Priority:** Low  
**Status:** Open  
**Component:** `scripts/hrr_qc_viz.py`

## Problem

The QC visualization (`hrr_qc_viz.py`) shows intervals with `quality_status = 'flagged'` as if they were rejected. The table output shows correct status, but the visual rendering is wrong.

**Example from session 5:**
- Peak 3: Table shows `flagged`, but viz renders it as rejected (wrong color/style)

## Root Cause

Unknown - needs investigation. Likely using old field or different logic than `quality_status`.

## Proposed Solution

Check viz code for status determination:
```bash
grep -n "rejected\|quality_status" scripts/hrr_qc_viz.py
```

Ensure viz uses `quality_status` field from database, not computed logic.

## Acceptance Criteria

- [ ] Viz correctly distinguishes pass/flagged/rejected
- [ ] Color coding matches status (e.g., green=pass, yellow=flagged, red=rejected)
