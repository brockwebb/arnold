# arnold-analytics-mcp

> **Purpose:** Training metrics, readiness assessment, and computed coaching insights
> **Database:** Postgres (`arnold_analytics`)
> **Codename:** T-1000

## Core Principle: Compute, Don't Interpret

This MCP is Arnold's "left brain" — it crunches numbers, detects patterns, and surfaces computed insights. But it does NOT interpret what matters or suppress information.

```
┌─────────────────────────────────────────────────────────────┐
│  Arnold (Intelligence Layer)                                 │
│  - Sees observations + annotations                          │
│  - Decides what to tell user                                │
│  - "HRV is down but that's expected after your big workout" │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│  arnold-analytics-mcp (This MCP)                            │
│  - Computes insights from raw data                          │
│  - Returns coaching_notes + annotations                     │
│  - Does NOT suppress or filter                              │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│  Postgres (arnold_analytics)                                │
│  - biometric_readings, strength_sessions, data_annotations  │
└─────────────────────────────────────────────────────────────┘
```

## What This MCP DOES (Computed Insights)

| Type | Example | Why It's OK |
|------|---------|-------------|
| Threshold checks | "Sleep under 6hr threshold" | Pre-computed math, saves LLM work |
| Trend detection | "HRV declining over 3 days" | Statistical computation |
| Comparisons | "15% below 7-day avg" | Arithmetic the LLM doesn't need to do |
| Zone classification | "ACWR in high_risk zone" | Lookup against known thresholds |
| Gap detection | "No Hip Hinge work in 10 days" | Set comparison |
| Aggregations | "Sleep averaging 6.2hrs over 7 nights" | SQL aggregation |

## What This MCP Does NOT (Interpretation)

| Type | Example | Why It's Wrong |
|------|---------|----------------|
| Suppression | "Don't show ACWR warning because annotation exists" | Hides information from Arnold |
| Recommendations | "Consider taking a rest day" | That's coaching, not computing |
| Filtering | "Only show warnings without annotations" | Arnold needs full picture |
| Priority decisions | "This is more important than that" | Context-dependent judgment |

## Tools

| Tool | Purpose | Returns |
|------|---------|---------|
| `get_readiness_snapshot` | HRV, sleep, recovery for a date | Data + `coaching_notes` |
| `get_training_load` | Volume trends, ACWR, pattern distribution | Data + `coaching_notes` |
| `get_exercise_history` | PR, working weights, 1RM estimates | Progression data |
| `check_red_flags` | Observations + annotations | `observations[]` + `annotations[]` |
| `get_sleep_analysis` | Sleep patterns and trends | Sleep data + insights |
| `run_sync` | Trigger data sync pipeline | Sync status |
| `get_sync_history` | Recent sync runs | Sync log |

### Tool Response Pattern

All tools follow this pattern — data + computed insights + annotations (no suppression):

```json
{
  "hrv": {"value": 42, "avg_7d": 49, "trend": "declining"},
  "sleep": {"hours": 5.8, "quality_pct": 72},
  "acwr": {"trimp_based": 1.52, "zone": "high_risk"},
  "coaching_notes": [
    "HRV 42 is 15% below 7-day avg",
    "Sleep 5.8hrs - under 6hr recovery threshold",
    "ACWR 1.52 - elevated injury risk zone"
  ]
}
```

For `check_red_flags`, annotations are included alongside observations:

```json
{
  "observations": [
    {"type": "hrv_trend", "observation": "HRV declining: -12% vs prior days", ...},
    {"type": "data_gap", "metric": "sleep", "observation": "No sleep data for 3 days", ...}
  ],
  "annotations": [
    {"date": "2026-01-03", "reason": "expected", 
     "explanation": "Birthday workout - HRV dip expected"}
  ],
  "observation_count": 2
}
```

## Boundaries

| This MCP Does | This MCP Does NOT |
|---------------|-------------------|
| Calculate training metrics | Write workout data |
| Assess readiness | Create plans |
| Compute pattern gaps | Make coaching decisions |
| Analyze sleep patterns | Suppress based on annotations |
| Track exercise progression | Recommend actions |
| Return annotations as context | Filter or hide information |

## Key Decisions

### Postgres for Analytics (ADR-001)

**Context:** Neo4j excels at relationships but time-series aggregations are better in SQL.

**Decision:** Postgres is source of truth for measurements. Neo4j holds relationships only.

**Tables:**
- `biometric_readings` — HRV, RHR, sleep, temp
- `strength_sessions` / `strength_sets` — Executed workouts (ADR-002)
- `endurance_sessions` / `endurance_laps` — FIT imports
- `data_annotations` — Context for data gaps/anomalies
- `log_entries` — Journal entries

### Coaching Notes (Pre-computed Insights)

**Context:** Raw data requires Claude to do math every time, wasting context window.

**Decision:** Tools return `coaching_notes` array with pre-computed threshold checks and comparisons.

**Examples:**
- "HRV 42 is 15% below 7-day avg"
- "Sleep 5.8hrs - under 6hr recovery threshold"  
- "ACWR 1.52 - elevated injury risk zone"
- "Pattern gaps (no work in 10d): Hip Hinge, Squat"

**Consequence:** Smaller context usage. Faster coaching. Analytics logic lives in MCP, not prompts.

### No Suppression (Annotations as Context)

**Context:** Previous implementation suppressed warnings when annotations existed. This hid information from Arnold.

**Decision:** Analytics tools return ALL observations + ALL relevant annotations. Arnold sees both and synthesizes.

**Wrong (removed):**
```python
if check_before_warning(cur, 'acwr', ...):
    # Don't add to flags - SUPPRESSION
    pass
```

**Right (current):**
```python
observations.append({"type": "acwr", "observation": "ACWR 1.52 - high risk"})
# ... later ...
annotations = get_annotations_for_period(cur, start, end)
return {"observations": observations, "annotations": annotations}
```

### Data Completeness Indicator

**Context:** Partial data leads to unreliable metrics. Claude needs to know confidence level.

**Decision:** `get_readiness_snapshot` returns a completeness score (0-4) indicating available data sources.

**Consequence:** Claude can caveat recommendations based on data quality.

## Metrics Calculated

| Metric | Formula | Use |
|--------|---------|-----|
| **ACWR** | Acute (7d) / Chronic (28d) TRIMP | Injury risk assessment |
| **HRV Trend** | Compare recent 3d avg to prior days | Recovery tracking |
| **Sleep Threshold** | Compare to 6hr/7hr benchmarks | Recovery quality |
| **Pattern Gaps** | Core patterns not trained in 10 days | Balance assessment |
| **Estimated 1RM** | Brzycki formula from working sets | Progression tracking |

## Data Sources

| Source | Data | Refresh |
|--------|------|---------|
| Ultrahuman API | HRV, sleep, recovery | Automated daily |
| Polar Export | HR sessions, TRIMP | Manual weekly |
| Apple Health | Labs, BP, meds | Manual monthly |
| FIT files | Endurance sessions | On import |
| Neo4j sync | Strength sessions | Pipeline |

## Dependencies

- **Postgres** (`arnold_analytics`) — Source of truth for measurements
- **Neo4j** (indirect) — Workout refs synced to Postgres
- **Sync pipeline** — `scripts/sync_pipeline.py`

## Known Issues / Tech Debt

1. **Annotation creation** — Currently manual SQL. Need MCP tool to create annotations from natural language.

2. **Neo4j annotation refs** — Postgres owns annotation content, but Neo4j refs with EXPLAINS relationships not yet implemented. Annotations are Postgres-only currently.

3. **ACWR baseline** — Post-surgery baseline is elevated. Annotation exists but interpretation is Arnold's job.
