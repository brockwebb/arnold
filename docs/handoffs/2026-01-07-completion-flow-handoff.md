# Handoff: Arnold System Improvements — January 7, 2026

## Session Summary

Implemented critical data capture improvements for sRPE-based training load calculations and pattern tracking.

## Completed This Session

### Items 1-2: Session RPE & Duration Capture
**Files Modified:** `/src/arnold-training-mcp/arnold_training_mcp/server.py`

- Added `session_rpe` (1-10) and `actual_duration_minutes` parameters to:
  - `complete_as_written` tool
  - `complete_with_deviations` tool
- Tool descriptions now prompt Coach to ask "How hard was that session?"
- Handlers pass data to `postgres_client.log_strength_session()`
- Response shows calculated sRPE load or warning if RPE missing
- Data cascade: actual_duration → plan.estimated_duration → 45min default (in view)

**Why it matters:** Foster's sRPE formula (RPE × Duration) is the gold standard for training load. Previously we were imputing most values. Now we capture ground truth at completion time.

### Item 3: Pattern Frequency View (TECH DEBT — MUST FIX)
**Database:** `arnold_analytics`

Created `pattern_last_trained` view — **BUT IT'S WRONG.**

The view uses **regex inference** from exercise names to guess movement patterns. This was a shortcut. Neo4j already has proper `Exercise -[:TRAINS_PATTERN]-> MovementPattern` relationships.

**⚠️ DROP THIS VIEW** and rebuild it correctly as part of Priority 4. Do not propagate the regex approach.

**Current gaps identified:** Carry (11 days), Rotation (7 days) — data is useful, implementation is not.

## Remaining Tasks (Priority Order)

### Priority 4: Neo4j → Postgres Relationship Sync (EXPANDED SCOPE)
**Status:** Data exists in Neo4j, not accessible for Postgres analytics

**This is now TWO syncs in ONE architecture:**

| Neo4j Relationship | Postgres Cache Table | Analytics Use Case |
|--------------------|---------------------|--------------------|
| `Exercise -[:TARGETS]-> Muscle` | `exercise_muscle_map` | Sets per muscle per week |
| `Exercise -[:TRAINS_PATTERN]-> MovementPattern` | `exercise_pattern_map` | Days since pattern, balance ratios |

**Why combined:** Same sync mechanism, same cache strategy, same freshness concerns. Don't build two separate solutions.

---

**Step 1: Drop the regex hack**
```sql
DROP VIEW IF EXISTS pattern_last_trained;
```
This view used regex on exercise names. It works but violates the principle that Neo4j owns relationship semantics.

---

**Step 2: Create cache tables**
```sql
-- Muscle targeting (for volume analytics)
CREATE TABLE exercise_muscle_map (
    exercise_id TEXT NOT NULL,
    muscle_name TEXT NOT NULL,
    role TEXT DEFAULT 'primary',  -- primary, secondary, stabilizer
    weight NUMERIC DEFAULT 1.0,   -- for volume attribution
    synced_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (exercise_id, muscle_name)
);

-- Movement patterns (for balance analytics)  
CREATE TABLE exercise_pattern_map (
    exercise_id TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    synced_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (exercise_id, pattern_name)
);
```

---

**Step 3: Sync from Neo4j**

Query Neo4j for relationships:
```cypher
// Muscle targets
MATCH (e:Exercise)-[r:TARGETS]->(m:Muscle)
RETURN e.id AS exercise_id, m.name AS muscle_name, 
       coalesce(r.role, 'primary') AS role,
       coalesce(r.weight, 1.0) AS weight

// Movement patterns  
MATCH (e:Exercise)-[:TRAINS_PATTERN]->(p:MovementPattern)
RETURN e.id AS exercise_id, p.name AS pattern_name
```

Upsert into Postgres cache tables. Can be:
- Python script in `/scripts/sync/`
- Part of the nightly data pipeline
- Triggered when exercises are created/modified

---

**Step 4: Rebuild analytics views**

```sql
-- Pattern frequency (replaces regex version)
CREATE VIEW pattern_last_trained AS
WITH exercise_patterns AS (
    SELECT ss.workout_id, ss.exercise_id, epm.pattern_name
    FROM strength_sets ss
    JOIN exercise_pattern_map epm ON ss.exercise_id = epm.exercise_id
),
-- ... rest of aggregation logic

-- Muscle volume per week
CREATE VIEW muscle_volume_weekly AS
WITH exercise_muscles AS (
    SELECT ss.*, emm.muscle_name, emm.role, emm.weight
    FROM strength_sets ss
    JOIN exercise_muscle_map emm ON ss.exercise_id = emm.exercise_id
),
-- ... aggregate sets × weight for volume attribution
```

---

**⚠️ ADR-001 Compliance:**
- Neo4j remains **source of truth** for relationships
- Postgres tables are **caches** for analytics joins
- Do NOT add/modify relationships in Postgres — sync is one-way
- Include `synced_at` timestamp for cache freshness tracking

**Primary vs secondary consideration:**
Neo4j TARGETS relationships may have `role` property (primary/secondary/stabilizer) and `weight` for volume attribution. Preserve these in the cache. A secondary muscle shouldn't count as a full set.

**Use cases unlocked:**
- "How many sets did I do for lats this week?" (10-20 sets/muscle/week literature)
- "Days since last Hip Hinge" (without regex guessing)
- Push:Pull ratio (from pattern counts)

### Priority 5: Balance Ratios View
**Status:** Documented in TRAINING_METRICS.md, not implemented

**Metrics needed:**
- Push:Pull ratio (target ~1:1)
- Upper:Lower ratio
- Quad:Ham ratio (anterior/posterior)

**Depends on:** Pattern frequency view (done) or muscle volume view

### Priority 6: Update Coach Briefing Tools
**Status:** `get_readiness_snapshot` and `get_coach_briefing` don't pull from new views yet

**New views to integrate:**
- `srpe_monotony_strain` (sRPE-based strain, created in 011 migration)
- `daily_activity_context` (steps as NEAT context)
- `pattern_last_trained` (just created)

**Location:** 
- `arnold-analytics-mcp` for readiness
- `arnold-training-mcp` for coach briefing

## Architecture Context

### Hybrid Database Model (ADR-001, ADR-002)
- **Postgres (left brain):** Facts, measurements, time-series, analytics views
- **Neo4j (right brain):** Relationships, knowledge graph, exercise taxonomy, plans

### Key Views in Postgres
```
srpe_training_load          -- RPE × Duration with data cascade
srpe_monotony_strain        -- Foster's original formula
daily_activity_context      -- Steps as NEAT/lifestyle context
pattern_last_trained        -- Days since each movement pattern
readiness_composite         -- Multi-signal readiness score
```

### MCP Servers
- `arnold-training-mcp` — Planning, logging, exercise search
- `arnold-analytics-mcp` — Readiness, training load, red flags
- `arnold-profile-mcp` — Person, equipment, activities
- `arnold-memory-mcp` — Coaching context, observations
- `arnold-journal-mcp` — Subjective data capture

## Files to Reference

- `/docs/TRAINING_METRICS.md` — Comprehensive metrics documentation
- `/docs/METRICS.md` — Implementation status tracker
- `/scripts/migrations/011_derived_metrics.sql` — Tier 1 analytics views
- `/src/arnold-training-mcp/arnold_training_mcp/server.py` — Just modified

## Testing Notes

Server was restarted after changes. Next workout completion will test the new flow.

Pattern frequency view verified working:
```
Carry: 11 days since
Rotation: 7 days since  
Hip Hinge: 3 days since
Vertical Pull: 0 days since (today)
```

## Questions for This Thread

If the new thread needs clarification on:
- sRPE science/thresholds
- Database schema details
- Existing view definitions
- Migration history

Ask here — context is preserved.
