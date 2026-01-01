# Arnold Training MCP - Claude Desktop Setup

## Prerequisites

1. ✅ arnold-profile-mcp working (profile exists)
2. ✅ Neo4j running at `bolt://localhost:7687`
3. ✅ Arnold conda environment active

## Installation Steps

### 1. Install the Package

```bash
cd /Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp
/opt/anaconda3/envs/arnold/bin/pip install -e .
```

### 2. Locate Claude Desktop Config

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

### 3. Add Arnold Training MCP

Add to the `mcpServers` section:

```json
{
  "mcpServers": {
    "arnold-profile": {
      "command": "/opt/anaconda3/envs/arnold/bin/python",
      "args": [
        "/Users/brock/Documents/GitHub/arnold/src/arnold-profile-mcp/arnold_profile_mcp/server.py"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "YOUR_PASSWORD_HERE",
        "NEO4J_DATABASE": "arnold"
      }
    },
    "arnold-training": {
      "command": "/opt/anaconda3/envs/arnold/bin/python",
      "args": [
        "/Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp/arnold_training_mcp/server.py"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "YOUR_PASSWORD_HERE",
        "NEO4J_DATABASE": "arnold"
      }
    }
  }
}
```

### 4. Restart Claude Desktop

1. **Quit Claude Desktop completely** (Cmd+Q)
2. **Reopen Claude Desktop**

### 5. Verify MCP is Loaded

Check for the hammer icon 🔨 and verify both MCPs appear in tools.

## Testing in Claude Desktop

### Test 1: Get Training Context

```
User: "What's my current training context?"
```

Expected: JSON with injuries, equipment, recent workouts, goals.

### Test 2: Suggest Exercises

```
User: "Suggest some hip hinge exercises"
```

Expected: List of exercises with Hip Hinge movement pattern.

### Test 3: Check Exercise Safety

```
User: "Is back squat safe for me right now?"
```

Expected: Safety check against current knee injury constraints.

### Test 4: Create a Plan

```
User: "Create a lower body workout plan for tomorrow"
```

Expected: Claude structures a plan and saves it via create_workout_plan.

### Test 5: Complete a Workout

```
User: "I finished the workout as planned"
```

Expected: complete_as_written converts plan to executed workout.

### Test 6: Log Deviation

```
User: "Done, but had to drop weight on the last set of squats - fatigue"
```

Expected: complete_with_deviations records the deviation.

## Tool Reference

### Context
- `get_training_context` - All context for planning
- `get_active_constraints` - Current injury constraints

### Exercise Selection
- `suggest_exercises` - Find by pattern/muscle
- `check_exercise_safety` - Validate against constraints
- `find_substitutes` - Alternatives for an exercise

### Planning
- `create_workout_plan` - Create new plan
- `get_plan_for_date` - Get plan by date
- `confirm_plan` - Lock in plan

### Execution
- `complete_as_written` - Done, no changes
- `complete_with_deviations` - Done with changes
- `skip_workout` - Skipped with reason
- `log_workout` - Ad-hoc workout

### History
- `get_workout_by_date` - Past workout
- `get_recent_workouts` - Summary

## Troubleshooting

### "No profile found" Error

The training MCP requires a profile. Create one first:
```
User: "Create my profile via intake"
```

### MCP Not Loading

Check logs:
```bash
tail -f /tmp/arnold-training-mcp.log
tail -f ~/Library/Logs/Claude/mcp*.log
```

### Import Errors

```bash
cd /Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp
/opt/anaconda3/envs/arnold/bin/pip install -e .
```

## Workflow Example

Full coaching conversation:

```
User: "What's my training context?"
[Claude calls get_training_context]

User: "Plan a push-focused workout for tomorrow"
[Claude calls get_training_context, suggest_exercises, create_workout_plan]

User: "Why pendlay rows in a push workout?"
[Claude explains: balanced programming, pulling for shoulder health]

User: "Swap bench press for dumbbell press - my shoulder feels off"
[Claude calls find_substitutes, creates new plan]

User: "Looks good, lock it in"
[Claude calls confirm_plan]

--- Next day ---

User: "Done, but had to drop weight on the last row set"
[Claude calls complete_with_deviations with fatigue reason]
```
