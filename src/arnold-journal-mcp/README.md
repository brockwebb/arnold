# Arnold Journal MCP

Subjective data capture for the Arnold fitness coaching system.

## Purpose

Captures what sensors can't measure:
- Fatigue levels and energy
- Soreness and pain
- Mood and stress
- Nutrition and hydration
- Supplements and medications
- Workout feedback
- Symptoms and medical observations

## Architecture (ADR-001 Compliant)

**Postgres stores facts.** **Neo4j stores relationships.**

```
User Input → Claude Extraction → log_entry tool
                                      ↓
              ┌───────────────────────┴────────────────────────┐
              ↓                                                ↓
        POSTGRES (facts)                               NEO4J (relationships)
        ┌──────────────────┐                          ┌──────────────────┐
        │ log_entries      │                          │ (:LogEntry)      │
        │   raw_text       │◄────────────────────────►│   postgres_id    │
        │   extracted      │                          │                  │
        │   severity       │                          │ -[:EXPLAINS]->   │
        │   tags           │                          │    (:Workout)    │
        └──────────────────┘                          │ -[:AFFECTS]->    │
                                                      │    (:Plan)       │
                                                      │ -[:RELATED_TO]-> │
                                                      │    (:Injury)     │
                                                      └──────────────────┘
```

## Tools

### Entry Creation
| Tool | Purpose |
|------|---------|
| `log_entry` | Create a new journal entry (Postgres + Neo4j node) |

### Relationship Creation (Neo4j)
| Tool | Purpose |
|------|---------|
| `link_to_workout` | Link entry to past workout (EXPLAINS) |
| `link_to_plan` | Link entry to future plan (AFFECTS) |
| `link_to_injury` | Link entry to injury (RELATED_TO) |
| `link_to_goal` | Link entry to goal (INFORMS) |

### Retrieval - Facts (Postgres)
| Tool | Purpose |
|------|---------|
| `get_recent_entries` | Get entries from last N days |
| `get_unreviewed_entries` | Get entries needing review |
| `get_entries_by_severity` | Get notable/concerning/urgent entries |
| `get_entries_for_date` | Get all entries for a date |
| `search_entries` | Search by tags, type, category |

### Retrieval - Relationships (Neo4j)
| Tool | Purpose |
|------|---------|
| `get_entries_for_workout` | Get entries linked to a workout |
| `get_entries_for_injury` | Get entries related to an injury |
| `get_entries_with_relationships` | Get entries with all relationships |

### Discovery (Find things to link to)
| Tool | Purpose |
|------|---------|
| `find_workouts_for_date` | Find workouts to link |
| `get_active_injuries` | Get injuries to link |
| `get_active_goals` | Get goals to link |

### Management
| Tool | Purpose |
|------|---------|
| `update_entry` | Update extracted data, severity, tags |
| `mark_reviewed` | Mark entry as reviewed by coach/doc |

## Entry Types

- `observation` - General subjective observation
- `nutrition` - Food, hydration, caffeine
- `supplement` - Supplements, vitamins
- `symptom` - Physical symptoms, pain, discomfort
- `mood` - Mental state, stress, motivation
- `feedback` - Workout feedback (too easy, form issues)

## Relationship Types

| Relationship | Meaning | Example |
|-------------|---------|---------|
| `EXPLAINS` | Entry explains workout performance | "Legs heavy" → today's run |
| `AFFECTS` | Entry should influence plan | "Too fatigued" → tomorrow's plan |
| `RELATED_TO` | Entry relates to injury | "Knee better" → knee injury |
| `INFORMS` | Entry provides goal insight | "Pull-up progress" → ring dips goal |
| `DOCUMENTS` | Entry documents symptom | "Dizziness" → symptom node |
| `MENTIONS` | Entry mentions supplement | "Started creatine" → supplement |

## Severity Levels

- `info` - Routine observation
- `notable` - Worth tracking, may show pattern
- `concerning` - Needs attention
- `urgent` - Immediate action required

## Usage Example

```
User: "Legs are toast today, still sore from yesterday's deadlifts. 
       Energy is low, probably need more sleep."

Claude:
1. Calls log_entry to create entry
2. Calls find_workouts_for_date to find yesterday's workout
3. Calls link_to_workout to create EXPLAINS relationship

Result:
- Postgres: Entry with extracted {fatigue: 7, soreness: [{area: legs, level: 8}]}
- Neo4j: LogEntry node → EXPLAINS → yesterday's StrengthWorkout
```

## Installation

```bash
# 1. Run the migration
psql arnold_analytics < scripts/migrations/009_journal_system.sql

# 2. Install the MCP
cd ~/Documents/GitHub/arnold/src/arnold-journal-mcp
pip install -e .

# 3. Add to Claude Desktop config
```

## Related

- Issue #7: Logbook / Journal System
- ADR-001: Data Layer Separation
- Migration 009: journal_system.sql
