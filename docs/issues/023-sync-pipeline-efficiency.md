# Issue 023: Sync Pipeline Efficiency Problems

**Created:** 2026-01-23  
**Updated:** 2026-01-23  
**Status:** Partially Resolved  
**Priority:** Medium  
**Type:** Performance / Technical Debt

## Resolution Summary (2026-01-23)

**Polar file importer** - FIXED:
- Added upfront query of all known session IDs
- Filters file list BEFORE opening any files  
- Exits immediately when no new sessions exist
- Fixed DB config to use `DATABASE_URI` env var
- Added source provenance (`polar_file`) to hr_samples

**Apple Health importer** - FIXED:
- Added marker file (`data/sync_state/apple_health_last_import.json`)
- Tracks export.xml mtime + size
- Skips entire 220MB XML parse if file unchanged
- Use `--full` to force reimport

## Problem

The sync pipeline (`scripts/sync_pipeline.py`) has significant efficiency issues. It processes ALL historical files on every run rather than using proper incremental sync patterns with early bailout.

### Observed Behavior

```
[2026-01-23 08:22:40] [INFO]   Processing training-session-2025-10-25-8251681128-...json...
[2026-01-23 08:22:40] [INFO]     Session 8251681128 already exists, skipping
[2026-01-23 08:22:40] [INFO]   Processing training-session-2026-01-03-8251681144-...json...
[2026-01-23 08:22:40] [INFO]     Session 8251681144 already exists, skipping
...
[2026-01-23 08:22:40] [INFO]   Sessions imported: 0
[2026-01-23 08:22:40] [INFO]   HR samples imported: 0
```

The pipeline iterates through every Polar session file, opens each one, checks if it exists in the database, then skips it. This is O(n) on total historical files when it should be O(n) on new files only.

### Affected Steps

| Step | Issue | Impact |
|------|-------|--------|
| `polar` | Iterates all session files, checks DB for each | Disk I/O + DB queries for every historical file |
| `apple` | Unknown - needs audit | Potentially same issue |
| `fit` | **Good example** - checks filename against import log first | Minimal overhead |

### FIT Importer (Correct Pattern)

The FIT importer shows the right approach:
```
[2026-01-23 08:22:43] [INFO]   Found 2 FIT file(s)
[2026-01-23 08:22:43] [INFO]     Skipping (already imported): 6960d42efd3c530989a4d287.fit
[2026-01-23 08:22:43] [INFO]     Skipping (already imported): 695ae4550c3e061a4d4d71dc.fit
[2026-01-23 08:22:43] [INFO]   No new files to import
```

It maintains an import log and checks filenames against it BEFORE opening files. When no new files exist, it exits immediately.

## Root Cause

Each importer was written independently with different assumptions:

1. **Polar importer**: Assumes "check DB on each file" is acceptable
2. **FIT importer**: Uses file-based manifest tracking
3. **Ultrahuman**: API-based, fetches date range (better)
4. **Apple Health**: Unknown - needs audit

No unified pattern for incremental sync with early bailout.

## Proposed Solution

### Option A: Manifest-Based Tracking (Preferred)

Each source maintains a manifest of imported files/records:

```
data/sync_state/
├── polar_imported.json      # {"files": ["session-xxx.json", ...], "last_run": "..."}
├── fit_imported.json
├── apple_imported.json
└── ultrahuman_state.json    # {"last_sync_date": "2026-01-22"}
```

**Import logic:**
1. Load manifest
2. List files in source directory
3. Filter to files NOT in manifest
4. If empty → exit immediately (no DB queries)
5. Process new files only
6. Update manifest

### Option B: Database Last-Import Tracking

Add `sync_metadata` table:
```sql
CREATE TABLE sync_metadata (
    source TEXT PRIMARY KEY,
    last_import_at TIMESTAMPTZ,
    last_file_processed TEXT,
    files_processed JSONB
);
```

Query this ONCE at start, skip entire source if nothing new.

### Option C: Filesystem Timestamps

Use file modification times + stored "last checked" timestamp. Skip files older than last successful run.

**Downside:** Less reliable if files are copied/moved.

## Implementation Steps

1. **Audit each importer** - document current behavior
2. **Define standard interface:**
   ```python
   class Importer:
       def get_pending_files(self) -> List[Path]: ...
       def import_file(self, path: Path) -> ImportResult: ...
       def mark_imported(self, path: Path): ...
   ```
3. **Implement manifest tracking** for Polar importer (worst offender)
4. **Audit Apple Health** importer - may have same issue
5. **Add metrics** - log time spent per step, files checked vs imported

## Quick Win

Before full refactor, add early bailout to Polar importer:

```python
# At start of import_polar_sessions():
known_sessions = set(
    row['polar_session_id'] 
    for row in cur.execute("SELECT polar_session_id FROM polar_sessions")
)

new_files = [
    f for f in session_files 
    if extract_session_id(f.name) not in known_sessions
]

if not new_files:
    log("No new Polar sessions to import")
    return

# Only iterate new_files, not all session_files
```

This trades one bulk query for N individual queries.

## Acceptance Criteria

- [x] Polar: Exits immediately when no new files (single DB query + filename check)
- [x] Apple Health: Skips XML parse when export.xml unchanged (marker file)
- [x] Full reprocess via `--full` flag (Apple Health) or by clearing marker
- [ ] Pipeline completes in <10 seconds when no new data (needs testing)
- [ ] FIT importer: Already uses manifest (no change needed)
- [ ] Ultrahuman: API-based, already efficient (no change needed)

## Related Issues

- Issue 012: Sync script conventions (directory structure)
- Issue 011: Ultrahuman sync plist (scheduling)
- Issue 014: Suunto data ingest (will need same patterns)

## Notes

The Ultrahuman step correctly fetched only recent data:
```
Ultrahuman → Postgres: 2026-01-22 to 2026-01-22 (1 days)
```

This is the right pattern - API-based sources should track last sync date and only fetch new data. File-based sources need equivalent manifest tracking.
