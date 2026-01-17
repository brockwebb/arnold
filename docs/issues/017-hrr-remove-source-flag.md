# Issue #017: Remove --source flag requirement from hrr_feature_extraction.py

**Type:** enhancement / tech-debt
**Status:** Open

## Problem

The script requires `--source polar` or `--source endurance` to be specified manually. This adds friction and is error-prone.

## Solution

Auto-detect session source by checking both tables:

```python
def detect_session_source(conn, session_id: int) -> Optional[str]:
    """Check both tables and return which has this session."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM polar_sessions WHERE id = %s", (session_id,))
        if cur.fetchone():
            return 'polar'
        cur.execute("SELECT 1 FROM endurance_sessions WHERE id = %s", (session_id,))
        if cur.fetchone():
            return 'endurance'
    return None
```

Then use this in main() when `--session-id` is provided without `--source`.
