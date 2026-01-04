# arnold-training-mcp

> **Purpose:** Workout planning, execution, and exercise selection

## What This MCP Owns

- **PlannedWorkout** lifecycle (create → confirm → complete/skip)
- **Workout** logging (both from plans and ad-hoc)
- Exercise safety checks and substitutions
- Training context for programming decisions

## Boundaries

| This MCP Does | This MCP Does NOT |
|---------------|-------------------|
| Create workout plans | Manage athlete profile |
| Log completed workouts | Record biometric observations |
| Check exercise safety vs injuries | Define injuries/constraints |
| Find exercise substitutes | Manage equipment inventory |
| Track plan status | Calculate training metrics (that's analytics) |

## Tools

### Context
| Tool | Purpose |
|------|---------|
| `get_coach_briefing` | Everything needed at conversation start |
| `get_training_context` | Injuries, equipment, recent workouts, goals |
| `get_active_constraints` | Current injury constraints for filtering |

### Exercise Selection
| Tool | Purpose |
|------|---------|
| `suggest_exercises` | Find exercises by pattern/muscle |
| `check_exercise_safety` | Validate against constraints |
| `find_substitutes` | Alternatives preserving characteristics |

### Planning
| Tool | Purpose |
|------|---------|
| `create_workout_plan` | Create plan with blocks and sets |
| `get_plan_for_date` | Retrieve plan by date |
| `get_planned_workout` | Retrieve plan by ID |
| `confirm_plan` | Mark plan ready to execute |
| `get_upcoming_plans` | Plans for next N days |
| `get_planning_status` | Day-by-day coverage view |

### Execution
| Tool | Purpose |
|------|---------|
| `complete_as_written` | Convert plan to workout (no changes) |
| `complete_with_deviations` | Convert plan with recorded changes |
| `skip_workout` | Mark plan as skipped with reason |
| `log_workout` | Log ad-hoc (unplanned) workout |

### History
| Tool | Purpose |
|------|---------|
| `get_workout_by_date` | Retrieve executed workout |
| `get_recent_workouts` | Summary of last N days |

## Key Decisions

### Atomic Writes with UNWIND (Jan 2026)

**Context:** Original implementation used Python loops with separate `session.run()` calls per block/set. If creation failed mid-workout, orphaned nodes were left in the database.

**Decision:** Refactor all write operations to use single Cypher statements with `UNWIND`. Pre-validate exercise IDs before writing.

**Consequence:** All-or-nothing semantics. Either complete workout/plan exists, or nothing does. Slightly more complex Cypher, but guarantees data integrity.

**Affected functions:**
- `create_planned_workout`
- `log_adhoc_workout`
- `complete_workout_with_deviations`

### Plan vs Execution Separation

**Context:** Considered routing ad-hoc workouts through planning (create plan → immediately complete).

**Decision:** Keep planning and execution as separate code paths.

**Rationale:**
- Plans have `prescribed_*` fields (intent)
- Workouts have actual values (what happened)
- Ad-hoc workouts are actuals, not prescriptions
- Routing through plans would create orphan PlannedWorkout nodes

**Consequence:** Two write paths to maintain, but cleaner data model and semantics.

### plan_id vs id Property (Jan 2026)

**Context:** PlannedWorkout nodes had `id` property, but Neo4j queries returned synthetic IDs. Caused mismatch between tool responses and actual data.

**Decision:** Use explicit `plan_id` property. All queries use `COALESCE(pw.plan_id, pw.id)` for backward compatibility with existing data.

**Consequence:** Stable, reliable plan identification. Migration handled existing nodes.

### Date Validation

**Context:** Plan created for "January 3" was stored as 2025-01-03 instead of 2026-01-03 due to ambiguous input.

**Decision:** Validate dates in `create_planned_workout`:
- Reject if year < current year (obvious error)
- Warn if date > 7 days in past (probably meant ad-hoc)

**Consequence:** Catches common errors at creation time, not when trying to execute.

## Data Model

```
(Person)-[:HAS_PLANNED_WORKOUT]->(PlannedWorkout)
(PlannedWorkout)-[:HAS_PLANNED_BLOCK]->(PlannedBlock)
(PlannedBlock)-[:CONTAINS_PLANNED]->(PlannedSet)
(PlannedSet)-[:PRESCRIBES]->(Exercise)

(Person)-[:PERFORMED]->(Workout)
(Workout)-[:HAS_BLOCK]->(WorkoutBlock)
(WorkoutBlock)-[:CONTAINS]->(Set)
(Set)-[:OF_EXERCISE]->(Exercise)

(Workout)-[:EXECUTED_FROM]->(PlannedWorkout)  // Links execution to plan
(Set)-[:DEVIATED_FROM]->(PlannedSet)          // Records changes
```

## Dependencies

- **Neo4j** — All data storage
- **profile.json** — Person ID resolution
- **Exercise nodes** — Must exist before planning/logging

## Known Issues / Tech Debt

1. ~~**Multiple round-trips in read functions**~~ — Fixed Jan 3, 2026. All read functions now use single queries with `CALL {}` subqueries.
