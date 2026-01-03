# Arnold Planning System — Design Document

> **Purpose**: Define the planning architecture that transforms goals into executed training, with intelligent feed-forward adaptation.
> **Status**: DRAFT — Ready for review
> **Created**: January 2, 2026
> **Author**: Claude (with Brock's direction)

---

## The Core Principle

**Failing to plan is planning to fail.**

Plans are not suggestions. They are first-class objects in the system — the connective tissue between aspirational goals and daily action. Every training session should trace its lineage to a goal through a chain of planning decisions.

---

## Terminology

To avoid confusion, Arnold uses precise terminology across planning and execution:

### Planning Domain (Theory)

| Term | Scope | Description |
|------|-------|-------------|
| **Goal** | Months-Years | What the athlete is training toward |
| **Macrocycle** | 12-52 weeks | Annual or competition cycle |
| **Mesocycle** (Block) | 3-6 weeks | Training phase with specific adaptation focus |
| **Microcycle** | 1 week | The repeating weekly pattern |
| **Session** | 1 day | The planned workout prescription |
| **Set** | Minutes | The atomic unit of work (exercise + load + reps) |

### Execution Domain (Implementation)

| Term | Scope | Description |
|------|-------|-------------|
| **Workout** | 1 day | The executed session (what actually happened) |
| **WorkoutBlock** | Section | Container organizing sets within a workout (warmup, main, finisher) |
| **Set** | Minutes | The atomic unit — same as planning domain |

### The Bridge

```
PLANNING prescribes → EXECUTION organizes → SET is shared

Session ──executes as──▶ Workout
                              │
                              ├── WorkoutBlock: "Warmup"
                              │     └── Set, Set, Set
                              ├── WorkoutBlock: "Main Work"  
                              │     └── Set, Set, Set, Set
                              └── WorkoutBlock: "Finisher"
                                    └── Set, Set
```

**Key insight**: `Block` (mesocycle) and `WorkoutBlock` (session organizer) are different concepts at different scales. Context disambiguates, but we remain explicit in code and data models.

---

## The Coaching Team

Arnold is not a single coach — it's a **team of specialized agents** orchestrated to serve the whole athlete:

```
                    ┌─────────────────┐
                    │   ORCHESTRATOR  │
                    │   (Arnold Core) │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
   ┌─────────┐         ┌─────────┐         ┌─────────┐
   │  COACH  │         │   DOC   │         │ ANALYST │
   │ (S&C)   │         │(Medical)│         │ (Data)  │
   └────┬────┘         └─────────┘         └─────────┘
        │
        ├── Strength & Conditioning (general)
        ├── Running Coach (ultra, sprint, mid-distance)
        ├── Conditioning Coach (cardio, swimming, cycling, hiking)
        ├── Sports Psychologist (mental training)
        └── PT/Mobility Specialist (injury prevention, rehab)
```

**Future specialists** (as system evolves):
- Nutrition Coach
- Sleep/Recovery Specialist
- Sport-specific coaches (martial arts, climbing, etc.)

**Orchestration principle**: The right specialist engages based on context. An ultra runner needs different running expertise than a 5K specialist. A desk worker needs different mobility work than a yoga practitioner. **The profile drives which specialists engage and how.**

---

## Personalization Philosophy

> *"Generalized medicine is a rough tuning controller. Individual data enables fine control."*

Arnold rejects one-size-fits-all programming. Every athlete is a **sample size of one** with unique:
- Genetics and physiology
- Training history and adaptation patterns
- Life constraints and recovery capacity
- Goals and preferences
- Injury history and movement limitations

**The profile is the source of truth.** All planning decisions flow from:
1. Who is this athlete? (demographics, history, phenotype)
2. What are their goals? (short and long term)
3. What constraints exist? (injuries, equipment, schedule)
4. How do they respond? (learned from execution data)

Population-based recommendations are **priors**. Individual data updates toward **personal posteriors**. With enough history, the athlete's own patterns dominate.

---

## The Planning Hierarchy

Training operates at multiple time scales, each with distinct purposes:

```
GOAL (months-years)
  │
  ├── What the athlete is training toward
  │
  ▼
MACROCYCLE (12-52 weeks)
  │
  ├── The annual or major competition cycle
  │
  ▼
MESOCYCLE / BLOCK (3-6 weeks)
  │
  ├── Training blocks with specific adaptations
  │   (Accumulation → Transmutation → Realization)
  │
  ▼
MICROCYCLE (1 week)
  │
  ├── The repeating weekly pattern
  │   (Push/Pull/Legs, Upper/Lower, etc.)
  │
  ▼
SESSION (1 day)
  │
  ├── The individual workout prescription
  │
  ▼
SET (atomic)
  │
  └── Exercise + Load + Reps + Execution parameters
```

Each layer answers different questions:

| Layer | Time Scale | Key Question |
|-------|------------|--------------|
| Goal | Months-Years | What am I training for? |
| Macrocycle | 12-52 weeks | How does the year flow toward peak performance? |
| Mesocycle | 3-6 weeks | What adaptation am I pursuing right now? |
| Microcycle | 1 week | How do I distribute stress and recovery? |
| Session | 1 day | What specific work am I doing today? |
| Set | Minutes | How am I executing this movement? |

---

## Workout Construction

When a Session (plan) becomes a Workout (execution), sets are organized into **WorkoutBlocks**:

```
Workout
├── WorkoutBlock: "Warmup"
│     ├── Set: Arm Circles × 10
│     ├── Set: Hip Circles × 10
│     └── Set: Goblet Squat × 8 @ 35lb
│
├── WorkoutBlock: "Main Work" [uses Protocol: "5×5"]
│     ├── Set: Deadlift × 5 @ 275lb
│     ├── Set: Deadlift × 5 @ 275lb
│     ├── Set: Deadlift × 5 @ 275lb
│     ├── Set: Deadlift × 5 @ 275lb
│     └── Set: Deadlift × 5 @ 275lb
│
├── WorkoutBlock: "Accessory"
│     ├── Set: RDL × 8 @ 185lb
│     ├── Set: RDL × 8 @ 185lb
│     └── Set: RDL × 8 @ 185lb
│
└── WorkoutBlock: "Finisher" [uses Protocol: "AMRAP 5min"]
      ├── Set: KB Swing × 10 @ 53lb
      └── Set: Ab Rollout × 10
```

**WorkoutBlock** is an organizational construct that:
- Groups related sets
- Can reference a Protocol (5×5, AMRAP, circuit, etc.)
- Defines rest periods and transitions
- Enables structured logging and analysis

**Planning prescribes the sets. Construction organizes them.**

---

## Planning Objects

### Goal (Exists)
```
Goal
├── name: "Primary strength goal"
├── target_date: date
├── priority: high | medium | low | meta
├── required_modalities: [Modality references]
└── status: active | achieved | deferred | abandoned
```

Goals are the **why**. They don't change frequently. They anchor everything below.

### Macrocycle (NEW)
```
Macrocycle
├── id: UUID
├── name: "Annual training cycle"
├── goal_ids: [goal1, goal2]
├── start_date: date
├── end_date: date
├── phases: [
│     { name: "Base Building", weeks: 12 },
│     { name: "Strength Focus", weeks: 16 },
│     { name: "Competition Prep", weeks: 8 },
│     { name: "Peak & Taper", weeks: 4 }
│   ]
├── key_dates: [
│     { date: date, event: "Competition name" }
│   ]
└── status: active | completed | adjusted
```

Macrocycles are the **annual roadmap**. They sequence mesocycles and account for life events, competitions, and recovery periods.

### Mesocycle / Block (Exists, needs enhancement)
```
Block
├── id: UUID
├── macrocycle_id: FK (NEW)
├── name: "Accumulation"
├── block_type: accumulation | transmutation | realization | deload
├── week_count: integer
├── start_date: date
├── end_date: date
├── intent: "Build work capacity, establish movement patterns"
├── volume_target: low | moderate | moderate-high | high
├── intensity_target: low | moderate | high | max
├── serves: [goal_ids]
├── microcycle_template_id: FK (NEW)
└── status: active | completed | adjusted
```

Blocks are the **adaptation focus**. Each block pursues specific physiological adaptations that ladder toward goals.

### Microcycle / Week Template (NEW)
```
MicrocycleTemplate
├── id: UUID
├── name: "4-Day Upper/Lower Split"
├── days: [
│     { day: 1, focus: "Upper Push", required_patterns: [...] },
│     { day: 2, focus: "Lower", required_patterns: [...] },
│     { day: 3, focus: "Rest" },
│     { day: 4, focus: "Upper Pull", required_patterns: [...] },
│     { day: 5, focus: "Lower + Conditioning", required_patterns: [...] },
│     { day: 6, focus: "Long Run", required_patterns: [...] },
│     { day: 7, focus: "Rest" }
│   ]
└── notes: "Designed for concurrent strength + endurance goals"
```

```
MicrocycleInstance (NEW)
├── id: UUID
├── template_id: FK
├── block_id: FK
├── week_number: integer
├── start_date: date
├── adjustments: "Notes on modifications from template"
├── planned_sessions: [session_ids]
└── status: planned | in_progress | completed
```

Microcycles are the **weekly rhythm**. They distribute training stress across the week and ensure pattern coverage.

### Session / PlannedWorkout (Exists, needs lifecycle)
```
PlannedWorkout
├── id: UUID
├── microcycle_id: FK (NEW)
├── date: date
├── goal: "Session objective"
├── focus: ["strength", "conditioning", etc.]
├── planned_blocks: [PlannedBlock references]
├── estimated_duration_minutes: integer
├── status: draft | confirmed | executed | skipped
├── confirmed_at: datetime (NEW)
├── executed_workout_id: FK (NEW - links to actual Workout)
└── deviation_summary: "Post-execution notes" (NEW)
```

Sessions are the **daily prescription**. They specify exactly what to do.

### Executed Workout (Exists)
```
Workout
├── id: UUID
├── planned_workout_id: FK (NEW - back-link)
├── date: date
├── blocks: [WorkoutBlock references]
├── deviations: [Deviation records]
├── athlete_feedback: "Subjective report" (NEW)
└── coaching_notes: "Coach observations" (NEW)
```

Executed workouts are the **reality**. They capture what actually happened.

---

## The Planning Pipeline

Plans flow through a defined lifecycle:

```
┌─────────┐     ┌───────────┐     ┌──────────┐     ┌──────────┐
│  DRAFT  │ ──▶ │ CONFIRMED │ ──▶ │ EXECUTED │ ──▶ │ REVIEWED │
└─────────┘     └───────────┘     └──────────┘     └──────────┘
     │                │                 │                │
     ▼                ▼                 ▼                ▼
  Created         Locked in        Completed        Informs
  by coach        for athlete      with deltas      future plans
```

### Stage: DRAFT
- Plan exists but is not committed
- Can be freely modified
- Not visible in "upcoming" views by default
- **Trigger to advance**: Coach and athlete agree on the plan

### Stage: CONFIRMED  
- Plan is locked in and committed
- Athlete knows what's coming
- Visible in briefings and reminders
- **Trigger to advance**: Workout date arrives and work begins

### Stage: EXECUTED
- Work is done (fully or partially)
- Deviations are captured
- Links to actual Workout node
- **Trigger to advance**: Post-workout reflection complete

### Stage: REVIEWED
- Coaching observations extracted
- Feed-forward adjustments identified
- Informs future planning
- **Trigger**: Automatic after execution, or explicit coach review

---

## Feed-Forward Mechanisms

The power of the system is **closed-loop adaptation**. Execution data modifies future plans.

### Automatic Adjustments

| Signal | Detection | Response |
|--------|-----------|----------|
| High fatigue | RPE consistently above prescribed | Reduce next session volume 10-20% |
| Missed reps | Actual reps < prescribed reps | Hold weight, don't progress |
| Pain reported | Deviation reason = "pain" | Flag exercise, suggest substitution |
| Pattern gap | >14 days since pattern trained | Auto-incorporate in next session |
| Overreaching | ACWR > 1.5 | Insert recovery day |
| Undertraining | ACWR < 0.8 for 2+ weeks | Increase stimulus |

### Manual Adjustments

Coach can adjust future plans based on:
- Athlete feedback ("I'm feeling beat up")
- Life events ("Travel next week")
- Goal changes ("Race moved up")
- Injury status changes

### Adjustment Propagation

When a plan is adjusted, the system must decide scope:
- **Session-only**: Just modify tomorrow
- **Week-cascade**: Modify remaining week
- **Block-cascade**: Modify remaining block
- **Replan**: Trigger full replanning from current state

Default: Minimal adjustment. Only cascade when explicitly needed.

---

## Enforcement Points

**When must planning happen?**

### Rule 1: No Training Without a Plan
Every executed workout SHOULD link to a PlannedWorkout. Ad-hoc workouts are allowed but flagged for review.

```
IF logging workout AND no PlannedWorkout exists for date:
  → Create PlannedWorkout retroactively (status: executed)
  → Flag as "unplanned" for coaching review
```

### Rule 2: Plans Must Be Persisted Before Moving On
When coach and athlete agree on a training plan, it MUST be saved before the conversation ends.

```
IF planning discussion concludes AND plans discussed but not saved:
  → Coach MUST call create_workout_plan before proceeding
  → Coach MUST NOT say "the plan is..." without persisting it
```

### Rule 3: Blocks Must Have Sessions
A training block without planned sessions is incomplete.

```
IF Block.status = active AND PlannedWorkouts for block < expected:
  → Surface in coach briefing as "incomplete planning"
  → Prompt: "Week 2 has no planned sessions"
```

### Rule 4: Weekly Planning Checkpoint
At minimum, plans should exist for the upcoming 7 days.

```
IF days_with_plans(next_7_days) < expected_training_days:
  → Surface in coach briefing
  → Prompt: "Only 2 of 4 training days planned for next week"
```

---

## Planning Horizons

Different athletes need different planning depths based on experience and schedule stability:

| Horizon | When to Use | Planning Depth |
|---------|-------------|----------------|
| **Reactive** | Beginner, chaotic schedule | 1-3 days ahead |
| **Weekly** | Intermediate, stable schedule | 7 days ahead |
| **Block** | Serious athlete, periodized | Full mesocycle (3-6 weeks) |
| **Annual** | Competitor, peak events | Full macrocycle (52 weeks) |

**Minimum Viable Planning** (all athletes):
- Always: Next session planned and confirmed
- Preferred: Full week planned
- Ideal: Full block sketched, current week detailed

The athlete's profile determines default horizon. Can be adjusted based on life circumstances.

---

## Tools Required

### Existing Tools (Keep)
- `create_workout_plan` — Create single session
- `confirm_plan` — Lock in a plan
- `complete_as_written` — Mark done without deviations  
- `complete_with_deviations` — Mark done with changes
- `skip_workout` — Mark as skipped
- `get_plan_for_date` — Retrieve single day
- `get_coach_briefing` — Current context

### New Tools Needed

#### `create_week_plan`
Create a full microcycle from template or custom spec.
```
Input: week_start_date, microcycle_template_id OR custom_days[]
Output: 7 PlannedWorkout drafts
```

#### `create_block_plan`
Sketch out a full mesocycle.
```
Input: block_id, weekly_pattern, progression_scheme
Output: Block with linked MicrocycleInstances and PlannedWorkouts (draft)
```

#### `get_planning_status`
Dashboard of planning completeness.
```
Output: {
  next_7_days: { planned: N, expected: N, gaps: [] },
  current_block: { weeks_planned: N, weeks_total: N },
  pattern_coverage: { last_14_days: {...}, gaps: [...] },
  flagged_items: [...]
}
```

#### `adjust_plan`
Modify future plan with reason tracking.
```
Input: plan_id, adjustments, reason, cascade_scope
Output: Modified plan(s), adjustment logged
```

#### `get_upcoming_plans`
Retrieve the planning queue.
```
Input: days_ahead (default 14)
Output: List of PlannedWorkouts with status
```

---

## Data Model Changes

### New Nodes
- `Macrocycle` — Annual/competition cycle
- `MicrocycleTemplate` — Reusable weekly patterns  
- `MicrocycleInstance` — Specific week within a block
- `PlanAdjustment` — Audit log of plan changes

### New Relationships
- `(Macrocycle)-[:CONTAINS_BLOCK]->(Block)`
- `(Block)-[:HAS_WEEK]->(MicrocycleInstance)`
- `(MicrocycleInstance)-[:HAS_SESSION]->(PlannedWorkout)`
- `(PlannedWorkout)-[:EXECUTED_AS]->(Workout)`
- `(PlanAdjustment)-[:MODIFIED]->(PlannedWorkout)`

### New Properties
- `PlannedWorkout.microcycle_id` — FK to week
- `PlannedWorkout.deviation_summary` — Post-execution notes
- `Workout.planned_workout_id` — Back-link to plan
- `Workout.athlete_feedback` — Subjective report
- `Block.microcycle_template_id` — Default weekly pattern

---

## Implementation Priority

### Phase 1: Enforce Persistence (Immediate)
- [ ] Coach behavioral rule: Always persist discussed plans
- [ ] Add `get_upcoming_plans` tool
- [ ] Add `get_planning_status` tool
- [ ] Surface planning gaps in coach briefing

### Phase 2: Weekly Planning (Weeks 1-2)
- [ ] Create `MicrocycleTemplate` node type
- [ ] Create `create_week_plan` tool
- [ ] Build 2-3 templates for common training splits

### Phase 3: Block Planning (Month 1)
- [ ] Link Blocks to MicrocycleInstances
- [ ] Create `create_block_plan` tool
- [ ] Implement progression schemes (linear, wave, etc.)

### Phase 4: Feed-Forward (Month 2)
- [ ] Deviation analysis pipeline
- [ ] Automatic adjustment suggestions
- [ ] `adjust_plan` with cascade logic

### Phase 5: Annual Planning (Quarter 2)
- [ ] Macrocycle node and tools
- [ ] Competition/event integration
- [ ] Long-range periodization

---

## Open Questions

1. **How rigid should templates be?** 
   - Fully prescribed (every set defined) vs. flexible (just focus areas)?
   - Suggestion: Templates define focus, coach fills details based on context

2. **What's the minimum planning horizon we enforce?**
   - Suggestion: 3 days mandatory, 7 days recommended, block sketched

3. **How do we handle spontaneous workouts?**
   - Allow but flag? Require retroactive planning? 
   - Suggestion: Allow, auto-create plan, flag for review

4. **Who owns plan modification — coach or athlete?**
   - Suggestion: Coach proposes, athlete confirms. Emergency self-service allowed.

5. **How granular should feed-forward be?**
   - Every session? Weekly rollup? Block summary?
   - Suggestion: Start with block-level, add granularity as patterns emerge

---

## Closing Thought

> "Plans are worthless, but planning is everything." — Eisenhower

The value isn't in the static plan. It's in the **thinking** that produces it, the **commitment** that confirms it, and the **learning** that refines it.

Arnold's job is to make planning effortless, adaptation automatic, and progress visible. The athlete's job is to show up and do the work.

Let's build this.

---

## References

### Periodization Definitions

**No formal ontology or ISO standard exists for periodization terminology.** The field developed organically from Soviet sports science (Matveyev, 1960s) and was adapted for Western audiences by Bompa. Standardization occurs through professional certification bodies rather than formal ontological work.

**Arnold adopts NSCA definitions as the practical standard** (from *Essentials of Strength Training and Conditioning*, Chapter 21/22):

| Term | Duration | Definition |
|------|----------|------------|
| **Macrocycle** | Several months to 1 year | The overall training period; long-range planning toward a goal |
| **Mesocycle** | 2-6 weeks (commonly 4) | A training block targeting specific adaptations; contains 2+ microcycles |
| **Microcycle** | Several days to 2 weeks (typically 1 week) | The "building blocks" forming mesocycles; organizes daily sessions |

**Optimal mesocycle duration**: Research suggests **4±2 weeks** provides the optimal timeframe for physiological adaptation (Plisk & Stone, 2003).

**Note on terminology**: The Brookbush Institute's systematic review suggests these classifications "may not accurately reflect the most effective organizational structures" and recommends simpler terminology where practical: **Phase** (for mesocycle), **Week** (for microcycle). Arnold uses both traditional and simplified terminology based on context.

### Primary Sources

1. **NSCA.** (2016). *Essentials of Strength Training and Conditioning* (4th ed.). Champaign, IL: Human Kinetics. Chapter 21: Periodization. — **The practical standard for US strength & conditioning certification (CSCS exam).**

2. **Matveyev, L.P.** (1977). *Fundamentals of Sports Training*. Moscow: Progress Publishers. — The original periodization text by the founder of modern periodization theory.

3. **Bompa, T.O. & Haff, G.G.** (2009). *Periodization: Theory and Methodology of Training* (5th ed.). Champaign, IL: Human Kinetics. — The foundational Western text, translated into 19 languages, used in 180+ countries.

4. **Bompa, T.O. & Buzzichelli, C.A.** (2018). *Periodization: Theory and Methodology of Training* (6th ed.). Champaign, IL: Human Kinetics. — Current edition with updated research.

### Peer-Reviewed Literature

5. **Plisk, S.S. & Stone, M.H.** (2003). Periodization strategies. *Strength and Conditioning Journal*, 25(6), 19-37. — Establishes 4±2 week mesocycle as optimal adaptation timeframe.

6. **Lorenz, D. & Morrison, S.** (2015). Current concepts in periodization of strength and conditioning for the sports physical therapist. *International Journal of Sports Physical Therapy*, 10(6), 734-747. PMC4637911. — Clinical application of periodization principles.

7. **Issurin, V.B.** (2010). New horizons for the methodology and physiology of training periodization. *Sports Medicine*, 40(3), 189-206. — Block periodization taxonomy: Accumulation → Transmutation → Realization.

8. **Williams, T.D., et al.** (2017). The science and practice of periodization: A brief review. *Strength and Conditioning Journal*, 39(1), 72-79. — Meta-analysis confirming 4±2 week mesocycle convention.

### Theoretical Foundations

9. **Selye, H.** (1956). *The Stress of Life*. New York: McGraw-Hill. — General Adaptation Syndrome (GAS), the physiological basis for periodization.

10. **Verkhoshansky, Y.V.** (1985). *Programming and Organization of Training*. Moscow: Fizkultura i Sport. — Conjugate/block periodization methodology.

### Practical Application

11. **Set For Set.** (2021). "Macrocycle, Mesocycle, and Microcycle in Periodization Training Explained." https://www.setforset.com/blogs/news/macrocycle-mesocycle-microcycle-explained — Accessible practitioner guide with examples.

### Cross-Reference

See also: `/docs/TRAINING_METRICS.md` for evidence-based workload metrics (ACWR, Monotony, Strain) with 17 citations on training load management.
