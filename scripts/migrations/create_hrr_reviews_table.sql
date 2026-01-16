-- Human Review Table for HRR Intervals
-- 
-- DESIGN PHILOSOPHY:
-- Interval data can be recomputed/reimported freely.
-- Human decisions (review status, determination) should NEVER be lost.
-- 
-- This table stores human QC decisions separately from computed interval data.
-- The stable identifier is (polar_session_id, interval_order, start_time).
-- Even if interval IDs change on reimport, we can match by these stable keys.

CREATE TABLE IF NOT EXISTS hrr_interval_reviews (
    id SERIAL PRIMARY KEY,
    
    -- Stable identifier (survives reimport)
    polar_session_id INTEGER NOT NULL,
    interval_order INTEGER NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    
    -- Algorithm flagging (copied from interval at review time for reference)
    flagged_for_review BOOLEAN DEFAULT FALSE,
    original_flags TEXT[],           -- Copy of quality_flags when flagged
    original_quality_score FLOAT,    -- Copy of quality_score when flagged
    
    -- Human review status
    human_reviewed BOOLEAN DEFAULT FALSE,
    determination BOOLEAN,           -- TRUE = valid peak, FALSE = not a peak, NULL = not yet reviewed
    annotation TEXT,                 -- Human notes
    
    -- Audit
    reviewed_by VARCHAR(50),         -- Who reviewed (for future multi-user)
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraint: one review record per interval (by stable ID)
    UNIQUE(polar_session_id, interval_order, start_time)
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_hrr_reviews_session ON hrr_interval_reviews(polar_session_id);
CREATE INDEX IF NOT EXISTS idx_hrr_reviews_pending ON hrr_interval_reviews(human_reviewed) WHERE human_reviewed = FALSE;
CREATE INDEX IF NOT EXISTS idx_hrr_reviews_flagged ON hrr_interval_reviews(flagged_for_review) WHERE flagged_for_review = TRUE;

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_hrr_review_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hrr_review_timestamp ON hrr_interval_reviews;
CREATE TRIGGER trg_hrr_review_timestamp
    BEFORE UPDATE ON hrr_interval_reviews
    FOR EACH ROW
    EXECUTE FUNCTION update_hrr_review_timestamp();

-- Comments
COMMENT ON TABLE hrr_interval_reviews IS 'Human QC decisions for HRR intervals. Separate from interval data so reimport does not lose human decisions.';
COMMENT ON COLUMN hrr_interval_reviews.determination IS 'Human determination: TRUE=valid peak, FALSE=not a peak, NULL=pending review';
COMMENT ON COLUMN hrr_interval_reviews.original_flags IS 'Copy of quality_flags from interval when review record was created';

-- View to join reviews with current interval data
CREATE OR REPLACE VIEW hrr_intervals_with_reviews AS
SELECT 
    i.*,
    r.human_reviewed,
    r.determination,
    r.annotation,
    r.reviewed_by,
    r.reviewed_at
FROM hr_recovery_intervals i
LEFT JOIN hrr_interval_reviews r 
    ON r.polar_session_id = i.polar_session_id 
    AND r.interval_order = i.interval_order 
    AND r.start_time = i.start_time;

COMMENT ON VIEW hrr_intervals_with_reviews IS 'HRR intervals joined with human review status';
