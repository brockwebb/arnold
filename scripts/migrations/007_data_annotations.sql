-- Migration 007: Data Annotations System
-- Purpose: Explain data gaps, outliers, and provide context
-- Created: 2026-01-04
--
-- ARCHITECTURE:
--   Neo4j = Source of truth (rich relationships to Workout, Injury, etc.)
--   Postgres = Analytics layer (time-series queries, materialized views)
--   Sync: scripts/sync_annotations.py runs in pipeline

-- =============================================================================
-- NEO4J SCHEMA (for reference - actual nodes created via Cypher)
-- =============================================================================
--
-- (:Annotation {
--     id: STRING,                    -- 'ann-' + uuid
--     annotation_date: DATE,
--     date_range_end: DATE | null,   -- null = ongoing
--     target_type: STRING,           -- 'biometric', 'workout', 'training', 'general'
--     target_metric: STRING,         -- 'hrv', 'sleep', 'all', etc.
--     reason_code: STRING,           -- See codes below
--     explanation: STRING,
--     tags: [STRING],
--     created_at: DATETIME,
--     created_by: STRING,
--     is_active: BOOLEAN
-- })
--
-- Relationships:
--   (Person)-[:HAS_ANNOTATION]->(Annotation)
--   (Annotation)-[:EXPLAINS {relationship_type}]->(Workout|Injury|PlannedWorkout)
--

-- =============================================================================
-- Table: data_annotations
-- =============================================================================

CREATE TABLE IF NOT EXISTS data_annotations (
    id SERIAL PRIMARY KEY,
    
    -- When does this annotation apply?
    annotation_date DATE NOT NULL,
    date_range_end DATE,                     -- NULL = ongoing or single day
    
    -- What does it annotate?
    target_type VARCHAR(50) NOT NULL,        -- 'biometric', 'workout', 'training', 'general'
    target_metric VARCHAR(50),               -- 'hrv', 'sleep', 'rhr', 'volume', 'all', etc.
    target_id VARCHAR(100),                  -- Optional: specific workout_id, reading_id, etc.
    
    -- Why?
    reason_code VARCHAR(50) NOT NULL,        -- See reason codes below
    explanation TEXT NOT NULL,               -- Human-readable context
    
    -- Metadata
    tags TEXT[],                             -- For retrieval: ['ring', 'sleep', 'gap']
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50) DEFAULT 'user',
    
    -- Soft delete
    is_active BOOLEAN DEFAULT TRUE
);

-- =============================================================================
-- Reason Codes (documented, not enforced)
-- =============================================================================
-- device_issue   : Sensor malfunction, app not syncing, battery dead
-- travel         : Away from home, different timezone, equipment unavailable
-- illness        : Sick, recovery from illness
-- surgery        : Medical procedure, post-op recovery
-- injury         : Active injury affecting training
-- event          : Race, competition, special occasion
-- expected       : Normal/expected variation (e.g., HRV drop after hard workout)
-- data_quality   : Known data issue, source confusion, cleanup note
-- deload         : Planned recovery week
-- life           : Work stress, family, schedule disruption

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_annotation_date_range 
    ON data_annotations(annotation_date, date_range_end);
CREATE INDEX IF NOT EXISTS idx_annotation_target 
    ON data_annotations(target_type, target_metric);
CREATE INDEX IF NOT EXISTS idx_annotation_reason 
    ON data_annotations(reason_code);
CREATE INDEX IF NOT EXISTS idx_annotation_tags 
    ON data_annotations USING GIN(tags);

-- =============================================================================
-- Function: annotations_for_date(DATE)
-- Returns all active annotations that apply to a specific date
-- =============================================================================

CREATE OR REPLACE FUNCTION annotations_for_date(check_date DATE)
RETURNS TABLE (
    id INT,
    target_type VARCHAR(50),
    target_metric VARCHAR(50),
    reason_code VARCHAR(50),
    explanation TEXT,
    annotation_date DATE,
    date_range_end DATE,
    is_ongoing BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.target_type,
        a.target_metric,
        a.reason_code,
        a.explanation,
        a.annotation_date,
        a.date_range_end,
        (a.date_range_end IS NULL AND a.annotation_date <= check_date) as is_ongoing
    FROM data_annotations a
    WHERE a.is_active = TRUE
      AND a.annotation_date <= check_date
      AND (a.date_range_end IS NULL OR a.date_range_end >= check_date)
    ORDER BY a.annotation_date DESC;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- View: active_data_issues
-- Current issues that should be surfaced in coach brief
-- =============================================================================

CREATE OR REPLACE VIEW active_data_issues AS
SELECT 
    target_metric,
    reason_code,
    explanation,
    annotation_date,
    date_range_end,
    CASE 
        WHEN date_range_end IS NULL THEN 'ongoing'
        ELSE 'bounded'
    END as issue_status,
    CURRENT_DATE - annotation_date as days_active
FROM data_annotations
WHERE is_active = TRUE
  AND (date_range_end IS NULL OR date_range_end >= CURRENT_DATE)
  AND annotation_date <= CURRENT_DATE
ORDER BY 
    CASE WHEN date_range_end IS NULL THEN 0 ELSE 1 END,
    annotation_date DESC;

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE data_annotations IS 'Context and explanations for data gaps, outliers, and anomalies. Reduces false positives in alerting and provides coach with situational awareness.';
COMMENT ON COLUMN data_annotations.date_range_end IS 'NULL means ongoing issue or single-day annotation';
COMMENT ON COLUMN data_annotations.target_id IS 'Optional foreign key to specific record (workout_id, etc.)';
COMMENT ON COLUMN data_annotations.reason_code IS 'Categorization for filtering. See migration comments for valid codes.';
