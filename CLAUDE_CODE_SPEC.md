# CLAUDE CODE EXECUTION SPECIFICATION
# Task: Run exercise relationship matcher on Dec 26, 2025 workout

## OBJECTIVE
Execute the exercise matching system to map 8 exercises from the December 26, 2025 workout to canonical exercises using gpt-5o-mini with 6 parallel workers.

## PREREQUISITES
- Files already exist in `/Users/brock/Documents/GitHub/arnold/src/`:
  - exercise_matcher.py
  - map_exercises.py
  - run_exercise_mapping.py
- Neo4j running on bolt://localhost:7687 with database "arnold"
- OpenAI API key available in environment

## EXECUTION STEPS

### Step 1: Verify Files Exist
```bash
cd /Users/brock/Documents/GitHub/arnold/src
ls -la exercise_matcher.py map_exercises.py run_exercise_mapping.py
```
Expected: All three files should exist

### Step 2: Install Dependencies
```bash
pip install openai neo4j python-dotenv tqdm --break-system-packages
```
Expected: All packages install successfully

### Step 3: Check Environment Variables
```bash
echo "OPENAI_API_KEY is set: $([ -n "$OPENAI_API_KEY" ] && echo 'YES' || echo 'NO')"
echo "NEO4J_PASSWORD is set: $([ -n "$NEO4J_PASSWORD" ] && echo 'YES' || echo 'NO')"
```
Expected: Both should say YES
If NO: Prompt user for missing keys

### Step 4: Verify Neo4j Connection
```bash
python3 << 'EOF'
import os
from neo4j import GraphDatabase

try:
    driver = GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", os.getenv("NEO4J_PASSWORD"))
    )
    with driver.session(database="arnold") as session:
        result = session.run("MATCH (ex:Exercise) RETURN count(ex) as total")
        count = result.single()["total"]
        print(f"✅ Connected to Neo4j. Found {count} exercises.")
    driver.close()
except Exception as e:
    print(f"❌ Neo4j connection failed: {e}")
    exit(1)
EOF
```
Expected: Connection succeeds and shows exercise count

### Step 5: Verify Exercises Need Mapping
```bash
python3 << 'EOF'
import os
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", os.getenv("NEO4J_PASSWORD"))
)

with driver.session(database="arnold") as session:
    result = session.run("""
        MATCH (w:Workout {date: date('2025-12-26')})-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(ex:Exercise)
        WHERE NOT (ex)-[:TARGETS]->(:MuscleGroup)
        RETURN DISTINCT ex.name as name
        ORDER BY ex.name
    """)
    
    exercises = [r["name"] for r in result]
    print(f"\n📋 Exercises needing mapping ({len(exercises)}):")
    for ex in exercises:
        print(f"  - {ex}")

driver.close()
EOF
```
Expected: Shows 8 exercises (Light Boxing, Sandbag Shoulder, etc.)

### Step 6: Execute Exercise Matcher
```bash
cd /Users/brock/Documents/GitHub/arnold/src
python3 run_exercise_mapping.py
```

Expected output format:
```
================================================================================
MAPPING EXERCISES FROM DECEMBER 26, 2025 WORKOUT
================================================================================

This will:
1. Search 5,000+ canonical exercises for matches
2. Use LLM to analyze exercise relationships
3. Create knowledge graph relationships
4. Inherit muscle group mappings

================================================================================

📋 Found 8 exercises to map

Matching exercises: 100%|████████████| 8/8 [00:30<00:00,  3.75s/it]

🔍 Matching: Light Boxing
  Found 12 candidates:
    - Shadow Boxing
    - Heavy Bag Punching
    - Boxing Workout
  
  Analyzing: Shadow Boxing
    Type: SIMILAR_TO
    Confidence: 0.78
    Reasoning: Light boxing is similar to shadow boxing...
  
  ✅ Created SIMILAR_TO relationship
     → Shadow Boxing
     → Inherited muscle mappings

[... repeats for all 8 exercises ...]

================================================================================
MAPPING SUMMARY
================================================================================

✅ Matched: 7/8
❌ Unmatched: 1/8

--------------------------------------------------------------------------------
MATCHED EXERCISES:
--------------------------------------------------------------------------------

Light Boxing
  → Shadow Boxing
  → Relationship: SIMILAR_TO
  → Confidence: 78%
  → ✓ Muscle groups inherited

[... etc for all matched exercises ...]

================================================================================
✅ EXERCISE MAPPING COMPLETE
================================================================================

Your workout now has intelligent muscle tracking!
```

### Step 7: Validate Results in Neo4j
```bash
python3 << 'EOF'
import os
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", os.getenv("NEO4J_PASSWORD"))
)

with driver.session(database="arnold") as session:
    # Check for relationships
    result = session.run("""
        MATCH (ex:Exercise {source: 'user'})-[r]->(canonical:Exercise)
        WHERE type(r) IN ['EXACT_MATCH', 'VARIATION_OF', 'SIMILAR_TO', 'SUBSTITUTES_FOR']
        RETURN ex.name as user_ex, type(r) as rel_type, canonical.name as canonical_ex
        ORDER BY user_ex
    """)
    
    print("\n✅ Created Relationships:")
    for r in result:
        print(f"  {r['user_ex']} --{r['rel_type']}--> {r['canonical_ex']}")
    
    # Check muscle inheritances
    result2 = session.run("""
        MATCH (w:Workout {date: date('2025-12-26')})-[:CONTAINS]->(s:Set)-[:OF_EXERCISE]->(ex:Exercise)
        WHERE ex.source = 'user'
        OPTIONAL MATCH (ex)-[:TARGETS]->(mg:MuscleGroup)
        RETURN DISTINCT ex.name as exercise, collect(mg.name) as muscles
        ORDER BY exercise
    """)
    
    print("\n✅ Muscle Mappings:")
    for r in result2:
        muscles = ", ".join(r['muscles']) if r['muscles'] else "None"
        print(f"  {r['exercise']}: {muscles}")

driver.close()
EOF
```

Expected: Shows all 8 exercises with relationships and muscle groups

## SUCCESS CRITERIA

1. ✅ All dependencies installed
2. ✅ Neo4j connection successful  
3. ✅ 8 exercises identified for mapping
4. ✅ run_exercise_mapping.py executes without errors
5. ✅ At least 6/8 exercises matched (>75% success rate)
6. ✅ Matched exercises have muscle group mappings
7. ✅ Knowledge graph relationships created (SIMILAR_TO, VARIATION_OF, etc.)

## ERROR HANDLING

### If OpenAI API key missing:
```bash
echo "Please set OPENAI_API_KEY:"
echo "export OPENAI_API_KEY='sk-...'"
```

### If Neo4j password missing:
```bash
echo "Please set NEO4J_PASSWORD:"
echo "export NEO4J_PASSWORD='your-password'"
```

### If Neo4j connection fails:
- Check Neo4j is running: `ps aux | grep neo4j`
- Check port 7687 is accessible: `nc -zv localhost 7687`
- Verify database exists: Check Neo4j Browser

### If OpenAI API fails:
- Check API key is valid
- Check rate limits not exceeded
- Reduce NUM_WORKERS from 6 to 3 in exercise_matcher.py if rate limited

### If matching confidence is low (<50%):
- This is normal for some exercises (e.g., "Light Boxing" is not well-defined)
- Manual mapping may be needed
- Check logs for reasoning

## DELIVERABLES

After successful execution, provide:
1. Console output from run_exercise_mapping.py
2. Validation results showing relationships created
3. Summary: "X/8 exercises matched, Y muscle groups inherited"
4. Any errors or warnings encountered

## NOTES FOR CLAUDE CODE

- Execute each step sequentially
- Don't proceed if any step fails
- Capture all output for the user
- If prompted for input, ask user first
- The script may take 30-60 seconds to run (parallel LLM calls)
- Progress bar will show real-time status
