# Issue 012: Sync Script Directory Convention

**Created:** 2026-01-13  
**Status:** Open  
**Priority:** Low

## Problem

Sync-related scripts are inconsistently organized:

**At `/scripts/` root:**
- `sync_pipeline.py` (orchestrator)
- `sync_annotations.py`
- `sync_exercise_relationships.py`
- `sync_neo4j_to_postgres.py`
- `sync_ultrahuman.py` ← DUPLICATE

**In `/scripts/sync/` subdirectory:**
- `apple_health_to_postgres.py`
- `import_apple_health.py`
- `import_polar_csv.py`
- `polar_api.py`
- `source_resolver.py`
- `stage_ultrahuman.py`
- `sync_ultrahuman.py` ← DUPLICATE
- `ultrahuman_to_postgres.py`
- `validate_config.py`

## Questions to Resolve

1. Should ALL sync scripts live in `/scripts/sync/`?
2. Or is the pattern "orchestrator at root, sources in subdir" intentional?
3. Which `sync_ultrahuman.py` is canonical? Delete the other.
4. Should the MCP's `run_sync` point to `/scripts/sync/sync_pipeline.py` instead?

## Current MCP Reference

`arnold-analytics-mcp` `run_sync` function points to:
```python
script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "sync_pipeline.py"
```

If convention is `/scripts/sync/`, this needs to change to:
```python
script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "sync" / "sync_pipeline.py"
```

## Proposed Convention

Option A: Everything in `/scripts/sync/`
```
/scripts/sync/
├── sync_pipeline.py         # Orchestrator
├── sync_annotations.py
├── sync_exercise_relationships.py
├── sync_neo4j_to_postgres.py
├── polar_api.py
├── ultrahuman_to_postgres.py
└── ...
```

Option B: Keep current (document it)
```
/scripts/
├── sync_pipeline.py         # Top-level orchestrators
├── sync_*.py                # Other orchestrators
└── sync/                    # Individual source scripts
    ├── polar_api.py
    └── ultrahuman_to_postgres.py
```

## Files to Move/Delete

If Option A:
- Move `sync_pipeline.py` → `/scripts/sync/`
- Move `sync_annotations.py` → `/scripts/sync/`
- Move `sync_exercise_relationships.py` → `/scripts/sync/`
- Move `sync_neo4j_to_postgres.py` → `/scripts/sync/`
- Delete `/scripts/sync_ultrahuman.py` (duplicate)
- Update MCP path reference

If Option B:
- Delete one of the duplicate `sync_ultrahuman.py` files
- Document convention in ARCHITECTURE.md

## Related

- Data architecture docs reference `sync_pipeline.py --step relationships`
- Analytics MCP `run_sync` tool depends on script location
- LaunchAgent plist (Issue 011) also references sync scripts
