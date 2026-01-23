# CC Task: Audit and Fix Briefing Data Sources

**Priority:** HIGH - Production readiness
**Principle:** Single source of truth per metric. No parallel query implementations.

## Problem

`load_briefing` in memory MCP has its own queries for metrics that analytics MCP already computes correctly. This creates:
- Two code paths that drift apart
- Double maintenance burden
- Inconsistent results (briefing shows "0 workouts" while analytics shows 20)

## Current State

| Metric | Briefing Shows | Analytics Shows | Root Cause |
|--------|----------------|-----------------|------------|
| 28d Volume | 0 workouts, 0 sets | 20 workouts, 244 sets | Different query path |
| HRV | No data | (not checked) | Query or sync issue |
| Sleep | No data | (not checked) | Query or sync issue |
| Recent workouts | ✅ Correct | N/A | Works |

## Files to Audit

**Memory MCP (briefing source):**
- `/src/arnold-memory-mcp/arnold_memory_mcp/server.py` - `load_briefing` handler
- `/src/arnold-memory-mcp/arnold_memory_mcp/neo4j_client.py` - may have workout queries
- `/src/arnold-memory-mcp/arnold_memory_mcp/postgres_client.py` - may have analytics queries

**Analytics MCP (working source):**
- `/src/arnold-analytics-mcp/arnold_analytics/server.py` - `get_training_load`, `get_readiness_snapshot`

## Task 1: Trace Briefing Queries

Find where "28d Volume" comes from in load_briefing:

```bash
grep -n "28d\|volume\|workouts" /Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp/arnold_memory_mcp/*.py
```

Identify:
1. Which function computes it
2. Which table/view it queries
3. Why it returns 0 when data exists

## Task 2: Fix 28d Volume

**Option A (Preferred):** Call analytics MCP's query directly
- Memory MCP imports or calls the same function analytics uses
- Single implementation, single maintenance point

**Option B:** Use the same view
- Both MCPs query `training_monotony_strain` or `workout_summaries`
- Still two call sites, but same underlying data

**Option C (Worst):** Fix the broken query in memory MCP
- Keeps parallel implementations
- Will drift again

Implementation for Option A:
```python
# In memory MCP's load_briefing
# Instead of custom query:
from arnold_analytics.server import get_training_load_data  # or similar

# Or query the same view analytics uses:
cursor.execute("""
    SELECT COUNT(*) as workouts, SUM(daily_sets) as sets, SUM(daily_volume) as volume
    FROM training_monotony_strain
    WHERE workout_date >= CURRENT_DATE - 28
""")
```

## Task 3: Trace HRV/Sleep Queries

Find where biometric data comes from:

```bash
grep -n "hrv\|sleep\|biometric\|ultrahuman" /Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp/arnold_memory_mcp/*.py
```

Check:
1. Which tables are queried (should be `biometrics` or similar)
2. Whether data exists: `SELECT * FROM biometrics WHERE date >= '2026-01-15' LIMIT 5;`
3. If no data, it's a sync issue not a query issue

## Task 4: Document Query Ownership

Create or update a reference showing which MCP owns which queries:

| Metric | Owner MCP | Table/View | Notes |
|--------|-----------|------------|-------|
| Training load (28d) | analytics | training_monotony_strain | Authoritative |
| ACWR | analytics | training_monotony_strain | |
| HRV trends | analytics | biometrics + views | |
| Recent workouts | memory | Neo4j StrengthWorkout | For briefing context |
| Workout details | training | workouts/blocks/sets | Authoritative |

Other MCPs should call the owner or use the same view, not reimplement.

## Task 5: Sync Pipeline

Check if sync runs automatically:

```bash
# Is there a cron job?
crontab -l | grep -i arnold

# Is there a launchd plist?
ls ~/Library/LaunchAgents/ | grep -i arnold

# What does the sync script do?
cat /Users/brock/Documents/GitHub/arnold/scripts/sync_pipeline.py | head -50
```

If no automation exists, create:
1. A wrapper script that runs full sync
2. A cron entry or launchd plist to run it (daily at minimum)
3. Log output to `/Users/brock/Documents/GitHub/arnold/logs/sync.log`

## Task 6: Observation Lifecycle

The briefing shows stale flags like "complete_as_written has bugs" that were fixed.

Find where observations are stored:
```bash
grep -n "observation\|flag\|coaching_note" /Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp/arnold_memory_mcp/*.py
```

Options:
1. **Add resolved_at timestamp** - Observations can be marked resolved
2. **Add expiry** - Observations auto-expire after N days unless refreshed
3. **Manual cleanup** - Provide a tool to mark observations resolved

Check Neo4j for observation nodes:
```cypher
MATCH (o:CoachingObservation) 
WHERE o.content CONTAINS 'complete_as_written' OR o.content CONTAINS 'postgres_id'
RETURN o.content, o.created_at, o.observation_type
```

## Verification

After fixes:

```bash
# Test briefing shows correct 28d volume
# Should match analytics output

# In Claude Desktop:
# 1. Call arnold-memory:load_briefing
# 2. Call arnold-analytics:get_training_load with days=28
# 3. Compare workout count, set count, volume - should match
```

## Success Criteria

1. Briefing's "28d Volume" matches `get_training_load()` output
2. No duplicate query implementations for the same metric
3. HRV/Sleep either shows data or clearly indicates sync needed
4. Stale observations have a path to resolution
5. Sync pipeline has automation (cron/launchd)
