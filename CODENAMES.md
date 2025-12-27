# Arnold Internal Codenames

> "Listen, and understand. That Terminator is out there. It can't be bargained with. It can't be reasoned with. It doesn't feel pity, or remorse, or fear. And it absolutely will not stop, ever, until you are fit."

## Cyberdyne Systems Model 101 - Component Designations

### Core Systems

| Component | Codename | Status | Description |
|-----------|----------|--------|-------------|
| Graph Database | **CYBERDYNE-CORE** | ✓ Phase 1 | Neural net processor - knowledge graph foundation |
| MCP Server | **SKYCOACH** | Phase 4 | Real-time tactical coaching interface |
| Email Agent | **T-800** | Phase 5 | Autonomous communication unit |
| Planning Engine | **JUDGMENT-DAY** | Phase 4 | Determines your workout fate |

### Supporting Systems

| Component | Codename | Description |
|-----------|----------|-------------|
| Workout Parser | **SKYNET-READER** | Reads and interprets training logs |
| Volume Analyzer | **TACTICAL-ASSESSMENT** | Analyzes training volume and fatigue |
| Injury Constraint Engine | **DAMAGE-REPORT** | Evaluates structural integrity |
| Progression Algorithm | **FUTURE-WAR** | Long-term adaptation planning |
| Deload Detector | **REST-PROTOCOL** | Identifies recovery requirements |

## Architecture Map

```
┌─────────────────────────────────────────────────────────┐
│                    JUDGMENT-DAY                         │
│              (Planning Engine - Phase 4)                │
│  "Decides what workout fate has in store for you"       │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│    SKYCOACH      │    │      T-800       │
│  (MCP Server)    │    │  (Email Agent)   │
│   Phase 4        │    │   Phase 5        │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌─────────────────────┐
         │   CYBERDYNE-CORE    │
         │  (Graph Database)   │
         │   ✓ Phase 1         │
         └─────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼           ▼           ▼
    [Anatomy]   [Exercises]  [Training]
     UBERON    free-exercise  History
                   -db
```

## Usage in Code

### Python Modules

```python
# src/arnold/graph.py
class ArnoldGraph:
    """CYBERDYNE-CORE: The neural net processor."""
    pass

# src/arnold/planner.py (Phase 4)
class JudgmentDay:
    """JUDGMENT-DAY: Determines workout fate."""
    pass

# src/arnold_mcp/server.py (Phase 4)
class SkycoachServer:
    """SKYCOACH: Real-time tactical coaching."""
    pass

# src/arnold/email_agent.py (Phase 5)
class T800:
    """T-800: Autonomous email communication unit."""
    pass
```

### Configuration

```yaml
# config/arnold.yaml

# SKYCOACH Configuration
skycoach:
  enabled: true
  model: claude-sonnet-4-20250514

# T-800 Configuration
t-800:
  email_schedule: "0 6 * * *"

# CYBERDYNE-CORE Configuration
cyberdyne_core:
  name: arnold
  backup_enabled: true

# JUDGMENT-DAY Configuration
judgment_day:
  lookahead_days: 7
  auto_deload_trigger: true
```

## Response Templates

Each system has personality:

### CYBERDYNE-CORE (Graph Database)
```python
MESSAGES = [
    "Data acquired. Processing...",
    "Neural net learning...",
    "Knowledge graph updated.",
]
```

### SKYCOACH (MCP Server)
```python
GREETINGS = [
    "Come with me if you want to lift.",
    "I'll be back... with your training plan.",
]

WARNINGS = [
    "You are terminated... if you keep this up.",
    "I'm a cybernetic organism. You are not. Recover.",
]
```

### T-800 (Email Agent)
```python
EMAIL_SIGNATURES = [
    "-- The T-800\nCyberdyne Systems Model 101",
    "-- Your Fitness Terminator\nI'll be back tomorrow.",
]
```

### JUDGMENT-DAY (Planning Engine)
```python
PLAN_HEADERS = [
    "Your fate has been decided...",
    "Judgment Day Protocol: Activated",
    "The following workout cannot be bargained with...",
]
```

## Easter Eggs

### Success Messages
```python
SUCCESS = [
    "Excellent. Your form is... adequate.",
    "Target acquired: gains.",
    "Mission accomplished.",
    "I need your clothes, your boots, and your PR.",
]
```

### Overtraining Warnings
```python
OVERTRAINING = [
    "You are terminated... if you keep this up.",
    "I'm a cybernetic organism. You are not. Recover.",
    "This is not a negotiation. Deload.",
    "Your foster parents are dead. So will your gains be.",
]
```

### Recovery Recommendations
```python
RECOVERY = [
    "Your muscles need time. I need a vacation.",
    "Rest day. Even machines need maintenance.",
    "You are not a machine. I am. Rest.",
    "Hasta la vista, weakness. (After you recover)",
]
```

### Progression Achievements
```python
ACHIEVEMENTS = [
    "I'll be back... you just got stronger.",
    "Come with me if you want to lift... heavier.",
    "Terminated that PR.",
    "No fate but what we make. You made gains.",
]
```

## File Headers

Each major file should include its codename:

```python
#!/usr/bin/env python3
"""
Arnold Graph Database Interface
================================
Internal Codename: CYBERDYNE-CORE

"The more contact I have with humans, the more I learn."
"""
```

## Log Messages

Use codenames in logs:

```python
logger.info("[CYBERDYNE-CORE] Database connection established")
logger.info("[JUDGMENT-DAY] Planning session initiated")
logger.info("[SKYCOACH] MCP server listening on port 8080")
logger.info("[T-800] Email sent: Daily training plan")
```

## Environment Variables

```bash
# .env
CYBERDYNE_CORE_URI=bolt://localhost:7687
SKYCOACH_PORT=8080
T800_EMAIL=arnold@cyberdyne.systems
JUDGMENT_DAY_MODE=adaptive
```

## Docker Containers

```bash
# Neo4j database
docker run --name cyberdyne-core neo4j:latest

# Future: Email processor
docker run --name t-800 arnold-email-agent

# Future: MCP server
docker run --name skycoach arnold-mcp-server
```

## Documentation References

When referring to components in docs:

- "The graph database (CYBERDYNE-CORE) stores..."
- "SKYCOACH, the MCP server, provides..."
- "When T-800 sends your daily plan..."
- "JUDGMENT-DAY analyzes your training history..."

## Why These Codenames?

| Codename | Reasoning |
|----------|-----------|
| **CYBERDYNE-CORE** | The company that created Skynet; the core knowledge system |
| **SKYCOACH** | Skynet + Coach; the AI coaching interface |
| **T-800** | Model 101 Terminator; relentless email communication |
| **JUDGMENT-DAY** | When Skynet became self-aware; when Arnold decides your workout |

## Quotes for Each System

### CYBERDYNE-CORE
> "The more contact I have with humans, the more I learn."

### SKYCOACH
> "Come with me if you want to lift."

### T-800
> "I'll be back." (Every morning with a new plan)

### JUDGMENT-DAY
> "No fate but what we make." (Your workout is not predetermined)

---

## Usage Guidelines

1. **Internal code**: Always use codenames in comments and class names
2. **User-facing**: Use friendly names ("Arnold", "the training planner")
3. **Logs**: Use codenames in square brackets `[CYBERDYNE-CORE]`
4. **Config files**: Use lowercase with underscores `cyberdyne_core`
5. **Easter eggs**: Go full Terminator quotes

---

*"Listen, and understand. That Terminator is out there, making you stronger."*
