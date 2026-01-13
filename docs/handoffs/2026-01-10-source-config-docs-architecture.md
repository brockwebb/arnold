# Source Config + Documentation Architecture - Handoff

> **Session Date**: January 10, 2026  
> **Status**: Complete  
> **Next Thread Priority**: Issue #20 Phase A

---

## Session Summary

Major session covering:
1. Implemented config-driven source priority (Issue #14) ✓ CLOSED
2. Created Documentation Register (Issue #16) ✓ CLOSED
3. Redesigned handoff architecture (Issue #17) ✓ CLOSED
4. Designed session protocols for consistent Coach behavior (Issue #20) — OPEN, next priority

---

## Changes Made

### Config-Driven Source Priority (Issue #14 - CLOSED)

**Files created:**
- `config/sources.yaml` — Source priority definitions with AI/human instructions
- `scripts/sync/source_resolver.py` — Resolution logic + CLI
- `scripts/sync/validate_config.py` — Config validation

**Files modified:**
- `scripts/sync/import_apple_health.py` — Reverted exclusions, now imports ALL data
- `docs/architecture/README.md` — Added Source Configuration section
- `docs/DATA_SOURCES.md` — Rewrote for config-driven approach

**Key decision:** Importers are "dumb pipes" — pull all data, resolution happens downstream via config.

### Documentation Register (Issue #16 - CLOSED)

**Files created:**
- `docs/DOCUMENTATION_REGISTER.md` — Master index of all documentation

**Purpose:** New threads know what docs exist and where to put new content.

### Handoff Architecture (Issue #17 - CLOSED)

**Changes:**
- Consolidated `docs/handoff/` (singular) into `docs/handoffs/` (plural)
- Created `docs/handoffs/README.md` — Thread handoff index
- Updated `docs/HANDOFF.md` — General project state with proper header

**Structure:**
```
docs/
├── DOCUMENTATION_REGISTER.md  ← Read first for doc work
├── HANDOFF.md                 ← General project state
└── handoffs/
    ├── README.md              ← Thread handoff index
    └── *.md                   ← Thread-specific handoffs
```

---

## Key Insight: The Consistency Problem

We had a deep discussion about why Coach behavior is inconsistent across threads.

**Root cause:** Claude Desktop doesn't support mandatory startup hooks. More MCPs, more data, more memory doesn't help if Claude doesn't reliably call the context-loading tools.

**Solution:** Convention-based protocols:
- Startup: "Coach, ready to train" → `load_briefing()` 
- Debrief: "Coach, let's debrief" → collaborative knowledge capture

This accepts the constraint and optimizes within it.

**Key realization:** We're building a knowledge layer (graph + analytics), not updating the LLM. Claude is the intelligence that uses the knowledge. As LLMs improve, they use the knowledge better. Investment is in the knowledge, not the model.

---

## Recommended Next Priority: Issue #20 Phase A

**Issue**: [#20 - Session protocols and data-driven personality](https://github.com/brockwebb/arnold/issues/20)

**Why this is highest priority:**
- Directly addresses the Coach consistency problem
- Foundation for all other Coach improvements
- Relatively contained scope (Phase A only)
- Immediate visible value

**Phase A Tasks:**
1. Define observation tags that inform personality (e.g., `coaching_approach`, `preference`, `pattern`)
2. Update `load_briefing()` in arnold-memory-mcp to assemble personality block from observations
3. Create base personality config: `config/personalities/coach.md`
4. Seed initial observations about athlete based on what we know

**Expected output from load_briefing():**
```markdown
## Athlete-Specific Coaching Notes

Based on {N} sessions with this athlete:
- Responds well to data-driven justification
- Tends to skip horizontal push; needs accountability
- When resistant to planned workout, probe for external stressors
- HRV < 40 correlates with low energy reports
- Prefers direct communication; doesn't need excessive warmth
```

**Where to start:**
1. Read `mcp-servers/arnold-memory-mcp/` to understand current `load_briefing()` implementation
2. Check what observations already exist via `get_observations()`
3. Design the personality assembly query
4. Add personality section to briefing output

---

## Open Issues After This Session

| # | Title | Priority | Notes |
|---|-------|----------|-------|
| **20** | Session protocols + data-driven personality | **HIGH** | Next thread priority |
| 18 | Agent personality prompts | Medium | #20 Phase A partially addresses |
| 19 | Predictive analysis & optimization | Medium | Needs foundation first |
| 15 | Detailed data pipeline diagram | Low | Documentation |
| 2 | Daily cron setup | Low | Sync works manually |

---

## Files Changed This Session

### Created
- `config/sources.yaml`
- `scripts/sync/source_resolver.py`
- `scripts/sync/validate_config.py`
- `docs/DOCUMENTATION_REGISTER.md`
- `docs/handoffs/README.md`
- `docs/handoffs/2026-01-10-source-config-docs-architecture.md`

### Modified
- `scripts/sync/import_apple_health.py`
- `docs/architecture/README.md`
- `docs/DATA_SOURCES.md`
- `docs/HANDOFF.md`

### Moved
- `docs/handoff/2026-01-10-apple-health-pipeline.md` → `docs/handoffs/`

---

## For Next Thread

1. Read `docs/HANDOFF.md` for project state
2. Read Issue #20 (full context on the problem and solution)
3. Read the collaborative debrief comment on #20
4. Start with `mcp-servers/arnold-memory-mcp/` to understand `load_briefing()`
5. Implement Phase A: data-driven personality assembly
