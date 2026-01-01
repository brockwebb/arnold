# Arnold Project - Thread Handoff

> **Last Updated**: January 1, 2026 (New Year's Day)
> **Previous Thread**: NYE Analytics Architecture Session

## For New Claude Instance

You're picking up development of **Arnold**, an AI-native fitness coaching system built on Neo4j. Read the architecture document first, then proceed.

---

## Step 1: Read the Architecture

```
Read /Users/brock/Documents/GitHub/arnold/docs/ARCHITECTURE.md
```

This is the authoritative reference covering system architecture, modality-based training model, memory architecture, and MCP roster.

---

## Step 2: Current State (January 1, 2026)

### What's New Since Last Handoff

1. **Analytics Foundation Complete** - Data lake architecture designed and partially implemented
2. **Data Catalog Created** - `/data/catalog.json` with schema intelligence
3. **Export Script Ready** - `/scripts/export_to_analytics.py` awaiting local execution
4. **10-Day Training Plan** - Birthday workout planned for Jan 2
5. **Knee Surgery Clearance** - Doctors cleared return to normal activity

### MCP Roster

| MCP | Status | Purpose |
|-----|--------|---------|
| arnold-memory-mcp | ✅ Operational | Context management, `load_briefing`, semantic search |
| arnold-training-mcp | ✅ Operational | Planning, exercise selection, workout logging |
| arnold-profile-mcp | ✅ Operational | Person, equipment, activities |
| neo4j-mcp | ✅ External | Direct graph queries |

### Graph Node Counts

| Node Type | Count |
|-----------|-------|
| Exercise | 4,242 |
| Workout | 163 |
| Set | 2,453 |
| MovementPattern | 28 |
| Modality | 14 |
| Goal | 4 |
| TrainingLevel | 6 |
| Block | 4 |

### Active Goals

| Goal | Target Date | Priority | Key Modalities |
|------|-------------|----------|----------------|
| Deadlift 405x5 | Dec 2026 | High | Hip Hinge (novice/linear), Core Stability (advanced) |
| Hellgate 100k | Dec 2026 | High | Ultra Endurance (advanced/block), Aerobic Base (advanced/block) |
| 10 Pain-Free Ring Dips | Jun 2026 | Medium | Shoulder Mobility (novice/linear) |
| Stay healthy | — | Meta | — |

### Current Block

**Accumulation** - Week 1 of 4 (Dec 30 → Jan 26)
- Intent: Build work capacity, establish movement patterns
- Volume: moderate-high | Intensity: moderate
- Serves: Deadlift, Ring Dips, Stay Healthy

### Medical Status

- **Knee Surgery** (Nov 12, 2025): **CLEARED** - Doctors cleared return to normal activity, 7 weeks post-op. No more "babying" the knee.
- **Shoulder Mobility Limitation** (Dec 30, 2025): Not injury — movement gap from desk posture. Ring dips contraindicated until addressed.

---

## Step 3: 10-Day Training Plan (Active)

**Context**: Brock turning 50 on Jan 2, 1976. Birthday workout planned.

| Date | Day | Focus | Key Notes |
|------|-----|-------|-----------|
| Tue 12/31 | REST | NYE recovery | |
| Wed 1/1 | EASY MOVE | 30 min kickboxing/jump rope | Light movement, blood flow |
| **Thu 1/2** | 🎂 **THE FIFTY** | 5mi run + 50s | Birthday workout! |
| Fri 1/3 | REST | Recovery | Earn it |
| Sat 1/4 | HINGE | Deadlift 4×5, RDL 3×8, KB swings | Hip hinge strength focus |
| Sun 1/5 | LONG RUN | 7-8 miles easy | First long run post-surgery |
| Mon 1/6 | REST | | |
| Tue 1/7 | UPPER PULL | Chin-up 4×6, Row 4×8, Face pulls | |
| Wed 1/8 | CONDITIONING | 30 min KB/burpee/rope intervals | |
| Thu 1/9 | SQUAT/PUSH | Back squat 4×6, KB press, dips | |

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

## Step 4: Analytics Foundation (NEW)

### Architecture Decision

**Data Lake, Not Data Warehouse** — Solve problems you can observe, not problems you imagine.

```
/data/
├── raw/                    # NATIVE FORMAT, UNTOUCHED
│   ├── neo4j_snapshots/
│   ├── suunto/
│   ├── ultrahuman/
│   └── apple_health/
├── staging/                # PARQUET, MINIMAL TRANSFORM
├── catalog.json            # ✅ THE INTELLIGENCE (CREATED)
└── arnold_analytics.duckdb # Query layer (pending)
```

### What Exists

1. **`/data/catalog.json`** - Data intelligence layer describing:
   - What data exists (sources, row counts, date ranges)
   - Schema and column types
   - Fitness for use (completeness, consistency)
   - Link strategies (how to join sources)
   - Known questions and how to answer them
   - Future sources (Ultrahuman, Suunto, Apple Health)

2. **`/scripts/export_to_analytics.py`** - Ready to run on local machine:
   - Exports workouts, sets, exercises, patterns from Neo4j
   - Writes raw JSON + staging Parquet
   - Run with: `cd ~/Documents/GitHub/arnold && python scripts/export_to_analytics.py`

### Key Design Decisions

1. **Date is universal join key** - Most health data is day-grain
2. **UTC storage + attribution date** - Handles midnight-crossing events (ultras, sleep)
3. **Raw stays raw** - Never destroy source fidelity
4. **Transform at query time OR pre-build** - Flexibility over prescription

### Edge Cases Documented but Unsolved

- **Ultrahuman time handling**: Unknown — need sample data
- **Midnight-crossing activities**: Store UTC, compute attribution
- **Duplicate sources**: Time overlap matching for deduplication

---

## Step 5: Protocols to Remember

### Shoulder Mobility - Daily 5min

```
Band Pull-Apart: 2x15
Wall Slide: 2x10
Shoulder CAR: 5 each direction
Pec Doorway Stretch: 30s each side
Thread the Needle: 5 each side
```

### Dip Progression (Ring Dips Goal)

- Phase 1 (Jan-Feb): Push-ups + mobility
- Phase 2 (Mar): Bench dips
- Phase 3 (Apr): Parallel bar dips
- Phase 4 (May): Ring support → partial ROM
- Phase 5 (Jun): Full ROM ring dips

---

## Step 6: Coaching Observations Stored

Key observations from recent sessions (stored in Neo4j with embeddings):

1. **Warmup preference**: General movement first (kickboxing, jump rope), not specific movement prep
2. **KB push press**: Start at 35lb, technique breaks down after 3 reps when overloaded
3. **Ring dips**: Contraindicated until shoulder mobility improves
4. **Knee surgery clearance**: Doctors cleared return to normal activity early Jan 2025

---

## Step 7: Key Files

| File | Purpose |
|------|---------|
| `/arnold/docs/ARCHITECTURE.md` | Master reference (updated Jan 1) |
| `/arnold/docs/HANDOFF.md` | This file |
| `/arnold/data/catalog.json` | **NEW** Data intelligence layer |
| `/arnold/scripts/export_to_analytics.py` | **NEW** Neo4j export script |
| `/arnold/src/arnold-memory-mcp/` | Context management + semantic search |
| `/arnold/src/arnold-training-mcp/` | Training/coaching tools |
| `/arnold/src/arnold-profile-mcp/` | Profile management |

---

## Step 8: What's Next

### Immediate (Today/This Week)

1. **Run export script** on local machine to populate Parquet files
2. **Test birthday workout** - Execute Jan 2, reconcile results
3. **Continue Week 1** - Execute planned sessions

### Near-Term

1. **DuckDB setup** - Create database, basic views
2. **First analytics queries** - Volume trends, pattern balance
3. **Import first external source** - Ultrahuman or Suunto

### Backlog

- arnold-analytics-mcp (query interface)
- Hot reports (pattern detection)
- Visual artifacts (React charts)

---

## Step 9: How to Start

```
1. Call load_briefing (arnold-memory-mcp)
2. Review context (goals, block, injuries, recent workouts)
3. Ask what Brock wants to work on
```

The briefing gives you everything. No more cold starts.

---

## Brock's Preferences

- Substance over praise
- Direct answers, no engagement farming
- Graph-first thinking
- Evidence-based (ontologies, citations)
- Phone-readable output formats
- Lifelong athlete phenotype (35 years) - program accordingly
- **Solve problems you can observe, not problems you imagine**

---

## Codenames (Internal)

| Codename | Component |
|----------|-----------|
| CYBERDYNE-CORE | Neo4j database |
| T-800 | Exercise knowledge graph |
| SARAH-CONNOR | User profile/digital twin |
| T-1000 | Analyst (analytics-mcp) |

---

## Transcript Location

Conversation transcripts are stored in Claude's container (`/mnt/transcripts/`) and are NOT accessible from your machine. They exist for Claude's continuity across context compactions. The handoff document and `load_briefing` are the primary mechanisms for thread-to-thread context transfer.
