-- Migration 015: HRR Extended 5-Minute Window Support
-- Adds columns for 180s, 240s, 300s timepoints and R² at each window
--
-- Context: HRR testing with deliberate 5-minute supine recovery (session 71)
-- showed need for extended recovery windows beyond the current 120s cap.

-- Add missing HR timepoints
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hr_240s SMALLINT;

-- Add missing HRR absolute values
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS hrr240_abs SMALLINT;

-- Add R² at extended windows (for fit quality at longer intervals)
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS r2_180 NUMERIC(4,3);

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS r2_240 NUMERIC(4,3);

ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS r2_300 NUMERIC(4,3);

-- Add tau_censored flag (tau hit upper bound, recovery incomplete)
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS tau_censored BOOLEAN DEFAULT FALSE;

-- Comment on extended window columns
COMMENT ON COLUMN hr_recovery_intervals.hr_180s IS 'Heart rate 180 seconds after peak';
COMMENT ON COLUMN hr_recovery_intervals.hr_240s IS 'Heart rate 240 seconds after peak';
COMMENT ON COLUMN hr_recovery_intervals.hr_300s IS 'Heart rate 300 seconds after peak';
COMMENT ON COLUMN hr_recovery_intervals.hrr180_abs IS 'Absolute HRR at 180s (peak - hr_180s)';
COMMENT ON COLUMN hr_recovery_intervals.hrr240_abs IS 'Absolute HRR at 240s (peak - hr_240s)';
COMMENT ON COLUMN hr_recovery_intervals.hrr300_abs IS 'Absolute HRR at 300s (peak - hr_300s)';
COMMENT ON COLUMN hr_recovery_intervals.r2_180 IS 'R² of exponential fit at 180s window';
COMMENT ON COLUMN hr_recovery_intervals.r2_240 IS 'R² of exponential fit at 240s window';
COMMENT ON COLUMN hr_recovery_intervals.r2_300 IS 'R² of exponential fit at 300s window';
COMMENT ON COLUMN hr_recovery_intervals.tau_censored IS 'True if tau estimate hit upper bound (600s), indicating incomplete recovery';
