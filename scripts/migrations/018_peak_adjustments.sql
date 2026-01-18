-- Migration 018: Peak Adjustments Table
-- Manual overrides for HRR peak detection when auto-detection fails
-- Date: 2026-01-17

-- When to use:
-- - QC viz shows rejected interval with valid-looking recovery offset from detected peak
-- - r2_30_60 fails but visual inspection shows clean decay starting later
-- - Double-peak pattern where scipy detected first (false) peak
-- - Plateau-to-decline not caught by automatic re-anchoring

CREATE TABLE IF NOT EXISTS peak_adjustments (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER NOT NULL REFERENCES polar_sessions(id),
    interval_order SMALLINT NOT NULL,  -- which detected peak (1-indexed)
    shift_seconds SMALLINT NOT NULL,   -- positive = shift later (right)
    reason TEXT,                        -- documentation
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,             -- set when extraction uses this
    UNIQUE(polar_session_id, interval_order)
);

-- Index for lookup during extraction
CREATE INDEX IF NOT EXISTS idx_peak_adj_polar 
ON peak_adjustments(polar_session_id);

COMMENT ON TABLE peak_adjustments IS 'Manual overrides for peak detection. Applied during HRR feature extraction.';
COMMENT ON COLUMN peak_adjustments.shift_seconds IS 'Seconds to shift peak. Positive = later in time (right on timeline).';
COMMENT ON COLUMN peak_adjustments.applied_at IS 'Set by extraction script when adjustment is used. NULL = pending.';

-- Workflow:
-- 1. Identify problem via QC viz: python scripts/hrr_qc_viz.py --session-id 51
-- 2. Estimate shift in seconds from visualization
-- 3. INSERT INTO peak_adjustments (polar_session_id, interval_order, shift_seconds, reason)
--    VALUES (51, 3, 54, 'False peak - real recovery starts ~54s later');
-- 4. Reprocess: python scripts/hrr_feature_extraction.py --session-id 51
-- 5. Verify with QC viz again. Adjust if needed:
--    UPDATE peak_adjustments SET shift_seconds = 60 WHERE polar_session_id = 51 AND interval_order = 3;

-- Quality flag: Intervals with manual adjustments get MANUAL_ADJUSTED in quality_flags
