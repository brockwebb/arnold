#!/bin/bash
# HRR QC System - Single file bundle for Claude Code
# 
# Usage: ./hrr_qc_bundle.sh [command]
#   setup     - Run migration and install deps
#   sessions  - List sessions
#   review    - Interactive review
#   stats     - Show statistics
#
# Or just run directly: ./hrr_qc_bundle.sh
# It will prompt for what to do.

DB_URL="${DATABASE_URL:-postgresql://localhost:5432/arnold}"

# Embedded SQL Migration
run_migration() {
    psql "$DB_URL" << 'SQL_EOF'
-- HRR QC Schema Migration (embedded)

-- Algorithm versions
CREATE TABLE IF NOT EXISTS hrr_algorithm_versions (
    id SERIAL PRIMARY KEY,
    version_tag VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    detection_config JSONB,
    quality_config JSONB,
    fit_config JSONB,
    activated_at TIMESTAMPTZ DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    notes TEXT
);

INSERT INTO hrr_algorithm_versions (version_tag, description, detection_config, quality_config)
VALUES (
    'v1.0-baseline',
    'Initial version before formal tracking',
    '{"prominence_min": 10, "distance_min": 30, "recovery_window_sec": 300}'::jsonb,
    '{"r2_30_60_threshold": 0.75, "r2_30_90_threshold": 0.75}'::jsonb
) ON CONFLICT (version_tag) DO NOTHING;

-- Algorithm runs
CREATE TABLE IF NOT EXISTS hrr_algo_runs (
    id BIGSERIAL PRIMARY KEY,
    algo_version_id INT NOT NULL REFERENCES hrr_algorithm_versions(id),
    polar_session_id INT,
    endurance_session_id INT,
    ran_at TIMESTAMPTZ DEFAULT NOW(),
    run_config JSONB,
    intervals_detected INT,
    intervals_passed INT,
    intervals_rejected INT,
    intervals_flagged INT,
    runtime_ms INT,
    notes TEXT,
    CONSTRAINT uq_algo_run_polar UNIQUE (algo_version_id, polar_session_id),
    CONSTRAINT uq_algo_run_endurance UNIQUE (algo_version_id, endurance_session_id)
);

CREATE INDEX IF NOT EXISTS idx_algo_runs_version ON hrr_algo_runs(algo_version_id);
CREATE INDEX IF NOT EXISTS idx_algo_runs_polar ON hrr_algo_runs(polar_session_id) WHERE polar_session_id IS NOT NULL;

-- Extend intervals table
ALTER TABLE hr_recovery_intervals 
    ADD COLUMN IF NOT EXISTS algo_run_id BIGINT REFERENCES hrr_algo_runs(id);
ALTER TABLE hr_recovery_intervals
    ADD COLUMN IF NOT EXISTS exercise_group_id INT;

-- Reason codes
CREATE TABLE IF NOT EXISTS hrr_qc_reason_codes (
    code VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100),
    applies_to VARCHAR(20) NOT NULL,
    requires_notes BOOLEAN DEFAULT FALSE,
    sort_order INT DEFAULT 99,
    active BOOLEAN DEFAULT TRUE
);

INSERT INTO hrr_qc_reason_codes (code, display_name, applies_to, requires_notes, sort_order) VALUES
('peak_misplaced', 'Peak not at true maximum', 'reject_passed', FALSE, 1),
('double_peak_undetected', 'Double peak not detected', 'reject_passed', FALSE, 2),
('early_termination', 'Recovery cut too short', 'reject_passed', FALSE, 3),
('late_onset', 'Peak detection started late', 'reject_passed', FALSE, 4),
('no_true_recovery', 'Not a true recovery interval', 'reject_passed', FALSE, 5),
('signal_artifact', 'Noise/artifact not caught', 'reject_passed', FALSE, 6),
('sub_threshold', 'Below recovery activation threshold', 'reject_passed', FALSE, 7),
('false_positive_double', 'False double peak detection', 'override_rejection', FALSE, 10),
('acceptable_r2', 'R² acceptable for analysis', 'override_rejection', FALSE, 11),
('known_context', 'Contextual knowledge applies', 'override_rejection', TRUE, 12),
('peak_shift_fixes', 'Peak adjustment makes valid', 'override_rejection', FALSE, 13),
('hiit_expected', 'Expected for HIIT/interval pattern', 'override_rejection', FALSE, 14),
('other', 'Other (see notes)', 'both', TRUE, 99)
ON CONFLICT (code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    applies_to = EXCLUDED.applies_to;

-- Extend judgments table
ALTER TABLE hrr_qc_judgments
    ADD COLUMN IF NOT EXISTS algo_run_id BIGINT,
    ADD COLUMN IF NOT EXISTS interval_id INT,
    ADD COLUMN IF NOT EXISTS interval_start_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS peak_sample_idx INT,
    ADD COLUMN IF NOT EXISTS human_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS reason_code VARCHAR(30),
    ADD COLUMN IF NOT EXISTS peak_shift_applied BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reviewer VARCHAR(50) DEFAULT 'brock';

CREATE INDEX IF NOT EXISTS idx_qc_judgments_locator 
ON hrr_qc_judgments(polar_session_id, interval_start_ts) 
WHERE interval_start_ts IS NOT NULL;

-- Session reviews
CREATE TABLE IF NOT EXISTS hrr_session_reviews (
    id SERIAL PRIMARY KEY,
    polar_session_id INT,
    endurance_session_id INT,
    algo_run_id BIGINT,
    review_action VARCHAR(30) NOT NULL,
    intervals_confirmed INT DEFAULT 0,
    intervals_rejected INT DEFAULT 0,
    intervals_skipped INT DEFAULT 0,
    reviewed_at TIMESTAMPTZ DEFAULT NOW(),
    reviewer VARCHAR(50) DEFAULT 'brock',
    notes TEXT
);

-- Backfill existing intervals with baseline algo run
DO $$
DECLARE
    baseline_version_id INT;
    run_id BIGINT;
    sess RECORD;
BEGIN
    SELECT id INTO baseline_version_id 
    FROM hrr_algorithm_versions 
    WHERE version_tag = 'v1.0-baseline';
    
    FOR sess IN 
        SELECT DISTINCT polar_session_id, endurance_session_id 
        FROM hr_recovery_intervals 
        WHERE algo_run_id IS NULL
          AND (polar_session_id IS NOT NULL OR endurance_session_id IS NOT NULL)
    LOOP
        INSERT INTO hrr_algo_runs (algo_version_id, polar_session_id, endurance_session_id, notes)
        VALUES (baseline_version_id, sess.polar_session_id, sess.endurance_session_id, 'Legacy backfill')
        ON CONFLICT DO NOTHING
        RETURNING id INTO run_id;
        
        IF run_id IS NOT NULL THEN
            UPDATE hr_recovery_intervals 
            SET algo_run_id = run_id
            WHERE polar_session_id IS NOT DISTINCT FROM sess.polar_session_id
              AND endurance_session_id IS NOT DISTINCT FROM sess.endurance_session_id
              AND algo_run_id IS NULL;
        END IF;
    END LOOP;
END $$;

-- Views
CREATE OR REPLACE VIEW v_hrr_session_summary AS
SELECT 
    polar_session_id,
    algo_run_id,
    COUNT(*) as total_intervals,
    COUNT(*) FILTER (WHERE quality_status = 'pass') as passed,
    COUNT(*) FILTER (WHERE quality_status = 'rejected') as rejected,
    COUNT(*) FILTER (WHERE quality_status = 'flagged') as flagged,
    COUNT(*) FILTER (WHERE needs_review = true) as needs_review,
    COUNT(*) FILTER (WHERE human_verified = true) as verified,
    AVG(hrr60_abs) FILTER (WHERE quality_status = 'pass') as avg_hrr60_passed
FROM hr_recovery_intervals
WHERE excluded IS NOT TRUE
GROUP BY polar_session_id, algo_run_id;

SELECT 'Migration complete' as status;
SQL_EOF
}

show_sessions() {
    psql "$DB_URL" << 'SQL_EOF'
SELECT 
    ps.id as "Session",
    ps.start_time::date as "Date",
    ps.sport as "Sport",
    COUNT(*) FILTER (WHERE hri.quality_status = 'pass') as "Pass",
    COUNT(*) FILTER (WHERE hri.quality_status = 'rejected') as "Reject",
    COUNT(*) FILTER (WHERE hri.quality_status = 'flagged') as "Flag",
    COUNT(*) FILTER (WHERE hri.needs_review = true) as "Review",
    COUNT(*) FILTER (WHERE hri.human_verified = true) as "Verified",
    ROUND(AVG(hri.hrr60_abs) FILTER (WHERE hri.quality_status = 'pass'), 1) as "HRR60"
FROM polar_sessions ps
JOIN hr_recovery_intervals hri ON hri.polar_session_id = ps.id
WHERE hri.excluded IS NOT TRUE
GROUP BY ps.id, ps.start_time, ps.sport
ORDER BY ps.start_time;
SQL_EOF
}

show_stats() {
    psql "$DB_URL" << 'SQL_EOF'
SELECT 
    COUNT(*) as "Total Intervals",
    COUNT(*) FILTER (WHERE quality_status = 'pass') as "Algo Pass",
    COUNT(*) FILTER (WHERE quality_status = 'rejected') as "Algo Reject",
    COUNT(*) FILTER (WHERE quality_status = 'flagged') as "Algo Flagged",
    COUNT(*) FILTER (WHERE human_verified = true) as "Verified",
    COUNT(*) FILTER (WHERE needs_review = true) as "Needs Review",
    ROUND(100.0 * COUNT(*) FILTER (WHERE human_verified = true) / COUNT(*), 1) as "% Complete"
FROM hr_recovery_intervals
WHERE excluded IS NOT TRUE;

SELECT human_status as "Judgment", COUNT(*) as "Count"
FROM hrr_qc_judgments
WHERE human_status IS NOT NULL
GROUP BY human_status
ORDER BY COUNT(*) DESC;
SQL_EOF
}

# Main
case "${1:-menu}" in
    setup)
        echo "Running migration..."
        run_migration
        echo ""
        echo "Installing Python deps..."
        pip3 install --quiet click rich psycopg2-binary 2>/dev/null || pip install --quiet click rich psycopg2-binary
        echo "Done! Run: $0 sessions"
        ;;
    sessions)
        show_sessions
        ;;
    stats)
        show_stats
        ;;
    review)
        echo "For full interactive review, use the Python CLI:"
        echo "  python3 hrr_qc_review.py review"
        echo ""
        echo "Quick session list:"
        show_sessions
        ;;
    menu|*)
        echo "HRR QC System"
        echo "============="
        echo ""
        echo "Commands:"
        echo "  $0 setup     - Run migration, install deps"
        echo "  $0 sessions  - List sessions with counts"
        echo "  $0 stats     - Show QC statistics"
        echo "  $0 review    - Show review instructions"
        echo ""
        echo "For full interactive review:"
        echo "  python3 hrr_qc_review.py review -r"
        ;;
esac
