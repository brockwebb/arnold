-- Migration 019: HRR Interval Reviews Table
-- Human review decisions at interval level
-- Date: 2026-01-17

-- Use cases:
-- - Clear informational flags (ONSET_DISAGREEMENT when R² is excellent)
-- - Verify manual peak adjustments worked correctly
-- - Mark intervals as accepted/rejected by human judgment

CREATE TABLE IF NOT EXISTS hrr_interval_reviews (
    id SERIAL PRIMARY KEY,
    interval_id INTEGER NOT NULL REFERENCES hr_recovery_intervals(id) ON DELETE CASCADE,
    review_action VARCHAR(30) NOT NULL,  -- see below
    original_flags TEXT[],                -- snapshot of flags at review time
    notes TEXT,
    reviewed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(interval_id, review_action)    -- one action per type per interval
);

COMMENT ON TABLE hrr_interval_reviews IS 'Human review decisions at interval level';
COMMENT ON COLUMN hrr_interval_reviews.review_action IS 
    'flags_cleared = informational flags OK, ' ||
    'peak_shift_verified = manual adjustment correct, ' ||
    'accepted = interval is good, ' ||
    'rejected_override = force reject good-looking data';

-- Helper view for review status
CREATE OR REPLACE VIEW hrr_review_status AS
SELECT 
    i.polar_session_id,
    i.interval_order,
    i.quality_status,
    i.quality_flags,
    r.review_action,
    r.notes as review_notes,
    r.reviewed_at
FROM hr_recovery_intervals i
LEFT JOIN hrr_interval_reviews r ON r.interval_id = i.id
ORDER BY i.polar_session_id, i.interval_order;

-- Also add session-level QC tracking to polar_sessions if not exists
ALTER TABLE polar_sessions 
ADD COLUMN IF NOT EXISTS hrr_qc_status VARCHAR(20) DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS hrr_qc_reviewed_at TIMESTAMPTZ;

COMMENT ON COLUMN polar_sessions.hrr_qc_status IS 'pending, reviewed, needs_reprocess';
