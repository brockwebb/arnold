-- Migration 009: Journal / Logbook System
-- 
-- Captures subjective data that sensors can't: fatigue, soreness, nutrition,
-- stress, mental state, supplement experiments, medication effects.
--
-- Per ADR-001: Postgres is source of truth for measurements/facts.
-- Journal entries are facts about subjective experience.
--
-- See GitHub Issue #7 for full design.

-- ============================================================================
-- LOG ENTRIES (Core journal table)
-- ============================================================================

CREATE TABLE IF NOT EXISTS log_entries (
    id SERIAL PRIMARY KEY,
    
    -- Timing
    entry_date DATE NOT NULL,                 -- Date being described
    entry_time TIME,                          -- Optional time of day
    recorded_at TIMESTAMP DEFAULT NOW(),      -- When entry was created
    
    -- Classification
    entry_type VARCHAR(50) NOT NULL,          -- 'observation', 'nutrition', 'supplement', 'symptom', 'mood', 'feedback'
    category VARCHAR(50),                     -- 'recovery', 'nutrition', 'mental', 'physical', 'medical', 'training'
    severity VARCHAR(20) DEFAULT 'info',      -- 'info', 'notable', 'concerning', 'urgent'
    
    -- Content
    raw_text TEXT NOT NULL,                   -- Original input (always preserve)
    extracted JSONB,                          -- LLM-parsed structured data
    summary VARCHAR(500),                     -- Brief summary for lists/reports
    
    -- Neo4j cross-reference (relationships live in graph)
    neo4j_id VARCHAR(100),                    -- UUID from Neo4j LogEntry node
    
    -- Organization
    tags TEXT[],                              -- For retrieval: ['fatigue', 'legs', 'post_surgery']
    source VARCHAR(50) DEFAULT 'chat',        -- 'chat', 'email', 'voice', 'manual'
    
    -- Review status
    reviewed BOOLEAN DEFAULT FALSE,           -- Coach/Doc has seen this
    reviewed_at TIMESTAMP,
    review_notes TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_log_entries_date ON log_entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_log_entries_type ON log_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_log_entries_category ON log_entries(category);
CREATE INDEX IF NOT EXISTS idx_log_entries_severity ON log_entries(severity);
CREATE INDEX IF NOT EXISTS idx_log_entries_tags ON log_entries USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_log_entries_unreviewed ON log_entries(reviewed) WHERE reviewed = FALSE;
CREATE INDEX IF NOT EXISTS idx_log_entries_neo4j ON log_entries(neo4j_id);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get recent log entries
CREATE OR REPLACE FUNCTION recent_log_entries(days_back INT DEFAULT 7)
RETURNS TABLE (
    id INT,
    entry_date DATE,
    entry_type VARCHAR,
    category VARCHAR,
    severity VARCHAR,
    summary VARCHAR,
    tags TEXT[],
    reviewed BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        le.id,
        le.entry_date,
        le.entry_type,
        le.category,
        le.severity,
        le.summary,
        le.tags,
        le.reviewed
    FROM log_entries le
    WHERE le.entry_date >= CURRENT_DATE - days_back
    ORDER BY le.entry_date DESC, le.recorded_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Get entries by severity (for alerts)
CREATE OR REPLACE FUNCTION entries_by_severity(min_severity VARCHAR DEFAULT 'notable')
RETURNS TABLE (
    id INT,
    entry_date DATE,
    entry_type VARCHAR,
    severity VARCHAR,
    summary VARCHAR,
    raw_text TEXT,
    reviewed BOOLEAN
) AS $$
DECLARE
    severity_order TEXT[] := ARRAY['info', 'notable', 'concerning', 'urgent'];
    min_idx INT;
BEGIN
    min_idx := array_position(severity_order, min_severity);
    
    RETURN QUERY
    SELECT 
        le.id,
        le.entry_date,
        le.entry_type,
        le.severity,
        le.summary,
        le.raw_text,
        le.reviewed
    FROM log_entries le
    WHERE array_position(severity_order, le.severity) >= min_idx
    ORDER BY array_position(severity_order, le.severity) DESC, le.entry_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Get unreviewed entries (for coach/doc briefing)
CREATE OR REPLACE FUNCTION unreviewed_entries()
RETURNS TABLE (
    id INT,
    entry_date DATE,
    entry_type VARCHAR,
    category VARCHAR,
    severity VARCHAR,
    summary VARCHAR,
    raw_text TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        le.id,
        le.entry_date,
        le.entry_type,
        le.category,
        le.severity,
        le.summary,
        le.raw_text
    FROM log_entries le
    WHERE le.reviewed = FALSE
    ORDER BY 
        CASE le.severity 
            WHEN 'urgent' THEN 1 
            WHEN 'concerning' THEN 2 
            WHEN 'notable' THEN 3 
            ELSE 4 
        END,
        le.entry_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Mark entry as reviewed
CREATE OR REPLACE FUNCTION mark_reviewed(
    p_entry_id INT,
    p_notes TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE log_entries
    SET reviewed = TRUE,
        reviewed_at = NOW(),
        review_notes = COALESCE(p_notes, review_notes),
        updated_at = NOW()
    WHERE id = p_entry_id;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE log_entries IS 'Subjective journal entries - fatigue, soreness, symptoms, nutrition, mood. Facts live here, relationships in Neo4j. See Issue #7 and ADR-001.';
COMMENT ON COLUMN log_entries.raw_text IS 'Always preserve original input for traceability.';
COMMENT ON COLUMN log_entries.extracted IS 'LLM-parsed structured data: {fatigue: 8, soreness: [{area: legs, level: 8}], etc.}';
COMMENT ON COLUMN log_entries.neo4j_id IS 'Cross-reference to Neo4j LogEntry node for relationship queries.';
COMMENT ON COLUMN log_entries.severity IS 'info=routine, notable=worth tracking, concerning=needs attention, urgent=immediate action';

-- ============================================================================
-- NEO4J RELATIONSHIP PATTERNS (for reference - implemented in Neo4j)
-- ============================================================================
--
-- (:LogEntry)-[:EXPLAINS]->(:Workout|:EnduranceWorkout|:StrengthWorkout)
--   Entry explains what happened during a past workout
--
-- (:LogEntry)-[:AFFECTS]->(:PlannedWorkout)
--   Entry should influence a future plan
--
-- (:LogEntry)-[:DOCUMENTS]->(:Symptom)
--   Entry documents a symptom pattern
--
-- (:LogEntry)-[:MENTIONS]->(:Supplement|:Medication)
--   Entry mentions starting/stopping/effects of supplements
--
-- (:LogEntry)-[:RELATED_TO]->(:Injury)
--   Entry relates to an injury (pain, recovery progress)
--
-- (:LogEntry)-[:INFORMS]->(:Goal)
--   Entry provides insight relevant to a goal
--
-- (:LogEntry)-[:INSTANCE_OF]->(:Pattern)
--   Entry is an instance of a recurring pattern
--
