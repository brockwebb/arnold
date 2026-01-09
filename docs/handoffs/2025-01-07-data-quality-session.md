# Handoff: January 7, 2026 - Data Quality Session

## Session Summary

Major data quality cleanup session focused on fixing bad exercise-pattern relationships and establishing a human verification workflow for LLM-generated classifications.

---

## Completed This Session

### 1. HRV Data Cleanup ✅
- **Problem:** 83 `hrv_morning` records (Dec 1-6) labeled "ultrahuman" were actually Apple Health passthrough (~100ms vs Ring-native ~25ms)
- **Fix:** Deleted 83 duplicate records from `biometric_readings`
- **Validation:** `hrv_morning` now Ring-native only (11-50ms range, avg 26.9ms)

### 2. Missing Deadhang Fix ✅
- **Problem:** 69-second deadhang from Jan 6 workout not in `strength_sets`
- **Root cause:** `complete_with_deviations` tool can't add unplanned exercises
- **Fix:** Manual INSERT into `strength_sets` (session_id=166, exercise_id='CANONICAL:FFDB:1888')
- **Schema fix:** Added 'timed' and 'isometric' to `set_type` constraint

### 3. Grip/Hang Pattern Classification Cleanup ✅
- **Problem:** Dec 29 script used naive regex to classify exercises, matching "Grip" and "Hang" keywords without semantic understanding
- **Result:** 253 exercises incorrectly linked to "Grip / Hang" pattern (e.g., "Close Grip Bench Press", "Hang Power Clean")
- **Fix process:**
  1. Exported all 253 to CSV for human review
  2. Brock marked T (keep) or F (delete) for each
  3. Script applied decisions: 146 kept + verified, 107 deleted
- **Current state:** 153 Grip/Hang relationships, ALL human_verified=true

### 4. Human Verification Workflow ✅
- **Added properties** to INVOLVES and TARGETS relationships:
  - `human_verified` (boolean)
  - `verified_at` (datetime)
  - `verified_by` (string)
- **Updated schema.md** with verification queries and workflow
- **Updated Postgres cache tables** with `human_verified` column
- **Updated sync script** to propagate verification status

### 5. Column Name Fixes ✅
- Fixed mismatch: views use `movement_pattern`/`days_since`, scripts expected `pattern_name`/`days_since_trained`
- Updated `generate_coach_brief.py` and `neo4j_client.py`

---

## Backlog Issues Created

| Issue | Priority | Description |
|-------|----------|-------------|
| 004 | High | Apple Health Import Deduplication - fix source labeling |
| 005 | Medium | Apple Health Data Expansion - investigate VO2max, steps, etc. |
| 006 | High | Logging Workflow - add `additional_sets` param for unplanned exercises |
| 007 | Medium | Pattern Classification - replace regex with LLM |

Issues located in: `/docs/issues/`

---

## First Challenge for Next Thread

### Hip Abductors Inconsistency

**Symptom:** Coach briefing shows:
- Hip Abductors in "muscles worked this week"
- Hip Abduction also showing as "pattern gap"

**Likely causes to investigate:**

1. **Taxonomy mismatch:** "Hip Abductors" (MuscleGroup) vs "Hip Abduction" (MovementPattern) - are exercises correctly linked to BOTH?

2. **View logic:** Check `pattern_last_trained` view - is it looking at the right relationships?

3. **Muscle vs Pattern confusion:** An exercise can target Hip Abductors (muscle) without being classified as Hip Abduction (pattern) if the classification is wrong or missing

**Starting queries:**

```cypher
// What exercises involve Hip Abduction pattern?
MATCH (e:Exercise)-[:INVOLVES]->(mp:MovementPattern {name: 'Hip Abduction'})
RETURN e.name LIMIT 20

// What exercises target Hip Abductors?
MATCH (e:Exercise)-[:TARGETS]->(m)
WHERE m.name CONTAINS 'Abduct'
RETURN e.name, m.name LIMIT 20

// Did any recent workout include Hip Abduction exercises?
MATCH (p:Person)-[:PERFORMED]->(w:Workout)-[:HAS_BLOCK]->(:WorkoutBlock)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(e:Exercise)
WHERE w.date >= date() - duration('P7D')
MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
WHERE mp.name CONTAINS 'Abduct'
RETURN w.date, e.name, mp.name
```

---

## Key Files

| File | Purpose |
|------|---------|
| `docs/schema.md` | Neo4j schema with verification workflow |
| `scripts/sync_exercise_relationships.py` | Neo4j → Postgres cache sync |
| `scripts/apply_grip_hang_review.py` | Template for future batch reviews |
| `data/review/grip_hang_pattern_review.csv` | Completed review (reference) |
| `scripts/reports/generate_coach_brief.py` | PDF report generator |

---

## Verification Workflow (for future use)

**Ad-hoc spot checks:**
```
User: "Give me 5 exercises to validate"
→ Run random unverified query from schema.md
→ Review, mark verified or fix
```

**Scope:** Only INVOLVES and TARGETS relationships (foundational biomechanics)

---

## Current Data State

| Metric | Value |
|--------|-------|
| Grip/Hang relationships | 153 (all verified) |
| Total INVOLVES relationships | ~4,200+ |
| Human verified INVOLVES | 153 (~4%) |
| Postgres cache synced | Yes |

---

## Environment Notes

- Neo4j database: `arnold`
- Scripts need `database=NEO4J_DATABASE` in session calls
- Coach brief script: `scripts/reports/generate_coach_brief.py`
- Transcript from this session: `/mnt/transcripts/2026-01-07-13-06-16-data-quality-fixes-hrv-deadhang-schema.txt`
