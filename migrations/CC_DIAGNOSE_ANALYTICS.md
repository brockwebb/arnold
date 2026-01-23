# CC Task: Diagnose Analytics MCP Schema Errors

## Problem
Analytics MCP tools (`get_training_load`, `get_exercise_history`, `check_red_flags`) fail with schema errors after table renames.

## Investigation Steps

### 1. Get current view definition
```bash
psql -h localhost -U brock -d arnold_analytics -c "SELECT pg_get_viewdef('workout_summaries', true);"
```

### 2. Find what columns analytics MCP expects
```bash
grep -n "workout_date\|patterns\|exercises\|duration_min" src/arnold-analytics-mcp/arnold_analytics/server.py
```

### 3. Compare and document gaps

Create a table showing:
- Column MCP expects
- What view actually has
- Fix needed

### 4. Check other views used by analytics
```bash
grep -n "FROM.*daily\|FROM.*summaries\|FROM.*load" src/arnold-analytics-mcp/arnold_analytics/server.py | head -20
```

### 5. Report findings

Update `/migrations/HANDOFF_2026-01-22_PHASE7.md` with:
- Exact view definition
- All column mismatches found
- Which queries are affected
- Proposed SQL fix

## Do NOT
- Make any changes yet
- Run extensive greps across entire codebase
- Fix anything - just diagnose

## Output
Append findings to the handoff file.
