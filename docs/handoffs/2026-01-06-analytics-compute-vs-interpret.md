# Handoff: Analytics Layer — Compute vs Interpret

> **Date**: January 6, 2026
> **Thread**: Annotation Architecture Clarification
> **Status**: Complete

## Summary

Fixed the analytics layer architecture to properly separate **computed insights** (what tools should do) from **interpretation/suppression** (what Arnold should do).

## The Problem

The previous implementation had annotation-based suppression logic in `arnold-analytics-mcp`:

```python
# WRONG - This was hiding information from Arnold
def check_before_warning(cur, warning_type, ...):
    if annotation_exists:
        return {"suppress": True, ...}  # Arnold never sees this
```

This violated the architectural principle that Arnold (the intelligence layer) should see all data and decide what matters.

## The Solution

### Three-Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│  INTELLIGENCE LAYER (Arnold/Claude)                         │
│  - Synthesizes observations + annotations                   │
│  - Decides what to surface to user                         │
│  - "HRV is down but that's expected after birthday workout" │
└─────────────────────────────────────────────────────────────┘
                              ▲
                    observations + annotations
                              │
┌─────────────────────────────────────────────────────────────┐
│  ANALYTICS LAYER (MCP Tools)                                │
│  - Computes insights from raw data                         │
│  - Returns coaching_notes + annotations                    │
│  - Does NOT suppress or filter                             │
└─────────────────────────────────────────────────────────────┘
                              ▲
                         raw metrics
                              │
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER (Postgres)                                      │
│  - biometric_readings, strength_sessions, data_annotations │
└─────────────────────────────────────────────────────────────┘
```

### What Tools SHOULD Do (Computed Insights)

| Type | Example |
|------|---------|
| Threshold checks | "Sleep under 6hr threshold" |
| Trend detection | "HRV declining over 3 days" |
| Comparisons | "15% below 7-day avg" |
| Zone classification | "ACWR in high_risk zone" |
| Gap detection | "No Hip Hinge work in 10 days" |
| Aggregations | "Sleep averaging 6.2hrs" |

### What Tools Should NOT Do (Interpretation)

| Type | Example |
|------|---------|
| Suppression | "Don't show warning because annotation exists" |
| Recommendations | "Consider taking a rest day" |
| Filtering | "Only show warnings without annotations" |
| Priority decisions | "This is more important than that" |

## Changes Made

### Code Changes

**`src/arnold-analytics-mcp/arnold_analytics/server.py`:**

1. **Removed** `check_before_warning()` function
2. **Removed** `get_active_overrides()` function
3. **Simplified** `check_red_flags()` to return:
   - `observations[]` — All computed observations
   - `annotations[]` — All relevant annotations for the period
   - No `acknowledged` array, no suppression

4. **Preserved** `coaching_notes` in `get_readiness_snapshot()` and `get_training_load()`:
   - "HRV 42 is 15% below 7-day avg"
   - "Sleep 5.8hrs - under 6hr recovery threshold"
   - "ACWR 1.52 - elevated injury risk zone"
   - "Pattern gaps (no work in 10d): Hip Hinge, Squat"

### Documentation Changes

**`docs/ARCHITECTURE.md`:**
- Fixed annotation section for ADR-001 compliance
- Added new section: "Analytics Layer: Compute vs Interpret"
- Added three-layer diagram
- Added tables for what tools should/shouldn't do
- Added `coaching_notes` pattern example

**`docs/mcps/arnold-analytics.md`:**
- Complete rewrite documenting the compute vs interpret pattern
- Updated tool descriptions
- Added response pattern examples
- Documented key decisions

**`docs/HANDOFF.md`:**
- Updated with session details
- Added critical note #2 about analytics layer

## The Key Distinction

**Computed insight (OK):** "HRV 42 is 15% below 7-day avg" — this is arithmetic

**Interpretation (NOT OK):** "Don't show this because an annotation explains it" — this is judgment

The `coaching_notes` array contains pre-computed math that saves LLM context window and processing time. Arnold still sees everything and decides what to tell the user.

## Example Output

```json
{
  "hrv": {"value": 42, "avg_7d": 49, "trend": "declining"},
  "sleep": {"hours": 5.8, "quality_pct": 72},
  "acwr": {"trimp_based": 1.52, "zone": "high_risk"},
  "coaching_notes": [
    "HRV 42 is 15% below 7-day avg",
    "Sleep 5.8hrs - under 6hr recovery threshold",
    "ACWR 1.52 - elevated injury risk zone"
  ],
  "annotations": [
    {"date": "2026-01-03", "reason": "expected", 
     "explanation": "Birthday workout - HRV dip expected"}
  ]
}
```

Arnold synthesizes: "Your HRV is down but that's expected after Saturday's birthday workout. Sleep is the real concern — let's go lighter today."

## Files Modified

| File | Changes |
|------|---------|
| `src/arnold-analytics-mcp/arnold_analytics/server.py` | Removed suppression, kept computed insights |
| `src/arnold-journal-mcp/arnold_journal_mcp/server.py` | Added annotation tools |
| `src/arnold-journal-mcp/arnold_journal_mcp/postgres_client.py` | Added annotation CRUD methods |
| `docs/ARCHITECTURE.md` | Added Analytics Layer section |
| `docs/mcps/arnold-analytics.md` | Complete rewrite |
| `docs/automation/LAUNCHD_SYNC.md` | macOS daily sync template |
| `docs/HANDOFF.md` | Session documentation |

## Remaining Work

1. **Annotation creation tool** — DONE, needs MCP restart to test
2. **Neo4j annotation refs** — Create lightweight `Annotation` nodes with `EXPLAINS` relationships
3. **Test annotation tools** — After restart: `create_annotation`, `get_active_annotations`, `deactivate_annotation`
