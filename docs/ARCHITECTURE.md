# Arnold Architecture

> ⚠️ **This document has been split into modular sections.**
> 
> See the **[architecture/](./architecture/)** directory for the full documentation.

---

## Quick Navigation

| Document | Content |
|----------|---------|
| **[README](./architecture/README.md)** | Index, principles, ADR references |
| [Vision](./architecture/vision.md) | Digital Twin concept, team model, data sources |
| [Coaching Philosophy](./architecture/coaching.md) | How Arnold coaches, feedback loops |
| [Data Architecture](./architecture/data_architecture.md) | Postgres/Neo4j split, bridge pattern |
| [Graph Model](./architecture/graph_model.md) | Node types, relationships, Cypher patterns |
| [Memory System](./architecture/memory.md) | Three-tier memory, semantic search |
| [Analytics](./architecture/analytics.md) | Control systems model, Bayesian framework |
| [Journal System](./architecture/journal.md) | Subjective data capture |
| [MCP Roster](./architecture/mcp_roster.md) | Tool distribution across MCPs |
| [Workflows](./architecture/workflows.md) | Coach workflow, session generation |
| [Roadmap](./architecture/roadmap.md) | Development phases and status |

---

## Architecture Decisions

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](./adr/001-data-layer-separation.md) | Data Layer Separation | Accepted |
| [ADR-002](./adr/002-strength-workout-migration.md) | Strength Workout Migration | Implemented |
| [ADR-003](./adr/003-exercise-hierarchy.md) | Exercise Hierarchy and Variation Modeling | Proposed |
| [ADR-004](./adr/004-decision-traces.md) | Decision Trace System | Proposed |

---

## Why Split?

The monolithic architecture document grew to ~45KB covering vision, coaching philosophy, data architecture, memory systems, analytics, and roadmap. Splitting by **audience and purpose** makes it easier to:

- Find relevant information quickly
- Update sections independently
- Onboard new conversation threads with targeted context
- Keep each file focused and maintainable

---

## Related Documents

- [TRAINING_METRICS.md](./TRAINING_METRICS.md) — Evidence-based metrics with citations
- [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) — Data source reference
- [HANDOFF.md](./HANDOFF.md) — Thread handoff quick reference
