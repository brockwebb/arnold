# Workout Logging Testing Guide (LLM-Native Design)

## Core Principle

**Claude Desktop is the intelligence layer. Tools are dumb data writers.**

NO REGEX. NO PARSING. NO PATTERN MATCHING in tools.

User → Claude interprets → Claude structures → Tool saves → Storage

## What Was Built

### LLM-Native Architecture

**Intelligence Layer (Claude Desktop):**
- Interprets any natural language format
- Identifies exercises from user descriptions
- Maps exercise names to canonical IDs using `find_canonical_exercise`
- Structures data into workout schema
- Handles edge cases, context, aliases

**Data Layer (Tools):**
- `find_canonical_exercise(exercise_name)`: Fuzzy search for canonical exercise ID
- `log_workout(workout_data)`: Saves pre-structured JSON (NO parsing)
- `get_workout_by_date(workout_date)`: Retrieves workout JSON

**Storage:**
- JSON files: `/data/workouts/YYYY-MM-DD.json`
- Neo4j graph: Workout → Set → Exercise nodes with relationships

### Components

1. **WorkoutManager** (`workout_manager.py`)
   - `save_workout()`: Saves structured JSON to file
   - `get_workout_by_date()`: Retrieves workout JSON
   - `get_workout_by_id()`: Retrieves workout by UUID
   - **NO PARSING LOGIC**

2. **Neo4jClient** (`neo4j_client.py`)
   - `find_exercise_by_name()`: Fuzzy search for canonical exercises
   - `create_workout_node()`: Creates Workout → Set → Exercise graph
   - Expects pre-structured data from Claude

3. **Workout Schema** (`/schemas/workout_schema.json`)
   - Defines complete workout structure
   - Claude structures user input into this schema

## Testing in Claude Desktop

### Prerequisites

1. ✅ Profile must exist
   ```bash
   cat /Users/brock/Documents/GitHub/arnold/data/profile.json
   ```

2. ✅ Restart Claude Desktop after updating server

### Test 1: Natural Language Workout (The Magic)

**User message:**
```
"Log yesterday's workout. I did some heavy squats today, worked up to 3 sets
of 5 reps at 225 pounds. Then hit bench press - got 185 for 3 sets of 8.
Finished with a single heavy deadlift at 315. Felt really strong, probably
RPE 8 on the squats."
```

**Expected Claude Desktop behavior:**
1. Interprets natural language
2. Identifies exercises: Back Squat, Bench Press, Deadlift
3. Calls `find_canonical_exercise("Back Squat")` → gets UUID
4. Calls `find_canonical_exercise("Bench Press")` → gets UUID
5. Calls `find_canonical_exercise("Deadlift")` → gets UUID
6. Structures into workout schema with all sets
7. Calls `log_workout(structured_data)`

**Expected output:**
```
✅ Workout logged!

**Date:** 2025-12-26
**Exercises:**
- Back Squat: 3 sets
- Bench Press: 3 sets
- Deadlift: 1 sets

Saved to: /Users/brock/Documents/GitHub/arnold/data/workouts/2025-12-26.json
Neo4j nodes created.
```

**Verification:**
```bash
# Check JSON file
cat /Users/brock/Documents/GitHub/arnold/data/workouts/2025-12-26.json | jq .

# Verify structure
jq '.exercises[0].exercise_id' /Users/brock/Documents/GitHub/arnold/data/workouts/2025-12-26.json
# Should show canonical exercise UUID, not null
```

### Test 2: Various Natural Language Formats

Test that Claude handles ANY format:

**Format variations:**
```
"Log today's workout:
- 3x5 @ 225 back squat
- Bench: three sets of eight at 185
- Single at 315 deadlift"

"Workout from yesterday:
Back squat: worked up to 225 for 5, did that for 3 sets
Bench pressed 185 pounds, 8 reps, 3 sets
One heavy deadlift at 315"

"Squats 225x5x3, bench 185x8x3, deadlift 315x1"
```

Claude should interpret all of these and structure them correctly.

### Test 3: Exercise Mapping

**User message:**
```
"Log workout: Backsquat 225x5x3"
```

**Expected behavior:**
- Claude calls `find_canonical_exercise("Backsquat")` (note: typo/no space)
- Fuzzy search finds "Back Squat" canonical exercise
- Returns exercise_id
- Claude uses that ID in workout structure

**Verification:**
```bash
jq '.exercises[0].exercise_id' /Users/brock/Documents/GitHub/arnold/data/workouts/[date].json
# Should NOT be null - should be canonical exercise UUID
```

### Test 4: Unmapped Exercise

**User message:**
```
"Log workout: Murray Walk 3x30 seconds"
```

**Expected behavior:**
- Claude calls `find_canonical_exercise("Murray Walk")`
- Returns "No canonical exercise found. Use null for exercise_id."
- Claude structures workout with `exercise_id: null`
- Workout still saves successfully

**Verification:**
```bash
jq '.exercises[0]' /Users/brock/Documents/GitHub/arnold/data/workouts/[date].json
```

Should show:
```json
{
  "exercise_name": "Murray Walk",
  "exercise_id": null,
  "purpose": "main-work",
  "sets": [...]
}
```

### Test 5: Complex Context Understanding

**User message:**
```
"Log yesterday's workout. Started with light warmup squats at 135, then 185,
then my working sets were 3x5 at 225. That felt like RPE 8. Then did 5 sets
of bench, first 3 at 185 for 8 reps, last 2 at 205 for 6 reps. Finished
with some accessory leg curls, 3 sets of 12."
```

**Expected Claude behavior:**
- Identifies warmup vs working sets
- Assigns `purpose: "warm-up"` to 135 and 185 squat sets
- Assigns `purpose: "main-work"` to 225 squat sets
- Handles variable reps/load in bench press
- Correctly sequences set numbers
- Applies RPE to appropriate sets

This tests Claude's intelligence - the tool just saves what Claude provides.

### Test 6: Retrieve Workout

**User message:**
```
"Show me my workout from 2025-12-26"
```

**Expected behavior:**
- Claude calls `get_workout_by_date("2025-12-26")`
- Returns complete workout JSON

**Expected output:**
```json
{
  "workout_id": "uuid",
  "person_id": "uuid",
  "date": "2025-12-26",
  "type": "strength",
  "exercises": [...]
}
```

### Test 7: No Profile Error

**Scenario:** User tries to log workout without profile

**Expected behavior:**
- `log_workout()` detects missing person_id
- Tries to auto-fill from profile
- Profile doesn't exist → FileNotFoundError
- Returns error message

**Expected output:**
```
❌ No profile found. Create your profile first using intake_profile.
```

## Success Criteria

- ✅ Tools contain ZERO parsing logic
- ✅ Tools contain ZERO regex
- ✅ Claude Desktop does ALL interpretation
- ✅ User can describe workout in ANY natural language format
- ✅ Claude handles edge cases (warmups, variable weights, context)
- ✅ Exercise mapping to canonical is Claude's job via `find_canonical_exercise`
- ✅ Data saved to JSON + Neo4j
- ✅ Unmapped exercises save successfully with `exercise_id: null`

## Key Design Validation

**This design is correct if:**
1. You can add ANY new workout format and the tool code never changes
2. Exercise aliases are handled by Claude, not code
3. Warmup detection is Claude's intelligence, not regex
4. RPE inference from context ("felt heavy") works without code changes
5. The tool is a "dumb pipe" - it just saves what Claude gives it

**This design is WRONG if:**
1. Adding a new format requires changing tool code
2. Exercise mapping is hardcoded in tools
3. Parsing logic exists in WorkoutManager
4. Tool tries to interpret user intent

## Verification Queries

### Check Canonical Exercise Linkage
```cypher
// Verify sets are linked to canonical exercises
MATCH (w:Workout)-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(ex:Exercise)
WHERE w.date = date('2025-12-26')
RETURN w.date, ex.name, s.reps, s.load_lbs, s.set_number
ORDER BY s.set_number
```

### Check Unmapped Exercises
```cypher
// Find sets NOT linked to canonical exercises (exercise_id was null)
MATCH (w:Workout)-[:CONTAINS]->(s:Set)
WHERE NOT (s)-[:OF_EXERCISE]->()
RETURN w.date, s.set_number, s.reps, s.load_lbs
```

### Workout Stats
```cypher
MATCH (a:Athlete)-[:PERFORMED]->(w:Workout)
OPTIONAL MATCH (w)-[:CONTAINS]->(s:Set)
OPTIONAL MATCH (s)-[:OF_EXERCISE]->(ex:Exercise)
RETURN
  count(DISTINCT w) as total_workouts,
  count(s) as total_sets,
  count(ex) as linked_sets,
  count(s) - count(ex) as unlinked_sets
```

## Troubleshooting

### Claude Not Calling find_canonical_exercise

**Issue:** Claude logs workout with all `exercise_id: null`

**Diagnosis:**
- Check tool description clarity in server.py
- Verify `find_canonical_exercise` tool is in list_tools_handler
- Check Claude Desktop logs for tool availability

**Fix:**
Update tool description to make it clearer that Claude should call this first.

### Exercise Search Returns Nothing

**Issue:** `find_canonical_exercise("Squat")` returns "No canonical exercise found"

**Diagnosis:**
```cypher
// Check if exercises exist
MATCH (ex:Exercise)
WHERE toLower(ex.name) CONTAINS 'squat'
RETURN ex.name
LIMIT 10
```

**Potential causes:**
- Canonical exercise database not imported (see kernel import)
- Exercise name mismatch (e.g., "Barbell Back Squat" vs "Back Squat")

### Workout Not Saving

**Issue:** `log_workout()` fails

**Check:**
1. Profile exists: `cat /Users/brock/Documents/GitHub/arnold/data/profile.json`
2. Workouts directory exists: `ls /Users/brock/Documents/GitHub/arnold/data/workouts/`
3. Permissions: `ls -la /Users/brock/Documents/GitHub/arnold/data/`
4. Check server logs for validation errors in workout_data structure

### Neo4j Node Not Created

**Issue:** JSON saves but Neo4j graph not created

**Check:**
1. Neo4j is running
2. Person/Athlete nodes exist: `MATCH (p:Person) RETURN p.name LIMIT 1`
3. Environment variables correct in Claude Desktop config
4. Check server logs for Neo4j connection errors

## The Power of LLM-Native Design

**Traditional approach (what we DON'T do):**
```python
# BAD: Parsing in tools
def parse_workout_text(text: str):
    if "x" in text:
        match = re.search(r'(\d+)x(\d+)', text)
        sets = int(match.group(1))
        reps = int(match.group(2))
    elif "sets of" in text:
        match = re.search(r'(\d+) sets of (\d+)', text)
        ...
    # Endless regex patterns for every format
```

**LLM-Native approach (what we DO):**
```python
# GOOD: Claude interprets, tool saves
def save_workout(workout_data: dict):
    # workout_data is already perfectly structured by Claude
    with open(filepath, 'w') as f:
        json.dump(workout_data, f, indent=2)
    # That's it. No parsing.
```

**Result:**
- User can say "three sets of five at 225" or "3x5@225" or "did 5 reps at 225 three times"
- ALL work the same
- Tool code NEVER changes
- Claude's intelligence handles variability

This is the future of AI-native applications.
