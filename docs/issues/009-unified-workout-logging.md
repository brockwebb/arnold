# Issue 009: Unified Workout Logging Path

**Created:** 2026-01-13  
**Status:** FIXED  
**Priority:** Resolved

## Resolution (2026-01-13)

Implemented **Option A (Smart Routing)** - `log_workout` now detects workout type and routes appropriately:

1. **postgres_client.py**: Added `log_endurance_session()` method
2. **server.py**: `log_workout` handler now detects endurance workouts by checking for:
   - `sport` field
   - `distance_miles` or `distance_km`
   - `avg_pace`
   - Keywords in name: run, walk, hike, bike, cycle, swim, row, ruck
3. **neo4j_client.py**: Added `create_endurance_workout_ref()` for graph references

### Testing

Restart MCP server and test:
```json
// Should route to endurance_sessions
{"date": "2026-01-13", "name": "Easy run", "distance_miles": 3.0, "duration_minutes": 30}

// Should route to strength_sessions
{"date": "2026-01-13", "name": "Lower body", "exercises": [...]}
```

---

## Original Problem

Currently `arnold-training:log_workout` routes ALL workouts to `strength_sessions` table, regardless of workout type. This caused a constraint violation when logging an endurance run:

```
new row for relation "strength_sessions" violates check constraint "strength_sessions_source_check"
```

The workaround was manual SQL insert to `endurance_sessions` + manual Neo4j node creation.

## Current State (Wrong)

Multiple code paths exist:
- `log_strength_session()` - for strength workouts
- `endurance_sessions` table - exists but no logging function
- `log_workout` tool - hardcoded to call `log_strength_session()`

Different tables with different schemas:
- `strength_sessions` - has `sets` JSONB, `session_rpe`, etc.
- `endurance_sessions` - has `distance_miles`, `avg_pace`, `tss`, etc.

## Desired State

**ONE unified logging path.** Claude as the agentic/semantic layer determines:
- Which table(s) to write to based on workout content
- What metadata is relevant (TSS for endurance, sRPE for strength, etc.)
- When to ask for clarification (missing duration, RPE, etc.)

The MCP tool should accept a generic `workout_data` structure and route intelligently, OR we unify the tables.

## Architectural Options

### Option A: Smart Routing (Quick Fix)
Keep separate tables, add routing logic in `log_workout`:
```python
if workout_data.get('sport') or workout_data.get('distance_miles'):
    return log_endurance_session(workout_data)
else:
    return log_strength_session(workout_data)
```

### Option B: Unified Table (Better Long-Term)
Single `workout_sessions` table with:
- Common columns: date, name, duration, session_rpe, notes, source
- Type-specific JSONB: `strength_data`, `endurance_data`
- Or just one `workout_data` JSONB blob

Claude interprets and structures; Postgres just stores facts.

### Option C: Hybrid (Recommended)
- Keep analytics-optimized views/tables as needed
- Single `log_workout` entry point that writes to appropriate storage
- Claude never needs to know about table routing

## Design Principle

> "Claude as the agentic layer is more than smart enough to figure that out, or ask for clarification before logging."

The tool should be DUMB about workout types. Claude provides structured data, tool stores it. Type-specific concerns (which table, which columns) are implementation details hidden from Claude.

## Files to Modify

- `/src/arnold-training-mcp/arnold_training_mcp/server.py` - `log_workout` handler
- `/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py` - add unified logging or routing

## Related

- ADR-002: Plans in Neo4j, Facts in Postgres
- Issue 008: Briefing data gaps (discovered this bug)
