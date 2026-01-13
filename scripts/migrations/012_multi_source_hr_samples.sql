-- Migration 012: Multi-source HR samples
-- Issue #23: Enable hr_samples table to support data from multiple sources
-- (Polar API, Suunto FIT, Garmin FIT, etc.)
--
-- Changes:
--   1. Add 'source' column for provenance tracking
--   2. Add 'endurance_session_id' FK for FIT-imported sessions
--   3. Make 'session_id' (polar FK) nullable
--   4. Add check constraint: at least one FK must be set
--   5. Backfill existing data with source='polar_api'

-- Step 1: Add new columns
ALTER TABLE hr_samples 
    ADD COLUMN IF NOT EXISTS source VARCHAR(20),
    ADD COLUMN IF NOT EXISTS endurance_session_id INTEGER;

-- Step 2: Make polar FK nullable (was NOT NULL)
ALTER TABLE hr_samples 
    ALTER COLUMN session_id DROP NOT NULL;

-- Step 3: Backfill existing Polar data with source
UPDATE hr_samples 
SET source = 'polar_api' 
WHERE source IS NULL AND session_id IS NOT NULL;

-- Step 4: Add FK to endurance_sessions
ALTER TABLE hr_samples 
    ADD CONSTRAINT hr_samples_endurance_session_fkey 
    FOREIGN KEY (endurance_session_id) 
    REFERENCES endurance_sessions(id) 
    ON DELETE CASCADE;

-- Step 5: Add check constraint - must have at least one session reference
-- Note: Defer this if there might be orphaned samples during migration
ALTER TABLE hr_samples 
    ADD CONSTRAINT hr_samples_session_check 
    CHECK (session_id IS NOT NULL OR endurance_session_id IS NOT NULL);

-- Step 6: Add index for FIT session lookups
CREATE INDEX IF NOT EXISTS idx_hr_samples_endurance 
    ON hr_samples(endurance_session_id) 
    WHERE endurance_session_id IS NOT NULL;

-- Step 7: Add index for source filtering
CREATE INDEX IF NOT EXISTS idx_hr_samples_source 
    ON hr_samples(source);

-- Verify migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 012 complete:';
    RAISE NOTICE '  - hr_samples.source column added';
    RAISE NOTICE '  - hr_samples.endurance_session_id FK added';
    RAISE NOTICE '  - session_id made nullable';
    RAISE NOTICE '  - Check constraint ensures at least one FK set';
    RAISE NOTICE '  - Existing Polar samples backfilled with source=polar_api';
END $$;
