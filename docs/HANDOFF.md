# Arnold Project - Thread Handoff

> **Last Updated**: January 2, 2026 (Training Metrics Specification Complete)
> **Previous Thread**: Training Metrics Research & Documentation Session
> **Compactions in Previous Thread**: 2

## For New Claude Instance

You're picking up development of **Arnold**, an AI-native fitness coaching system built on Neo4j. This thread completed major data infrastructure work.

---

## Step 1: Read the Core Documents

```
1. /Users/brock/Documents/GitHub/arnold/docs/ARCHITECTURE.md  (Master reference)
2. /Users/brock/Documents/GitHub/arnold/docs/DATA_DICTIONARY.md  (Data lake reference)
3. /Users/brock/Documents/GitHub/arnold/docs/TRAINING_METRICS.md  (NEW - Evidence-based metrics w/ citations)
4. /Users/brock/Documents/GitHub/arnold/docs/ROADMAP.md  (Vision document)
```

---

## Step 2: What Was Accomplished This Session

### Major Deliverables

1. **TRAINING_METRICS.md Created** - Comprehensive evidence-based metrics specification
   - Tier 1: Metrics from logged workouts (ACWR, Volume Load, Monotony, Strain)
   - Tier 2: Metrics requiring biometrics (hrTSS, Readiness, ATL/CTL/TSB)
   - Tier 3: External platform metrics (Suunto TSS - NOT available via Apple Health)
   - 17 peer-reviewed citations with full bibliographic details
   - Coaching decision matrix with thresholds

2. **Data Availability Clarified**
   - Suunto TSS does NOT sync to Apple Health (confirmed via research)
   - hrTSS can be calculated from HR data during workouts
   - Polar arm band HR can provide workout HR when worn during strength sessions
   - Max HR calculated from age (220 - 50 = 170 bpm for Brock)

3. **Documentation Updated**
   - ARCHITECTURE.md: Added Training Metrics section, updated roadmap
   - DATA_DICTIONARY.md: Added reference to TRAINING_METRICS.md
   - HANDOFF.md: This file, updated for new session

### Previous Session Accomplishments (Preserved)

- Apple Health Import: 292K records, 12 Parquet tables
- Race History: 95 races (2005-2023) consolidated
- Clinical FHIR: 494 labs with LOINC codes
- Ultrahuman: 234 days daily metrics

### Data Lake Current State

```
/data/staging/                          ROWS
├── apple_health_hr.parquet            3,892   (hourly aggregated)
├── apple_health_hrv.parquet           9,912   (raw measurements)
├── apple_health_sleep.parquet         4,281   (sleep segments)
├── apple_health_workouts.parquet        197   (from Suunto/Polar/Ultrahuman)
├── apple_health_steps.parquet         1,672   (daily by source)
├── apple_health_resting_hr.parquet      168
├── apple_health_weight.parquet            3   (sparse - manual only)
├── apple_health_bp.parquet                2   (sparse)
├── clinical_labs.parquet                494   (179 unique tests, LOINC coded)
├── clinical_conditions.parquet           12   (ICD/SNOMED coded)
├── clinical_medications.parquet          58   (RxNorm coded)
├── clinical_immunizations.parquet        20   (CVX coded)
├── ultrahuman_daily.parquet             234   (May 2025 → Jan 2026)
├── race_history.parquet                  95   (2005 → 2023)
├── workouts.parquet                     163   (Neo4j export)
├── sets.parquet                       2,453   (Neo4j export)
├── exercises.parquet                  4,242   (Neo4j export)
└── movement_patterns.parquet             28   (Neo4j export)
```

---

## Step 3: Current Context

### Active Goals

| Goal | Target Date | Priority | Key Modalities |
|------|-------------|----------|----------------|
| Deadlift 405x5 | Dec 2026 | High | Hip Hinge (novice/linear) |
| Hellgate 100k | Dec 2026 | High | Ultra Endurance (advanced/block) |
| 10 Pain-Free Ring Dips | Jun 2026 | Medium | Shoulder Mobility (novice/linear) |
| Stay healthy | — | Meta | — |

### Current Block

**Accumulation** - Week 1 of 4 (Dec 30 → Jan 26)
- Intent: Build work capacity, establish movement patterns
- Volume: moderate-high | Intensity: moderate

### Medical Status

- **Knee Surgery** (Nov 12, 2025): **CLEARED** for normal activity
- **Shoulder Mobility Limitation**: Movement gap, ring dips contraindicated until addressed

### 10-Day Training Plan (Active)

| Date | Focus | Status |
|------|-------|--------|
| Wed 1/1 | Easy Move - kickboxing/jump rope | Today |
| **Thu 1/2** | 🎂 **THE FIFTY** - Birthday workout | Tomorrow |
| Fri 1/3 | REST | |
| Sat 1/4 | HINGE - Deadlift focus | |
| Sun 1/5 | LONG RUN - 7-8 miles | |
| Mon 1/6 | REST | |
| Tue 1/7 | UPPER PULL | |
| Wed 1/8 | CONDITIONING | |
| Thu 1/9 | SQUAT/PUSH | |

### Birthday Workout (Jan 2) - "The Fifty"

```
5.0 mile run
50 pushups
50 pullups  
50 KB swings @53lb
50 air squats
50 ab rollouts
```

---

## Step 4: Key Discoveries This Session

### Training Load Data Availability

**What's Available:**
- Suunto calculates TSS, ATL, CTL, TSB internally
- Polar arm band HR monitor provides quality HR data
- Apple Health contains granular HR samples (~5 min intervals)
- Ultrahuman provides daily HRV, sleep scores, recovery scores

**What's NOT Available:**
- Suunto TSS does NOT sync to Apple Health (proprietary)
- FIT file manual export would have TSS, but not worth the effort
- rTSS (pace-based) only available in Suunto/Garmin apps

**Workaround:**
- Calculate hrTSS from HR data during workouts
- Wear Polar arm band during strength sessions (currently only paired with Suunto for cardio)
- HR during workout is better than RPE for load quantification

### Biometric Parameters for Brock

| Parameter | Value | Source |
|-----------|-------|--------|
| Max HR (estimated) | 170 bpm | 220 - age (50) |
| LTHR (estimated) | 144.5 bpm | 0.85 × Max HR |
| Resting HR | ~50 bpm | Ultrahuman data |

### Ultrahuman Granular Data in Apple Health

Ultrahuman writes HR samples every ~5 minutes to Apple Health (not just daily aggregates).
- **Aggregated** (Ultrahuman CSV): Sleep scores, recovery scores → `/data/staging/ultrahuman_daily.parquet`
- **Granular** (Apple Health XML): HR every ~5min → `/data/staging/apple_health_hr.parquet`

### Clinical Data is Gold

494 lab results with LOINC codes from MyChart/Epic. This enables longitudinal biomarker tracking — exactly the kind of analysis specialists charge thousands for.

### Race History Complete

18 years of endurance racing (2005-2023):
- 7 × 100-milers (including Old Dominion, Massanutten, Grindstone)
- 14 × 100Ks (Hellgate 12 times!)
- 2 × Half Ironman (Eagleman, Black Bear)
- Multiple marathons, 50-milers, shorter races

### Data Gaps Identified

- **Weight**: Only 3 manual entries — needs regular weigh-ins
- **Blood Pressure**: Only 2 entries — sparse
- **Workout Overlap**: 197 Apple Health workouts vs 163 Neo4j workouts — some dedupe needed

---

## Step 5: What's Next

### Immediate Priority

1. **Create DuckDB database** (`arnold_analytics.duckdb`)
   - Load all Parquet files
   - Create unified views

2. **First Analytics Queries**
   - Training volume trends
   - HRV ↔ workout performance correlation
   - Sleep impact analysis

3. **Continue Training Plan**
   - Execute birthday workout (Jan 2)
   - Log results, reconcile

### Near-Term

1. **arnold-analytics-mcp** - Query interface for Claude
2. **Pattern detection** - Bayesian evidence framework implementation
3. **Visual artifacts** - React charts for data exploration

### Backlog

- Workout deduplication (Apple Health vs Neo4j)
- Garmin historical .FIT import
- Real-time sync pipeline

---

## Step 6: Key Files Reference

| File | Purpose |
|------|---------|
| `/docs/TRAINING_METRICS.md` | **NEW** - Evidence-based metrics with citations |
| `/docs/ARCHITECTURE.md` | Master technical reference |
| `/docs/DATA_DICTIONARY.md` | **NEW** - Data lake schema reference |
| `/docs/ROADMAP.md` | Vision, narrative, design philosophy |
| `/docs/HANDOFF.md` | This file |
| `/data/catalog.json` | Data intelligence layer (17 sources) |
| `/scripts/sync/import_apple_health.py` | **NEW** - Apple Health streaming parser |
| `/scripts/sync/stage_ultrahuman.py` | CSV → Parquet staging |
| `/src/arnold-analytics-mcp/DESIGN.md` | Analytics MCP tool interface |

---

## Step 7: Brock's Preferences

- Substance over praise
- Direct answers, no engagement farming
- Graph-first thinking
- Evidence-based (ontologies, citations)
- Phone-readable output formats
- Lifelong athlete phenotype (35 years martial arts, 18 years ultra) — program accordingly
- **Solve problems you can observe, not problems you imagine**
- Census questions: Use Census API, never web search

---

## Step 8: How to Start

```
1. Call load_briefing (arnold-memory-mcp)
2. Read DATA_DICTIONARY.md for data lake context
3. Review what Brock wants to work on
```

---

## Step 9: Transcript Location

Previous conversation transcripts available at:
```
/mnt/transcripts/2026-01-02-00-22-23-training-load-metrics-specification.txt  (Current session)
/mnt/transcripts/2026-01-01-17-24-56-apple-health-export-discovery.txt  (Previous session)
```

Use these for detailed context if needed. Current transcript contains:
- Training load metrics research (ACWR, TSS, hrTSS)
- Data source investigation (Neo4j, DuckDB, Suunto, Apple Health)
- Metric tier definitions with citations
- Data pipeline architecture

---

## Codenames (Internal)

| Codename | Component |
|----------|-----------|
| CYBERDYNE-CORE | Neo4j database |
| T-800 | Exercise knowledge graph |
| SARAH-CONNOR | User profile/digital twin |
| T-1000 | Analyst (analytics-mcp) |
| SKYNET-READER | Data import pipelines |
