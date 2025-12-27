# Arnold Setup Guide

This guide will walk you through setting up Arnold from scratch.

## Prerequisites

1. **Python 3.10+**
   ```bash
   python --version  # Should be 3.10 or higher
   ```

2. **Neo4j Database**

   Option A: Docker (Recommended)
   ```bash
   docker run -d \
     --name arnold-neo4j \
     -p 7474:7474 -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/your_password_here \
     -e NEO4J_PLUGINS='["apoc"]' \
     -v $HOME/neo4j/data:/data \
     neo4j:latest
   ```

   Option B: Local Installation
   - Download from https://neo4j.com/download/
   - Install and start Neo4j Desktop
   - Create a new database named "arnold"

3. **Git** (for cloning exercise database)
   ```bash
   git --version
   ```

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd arnold
```

### 2. Automated Setup (Recommended)

Arnold automatically creates an **isolated environment** to avoid conflicts:

```bash
# Interactive setup
./setup.sh

# Or one-command quickstart
export NEO4J_PASSWORD=your_password
make quickstart
```

The Makefile will:
- Detect if you have **conda** (uses `arnold` environment) or falls back to **venv** (`.venv/`)
- Create isolated environment automatically
- Install all dependencies in that environment
- Never touch your system Python

### 2b. Manual Environment Setup

If you prefer manual control:

```bash
# Check what environment system will be used
make env-info

# Create isolated environment (conda or venv)
make env-create

# Install dependencies
make install
```

### 3. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env and set your Neo4j password
# NEO4J_PASSWORD=your_password_here
```

### 4. Create User Profile

```bash
# Copy example profile
cp data/user/profile.yaml.example data/user/profile.yaml

# Edit data/user/profile.yaml with your information
```

### 5. Initialize the Database

```bash
# Set up Neo4j schema
python scripts/setup_neo4j.py

# This will:
# - Verify connectivity
# - Create constraints and indexes
# - Display current graph statistics
```

### 6. Import Data

Run the import scripts in order:

```bash
# 1. Import anatomy (UBERON ontology)
# This downloads ~20MB OBO file and imports musculoskeletal structures
python scripts/import_uberon.py

# 2. Import exercises (free-exercise-db)
# This clones the exercise repository and imports 800+ exercises
python scripts/import_exercises.py

# 3. Import your profile
# This imports your goals, injuries, and equipment
python scripts/import_user_profile.py
```

Each import will show progress and statistics.

### 7. Validate Installation

```bash
# Run validation queries
python scripts/validate_phase1.py

# This will test:
# - Exercise-muscle mappings
# - Equipment availability
# - Injury constraints
# - Graph connectivity
```

## Verify Setup

1. **Check Neo4j Browser**
   - Open http://localhost:7474
   - Login with neo4j / your_password
   - Run: `MATCH (n) RETURN count(n) as nodes`
   - You should see 1000+ nodes

2. **Run Example Queries**
   ```cypher
   // What exercises target glutes?
   MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
   WHERE toLower(m.name) CONTAINS 'glute'
   RETURN e.name
   LIMIT 10
   ```

## Expected Results

After successful setup, you should have:

- **Anatomy Layer**: 500-1000 nodes (muscles, joints, bones from UBERON)
- **Exercise Layer**: 800+ exercises from free-exercise-db
- **Equipment**: Your home gym equipment marked as owned
- **Injuries**: Your current injuries with constraints
- **Goals**: Your short and long-term training goals

## Troubleshooting

### Connection Issues

```bash
# Test Neo4j connection
python -c "from neo4j import GraphDatabase; GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password')).verify_connectivity(); print('OK')"
```

### Import Failures

- **UBERON download fails**: The file is large (~20MB). Try downloading manually from http://purl.obolibrary.org/obo/uberon/basic.obo and place in `data/ontologies/`

- **Exercise repo clone fails**: Check git is installed and you have internet access. You can manually clone:
  ```bash
  git clone https://github.com/yuhonas/free-exercise-db data/exercises/
  ```

- **Profile import fails**: Ensure `data/user/profile.yaml` exists and is valid YAML

### Reset Database

To start fresh:

```bash
# WARNING: This deletes all data!
python scripts/setup_neo4j.py --clear
```

## Next Steps

Now that Phase 1 is complete, you can:

1. **Explore the graph** in Neo4j Browser
2. **Run custom queries** using the examples in docs/schema.md
3. **Import workout history** (Phase 2) - coming soon
4. **Set up LLM integration** (Phase 4) - coming soon

## Configuration Files

- `.env` - Database credentials and API keys
- `config/neo4j.yaml` - Neo4j connection settings
- `config/arnold.yaml` - Arnold application settings
- `data/user/profile.yaml` - Your personal profile

## Need Help?

- Check the full spec: `docs/arnold-spec.md`
- Schema reference: `docs/schema.md`
- Example queries in Neo4j Browser
