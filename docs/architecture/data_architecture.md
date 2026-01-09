# Data Architecture

> **Last Updated**: January 8, 2026
> **Related ADRs**: [ADR-001](../adr/001-data-layer-separation.md), [ADR-002](../adr/002-strength-workout-migration.md)

---

## The Right Brain / Left Brain Model

> **Key Insight (ADR-001):** Neo4j stores *relationships and meaning*. Postgres stores *measurements and facts*.

Arnold uses a hybrid database architecture where each system handles what it does best:

```
┌─────────────────────────────────────────────────────────────┐
│                    POSTGRES (Left Brain)                     │
│              Measurements, Facts, Time-Series                │
│                                                              │
│  strength_sessions     - Executed strength workouts (165)   │
│  strength_sets         - Individual sets (2,482)            │
│  endurance_sessions    - FIT imports (runs, rides)          │
│  endurance_laps        - Per-lap splits                     │
│  biometric_readings    - HRV, RHR, sleep, temp              │
│  hr_samples            - Beat-by-beat (optional)            │
│  log_entries           - Journal/subjective data            │
│  race_history          - Competition results                │
│  data_annotations      - Time-series context                │
│                                                              │
│  SQL, aggregations, materialized views, analytics           │
└─────────────────────────────────┬───────────────────────────┘
                              │
                         FK references
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     NEO4J (Right Brain)                      │
│              Relationships, Semantics, Knowledge             │
│                                                              │
│  Person, Goal, Modality, Block    - Training structure      │
│  Exercise, MovementPattern, Muscle - Knowledge base         │
│  Injury, Constraint, Protocol      - Medical context        │
│  Annotation (relationships)        - Explanatory links      │
│  StrengthWorkout, EnduranceWorkout - FK refs to Postgres    │
│  PlannedWorkout, PlannedBlock      - Intentions (pre-exec)  │
│                                                              │
│  Graph traversals, pattern matching, "why" queries          │
└─────────────────────────────────────────────────────────────┘
```

---

## Query Pattern Examples

| Question | Database | Why |
|----------|----------|-----|
| "Average HRV last 30 days?" | Postgres | Time-series aggregation |
| "What modalities does this goal require?" | Neo4j | Relationship traversal |
| "All workouts affected by knee injury?" | Neo4j → Postgres | Graph query, then fetch details |
| "TSS trend by week?" | Postgres | Analytical rollup |
| "Why did my performance drop Jan 3?" | Neo4j | Annotation → Workout explanation |

---

## The Bridge Pattern (ADR-002)

When data needs to exist in both systems, Postgres holds the detail and Neo4j holds a lightweight reference:

```
Postgres                              Neo4j
┌──────────────────────┐            ┌──────────────────────┐
│ strength_sessions    │            │ (:StrengthWorkout)   │
│ id: 165              │◄──── FK ───►│ postgres_id: 165     │
│ date, name, volume   │            │ date (for queries)   │
│ total_sets, reps     │            │ [:PERFORMED]->Person │
│ + strength_sets (det)│            │ [:EXECUTED_FROM]->Plan│
└──────────────────────┘            └──────────────────────┘

┌──────────────────────┐            ┌──────────────────────┐
│ endurance_sessions   │            │ (:EnduranceWorkout)  │
│ id: 12345            │◄──── FK ───►│ postgres_id: 12345   │
│ date, distance, tss  │            │ date (for queries)   │
│ duration, hr, pace   │            │ [:PERFORMED]->Person │
│ ALL the detail       │            │ [:EXPLAINS]<-Annot   │
└──────────────────────┘            └──────────────────────┘
```

**Execution Flow (ADR-002):**
```
PlannedWorkout (Neo4j)  ───complete_as_written───►  strength_sessions (Postgres)
       │                                                     │
       │                                                     │
       └─────────────[:EXECUTED_FROM]───────────── StrengthWorkout ref
```

---

## Relationship Caching (ADR-001 Addendum)

Neo4j relationships are cached in Postgres to enable efficient analytics JOINs:

```
Neo4j (source of truth)              Postgres (analytics cache)
┌──────────────────────┐            ┌────────────────────────────────┐
│ (Exercise)-[:INVOLVES]│            │ neo4j_cache_exercise_patterns  │
│ ->(MovementPattern)  │───sync────►│ exercise_id, pattern_name      │
│                      │            │ synced_at                      │
├──────────────────────┤            ├────────────────────────────────┤
│ (Exercise)-[:TARGETS]│            │ neo4j_cache_exercise_muscles   │
│ ->(Muscle)           │───sync────►│ exercise_id, muscle_name, role │
│                      │            │ synced_at                      │
└──────────────────────┘            └────────────────────────────────┘
```

**Sync characteristics:**
- One-way: Neo4j → Postgres only (Neo4j is source of truth)
- Full refresh: TRUNCATE + reload (not incremental)
- Triggered by: `sync_pipeline.py --step relationships`
- Script: `scripts/sync_exercise_relationships.py`

**Why cache relationships?**
- Analytics queries need JOINs: "sets per muscle per week"
- Cross-database JOINs are expensive/impossible
- Cache enables SQL views without runtime graph queries

**Views built on cache:**

| View | Purpose |
|------|--------|
| `pattern_last_trained` | Days since each movement pattern |
| `muscle_volume_weekly` | Sets/reps/volume per muscle per week |

**Current stats (Jan 2026):**
- Pattern cache: 4,952 rows (4,136 exercises × 30 patterns)
- Muscle cache: 13,430 rows (4,240 exercises × 45 muscles)
- Workout coverage: 100% pattern, 97% muscle

---

## Data Annotation System

Data gaps and anomalies need context. The annotation system provides explanations that:
1. **Provide context** — "Why does the data look like this?"
2. **Preserve institutional knowledge** — Explanations persist across conversations
3. **Enable graph relationships** — Link explanations to workouts, injuries, plans

**Architecture (ADR-001 Compliant):**

```
┌─────────────────────────────────────────────────────────────┐
│                    POSTGRES (Source of Truth)                │
│                        Facts & Content                       │
│                                                              │
│  data_annotations                                            │
│  ├── id, annotation_date, date_range_end                    │
│  ├── target_type, target_metric, reason_code                │
│  ├── explanation (the actual content)                       │
│  ├── tags[], is_active                                      │
│  └── created_at, updated_at                                 │
│                                                              │
│  Helper functions:                                           │
│  ├── annotations_for_date(date) - time-range queries        │
│  └── active_data_issues - current gaps/anomalies            │
└─────────────────────────────────────────────────────────────┘
                              │
                         FK reference
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     NEO4J (Relationships)                    │
│                   Lightweight Refs + Links                   │
│                                                              │
│  (:Annotation {                                              │
│      id: STRING,              // matches Postgres id         │
│      postgres_id: INT,        // FK to data_annotations      │
│      annotation_date: DATE,   // for graph queries           │
│      reason_code: STRING      // for graph queries           │
│  })                                                          │
│                                                              │
│  Relationships:                                              │
│  (Person)-[:HAS_ANNOTATION]->(Annotation)                   │
│  (Annotation)-[:EXPLAINS]->(StrengthWorkout|EnduranceWorkout)│
│  (Annotation)-[:EXPLAINS]->(Injury)                         │
│  (Annotation)-[:AFFECTS]->(PlannedWorkout)                  │
└─────────────────────────────────────────────────────────────┘
```

**Reason Codes:**
- `device_issue` — Sensor malfunction, app not syncing
- `surgery` — Medical procedure, post-op recovery  
- `injury` — Active injury affecting training
- `expected` — Normal variation (e.g., HRV drop after hard workout)
- `data_quality` — Known data issue, source confusion
- `travel`, `illness`, `deload`, `life` — Other common reasons

---

## Analytics Layer: Compute vs Interpret

The analytics MCP tools are Arnold's "left brain" — they crunch numbers, detect patterns, and surface computed insights. But they do NOT interpret what matters or suppress information.

**The Three-Layer Model:**

```
┌─────────────────────────────────────────────────────────────┐
│                  INTELLIGENCE LAYER (Arnold/Claude)          │
│                                                              │
│  Synthesizes data + annotations + context                   │
│  Decides what to tell the user                              │
│  "HRV is down 15%, but the annotation says this was         │
│   expected after your birthday workout. No concern."        │
└─────────────────────────────────────────────────────────────┘
                              ▲
                    observations + annotations
                              │
┌─────────────────────────────────────────────────────────────┐
│                    ANALYTICS LAYER (MCP Tools)               │
│                                                              │
│  Computes insights from raw data:                           │
│  • "HRV 42 is 15% below 7-day avg"                          │
│  • "Sleep 5.8hrs - under 6hr threshold"                     │
│  • "ACWR 1.52 - elevated injury risk zone"                  │
│  • "Pattern gaps: Hip Hinge, Squat (no work in 10d)"        │
│                                                              │
│  Returns alongside active annotations — does NOT filter     │
└─────────────────────────────────────────────────────────────┘
                              ▲
                         raw metrics
                              │
┌─────────────────────────────────────────────────────────────┐
│                      DATA LAYER (Postgres)                   │
│                                                              │
│  biometric_readings, strength_sessions, data_annotations    │
└─────────────────────────────────────────────────────────────┘
```

**What Analytics Tools SHOULD Do (Computed Insights):**

| Type | Example | Why It's OK |
|------|---------|-------------|
| Threshold checks | "Sleep under 6hr threshold" | Pre-computed math |
| Trend detection | "HRV declining over 3 days" | Statistical computation |
| Comparisons | "15% below 7-day avg" | Arithmetic |
| Zone classification | "ACWR in high_risk zone" | Lookup against thresholds |
| Gap detection | "No Hip Hinge work in 10 days" | Set comparison |
| Aggregations | "Sleep averaging 6.2hrs over 7 nights" | SQL aggregation |

**What Analytics Tools Should NOT Do (Interpretation):**

| Type | Example | Why It's Wrong |
|------|---------|----------------|
| Suppression | "Don't show ACWR warning because annotation exists" | Hides info from Arnold |
| Recommendations | "Consider taking a rest day" | That's coaching |
| Filtering | "Only show warnings without annotations" | Arnold needs full picture |
| Priority decisions | "This is more important than that" | Context-dependent |

---

## File Structure

```
/arnold/data/
├── raw/                        # Native format, untouched
│   ├── neo4j_snapshots/        # JSON exports from graph
│   ├── ultrahuman/             # API syncs + manual exports
│   ├── apple_health/           # XML exports
│   ├── garmin/                 # Historical .FIT files
│   ├── race_logs/              # Manual historical data
│   └── labs/                   # PDF/CSV lab results
├── staging/                    # Parquet, minimal transform
│   ├── workouts.parquet
│   ├── sets.parquet
│   └── apple_health_*.parquet
├── catalog.json                # Data intelligence registry
├── sources.json                # Source registry
└── exports/                    # Generated reports, charts
```

---

## Data Quality

The `data_quality_audit.py` script validates database health:

```bash
python scripts/data_quality_audit.py          # Full audit
python scripts/data_quality_audit.py --quick  # Skip slow checks
```

**Checks performed:**
- Postgres: duplicates, anomalies, gaps, sync history
- Neo4j: orphan exercises, dangling refs, coverage stats
- Cross-database: workout count alignment

See [DATA_QUALITY_AUDIT.md](../automation/DATA_QUALITY_AUDIT.md) for details.
