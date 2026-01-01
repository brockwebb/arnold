# Arnold Profile MCP v0.1

Minimal MCP server for creating and managing user profiles in Arnold.

## Features

### Profile Management
- **intake_profile**: Start guided profile creation workflow
- **complete_intake**: Process questionnaire and create profile
- **create_profile**: [Advanced] Direct profile creation (prefer intake workflow)
- **get_profile**: Retrieve the current profile
- **update_profile**: Update specific profile fields

### Workout Logging (LLM-Native Design)
- **find_canonical_exercise**: Search for canonical exercise IDs by name
- **log_workout**: Save pre-structured workout data (Claude structures, tool saves)
- **get_workout_by_date**: Retrieve a logged workout by date

### Observation Tracking
- **record_observation**: Track body metrics (weight, HR, HRV) with LOINC codes
- Automatic weight observation during profile creation
- Time-series data with proper timestamps

## Installation

```bash
cd /Users/brock/Documents/GitHub/arnold/src/arnold-profile-mcp
pip install -e . --break-system-packages
```

## Configuration

### Environment Variables

Create a `.env` file or set these environment variables:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=arnold
```

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arnold-profile": {
      "command": "python",
      "args": ["/Users/brock/Documents/GitHub/arnold/src/arnold-profile-mcp/server.py"],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "NEO4J_DATABASE": "arnold"
      }
    }
  }
}
```

Restart Claude Desktop after adding this configuration.

## Usage

### Profile Creation Workflow (Recommended)

#### Step 1: Start Intake

```
User: "Create my profile" or "I need to set up Arnold"

Claude calls: arnold-profile.intake_profile()

Returns intake questionnaire with required/optional fields
```

#### Step 2: Complete Intake

```
User provides answers:
Name: Brock Webb
Age: 49
Sex: male
Weight: 158
Date weighed: today
Height: 67.5
Birth Date: 1976-01-02

Claude calls: arnold-profile.complete_intake(user_response)

Profile created with initial weight observation
```

### Direct Profile Creation (Advanced)

For programmatic use, `create_profile()` can be called directly:

```
User: "Create my profile. Name: Brock, Age: 34, Sex: male"

Claude calls: arnold-profile.create_profile(
    name="Brock",
    age=34,
    sex="male"
)
```

### Get Profile

```
User: "Get my profile"

Claude calls: arnold-profile.get_profile()
```

### Update Profile

```
User: "Update my age to 35"

Claude calls: arnold-profile.update_profile(
    field_path="demographics.age",
    value=35
)
```

### Log Workout (LLM-Native Workflow)

**The Intelligence Layer:**
Claude Desktop interprets natural language and structures data. Tools are dumb - they just save.

```
User: "Log yesterday's workout. Did some heavy squats, worked up to 3 sets
of 5 at 225. Then bench press - hit 185 for 3 sets of 8. Finished with a
single heavy deadlift at 315. Felt strong, probably RPE 8 on the squats."

Claude Desktop (internally):
1. Interprets natural language
2. Identifies exercises: Back Squat, Bench Press, Deadlift
3. Calls find_canonical_exercise("Back Squat") → gets exercise_id
4. Calls find_canonical_exercise("Bench Press") → gets exercise_id
5. Calls find_canonical_exercise("Deadlift") → gets exercise_id
6. Structures into workout schema:
{
  "person_id": "auto-filled-from-profile",
  "date": "2025-12-26",
  "type": "strength",
  "exercises": [
    {
      "exercise_name": "Back Squat",
      "exercise_id": "canonical-uuid-from-step-3",
      "purpose": "main-work",
      "sets": [
        {"set_number": 1, "reps": 5, "load_lbs": 225, "rpe": 8},
        {"set_number": 2, "reps": 5, "load_lbs": 225, "rpe": 8},
        {"set_number": 3, "reps": 5, "load_lbs": 225, "rpe": 8}
      ]
    },
    {
      "exercise_name": "Bench Press",
      "exercise_id": "canonical-uuid-from-step-4",
      "purpose": "main-work",
      "sets": [
        {"set_number": 1, "reps": 8, "load_lbs": 185},
        {"set_number": 2, "reps": 8, "load_lbs": 185},
        {"set_number": 3, "reps": 8, "load_lbs": 185}
      ]
    },
    {
      "exercise_name": "Deadlift",
      "exercise_id": "canonical-uuid-from-step-5",
      "purpose": "main-work",
      "sets": [
        {"set_number": 1, "reps": 1, "load_lbs": 315}
      ]
    }
  ]
}
7. Calls log_workout(structured_data)

Tool: Saves to JSON + Neo4j. Done.
```

**Key Design Principle:**
- **NO REGEX** in tools
- **NO PARSING** in tools
- Claude handles ALL interpretation (formats, aliases, context, edge cases)
- Tools are simple data writers

**What Claude Desktop Handles:**
- Any natural language format ("3x5 @ 225", "three sets of five at 225 lbs", etc.)
- Recognizing warmups vs working sets
- Mapping exercise names to canonical IDs
- Understanding context ("felt heavy" → high RPE)
- Handling missing data
- Exercise aliases (user-specific shorthand)

### Get Workout by Date

```
User: "Show me my workout from 2025-12-26"

Claude calls: arnold-profile.get_workout_by_date(
    workout_date="2025-12-26"
)
```

## Profile Schema

The profile is stored in `/data/profile.json` and includes:

- **person_id**: Unique UUID
- **created_at**: Timestamp
- **demographics**: Name, age, sex, height, birth date
- **check_in**: Last check-in, frequency, next reminder
- **exercise_aliases**: User-specific exercise mappings
- **preferences**: Default units, communication style, time zone
- **neo4j_refs**: References to Neo4j nodes

See `/schemas/profile_schema.json` for the complete JSON schema.

## Neo4j Integration

The MCP creates and maintains:

**Profile Nodes:**
- **Person** node with demographic info
- **Athlete** node (role)
- **HAS_ROLE** relationship between Person and Athlete

**Workout Nodes:**
- **Workout** node with date, type, duration, notes
- **Set** node with set_number, reps, load_lbs, rpe, etc.
- **PERFORMED** relationship: Athlete → Workout
- **CONTAINS** relationship: Workout → Set
- **OF_EXERCISE** relationship: Set → Exercise (fuzzy matched to canonical database)

Updates to demographic fields are automatically synced to Neo4j.

When logging workouts, exercise names are fuzzy matched against the canonical exercise database (4,997 exercises). If no match is found, the custom exercise name is stored in the Set node's `custom_exercise_name` property for later mapping.

## Testing

1. Install the MCP
2. Add to Claude Desktop config
3. Restart Claude Desktop
4. Test create_profile, get_profile, update_profile

## Workout Schema

Workouts are stored in `/data/workouts/YYYY-MM-DD.json` and include:

- **workout_id**: Unique UUID
- **person_id**: Reference to person who performed workout
- **date**: Workout date (YYYY-MM-DD)
- **type**: strength, endurance, mobility, sport, mixed
- **exercises**: Array of exercises with sets
  - **exercise_name**: Name of exercise (fuzzy matched to canonical)
  - **purpose**: warm-up, main-work, accessory, cool-down, active-recovery
  - **sets**: Array of sets
    - **set_number**: Set number (1, 2, 3, ...)
    - **reps**: Number of repetitions
    - **load_lbs**: Load in pounds
    - **duration_seconds**: Duration (for timed exercises)
    - **distance_miles**: Distance (for cardio)
    - **rpe**: Rate of perceived exertion (1-10)
    - **notes**: Set-specific notes

See `/schemas/workout_schema.json` for the complete JSON schema.

## Next Steps (v0.2+)

- ✅ Workout logging with freeform text parsing
- Goal management tools
- Constraint management tools
- Equipment management tools
- Exercise alias management
- Check-in reminders
- Workout analytics and querying

## Version

v0.1.3 - Profile management + workout logging + observation tracking
