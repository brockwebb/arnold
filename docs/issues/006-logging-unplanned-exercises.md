# Issue 006: Logging Workflow - Unplanned Exercises

> **Created**: January 7, 2026
> **Status**: Backlog  
> **Priority**: High (data loss during active training)

## Problem

When completing a planned workout with additional exercises not in the original plan, the current workflow loses data:

**Example (Jan 6, 2026):**
- Plan had: Chin-ups, rows, face pulls, ring support
- User did extras: Pelvic bridges, cat-cow, 69-second deadhang
- `complete_with_deviations` logged: Only planned exercises + deviations
- **Lost**: The unplanned exercises (had to be manually inserted)

## Root Cause

`arnold-training:complete_with_deviations` only handles:
1. Sets that match existing `planned_set_id` (deviations)
2. Cannot add entirely new exercises to the session

The assistant put the unplanned work into a journal entry narrative, but journal entries don't create `strength_sets` records.

## Required Fix

Options:

### Option A: Enhance `complete_with_deviations`
Add `additional_sets` parameter:
```python
{
  "plan_id": "PLAN:...",
  "deviations": [...],  # Existing
  "additional_sets": [   # NEW
    {
      "exercise_id": "CANONICAL:FFDB:1888",
      "exercise_name": "Bar Dead Hang",
      "block_name": "Cooldown",
      "block_type": "cooldown",
      "actual_reps": 1,
      "set_type": "timed",
      "notes": "69 second hold"
    }
  ]
}
```

### Option B: Separate tool for additions
Create `add_unplanned_sets` tool to append sets to an existing session.

### Option C: Update assistant prompting
Train the assistant to call `log_workout` for unplanned work separately.

## Recommendation

**Option A** is cleanest - keeps workout completion atomic. User reports everything, it all gets logged in one call.

## Validation

After fix:
```sql
-- Verify all reported exercises appear in strength_sets
SELECT exercise_name, COUNT(*) 
FROM strength_sets 
WHERE session_id = ? 
GROUP BY exercise_name;
```

## Related

- ADR-002: Strength data in Postgres
- Issue with session 166 (Jan 6, 2026)
