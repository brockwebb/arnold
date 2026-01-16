# Issue 013: Implement Unified Workout Schema (Segments + Sport-Specific Tables)

**Created:** 2026-01-13  
**Status:** Closed (2026-01-14)  
**Priority:** High  
**ADR:** [006-unified-workout-schema.md](../adr/006-unified-workout-schema.md)

## Problem

Current two-table design (`strength_sessions`, `endurance_sessions`) doesn't scale:
- Can't handle rowing, cycling, swimming, climbing, martial arts, CrossFit
- Can't represent multi-modal sessions (e.g., brick workouts, CrossFit WODs)
- Adding new sport = new table = constant migrations

## Solution

Implement segment-based model per ADR-006:

```
workouts
  └── segments (sport_type discriminator)
        ├── strength_sets
        ├── rowing_intervals
        ├── running_intervals
        ├── swimming_laps
        ├── cycling_intervals
        └── segment_events_generic (fallback)
```

Plus `metric_catalog` for Claude navigation.

## Implementation Phases

### Phase 1: Core Schema (DDL)

Create new tables:

```sql
-- Core workout record
CREATE TABLE workouts_v2 (
  workout_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  duration_seconds INT,
  timezone TEXT,
  rpe NUMERIC(3,1),
  notes TEXT,
  source TEXT,                    -- 'logged', 'from_plan', 'imported'
  source_fidelity SMALLINT,       -- 1-5 confidence in data quality
  source_device TEXT,             -- 'polar_h10', 'ultrahuman', 'manual'
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Segments: ordered modality blocks within workout
CREATE TABLE segments (
  segment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workout_id UUID NOT NULL REFERENCES workouts_v2(workout_id),
  seq SMALLINT NOT NULL,          -- order within workout
  sport_type TEXT NOT NULL,       -- 'strength', 'running', 'rowing', etc.
  start_time TIMESTAMPTZ,
  end_time TIMESTAMPTZ,
  duration_seconds INT,
  transition_seconds INT,         -- gap from previous segment
  planned_segment_id TEXT,        -- links to Neo4j plan (intent vs outcome)
  local_baseline_hr NUMERIC,      -- optional per-segment baseline
  raw_blob_ref TEXT,              -- pointer to timeseries file
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workout_id, seq)
);

COMMENT ON TABLE segments IS 'Ordered modality blocks within a workout. One segment per contiguous activity type.';
COMMENT ON COLUMN segments.sport_type IS 'Discriminator: strength, running, rowing, cycling, swimming, climbing, martial_arts, crossfit, generic';
COMMENT ON COLUMN segments.transition_seconds IS 'Time gap from previous segment end - useful for brick workout analysis';
COMMENT ON COLUMN segments.planned_segment_id IS 'Links to Neo4j PlannedWorkout for intent vs outcome comparison';

-- Strength sets (child of segment)
CREATE TABLE strength_sets (
  set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(segment_id),
  seq SMALLINT NOT NULL,          -- set order within segment
  exercise_id TEXT,               -- links to Neo4j exercise catalog
  exercise_name TEXT,             -- denormalized for convenience
  reps SMALLINT,
  load NUMERIC(7,2),
  load_unit TEXT DEFAULT 'lb',
  rpe NUMERIC(3,1),
  time_started TIMESTAMPTZ,
  time_ended TIMESTAMPTZ,
  rest_seconds INT,               -- rest before this set
  failed BOOLEAN DEFAULT false,
  pain_scale SMALLINT,            -- 0-10, rehab context
  is_warmup BOOLEAN DEFAULT false,
  tempo_code TEXT,                -- e.g., '3010' for rehab
  notes TEXT,
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(segment_id, seq)
);

COMMENT ON TABLE strength_sets IS 'Individual sets within a strength segment. One row per set.';
COMMENT ON COLUMN strength_sets.exercise_id IS 'Foreign key to Neo4j Exercise node ID';
COMMENT ON COLUMN strength_sets.pain_scale IS 'Post-op subjective feedback (0-10). Critical for rehab tracking.';
COMMENT ON COLUMN strength_sets.time_started IS 'Enables HR window alignment for inter-set HRR calculation';

-- Running intervals (child of segment)
CREATE TABLE running_intervals (
  interval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(segment_id),
  seq SMALLINT NOT NULL,
  distance_m NUMERIC(10,2),
  duration_seconds INT,
  avg_pace_per_km TEXT,           -- e.g., '5:30'
  avg_hr SMALLINT,
  max_hr SMALLINT,
  avg_cadence SMALLINT,
  elevation_gain_m NUMERIC(7,2),
  elevation_loss_m NUMERIC(7,2),
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(segment_id, seq)
);

-- Rowing intervals (child of segment)
CREATE TABLE rowing_intervals (
  interval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(segment_id),
  seq SMALLINT NOT NULL,
  distance_m NUMERIC(10,2),
  duration_seconds INT,
  avg_500m_pace_seconds NUMERIC(6,2),
  stroke_rate NUMERIC(5,2),       -- strokes per minute
  stroke_count INT,
  drag_factor SMALLINT,
  avg_hr SMALLINT,
  max_hr SMALLINT,
  avg_power_watts SMALLINT,
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(segment_id, seq)
);

-- Cycling intervals (child of segment)
CREATE TABLE cycling_intervals (
  interval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(segment_id),
  seq SMALLINT NOT NULL,
  distance_m NUMERIC(10,2),
  duration_seconds INT,
  avg_power_watts SMALLINT,
  normalized_power SMALLINT,
  intensity_factor NUMERIC(4,3),
  avg_hr SMALLINT,
  max_hr SMALLINT,
  avg_cadence SMALLINT,
  elevation_gain_m NUMERIC(7,2),
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(segment_id, seq)
);

-- Swimming laps (child of segment)
CREATE TABLE swimming_laps (
  lap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(segment_id),
  seq SMALLINT NOT NULL,
  distance_m NUMERIC(7,2),
  duration_seconds INT,
  stroke_type TEXT,               -- 'freestyle', 'backstroke', etc.
  stroke_count SMALLINT,
  swolf SMALLINT,                 -- strokes + seconds
  avg_hr SMALLINT,
  pool_length_m NUMERIC(5,2),
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(segment_id, seq)
);

-- Generic fallback for unmapped sports
CREATE TABLE segment_events_generic (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id UUID NOT NULL REFERENCES segments(segment_id),
  seq SMALLINT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value NUMERIC,
  metric_unit TEXT,
  metric_ts TIMESTAMPTZ,          -- when metric applies (optional)
  source TEXT,
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE segment_events_generic IS 'Fallback for rare/unknown sports. Promotes to dedicated table when usage warrants.';

-- Metric catalog: Claude's navigation map
CREATE TABLE metric_catalog (
  metric_name TEXT PRIMARY KEY,
  table_name TEXT NOT NULL,
  display_name TEXT,
  unit TEXT,
  sport_types TEXT[],             -- NULL means universal
  description TEXT,
  computation_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE metric_catalog IS 'Maps metric names to tables. Claude reads this to know where to query.';
```

### Phase 2: Indexes and Views

```sql
-- Key indexes
CREATE INDEX idx_workouts_v2_user_date ON workouts_v2(user_id, start_time);
CREATE INDEX idx_segments_workout ON segments(workout_id, seq);
CREATE INDEX idx_segments_sport ON segments(sport_type);
CREATE INDEX idx_strength_sets_segment ON strength_sets(segment_id, seq);
CREATE INDEX idx_strength_sets_exercise ON strength_sets(exercise_id);
CREATE INDEX idx_running_intervals_segment ON running_intervals(segment_id, seq);
CREATE INDEX idx_rowing_intervals_segment ON rowing_intervals(segment_id, seq);

-- Unified activity view for cross-modal queries
CREATE VIEW v_all_activity_events AS
SELECT 
  s.segment_id, s.workout_id, s.sport_type, s.seq as segment_seq,
  ss.seq as event_seq, 'set' as event_type,
  ss.exercise_name as description,
  (ss.reps * ss.load) as volume,
  ss.rpe as intensity,
  ss.time_started, ss.time_ended
FROM segments s
JOIN strength_sets ss ON s.segment_id = ss.segment_id
UNION ALL
SELECT 
  s.segment_id, s.workout_id, s.sport_type, s.seq,
  ri.seq, 'interval',
  'running',
  ri.distance_m as volume,
  ri.avg_hr as intensity,
  NULL, NULL
FROM segments s
JOIN running_intervals ri ON s.segment_id = ri.segment_id
UNION ALL
SELECT 
  s.segment_id, s.workout_id, s.sport_type, s.seq,
  ro.seq, 'interval',
  'rowing',
  ro.distance_m as volume,
  ro.avg_hr as intensity,
  NULL, NULL
FROM segments s
JOIN rowing_intervals ro ON s.segment_id = ro.segment_id;

COMMENT ON VIEW v_all_activity_events IS 'Unified view for cross-modal queries. Claude uses this for aggregate questions.';
```

### Phase 3: Metric Catalog Population

```sql
INSERT INTO metric_catalog (metric_name, table_name, unit, sport_types, description) VALUES
-- Universal
('rpe', 'workouts_v2', '1-10', NULL, 'Session RPE'),
('duration_seconds', 'segments', 's', NULL, 'Segment duration'),

-- Strength
('reps', 'strength_sets', 'count', ARRAY['strength'], 'Repetitions per set'),
('load', 'strength_sets', 'lb', ARRAY['strength'], 'Weight lifted'),
('pain_scale', 'strength_sets', '0-10', ARRAY['strength'], 'Rehab pain feedback'),

-- Running
('distance_m', 'running_intervals', 'm', ARRAY['running'], 'Distance in meters'),
('avg_pace_per_km', 'running_intervals', 'min:sec', ARRAY['running'], 'Average pace'),
('avg_cadence', 'running_intervals', 'spm', ARRAY['running'], 'Steps per minute'),

-- Rowing
('stroke_rate', 'rowing_intervals', 'spm', ARRAY['rowing'], 'Strokes per minute'),
('avg_500m_pace_seconds', 'rowing_intervals', 's', ARRAY['rowing'], 'Average 500m split'),
('drag_factor', 'rowing_intervals', 'unitless', ARRAY['rowing'], 'Erg drag factor'),

-- Cycling
('normalized_power', 'cycling_intervals', 'W', ARRAY['cycling'], 'Normalized power'),
('intensity_factor', 'cycling_intervals', 'ratio', ARRAY['cycling'], 'IF = NP/FTP'),

-- Swimming
('swolf', 'swimming_laps', 'score', ARRAY['swimming'], 'Strokes + seconds per length'),
('stroke_count', 'swimming_laps', 'count', ARRAY['swimming'], 'Strokes per lap');
```

### Phase 4: Data Migration

Migrate existing data from `strength_sessions` and `endurance_sessions`:

1. Create `workouts_v2` records from existing sessions
2. Create `segments` records (one per session, since current data is single-modal)
3. Transform `strength_sessions.sets` JSONB → `strength_sets` rows
4. Transform `endurance_sessions` → `running_intervals` (or appropriate sport table)
5. Verify counts match
6. Update MCP tools to use new schema
7. Deprecate old tables (keep for rollback period)

### Phase 5: MCP Updates ✅ COMPLETE (2026-01-14)

Updated `arnold-training-mcp/postgres_client.py`:
- `log_strength_session()` → writes to workouts_v2 + segments + v2_strength_sets
- `log_endurance_session()` → writes to workouts_v2 + segments + sport-specific table
  - Routes to: v2_running_intervals, v2_rowing_intervals, v2_cycling_intervals, v2_swimming_laps
  - Falls back to v2_segment_events_generic for unknown sports
- Query functions updated to read from v2 schema
- Backward compatible return values (session_id preserved alongside workout_id)

Note: Old tables (strength_sessions, endurance_sessions) remain for rollback. New data goes to v2 schema.

### Phase 6: Neo4j References ✅ COMPLETE (2026-01-14)

Updated Neo4j reference nodes with new UUIDs:
- 168 `StrengthWorkout` nodes updated with `workout_id` property
- 2 `EnduranceWorkout` nodes updated with `workout_id` property
- Mapping verified: Neo4j `postgres_id` → Postgres `workouts_v2.workout_id` via date+source join
- Old `postgres_id` property retained for backward compatibility

Note: Unified `Workout` node type deferred - current dual-label approach works fine.

## Acceptance Criteria

- [ ] All new tables created with comments
- [ ] Indexes in place for common query patterns
- [ ] `v_all_activity_events` view working
- [ ] `metric_catalog` populated for existing metrics
- [ ] Existing data migrated without loss
- [ ] MCP tools updated and tested
- [ ] Multi-modal workout can be logged (e.g., row + lift)
- [ ] Unknown sport can be logged to generic fallback

## Risks

- **Migration complexity** — Existing data needs careful transformation
- **MCP changes** — Multiple tools need updates
- **Query changes** — Analytics views need updating

## Dependencies

- Issue 009 (unified logging) should be verified working first
- May want to batch with Issue 010 (Neo4j sync gap) fixes

## References

- [ADR-006: Unified Workout Schema](../adr/006-unified-workout-schema.md)
- ChatGPT Health consultation (2026-01-13)
- Gemini 2.5 Pro consultation (2026-01-13)
