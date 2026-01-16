-- Migration: Add nadir_time_sec column to hr_recovery_intervals
-- Date: 2026-01-16
-- Purpose: Track when nadir occurs (seconds from onset) for recovery curve analysis
--          Helps identify if nadir happens early (90s) vs late (240s+) in the recovery

-- Add the column
ALTER TABLE hr_recovery_intervals
ADD COLUMN IF NOT EXISTS nadir_time_sec INTEGER;

-- Add comment
COMMENT ON COLUMN hr_recovery_intervals.nadir_time_sec IS 'Seconds from onset to nadir (lowest HR point). Useful for curve shape analysis.';

-- Verification
SELECT 
    'nadir_time_sec' as column_name,
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'hr_recovery_intervals' 
AND column_name = 'nadir_time_sec';
