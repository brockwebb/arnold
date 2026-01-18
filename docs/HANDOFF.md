# Arnold Project Handoff

> **Last Updated:** 2026-01-17
> 
> General project state for new threads. For thread-specific details, see `/docs/handoffs/`.

---

## Project Summary

Arnold is an AI-native fitness coaching system that serves as a comprehensive "Digital Twin" health platform. It combines:
- **Neo4j** (right brain) - relationships, semantics, knowledge graph
- **Postgres** (left brain) - measurements, facts, analytics
- **Claude Desktop MCPs** - domain-specific tools for coaching

---

## Current State

### What's Working
- Consolidated briefing (`memory:load_briefing`) - single call gets all context
- Workout planning and logging (with some routing issues)
- Exercise knowledge graph (4,200+ exercises with muscle targeting)
- HRV/Sleep/Biometric data pipeline (when plist runs)
- Data annotation system for explaining gaps/anomalies
- Memory system with semantic search over coaching observations
- **HRR Pipeline** - Heart rate recovery feature extraction with quality gates

### HRR Pipeline (FR-004)

Fully operational pipeline for extracting heart rate recovery metrics from Polar HR data:

| Component | Status | Description |
|-----------|--------|-------------|
| Feature Extraction | ✅ Complete | `hrr_feature_extraction.py` - detects peaks, computes HRR metrics |
| Quality Gates | ✅ Complete | R² thresholds, slope detection, automatic rejection |
| QC Visualization | ✅ Complete | `hrr_qc_viz.py` - visual validation of intervals |
| Peak Adjustments | ✅ Complete | `peak_adjustments` table for false peak correction |
| Quality Overrides | ✅ NEW | `hrr_quality_overrides` table for force-pass/reject |

**Key Documentation:**
- `/docs/hrr_quality_gates.md` - Quality criteria, peak adjustments, and quality overrides
- `/docs/DATA_DICTIONARY.md` - Schema for all HRR tables
- `/docs/adr/005-hrr-pipeline-architecture.md` - Architecture decisions

**Quick Commands:**
```bash
# Process a session
python scripts/hrr_feature_extraction.py --session-id 70

# Visual QC
python scripts/hrr_qc_viz.py --session-id 70

# Process all sessions
python scripts/hrr_feature_extraction.py --all
```

**QC Override Workflow (when human says interval is valid despite auto-reject):**
```sql
-- 1. Insert override (force_pass example)
INSERT INTO hrr_quality_overrides 
    (polar_session_id, interval_order, override_action, original_status, original_reason, reason)
VALUES 
    (70, 1, 'force_pass', 'rejected', 'r2_30_60_below_0.75', 
     'Human reviewed: valid recovery curve despite segment R² flag.');

-- 2. Reprocess: python scripts/hrr_feature_extraction.py --session-id 70
-- 3. Verify: interval shows pass with HUMAN_OVERRIDE flag
```

**Choosing Peak Adjustment vs Quality Override:**
- Peak detected in wrong place → Peak Adjustment (shifts detection point)
- Peak correct but R² gate too strict → Quality Override (changes status only)

### Active Issues

| Issue | Priority | Description |
|-------|----------|-------------|
| 013 | High | Unified workout schema - segments + sport-specific tables |
| 009 | High | Unified workout logging - needs MCP restart to verify fix |
| 010 | Medium | Neo4j sync gap - silent failures |
| 012 | Low | Sync script directory convention |
| 011 | Closed | LaunchAgent plist (misdiagnosed - API data issue) |

See `/docs/issues/` for details.

### Major Architectural Work Pending

**Issue 013 / ADR-006:** Complete redesign of workout storage schema.
- Current two-table design (`strength_sessions`, `endurance_sessions`) doesn't scale
- New design: `workouts` → `segments` → sport-specific child tables
- Enables multi-modal sessions, arbitrary sports, decades of data
- Consulted ChatGPT Health and Gemini 2.5 Pro for design validation

### Current Training Block
- **Accumulation** - Week 3 of 4 (ends 2026-01-26)
- Focus: Build work capacity, establish movement patterns
- Post knee surgery (8 weeks, cleared for normal activity)

---

## Architecture Quick Reference

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Desktop                           │
│                   (Orchestration Layer)                      │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   memory    │ │  training   │ │  analytics  │ │   journal   │
│    MCP      │ │    MCP      │ │    MCP      │ │    MCP      │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│  Neo4j (relationships)          Postgres (facts)            │
└─────────────────────────────────────────────────────────────┘
```

**Key Principle (ADR-001):** Neo4j stores relationships and meaning. Postgres stores measurements and facts.

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| `/docs/architecture/` | Full architecture docs (modular) |
| `/docs/adr/` | Architecture Decision Records (001-006) |
| `/docs/issues/` | Open issues and bugs |
| `/docs/handoffs/` | Thread-specific handoffs |
| `/docs/handoffs/NEXT_THREAD.md` | Startup script for new threads |

---

## Starting a New Thread

1. Read this file for project context
2. Read `/docs/handoffs/NEXT_THREAD.md` for immediate priorities
3. Call `memory:load_briefing` to get current coaching context
4. Check `/docs/issues/` for open work items

---

## MCP Quick Reference

| MCP | Purpose |
|-----|---------|
| `arnold-memory` | Context loading, observations, semantic search |
| `arnold-training` | Workout planning, logging, exercise resolution |
| `arnold-analytics` | Metrics, trends, data sync |
| `arnold-journal` | Subjective data, annotations |
| `arnold-profile` | Athlete profile, equipment, activities |

---

## Conventions

- **Issues:** `/docs/issues/NNN-description.md`
- **ADRs:** `/docs/adr/NNN-description.md`
- **Handoffs:** `/docs/handoffs/YYYY-MM-DD-topic.md`
- **Transcripts:** `/mnt/transcripts/` (compacted conversations)
- **Scripts:** `/scripts/` (sync, import, analysis tools)
