# FR-003: HR Session to Workout Linking

## Metadata
- **Priority**: High
- **Status**: Proposed
- **Created**: 2026-01-09
- **Dependencies**: FR-001, FR-002, ADR-001

## Description

Implement automatic and manual linking between HR monitoring sessions (Polar, Suunto) and logged workouts (strength_sessions, endurance_sessions). This enables:

1. HR-based analytics on strength workouts (recovery intervals, work:rest patterns)
2. Verification of session RPE against physiological data
3. Richer workout visualization with HR overlay

## Rationale

Currently:
- `polar_sessions` table has HR data with timestamps
- `strength_sessions` table has workout data with timestamps
- **No link between them** — we can't query "what was my HR during yesterday's deadlift session"

With linking:
- Calculate recovery intervals (FR-004) per workout
- Correlate RPE with actual HR response
- Identify workouts where HR data is missing
- Build HR-informed training load models

## Matching Logic

### Case 1: Single Workout + Single HR Session (Same Day)
**Confidence: High → Auto-link**

```sql
-- If exactly one of each on the same day, link automatically
SELECT s.id as strength_session_id, p.id as polar_session_id
FROM strength_sessions s
JOIN polar_sessions p ON DATE(s.session_date) = DATE(p.start_time AT TIME ZONE 'America/New_York')
GROUP BY DATE(s.session_date)
HAVING COUNT(DISTINCT s.id) = 1 AND COUNT(DISTINCT p.id) = 1
```

### Case 2: Multiple Workouts or Sessions
**Confidence: Medium → Time-overlap matching**

```sql
-- Match by time overlap (workout within session window, or close to it)
SELECT s.id, p.id,
       -- Check if workout time falls within session window (±15 min buffer)
       CASE 
         WHEN s.session_date BETWEEN p.start_time - INTERVAL '15 minutes' 
                                 AND p.stop_time + INTERVAL '15 minutes'
         THEN 'overlap'
         ELSE 'no_overlap'
       END as match_type
FROM strength_sessions s
CROSS JOIN polar_sessions p
WHERE DATE(s.session_date) = DATE(p.start_time AT TIME ZONE 'America/New_York')
```

### Case 3: Ambiguous
**Confidence: Low → Elicitation required**

When multiple HR sessions could match a workout, surface to user:
```
"I found 2 Polar sessions on Jan 9:
 1. 17:02-17:43 (41 min, avg HR 120) - OTHER
 2. 19:30-20:15 (45 min, avg HR 135) - STRENGTH_TRAINING
 
 Which one corresponds to 'Upper Push/Pull + Sandbag Conditioning'?"
```

### Case 4: No HR Session
**Action: Mark workout as no HR data**

```sql
UPDATE strength_sessions 
SET hr_session_id = NULL, hr_data_status = 'missing'
WHERE id = ?
```

## Data Model

### Option A: FK on strength_sessions (Recommended)

```sql
ALTER TABLE strength_sessions ADD COLUMN polar_session_id INTEGER REFERENCES polar_sessions(id);
ALTER TABLE strength_sessions ADD COLUMN hr_data_status TEXT DEFAULT 'unlinked' 
    CHECK (hr_data_status IN ('unlinked', 'linked', 'missing', 'ambiguous'));
    
-- Same for endurance
ALTER TABLE endurance_sessions ADD COLUMN polar_session_id INTEGER REFERENCES polar_sessions(id);
ALTER TABLE endurance_sessions ADD COLUMN hr_data_status TEXT DEFAULT 'unlinked';
```

### Option B: Junction Table (More Flexible)

```sql
CREATE TABLE workout_hr_links (
    id SERIAL PRIMARY KEY,
    workout_type TEXT NOT NULL,  -- 'strength', 'endurance'
    workout_id INTEGER NOT NULL,
    hr_source TEXT NOT NULL,     -- 'polar', 'suunto', 'apple'
    hr_session_id INTEGER NOT NULL,
    match_confidence TEXT,       -- 'auto_single', 'time_overlap', 'manual'
    linked_at TIMESTAMPTZ DEFAULT NOW(),
    linked_by TEXT               -- 'system' or 'user'
);
```

**Recommendation**: Start with Option A (simpler), migrate to Option B if multi-source HR becomes common.

## Acceptance Criteria

- [ ] Schema change: `polar_session_id` added to `strength_sessions` and `endurance_sessions`
- [ ] Auto-linking runs after workout completion (when single match exists)
- [ ] Manual linking available via MCP tool when ambiguous
- [ ] `hr_data_status` populated for all sessions
- [ ] Query works: "Get HR samples for workout X" returns time-series data
- [ ] Unlinked sessions surfaced in daily/weekly reports
- [ ] Historical backfill: Link existing sessions where possible

## MCP Interface

```typescript
// Auto-link if confident, return status
link_hr_to_workout(workout_id: number, workout_type: 'strength' | 'endurance')
  → { status: 'linked', polar_session_id: 69, confidence: 'auto_single' }
  → { status: 'ambiguous', candidates: [{id: 68, ...}, {id: 69, ...}] }
  → { status: 'no_hr_data', message: 'No Polar session found for this date' }

// Manual override
force_link_hr(workout_id: number, workout_type: string, polar_session_id: number)
  → { status: 'linked', confidence: 'manual' }

// Query HR for a workout
get_workout_hr(workout_id: number, workout_type: string)
  → { 
      linked: true,
      polar_session_id: 69,
      summary: { avg_hr: 120, max_hr: 153, duration: 2474 },
      samples_available: true
    }
```

## Technical Notes

### Sync Pipeline Integration

After `complete_as_written` or `log_workout`:
1. Check for Polar sessions on same day
2. Apply matching logic
3. Auto-link if confident
4. Set `hr_data_status` regardless

### Time Zone Handling

- `strength_sessions.session_date` is DATE (no time)
- `polar_sessions.start_time` is TIMESTAMPTZ
- Must convert Polar to local time zone before date comparison

### Historical Backfill Query

```sql
-- Find unlinked strength sessions that have matching Polar data
WITH unlinked AS (
    SELECT id, session_date FROM strength_sessions WHERE polar_session_id IS NULL
),
candidates AS (
    SELECT 
        u.id as strength_id,
        p.id as polar_id,
        p.start_time,
        p.duration_seconds
    FROM unlinked u
    JOIN polar_sessions p ON DATE(u.session_date) = DATE(p.start_time AT TIME ZONE 'America/New_York')
)
SELECT strength_id, COUNT(polar_id) as candidate_count
FROM candidates
GROUP BY strength_id;
-- If candidate_count = 1, auto-link
-- If candidate_count > 1, queue for manual review
```

## Open Questions

- [ ] Should we link at session level or set level? (Session is simpler, set enables per-exercise HR)
- [ ] How to handle Polar sessions that span multiple workouts (e.g., AM strength + PM run)?
- [ ] Should Suunto/Apple data use the same table or separate `suunto_sessions`, `apple_workouts`?
- [ ] Do we need a "split session" feature for when one Polar session covers two workouts?
