# Documentation Register

> **Last Updated**: January 20, 2026  
> **Purpose**: Master index of all documentation artifacts. Read before creating or editing docs.

---

## ⚠️ Before Editing Documentation

1. Check this register for existing docs on your topic
2. Follow naming conventions for your document type
3. Update this register if you create new docs
4. Thread-specific work goes in `docs/handoffs/`

---

## Quick Reference

| I need to... | Go to... |
|--------------|----------|
| Understand the system | `docs/architecture/README.md` |
| Start a new thread | `docs/HANDOFF.md` |
| Find thread-specific context | `docs/handoffs/` |
| Log a decision | `docs/adr/` |
| Document a requirement | `docs/requirements/` |
| Understand an MCP | `docs/mcps/` |
| Verify changes / regression test | `docs/TESTING.md` |

---

## Architecture Documents

Core system design documentation.

| Document | Location | Purpose | Update When |
|----------|----------|---------|-------------|
| Architecture Overview | `docs/architecture/README.md` | Navigation hub, principles, ADR index | Architecture changes |
| Vision | `docs/architecture/vision.md` | Digital Twin concept, team model | Vision evolves |
| Data Architecture | `docs/architecture/data_architecture.md` | Postgres/Neo4j split, ADR-001 | Schema changes |
| Graph Model | `docs/architecture/graph_model.md` | Neo4j node types, relationships | Graph schema changes |
| Memory System | `docs/architecture/memory.md` | Three-tier memory, semantic search | Memory MCP changes |
| Analytics | `docs/architecture/analytics.md` | Metrics, Bayesian framework | Analytics changes |
| Journal System | `docs/architecture/journal.md` | Subjective data capture | Journal MCP changes |
| Coaching Philosophy | `docs/architecture/coaching.md` | How Arnold coaches | Coaching approach changes |
| MCP Roster | `docs/architecture/mcp_roster.md` | Tool distribution across MCPs | MCP changes |
| Workflows | `docs/architecture/workflows.md` | Coach workflow, session flow | Workflow changes |
| Roadmap | `docs/architecture/roadmap.md` | Development phases | Phase completion |

---

## Architecture Decision Records (ADRs)

Significant architectural decisions with rationale.

| ADR | Title | Status | Location |
|-----|-------|--------|----------|
| 001 | Data Layer Separation | Accepted | `docs/adr/001-data-layer-separation.md` |
| 002 | Strength Workout Migration | Implemented | `docs/adr/002-strength-workout-migration.md` |
| 003 | Exercise Hierarchy | Proposed | `docs/adr/003-exercise-hierarchy.md` |
| 004 | Decision Traces | Proposed | `docs/adr/004-decision-traces.md` |
| 005 | HRR Pipeline Architecture | Accepted | `docs/adr/005-hrr-pipeline-architecture.md` |

**Convention**: `docs/adr/NNN-short-title.md`

---

## Requirements

Formal requirements with traceability.

| Requirement | Title | Status | Location |
|-------------|-------|--------|----------|
| FR-001 | Athlete Profile ADR-001 Compliance | — | `docs/requirements/FR-001-athlete-profile-adr001-compliance.md` |
| FR-002 | Sensor Hierarchy | Implemented | `docs/requirements/FR-002-sensor-hierarchy.md` |
| FR-003 | HR Session Workout Linking | — | `docs/requirements/FR-003-hr-session-workout-linking.md` |
| FR-004 | Recovery Interval Detection | — | `docs/requirements/FR-004-recovery-interval-detection.md` |
| FR-005 | Exercise Alias System | — | `docs/requirements/FR-005-exercise-alias-system.md` |
| INDEX | Requirements Index | — | `docs/requirements/INDEX.md` |

**Convention**: `docs/requirements/FR-NNN-short-title.md`

---

## MCP Documentation

Per-server documentation for each MCP.

| MCP | Purpose | Location |
|-----|---------|----------|
| Overview | MCP architecture | `docs/mcps/README.md` |
| arnold-profile | Athlete data, equipment | `docs/mcps/arnold-profile.md` |
| arnold-training | Planning, workout logging | `docs/mcps/arnold-training.md` |
| arnold-memory | Context, observations | `docs/mcps/arnold-memory.md` |
| arnold-analytics | Metrics, readiness | `docs/mcps/arnold-analytics.md` |

---

## Diagrams

Visual architecture representations.

| Diagram | Type | Location |
|---------|------|----------|
| Overview | Index | `docs/architecture/diagrams/README.md` |
| System Context | SV-0 | `docs/architecture/diagrams/sv0-system-context.mermaid` |
| Component Architecture | SV-1 | `docs/architecture/diagrams/sv1-component-architecture.mermaid` |
| Data Flow | Flow | `docs/architecture/diagrams/data-flow.mermaid` |
| Intelligence Stack | Stack | `docs/architecture/diagrams/intelligence-stack.mermaid` |

**Note**: Issue #15 tracks creating detailed data pipeline diagram.

---

## Operational Documents

Day-to-day operations and automation.

| Document | Purpose | Location |
|----------|---------|----------|
| **Testing Guide** | Verification procedures, test cases, regression testing | `docs/TESTING.md` |
| Data Sources | Source hierarchy, provenance | `docs/DATA_SOURCES.md` |
| Data Dictionary | Data catalog reference | `docs/DATA_DICTIONARY.md` |
| Training Metrics | Evidence-based metrics | `docs/TRAINING_METRICS.md` |
| Standards & Ontologies | LOINC, ICD-10, etc. | `docs/STANDARDS_AND_ONTOLOGIES.md` |
| Setup Guide | Installation | `docs/setup.md` |
| Schema Reference | Database schemas | `docs/schema.md` |

---

## Automation

Scheduled jobs and operations.

| Document | Purpose | Location |
|----------|---------|----------|
| Launchd Sync | macOS sync scheduling | `docs/automation/LAUNCHD_SYNC.md` |
| Data Quality Audit | Health checks | `docs/automation/DATA_QUALITY_AUDIT.md` |

---

## Handoffs

Thread continuity documentation.

| Document | Purpose | Location |
|----------|---------|----------|
| **General Handoff** | Current project state | `docs/HANDOFF.md` |
| **Thread Index** | List of thread handoffs | `docs/handoffs/README.md` |
| Thread-specific | Per-thread context | `docs/handoffs/*.md` |

**Convention**: `docs/handoffs/YYYY-MM-DD-topic.md`

See Issue #17 for handoff architecture.

---

## Workflows

Operational workflows and protocols.

| Document | Purpose | Location |
|----------|---------|----------|
| Session Protocols | Startup + debrief rituals | `docs/workflows/session_protocols.md` |

See Issue #20 for session protocol implementation.

---

## Configuration

System configuration files.

| File | Purpose | Location |
|------|---------|----------|
| Source Priorities | Device/metric priorities | `config/sources.yaml` |
| (Future) Personalities | Agent behavior | `config/personalities/` |

---

## Legacy Documents

Historical documents — reference only, may be outdated.

| Document | Status | Location |
|----------|--------|----------|
| Arnold Spec | Historical | `docs/arnold-spec.md` |
| Phase 2 Spec | Historical | `docs/arnold-phase2-spec.md` |
| Phase 4 Summary | Historical | `docs/PHASE4_SUMMARY.md` |
| Phase 4 Verification | Historical | `docs/PHASE4_VERIFICATION_REPORT.md` |
| Phase 4 Workout Ingestion | Historical | `docs/PHASE4_WORKOUT_INGESTION_COMPLETE.md` |
| Movement Pattern Report | Historical | `docs/MOVEMENT_PATTERN_CLASSIFICATION_REPORT.md` |
| Exercise KB Plan | Historical | `docs/exercise_kb_improvement_plan.md` |
| Workout Ingest Spec | Historical | `docs/WORKOUT_INGEST_SPEC.md` |

---

## Local Issue Tracking

Pre-GitHub issue tracking (historical).

| Location | Purpose |
|----------|---------|
| `docs/issues/` | Legacy issue docs |

**Note**: Use GitHub Issues for current tracking.

---

## Document Types & Conventions

| Type | Location | Naming | Purpose |
|------|----------|--------|---------|
| ADR | `docs/adr/` | `NNN-title.md` | Architecture decisions |
| Requirement | `docs/requirements/` | `FR-NNN-title.md` | Formal requirements |
| MCP Doc | `docs/mcps/` | `arnold-{name}.md` | Server documentation |
| Handoff | `docs/handoffs/` | `YYYY-MM-DD-topic.md` | Thread context |
| Diagram | `docs/architecture/diagrams/` | `*.mermaid` | Visual architecture |

---

## Ownership

| Area | Owner |
|------|-------|
| Architecture | Brock + Claude threads |
| ADRs | Whoever proposes |
| Handoffs | Each thread |
| This Register | Update as you create docs |
