# Issue 024: get_workout_by_date Returns Only First Block

**Created:** 2026-01-23  
**Status:** Resolved  
**Priority:** High  
**Type:** Bug

## Problem

`arnold-training:get_workout_by_date` returns only the first block of a multi-block workout instead of all blocks and sets.

### Observed Behavior

For Jan 22 workout (9 blocks, 36 sets):
- **Expected:** 9 blocks, 36 sets
- **Actual:** 1 block (warmup), 6 sets

Had to drop to raw Postgres queries to see/fix the actual data. The data itself was intact in Postgres - the MCP tool just didn't surface it properly.

### Root Cause

In `postgres_client.py`, method `get_session_by_date()`:

```python
cursor.execute("""
    SELECT 
        w.workout_id, w.start_time::date as session_date,
        ...
        b.block_id, b.modality, b.extra as block_extra
    FROM workouts w
    JOIN blocks b ON w.workout_id = b.workout_id
    WHERE w.start_time::date = %s
    ORDER BY w.created_at DESC
    LIMIT 1   # ← BUG: Returns ONE row (first block), not all blocks
""", (session_date,))
```

The query joins `workouts` to `blocks`, then applies `LIMIT 1`. This returns a single row, which is ONE block. The code then queries sets only for that single `block_id`, missing all other blocks.

## File Location

`/Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp/arnold_training_mcp/postgres_client.py`

Method: `get_session_by_date()` (around line 390)

## Fix

Restructure the method to:
1. Get the workout (without joining to blocks)
2. Get ALL blocks for that workout
3. Get ALL sets for ALL blocks

### Corrected Implementation

```python
def get_session_by_date(self, session_date: str) -> Optional[Dict[str, Any]]:
    """
    Get workout(s) for a date with all blocks and sets.
    
    Returns the most recent workout if multiple exist.
    """
    cursor = self.conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Get the workout (not joined to blocks yet)
    cursor.execute("""
        SELECT 
            workout_id, start_time::date as session_date,
            duration_seconds, rpe as session_rpe, notes, source, sport_type
        FROM workouts
        WHERE start_time::date = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (session_date,))

    workout = cursor.fetchone()
    if not workout:
        return None

    workout_id = workout['workout_id']
    
    result = {
        'session': self._convert_decimals(dict(workout)),
        'blocks': [],
        'sets': [],        # Flat list of all sets (for backward compat)
        'intervals': []
    }

    # 2. Get ALL blocks for this workout
    cursor.execute("""
        SELECT 
            block_id, seq, modality, block_type, duration_seconds,
            extra as block_extra
        FROM blocks
        WHERE workout_id = %s
        ORDER BY seq
    """, (workout_id,))
    
    blocks = cursor.fetchall()
    
    # 3. Get sets for each block
    total_volume = 0
    total_sets = 0
    total_reps = 0
    
    for block in blocks:
        block_dict = self._convert_decimals(dict(block))
        block_id = block['block_id']
        modality = block['modality'] or 'strength'
        
        if modality == 'strength' or modality is None:
            cursor.execute("""
                SELECT 
                    set_id as id, seq as set_order, exercise_id, exercise_name,
                    reps, load as load_lbs, rpe, rest_seconds,
                    is_warmup, failed, notes, extra
                FROM sets
                WHERE block_id = %s
                ORDER BY seq
            """, (block_id,))
            
            block_sets = [self._convert_decimals(dict(s)) for s in cursor.fetchall()]
            block_dict['sets'] = block_sets
            
            # Accumulate to flat list for backward compat
            result['sets'].extend(block_sets)
            
            # Accumulate totals
            for s in block_sets:
                reps = s.get('reps') or 0
                load = s.get('load_lbs') or 0
                total_volume += reps * load
                total_sets += 1
                total_reps += reps
                
        # TODO: Handle running/rowing/cycling intervals if needed
        
        result['blocks'].append(block_dict)
    
    # Add totals to session
    result['session']['total_volume_lbs'] = total_volume
    result['session']['total_sets'] = total_sets
    result['session']['total_reps'] = total_reps
    result['session']['block_count'] = len(blocks)
    
    return result
```

## Also Audit

These methods may have similar single-block assumptions:

- `get_recent_sessions()` - joins to blocks, may only return first block's data
- `get_sessions_for_briefing()` - subqueries reference `b.block_id` singular

Review and fix if they exhibit similar truncation behavior.

## Verification

After fix, restart Claude Desktop and test:

```
arnold-training:get_workout_by_date(date="2026-01-22")
```

**Expected result:**
```json
{
  "session": {
    "workout_id": "348c1dca-...",
    "session_date": "2026-01-22",
    "total_sets": 36,
    "total_reps": ...,
    "total_volume_lbs": ...,
    "block_count": 9
  },
  "blocks": [
    {"seq": 1, "block_type": "warmup", "sets": [...]},
    {"seq": 2, "block_type": "main", "sets": [...]},
    ...
  ],
  "sets": [/* flat list of all 36 sets */]
}
```

## Acceptance Criteria

- [ ] `get_session_by_date("2026-01-22")` returns all 9 blocks and 36 sets
- [ ] Backward compatibility: `result['sets']` contains flat list of all sets
- [ ] `result['blocks']` contains structured block data with nested sets
- [ ] Totals (volume, sets, reps) are calculated across ALL blocks
- [ ] `get_recent_sessions()` audited and fixed if needed
- [ ] `get_sessions_for_briefing()` audited and fixed if needed

## Related

- Issue 013: Unified workout schema (created the blocks structure)
- ADR-007: Workout schema design (blocks are first-class entities)
- Phase 7 migration: Verified log_workout writes correctly, but read path was broken
