# Arnold Memory MCP

Context management and coaching continuity for the Arnold training system.

## Purpose

Solves the "amnesia problem" - Claude starts every conversation fresh without knowing:
- Who you are
- What your goals are
- What block you're in
- Your training levels per modality
- Recent workouts
- Past coaching observations

This MCP loads comprehensive context at conversation start, enabling effective coaching from message one.

## Tools

### `load_briefing`

**Call this FIRST in any training conversation.**

Returns comprehensive coaching context:
- Athlete identity & phenotype
- Athletic background
- Active goals with modality requirements
- Training levels per modality with progression models
- Current block (week X of Y, intent, targets)
- Medical constraints & injuries
- Recent workouts (14 days)
- Coaching observations from past conversations
- Upcoming planned sessions
- Available equipment

### `store_observation`

Persist coaching insights for future reference:

```
store_observation(
  content="Fatigue pattern emerges on deadlift set 3+ above 275lbs",
  observation_type="pattern",  // pattern | preference | insight | flag | decision
  tags=["deadlift", "fatigue"]
)
```

### `get_observations`

Retrieve past observations with optional filters:

```
get_observations(tags=["deadlift"], limit=10)
```

### `get_block_summary` / `store_block_summary`

Capture block-level summaries at block end.

## Installation

```bash
cd /Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp
pip install -e .
```

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arnold-memory": {
      "command": "/path/to/python",
      "args": ["-m", "arnold_memory_mcp.server"],
      "cwd": "/Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "NEO4J_DATABASE": "arnold"
      }
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| NEO4J_URI | bolt://localhost:7687 | Neo4j connection URI |
| NEO4J_USER | neo4j | Neo4j username |
| NEO4J_PASSWORD | (required) | Neo4j password |
| NEO4J_DATABASE | arnold | Database name |

## Usage Pattern

Every training conversation should start with:

```
Claude: [calls load_briefing]

# COACHING CONTEXT: Brock Webb

**Athlete Type:** lifelong (35 years total)

## Active Goals
- **Deadlift 405x5** (by 2026-12-31) [high]
  → Hip Hinge Strength: novice level, Linear Periodization
  → Core Stability: advanced level, Non-Linear/Undulating Periodization
- **Hellgate 100k** (by 2026-12-01) [high]
  → Ultra Endurance: advanced level, Block Periodization
...

## Current Block
**Accumulation** (accumulation)
- Week 1 of 4
- Intent: Build work capacity, establish movement patterns
...
```

Now Claude has full context and can coach effectively.

## Architecture

```
load_briefing
     │
     ▼
┌─────────────────────────────────────────┐
│              NEO4J GRAPH                │
│                                         │
│  Person ──┬── HAS_GOAL ──► Goal         │
│           │                  │          │
│           │            [:REQUIRES]      │
│           │                  ▼          │
│           ├── HAS_LEVEL ► TrainingLevel │
│           │                  │          │
│           │           [:FOR_MODALITY]   │
│           │                  ▼          │
│           │              Modality       │
│           │                             │
│           ├── HAS_BLOCK ──► Block       │
│           │                             │
│           ├── PERFORMED ──► Workout     │
│           │                             │
│           ├── HAS_INJURY ─► Injury      │
│           │                             │
│           └── HAS_OBSERVATION ► Obs     │
└─────────────────────────────────────────┘
```

## Development

Logs written to `/tmp/arnold-memory-mcp.log`
