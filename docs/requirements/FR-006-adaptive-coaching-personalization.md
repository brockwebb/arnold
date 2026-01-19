# FR-006: Adaptive Coaching Personalization

## Metadata
- **Priority**: High
- **Status**: Proposed
- **Created**: 2026-01-19
- **Dependencies**: [FR-001 Athlete Profile]

## Description

The coaching intelligence layer must adapt its programming approach, communication style, and decision-making to the unique needs, preferences, and characteristics of each individual athlete. The system must not default to rigid templates or generic programming patterns when athlete-specific context is available.

### Core Principle
> "Be like water" — the coaching style should adapt to the vessel (athlete), not force athletes into a template.

## Rationale

1. **Athletes have different needs**: Schedule-rigid athletes benefit from predictable multi-month plans; flexible athletes ("schedule jiu-jitsu") need adaptive weekly adjustments.

2. **Generic AI coaching failure mode**: LLM-based coaches tend to default to pattern-matching and template application rather than context-aware adjustments. This produces suboptimal programming (e.g., stacking deadlifts after a long run without considering posterior chain overlap).

3. **Optimal results require individualization**: Elite coaching adapts methods to the athlete. Leadership adapts style to the team. Arnold must do the same.

## Functional Requirements

### FR-006.1: Athlete Preference Storage
The system SHALL store and retrieve athlete-specific coaching preferences including:
- Programming flexibility preference (rigid schedule vs. adaptive)
- Preferred session structures
- Communication style preferences
- Training philosophy alignment

### FR-006.2: Context-Aware Session Planning
When creating workout plans, the system SHALL:
- Consider the previous day's training stimulus before programming overlapping movement patterns
- Adjust for life events (travel, memorial services, work demands)
- Respect athlete's preferred training days for specific modalities (e.g., "Sunday long runs")
- Not stack movements with high overlap without explicit justification

### FR-006.3: Weekly Adjustment Capability
The system SHALL support weekly plan modifications based on:
- Subjective recovery feedback
- Biometric signals (when available)
- Schedule changes
- Accumulated fatigue indicators
- Athlete requests

### FR-006.4: Coaching Style Adaptation
The intelligence layer SHALL adapt its approach based on athlete profile:
- Training age and experience level per modality
- Self-coaching competency in specific domains
- Preference for explanation depth vs. directive brevity
- Response to different coaching cues

### FR-006.5: Anti-Pattern Detection
The system SHALL flag and avoid common coaching anti-patterns:
- Template application without context consideration
- Stacking overlapping movement patterns on consecutive days without justification
- Ignoring athlete-stated preferences
- Defaulting to "rest day" recommendations for trained athletes after moderate efforts

## Acceptance Criteria

- [ ] Athlete preferences are stored in profile and accessible to coaching intelligence
- [ ] Planning functions check prior day's training before generating sessions
- [ ] Weekly plans can be modified without regenerating entire mesocycle
- [ ] Coaching observations capture and persist athlete-specific patterns
- [ ] System can justify programming decisions when challenged by athlete
- [ ] Anti-patterns are documented and checked during plan generation

## Technical Notes

### Implementation Guidance
1. **Observation System**: Use `arnold-memory:store_observation` with type `preference` to capture coaching style notes
2. **Briefing Context**: `load_briefing` should surface relevant preferences for session context
3. **Plan Validation**: Before confirming plans, validate against known athlete preferences and prior day training

### Data Model Considerations
- Preferences may be stored as CoachingObservation nodes with type="preference"
- May need structured preference schema in athlete profile for machine-readable preferences
- Consider confidence/strength of preference (firm rule vs. soft preference)

## Examples

### Anti-Pattern (What NOT to do)
```
Athlete: Ran 10 miles Sunday
Coach: Monday — Deadlift progression day

Problem: Stacks posterior chain stress without separation
```

### Correct Pattern
```
Athlete: Ran 10 miles Sunday  
Coach: Monday — Upper Push/Pull (natural separation from running stimulus)
       Tuesday — Deadlift progression (48hr recovery from run)
```

### Adaptive Scheduling
```
Athlete: "Wednesday I have a memorial service"
Coach: Adjusts plan, moves rest day to Wednesday, redistributes sessions around it
```

## Open Questions

- [ ] Should preferences have expiration or staleness indicators?
- [ ] How to handle conflicting preferences (athlete says X, data suggests Y)?
- [ ] What's the minimum preference set needed for effective personalization?

## Related Documents
- [FR-001: Athlete Profile](FR-001-athlete-profile-adr001-compliance.md)
- Coaching Observation schema in memory-mcp
