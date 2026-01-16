-- Migration: HRR Quality Metrics and Human Verification Workflow
-- Date: 2026-01-15
-- Purpose: Store all computed quality metrics and enable human-in-loop verification
--
-- Philosophy: Algorithm proposes, human verifies. Every interval gets reviewed eventually.
-- This builds a research-quality dataset with full audit trail.

-- =============================================================================
-- SEGMENT R² METRICS (validated: 10.3% catch rate for masked problems)
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS r2_0_30 FLOAT;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS r2_30_60 FLOAT;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS r2_delta FLOAT;  -- r2_0_30 - r2_30_60

COMMENT ON COLUMN hr_recovery_intervals.r2_0_30 IS 'R² of exponential fit on first 30s - discriminating metric';
COMMENT ON COLUMN hr_recovery_intervals.r2_30_60 IS 'R² of exponential fit on 30-60s - discriminating metric';
COMMENT ON COLUMN hr_recovery_intervals.r2_delta IS 'r2_0_30 - r2_30_60; high delta with good overall R² = masked problem';

-- =============================================================================
-- LATE SLOPE METRICS (validated: weak signal, useful for HRR120)
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS slope_90_120 FLOAT;  -- bpm/sec
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS slope_90_120_r2 FLOAT;

COMMENT ON COLUMN hr_recovery_intervals.slope_90_120 IS 'Linear slope 90-120s (bpm/sec). >0.1 = hard fail, 0-0.1 = review';
COMMENT ON COLUMN hr_recovery_intervals.slope_90_120_r2 IS 'R² of linear fit for 90-120s slope';

-- =============================================================================
-- DETECTION FLAGS (peak=useful, valley=store only)
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS peak_detected BOOLEAN DEFAULT FALSE;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS valley_detected BOOLEAN DEFAULT FALSE;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS peak_count INT DEFAULT 0;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS valley_count INT DEFAULT 0;

COMMENT ON COLUMN hr_recovery_intervals.peak_detected IS 'SciPy peak detected in recovery window - hard fail signal';
COMMENT ON COLUMN hr_recovery_intervals.valley_detected IS 'SciPy valley detected - stored for research, not discriminating';

-- =============================================================================
-- FIT PARAMETERS (for paper reproducibility)
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS fit_amplitude FLOAT;  -- A in: A*exp(-t/tau) + C
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS fit_asymptote FLOAT;  -- C

COMMENT ON COLUMN hr_recovery_intervals.fit_amplitude IS 'Exponential fit amplitude (A) for reproducibility';
COMMENT ON COLUMN hr_recovery_intervals.fit_asymptote IS 'Exponential fit asymptote (C) for reproducibility';

-- =============================================================================
-- EXTRAPOLATION METRICS (continuous confidence)
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS extrap_residual_60 FLOAT;  -- actual - predicted at 60s
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS extrap_accumulated_error FLOAT;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS extrap_late_trend FLOAT;  -- slope of residuals 45-60s

COMMENT ON COLUMN hr_recovery_intervals.extrap_residual_60 IS 'Actual HR - predicted HR at 60s (from 0-30s fit extrapolation)';
COMMENT ON COLUMN hr_recovery_intervals.extrap_accumulated_error IS 'Sum of absolute residuals at checkpoints';
COMMENT ON COLUMN hr_recovery_intervals.extrap_late_trend IS 'Slope of residuals 45-60s; positive = fit deteriorating';

-- =============================================================================
-- PEAK IDENTIFICATION (for review workflow)
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS peak_label TEXT;  -- e.g., "S71:p03"
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS peak_sample_idx INT;  -- exact sample position in session

COMMENT ON COLUMN hr_recovery_intervals.peak_label IS 'Human-readable ID: session:peak_number (e.g., S71:p03)';
COMMENT ON COLUMN hr_recovery_intervals.peak_sample_idx IS 'Sample index in session for precise relocation';

-- =============================================================================
-- ALGORITHM QUALITY ASSESSMENT
-- =============================================================================
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS quality_status TEXT DEFAULT 'pending';
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS quality_flags TEXT[] DEFAULT '{}';
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS quality_score FLOAT;  -- 0-1 confidence
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS auto_reject_reason TEXT;

COMMENT ON COLUMN hr_recovery_intervals.quality_status IS 'Algorithm assessment: pending, pass, flagged, rejected';
COMMENT ON COLUMN hr_recovery_intervals.quality_flags IS 'Array of flag codes: late_discontinuity, peak_in_recovery, late_slope_positive, etc.';
COMMENT ON COLUMN hr_recovery_intervals.quality_score IS 'Continuous confidence score 0-1 for weighting in analytics';
COMMENT ON COLUMN hr_recovery_intervals.auto_reject_reason IS 'If auto-rejected, the primary reason';

-- =============================================================================
-- HUMAN VERIFICATION WORKFLOW
-- =============================================================================
-- Every interval needs human verification, even auto-rejected ones
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS human_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS verified_status TEXT;  -- confirmed, overridden_pass, overridden_fail
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS verification_notes TEXT;

-- Review queue management
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT TRUE;  -- all start needing review
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS review_priority INT DEFAULT 3;  -- 1=high, 2=medium, 3=low (spot check)

-- Final disposition (after human verification)
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS excluded BOOLEAN DEFAULT FALSE;
ALTER TABLE hr_recovery_intervals ADD COLUMN IF NOT EXISTS exclusion_reason TEXT;

COMMENT ON COLUMN hr_recovery_intervals.human_verified IS 'TRUE when a human has reviewed this interval';
COMMENT ON COLUMN hr_recovery_intervals.verified_status IS 'Human decision: confirmed (agree with algo), overridden_pass, overridden_fail';
COMMENT ON COLUMN hr_recovery_intervals.needs_review IS 'In review queue - all intervals start TRUE';
COMMENT ON COLUMN hr_recovery_intervals.review_priority IS '1=rejected/high-flag, 2=flagged, 3=passed (spot check)';
COMMENT ON COLUMN hr_recovery_intervals.excluded IS 'Final disposition: exclude from analytics';

-- =============================================================================
-- INDEXES FOR REVIEW WORKFLOW
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_hrr_needs_review ON hr_recovery_intervals(needs_review, review_priority) 
    WHERE needs_review = TRUE;
CREATE INDEX IF NOT EXISTS idx_hrr_human_verified ON hr_recovery_intervals(human_verified) 
    WHERE human_verified = FALSE;
CREATE INDEX IF NOT EXISTS idx_hrr_excluded ON hr_recovery_intervals(excluded);

-- =============================================================================
-- VIEW: Review Queue
-- =============================================================================
CREATE OR REPLACE VIEW hrr_review_queue AS
SELECT 
    id,
    peak_label,
    COALESCE(polar_session_id, endurance_session_id) as session_id,
    start_time,
    hr_peak,
    hrr60_abs,
    tau_fit_r2 as r2_full,
    r2_0_30,
    r2_30_60,
    r2_delta,
    slope_90_120,
    quality_status,
    quality_flags,
    quality_score,
    auto_reject_reason,
    review_priority,
    human_verified,
    verified_status
FROM hr_recovery_intervals
WHERE needs_review = TRUE
ORDER BY review_priority, start_time;

COMMENT ON VIEW hrr_review_queue IS 'Intervals awaiting human verification, ordered by priority';

-- =============================================================================
-- VIEW: Verified Clean Data (for analytics)
-- =============================================================================
CREATE OR REPLACE VIEW hrr_verified_clean AS
SELECT *
FROM hr_recovery_intervals
WHERE human_verified = TRUE
  AND excluded = FALSE
  AND (verified_status = 'confirmed' OR verified_status = 'overridden_pass');

COMMENT ON VIEW hrr_verified_clean IS 'Only human-verified, non-excluded intervals for analytics';

-- =============================================================================
-- FUNCTION: Mark interval as verified
-- =============================================================================
CREATE OR REPLACE FUNCTION verify_hrr_interval(
    p_interval_id INT,
    p_status TEXT,  -- 'confirmed', 'overridden_pass', 'overridden_fail'
    p_notes TEXT DEFAULT NULL,
    p_exclude BOOLEAN DEFAULT FALSE,
    p_exclusion_reason TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    UPDATE hr_recovery_intervals
    SET 
        human_verified = TRUE,
        verified_at = NOW(),
        verified_status = p_status,
        verification_notes = p_notes,
        needs_review = FALSE,
        excluded = p_exclude,
        exclusion_reason = p_exclusion_reason
    WHERE id = p_interval_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION verify_hrr_interval IS 'Mark an interval as human-verified with disposition';
