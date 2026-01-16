# Issue 009: Unified Workout Logging Path

**Created:** 2026-01-13  
**Status:** CLOSED (Superseded by Issue 013)  
**Priority:** N/A

## Resolution (2026-01-13)

**Closed without completing.** The underlying two-table schema (`strength_sessions`, `endurance_sessions`) is being replaced by the segment-based architecture in Issue 013.

Partial fixes implemented but not fully tested:
- Routing logic for endurance vs strength detection
- `duration_minutes` generated column fix
- `source='logged'` constraint fix
- Field name flexibility (`name` vs `exercise_name`)

These fixes are throwaway - Issue 013 introduces completely new tables and routing logic.

**Decision rationale:** Correctly logging daily activity is critical. Better to invest in the right architecture (Issue 013) than accumulate tech debt patching the old schema.

See: [Issue 013](./013-unified-workout-schema.md), [ADR-006](../adr/006-unified-workout-schema.md)

---

## Original Problem (Historical)

`arnold-training:log_workout` routed ALL workouts to `strength_sessions` table, regardless of workout type. This caused constraint violations when logging endurance activities.

The real problem was architectural: two rigid tables can't handle the diversity of sports and multi-modal sessions.
