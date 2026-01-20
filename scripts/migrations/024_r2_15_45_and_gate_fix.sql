-- Migration 024: Add r2_15_45 centered window and document r2_30_90 gate fix
-- Date: 2026-01-19
-- Issue: #37 cascading validity bug
--
-- Changes:
-- 1. Add r2_15_45 column for centered 15-45s window R² (diagnostic for edge artifacts)
-- 2. Document that r2_30_90 is now diagnostic only (code fix in metrics.py)
--
-- The r2_30_90 gate was previously a hard reject, but this caused valid HRR60
-- intervals to be rejected when only HRR120 was invalid. The code fix removes
-- r2_30_90 as a hard reject gate - it now only serves as a diagnostic marker
-- for HRR120 validity.

-- Add r2_15_45 column
ALTER TABLE hr_recovery_intervals 
ADD COLUMN IF NOT EXISTS r2_15_45 REAL;

-- Add comment documenting the column's purpose
COMMENT ON COLUMN hr_recovery_intervals.r2_15_45 IS 
'R² for centered 15-45s window. Diagnostic for edge artifacts that hurt r2_30_60. Added migration 024.';

-- Update comment on r2_30_90 to reflect new role
COMMENT ON COLUMN hr_recovery_intervals.r2_30_90 IS 
'R² for 30-90s transition window. Diagnostic only - validates HRR120 but does NOT reject interval. Gate fix in migration 024.';

-- Verify the column was added
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'hr_recovery_intervals' 
        AND column_name = 'r2_15_45'
    ) THEN
        RAISE NOTICE 'Migration 024 complete: r2_15_45 column added';
    ELSE
        RAISE EXCEPTION 'Migration 024 failed: r2_15_45 column not found';
    END IF;
END $$;
