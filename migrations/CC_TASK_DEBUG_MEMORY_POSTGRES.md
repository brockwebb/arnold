# CC Task: Debug Memory MCP Postgres Connection

**Priority:** HIGH - Blocking correct briefing display
**Context:** Briefing shows "28d Volume: 0 workouts, 0 sets" but data exists in database

## Verified Facts

1. `workout_summaries` view HAS data:
   ```sql
   SELECT workout_date, set_count FROM workout_summaries 
   WHERE workout_date >= '2025-12-25';
   -- Returns: Jan 22 = 33 sets, Jan 20 = 12 sets, etc.
   ```

2. `arnold-memory` config has correct DATABASE_URI:
   ```json
   "DATABASE_URI": "postgresql://brock@localhost:5432/arnold_analytics"
   ```

3. Query in `get_training_load_summary()` is correct:
   ```python
   SELECT COUNT(*) as workouts, COALESCE(SUM(set_count), 0) as total_sets...
   FROM workout_summaries WHERE workout_date BETWEEN %s AND %s
   ```

4. Exception is silently caught:
   ```python
   except Exception as e:
       logger.error(f"Error getting training load: {e}")
   # Returns empty result
   ```

## Debug Steps

1. Check `/tmp/arnold-memory-mcp.log` for errors:
   ```bash
   tail -100 /tmp/arnold-memory-mcp.log | grep -i "training\|error\|exception"
   ```

2. Add explicit debug logging in `get_training_load_summary()`:
   ```python
   # At start of try block:
   logger.info(f"Querying training load: {start_date} to {end_date}")
   
   # After query:
   logger.info(f"Training load result: {summary}")
   ```

3. Test connection directly:
   ```python
   # Add at top of get_training_load_summary:
   try:
       test = cur.execute("SELECT 1")
       logger.info(f"Postgres connection OK, DSN: {self.dsn}")
   except Exception as e:
       logger.error(f"Postgres connection FAILED: {e}")
   ```

4. Check if view exists from MCP's perspective:
   ```python
   cur.execute("SELECT COUNT(*) FROM workout_summaries")
   count = cur.fetchone()
   logger.info(f"workout_summaries row count: {count}")
   ```

## Likely Causes

1. **Connection failure** - DSN not resolving, auth issue
2. **View doesn't exist** - Different schema/search path
3. **Date math issue** - `start_date` or `end_date` malformed
4. **Transaction isolation** - Uncommitted data not visible

## Fix

Once root cause identified, fix the connection or query. Restart Claude Desktop to verify.

## Verification

After fix, `load_briefing` should show:
- **28d Volume:** ~20 workouts, ~244 sets (matching analytics MCP output)
