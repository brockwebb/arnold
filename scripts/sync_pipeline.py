#!/usr/bin/env python3
"""
Arnold Data Sync Pipeline

Single entry point for all data synchronization. Idempotent - safe to run repeatedly.

Usage:
    python scripts/sync_pipeline.py              # Run all steps
    python scripts/sync_pipeline.py --step neo4j # Run specific step
    python scripts/sync_pipeline.py --dry-run    # Show what would run

Steps (in order):
    1. polar     - Import new Polar HR exports from data/raw/
    2. ultrahuman - Fetch new data from Ultrahuman API (if configured)
    3. apple     - Import Apple Health exports from data/staging/
    4. neo4j     - Sync workouts from Neo4j to Postgres
    5. clean     - Run outlier detection on biometrics
    6. refresh   - Refresh Postgres materialized views

Run via cron:
    0 6 * * * cd ~/Documents/GitHub/arnold && /opt/anaconda3/envs/arnold/bin/python scripts/sync_pipeline.py >> logs/sync.log 2>&1
"""

import os
import sys
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

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
    """Fetch new data from Ultrahuman API."""
    log("=== Step: Ultrahuman API Sync ===")
    
    api_key = os.environ.get("ULTRAHUMAN_AUTH_TOKEN")
    if not api_key:
        log("ULTRAHUMAN_AUTH_TOKEN not set, skipping", "WARN")
        return True
    
    script_path = SCRIPTS / "sync_ultrahuman.py"
    if not script_path.exists():
        log("sync_ultrahuman.py not implemented yet, skipping", "WARN")
        return True
    
    return run_script("sync_ultrahuman.py", dry_run=dry_run)


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


def step_clean(dry_run: bool = False) -> bool:
    """Run outlier detection on biometrics."""
    log("=== Step: Biometric Outlier Detection ===")
    return run_script("clean_biometrics.py", dry_run=dry_run)


def step_refresh(dry_run: bool = False) -> bool:
    """Refresh Postgres materialized views."""
    log("=== Step: Refresh Materialized Views ===")
    
    if dry_run:
        log("Would refresh: training_load_daily, readiness_daily", "DRY-RUN")
        return True
    
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://brock@localhost:5432/arnold_analytics")
        cur = conn.cursor()
        
        log("Refreshing training_load_daily...")
        cur.execute("REFRESH MATERIALIZED VIEW training_load_daily;")
        
        log("Refreshing readiness_daily...")
        cur.execute("REFRESH MATERIALIZED VIEW readiness_daily;")
        
        conn.commit()
        conn.close()
        log("Views refreshed")
        return True
    except Exception as e:
        log(f"Failed to refresh views: {e}", "ERROR")
        return False


# Step registry
STEPS = {
    "polar": step_polar,
    "ultrahuman": step_ultrahuman,
    "apple": step_apple,
    "neo4j": step_neo4j,
    "clean": step_clean,
    "refresh": step_refresh,
}

STEP_ORDER = ["polar", "ultrahuman", "apple", "neo4j", "clean", "refresh"]


def main():
    parser = argparse.ArgumentParser(description="Arnold Data Sync Pipeline")
    parser.add_argument("--step", choices=STEPS.keys(), help="Run specific step only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--skip", nargs="+", choices=STEPS.keys(), default=[], help="Skip specific steps")
    args = parser.parse_args()
    
    log("=" * 60)
    log("Arnold Data Sync Pipeline")
    log("=" * 60)
    
    if args.dry_run:
        log("DRY RUN MODE - no changes will be made", "WARN")
    
    steps_to_run = [args.step] if args.step else STEP_ORDER
    steps_to_run = [s for s in steps_to_run if s not in args.skip]
    
    results = {}
    for step_name in steps_to_run:
        step_fn = STEPS[step_name]
        success = step_fn(dry_run=args.dry_run)
        results[step_name] = "✓" if success else "✗"
    
    log("=" * 60)
    log("Summary:")
    for step_name, status in results.items():
        log(f"  {status} {step_name}")
    
    failed = [s for s, r in results.items() if r == "✗"]
    if failed:
        log(f"Pipeline completed with {len(failed)} failures", "WARN")
        sys.exit(1)
    else:
        log("Pipeline completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
