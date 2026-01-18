#!/bin/bash
# HRR QC System Setup Script
# Run via Claude Code: claude -p "run this setup script"
#
# This script:
# 1. Runs the schema migration
# 2. Installs Python dependencies
# 3. Verifies the setup
# 4. Shows usage instructions

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}HRR QC System Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# Configuration - adjust these paths as needed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARNOLD_DIR="${ARNOLD_DIR:-$HOME/dev/arnold}"
SQL_FILE="${SCRIPT_DIR}/hrr_qc_schema_migration.sql"
CLI_FILE="${SCRIPT_DIR}/hrr_qc_review.py"

# Database connection - uses DATABASE_URL or defaults
DB_URL="${DATABASE_URL:-postgresql://localhost:5432/arnold}"

echo -e "\n${YELLOW}Configuration:${NC}"
echo "  Script dir: $SCRIPT_DIR"
echo "  Arnold dir: $ARNOLD_DIR"
echo "  Database: $DB_URL"

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command -v psql &> /dev/null; then
    echo -e "${RED}Error: psql not found. Install PostgreSQL client.${NC}"
    exit 1
fi
echo "  ✓ psql found"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found.${NC}"
    exit 1
fi
echo "  ✓ python3 found"

# Test database connection
echo -e "\n${YELLOW}Testing database connection...${NC}"
if ! psql "$DB_URL" -c "SELECT 1" &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to database${NC}"
    echo "  Check DATABASE_URL or ensure PostgreSQL is running"
    exit 1
fi
echo "  ✓ Database connected"

# Check if migration files exist
if [[ ! -f "$SQL_FILE" ]]; then
    echo -e "${RED}Error: Migration file not found: $SQL_FILE${NC}"
    echo "  Download from Claude or copy to script directory"
    exit 1
fi
echo "  ✓ Migration file found"

if [[ ! -f "$CLI_FILE" ]]; then
    echo -e "${RED}Error: CLI file not found: $CLI_FILE${NC}"
    exit 1
fi
echo "  ✓ CLI file found"

# Run schema migration
echo -e "\n${YELLOW}Running schema migration...${NC}"
echo "  This will create/update tables for HRR QC tracking"

# Show what will be created
echo -e "\n  Tables to create/update:"
echo "    - hrr_algorithm_versions"
echo "    - hrr_algo_runs"
echo "    - hrr_qc_reason_codes"
echo "    - hrr_session_reviews"
echo "    - Extensions to hr_recovery_intervals"
echo "    - Extensions to hrr_qc_judgments"

read -p "  Proceed with migration? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "  Migration skipped"
else
    psql "$DB_URL" -f "$SQL_FILE"
    echo -e "  ${GREEN}✓ Migration complete${NC}"
fi

# Install Python dependencies
echo -e "\n${YELLOW}Installing Python dependencies...${NC}"
pip3 install --quiet click rich psycopg2-binary
echo "  ✓ Dependencies installed"

# Make CLI executable
chmod +x "$CLI_FILE"
echo "  ✓ CLI made executable"

# Verify setup
echo -e "\n${YELLOW}Verifying setup...${NC}"

# Check tables exist
TABLES=$(psql "$DB_URL" -t -c "
SELECT COUNT(*) FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('hrr_algorithm_versions', 'hrr_algo_runs', 'hrr_qc_reason_codes')
")
TABLES=$(echo $TABLES | tr -d ' ')

if [[ "$TABLES" -ge 3 ]]; then
    echo "  ✓ QC tables verified"
else
    echo -e "  ${YELLOW}⚠ Some tables may be missing (found $TABLES/3)${NC}"
fi

# Check reason codes
CODES=$(psql "$DB_URL" -t -c "SELECT COUNT(*) FROM hrr_qc_reason_codes" 2>/dev/null || echo "0")
CODES=$(echo $CODES | tr -d ' ')
echo "  ✓ Reason codes loaded: $CODES"

# Check intervals have algo_run_id
INTERVALS=$(psql "$DB_URL" -t -c "
SELECT COUNT(*) FROM hr_recovery_intervals WHERE algo_run_id IS NOT NULL
" 2>/dev/null || echo "0")
INTERVALS=$(echo $INTERVALS | tr -d ' ')
echo "  ✓ Intervals with algo_run_id: $INTERVALS"

# Show stats
echo -e "\n${YELLOW}Current HRR QC Status:${NC}"
psql "$DB_URL" -c "
SELECT 
    COUNT(*) as total_intervals,
    COUNT(*) FILTER (WHERE quality_status = 'pass') as passed,
    COUNT(*) FILTER (WHERE quality_status = 'rejected') as rejected,
    COUNT(*) FILTER (WHERE human_verified = true) as verified,
    COUNT(*) FILTER (WHERE needs_review = true) as needs_review
FROM hr_recovery_intervals
WHERE excluded IS NOT TRUE;
"

# Usage instructions
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}Usage:${NC}"
echo ""
echo "  # List sessions overview"
echo "  python3 $CLI_FILE sessions"
echo ""
echo "  # Interactive review (needs-review only)"
echo "  python3 $CLI_FILE review -r"
echo ""
echo "  # Review specific session"
echo "  python3 $CLI_FILE review -s 5"
echo ""
echo "  # Batch confirm sessions 1, 2, 3"
echo "  python3 $CLI_FILE batch-confirm 1 2 3"
echo ""
echo "  # Show QC statistics"
echo "  python3 $CLI_FILE stats"
echo ""

echo -e "${YELLOW}Keyboard shortcuts in review mode:${NC}"
echo "  Enter  = Confirm (accept algo decision)"
echo "  A      = All Good (batch confirm session)"
echo "  R      = Reject passed interval"
echo "  O      = Override rejection"
echo "  S      = Skip"
echo "  Q      = Quit session"
echo ""

echo -e "${YELLOW}Environment:${NC}"
echo "  DATABASE_URL=$DB_URL"
echo ""

# Optional: create alias
echo -e "${YELLOW}Optional: Add alias to ~/.bashrc or ~/.zshrc:${NC}"
echo "  alias hrr-qc='python3 $CLI_FILE'"
echo ""
