# Arnold Roadmap — Vision & Journey

> **Purpose**: This document tells the story of where Arnold is going and why it matters. For technical architecture details, see ARCHITECTURE.md.

> **Last Updated**: January 5, 2026 (ADR-002 Strength Migration Complete)

---

## The Vision

### What We're Building

Arnold is the first implementation of a radical idea: **personal health sovereignty through data ownership and AI-augmented analysis.**

Today, your health data is scattered across:
- Fitness apps that don't talk to each other
- Medical records you don't control
- Wearables with proprietary algorithms
- Lab results buried in patient portals
- Years of training logs in forgotten spreadsheets

Meanwhile, you get 15 minutes with a doctor twice a year. They see snapshots, not patterns. They know population averages, not your individual response curves.

Arnold changes this.

### The Digital Twin

Imagine a comprehensive model of YOU that:

- **Sees everything** — every workout, every sleep, every heart rate, every lab result, every symptom, connected across time
- **Finds patterns humans miss** — "Your HRV drops 48 hours before you get sick. Your deadlift performance correlates with sleep from two nights ago, not last night."
- **Learns YOUR responses** — not population averages, but how YOUR body responds to training, stress, sleep, nutrition
- **Speaks your language** — translates data into actionable recommendations without requiring a PhD in statistics
- **Stays in YOUR control** — your data, your instance, your choice who sees it

This isn't about replacing doctors or coaches. It's about arriving informed, asking better questions, and detecting patterns that no 15-minute appointment could ever catch.

### Why This Matters

The democratization of elite analysis.

Professional athletes have teams: coaches, nutritionists, sports scientists, medical staff analyzing their data full-time. Regular people have... apps that give badges for step counts.

Arnold bridges this gap. Not by simplifying the analysis, but by making sophisticated analysis accessible. The same pattern detection, the same longitudinal insight, the same evidence-based recommendations — available to anyone willing to track and engage with their own health.

---

## The Journey

### Phase 0: Foundation (Complete)
*"Can we make a useful AI fitness coach?"*

- ✅ Built the knowledge graph (Neo4j with 4,000+ exercises)
- ✅ Established modality-based training architecture
- ✅ Created MCP tools for planning, tracking, coaching
- ✅ Implemented semantic memory (context survives across conversations)
- ✅ Proved Claude can reason about training effectively
- ✅ **ADR-001: Data Layer Separation** - Postgres for facts, Neo4j for relationships
- ✅ **ADR-002: Strength Workout Migration** - 165 sessions, 2,482 sets to Postgres
- ✅ **Journal System** - 17 MCP tools for subjective data capture
- ✅ **Endurance Sessions** - FIT imports to Postgres

**Key Learning:** Claude + Graph + MCP = surprisingly capable coaching. The LLM-native approach works.

**Architecture Established:**
```
POSTGRES (Facts)                    NEO4J (Relationships)
────────────────────────────────    ─────────────────────────
• strength_sessions (165)          • Goals → Modalities → Blocks
• strength_sets (2,482)            • Exercises → MovementPatterns
• endurance_sessions               • PlannedWorkout → PlannedSets
• biometric_readings               • Injuries → Constraints
• log_entries (journal)            • StrengthWorkout refs (FK)
• race_history                     • LogEntry → EXPLAINS → Workout
```

### Phase 1: Core Coaching Loop (Current)
*"Can we run a real training program?"*

- ⏳ Execute planned workouts, capture deviations
- ⏳ Build coaching observations over time
- ⏳ Test periodization across a full training block
- ⏳ Validate the plan → execute → reflect cycle
- 📋 **Requirement-gated progression** — auto-advance weight/reps only if previous week's targets met (from wger)
- 📋 **Exercise type modeling** — dropset, myo-reps, TUT, iso-hold, AMRAP sets (from wger)
- 📋 **RIR tracking** — Reps in Reserve alongside RPE for autoregulation (from wger)
- 📋 **Workout day types** — EMOM, AMRAP, TABATA, HIIT, RFT templates (from wger)

**Key Question:** Does the system actually improve training outcomes?

### Phase 2: The Analyst (In Progress)
*"Can we extract insight from accumulated data?"*

- ✅ Data lake architecture (raw → staging → analytics)
- ✅ Data catalog with 18 sources registered
- ✅ Apple Health import complete (292K records → 12 Parquet tables)
- ✅ Clinical data import (494 labs with LOINC, conditions, meds, immunizations)
- ✅ Ultrahuman daily metrics staged (234 days)
- ✅ Race history consolidated (95 races, 2005-2023, running + triathlon)
- ✅ DATA_DICTIONARY.md created (comprehensive schema reference)
- ✅ **TRAINING_METRICS.md created** (evidence-based metrics with 17 citations)
- ✅ **Muscle heatmap dashboard** (Streamlit + DuckDB, Weber-Fechner log normalization)
- ✅ **DuckDB analytics setup script** (scripts/setup_analytics.py with Tier 1 metrics)
- ⏳ Run setup script, verify metrics working
- 📋 arnold-analytics-mcp (query interface, report generation)
- 📋 Pattern detection with Bayesian evidence framework
- 📋 Visual artifacts (charts, correlations, trends)

**Key Question:** What patterns emerge when we see everything?

**Training Metrics by Tier:**
| Tier | Metrics | Data Source |
|------|---------|-------------|
| 1 | Volume Load, ACWR, Monotony, Strain, Pattern Freq | Neo4j workouts |
| 2 | hrTSS, Readiness, ATL/CTL/TSB | Ultrahuman + Apple Health HR |
| 3 | Suunto TSS, rTSS | FIT export (manual, not planned) |

**Data Lake Current State:**
| Source | Tables | Rows | Status |
|--------|--------|------|--------|
| Apple Health | 8 | 20,227 | ✅ Staged |
| Clinical (FHIR) | 4 | 584 | ✅ Staged |
| Ultrahuman | 1 | 234 | ✅ Staged |
| Neo4j Export | 4 | 6,886 | ✅ Staged |
| Race History | 1 | 95 | ✅ Staged |

### Phase 3: The Doctor
*"Can we meaningfully track and interpret health data?"*

- 📋 Lab result import and trending
- 📋 Medication tracking with interaction awareness
- 📋 Symptom logging with pattern detection
- 📋 Blood pressure monitoring with context
- 📋 Integration with medical record data (MyChart)

**Key Question:** Can we catch what doctors miss between appointments?

### Phase 4: Data Integration
*"Can we unify all health data sources?"*

- ✅ Full Apple Health parsing (HR, HRV, sleep, workouts, steps)
- ✅ Race history reconstruction (18 years consolidated)
- 📋 Historical Garmin/Suunto .FIT import
- 📋 Body composition tracking (sparse - needs regular weigh-ins)
- 📋 **Nutrition tracking** — Open Food Facts API (2M+ foods, used by wger)
- 📋 Workout deduplication (Apple Health vs Neo4j)

**Key Question:** What's the complete picture?

### Phase 5: The Complete Twin
*"Can we model the whole person?"*

- 📋 Cross-domain correlation (sleep ↔ performance ↔ labs ↔ mood)
- 📋 Predictive insights (injury risk, illness precursors)
- 📋 Research agent (latest literature on your conditions)
- 📋 Journaling/reflection with semantic search
- 📋 Long-term trend analysis (years of data)

**Key Question:** What would a team of specialists see that you can't?

### Phase 6: Delivery & Scale
*"Can others use this?"*

- 📋 Clean deployment model
- 📋 Privacy-preserving architecture
- 📋 Onboarding for new users
- 📋 Mobile-friendly interfaces
- 📋 Open-source core components

**Key Question:** Can this help anyone, not just the builder?

---

## Design Philosophy

### Simple Enough, But Not Simpler

The goal is not to hide complexity. It's to present the right level of detail for the context.

- **Default**: Simple, actionable recommendation
- **On request**: Reasoning and evidence
- **Available**: Full derivation, raw data, explicit assumptions

The barista doesn't need to know the extraction curves. The coffee scientist does. Both should be able to get what they need.

### Complex Enough, But Not More Complex

We don't add sophistication for its own sake. Every model, every feature, every data source must answer:

1. Does this improve decisions?
2. Is the effect large enough to matter?
3. Can we validate it actually works?

Pseudoscience measurements (looking at you, body fat percentage from scales) get ingested but flagged. They might be useful for trend detection even if the absolute values are garbage.

### Individualized Medicine for Optimal Outcomes

Population studies tell us what works "on average." But you're not average. You're a sample size of one with a unique genotype, phenotype, history, and context.

Arnold learns YOUR response curves:
- How YOUR body responds to training volume
- How YOUR sleep affects YOUR performance
- What predicts illness FOR YOU
- What YOUR optimal recovery looks like

The system starts with population priors (informed by literature) and updates toward YOUR individual posterior (informed by YOUR data). With enough data, your patterns dominate. With sparse data, you fall back toward what science knows about humans in general.

### Control Systems Thinking

This isn't a dashboard. It's a closed-loop control system.

```
Measure → Estimate State → Decide → Act → Measure Response → Update
```

Every recommendation is a hypothesis. Every outcome is feedback. The system learns which interventions work for you and which don't.

Key control principles:
- **Dampening**: Don't overreact to single data points
- **Persistence detection**: Notice when signals keep showing up
- **Loop tuning**: Learn the right responsiveness for each pattern
- **Stability**: Prioritize recommendations that don't oscillate wildly

### Transparency as Foundation

Every recommendation must be explainable:
- What data drove this?
- What assumptions were made?
- How confident are we?
- What would change our mind?

Not because users always want to see it. Because unexplainable recommendations can't be debugged, validated, or trusted.

---

## The Bayesian Mindset

### No Binary Gates

We don't ask "Is this significant?" We ask "How much should we update our beliefs?"

- P-values create false certainty (p=0.049 vs p=0.051 treated completely differently)
- Credible intervals communicate uncertainty honestly
- Prior knowledge matters (sleep affecting recovery is more plausible than moon phases affecting recovery)
- Effect size matters (a "significant" effect too small to notice is useless)

### Evidence Grades, Not Pass/Fail

| Grade | Meaning |
|-------|---------|
| **Strong** | High confidence, consistent across time, large effect |
| **Moderate** | Good evidence, reasonable confidence |
| **Suggestive** | Pattern emerging, needs more data |
| **Weak** | Possible signal, high uncertainty |
| **Insufficient** | Not enough data to say anything |

These are communication tools, not decision gates. The underlying numbers are always available.

### Continuous Learning

Every day brings new data. Every recommendation is a test. The system never stops updating:
- Did the intervention work?
- Is the pattern holding?
- Has something changed?

---

## Technical Bets

### Bet 1: Graph + LLM > Traditional Software

Rigid rule engines can't handle the nuance of coaching. Pattern matching breaks on edge cases. But an LLM that can traverse a knowledge graph, reason about relationships, and generate natural language recommendations? That's a different capability.

**Validation**: Does Claude make better training recommendations with the graph than without?

### Bet 2: Bayesian > Frequentist for Personal Data

Population statistics average away individual variation. Bayesian methods let us learn individual response curves while using population knowledge as priors.

**Validation**: Do individualized models outperform population-average recommendations?

### Bet 3: Data Lake > Data Warehouse (For Now)

We don't know what questions we'll want to ask. Premature schema optimization creates rigidity. Keep raw data raw, transform at query time, build views as patterns emerge.

**Validation**: Do we regret any early design decisions? Are we able to answer new questions without schema changes?

### Bet 4: Transparency > Black Box

Explainable recommendations build trust, enable debugging, and allow human override. Black box ML might be more "accurate" but can't be interrogated when it fails.

**Validation**: Do users trust the system? Can we diagnose failures?

---

## Success Metrics

### For the Athlete (Brock)

- Training consistency improves
- Progress toward goals accelerates
- Injury frequency decreases
- Recovery quality improves
- Time spent on training admin decreases

### For the System

- Recommendations are followed (signal of trust)
- Predictions are accurate (signal of validity)
- Patterns discovered are actionable (signal of utility)
- Explainability is used (signal of engagement)

### For the Vision

- System works for someone other than the builder
- Architecture is replicable
- Privacy is maintained
- Value exceeds effort

---

## Research Notes

### wger Workout Manager (Evaluated Jan 2026)

Open-source fitness app (`research/wger/`). Patterns adopted into roadmap above. Not using their exercise database (691 vs our 4,000+), muscle model (16 flat vs our UBERON hierarchy), or Django architecture.

---

## What's Not In Scope (Yet)

### Not a Medical Device
Arnold doesn't diagnose, treat, or prescribe. It observes, correlates, and suggests. Always consult professionals for medical decisions.

### Not a Social Platform
This is personal health sovereignty, not social fitness. No leaderboards, no sharing, no gamification. Just your data, your analysis, your decisions.

### Not a Replacement for Expertise
Arnold augments professionals, doesn't replace them. Better informed conversations, not avoided conversations.

### Not Perfect
The system will be wrong. Patterns will be noise. Recommendations will miss the mark. The goal is to be useful on average, transparent about uncertainty, and continuously improving.

---

## The Name

Arnold — yes, that Arnold. Schwarzenegger. The Terminator.

Internal codenames continue the theme:
- CYBERDYNE-CORE: Neo4j database
- T-800: Exercise knowledge graph
- SARAH-CONNOR: User profile/digital twin
- T-1000: Analyst (analytics-mcp)
- SKYNET-READER: Data import pipelines
- JUDGMENT-DAY: Workout planning logic

It's playful. It's memorable. And there's something fitting about building a machine that helps humans become stronger.

---

## Closing Thought

> "The best time to plant a tree was 20 years ago. The second best time is now."

Every day of health data is a day of insight into yourself. Every tracked workout is a data point in your individual response curve. Every lab result is a snapshot in your longitudinal health story.

Arnold makes that history useful. Not by replacing your judgment, but by showing you patterns you couldn't see. Not by telling you what to do, but by informing your decisions with evidence.

Your data. Your analysis. Your health sovereignty.

Let's build.
