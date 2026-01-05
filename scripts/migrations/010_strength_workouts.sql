-- ============================================================================
-- MIGRATION 010: Strength Workouts to Postgres
-- 
-- Purpose: Migrate strength workout data from Neo4j to Postgres-first
-- architecture per ADR-002. Enables direct SQL analytics on sets.
--
-- Architecture (per ADR-001, ADR-002):
--   - Postgres stores FACTS (executed sessions, sets, measurements)
--   - Neo4j stores RELATIONSHIPS (exercise ontology, goals, blocks, plans)
--   - Lightweight Neo4j refs bridge to Postgres detail
--
-- Key insight: Plans are intentions (Neo4j). Executions are facts (Postgres).
--
-- See: ADR-001, ADR-002
-- ============================================================================

-- ============================================================================
-- STRENGTH SESSIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS strength_sessions (
    id SERIAL PRIMARY KEY,
    
    -- Temporal
    session_date DATE NOT NULL,
    session_time TIME,
    
    -- Identity
    name VARCHAR(255),                        -- "Lower Body - Deadlift Focus"
    
    -- Training context (FKs to Neo4j)
    block_id VARCHAR(100),                    -- Neo4j Block.id (training phase)
    plan_id VARCHAR(100),                     -- Neo4j PlannedWorkout.plan_id (if from plan)
    
    -- Session metrics (calculated on insert/update)
    duration_minutes INT,
    total_volume_lbs DECIMAL(12,1),           -- SUM(reps * load)
    total_sets INT,
    total_reps INT,
    avg_rpe DECIMAL(3,1),
    max_rpe INT,
    
    -- Subjective
    session_rpe INT CHECK (session_rpe BETWEEN 1 AND 10),
    energy_level INT CHECK (energy_level BETWEEN 1 AND 10),
    notes TEXT,
    tags TEXT[],
    
    -- Execution tracking
    status VARCHAR(20) DEFAULT 'completed' 
        CHECK (status IN ('completed', 'partial', 'skipped')),
    deviation_notes TEXT,                     -- If deviated from plan
    
    -- Metadata
    source VARCHAR(50) DEFAULT 'logged'
        CHECK (source IN ('logged', 'from_plan', 'imported', 'migrated')),
    neo4j_id VARCHAR(100),                    -- Reference to Neo4j StrengthWorkout node
    legacy_neo4j_id VARCHAR(100),             -- Original Neo4j Workout.id (for migration)
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Prevent duplicates
    CONSTRAINT uq_strength_session UNIQUE (session_date, name)
);

-- ============================================================================
-- STRENGTH SETS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS strength_sets (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES strength_sessions(id) ON DELETE CASCADE,
    
    -- Position in workout
    block_name VARCHAR(100),                  -- "Warm-Up", "Main Work", "Accessory"
    block_type VARCHAR(50)                    -- 'warmup', 'main', 'accessory', 'finisher', 'cooldown'
        CHECK (block_type IN ('warmup', 'main', 'accessory', 'finisher', 'cooldown')),
    set_order INT NOT NULL,                   -- Order within session (1, 2, 3...)
    
    -- Exercise reference (FK to Neo4j Exercise node)
    exercise_id VARCHAR(100) NOT NULL,        -- Neo4j Exercise.id
    exercise_name VARCHAR(255) NOT NULL,      -- Denormalized for query convenience
    
    -- Prescription (if from plan)
    prescribed_reps INT,
    prescribed_load_lbs DECIMAL(7,1),
    prescribed_rpe INT CHECK (prescribed_rpe BETWEEN 1 AND 10),
    prescribed_tempo VARCHAR(20),             -- "3-1-2-0"
    prescribed_rest_seconds INT,
    
    -- Actual execution
    actual_reps INT,
    actual_load_lbs DECIMAL(7,1),
    actual_rpe INT CHECK (actual_rpe BETWEEN 1 AND 10),
    
    -- Computed columns (use actual if present, else prescribed)
    reps INT GENERATED ALWAYS AS (COALESCE(actual_reps, prescribed_reps)) STORED,
    load_lbs DECIMAL(7,1) GENERATED ALWAYS AS (COALESCE(actual_load_lbs, prescribed_load_lbs)) STORED,
    rpe INT GENERATED ALWAYS AS (COALESCE(actual_rpe, prescribed_rpe)) STORED,
    
    -- Volume calculation
    volume_lbs DECIMAL(10,1) GENERATED ALWAYS AS (
        COALESCE(actual_reps, prescribed_reps, 0) * 
        COALESCE(actual_load_lbs, prescribed_load_lbs, 0)
    ) STORED,
    
    -- Set metadata
    set_type VARCHAR(50)                      -- 'working', 'warmup', 'backoff', 'amrap', 'drop'
        CHECK (set_type IN ('working', 'warmup', 'backoff', 'amrap', 'drop', 'cluster', 'rest_pause')),
    tempo VARCHAR(20),                        -- Actual tempo used
    rest_seconds INT,                         -- Actual rest taken
    
    -- Deviation tracking
    is_deviation BOOLEAN DEFAULT FALSE,
    deviation_reason VARCHAR(50)              -- 'fatigue', 'pain', 'equipment', 'time', 'technique'
        CHECK (deviation_reason IS NULL OR deviation_reason IN (
            'fatigue', 'pain', 'equipment', 'time', 'technique', 'other'
        )),
    notes TEXT,
    
    -- Legacy reference
    legacy_neo4j_id VARCHAR(100),             -- Original Neo4j Set node id
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Session queries
CREATE INDEX IF NOT EXISTS idx_strength_sessions_date ON strength_sessions(session_date DESC);
CREATE INDEX IF NOT EXISTS idx_strength_sessions_block ON strength_sessions(block_id);
CREATE INDEX IF NOT EXISTS idx_strength_sessions_plan ON strength_sessions(plan_id);
CREATE INDEX IF NOT EXISTS idx_strength_sessions_neo4j ON strength_sessions(neo4j_id);
CREATE INDEX IF NOT EXISTS idx_strength_sessions_legacy ON strength_sessions(legacy_neo4j_id);

-- Set queries
CREATE INDEX IF NOT EXISTS idx_strength_sets_session ON strength_sets(session_id);
CREATE INDEX IF NOT EXISTS idx_strength_sets_exercise ON strength_sets(exercise_id);
CREATE INDEX IF NOT EXISTS idx_strength_sets_exercise_name ON strength_sets(exercise_name);
CREATE INDEX IF NOT EXISTS idx_strength_sets_date_exercise ON strength_sets(session_id, exercise_id);

-- Analytics queries
CREATE INDEX IF NOT EXISTS idx_strength_sets_for_progression ON strength_sets(exercise_id, session_id);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get recent strength sessions
CREATE OR REPLACE FUNCTION recent_strength_sessions(
    days_back INT DEFAULT 14
)
RETURNS TABLE (
    id INT,
    session_date DATE,
    name VARCHAR,
    duration_minutes INT,
    total_volume_lbs DECIMAL,
    total_sets INT,
    total_reps INT,
    session_rpe INT,
    status VARCHAR,
    neo4j_id VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ss.id,
        ss.session_date,
        ss.name,
        ss.duration_minutes,
        ss.total_volume_lbs,
        ss.total_sets,
        ss.total_reps,
        ss.session_rpe,
        ss.status,
        ss.neo4j_id
    FROM strength_sessions ss
    WHERE ss.session_date >= CURRENT_DATE - days_back
    ORDER BY ss.session_date DESC, ss.created_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Get sets for a session
CREATE OR REPLACE FUNCTION sets_for_session(
    p_session_id INT
)
RETURNS TABLE (
    id INT,
    set_order INT,
    block_name VARCHAR,
    exercise_name VARCHAR,
    reps INT,
    load_lbs DECIMAL,
    rpe INT,
    volume_lbs DECIMAL,
    is_deviation BOOLEAN,
    notes TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        st.id,
        st.set_order,
        st.block_name,
        st.exercise_name,
        st.reps,
        st.load_lbs,
        st.rpe,
        st.volume_lbs,
        st.is_deviation,
        st.notes
    FROM strength_sets st
    WHERE st.session_id = p_session_id
    ORDER BY st.set_order;
END;
$$ LANGUAGE plpgsql;

-- Get exercise history (for progression tracking)
CREATE OR REPLACE FUNCTION exercise_history(
    p_exercise_id VARCHAR,
    p_days_back INT DEFAULT 180
)
RETURNS TABLE (
    session_date DATE,
    session_name VARCHAR,
    set_order INT,
    reps INT,
    load_lbs DECIMAL,
    rpe INT,
    volume_lbs DECIMAL,
    estimated_1rm DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ss.session_date,
        ss.name as session_name,
        st.set_order,
        st.reps,
        st.load_lbs,
        st.rpe,
        st.volume_lbs,
        -- Brzycki formula for estimated 1RM
        CASE 
            WHEN st.reps > 0 AND st.reps <= 10 AND st.load_lbs > 0
            THEN ROUND((st.load_lbs * (36.0 / (37.0 - st.reps)))::NUMERIC, 1)
            ELSE NULL
        END as estimated_1rm
    FROM strength_sets st
    JOIN strength_sessions ss ON st.session_id = ss.id
    WHERE st.exercise_id = p_exercise_id
      AND ss.session_date >= CURRENT_DATE - p_days_back
    ORDER BY ss.session_date DESC, st.set_order;
END;
$$ LANGUAGE plpgsql;

-- Get PR (personal record) for an exercise
CREATE OR REPLACE FUNCTION exercise_pr(
    p_exercise_id VARCHAR
)
RETURNS TABLE (
    pr_type VARCHAR,
    value DECIMAL,
    reps INT,
    session_date DATE,
    session_name VARCHAR
) AS $$
BEGIN
    -- Max weight (any reps)
    RETURN QUERY
    SELECT 
        'max_weight'::VARCHAR as pr_type,
        MAX(st.load_lbs) as value,
        (SELECT st2.reps FROM strength_sets st2 
         JOIN strength_sessions ss2 ON st2.session_id = ss2.id
         WHERE st2.exercise_id = p_exercise_id 
         AND st2.load_lbs = MAX(st.load_lbs)
         ORDER BY ss2.session_date DESC LIMIT 1) as reps,
        (SELECT ss2.session_date FROM strength_sets st2 
         JOIN strength_sessions ss2 ON st2.session_id = ss2.id
         WHERE st2.exercise_id = p_exercise_id 
         AND st2.load_lbs = MAX(st.load_lbs)
         ORDER BY ss2.session_date DESC LIMIT 1) as session_date,
        (SELECT ss2.name FROM strength_sets st2 
         JOIN strength_sessions ss2 ON st2.session_id = ss2.id
         WHERE st2.exercise_id = p_exercise_id 
         AND st2.load_lbs = MAX(st.load_lbs)
         ORDER BY ss2.session_date DESC LIMIT 1) as session_name
    FROM strength_sets st
    WHERE st.exercise_id = p_exercise_id
      AND st.load_lbs IS NOT NULL;
    
    -- Max estimated 1RM
    RETURN QUERY
    SELECT 
        'estimated_1rm'::VARCHAR as pr_type,
        MAX(ROUND((st.load_lbs * (36.0 / (37.0 - st.reps)))::NUMERIC, 1)) as value,
        NULL::INT as reps,
        NULL::DATE as session_date,
        NULL::VARCHAR as session_name
    FROM strength_sets st
    WHERE st.exercise_id = p_exercise_id
      AND st.reps > 0 AND st.reps <= 10
      AND st.load_lbs > 0;
    
    -- Max volume single set
    RETURN QUERY
    SELECT 
        'max_set_volume'::VARCHAR as pr_type,
        MAX(st.volume_lbs) as value,
        (SELECT st2.reps FROM strength_sets st2 
         WHERE st2.exercise_id = p_exercise_id 
         AND st2.volume_lbs = MAX(st.volume_lbs)
         LIMIT 1) as reps,
        NULL::DATE as session_date,
        NULL::VARCHAR as session_name
    FROM strength_sets st
    WHERE st.exercise_id = p_exercise_id;
END;
$$ LANGUAGE plpgsql;

-- Calculate session totals (call after inserting sets)
CREATE OR REPLACE FUNCTION update_session_totals(
    p_session_id INT
)
RETURNS VOID AS $$
BEGIN
    UPDATE strength_sessions ss
    SET 
        total_volume_lbs = agg.total_volume,
        total_sets = agg.set_count,
        total_reps = agg.rep_count,
        avg_rpe = agg.avg_rpe,
        max_rpe = agg.max_rpe,
        updated_at = NOW()
    FROM (
        SELECT 
            session_id,
            SUM(volume_lbs) as total_volume,
            COUNT(*) as set_count,
            SUM(reps) as rep_count,
            ROUND(AVG(rpe)::NUMERIC, 1) as avg_rpe,
            MAX(rpe) as max_rpe
        FROM strength_sets
        WHERE session_id = p_session_id
        GROUP BY session_id
    ) agg
    WHERE ss.id = agg.session_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Weekly volume by movement pattern (requires join to Neo4j exercise data)
-- This is a simplified version using exercise_name patterns
CREATE OR REPLACE VIEW weekly_strength_volume AS
SELECT 
    DATE_TRUNC('week', ss.session_date)::DATE as week_start,
    COUNT(DISTINCT ss.id) as sessions,
    COUNT(st.id) as total_sets,
    SUM(st.reps) as total_reps,
    ROUND(SUM(st.volume_lbs)::NUMERIC, 0) as total_volume_lbs,
    ROUND(AVG(st.rpe)::NUMERIC, 1) as avg_rpe
FROM strength_sessions ss
JOIN strength_sets st ON ss.id = st.session_id
WHERE ss.status = 'completed'
GROUP BY DATE_TRUNC('week', ss.session_date)
ORDER BY week_start DESC;

-- Exercise frequency (which exercises most often)
CREATE OR REPLACE VIEW exercise_frequency AS
SELECT 
    st.exercise_id,
    st.exercise_name,
    COUNT(DISTINCT ss.id) as session_count,
    COUNT(st.id) as total_sets,
    SUM(st.reps) as total_reps,
    ROUND(AVG(st.load_lbs)::NUMERIC, 1) as avg_load,
    MAX(st.load_lbs) as max_load,
    MIN(ss.session_date) as first_logged,
    MAX(ss.session_date) as last_logged
FROM strength_sets st
JOIN strength_sessions ss ON st.session_id = ss.id
GROUP BY st.exercise_id, st.exercise_name
ORDER BY session_count DESC;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE strength_sessions IS 'Executed strength training sessions. Source of truth per ADR-002. Plans live in Neo4j, executions live here.';
COMMENT ON TABLE strength_sets IS 'Individual sets within strength sessions. Supports both planned (prescribed_*) and actual execution tracking.';

COMMENT ON COLUMN strength_sessions.block_id IS 'FK to Neo4j Block node (training phase context)';
COMMENT ON COLUMN strength_sessions.plan_id IS 'FK to Neo4j PlannedWorkout if this session was from a plan';
COMMENT ON COLUMN strength_sessions.legacy_neo4j_id IS 'Original Neo4j Workout.id before migration - for traceability';

COMMENT ON COLUMN strength_sets.exercise_id IS 'FK to Neo4j Exercise node. Exercise ontology stays in graph.';
COMMENT ON COLUMN strength_sets.exercise_name IS 'Denormalized for query convenience - avoids Neo4j lookup for basic queries';
COMMENT ON COLUMN strength_sets.reps IS 'Computed: COALESCE(actual_reps, prescribed_reps)';
COMMENT ON COLUMN strength_sets.load_lbs IS 'Computed: COALESCE(actual_load_lbs, prescribed_load_lbs)';
COMMENT ON COLUMN strength_sets.volume_lbs IS 'Computed: reps * load_lbs';

-- ============================================================================
-- MIGRATION TRACKING
-- ============================================================================

-- Track migration status
CREATE TABLE IF NOT EXISTS _migration_status (
    migration_name VARCHAR(100) PRIMARY KEY,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    records_migrated INT,
    notes TEXT
);

INSERT INTO _migration_status (migration_name, started_at, notes)
VALUES ('010_strength_workouts', NOW(), 'Schema created, data migration pending')
ON CONFLICT (migration_name) DO NOTHING;
