# ADR-004: Decision Trace System

**Date:** January 8, 2026  
**Status:** Proposed  
**Deciders:** Brock Webb, Claude (Arnold development)  
**Related:** ADR-001 (Data Layer Separation), Coach Brief Architecture

## Context

Arnold makes coaching decisions — workout plans, intensity adjustments, exercise substitutions, rest recommendations. Currently, the reasoning behind these decisions exists only in the conversation where they occurred. Once the context window closes, the "why" is lost.

This creates several problems:

1. **No auditability**: "Why did Coach recommend light technique work instead of heavy deadlifts on Jan 3?" — we can't answer this without re-deriving from raw data
2. **No precedent**: Similar situations recur, but we can't reference how we handled them before
3. **No learning**: We can't analyze which decision patterns led to good vs bad outcomes
4. **Trust gap**: The athlete has to trust Coach's recommendations without seeing the reasoning

### The Missing Component

The current architecture has:
- **Facts** (Postgres): What happened — workouts, biometrics, sets, reps
- **Relationships** (Neo4j): How things connect — goals, modalities, injuries, constraints
- **Memory** (Observations): Coaching insights persisted across conversations

What's missing is the **decision context graph** — the record of WHY Coach made specific recommendations given the state at decision time.

## Decision

Implement a Decision Trace system that captures coaching decisions with full context, following the ADR-001 dual-storage pattern.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   POSTGRES (Trace Facts)                         │
│                                                                  │
│  decision_traces                                                 │
│  ├── id SERIAL PRIMARY KEY                                      │
│  ├── trace_id VARCHAR(50) UNIQUE  -- "dt_20260108_001"          │
│  ├── decision_type VARCHAR(50)     -- plan_generated, deviation, etc │
│  ├── decision_date DATE                                         │
│  ├── created_at TIMESTAMP                                       │
│  │                                                               │
│  ├── inputs_snapshot JSONB         -- state at decision time    │
│  ├── policies_applied JSONB        -- which rules triggered     │
│  ├── conflicts_resolved JSONB      -- competing signals         │
│  ├── output_summary TEXT           -- what was decided          │
│  │                                                               │
│  ├── outcome_type VARCHAR(50)      -- plan, workout, adjustment │
│  ├── outcome_id VARCHAR(100)       -- FK to plan/workout/etc    │
│  │                                                               │
│  ├── approval_status VARCHAR(20)   -- pending, approved, rejected │
│  ├── approved_by VARCHAR(50)       -- user, auto                │
│  ├── approved_at TIMESTAMP                                      │
│  │                                                               │
│  └── tags TEXT[]                   -- for retrieval             │
│                                                                  │
│  Enables: "Show me all decisions where ACWR > 1.3"              │
│  Enables: "Trace history for plan_20260108"                     │
│  Enables: "Decisions that led to skipped workouts"              │
└─────────────────────────────────────────────────────────────────┘
                              │
                         FK reference
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  NEO4J (Trace Relationships)                     │
│                                                                  │
│  (:DecisionTrace {                                               │
│      trace_id: STRING,           // matches Postgres             │
│      postgres_id: INT,           // FK to decision_traces        │
│      decision_type: STRING,                                      │
│      decision_date: DATE                                         │
│  })                                                              │
│                                                                  │
│  Relationships:                                                  │
│  (Person)-[:HAD_DECISION]->(DecisionTrace)                      │
│  (DecisionTrace)-[:PRODUCED]->(PlannedWorkout|StrengthWorkout)  │
│  (DecisionTrace)-[:CONSIDERED]->(Injury|Goal|Constraint)        │
│  (DecisionTrace)-[:INFORMED_BY]->(Annotation|LogEntry)          │
│  (DecisionTrace)-[:REFERENCED_PRECEDENT]->(DecisionTrace)       │
│  (DecisionTrace)-[:SUPERSEDED_BY]->(DecisionTrace)              │
│                                                                  │
│  Enables: "Show me all decisions affected by knee injury"       │
│  Enables: "What decisions referenced this precedent?"           │
│  Enables: "Decision chain for this workout"                     │
└─────────────────────────────────────────────────────────────────┘
```

### Schema Detail: inputs_snapshot

Captures the complete state Coach saw when making the decision:

```json
{
  "readiness": {
    "status": "caution",
    "hrv_value": 28,
    "hrv_vs_baseline_pct": -12,
    "sleep_hours": 5.2,
    "sleep_quality": "poor",
    "rhr_value": 58,
    "recovery_score": 62
  },
  "training_load": {
    "acwr": 1.15,
    "acwr_zone": "optimal",
    "weekly_volume": 47,
    "monotony": 1.8,
    "strain": 84
  },
  "pattern_gaps": {
    "hip_hinge_days": 5,
    "squat_days": 3,
    "horizontal_pull_days": 10
  },
  "active_constraints": [
    {
      "type": "injury",
      "id": "inj_knee_surgery_nov_2025",
      "name": "Right knee meniscus surgery",
      "constraints": ["no deep squats", "no jumping", "limit knee flexion > 90°"]
    }
  ],
  "block_context": {
    "name": "Winter Base Building",
    "type": "accumulation",
    "week": 2,
    "of_weeks": 4,
    "intent": "Build work capacity, establish movement patterns"
  },
  "goals_served": ["deadlift_405x5", "hellgate_100k"]
}
```

### Schema Detail: policies_applied

Documents which coaching rules/heuristics influenced the decision:

```json
[
  {
    "policy": "acwr_load_management",
    "triggered": true,
    "condition": "ACWR 1.15 in optimal zone (0.8-1.3)",
    "action": "No volume adjustment required",
    "citation": "Gabbett 2016, Murray 2017"
  },
  {
    "policy": "hrv_readiness_gate",
    "triggered": true,
    "condition": "HRV 12% below baseline",
    "action": "Cap intensity at RPE 7, prefer technique work",
    "citation": "Plews 2013"
  },
  {
    "policy": "pattern_frequency",
    "triggered": true,
    "condition": "Hip hinge gap > 4 days",
    "action": "Prioritize hip hinge movement",
    "citation": "Schoenfeld 2016 (frequency recommendations)"
  },
  {
    "policy": "injury_constraint_filter",
    "triggered": true,
    "condition": "Active knee surgery constraint",
    "action": "Excluded: deep squats, jumping, high-impact",
    "source": "Injury protocol"
  }
]
```

### Schema Detail: conflicts_resolved

Documents when policies or signals conflicted and how Coach resolved them:

```json
[
  {
    "conflict": "HRV says recover vs pattern gap says train hip hinge",
    "signals": {
      "recover": {"source": "hrv_readiness_gate", "strength": "moderate"},
      "train": {"source": "pattern_frequency", "strength": "moderate"}
    },
    "resolution": "Reduced intensity hip hinge (RPE 6 cap), not skipped",
    "rationale": "Pattern maintenance with recovery accommodation"
  },
  {
    "conflict": "Block intent (volume) vs readiness (fatigue)",
    "signals": {
      "volume": {"source": "block_context", "strength": "moderate"},
      "reduce": {"source": "sleep_debt", "strength": "strong"}
    },
    "resolution": "Reduced volume by 20%, maintained movement selection",
    "rationale": "Sleep debt is transient; maintain pattern exposure"
  }
]
```

### Decision Types

| Type | Trigger | What It Captures |
|------|---------|------------------|
| `plan_generated` | `create_workout_plan` | Full planning decision for a session |
| `plan_adjusted` | User requests modification | Changes to existing plan |
| `deviation_recorded` | `complete_with_deviations` | Why actual differed from plan |
| `workout_skipped` | `skip_workout` | Reason for skip, rescheduling decision |
| `intensity_override` | Manual RPE/load change | Coach-initiated adjustment |
| `constraint_applied` | New injury/limitation | How constraint affected planning |
| `goal_impact` | Goal progress update | How progress informed next steps |

### Capture Points (MCP Integration)

Tools that emit decision traces:

| MCP | Tool | Trace Type |
|-----|------|------------|
| arnold-training | `create_workout_plan` | `plan_generated` |
| arnold-training | `complete_with_deviations` | `deviation_recorded` |
| arnold-training | `skip_workout` | `workout_skipped` |
| arnold-journal | `log_entry` (severity: concerning+) | `constraint_applied` |
| arnold-profile | Injury/constraint creation | `constraint_applied` |

### Precedent Search

Enable finding similar past decisions:

```sql
-- Find decisions with similar readiness state
SELECT trace_id, decision_date, output_summary
FROM decision_traces
WHERE (inputs_snapshot->'readiness'->>'status') = 'caution'
  AND (inputs_snapshot->'training_load'->>'acwr')::float BETWEEN 1.0 AND 1.3
ORDER BY decision_date DESC
LIMIT 5;
```

```cypher
// Find decisions that considered the same injury
MATCH (dt:DecisionTrace)-[:CONSIDERED]->(i:Injury {id: $injury_id})
RETURN dt.trace_id, dt.decision_date, dt.decision_type
ORDER BY dt.decision_date DESC
```

### Usage in Coach Brief

The coach brief can now include decision context:

```
📋 RECENT DECISIONS

Jan 8: Plan generated for Thu strength session
  • HRV down 12% → capped intensity at RPE 7
  • Pattern gap (hip hinge 5d) → prioritized deadlift variation
  • Knee constraint → excluded deep squats
  → Trap bar deadlift technique day, moderate volume

Jan 6: Workout completed with deviations
  • Planned: 315x5x4, Actual: 315x5x3 + 295x5x1
  • Reason: fatigue (set 4 form breakdown)
  • Similar to Dec 20 decision (same pattern)
```

### MCP Tools (arnold-training or new arnold-trace)

```python
# Creation
create_decision_trace(
    decision_type: str,
    inputs_snapshot: dict,
    policies_applied: list,
    conflicts_resolved: list,
    output_summary: str,
    outcome_type: str,
    outcome_id: str
) -> trace_id

# Retrieval
get_decision_trace(trace_id: str) -> DecisionTrace
get_decisions_for_outcome(outcome_id: str) -> list[DecisionTrace]
get_recent_decisions(days: int = 7) -> list[DecisionTrace]

# Search
search_decisions(
    decision_type: str = None,
    readiness_status: str = None,
    acwr_range: tuple = None,
    involved_injury: str = None,
    date_range: tuple = None
) -> list[DecisionTrace]

# Precedent
find_similar_decisions(
    current_state: dict,
    limit: int = 5
) -> list[DecisionTrace]

# Linking
link_decision_to_entity(trace_id: str, entity_type: str, entity_id: str, relationship: str)
```

## Consequences

### Positive

1. **Auditability**: Every recommendation traceable to specific inputs and policies
2. **Precedent**: "Last time HRV was down and ACWR was 1.2, we did X" becomes queryable
3. **Learning**: Analyze decision→outcome pairs to improve coaching logic
4. **Trust**: "Here's exactly why I recommended this" on demand
5. **Debugging**: When coaching seems off, trace back to see what happened
6. **Continuity**: New conversation threads can see decision history

### Negative

1. **Storage growth**: Each decision creates records in both databases
2. **Capture overhead**: MCP tools need to emit traces (added complexity)
3. **Schema maintenance**: inputs_snapshot structure may evolve
4. **Query complexity**: Precedent search requires thoughtful indexing

### Mitigation

- **Storage**: Implement retention policy (e.g., full detail 90 days, summaries thereafter)
- **Overhead**: Start with plan generation only, expand capture points incrementally
- **Schema**: Use JSONB for flexibility; version the snapshot schema
- **Queries**: Create materialized views for common precedent patterns

## Implementation Plan

### Phase 1: Schema and Basic Capture

1. Create `decision_traces` table in Postgres
2. Create `DecisionTrace` node type in Neo4j
3. Implement `create_decision_trace` in arnold-training
4. Wire into `create_workout_plan` — emit trace on every plan

### Phase 2: Relationship Linking

1. Implement Neo4j relationship creation (CONSIDERED, PRODUCED, etc.)
2. Add `link_decision_to_entity` tool
3. Update planning workflow to create links automatically

### Phase 3: Retrieval and Search

1. Implement retrieval tools
2. Add precedent search (SQL + Cypher)
3. Create indexes for common query patterns

### Phase 4: Coach Brief Integration

1. Add "Recent Decisions" section to coach brief
2. Enable "Why this recommendation?" queries
3. Surface precedent references in planning explanations

## Open Questions

1. **Retention**: How long to keep full decision traces? (Proposal: 1 year full, summaries forever)

2. **Granularity**: Trace every set prescription, or just session-level? (Proposal: Session-level initially)

3. **Auto-approval**: Should well-understood decisions auto-approve? (Proposal: Yes, with audit trail)

4. **Embedding**: Should we embed decision contexts for semantic precedent search? (Proposal: Phase 2, after basic search proves useful)

## References

- ADR-001: Data Layer Separation (dual-storage pattern)
- TRAINING_METRICS.md: Evidence-based policies with citations
- Coach Brief Architecture discussion (Jan 8, 2026)
- Memory Architecture: Observations system as prior art
