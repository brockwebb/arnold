-- Migration 020: HRR Quality Overrides Table
-- Stable-keyed human review decisions that persist through re-extraction
-- Date: 2026-01-17

-- Problem: hrr_interval_reviews uses interval_id FK which is volatile.
-- When extraction re-runs, intervals get deleted/recreated with new IDs.
-- This table uses (polar_session_id, interval_order) like peak_adjustments.

-- When to use:
-- - Auto-reject that visual inspection shows is valid (e.g., mid-peak plateau in steady decline)
-- - Auto-pass that should be rejected (rare edge case)
-- - Any quality decision that should survive re-extraction

CREATE TABLE IF NOT EXISTS hrr_quality_overrides (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    endurance_session_id INTEGER REFERENCES endurance_sessions(id),
    interval_order SMALLINT NOT NULL,
    override_action VARCHAR(30) NOT NULL,   -- force_pass, force_reject
    original_status VARCHAR(20),            -- what extraction computed before override
    original_reason TEXT,                   -- auto_reject_reason or flags that were overridden
    reason TEXT NOT NULL,                   -- human explanation of why override is correct
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,                 -- set when extraction applies this
    UNIQUE(polar_session_id, interval_order),
    CHECK (polar_session_id IS NOT NULL OR endurance_session_id IS NOT NULL)
);

-- Index for lookup during extraction
CREATE INDEX IF NOT EXISTS idx_quality_override_polar 
ON hrr_quality_overrides(polar_session_id) WHERE polar_session_id IS NOT NULL;

COMMENT ON TABLE hrr_quality_overrides IS 
    'Human quality overrides that persist through re-extraction. Uses stable keys (session_id, interval_order) not volatile interval_id.';

COMMENT ON COLUMN hrr_quality_overrides.override_action IS 
    'force_pass = accept despite auto-reject, force_reject = reject despite auto-pass';

COMMENT ON COLUMN hrr_quality_overrides.applied_at IS 
    'Set by extraction script when override is applied. NULL = pending (awaiting re-extraction).';

-- Workflow:
-- 1. Run extraction: python scripts/hrr_feature_extraction.py --session-id 70
-- 2. See rejection you disagree with
-- 3. Insert override:
--    INSERT INTO hrr_quality_overrides 
--      (polar_session_id, interval_order, override_action, original_status, original_reason, reason)
--    VALUES 
--      (70, 1, 'force_pass', 'rejected', 'r2_30_60_below_0.75', 
--       'Human reviewed: mid-peak plateau in middle of steady drop. Valid recovery curve.');
-- 4. Re-run extraction - it will apply the override and set applied_at
-- 5. Interval now passes despite gate failure
