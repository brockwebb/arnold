# Arnold Training Coach MCP Server

The strength & conditioning coach for Arnold - handles workout planning, exercise selection, and logging.

## Role

Arnold Training MCP is the **coach** - it creates workout plans, selects exercises, checks safety against injuries, and logs execution with deviation tracking.

## Tools

### Context
- `get_training_context` - Load injuries, equipment, recent history, goals
- `get_active_constraints` - Get current injury-based constraints

### Exercise Selection
- `suggest_exercises` - Find exercises by pattern/muscle/equipment
- `check_exercise_safety` - Validate exercise against current constraints
- `find_substitutes` - Find alternatives for contraindicated exercises

### Planning
- `create_workout_plan` - Create structured plan with blocks and sets
- `get_plan_for_date` - Get plan for a specific date
- `get_planned_workout` - Get full plan details by ID
- `confirm_plan` - Lock in plan for execution

### Execution
- `complete_as_written` - Mark plan completed with no changes
- `complete_with_deviations` - Complete plan with recorded deviations
- `skip_workout` - Mark plan as skipped with reason
- `log_workout` - Log ad-hoc/unplanned workout

### History
- `get_workout_by_date` - Get executed workout by date
- `get_recent_workouts` - Summary of recent workouts

## Workflow

```
1. Coach creates plan
   → create_workout_plan()

2. User reviews plan
   → "Why are we doing pendlay rows?"
   → Coach explains based on goals/constraints

3. User requests adjustments
   → Coach modifies plan
   → create_workout_plan() (new version)

4. User confirms
   → confirm_plan()

5. User executes (IRL)

6. User reports completion
   → "Done" → complete_as_written()
   → "Done but had to drop weight" → complete_with_deviations()
   → "Skipped, felt sick" → skip_workout()
```

## Installation

```bash
cd src/arnold-training-mcp
pip install -e .
```

## Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arnold-training": {
      "command": "python",
      "args": ["-m", "arnold_training_mcp.server"],
      "cwd": "/path/to/arnold/src/arnold-training-mcp",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "NEO4J_DATABASE": "arnold"
      }
    }
  }
}
```

## Dependencies

- `mcp>=0.1.0`
- `neo4j>=5.0.0`
- `python-dotenv>=1.0.0`

## Graph Schema

Uses these Neo4j node types:
- `PlannedWorkout` - Workout plans
- `PlannedBlock` - Blocks within plans
- `PlannedSet` - Sets within blocks (links to Exercise)
- `Workout` - Executed workouts
- `WorkoutBlock` - Blocks in executed workouts
- `Set` - Executed sets

Key relationships:
- `(Person)-[:HAS_PLANNED_WORKOUT]->(PlannedWorkout)`
- `(PlannedSet)-[:PRESCRIBES]->(Exercise)`
- `(Workout)-[:EXECUTED_FROM]->(PlannedWorkout)`
- `(Set)-[:DEVIATED_FROM]->(PlannedSet)` (when actual differs from plan)
