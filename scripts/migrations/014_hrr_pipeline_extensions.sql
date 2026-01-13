-- Migration 014: HRR Pipeline Extensions
-- Created: 2026-01-12
-- Purpose: Add columns for HRR trend detection pipeline (ADR-005)
-- Extends hr_recovery_intervals with confidence scoring, quality flags, and protocol metadata

-- =============================================================================
-- NEW COLUMNS
-- =============================================================================

-- Confidence scoring components
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS confidence NUMERIC(4,3);  -- 0.000 to 1.000

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS weighted_hrr60 NUMERIC(5,2);  -- hrr60 × confidence

-- Quality flag for trend detection (R² >= 0.75)
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS actionable BOOLEAN DEFAULT TRUE;

-- Protocol metadata
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS recovery_posture VARCHAR(20);  -- standing, supine, seated, walking

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS protocol_type VARCHAR(20);  -- inter_set, end_of_session, dedicated

-- Stratum for per-context baselines
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS stratum VARCHAR(20);  -- STRENGTH, ENDURANCE, OTHER

-- Local baseline (pre-peak context)
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS local_baseline_hr SMALLINT;  -- Median HR -180s to -60s before peak

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS peak_minus_local SMALLINT;  -- hr_peak - local_baseline_hr (effort proxy)

-- Early slope (first 15 seconds, more sensitive than 60s slope)
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS early_slope NUMERIC(5,3);  -- bpm/sec, negative = recovery

-- Extended recovery for dedicated protocols
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hr_180s SMALLINT;

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hr_300s SMALLINT;

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hrr180_abs SMALLINT;

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hrr300_abs SMALLINT;

-- =============================================================================
-- INDEXES FOR TREND DETECTION QUERIES
-- =============================================================================

-- Actionable readings only (the common case)
CREATE INDEX IF NOT EXISTS idx_hr_recovery_actionable 
ON hr_recovery_intervals(start_time) 
WHERE actionable = TRUE;

-- Per-stratum queries
CREATE INDEX IF NOT EXISTS idx_hr_recovery_stratum 
ON hr_recovery_intervals(stratum, start_time);

-- Posture-specific queries (don't mix standing and supine in same EWMA)
CREATE INDEX IF NOT EXISTS idx_hr_recovery_posture 
ON hr_recovery_intervals(recovery_posture, start_time) 
WHERE recovery_posture IS NOT NULL;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON COLUMN hr_recovery_intervals.confidence IS 
'Composite confidence score 0-1: weighted combination of effort magnitude, normalized recovery, R² fit quality, and window completeness (ADR-005)';

COMMENT ON COLUMN hr_recovery_intervals.weighted_hrr60 IS 
'hrr60_abs × confidence — used for EWMA/CUSUM trend detection';

COMMENT ON COLUMN hr_recovery_intervals.actionable IS 
'TRUE if R² >= 0.75 (tau_fit_r2). Low R² readings excluded from trend alerts but retained for analysis';

COMMENT ON COLUMN hr_recovery_intervals.recovery_posture IS 
'Body position during recovery: standing (inter-set), supine (dedicated protocol), seated, walking';

COMMENT ON COLUMN hr_recovery_intervals.protocol_type IS 
'Measurement context: inter_set (during workout), end_of_session, dedicated (weekly 5-min protocol)';

COMMENT ON COLUMN hr_recovery_intervals.stratum IS 
'Training context for per-stratum baselines: STRENGTH, ENDURANCE, OTHER. Do not mix in trend detection';

COMMENT ON COLUMN hr_recovery_intervals.local_baseline_hr IS 
'Median HR from -180s to -60s before peak. More accurate effort calculation than session minimum';

COMMENT ON COLUMN hr_recovery_intervals.peak_minus_local IS 
'hr_peak - local_baseline_hr. Effort proxy for confidence scoring';

COMMENT ON COLUMN hr_recovery_intervals.early_slope IS 
'Linear slope of first 15 seconds in bpm/sec. More sensitive early indicator than 60s metrics';

-- =============================================================================
-- VIEW: Actionable HRR for coaching queries
-- =============================================================================

CREATE OR REPLACE VIEW hrr_actionable AS
SELECT 
    id,
    polar_session_id,
    endurance_session_id,
    start_time,
    stratum,
    recovery_posture,
    protocol_type,
    
    -- Core metrics
    hr_peak,
    local_baseline_hr,
    peak_minus_local,
    hrr30_abs AS hrr30,
    hrr60_abs AS hrr60,
    hrr60_frac AS hrr_frac,
    early_slope,
    
    -- Quality
    tau_fit_r2 AS r2_60,
    confidence,
    weighted_hrr60,
    
    -- Extended (for dedicated protocols)
    hrr180_abs AS hrr180,
    hrr300_abs AS hrr300,
    tau_seconds AS tau,
    
    -- Context
    session_type,
    duration_seconds AS window_seconds
    
FROM hr_recovery_intervals
WHERE actionable = TRUE;

COMMENT ON VIEW hrr_actionable IS 
'High-quality HRR readings (R² >= 0.75) for EWMA/CUSUM trend detection. Filters out low-confidence measurements.';

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
