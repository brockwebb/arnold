-- Migration 008: Endurance Sessions (Postgres-first per ADR-001)
-- 
-- FIT file imports (Suunto, Garmin, Wahoo) are source of truth in Postgres.
-- Neo4j holds lightweight reference nodes for relationship queries.
--
-- This aligns with ADR-001: Data Layer Separation
--   - Postgres = measurements, facts, time-series (LEFT BRAIN)
--   - Neo4j = relationships, semantics, knowledge (RIGHT BRAIN)

-- ============================================================================
-- ENDURANCE SESSIONS (Source of Truth for FIT imports)
-- ============================================================================

CREATE TABLE IF NOT EXISTS endurance_sessions (
    id SERIAL PRIMARY KEY,
    
    -- Identity
    session_date DATE NOT NULL,
    session_time TIME,                        -- Start time of day
    name VARCHAR(255),                        -- "Long Run - Odenton Loop"
    sport VARCHAR(50) NOT NULL,               -- 'running', 'cycling', 'swimming'
    
    -- Source tracking
    source VARCHAR(50) NOT NULL,              -- 'suunto', 'garmin', 'polar', 'wahoo'
    source_file VARCHAR(255),                 -- Original filename
    
    -- Distance / Duration
    distance_miles DECIMAL(6,2),
    distance_meters DECIMAL(10,1),
    duration_seconds INT,
    duration_minutes DECIMAL(8,1) GENERATED ALWAYS AS (duration_seconds / 60.0) STORED,
    avg_pace VARCHAR(20),                     -- "11:13/mi"
    
    -- Heart Rate
    avg_hr INT,
    max_hr INT,
    min_hr INT,
    
    -- Elevation
    elevation_gain_m INT,
    elevation_loss_m INT,
    max_altitude_m DECIMAL(7,1),
    min_altitude_m DECIMAL(7,1),
    
    -- Cadence
    avg_cadence INT,                          -- steps/min for running
    max_cadence INT,
    
    -- Calories
    calories INT,
    
    -- Training Load (computed by device)
    tss DECIMAL(5,1),                         -- Training Stress Score
    training_effect DECIMAL(3,1),             -- Aerobic training effect (1.0-5.0)
    recovery_time_hours DECIMAL(5,1),         -- Suggested recovery (hours)
    
    -- Subjective (added post-import)
    rpe INT CHECK (rpe BETWEEN 1 AND 10),     -- Rate of Perceived Exertion
    notes TEXT,                               -- Rich notes from athlete
    weather_actual VARCHAR(100),              -- Corrected weather (watch sensor lies)
    tags TEXT[],                              -- ['long_run', 'post_surgery', 'fatigued']
    
    -- Metadata
    imported_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Neo4j cross-reference (lightweight bridge)
    neo4j_id VARCHAR(100),                    -- UUID from Neo4j reference node
    
    -- Deduplication constraint
    UNIQUE(session_date, distance_miles, duration_seconds)
);

-- ============================================================================
-- ENDURANCE LAPS (Per-lap splits)
-- ============================================================================

CREATE TABLE IF NOT EXISTS endurance_laps (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES endurance_sessions(id) ON DELETE CASCADE,
    
    lap_number INT NOT NULL,
    
    -- Distance / Duration
    distance_miles DECIMAL(5,2),
    distance_meters DECIMAL(8,1),
    duration_seconds INT,
    pace VARCHAR(20),                         -- "10:32/mi"
    
    -- Heart Rate
    avg_hr INT,
    max_hr INT,
    
    -- Other
    avg_cadence INT,
    elevation_gain_m INT,
    calories INT,
    
    UNIQUE(session_id, lap_number)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_sessions_date ON endurance_sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_sessions_sport ON endurance_sessions(sport);
CREATE INDEX IF NOT EXISTS idx_sessions_source ON endurance_sessions(source);
CREATE INDEX IF NOT EXISTS idx_laps_session ON endurance_laps(session_id);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get recent endurance sessions
CREATE OR REPLACE FUNCTION recent_endurance_sessions(days_back INT DEFAULT 30)
RETURNS TABLE (
    session_date DATE,
    name VARCHAR,
    sport VARCHAR,
    distance_miles DECIMAL,
    duration_minutes DECIMAL,
    avg_hr INT,
    tss DECIMAL,
    rpe INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        es.session_date,
        es.name,
        es.sport,
        es.distance_miles,
        es.duration_minutes,
        es.avg_hr,
        es.tss,
        es.rpe
    FROM endurance_sessions es
    WHERE es.session_date >= CURRENT_DATE - days_back
    ORDER BY es.session_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Get endurance training load summary
CREATE OR REPLACE FUNCTION endurance_training_load(days_back INT DEFAULT 28)
RETURNS TABLE (
    total_distance DECIMAL,
    total_duration_hours DECIMAL,
    total_tss DECIMAL,
    session_count BIGINT,
    avg_tss_per_session DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        SUM(es.distance_miles)::DECIMAL as total_distance,
        (SUM(es.duration_seconds) / 3600.0)::DECIMAL as total_duration_hours,
        SUM(es.tss)::DECIMAL as total_tss,
        COUNT(*)::BIGINT as session_count,
        AVG(es.tss)::DECIMAL as avg_tss_per_session
    FROM endurance_sessions es
    WHERE es.session_date >= CURRENT_DATE - days_back;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE endurance_sessions IS 'Source of truth for FIT file imports (Suunto, Garmin, Wahoo). Neo4j holds lightweight reference for relationships. See ADR-001.';
COMMENT ON TABLE endurance_laps IS 'Per-lap splits from endurance sessions. FK to endurance_sessions.';
COMMENT ON COLUMN endurance_sessions.neo4j_id IS 'Cross-reference to Neo4j EnduranceWorkout node for graph queries.';
COMMENT ON COLUMN endurance_sessions.weather_actual IS 'Corrected weather - watch skin sensor is unreliable.';
