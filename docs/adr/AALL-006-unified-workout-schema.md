# After Action Lessons Learned (AALL): ADR-006 Unified Workout Schema

**Document ID:** AALL-006  
**Date:** January 20, 2026  
**Project:** Arnold - AI Fitness Coaching System  
**Subject ADR:** ADR-006: Unified Workout Schema — Segments + Sport-Specific Child Tables  
**Status of Subject ADR:** Superseded by ADR-007  
**Lifespan:** January 13, 2026 → January 20, 2026 (7 days in production)

---

## 1. Executive Summary

ADR-006 introduced a segment-based workout schema with sport-specific child tables to handle multi-modal workouts. The design was technically sound but over-engineered for actual use patterns. After one week in production, we rolled back to a simpler three-table model (ADR-007). This AALL documents what went wrong, why, and how to avoid similar mistakes.

**Bottom line:** We solved problems we didn't have while creating problems we didn't anticipate.

---

## 2. Background

### 2.1 Problem Statement (as understood at decision time)

The system needed to handle:
- Multi-modal workouts (CrossFit, brick workouts, hybrid training)
- Sport-specific metrics (SWOLF, power, strokes, splits)
- 35+ years of diverse athletic history
- Decades of future data

### 2.2 Decision Made

Adopt a discriminator pattern:
```
workouts → segments (discriminator: sport_type) → child tables
           ├── strength_sets
           ├── running_intervals
           ├── rowing_intervals
           ├── cycling_intervals
           └── swimming_laps
```

### 2.3 Stakeholders Consulted

- Brock Webb (athlete/developer)
- Claude (primary AI assistant)
- ChatGPT Health (domain expert consultation)
- Gemini 2.5 Pro (architecture review)

### 2.4 Implementation Artifacts

- Tables: `workouts_v2`, `segments`, `v2_strength_sets`, `v2_running_intervals`, `v2_rowing_intervals`, `v2_cycling_intervals`, `v2_swimming_laps`, `segment_events_generic`
- Views: `v_all_activity_events`, `workout_summaries_v2`, `srpe_training_load`, `training_load_daily`
- MCP updates: `arnold-training-mcp`, `arnold-analytics-mcp`, `arnold-memory-mcp`

---

## 3. What Happened

### 3.1 Timeline

| Date | Event |
|------|-------|
| Jan 13 | ADR-006 accepted after multi-model consultation |
| Jan 14-15 | Schema implemented, MCPs updated |
| Jan 15-19 | Production use revealed double-insert bug, query complexity |
| Jan 19 | Decision to simplify after workout logging friction observed |
| Jan 20 | ADR-007 drafted, migration plan created |

### 3.2 Observed Problems

1. **Empty sport tables** — `v2_running_intervals`, `v2_rowing_intervals`, etc. had zero rows. Nobody manually logs running intervals; that data comes from device imports (FIT files).

2. **Query complexity** — Every workout query required segment → child table joins with sport_type discrimination. Simple questions became complex SQL.

3. **Naming confusion** — "Segment" was overloaded to mean both sport modality and training phase. Engineers couldn't reason about it clearly.

4. **Deviation capture friction** — Forcing explanations at logging time interrupted workout flow.

5. **Double-insert bug** — Race condition in MCP caused duplicate workouts (Jan 15, 19).

6. **Technical debt accumulation** — "v2" prefix shipped to production, creating permanent namespace pollution.

### 3.3 Data State at Rollback

- `workouts_v2`: ~50 rows (valid workout data)
- `segments`: ~50 rows (valid, 1:1 with workouts)
- `v2_strength_sets`: ~300 rows (valid set data)
- `v2_running_intervals`: 0 rows
- `v2_rowing_intervals`: 0 rows  
- `v2_cycling_intervals`: 0 rows
- `v2_swimming_laps`: 0 rows
- `segment_events_generic`: 0 rows

The empty tables prove we built for hypothetical futures, not actual use.

---

## 4. Root Cause Analysis

### 4.1 Primary Cause: Premature Generalization

We designed for "what if we need to track rowing?" instead of "what do we actually track?" The 95% use case (strength training) was buried under architecture for the 5% case (multi-sport).

**Contributing factors:**
- Athlete's diverse background (martial arts, ultrarunning) suggested multi-modal needs
- AI consultants optimized for "complete" solutions rather than pragmatic ones
- No validation of actual data patterns before designing schema

### 4.2 Secondary Cause: Concept Conflation

"Segment" tried to serve two purposes:
1. **Sport modality container** — Strength vs running vs rowing
2. **Training phase container** — Warmup vs main work vs accessory

These are orthogonal. A running workout has warmup blocks. A strength workout has conditioning blocks. By merging them, we couldn't express either cleanly.

### 4.3 Tertiary Cause: Data Source Confusion

We designed sport-specific tables for *manual entry* when sport-specific data actually comes from *devices*. Nobody types in their swimming SWOLF; it comes from a Garmin FIT file with a device-native schema.

**The correct split:**
- Workout log = human-authored, universal, simple
- Device telemetry = device-authored, device-typed, raw

### 4.4 Process Failures

1. **No prototype validation** — Schema was designed in discussion, not tested against real logging sessions
2. **Multi-model consensus ≠ correctness** — Three AIs agreeing doesn't validate against reality
3. **"v2" naming accepted** — Should have insisted on clean names before shipping

---

## 5. Lessons Learned

### 5.1 Design Principles

| Lesson | Description | Application |
|--------|-------------|-------------|
| **LL-001** | Build for the 95% case | Don't add complexity for hypothetical edge cases. Add it when the edge case actually appears. |
| **LL-002** | Keep orthogonal concepts separate | If two things vary independently (sport vs training phase), they need separate axes in your model. |
| **LL-003** | Data sources dictate schema | Tables should reflect where data comes from (manual entry, device API, file import), not what the data describes. |
| **LL-004** | Friction at capture time kills adoption | Users will abandon systems that interrupt their flow. Defer optional data capture. |
| **LL-005** | OOP patterns don't need ORM patterns | Three objects (workout, block, set) map cleanly to three tables. Discriminator inheritance adds complexity without benefit in SQL. |

### 5.2 Process Principles

| Lesson | Description | Application |
|--------|-------------|-------------|
| **LL-006** | Validate with real data before shipping | Log 10 real workouts against a prototype schema before committing to production. |
| **LL-007** | AI consensus requires reality check | Multiple AIs agreeing means the design is internally consistent, not that it matches real-world use patterns. |
| **LL-008** | Never ship temporary names | "v2" prefixes are not a versioning strategy. Name things correctly the first time or don't ship. |
| **LL-009** | Empty tables are signal | If a table has zero rows after a week of use, the schema is wrong. |
| **LL-010** | Rollback speed matters | Design migrations to be reversible. Take backups. Test rollback procedures. |

### 5.3 Domain-Specific Lessons

| Lesson | Description | Application |
|--------|-------------|-------------|
| **LL-011** | Device data ≠ sport-typed data | Fitness device telemetry should be schematized by device/protocol (FIT, Polar API), not by sport. |
| **LL-012** | Workout logging should be dumb | The workout log captures what the human did. Analytics and device integration are separate concerns. |
| **LL-013** | Deviation tracking is analytics, not logging | Compare plan vs execution after the fact, don't force explanations during logging. |

---

## 6. Recommendations

### 6.1 Immediate (Completed)

- [x] Create ADR-007 with simplified schema
- [x] Create migration plan with verification gates
- [x] Preserve ADR-006 with "Superseded" status and failure analysis
- [x] Document lessons learned (this AALL)

### 6.2 Short-term (Migration Phase)

- [ ] Execute schema migration (rename tables, update views)
- [ ] Deprecate unused tables (rename to `_deprecated_*`, don't drop)
- [ ] Update all MCPs to use new table names
- [ ] Verify end-to-end workout logging works

### 6.3 Long-term (Future Architecture)

- [ ] Implement ADR-008 for device telemetry (separate from workout log)
- [ ] Establish prototype validation practice for future schema changes
- [ ] Create "schema change checklist" including real-data validation step

---

## 7. What Went Right

Not everything failed. Documenting successes prevents over-correction.

1. **Core data model was sound** — The workout → segment → sets hierarchy was correct; we just over-complicated the middle layer.

2. **Quick detection** — Problems were identified within one week, before significant data accumulated in the wrong schema.

3. **Multi-model consultation was valuable** — ChatGPT Health's device telemetry guidance (during rollback discussion) was excellent. The failure was in the original question framing, not the consultation process.

4. **ADR discipline paid off** — Having a written decision record made it easy to analyze what went wrong and communicate the rollback rationale.

5. **Data preserved** — The actual workout data (workouts, segments, sets) migrates cleanly. Only the empty sport-specific tables are waste.

---

## 8. Attachments

- **ADR-006:** `/docs/adr/006-unified-workout-schema.md` — Original decision record (now superseded)
- **ADR-007:** `/docs/adr/007-simplified-workout-schema.md` — Replacement decision record
- **ADR-008:** `/docs/adr/008-device-telemetry-layer.md` — Device telemetry architecture (proposed)
- **Migration Plan:** `/migrations/SCHEMA_SIMPLIFICATION_INSTRUCTIONS.md`

---

## 9. Approval

| Role | Name | Date |
|------|------|------|
| Athlete/Developer | Brock Webb | 2026-01-20 |
| AI Assistant | Claude | 2026-01-20 |

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-20 | Claude | Initial AALL document |
