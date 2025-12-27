# Arnold Installation Guide

## TL;DR - Quick Install

```bash
# Set password and go
export NEO4J_PASSWORD=your_password
make quickstart
```

Done! Arnold creates its own isolated environment and won't touch your system Python.

---

## Environment Isolation

Arnold **always** uses an isolated Python environment:

- **Conda users**: Creates `arnold` conda environment
- **No conda?** Falls back to venv at `.venv/`
- **Zero** system Python modifications

### Check Your Setup

```bash
make env-info
```

Example output:
```
Environment Information
=======================
Environment type: conda
Using: conda
Environment name: arnold
Status: ✓ Environment exists at /opt/conda/envs/arnold

To activate manually:
  conda activate arnold
```

---

## Installation Options

### Option 1: Interactive Setup Script (Easiest)

```bash
./setup.sh
```

This will:
1. Detect conda vs venv
2. Create isolated environment
3. Prompt for Neo4j password
4. Optionally create user profile
5. Start Neo4j and import all data

### Option 2: Make Quickstart (One Command)

```bash
export NEO4J_PASSWORD=your_secure_password
make quickstart
```

Does everything automatically:
- Creates isolated environment (conda or venv)
- Starts Neo4j in Docker
- Installs dependencies
- Imports anatomy, exercises, profile
- Validates installation

### Option 3: Step-by-Step (Manual Control)

```bash
# 1. Check environment
make env-info

# 2. Create environment
make env-create

# 3. Set password
export NEO4J_PASSWORD=your_password

# 4. Start database
make docker-start

# 5. Install dependencies (in isolated env)
make install

# 6. Create .env file
cp .env.example .env
echo "NEO4J_PASSWORD=$NEO4J_PASSWORD" >> .env

# 7. Initialize database
make setup

# 8. Import data
make import

# 9. Validate
make validate
```

---

## Environment Detection Logic

The Makefile automatically detects your setup:

```makefile
if conda available:
    → Create/use: conda env named "arnold"
else:
    → Create/use: venv at ".venv/"
```

All `make` commands automatically:
1. Create environment if needed
2. Activate the environment
3. Run the command in that environment
4. Leave your system Python untouched

---

## Working with the Environment

### Activation

The `make` commands handle activation automatically, but for manual work:

**Conda:**
```bash
conda activate arnold
python scripts/validate_phase1.py
```

**Venv:**
```bash
source .venv/bin/activate
python scripts/validate_phase1.py
```

### Deactivation

**Conda:**
```bash
conda deactivate
```

**Venv:**
```bash
deactivate
```

### Checking Active Environment

```bash
# Should show arnold env, not system python
which python
python --version

# Check installed packages
pip list
```

---

## Environment Commands

```bash
# Show environment info and status
make env-info

# Create environment (idempotent - safe to run multiple times)
make env-create

# Remove environment completely
make env-remove
```

---

## Troubleshooting

### "conda: command not found" but I have conda

The Makefile checks `command -v conda`. If your conda isn't in PATH:

```bash
# Add conda to path, then retry
export PATH="/opt/conda/bin:$PATH"
make env-info
```

Or it will automatically fall back to venv.

### "Python version too old"

Arnold needs Python 3.10+:

**Conda:**
```bash
# Specify Python version
conda create -n arnold python=3.11
conda activate arnold
make install
```

**System Python:**
```bash
# Install Python 3.11, then
python3.11 -m venv .venv
source .venv/bin/activate
make install
```

### "Permission denied" on setup.sh

```bash
chmod +x setup.sh
./setup.sh
```

### Want to switch from venv to conda?

```bash
# Remove venv
make env-remove

# Install conda, then
make env-create  # Will now use conda
```

### Can I use my own environment name?

Edit the Makefile:
```makefile
ENV_NAME := my_custom_name
```

---

## What Gets Installed Where

### In the Arnold Environment

```
arnold (conda) or .venv/ (venv)
├── neo4j driver
├── pronto (ontology parser)
├── pyyaml
├── requests
├── anthropic
├── mcp
└── ... (see requirements.txt)
```

### In Docker

```
arnold-neo4j container
└── Neo4j database + APOC plugins
    └── Data: ~/neo4j/arnold/
```

### System Python

```
Nothing! ✓
```

---

## Verify Isolation

```bash
# Before activating Arnold env
python -c "import neo4j"
# → Should fail (unless you have it globally)

# After activating
conda activate arnold  # or source .venv/bin/activate
python -c "import neo4j"
# → Should work ✓

# After deactivating
conda deactivate  # or deactivate
python -c "import neo4j"
# → Should fail again ✓
```

---

## Uninstall

```bash
# Remove environment
make env-remove

# Remove Neo4j container
make docker-stop
docker volume rm arnold-neo4j

# Remove project
cd ..
rm -rf arnold/
```

---

## Summary

✓ All Python dependencies installed in **isolated environment**
✓ System Python **never modified**
✓ Auto-detects conda vs venv
✓ `make` commands handle activation automatically
✓ Easy to remove completely

"Come with me if you want to lift."
