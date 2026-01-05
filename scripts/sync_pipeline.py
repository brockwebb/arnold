#!/usr/bin/env python3
"""
Arnold Data Sync Pipeline

Single entry point for all data synchronization. Idempotent - safe to run repeatedly.

Usage:
    python scripts/sync_pipeline.py              # Run all steps
    python scripts/sync_pipeline.py --step neo4j # Run specific step
    python scripts/sync_pipeline.py --dry-run    # Show what would run

Steps (in order):
    1. polar       - Import new Polar HR exports from data/raw/
    2. ultrahuman  - Fetch new data from Ultrahuman API (if configured)
    3. fit         - Import FIT files (Suunto/Garmin/Wahoo) from data/raw/
    4. apple       - Import Apple Health exports from data/staging/
    5. neo4j       - Sync workouts from Neo4j to Postgres
    6. annotations - Sync annotations from Neo4j to Postgres  
    7. clean       - Run outlier detection on biometrics
    8. refresh     - Refresh Postgres materialized views

Run via cron:
    0 6 * * * cd ~/Documents/GitHub/arnold && /opt/anaconda3/envs/arnold/bin/python scripts/sync_pipeline.py >> logs/sync.log 2>&1
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_RAW = PROJECT_ROOT / "data" / "raw"
SCRIPTS = PROJECT_ROOT / "scripts"
LOGS = PROJECT_ROOT / "logs"

# Ensure logs directory exists
LOGS.mkdir(exist_ok=True)


def log(msg: str, level: str = "INFO"):
    """Log with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def run_script(script_name: str, args: list = None, dry_run: bool = False) -> bool:
    """Run a Python script from the scripts directory."""
    script_path = SCRIPTS / script_name
    if not script_path.exists():
        log(f"Script not found: {script_path}", "ERROR")
        return False
    
    cmd = [sys.executable, str(script_path)] + (args or [])
    
    if dry_run:
        log(f"Would run: {' '.join(cmd)}", "DRY-RUN")
        return True
    
    log(f"Running: {script_name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                log(f"  {line}")
        if result.returncode != 0:
            log(f"Script failed with code {result.returncode}", "ERROR")
            if result.stderr:
                for line in result.stderr.strip().split('\n'):
                    log(f"  {line}", "ERROR")
            return False
        return True
    except Exception as e:
        log(f"Failed to run script: {e}", "ERROR")
        return False


def find_new_polar_exports() -> list:
    """Find Polar export folders that haven't been processed."""
    polar_dirs = []
    if not DATA_RAW.exists():
        return polar_dirs
    
    for item in DATA_RAW.iterdir():
        if item.is_dir() and "polar" in item.name.lower():
            # Check if it contains training session files
            sessions = list(item.glob("training-session-*.json"))
            if sessions:
                polar_dirs.append(item)
    
    return polar_dirs


def step_polar(dry_run: bool = False) -> bool:
    """Import new Polar HR exports."""
    log("=== Step: Polar HR Import ===")
    
    exports = find_new_polar_exports()
    if not exports:
        log("No Polar exports found in data/raw/")
        return True
    
    success = True
    for export_dir in exports:
        log(f"Found Polar export: {export_dir.name}")
        if not run_script("import_polar_sessions.py", [str(export_dir)], dry_run):
            success = False
    
    return success


def step_ultrahuman(dry_run: bool = False) -> bool:
    """Fetch new data from Ultrahuman API and write directly to Postgres."""
    log("=== Step: Ultrahuman API Sync ===")
    
    api_key = os.environ.get("ULTRAHUMAN_AUTH_TOKEN")
    if not api_key:
        log("ULTRAHUMAN_AUTH_TOKEN not set, skipping", "WARN")
        return True
    
    script_path = SCRIPTS / "sync" / "ultrahuman_to_postgres.py"
    if not script_path.exists():
        log("sync/ultrahuman_to_postgres.py not found, skipping", "WARN")
        return True
    
    return run_script("sync/ultrahuman_to_postgres.py", dry_run=dry_run)


def step_fit(dry_run: bool = False) -> bool:
    """Import FIT files (Suunto/Garmin/Wahoo)."""
    log("=== Step: FIT File Import ===")
    
    script_path = SCRIPTS / "import_fit_workouts.py"
    if not script_path.exists():
        log("import_fit_workouts.py not found, skipping", "WARN")
        return True
    
    args = ["--dry-run"] if dry_run else []
    return run_script("import_fit_workouts.py", args, dry_run=False)  # Script handles its own dry-run


def step_apple(dry_run: bool = False) -> bool:
    """Import Apple Health exports."""
    log("=== Step: Apple Health Import ===")
    
    script_path = SCRIPTS / "import_apple_health.py"
    if not script_path.exists():
        log("import_apple_health.py not found, skipping", "WARN")
        return True
    
    return run_script("import_apple_health.py", dry_run=dry_run)


def step_neo4j(dry_run: bool = False) -> bool:
    """Sync workouts from Neo4j to Postgres."""
    log("=== Step: Neo4j → Postgres Sync ===")
    return run_script("sync_neo4j_to_postgres.py", dry_run=dry_run)


def step_annotations(dry_run: bool = False) -> bool:
    """Sync annotations from Neo4j to Postgres."""
    log("=== Step: Annotations Neo4j → Postgres ===")
    return run_script("sync_annotations.py", dry_run=dry_run)


def step_clean(dry_run: bool = False) -> bool:
    """Run outlier detection on biometrics."""
    log("=== Step: Biometric Outlier Detection ===")
    return run_script("clean_biometrics.py", dry_run=dry_run)


def step_refresh(dry_run: bool = False) -> bool:
    """Refresh Postgres materialized views."""
    log("=== Step: Refresh Materialized Views ===")
    
    # Only actual materialized views (not regular views)
    views_to_refresh = [
        "biometric_trends",
        "training_trends",
    ]
    
    if dry_run:
        log(f"Would refresh: {', '.join(views_to_refresh)}", "DRY-RUN")
        return True
    
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://brock@localhost:5432/arnold_analytics")
        cur = conn.cursor()
        
        for view in views_to_refresh:
            log(f"Refreshing {view}...")
            cur.execute(f"REFRESH MATERIALIZED VIEW {view};")
        
        conn.commit()
        conn.close()
        log(f"Refreshed {len(views_to_refresh)} materialized views")
        return True
    except Exception as e:
        log(f"Failed to refresh views: {e}", "ERROR")
        return False


# Step registry
STEPS = {
    "polar": step_polar,
    "ultrahuman": step_ultrahuman,
    "fit": step_fit,
    "apple": step_apple,
    "neo4j": step_neo4j,
    "annotations": step_annotations,
    "clean": step_clean,
    "refresh": step_refresh,
}

STEP_ORDER = ["polar", "ultrahuman", "fit", "apple", "neo4j", "annotations", "clean", "refresh"]

# Database connection
PG_URI = os.environ.get("DATABASE_URI", "postgresql://brock@localhost:5432/arnold_analytics")


def log_sync_start(triggered_by: str) -> int:
    """Log sync start to history table, return sync_id."""
    try:
        conn = psycopg2.connect(PG_URI)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sync_history (triggered_by) VALUES (%s) RETURNING id",
            [triggered_by]
        )
        sync_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return sync_id
    except Exception as e:
        log(f"Failed to log sync start: {e}", "WARN")
        return None


def log_sync_end(sync_id: int, results: dict, error_message: str = None):
    """Log sync completion to history table."""
    if sync_id is None:
        return
    
    # Determine overall status
    statuses = list(results.values())
    if all(s == "success" or s == "skipped" for s in statuses):
        status = "success"
    elif any(s == "success" for s in statuses):
        status = "partial"
    else:
        status = "failed"
    
    try:
        conn = psycopg2.connect(PG_URI)
        cur = conn.cursor()
        cur.execute(
            """UPDATE sync_history 
               SET completed_at = NOW(), 
                   status = %s, 
                   steps_run = %s,
                   error_message = %s
               WHERE id = %s""",
            [status, Json(results), error_message, sync_id]
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Failed to log sync end: {e}", "WARN")


def main():
    parser = argparse.ArgumentParser(description="Arnold Data Sync Pipeline")
    parser.add_argument("--step", choices=STEPS.keys(), help="Run specific step only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--skip", nargs="+", choices=STEPS.keys(), default=[], help="Skip specific steps")
    parser.add_argument("--trigger", choices=["scheduled", "manual", "mcp"], default="manual", help="What triggered this sync")
    args = parser.parse_args()
    
    log("=" * 60)
    log("Arnold Data Sync Pipeline")
    log("=" * 60)
    
    if args.dry_run:
        log("DRY RUN MODE - no changes will be made", "WARN")
    
    # Log sync start (skip for dry runs)
    sync_id = None
    if not args.dry_run:
        sync_id = log_sync_start(args.trigger)
        if sync_id:
            log(f"Sync #{sync_id} started (triggered by: {args.trigger})")
    
    steps_to_run = [args.step] if args.step else STEP_ORDER
    steps_to_run = [s for s in steps_to_run if s not in args.skip]
    
    results = {}
    error_message = None
    
    try:
        for step_name in steps_to_run:
            step_fn = STEPS[step_name]
            success = step_fn(dry_run=args.dry_run)
            results[step_name] = "success" if success else "failed"
    except Exception as e:
        error_message = str(e)
        log(f"Pipeline error: {e}", "ERROR")
    
    # Mark skipped steps
    for step_name in args.skip:
        results[step_name] = "skipped"
    
    log("=" * 60)
    log("Summary:")
    for step_name, status in results.items():
        icon = "✓" if status == "success" else "✗" if status == "failed" else "-"
        log(f"  {icon} {step_name}: {status}")
    
    # Log sync end
    if not args.dry_run:
        log_sync_end(sync_id, results, error_message)
    
    failed = [s for s, r in results.items() if r == "failed"]
    if failed:
        log(f"Pipeline completed with {len(failed)} failures", "WARN")
        sys.exit(1)
    else:
        log("Pipeline completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
