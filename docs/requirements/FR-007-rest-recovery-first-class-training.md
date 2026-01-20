# FR-007: Rest and Recovery as First-Class Training

## Metadata
- **Priority**: Medium
- **Status**: Proposed
- **Created**: 2026-01-19
- **Dependencies**: [FR-006 Adaptive Coaching Personalization]

## Description

Rest and recovery days must be treated as active training components, not absence of training. The system should support documentation of rest days, check in with athletes about recovery status, and recognize that mental conditioning, proper rest, and light restorative movement all serve long-term health goals.

### Core Principles

> **"Rest is training"** — Recovery adaptations happen during rest, not during work. Skipping rest undermines the training stimulus.

> **"Know your athlete"** — Rest day check-ins are about understanding athlete state, not compliance enforcement.

> **"Mental conditioning is training"** — Stress management, sleep quality, and psychological recovery are performance variables.

## Rationale

1. **Rest serves goals**: The meta-goal "stay healthy, minimize injury" is actively served by rest days. They are not empty — they're doing work.

2. **Fatigue signals inform planning**: Rest day feedback (how athlete feels, sleep quality, lingering soreness) should influence remaining week and future planning.

3. **Shadow exercise is real**: Some athletes sneak in extra work despite guidance. Coaches must know athlete tendencies and watch for patterns that undermine recovery.

4. **Light movement ≠ breaking rest**: Daily stretching, walking, tai chi, meditation — done without excess — supports circulation and mental health without compromising recovery.

5. **Athlete psychology varies**: Some athletes are schedule-rigid and will follow rest prescriptions exactly. Others will abuse any permission ("hours of tai chi because it was allowed"). Coaching must adapt.

## Functional Requirements

### FR-007.1: Rest Day Documentation
The system SHALL support logging rest days with optional context:
- Subjective fatigue level
- Sleep quality/quantity
- Any lingering soreness or issues
- Mental state / stress indicators
- Light activities performed (if any)

Documentation is **aspirational, not mandatory** — the system invites input without demanding compliance.

### FR-007.2: Rest Day Goal Attribution
When displaying or planning rest days, the system SHALL:
- Associate rest days with the "Stay healthy" meta-goal (or equivalent)
- Not display rest days as empty or goalless
- Recognize rest as serving all active goals through recovery adaptation

### FR-007.3: Recovery Check-In Prompts
The system SHOULD (aspirationally) prompt for rest day feedback:
- Light touch, not interrogation
- "How are you feeling today?" style, not "Did you comply with rest protocol?"
- Use responses to inform forward planning

### FR-007.4: Acceptable Rest Day Activities
The system SHALL maintain guidance on activities compatible with rest/recovery:

**Generally Compatible (if not done to excess):**
- Walking (including dog walks)
- Light stretching / flexibility work
- Meditation / breathwork
- Tai chi / yoga (restorative, not power)
- Foam rolling / self-massage
- Light swimming / floating

**Caution / Know Your Athlete:**
- "Active recovery" sessions (some athletes interpret this as license for real work)
- Any activity lasting > 30-45 minutes
- Anything that elevates HR significantly

**Not Rest:**
- "Easy" runs that somehow become tempo
- "Just a few sets" of strength work
- Competitive anything

### FR-007.5: Shadow Exercise Detection (Aspirational)
The system SHOULD watch for patterns suggesting athletes are not respecting rest:
- Unexpected biometric signals (elevated resting HR, suppressed HRV on rest days)
- Self-reported "light" activities that seem frequent or extensive
- Performance patterns suggesting inadequate recovery
- Direct athlete disclosure (some will confess)

Response is coaching conversation, not punishment — understand WHY and address root cause.

### FR-007.6: Taper Protocol Support
During taper periods (pre-competition), the system SHALL:
- Increase emphasis on rest compliance
- Flag any activities that might compromise taper
- Remind athlete of taper rationale
- Watch extra carefully for shadow exercise tendencies

## Acceptance Criteria

- [ ] Rest days can be logged with optional subjective data
- [ ] Rest days display associated health/recovery goal
- [ ] System can prompt (not demand) rest day check-ins
- [ ] Acceptable rest activities documented and accessible
- [ ] Athlete tendencies (compliant vs. shadow exerciser) can be noted in profile
- [ ] Rest day feedback influences forward planning recommendations

## Examples

### Rest Day Check-In (Light Touch)
```
System: "Wednesday is a rest day. How are you feeling?"
Athlete: "Little tired, slept okay but not great"
System: [Logs observation, notes for Thursday planning consideration]
```

### Rest Day with Goal Attribution
```
Wednesday Jan 21
Session: REST
Goal: Stay Healthy, Minimize Injury
Notes: Memorial service — life comes first. Recovery supports all other goals.
```

### Shadow Exercise Pattern Detection
```
System notices: Athlete reports "light stretching" on every rest day, 
               HRV consistently lower day after rest days than after training days
               
Coaching response: "I'm noticing your HRV doesn't bounce back on rest days 
                   as much as I'd expect. Are the stretching sessions longer 
                   or more intense than intended? Or is something else 
                   affecting recovery?"
```

### Taper Reminder
```
Athlete: "Feeling antsy, might do a short easy run"
System: "You're 5 days out from Hellgate. This is peak taper — the hay is in 
        the barn. A short run won't make you fitter, but it could compromise 
        freshness. Trust the training. Walk Murray instead?"
```

## Open Questions

- [ ] How to balance check-in prompts without being annoying?
- [ ] Should shadow exercise detection be explicit or subtle?
- [ ] How to handle athletes who genuinely need more or less rest than typical?
- [ ] Integration with biometric data for recovery validation?

## Related Documents
- [FR-006: Adaptive Coaching Personalization](FR-006-adaptive-coaching-personalization.md)
- Journal system for subjective data capture
- Biometric integration for recovery signals
