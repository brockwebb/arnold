# Issue #019: Fix Ultrahuman data pipeline - API → Postgres direct path

**Status:** Open

## Problem

The Ultrahuman data pipeline is broken due to architecture drift during the DuckDB → Postgres migration.

**Current state:**
- `sync_ultrahuman.py` → outputs JSON to `/data/raw/ultrahuman/`
- `stage_ultrahuman.py` → converts to Parquet (deprecated format)
- `import_ultrahuman_csv.py` → only reads CSV, not JSON

**Result:** No automated path from Ultrahuman API to `biometric_readings` table.

**Data gap:** Sleep metrics stopped Dec 6, 2025 when user's phone app wasn't open. HRV/RHR continued via different sync path. Gap is unrecoverable - no alternative data source.

## Root Cause

ADR-002 deprecated DuckDB/Parquet staging in favor of direct Postgres writes, but the Ultrahuman pipeline wasn't updated.

## Solution Implemented

Created `scripts/sync/ultrahuman_to_postgres.py` that:
1. Fetches from Ultrahuman Partner API (`/api/v1/metrics`)
2. Upserts directly to `biometric_readings` table
3. Supports date range parameters
4. Handles the metric type mapping

**Single script, no intermediate files.**

## Usage

```bash
# Sync yesterday (default)
python scripts/sync/ultrahuman_to_postgres.py

# Sync last 7 days
python scripts/sync/ultrahuman_to_postgres.py --days 7

# Sync specific date
python scripts/sync/ultrahuman_to_postgres.py --date 2025-12-07

# Sync date range
python scripts/sync/ultrahuman_to_postgres.py --start 2025-12-07 --end 2026-01-05

# Preview without writing
python scripts/sync/ultrahuman_to_postgres.py --days 30 --dry-run
```

## Files Status

- [x] Created: `scripts/sync/ultrahuman_to_postgres.py`
- [ ] Deprecate: `scripts/sync/stage_ultrahuman.py` (parquet output)
- [x] Keep: `scripts/import_ultrahuman_csv.py` (manual CSV fallback)
- [ ] Optional: Update `scripts/sync/sync_ultrahuman.py` to call new importer

## Related

- Data annotations #5, #6: Documents the Dec 6 → present sleep data gap
- ADR-002: Postgres-first architecture decision

## To Backfill Data

Once Ultrahuman app is reopened and syncing:

```bash
# Backfill from Dec 7 to now
python scripts/sync/ultrahuman_to_postgres.py --start 2025-12-07

# Or just get recent data
python scripts/sync/ultrahuman_to_postgres.py --days 7
```
