-- Migration 021: Add extended HRR columns (hr_180s, hr_300s, hrr180_abs, hrr300_abs)
-- Fix for incomplete migration 015 - these columns were computed but never stored
--
-- Created: 2026-01-17
-- Author: Brock + Claude

-- Add extended HR measurement columns
ALTER TABLE hr_recovery_intervals
ADD COLUMN IF NOT EXISTS hr_180s SMALLINT,
ADD COLUMN IF NOT EXISTS hr_240s SMALLINT,
ADD COLUMN IF NOT EXISTS hr_300s SMALLINT;

-- Add extended HRR absolute drop columns
ALTER TABLE hr_recovery_intervals
ADD COLUMN IF NOT EXISTS hrr180_abs SMALLINT,
ADD COLUMN IF NOT EXISTS hrr240_abs SMALLINT,
ADD COLUMN IF NOT EXISTS hrr300_abs SMALLINT;

-- Add extended HRR fractional columns (for consistency with hrr30_frac, hrr60_frac, etc.)
ALTER TABLE hr_recovery_intervals
ADD COLUMN IF NOT EXISTS hrr180_frac NUMERIC(5,4),
ADD COLUMN IF NOT EXISTS hrr240_frac NUMERIC(5,4),
ADD COLUMN IF NOT EXISTS hrr300_frac NUMERIC(5,4);

COMMENT ON COLUMN hr_recovery_intervals.hr_180s IS 'Heart rate at 180 seconds post-peak';
COMMENT ON COLUMN hr_recovery_intervals.hr_240s IS 'Heart rate at 240 seconds post-peak';
COMMENT ON COLUMN hr_recovery_intervals.hr_300s IS 'Heart rate at 300 seconds post-peak';
COMMENT ON COLUMN hr_recovery_intervals.hrr180_abs IS 'HRR at 180s: absolute drop from peak (bpm)';
COMMENT ON COLUMN hr_recovery_intervals.hrr240_abs IS 'HRR at 240s: absolute drop from peak (bpm)';
COMMENT ON COLUMN hr_recovery_intervals.hrr300_abs IS 'HRR at 300s: absolute drop from peak (bpm)';
COMMENT ON COLUMN hr_recovery_intervals.hrr180_frac IS 'HRR at 180s: fraction of HR reserve recovered';
COMMENT ON COLUMN hr_recovery_intervals.hrr240_frac IS 'HRR at 240s: fraction of HR reserve recovered';
COMMENT ON COLUMN hr_recovery_intervals.hrr300_frac IS 'HRR at 300s: fraction of HR reserve recovered';
