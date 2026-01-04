# arnold-analytics-mcp

> **Purpose:** Training metrics, readiness assessment, and coaching insights

## What This MCP Owns

- **Readiness data** (HRV, sleep, recovery scores)
- **Training load calculations** (ACWR, monotony, strain)
- **Exercise progression history**
- **Red flag detection** (overtraining, data gaps, recovery issues)
- **Sleep analysis**

## Boundaries

| This MCP Does | This MCP Does NOT |
|---------------|-------------------|
| Calculate training metrics | Write workout data |
| Assess readiness | Create plans |
| Detect red flags | Make coaching decisions (Claude does) |
| Analyze sleep patterns | Record observations |
| Track exercise progression | Manage profile |

## Tools

| Tool | Purpose |
|------|---------|
| `get_readiness_snapshot` | HRV, sleep, recovery for a date |
| `get_training_load` | Volume trends, ACWR, pattern distribution |
| `get_exercise_history` | PR, working weights, 1RM estimates |
| `check_red_flags` | Proactive concern detection |
| `get_sleep_analysis` | Sleep patterns and trends |

## Key Decisions

### DuckDB for Analytics

**Context:** Neo4j excels at relationships but complex time-series aggregations (rolling averages, ACWR) are verbose in Cypher.

**Decision:** Use DuckDB with Parquet files as the analytics query layer. Neo4j remains source of truth; Parquet files are derived/refreshed.

**Consequence:** Fast analytical queries. Slight data lag possible if Parquet not refreshed. Two query engines to understand.

### Coaching-Ready Tool Responses

**Context:** Raw data requires Claude to do math and interpretation every time.

**Decision:** Tools return pre-computed insights, not raw numbers. Example: `get_readiness_snapshot` returns coaching notes like "HRV trending down 15% over 7 days" rather than just the numbers.

**Consequence:** Smaller context window usage. Faster coaching responses. Analytics logic lives in MCP, not prompt.

### Data Completeness Indicator

**Context:** Partial data leads to unreliable metrics. Claude needs to know confidence level.

**Decision:** `get_readiness_snapshot` returns a completeness score (0-4) indicating how many data sources are available.

**Consequence:** Claude can caveat recommendations based on data quality.

### Red Flags as Proactive Check

**Context:** Issues like declining HRV or pattern gaps shouldn't wait for user to ask.

**Decision:** `check_red_flags` designed to be called at conversation start, surfaces concerns proactively.

**Consequence:** Arnold can say "Before we plan today's workout, I noticed your HRV has been declining..." without being asked.

## Metrics Calculated

| Metric | Formula | Use |
|--------|---------|-----|
| **ACWR** | Acute (7d) / Chronic (28d) load | Injury risk assessment |
| **Training Monotony** | Mean / StdDev of weekly load | Variation assessment |
| **Training Strain** | Load × Monotony | Total stress indicator |
| **Estimated 1RM** | Epley formula from working sets | Progression tracking |

## Data Sources

| Source | Data | Refresh |
|--------|------|---------|
| Neo4j | Workouts, sets, exercises | Real-time |
| Apple Health | HRV, sleep, resting HR | Import script |
| Ultrahuman | Recovery scores, sleep stages | API sync |
| Parquet | Pre-aggregated metrics | On-demand |

## Data Model

Analytics reads from the core graph:

```
(Person)-[:PERFORMED]->(Workout)-[:HAS_BLOCK]->(WorkoutBlock)-[:CONTAINS]->(Set)
(Set)-[:OF_EXERCISE]->(Exercise)-[:INVOLVES]->(MovementPattern)
```

And from observation data:

```
(Person)-[:HAS_OBSERVATION]->(Observation)-[:HAS_CONCEPT]->(ObservationConcept)
```

## Dependencies

- **Neo4j** — Source of truth for workouts
- **DuckDB** — Analytics query engine
- **Parquet files** — Pre-aggregated data
- **profile.json** — Person ID resolution

## Known Issues / Tech Debt

1. **Parquet refresh** — Currently manual. Should be triggered on workout log or scheduled.

2. **Apple Health sync** — One-time import exists, but no ongoing sync. HRV data may be stale.
