# Arnold Architecture

> **Purpose**: Authoritative reference for Arnold's architecture. Context handoff between conversation threads and north star for development.

> **Last Updated**: January 8, 2026

---

## Quick Navigation

| Document | Content |
|----------|---------|  
| **[Diagrams](./diagrams/)** | **System views for presentations (SV-0, SV-1, data flow)** |
| [Vision](./vision.md) | Digital Twin concept, team model, data sources, core principles |
| [Coaching Philosophy](./coaching.md) | How Arnold coaches, intensity scaling, feedback loops, explanations |
| [Data Architecture](./data_architecture.md) | Postgres/Neo4j split, bridge pattern, relationship caching |
| [Graph Model](./graph_model.md) | Node types, relationships, Cypher query patterns |
| [Memory System](./memory.md) | Three-tier memory, semantic search, briefings |
| [Analytics](./analytics.md) | Control systems model, Bayesian framework, metrics |
| [Journal System](./journal.md) | Subjective data capture, relationship linking |
| [MCP Roster](./mcp_roster.md) | Tool distribution across MCPs |
| [Workflows](./workflows.md) | Coach workflow, session generation, output formats |
| [Roadmap](./roadmap.md) | Development phases and status |

---

## Executive Summary

Arnold is an AI-native fitness coaching system built on Neo4j + Postgres. Claude Desktop serves as the reasoning/orchestration layer, with specialist MCP servers providing domain tools.

**Critical insight: Claude IS the orchestrator** — MCPs are tools, not agents.

Arnold is designed as a **proto-human system**: it learns and grows with the user, adapting to goals, experience level, and life context.

---

## Core Principles

### Graph-First
Everything is relationships. Start at any node, traverse to what you need.

### Modality as Hub
Training domains are the central organizing concept. "What are we training?" is the fundamental question.

### LLM-Native
Use Claude's reasoning for decisions, not rigid rule engines. MCPs provide data; Claude provides intelligence.

### Science-Grounded
Periodization models, progression schemes, and coaching logic are grounded in peer-reviewed exercise science.

### Data Sovereignty
Your data, your control. All personal health data lives in your own databases. Portable, queryable, private.

### Minimal State
MCPs query fresh data, don't cache. Context is managed explicitly through memory layer.

### Compact Output
Phone-readable. The athlete is in the gym, not at a desk.

### Human in the Loop
The system advises; the human decides.

---

## Architecture Decisions

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](../adr/001-data-layer-separation.md) | Data Layer Separation | Accepted |
| [ADR-002](../adr/002-strength-workout-migration.md) | Strength Workout Migration | Implemented |
| [ADR-003](../adr/003-exercise-hierarchy.md) | Exercise Hierarchy and Variation Modeling | Proposed |
| [ADR-004](../adr/004-decision-traces.md) | Decision Trace System | Proposed |

---

## Source Configuration

Data source priorities are defined in `config/sources.yaml`. This config-driven approach allows:

- **Device changes** without code changes
- **Algorithm documentation** (e.g., SDNN vs RMSSD for HRV)
- **AI-friendly** self-documenting format with prompt instructions

Key components:
- `config/sources.yaml` — Source priority definitions
- `scripts/sync/source_resolver.py` — Resolution logic
- `scripts/sync/validate_config.py` — Configuration validation

See [DATA_SOURCES.md](../DATA_SOURCES.md) for detailed provenance documentation.

---

## Related Documents

- [TRAINING_METRICS.md](../TRAINING_METRICS.md) — Evidence-based metrics with citations
- [DATA_DICTIONARY.md](../DATA_DICTIONARY.md) — Data source reference
- [HANDOFF.md](../HANDOFF.md) — Thread handoff quick reference
- [STANDARDS_AND_ONTOLOGIES.md](../STANDARDS_AND_ONTOLOGIES.md) — Medical ontology references

## Automation & Operations

- [LAUNCHD_SYNC.md](../automation/LAUNCHD_SYNC.md) — Daily sync scheduling (macOS)
- [DATA_QUALITY_AUDIT.md](../automation/DATA_QUALITY_AUDIT.md) — Database health checks

---

## Codenames (Internal)

| Codename | Component |
|----------|-----------|
| CYBERDYNE-CORE | Neo4j database |
| SKYNET-READER | Data import pipelines |
| JUDGMENT-DAY | Workout planning logic |
| T-800 | Exercise knowledge graph |
| SARAH-CONNOR | User profile/digital twin |
| T-1000 | Analyst (analytics-mcp) |
| MILES-DYSON | Doc (medical-mcp) |
| JOHN-CONNOR | Researcher (research-mcp) |
