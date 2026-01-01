# Obsidian Workout Import

Import your historical Obsidian workout logs into Neo4j Arnold database.

## Prerequisites

```bash
pip install pyyaml tqdm --break-system-packages
```

## Usage

### 1. Verify your Obsidian workout directory

The script defaults to: `~/Documents/obsidian-vault/workouts`

If your workouts are elsewhere, use `--dir`:

```bash
python import_obsidian_workouts.py --dir /path/to/your/workouts
```

### 2. Dry run first (recommended)

See what would be imported without actually importing:

```bash
cd ~/Documents/GitHub/arnold/src
python import_obsidian_workouts.py --dry-run
```

This will:
- Find all workout markdown files
- Parse the first one as an example
- Show you what data would be imported

### 3. Test with a few files

Import just the first 5 workouts to verify everything works:

```bash
python import_obsidian_workouts.py --limit 5
```

### 4. Full import

Import all workouts:

```bash
python import_obsidian_workouts.py
```

## Expected Obsidian Format

The script expects markdown files like:

```markdown
---
date: 2025-12-26
type: strength
duration: 60
notes: "Good session"
---

## Barbell Bench Press
- 10 reps x 135 lbs
- 8 reps x 155 lbs
- 6 reps x 175 lbs

## Turkish Get-Up
- 5 reps x 35 lbs
- 5 reps x 35 lbs

## Ab Wheel Rollout
- 10 reps
- 8 reps
- 6 reps
```

**Supported formats:**
- `10 reps x 135 lbs` - reps with load
- `10 reps` - bodyweight reps
- `30 seconds` - duration
- `100m` - distance
- `Set 1: 10 reps x 135 lbs` - with set number prefix

**Flexible on:**
- Frontmatter (optional, will extract date from filename if missing)
- Load units (lbs assumed)
- Separator (x or @)

## What It Does

1. **Scans directory** for `.md` files
2. **Parses each file:**
   - Extracts YAML frontmatter (date, type, duration, notes)
   - Parses exercise sections (## headers)
   - Parses set data (bullet points)
3. **Matches exercises** to ExerciseVariants/Archetypes:
   - Tries exact name match
   - Tries fuzzy match
   - Creates unmatched exercises as user exercises
4. **Creates workout in Neo4j:**
   - Workout node with date, type, duration
   - Set nodes with reps, load, duration
   - Relationships: Workout→Set→Exercise
   - Auto-maps to variants where possible

## Output

```
================================================================================
OBSIDIAN WORKOUT IMPORT
================================================================================

Scanning: /Users/brock/Documents/obsidian-vault/workouts
Found 162 workout files

Parsing and importing...

Importing workouts: 100%|████████████████| 162/162 [01:23<00:00,  1.94it/s]

================================================================================
IMPORT SUMMARY
================================================================================

Files found:       162
Files parsed:      158
Files skipped:     4
Workouts created:  158

Exercises matched:   432
Exercises unmatched: 78

⚠️  Some exercises were not matched to archetypes/variants
   Run exercise matcher to map them
```

## After Import

### View imported workouts

```cypher
MATCH (w:Workout)
WHERE w.source = 'obsidian_import'
RETURN w.date, w.type, count{(w)-[:CONTAINS]->(:Set)} as sets
ORDER BY w.date DESC
LIMIT 10
```

### Find unmatched exercises

```cypher
MATCH (ex:Exercise {source: 'user'})
WHERE NOT (ex)-[:MAPS_TO]->()
RETURN ex.name, count{(:Set)-[:OF_EXERCISE]->(ex)} as usage_count
ORDER BY usage_count DESC
```

### Map unmatched exercises

```bash
# Use the exercise matcher to map unmatched exercises
python map_exercises.py
```

## Troubleshooting

**"No workout files found"**
- Check the directory path with `--dir`
- Verify markdown files exist in that location

**"Error parsing YYYY-MM-DD-workout.md"**
- Check the file format matches expected structure
- Run with `--dry-run` to see parse errors

**"Workout YYYY-MM-DD already exists, skipping"**
- The script won't re-import existing workouts
- Delete from Neo4j first if you want to re-import

**Many exercises unmatched**
- This is normal if you have custom exercise names
- Run `python map_exercises.py` after import
- Or manually create ExerciseVariants for common exercises

## Example Workflow

```bash
# 1. Dry run to verify format
python import_obsidian_workouts.py --dry-run

# 2. Test with 5 workouts
python import_obsidian_workouts.py --limit 5

# 3. Check in Neo4j Browser
# Run queries to verify data looks correct

# 4. Full import
python import_obsidian_workouts.py

# 5. Map unmatched exercises
python map_exercises.py

# 6. Verify complete import
# Check workout count, exercise mappings, muscle targets
```

## Performance

- ~1-2 workouts/second
- 160 workouts = ~1-2 minutes
- Faster with SSD and local Neo4j

## Safety

- Won't overwrite existing workouts (checks by date)
- Won't delete any data
- Safe to run multiple times
- Use `--limit` to test first
