# Issue #20 Phase A: Data-Driven Personality Assembly - Handoff

> **Session Date**: January 10, 2026  
> **Status**: Complete  
> **Issue**: [#20](https://github.com/brockwebb/arnold/issues/20) - Session protocols and data-driven personality

---

## Session Summary

Implemented Phase A of Issue #20: data-driven personality assembly for consistent Coach behavior across conversation threads.

---

## Changes Made

### 1. Created Base Personality Config

**File**: `config/personalities/coach.md`

Defines:
- Core identity and communication style (base defaults)
- Coaching approach principles
- Data-driven personality assembly methodology
- Observation tags that inform personality categories
- Template for how observations should be synthesized

### 2. Updated `load_briefing()` with Personality Assembly

**File**: `src/arnold-memory-mcp/arnold_memory_mcp/server.py`

Added:
- `PERSONALITY_TAGS` constant mapping tag categories to coaching personality areas
- `categorize_observation()` function to classify observations
- `truncate_observation()` function for actionable summaries
- `assemble_coaching_notes()` function that transforms raw observations into categorized coaching guidance

**Old output:**
```markdown
## Coaching Observations
- [pattern] Fatigue pattern emerges on deadlift set 3+...
- [preference] Bench press: Don't underprogram...
```

**New output:**
```markdown
## Athlete-Specific Coaching Notes
*Based on 23 observations from past sessions*

### Physical Patterns
- Asymmetry pattern identified: Right-side dominant...
- Fatigue pattern emerges on deadlift set 3+ above 275lbs...

### Programming Approach
- General programming preference: With 35 years training experience...
- Sandbag shouldering preference: descending rep pyramid...

### Communication
- Direct and substantive. Skip pleasantries, get to the point...
- Don't spare the ego. Be honest about concerns...

### ⚠️ Active Flags
- Knee surgery clearance received - doctors cleared return to normal activity...

### Reference Points
- Pre-surgery trap bar deadlift baseline: ~305 lbs for working sets...
- Weighted chin-up data point (Jan 6 2026): 4x4@25lbs, RPE ~8-9...
```

### 3. Seeded Initial Observations

Added communication/interaction observations that were known from context but missing from the database:

| Type | Content Summary |
|------|----------------|
| preference | Direct communication style, data-driven, no engagement farming |
| preference | Don't spare ego, honest feedback, values contrarian perspectives |
| insight | Experience calibration - 35 years, trust athlete override |

---

## Personality Tag Categories

The assembly logic uses these tag sets to categorize observations:

| Category | Tags |
|----------|------|
| `physical` | asymmetry, fatigue, form, grip, balance, mobility, flexibility, rom, technique, breakdown |
| `programming` | programming, loading, autoregulation, pyramid, progression, rep_scheme, volume, intensity |
| `communication` | communication, feedback, coaching_style, trust, interaction, preference |
| `baselines` | baseline, progression, pr, working_weight, capacity |
| `flags` | surgery, injury, clearance, recovery, pain, watch, caution |

---

## Testing Required

1. **Restart MCP server** to pick up changes:
   ```bash
   # Kill existing process and restart Claude Desktop
   # OR restart the MCP server process directly
   ```

2. **Test `load_briefing()`** output:
   - Call `load_briefing()` and verify new "Athlete-Specific Coaching Notes" section appears
   - Verify observations are categorized correctly
   - Verify truncation keeps notes actionable (not verbose dumps)

3. **Test observation storage**:
   - Store a new observation with communication tags
   - Verify it appears in the Communication category on next briefing

---

## What This Enables

1. **Consistent personality** — New threads that call `load_briefing()` get categorized coaching guidance, not raw observation dumps
2. **Actionable context** — Truncated summaries focus on what Coach needs to know, not full history
3. **Evolving personality** — As more observations accumulate, the coaching notes section becomes richer
4. **Flag visibility** — Active flags (surgery, injury, pain) are always visible regardless of observation limits

---

## Remaining Phase A Work

- [x] Define observation tags that inform personality
- [x] Update `load_briefing()` to assemble personality block
- [x] Create base personality config
- [x] Seed initial observations

---

## Next Steps: Phase B

Phase B (Session Capture Protocol) can now proceed:

1. Design `capture_session_knowledge()` protocol or tool
2. Define extraction heuristics for end-of-session knowledge capture
3. Create relationship links (observation → workout, goal, injury)
4. Document the "Coach, let's debrief" ritual

---

## Files Changed

### Created
- `config/personalities/coach.md`
- `docs/handoffs/2026-01-10-issue-20-phase-a.md`

### Modified  
- `src/arnold-memory-mcp/arnold_memory_mcp/server.py`

---

## Observations Seeded

| ID | Type | Summary |
|----|------|---------|
| OBS:dc4ff731... | preference | Communication: direct, substantive, data-driven |
| OBS:029c052e... | preference | Feedback: don't spare ego, honest, contrarian |
| OBS:1bca9488... | insight | Experience calibration: 35 years, trust override |

---

## For Next Thread

If continuing Issue #20:
1. Read this handoff
2. Read Issue #20 for Phase B details
3. Test `load_briefing()` to verify Phase A works
4. Start Phase B: session capture protocol

If doing other work:
1. The Coach personality is now data-driven
2. Store observations with appropriate tags to build the knowledge base
3. Remember: "Coach, ready to train" triggers `load_briefing()`
