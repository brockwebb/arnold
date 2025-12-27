# Arnold Quick Reference

## Setup (First Time)

```bash
# Option 1: Interactive setup (recommended)
./setup.sh

# Option 2: One-command setup
export NEO4J_PASSWORD=your_password
make quickstart

# Option 3: Manual
make env-create     # Create isolated environment
make docker-start   # Start Neo4j
make install        # Install dependencies
make setup          # Initialize database
make import         # Import data
```

## Environment Management

```bash
# Check environment status
make env-info

# Create isolated environment (conda or venv)
make env-create

# Activate manually
conda activate arnold        # if conda available
source .venv/bin/activate   # if using venv

# Remove environment
make env-remove
```

## Daily Commands

```bash
make validate     # Check database health
make import       # Re-import data
make clean        # Clear database (WARNING: destructive)
```

## Common Cypher Queries

### Find Exercises

```cypher
// By muscle
MATCH (e:Exercise)-[:TARGETS]->(m:Muscle)
WHERE toLower(m.name) CONTAINS 'glute'
RETURN e.name, e.difficulty
LIMIT 10

// By equipment you own
MATCH (e:Exercise)-[:REQUIRES]->(eq:Equipment)
WHERE eq.user_has = true
RETURN e.name, eq.name
LIMIT 20

// By movement pattern
MATCH (e:Exercise)
WHERE e.force_type = 'pull'
  AND e.mechanic = 'compound'
RETURN e.name, e.difficulty
```

### Check Your Data

```cypher
// Your injuries
MATCH (i:Injury)
WHERE i.status IN ['active', 'recovering']
RETURN i.name, i.status

// Your constraints
MATCH (i:Injury)-[:CREATES]->(c:Constraint)
RETURN i.name, c.description, c.constraint_type

// Your equipment
MATCH (eq:Equipment)
WHERE eq.user_has = true
RETURN eq.name, eq.category
ORDER BY eq.category
```

### Anatomy Exploration

```cypher
// Muscles in a group
MATCH (m:Muscle)
WHERE toLower(m.name) CONTAINS 'quadriceps'
RETURN m.name

// Joints and their movements
MATCH (j:Joint)
RETURN j.name, j.joint_type, j.primary_movements
LIMIT 10
```

## Python Scripts

```bash
# Initialize database
python scripts/setup_neo4j.py
python scripts/setup_neo4j.py --clear  # Reset everything

# Import data
python scripts/import_uberon.py         # Anatomy
python scripts/import_uberon.py --download  # Force re-download
python scripts/import_exercises.py      # Exercises
python scripts/import_exercises.py --update # Update repo
python scripts/import_user_profile.py   # Your data

# Validate
python scripts/validate_phase1.py
```

## File Locations

```
config/arnold.yaml          # Settings
data/user/profile.yaml      # Your profile (create from .example)
.env                        # Database credentials (create from .example)
```

## Troubleshooting

```bash
# Can't connect to Neo4j?
docker ps  # Check if running
docker logs arnold-neo4j  # Check logs

# Import failed?
python scripts/validate_phase1.py  # See what's missing

# Start over?
make clean  # Clear database
make import # Re-import everything
```

## Neo4j Browser Tips

1. **View Schema**
   ```cypher
   CALL db.schema.visualization()
   ```

2. **Count Everything**
   ```cypher
   MATCH (n) RETURN labels(n) as type, count(*) as count
   ORDER BY count DESC
   ```

3. **Sample Data**
   ```cypher
   MATCH (n) RETURN n LIMIT 25
   ```

## Environment Variables

```bash
export NEO4J_PASSWORD=your_password
export NEO4J_URI=bolt://localhost:7687
export ANTHROPIC_API_KEY=sk-...  # For Phase 4
```

## Next Phase Preview

Phase 2 will add:
- Historical workout import
- Volume and progression tracking
- Training trends and analytics

Stay tuned for `scripts/import_workout_history.py`

---

"Hasta la vista, weakness."
