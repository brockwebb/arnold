# Arnold Functional Requirements

> **Purpose**: Define what the system must do, with traceable IDs, priorities, and acceptance criteria.
> **Governance**: New requirements proposed as drafts → reviewed → approved before implementation.

---

## Requirements by Domain

### Athlete Profile & Configuration
| ID | Title | Priority | Status |
|----|-------|----------|--------|
| [FR-001](FR-001-athlete-profile-adr001-compliance.md) | Athlete Profile ADR-001 Compliance | High | Proposed |
| [FR-002](FR-002-sensor-hierarchy.md) | Sensor Hierarchy & Preferences | High | Proposed |

### Heart Rate & Recovery Analytics
| ID | Title | Priority | Status |
|----|-------|----------|--------|
| [FR-003](FR-003-hr-session-workout-linking.md) | HR Session to Workout Linking | High | Proposed |
| [FR-004](FR-004-recovery-interval-detection.md) | Recovery Interval Detection (HRR) | Medium | Proposed |

### Exercise Resolution (Backlog)
| ID | Title | Priority | Status |
|----|-------|----------|--------|
| [FR-005](FR-005-exercise-alias-system.md) | Exercise Alias System | High | Proposed |

---

## Status Definitions

| Status | Meaning |
|--------|---------|
| **Proposed** | Documented, awaiting review |
| **Approved** | Reviewed, ready for implementation |
| **In Progress** | Currently being implemented |
| **Implemented** | Code complete, needs verification |
| **Verified** | Tested and working |
| **Deferred** | Postponed to future phase |

---

## Requirement Template

```markdown
# FR-XXX: [Title]

## Metadata
- **Priority**: High / Medium / Low
- **Status**: Proposed
- **Created**: YYYY-MM-DD
- **Dependencies**: [list of FR-IDs or ADRs]

## Description
[What the system must do]

## Rationale
[Why this is needed]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Technical Notes
[Implementation guidance, not prescription]

## Open Questions
- [ ] Question 1
```

---

## Related Documents
- [ADR-001: Data Layer Separation](../adr/001-data-layer-separation.md)
- [ADR-002: Strength Workout Migration](../adr/002-strength-workout-migration.md)
- [Architecture Overview](../architecture/README.md)
