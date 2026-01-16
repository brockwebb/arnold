-- Migration 016: HRR Deliberate Test Metadata
-- Created: 2026-01-14
-- Purpose: Add columns for user-annotated deliberate HRR tests
--
-- Context: Most intervals are auto-detected inter-set recoveries.
-- Deliberate tests (e.g., 5-min supine after Tabata) need user annotation
-- to capture protocol context for meaningful baselines.
--
-- Flow:
--   1. Sync runs, algorithm detects intervals, writes with defaults
--   2. User tells Arnold "that was a deliberate test after Tabata burpees"
--   3. Arnold updates interval with metadata

-- Flag for user-annotated deliberate tests
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS is_deliberate BOOLEAN DEFAULT FALSE;

-- What preceded the test (for protocol-specific baselines)
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS preceding_activity VARCHAR(50);

-- Free-form notes
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS notes TEXT;

-- Index for querying deliberate tests
CREATE INDEX IF NOT EXISTS idx_hr_recovery_deliberate 
ON hr_recovery_intervals(start_time DESC) 
WHERE is_deliberate = TRUE;

-- Comments
COMMENT ON COLUMN hr_recovery_intervals.is_deliberate IS 
'True when user explicitly annotated this as a deliberate HRR test (not just inter-set recovery)';

COMMENT ON COLUMN hr_recovery_intervals.preceding_activity IS 
'What was done before the test: tabata_burpees, zone2_run, heavy_deadlifts, etc. For protocol-specific baselines';

COMMENT ON COLUMN hr_recovery_intervals.notes IS 
'Free-form notes about the test conditions or observations';

-- Update protocol_type enum values for clarity
COMMENT ON COLUMN hr_recovery_intervals.protocol_type IS 
'Detection context: inter_set (during workout rest), end_of_session, deliberate_test (annotated 5-min protocol)';
