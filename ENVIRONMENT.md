# Arnold Environment Management

## Overview

Arnold **never modifies your system Python**. All dependencies are installed in an isolated environment that's automatically created and managed for you.

## How It Works

```
┌─────────────────────────────────────────────┐
│  Your System Python                         │
│  (Completely untouched)                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Arnold Isolated Environment                │
│                                             │
│  Conda:  arnold env                         │
│    or                                       │
│  Venv:   .venv/                            │
│                                             │
│  All Arnold dependencies installed here    │
└─────────────────────────────────────────────┘
```

## Automatic Detection

When you run `make quickstart`, `make install`, or any make command:

1. **Detects** if conda is installed
2. **Chooses** environment type:
   - Conda available → Creates/uses `arnold` conda environment
   - No conda → Creates/uses `.venv/` venv
3. **Creates** environment if it doesn't exist
4. **Activates** environment
5. **Runs** command in isolated environment
6. Your system Python is never touched

## Quick Start

Just run:

```bash
export NEO4J_PASSWORD=your_password
make quickstart
```

That's it! Arnold will:
- ✓ Create isolated environment (conda or venv)
- ✓ Install all dependencies there
- ✓ Start Neo4j
- ✓ Import all data
- ✓ Never touch system Python

## Environment Commands

```bash
# See what environment system will be used
make env-info

# Create environment (safe to run multiple times)
make env-create

# Install dependencies (automatically creates env first)
make install

# Remove environment completely
make env-remove

# All other make commands automatically use the isolated env:
make setup     # Creates env if needed, then runs
make import    # Creates env if needed, then runs
make validate  # Creates env if needed, then runs
```

## Example: First Time Setup

```bash
$ make env-info
Environment Information
=======================
Environment type: conda
Using: conda
Environment name: arnold
Status: ✗ Environment not created yet

$ export NEO4J_PASSWORD=mypassword123

$ make quickstart
Creating isolated Python environment...
Creating conda environment: arnold
✓ Conda environment created

Installing dependencies in isolated environment...
✓ Dependencies installed

Starting Neo4j container...
✓ Neo4j started

Initializing Neo4j database...
✓ Connected

Importing UBERON anatomy...
✓ Imported 874 anatomy nodes

Importing exercises...
✓ Imported 826 exercises

✓ Arnold Phase 1 setup complete!

Environment: conda
To activate: conda activate arnold
```

## Manual Activation

The `make` commands handle activation automatically, but if you want to run Python scripts manually:

**If using conda:**
```bash
conda activate arnold
python scripts/validate_phase1.py
conda deactivate
```

**If using venv:**
```bash
source .venv/bin/activate
python scripts/validate_phase1.py
deactivate
```

## Checking Isolation

Verify that your system Python is untouched:

```bash
# System Python (Arnold NOT activated)
$ python -c "import neo4j"
ModuleNotFoundError: No module named 'neo4j'
✓ Good! System Python is clean

# Arnold environment
$ conda activate arnold  # or: source .venv/bin/activate
$ python -c "import neo4j; print('✓ Works!')"
✓ Works!

# Back to system
$ conda deactivate  # or: deactivate
$ python -c "import neo4j"
ModuleNotFoundError: No module named 'neo4j'
✓ Still clean!
```

## What's Installed Where

### System Python
```
Nothing! Completely untouched.
```

### Arnold Environment (conda or venv)
```
neo4j>=5.14.0      - Neo4j driver
pronto>=2.5.4      - Ontology parser
pyyaml>=6.0        - YAML files
requests>=2.31.0   - HTTP requests
anthropic>=0.39.0  - Claude API
mcp>=1.0.0         - Model Context Protocol
pytest, black, ruff (dev tools)
```

### Docker Container
```
Neo4j database (arnold-neo4j)
Data stored: ~/neo4j/arnold/
```

## Environment Preferences

### Force Venv (Even if Conda Available)

Edit `Makefile`, comment out conda detection:
```makefile
# CONDA := $(shell command -v conda 2> /dev/null)
CONDA :=
```

### Use Different Conda Env Name

Edit `Makefile`:
```makefile
ENV_NAME := my_custom_name
```

### Use Different Venv Path

Edit `Makefile`:
```makefile
VENV_PATH := my_custom_venv
```

## Troubleshooting

### "Environment not activated"

All `make` commands activate automatically. But if running scripts directly:

```bash
# Wrong - uses system Python
python scripts/setup_neo4j.py

# Right - use make (auto-activates)
make setup

# Or activate manually first
conda activate arnold
python scripts/setup_neo4j.py
```

### "Already have arnold conda env"

No problem! The Makefile will use it:

```bash
$ make env-create
✓ Conda environment already exists
```

### Want fresh start?

```bash
make env-remove  # Removes environment
make env-create  # Creates fresh environment
make install     # Reinstalls dependencies
```

## Complete Removal

To uninstall Arnold completely:

```bash
# 1. Remove environment
make env-remove

# 2. Stop and remove Neo4j
make docker-stop
docker volume rm $(docker volume ls -q | grep arnold)

# 3. Remove project
cd ..
rm -rf arnold/
```

Your system Python: Still pristine ✓

## Summary

| Aspect | Status |
|--------|--------|
| System Python modified? | ❌ Never |
| Isolated environment? | ✓ Always |
| Auto-detection? | ✓ Conda or venv |
| Manual activation needed? | ❌ Make handles it |
| Can remove cleanly? | ✓ Yes |

---

> "Your system Python. Give it to me."
>
> "No."
>
> Arnold creates isolated environment instead.
