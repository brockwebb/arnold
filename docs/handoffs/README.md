# Thread Handoffs

Thread-specific context documents for preserving expertise across conversation threads.

---

## Purpose

When a thread does specialized work, the handoff captures:
- What was worked on
- Decisions made and rationale
- Open questions / blockers
- Next steps

This preserves context that would otherwise be lost when a thread ends.

---

## When to Create a Handoff

Create a thread handoff when:
- Significant technical work was done
- Decisions were made that future threads need to know
- Work is incomplete and needs continuation
- Debugging uncovered important insights

Don't create one for:
- Simple Q&A sessions
- Work fully captured in GitHub issues
- Sessions that only modified well-documented files

---

## Naming Convention

```
YYYY-MM-DD-topic.md
```

Examples:
- `2026-01-10-apple-health-pipeline.md`
- `2026-01-08-exercise-resolution-diagnostic.md`

---

## Template

```markdown
# [Topic] - Handoff

## Session Summary
Brief description of what was accomplished.

## Changes Made
- File changes with rationale
- Configuration changes
- Database changes

## Decisions Made
- Decision 1: Why this approach
- Decision 2: Tradeoffs considered

## Open Items
- [ ] Thing that still needs doing
- [ ] Question that needs answering

## Next Steps
What a future thread should do to continue this work.

## Related
- Issue #XX
- ADR-XXX
```

---

## Current Handoffs

| Date | Topic | Summary |
|------|-------|---------|
| 2026-01-13 | Briefing Bugs | Deduplication, annotation filter, workout names fixed |
| 2026-01-13 | Consolidated Briefing | Merged Neo4j + Postgres into single load_briefing call |
| 2026-01-12 | HRR Detection | Completed HRR pipeline with EWMA/CUSUM detection |
| 2026-01-11 | HRR Extraction | Heart rate recovery feature extraction |
| 2026-01-10 | Apple Health Pipeline | Fixed pipeline gap, added gait metrics, created Postgres loader |
| 2026-01-10 | Source Config | Implemented config-driven source priority (Issue #14) |
| 2026-01-08 | Exercise Resolution | Diagnostic and threshold fix |
| 2026-01-07 | Completion Flow | Workout completion workflow |
| 2026-01-07 | Exercise Normalization | Improved exercise matching |
| 2026-01-06 | Analytics Compute vs Interpret | Separated calculation from interpretation |
| 2026-01-06 | Ultrahuman Timeseries | Fixed timeseries data handling |
| 2025-01-07 | Data Quality Session | Database cleanup work |
| 2025-01-06 | Annotation Architecture | Fixed annotation system |

---

## Relationship to HANDOFF.md

- `docs/HANDOFF.md` — General project state (read first)
- `docs/handoffs/*.md` — Thread-specific details (read if relevant)

General handoff tells you where the project is.
Thread handoffs tell you details about specific work streams.
