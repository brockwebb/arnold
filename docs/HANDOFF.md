# Arnold Project - Thread Handoff

## For New Claude Instance

You're picking up development of **Arnold**, an AI-native fitness coaching system built on Neo4j. Read the architecture document first, then proceed.

---

## Step 1: Read the Architecture

```
Read /Users/brock/Documents/GitHub/arnold/docs/ARCHITECTURE.md
```

This is the authoritative reference covering system architecture, modality-based training model, memory architecture, and MCP roster.

---

## Step 2: Current State (Dec 31, 2025)

### The System Works

**arnold-memory-mcp is live.** Call `load_briefing` at conversation start to get full coaching context:
- Athlete identity & phenotype (lifelong, 35 years)
- Athletic background (martial arts, ultrarunning, triathlon)
- Active goals with modality requirements
- Training levels per modality with progression models
- Current block (week X of Y, intent, targets)
- Medical constraints & injuries
- Recent workouts
- Equipment

**No more drift. No more re-explaining context.**

### MCP Roster

| MCP | Status | Purpose |
|-----|--------|---------|
| arnold-memory-mcp | ✅ **NEW** | Context management, `load_briefing`, observations, semantic search |
| arnold-training-mcp | ✅ Operational | Planning, exercise selection, workout logging |
| arnold-profile-mcp | ✅ Operational | Person, equipment, activities |
| neo4j-mcp | ✅ External | Direct graph queries |

### Graph Node Counts

| Node Type | Count |
|-----------|-------|
| Exercise | 4,242 |
| Workout | 163 |
| Modality | 14 |
| Goal | 4 |
| TrainingLevel | 6 |
| Block | 4 |
| PlannedWorkout | 1 |
| Protocol | 10 |

### Vector Indexes

| Index | Node Type | Dimensions | Similarity |
|-------|-----------|------------|------------|
| obs_embedding_index | Observation | 1536 | cosine |

### Active Goals

| Goal | Target Date | Priority | Key Modalities |
|------|-------------|----------|----------------|
| Deadlift 405x5 | Dec 2026 | High | Hip Hinge (novice/linear), Core Stability (advanced) |
| Hellgate 100k | Dec 2026 | High | Ultra Endurance (advanced/block), Aerobic Base (advanced/block) |
| 10 Pain-Free Ring Dips | Jun 2026 | Medium | Shoulder Mobility (novice/linear) |
| Stay healthy | — | Meta | — |

### Training Levels

| Modality | Level | Model |
|----------|-------|-------|
| Hip Hinge Strength | novice | Linear |
| Shoulder Mobility | novice | Linear |
| Anaerobic Capacity | intermediate | Undulating |
| Core Stability | advanced | Undulating |
| Ultra Endurance | advanced | Block |
| Aerobic Base | advanced | Block |

### Current Block

**Accumulation** - Week 1 of 4 (Dec 30 → Jan 26)
- Intent: Build work capacity, establish movement patterns
- Volume: moderate-high | Intensity: moderate
- Serves: Deadlift, Ring Dips, Stay Healthy

### Medical

- **Knee Surgery** (Nov 12, 2025): Recovering, 7 weeks post-op. Rapid recovery. Exposed frontal plane core gap.
- **Shoulder Mobility Limitation** (Dec 30, 2025): Ring dips exposed desk-posture tightness. Not injury - movement gap to train.
- **Triple Hernia** (Nov 2023): Resolved, no issues.

---

## Step 3: What's Next

### Immediate Options

1. **Plan the week** - Rest of Week 1 (Tue-Sun). Include:
   - Strength sessions (hip hinge focus for deadlift goal)
   - Shoulder mobility routine (5 min daily)
   - Balance across modalities

2. **Test full workflow** - Plan → Confirm → Execute → Reconcile a session

3. **Test semantic search** - Store observations, query them naturally

### Protocols to Remember

**Shoulder Mobility - Daily 5min:**
- Band Pull-Apart: 2x15
- Wall Slide: 2x10
- Shoulder CAR: 5 each direction
- Pec Doorway Stretch: 30s each side
- Thread the Needle: 5 each side

**Dip Progression (for ring dips goal):**
- Phase 1 (Jan-Feb): Push-ups + mobility
- Phase 2 (Mar): Bench dips
- Phase 3 (Apr): Parallel bar dips
- Phase 4 (May): Ring support → partial ROM
- Phase 5 (Jun): Full ROM ring dips

### Coaching Feedback from Last Session

1. **Warmup preference**: General movement first (kickboxing, jump rope), not specific movement prep
2. **KB push press**: Start at 35lb, technique breaks down after 3 reps when overloaded
3. **Ring dips**: Contraindicated until shoulder mobility improves

---

## Step 4: Key Queries

```cypher
// Get coach briefing data
MATCH (p:Person {name: "Brock Webb"})-[:HAS_GOAL]->(g:Goal {status: 'active'})
OPTIONAL MATCH (g)-[:REQUIRES]->(m:Modality)
RETURN g.name, collect(m.name) as modalities

// Recent workouts
MATCH (p:Person {name: 'Brock Webb'})-[:PERFORMED]->(w:Workout)
RETURN w.date, w.type, w.notes
ORDER BY w.date DESC
LIMIT 7

// Get protocols for a goal
MATCH (g:Goal {name: '10 Pain-Free Ring Dips'})-[:HAS_PROTOCOL]->(proto:Protocol)
RETURN proto.name, proto.routine, proto.phases

// Semantic search over observations (via MCP tool)
search_observations(query="why does my deadlift break down?", threshold=0.7)
```

---

## Step 5: Key Files

| File | Purpose |
|------|---------|  
| `/arnold/docs/ARCHITECTURE.md` | Master reference |
| `/arnold/docs/schema.md` | Neo4j schema |
| `/arnold/docs/HANDOFF.md` | This file |
| `/arnold/src/arnold-memory-mcp/` | Context management (NEW) |
| `/arnold/src/arnold-training-mcp/` | Training/coaching tools |
| `/arnold/src/arnold-profile-mcp/` | Profile management |

### Claude Desktop Config

**Location:** `~/Library/Application Support/Claude/claude_desktop_config.json`

When adding a new MCP server, add an entry to this file:

```json
{
  "mcpServers": {
    "arnold-memory-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp",
        "run",
        "arnold-memory-mcp"
      ]
    }
  }
}
```

**After editing config:** Restart Claude Desktop to pick up changes.

**Note:** `pip install -e .` is NOT required. Claude Desktop uses `uv run` directly.

---

## Brock's Preferences

- Substance over praise
- Direct answers, no engagement farming
- Graph-first thinking
- Evidence-based (ontologies, citations)
- Phone-readable output formats
- Lifelong athlete phenotype - program accordingly

---

## How to Start a Conversation

```
1. Call load_briefing (arnold-memory-mcp)
2. Review context
3. Ask what Brock wants to work on
```

The briefing gives you everything. No more cold starts.

---

## Codenames (Internal)

| Codename | Component |
|----------|-----------|
| CYBERDYNE-CORE | Neo4j database |
| T-800 | Exercise knowledge graph |
| SARAH-CONNOR | User profile/digital twin |
