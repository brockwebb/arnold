# Journal System (Subjective Data Capture)

> **Last Updated**: January 8, 2026

The journal captures **what sensors can't measure** — the subjective experience that completes the Digital Twin.

---

## What It Captures

| Category | Examples |
|----------|----------|
| Recovery | Fatigue levels, soreness, energy |
| Physical | Symptoms, pain, stiffness, numbness |
| Mental | Mood, stress, motivation |
| Nutrition | Food, hydration, caffeine |
| Medical | Supplements, medications, side effects |
| Training | Workout feedback, form issues, RPE |

---

## Architecture (ADR-001 Compliant)

```
User: "My right knee feels stiff from yesterday's run"
                    │
                    ▼
            Claude extracts:
            • symptom: stiffness
            • location: right knee
            • cause: running
            • severity: notable
                    │
    ┌───────────────┴───────────────┐
    ▼                               ▼
POSTGRES (facts)              NEO4J (relationships)
log_entries                   (:LogEntry)
  id: 2                         │
  raw_text: "..."           ─[:EXPLAINS]─▶ (:EnduranceWorkout)
  extracted: {...}          ─[:RELATED_TO]─▶ (:Injury {right_knee_meniscus})
  severity: notable
```

**Key Insight**: The graph *knows* about the knee surgery. When the user mentions "right knee" + "stiffness", the relationship to the injury is automatic — no rules, no keywords, just graph traversal.

---

## Relationship Types

| Relationship | Direction | Meaning |
|--------------|-----------|--------|
| `EXPLAINS` | LogEntry → Workout | Entry explains workout performance |
| `AFFECTS` | LogEntry → PlannedWorkout | Entry should influence future plan |
| `RELATED_TO` | LogEntry → Injury | Entry relates to injury |
| `INFORMS` | LogEntry → Goal | Entry provides goal insight |
| `DOCUMENTS` | LogEntry → Symptom | Entry documents symptom pattern |
| `MENTIONS` | LogEntry → Supplement | Entry mentions supplement |

---

## MCP Tools (arnold-journal-mcp)

**Entry Creation**:
- `log_entry` — Create entry with Claude-extracted structured data

**Relationship Creation**:
- `link_to_workout` — EXPLAINS a past workout
- `link_to_plan` — AFFECTS a future plan  
- `link_to_injury` — RELATED_TO an injury
- `link_to_goal` — INFORMS a goal

**Retrieval (Postgres)**:
- `get_recent_entries` — Last N days
- `get_unreviewed_entries` — For coach/doc briefings
- `get_entries_by_severity` — Notable/concerning/urgent
- `search_entries` — Filter by tags, type, category

**Retrieval (Neo4j)**:
- `get_entries_for_workout` — All entries explaining a workout
- `get_entries_for_injury` — All entries related to an injury
- `get_entries_with_relationships` — Entries with all their links

**Discovery**:
- `find_workouts_for_date` — Find workouts to link
- `get_active_injuries` — Find injuries to link
- `get_active_goals` — Find goals to link

---

## Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `info` | Routine observation | Log only |
| `notable` | Worth tracking | Include in briefings |
| `concerning` | Needs attention | Flag for review |
| `urgent` | Immediate action | Alert |

---

## Usage Flow

1. User shares observation naturally: *"Legs are toast from yesterday's run"*
2. Claude extracts structured data (fatigue level, body part, cause)
3. `log_entry` creates Postgres record + Neo4j node
4. Claude finds related entities (yesterday's workout, any injuries)
5. `link_to_*` tools create graph relationships
6. Entry appears in future briefings with full context

---

## Data Annotations

Annotations explain data gaps and anomalies. They follow the same dual-storage pattern:

**Postgres** (`data_annotations`):
- Content, date range, reason code, tags
- Time-series queries: "annotations covering this date"

**Neo4j** (`(:Annotation)`):
- Lightweight reference with postgres_id
- Relationships: `[:EXPLAINS]` workouts, injuries

**Reason Codes:**
- `device_issue` — Sensor malfunction
- `surgery` — Post-op recovery
- `injury` — Active injury
- `expected` — Normal variation (hard workout)
- `travel`, `illness`, `deload`, `life`

**Critical:** Analytics layer reports observations alongside annotations. It does NOT suppress warnings. Arnold synthesizes both and decides what to surface.

See `/src/arnold-journal-mcp/README.md` for full documentation.
