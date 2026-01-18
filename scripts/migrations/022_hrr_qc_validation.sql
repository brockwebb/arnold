-- Migration 022: HRR QC Validation Judgments
-- Algorithm validation: TP/FP/TN/FN classification for precision/recall
-- Date: 2026-01-18
-- Related: GitHub #30

-- Purpose: Track human judgments about algorithm accuracy for system validation.
-- This is NOT about overriding the algorithm - it's about measuring its accuracy.
-- Uses stable keys (session_id, interval_order) to survive re-extraction.

-- =============================================================================
-- SESSION-LEVEL QC STATUS
-- =============================================================================

-- Session review queue status (already partially in polar_sessions, let's add to endurance too)
ALTER TABLE endurance_sessions 
ADD COLUMN IF NOT EXISTS hrr_qc_status VARCHAR(20) DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS hrr_qc_reviewed_at TIMESTAMPTZ;

COMMENT ON COLUMN endurance_sessions.hrr_qc_status IS 'pending, in_progress, reviewed';

-- =============================================================================
-- INTERVAL-LEVEL QC JUDGMENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS hrr_qc_judgments (
    id SERIAL PRIMARY KEY,
    
    -- Stable keys (survive re-extraction)
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    endurance_session_id INTEGER REFERENCES endurance_sessions(id),
    interval_order SMALLINT NOT NULL,
    
    -- Human judgment for algorithm validation
    judgment VARCHAR(20) NOT NULL,  -- TP, FP, TN, FN_REJECTED, FN_MISSED, SKIP
    
    -- What the algorithm decided (snapshot at review time)
    algo_status VARCHAR(20),        -- pass, flagged, rejected
    algo_reject_reason TEXT,        -- auto_reject_reason snapshot
    
    -- Peak location accuracy
    peak_correct VARCHAR(10),       -- yes, no, shifted
    peak_shift_sec SMALLINT,        -- if shifted, by how much
    
    -- Human notes
    notes TEXT,
    
    -- Timestamps
    judged_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(polar_session_id, interval_order),
    UNIQUE(endurance_session_id, interval_order),
    CHECK (polar_session_id IS NOT NULL OR endurance_session_id IS NOT NULL),
    CHECK (judgment IN ('TP', 'FP', 'TN', 'FN_REJECTED', 'FN_MISSED', 'SKIP'))
);

CREATE INDEX IF NOT EXISTS idx_qc_judgments_polar ON hrr_qc_judgments(polar_session_id);
CREATE INDEX IF NOT EXISTS idx_qc_judgments_endurance ON hrr_qc_judgments(endurance_session_id);

COMMENT ON TABLE hrr_qc_judgments IS 'Algorithm validation judgments for HRR detection. Used to calculate precision/recall.';

COMMENT ON COLUMN hrr_qc_judgments.judgment IS 
    'TP = true positive (correctly found real peak), ' ||
    'FP = false positive (found fake peak), ' ||
    'TN = true negative (correctly rejected), ' ||
    'FN_REJECTED = false negative (real peak but algo rejected it), ' ||
    'FN_MISSED = false negative (algo missed peak entirely), ' ||
    'SKIP = cannot determine';

-- =============================================================================
-- MISSED PEAKS (FN_MISSED)
-- =============================================================================

-- When algorithm misses a peak entirely, we need to record where it should have been
CREATE TABLE IF NOT EXISTS hrr_missed_peaks (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    endurance_session_id INTEGER REFERENCES endurance_sessions(id),
    
    -- Location of missed peak (elapsed seconds from session start)
    peak_time_elapsed_sec INT NOT NULL,
    
    -- Approximate HR values (if known)
    hr_peak_approx SMALLINT,
    
    -- Notes
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CHECK (polar_session_id IS NOT NULL OR endurance_session_id IS NOT NULL)
);

COMMENT ON TABLE hrr_missed_peaks IS 'Peaks the algorithm missed entirely (FN_MISSED). Used for improving detection.';

-- =============================================================================
-- VALIDATION STATS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW hrr_qc_stats AS
WITH counts AS (
    SELECT 
        judgment,
        COUNT(*) as ct
    FROM hrr_qc_judgments
    GROUP BY judgment
),
pivoted AS (
    SELECT
        COALESCE(SUM(ct) FILTER (WHERE judgment = 'TP'), 0) as tp,
        COALESCE(SUM(ct) FILTER (WHERE judgment = 'FP'), 0) as fp,
        COALESCE(SUM(ct) FILTER (WHERE judgment = 'TN'), 0) as tn,
        COALESCE(SUM(ct) FILTER (WHERE judgment = 'FN_REJECTED'), 0) as fn_rejected,
        COALESCE(SUM(ct) FILTER (WHERE judgment = 'FN_MISSED'), 0) as fn_missed,
        COALESCE(SUM(ct) FILTER (WHERE judgment = 'SKIP'), 0) as skip,
        SUM(ct) as total
    FROM counts
)
SELECT 
    tp, fp, tn, fn_rejected, fn_missed, skip, total,
    (fn_rejected + fn_missed) as fn_total,
    
    -- Precision: of intervals marked 'pass', how many are real?
    CASE WHEN (tp + fp) > 0 
        THEN ROUND(tp::numeric / (tp + fp), 3) 
        ELSE NULL END as precision,
    
    -- Recall: of real peaks, how many marked 'pass'?
    CASE WHEN (tp + fn_rejected + fn_missed) > 0 
        THEN ROUND(tp::numeric / (tp + fn_rejected + fn_missed), 3) 
        ELSE NULL END as recall,
    
    -- F1 score
    CASE WHEN (tp + fp) > 0 AND (tp + fn_rejected + fn_missed) > 0
        THEN ROUND(
            2.0 * (tp::numeric / (tp + fp)) * (tp::numeric / (tp + fn_rejected + fn_missed)) /
            ((tp::numeric / (tp + fp)) + (tp::numeric / (tp + fn_rejected + fn_missed))), 3)
        ELSE NULL END as f1,
    
    -- Detection recall: of real peaks, how many detected at all?
    CASE WHEN (tp + fn_rejected + fn_missed) > 0
        THEN ROUND((tp + fn_rejected)::numeric / (tp + fn_rejected + fn_missed), 3)
        ELSE NULL END as detection_recall,
    
    -- Rejection accuracy: of rejected, how many should be?
    CASE WHEN (tn + fn_rejected) > 0
        THEN ROUND(tn::numeric / (tn + fn_rejected), 3)
        ELSE NULL END as rejection_accuracy

FROM pivoted;

COMMENT ON VIEW hrr_qc_stats IS 'Algorithm validation metrics: precision, recall, F1, detection recall, rejection accuracy';

-- =============================================================================
-- SESSION QC STATUS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW hrr_session_qc_queue AS
SELECT 
    'polar' as source,
    ps.id as session_id,
    ps.start_time::date as session_date,
    ps.sport_type,
    ps.hrr_qc_status,
    ps.hrr_qc_reviewed_at,
    COUNT(DISTINCT hri.id) as total_intervals,
    COUNT(DISTINCT hri.id) FILTER (WHERE hri.quality_status = 'pass') as pass_ct,
    COUNT(DISTINCT hri.id) FILTER (WHERE hri.quality_status = 'flagged') as flagged_ct,
    COUNT(DISTINCT hri.id) FILTER (WHERE hri.quality_status = 'rejected') as rejected_ct,
    COUNT(DISTINCT j.id) as judged_ct
FROM polar_sessions ps
LEFT JOIN hr_recovery_intervals hri ON hri.polar_session_id = ps.id
LEFT JOIN hrr_qc_judgments j ON j.polar_session_id = ps.id AND j.interval_order = hri.interval_order
WHERE EXISTS (SELECT 1 FROM hr_recovery_intervals WHERE polar_session_id = ps.id)
GROUP BY ps.id, ps.start_time, ps.sport_type, ps.hrr_qc_status, ps.hrr_qc_reviewed_at

UNION ALL

SELECT 
    'endurance' as source,
    es.id as session_id,
    es.session_date,
    es.sport as sport_type,
    es.hrr_qc_status,
    es.hrr_qc_reviewed_at,
    COUNT(DISTINCT hri.id) as total_intervals,
    COUNT(DISTINCT hri.id) FILTER (WHERE hri.quality_status = 'pass') as pass_ct,
    COUNT(DISTINCT hri.id) FILTER (WHERE hri.quality_status = 'flagged') as flagged_ct,
    COUNT(DISTINCT hri.id) FILTER (WHERE hri.quality_status = 'rejected') as rejected_ct,
    COUNT(DISTINCT j.id) as judged_ct
FROM endurance_sessions es
LEFT JOIN hr_recovery_intervals hri ON hri.endurance_session_id = es.id
LEFT JOIN hrr_qc_judgments j ON j.endurance_session_id = es.id AND j.interval_order = hri.interval_order
WHERE EXISTS (SELECT 1 FROM hr_recovery_intervals WHERE endurance_session_id = es.id)
GROUP BY es.id, es.session_date, es.sport, es.hrr_qc_status, es.hrr_qc_reviewed_at

ORDER BY session_date;

COMMENT ON VIEW hrr_session_qc_queue IS 'QC review queue showing sessions and their review status';
