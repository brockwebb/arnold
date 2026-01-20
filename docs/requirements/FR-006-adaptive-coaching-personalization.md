# FR-006: Adaptive Coaching Personalization

## Metadata
- **Priority**: High
- **Status**: Proposed
- **Created**: 2026-01-19
- **Updated**: 2026-01-19
- **Dependencies**: [FR-001 Athlete Profile]

## Description

The coaching intelligence layer must adapt its programming approach, communication style, and decision-making to the unique needs, preferences, and characteristics of each individual athlete. The system must not default to rigid templates or generic programming patterns when athlete-specific context is available.

### Core Principles

> **"Be like water"** — the coaching style should adapt to the vessel (athlete), not force athletes into a template.

> **"The plan is a hypothesis, not a contract"** — plans provide direction; execution adapts to reality.

## Rationale

1. **Athletes have different needs**: Schedule-rigid athletes benefit from predictable multi-month plans; flexible athletes ("schedule jiu-jitsu") need adaptive weekly adjustments.

2. **Generic AI coaching failure mode**: LLM-based coaches tend to default to pattern-matching and template application rather than context-aware adjustments. This produces suboptimal programming (e.g., stacking deadlifts after a long run without considering posterior chain overlap).

3. **Optimal results require individualization**: Elite coaching adapts methods to the athlete. Leadership adapts style to the team. Arnold must do the same.

4. **Training is a constraint satisfaction problem**: Each week solves for multiple competing constraints — goals, injuries, life events, equipment, time, movement pattern coverage, accumulated fatigue. Sessions are the OUTPUT of satisfying constraints, not fixed templates.

## Hierarchical Planning Model

The system must operate across multiple planning horizons with **increasing specificity as execution approaches**:

### Macro-cycle (Months to Year)
- **Stability**: High — intent and direction are stable
- **Content**: Goal targets, competition dates, major periodization phases
- **Adjustment frequency**: Quarterly or on major life/injury events

### Meso-cycle / Training Block (3-6 weeks)
- **Stability**: Medium — block intent is stable, session types may shift
- **Content**: Volume/intensity targets, movement pattern emphasis, progression model
- **Adjustment frequency**: At block boundaries or on significant constraint changes

### Micro-cycle / Weekly (7 days)
- **Stability**: Lower — refined based on accumulated load and recovery trends
- **Content**: Specific session assignments, rest day placement, modality distribution
- **Adjustment frequency**: Weekly planning session, adjusted as life events arise

### Daily Execution
- **Stability**: Lowest — adapts to incoming data
- **Content**: Confirmed session details, load/rep prescriptions, exercise selection
- **Adjustment frequency**: Real-time based on readiness, feedback, or constraint changes

### Key Insight
Templated macro/meso structure is critical for progressive overload and periodization. But the closer to execution, the more the system must optimize against current constraints rather than follow a predetermined script.

## Trend-Weighted Load Context

Session planning must consider **load trends**, not just the previous day:

### Temporal Weighting
- **Acute window (7 days)**: High weight — immediate fatigue and stimulus
- **Chronic window (28 days)**: Context for work capacity and baseline
- **ACWR ratio**: Injury risk indicator; informs intensity decisions

### What This Means
- A single hard session yesterday matters, but so does cumulative load over the week
- "Yesterday was rest" doesn't mean today should be max effort if the prior 6 days were brutal
- Trends inform whether athlete is in accumulation, realization, or recovery phase

### Data Inputs
- Recent workout volume (sets, tonnage, duration)
- Movement pattern frequency (gap detection)
- Biometric trends (HRV, sleep, resting HR) when available
- Subjective feedback (RPE, fatigue, soreness)

## Constraint-Based Optimization

Each planning cycle (weekly, daily) is an **optimization problem** with constraints:

### Hard Constraints (Must Satisfy)
- Active injuries and movement restrictions
- Non-negotiable schedule commitments (travel, work, life events)
- Equipment availability
- Recovery minimums (e.g., no back-to-back max effort days)

### Soft Constraints (Optimize For)
- Goal progression (deadlift strength, endurance base, skill acquisition)
- Movement pattern coverage (avoid gaps > 7-10 days)
- Athlete preferences (Sunday long runs, variety vs. consistency)
- Load management (ACWR targets, fatigue accumulation)

### Constraint Hierarchy
When constraints conflict, resolve in order:
1. Safety (injury, medical)
2. Recovery (overtraining prevention)
3. Life (schedule realities)
4. Goals (progressive overload toward targets)
5. Preferences (athlete comfort and buy-in)

## Real-Time Re-Optimization

New information must **propagate forward** and may require adjusting remaining sessions:

### Trigger Events
- Workout logged (actual vs. planned may differ)
- Injury reported (hard constraint change)
- Life event inserted (schedule constraint)
- Biometric alert (recovery signal)
- Athlete feedback ("that was harder than expected")

### Response
- Evaluate remaining week against updated constraint set
- Identify conflicts or suboptimal sequences
- Propose adjustments (not silently change)
- Document rationale for changes

### Injury as Hard Reset
Injury is not a minor modification — it fundamentally changes the constraint set:
- All planned sessions require re-evaluation against new movement restrictions
- May require block/phase adjustment, not just session swaps
- Conservative re-entry protocol supersedes progression goals

## Functional Requirements

### FR-006.1: Athlete Preference Storage
The system SHALL store and retrieve athlete-specific coaching preferences including:
- Programming flexibility preference (rigid schedule vs. adaptive)
- Preferred session structures and training days by modality
- Communication style preferences
- Training philosophy alignment

### FR-006.2: Hierarchical Plan Management
The system SHALL maintain plans at multiple horizons:
- Block-level intent (stable)
- Weekly session assignments (refined weekly)
- Daily execution details (adjusted as needed)
- Clear distinction between "intent" and "prescription"

### FR-006.3: Trend-Weighted Context Loading
When creating or adjusting plans, the system SHALL consider:
- Acute load (7-day rolling)
- Chronic load (28-day rolling)
- Movement pattern recency (days since last stimulus per pattern)
- ACWR and injury risk indicators
- Available biometric trends

### FR-006.4: Constraint-Based Session Generation
The system SHALL treat session planning as constraint satisfaction:
- Enumerate active constraints (injuries, schedule, equipment, goals)
- Generate sessions that satisfy hard constraints
- Optimize across soft constraints with appropriate weighting
- Document constraint violations or trade-offs when unavoidable

### FR-006.5: Forward Propagation on New Data
When new data is logged (workout, injury, feedback), the system SHALL:
- Evaluate impact on remaining planned sessions
- Flag conflicts or suboptimal sequences
- Propose adjustments with rationale
- Allow athlete override with documented deviation

### FR-006.6: Anti-Pattern Detection
The system SHALL flag and avoid common coaching anti-patterns:
- Template application without context consideration
- Stacking overlapping movement patterns without justification
- Ignoring accumulated load trends (planning in isolation)
- Ignoring athlete-stated preferences
- Defaulting to "rest day" for trained athletes after moderate efforts
- Failing to re-evaluate after constraint changes

## Acceptance Criteria

- [ ] Athlete preferences stored and surfaced in planning context
- [ ] Block intent persists while weekly details can be refined
- [ ] Planning functions load 7-day and 28-day load context
- [ ] Movement pattern gaps detected and surfaced in planning
- [ ] Injury creates re-evaluation trigger for all forward plans
- [ ] System can justify programming decisions when challenged
- [ ] Logged workout triggers forward-plan review
- [ ] Anti-patterns documented and checked during generation

## Evidence Base

| Concept | Literature |
|---------|-----------|
| Block periodization with flexible execution | Issurin (2010), Bompa & Haff |
| Auto-regulation / RPE-based adjustment | Helms, Zourdos — MASS research review |
| ACWR and rolling load windows | Gabbett (2016), Hulin et al. |
| Nonlinear periodization for trained athletes | Rhea et al. meta-analysis |
| Constraint-led approach | Davids, Newell (motor learning applied to S&C) |

## Examples

### Anti-Pattern: Template Without Context
```
Athlete: Ran 10 miles Sunday
Coach: Monday — Deadlift progression day

Problem: Stacks posterior chain stress without separation
```

### Correct: Context-Aware Sequencing
```
Athlete: Ran 10 miles Sunday  
Coach: Monday — Upper Push/Pull (natural separation)
       Tuesday — Deadlift progression (48hr recovery from run)
```

### Real-Time Re-Optimization
```
Tuesday AM: Athlete reports "slept terribly, HRV tanked"
Coach: Today was planned as heavy DL. Options:
       (a) Shift to technique work at 60%
       (b) Swap with Thursday's lighter session
       (c) Convert to mobility/recovery day
       Recommend (b) — preserves weekly volume, respects recovery signal
```

### Injury Constraint Reset
```
Wednesday: Athlete reports knee pain during squats
Coach: 
  - Flag: Hard constraint change
  - Evaluate all forward sessions for squat/lunge/knee-flexion movements
  - Propose modifications or substitutions
  - Note: This may affect block-level programming, not just this week
```

## Open Questions

- [ ] Should preferences have expiration or staleness indicators?
- [ ] How to handle conflicting preferences (athlete says X, data suggests Y)?
- [ ] What's the minimum preference set needed for effective personalization?
- [ ] How to represent constraint priorities in a machine-readable way?
- [ ] Should re-optimization be automatic or always require athlete confirmation?

## Related Documents
- [FR-001: Athlete Profile](FR-001-athlete-profile-adr001-compliance.md)
- [TRAINING_METRICS.md](../TRAINING_METRICS.md) — ACWR, load calculations
- Coaching Observation schema in memory-mcp
