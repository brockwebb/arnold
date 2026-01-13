# Handoff: Consolidated Briefing Architecture

**Date:** 2026-01-13
**From:** Claude (briefing consolidation session)
**Status:** Implementation complete, needs testing

## What Was Done

### Problem Identified
Architecture had drifted from original design intent. Instead of ONE call at conversation start, the system required THREE:
1. `memory:load_briefing` (Neo4j only)
2. `analytics:check_red_flags` (Postgres)
3. `training:get_planning_status` (mixed)

This violated the design principle "one call gets everything" and leaked implementation details (data layer separation) into the API surface.

### Solution Implemented

**Consolidated `memory:load_briefing`** to query BOTH databases and return comprehensive context:

```
┌─────────────────────────────────────────────────────────────────┐
│                    load_briefing                                 │
│                                                                  │
│  ┌──────────────────────┐    ┌──────────────────────┐          │
│  │       Neo4j          │    │      Postgres         │          │
│  │  - Goals, Block      │    │  - HRV, Sleep, RHR    │          │
│  │  - Injuries          │    │  - ACWR, Load         │          │
│  │  - Observations      │    │  - HRR Trends         │          │
│  │  - Equipment         │    │  - Annotations        │          │
│  │  - Recent Workouts   │    │  - Pattern Gaps       │          │
│  └──────────────────────┘    └──────────────────────┘          │
│                                                                  │
│                    → Single formatted response                   │
└─────────────────────────────────────────────────────────────────┘
```

### Files Created/Modified

**New:**
- `/src/arnold-memory-mcp/arnold_memory_mcp/postgres_client.py` - PostgresAnalyticsClient for briefing analytics

**Modified:**
- `/src/arnold-memory-mcp/arnold_memory_mcp/server.py` - Consolidated load_briefing with Postgres integration
- `/src/arnold-training-mcp/arnold_training_mcp/server.py` - Deprecated `get_coach_briefing`
- `/docs/mcps/README.md` - Updated architecture with database access patterns
- `/docs/mcps/arnold-memory.md` - Comprehensive memory MCP documentation

### Architecture Note Added

Documented the distinction between:
- **postgres-mcp** (generic tool) - Raw SQL for Claude's ad-hoc queries
- **PostgresAnalyticsClient** (private helper) - Domain-specific queries inside MCPs

Internal clients are implementation details, not exposed tools.

## What Needs Testing

1. **Restart arnold-memory-mcp** and verify it starts without errors
2. **Call `memory:load_briefing`** and verify:
   - Neo4j data appears (goals, block, injuries, observations)
   - Postgres data appears (HRV, sleep, ACWR, HRR trends)
   - Coaching alerts section populated
   - No errors in `/tmp/arnold-memory-mcp.log`
3. **Verify `training:get_coach_briefing`** returns deprecation notice

## What's Next

After verifying the consolidated briefing works:

1. **Check open issues** at `docs/issues/` for next priorities
2. **Likely candidates:**
   - HRR sync integration (incremental sync pipeline)
   - Any data quality issues surfaced
   - Block summary workflows

## Key Files for Context

```
/Users/brock/Documents/GitHub/arnold/
├── src/arnold-memory-mcp/arnold_memory_mcp/
│   ├── server.py           # Consolidated briefing implementation
│   ├── postgres_client.py  # NEW - analytics queries
│   └── neo4j_client.py     # Existing Neo4j queries
├── docs/mcps/
│   ├── README.md           # Updated architecture overview
│   └── arnold-memory.md    # Memory MCP documentation
└── docs/handoffs/
    └── 2026-01-13-consolidated-briefing.md  # This file
```

## Commands for Next Session

```bash
# Restart the memory MCP (Claude Desktop restart or manual)
# Then test:
# 1. Call memory:load_briefing
# 2. Verify output includes "Today's Status" section with HRV/Sleep/ACWR
# 3. Check /tmp/arnold-memory-mcp.log for errors
```
