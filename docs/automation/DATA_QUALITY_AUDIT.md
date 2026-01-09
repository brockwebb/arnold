# Data Quality Audit

A standalone script to check database health across Postgres and Neo4j.

## Quick Start

```bash
# Full audit
python scripts/data_quality_audit.py

# Skip slow checks (gap analysis)
python scripts/data_quality_audit.py --quick
```

## What It Checks

### Postgres Checks

| Check | Description | Status |
|-------|-------------|--------|
| **Biometric Duplicates** | Same date/metric/source appearing multiple times | FAIL if found |
| **HRV Source Coverage** | Multiple sources on same date (expected: Apple + Ultrahuman) | INFO |
| **Biometric Anomalies** | Values outside reasonable ranges (HRV 5-200, RHR 30-100, etc.) | WARN if found |
| **Workout Integrity** | Duplicate dates, NULL exercise_ids | WARN if found |
| **Sync History** | Recent sync failures, stale syncs (>24h) | WARN if issues |
| **Biometric Gaps** | Missing HRV/sleep in last 30 days | WARN if found |

### Neo4j Checks

| Check | Description | Status |
|-------|-------------|--------|
| **Orphan Exercises** | Exercises without TARGETS or INVOLVES relationships | WARN if found |
| **Dangling References** | Relationships pointing to wrong node types | FAIL if found |
| **Exercise Coverage** | % of exercises with TARGETS and INVOLVES | WARN if <90% |
| **Workout Sync** | Neo4j workout count vs Postgres | WARN if diff >5 |
| **Schema Inventory** | Report of tables and node counts | INFO |

## Sample Output

```
============================================================
Arnold Data Quality Audit
Started: 2026-01-09 09:15:00
============================================================

--- Postgres Checks ---

--- Neo4j Checks ---

============================================================
RESULTS
============================================================

✓ Biometric Duplicates: PASS
    No duplicates

✓ HRV Source Coverage: PASS
    16 dates have HRV from multiple sources (expected)

✓ Biometric Value Anomalies: PASS
    All values within expected ranges

✓ Workout Data Integrity: PASS
    Workout data clean (tables: workout_summaries, strength_sets)

✓ Sync History: PASS
    Last sync: 2026-01-09 08:40:07 (success)

⚠ Biometric Data Gaps: WARN
    Found 22 days with missing HRV or sleep data

⚠ Neo4j Orphan Exercises: WARN
    Found 7 exercises without relationships
      - Band Pull-Apart (arnold-coach)
      - Wall Slide (arnold-coach)
      ...

✓ Neo4j Exercise Counts: PASS
    4222 exercises: 100% TARGETS, 99% INVOLVES

✓ Neo4j ↔ Postgres Workout Sync: PASS
    Counts match: 165

============================================================
Summary: 8 passed, 2 warnings, 0 failures
============================================================
```

## Expected Warnings

Some warnings are expected and documented:

| Warning | Explanation |
|---------|-------------|
| Biometric gaps Dec 10+ | Device issue annotation covers this period |
| 7 orphan exercises | Custom arnold-coach exercises need enrichment |

## Configuration

The script loads credentials from `.env` in project root:

```bash
# Postgres
POSTGRES_DB=arnold_analytics
POSTGRES_USER=brock
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your-password-here>
NEO4J_DATABASE=arnold
```

## Integration with Sync Pipeline

Run audit after sync to validate data quality:

```bash
python scripts/sync_pipeline.py && python scripts/data_quality_audit.py --quick
```

Or add to the launchd job (see [LAUNCHD_SYNC.md](./LAUNCHD_SYNC.md)).

## Exit Codes

- `0` - All checks passed (warnings OK)
- `1` - One or more FAIL results

Use in CI/automation:
```bash
python scripts/data_quality_audit.py || echo "Audit failed!"
```
