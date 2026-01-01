# Intake Workflow Testing Guide

## What Was Added

The arnold-profile-mcp now has a **guided intake conversation** workflow instead of requiring direct tool calls with all parameters.

### New Tools

1. **intake_profile()** - Starts the profile creation workflow
   - Checks if profile already exists
   - Returns structured questionnaire
   - No parameters required

2. **complete_intake(intake_response)** - Processes user's questionnaire response
   - Parses freeform text response
   - Validates required fields (name, age, sex)
   - Creates profile + Neo4j nodes
   - Returns confirmation with next steps

### Updated Tools

3. **create_profile()** - Now marked as `[Advanced]`
   - Still available for direct programmatic use
   - Claude should prefer intake workflow

## Testing in Claude Desktop

### Prerequisites

1. ✅ Delete existing profile (if any):
   ```bash
   rm /Users/brock/Documents/GitHub/arnold/data/profile.json
   ```

2. ✅ Restart Claude Desktop after config changes

### Test 1: Start Intake

**User message:**
```
"I need to create my Arnold profile"
```

**Expected behavior:**
- Claude calls `intake_profile()`
- Returns questionnaire with required/optional fields
- Shows example response format

**Expected output:**
```
🏋️ Arnold Profile Creation - Intake Questionnaire

Please provide the following information to create your digital twin profile:

**Required Information:**
1. Name: [Your name]
2. Age: [Your age in years]
3. Sex: [male/female/intersex]
4. Weight: [Current weight in lbs]

**Optional Information:**
5. Height: [Height in inches, or skip]
6. Birth Date: [YYYY-MM-DD format, or skip]
7. Time Zone: [e.g., America/New_York, or skip for default]

**Example Response:**
Name: John Smith
Age: 32
Sex: male
Weight: 185
Height: 72
Birth Date: 1992-06-15
Time Zone: America/Los_Angeles

Once you provide this information, I'll create your profile with these details.
```

### Test 2: Complete Intake

**User provides response:**
```
Name: Brock
Age: 34
Sex: male
Weight: 158
Height: 73
Time Zone: America/New_York
```

**Expected behavior:**
- Claude calls `complete_intake(user_response)`
- Parses the response
- Extracts weight for baseline observation
- Creates profile.json
- Creates Neo4j Person + Athlete nodes
- Returns success confirmation with weight noted

**Expected output:**
```
✅ Profile created successfully!

**Person ID:** [uuid]
**Name:** Brock
**Age:** 34
**Sex:** male
**Weight:** 158 lbs (baseline recorded)

Your Arnold digital twin is now initialized!

Profile saved to /data/profile.json and Neo4j Person node created.

Next steps:
- Add equipment inventory (home gym, commercial gym access)
- Set training goals (strength, hypertrophy, endurance, sport-specific)
- Add constraints (injuries, limitations)
- Create exercise aliases (personal shorthand)
```

### Test 3: Prevent Duplicate

**User message:**
```
"Create my profile"
```

**Expected behavior:**
- Claude calls `intake_profile()`
- Detects existing profile
- Returns error message

**Expected output:**
```
❌ Profile already exists for Brock (ID: [uuid])

Use update_profile to modify existing profile.
```

### Test 4: Verify Profile

**User message:**
```
"Show me my profile"
```

**Expected behavior:**
- Claude calls `get_profile()`
- Returns complete profile JSON

### Test 5: Handle Invalid Response

Delete profile and restart intake, then provide incomplete response:

**User provides:**
```
Name: Bob
Age: 30
```

**Expected behavior:**
- Claude calls `complete_intake(user_response)`
- Parser detects missing `sex` field
- Returns error message

**Expected output:**
```
❌ Invalid intake response: Missing required fields: sex

Please provide all required fields:
- Name
- Age
- Sex (male/female/intersex)
- Weight (lbs)
```

## Success Criteria

- ✅ `intake_profile()` returns questionnaire
- ✅ `intake_profile()` detects existing profile
- ✅ `complete_intake()` parses valid responses
- ✅ `complete_intake()` validates required fields
- ✅ `complete_intake()` creates profile.json
- ✅ `complete_intake()` creates Neo4j nodes
- ✅ User never sees raw `create_profile()` in normal workflow
- ✅ Conversational, guided experience

## Verification Commands

After profile creation, verify in terminal:

```bash
# Check profile.json exists
cat /Users/brock/Documents/GitHub/arnold/data/profile.json

# Check Neo4j Person node
/opt/anaconda3/envs/arnold/bin/python -c "
from arnold.graph import ArnoldGraph
g = ArnoldGraph()
result = g.execute_query('MATCH (p:Person) RETURN p.name, p.age, p.sex')
for r in result:
    print(r)
g.close()
"
```

## Troubleshooting

### MCP Not Showing New Tools

1. Check server.py imports are correct (absolute, not relative)
2. Restart Claude Desktop completely
3. Check Claude Desktop logs: `tail -f ~/Library/Logs/Claude/mcp*.log`

### Parsing Errors

The parser expects this format:
```
Name: <value>
Age: <number>
Sex: male/female/other
Height: <number>  (optional)
Birth Date: YYYY-MM-DD  (optional)
Time Zone: <timezone>  (optional)
```

- Field names are case-insensitive
- "Sex" or "Biological Sex" both work
- Fields can be on separate lines or same line

### Profile Already Exists

If testing multiple times:
```bash
rm /Users/brock/Documents/GitHub/arnold/data/profile.json
```

Then restart workflow.

## Next Steps

Once intake workflow is working:
1. ✅ Profile creation with guided conversation
2. Add equipment intake workflow
3. Add goals intake workflow
4. Add constraints intake workflow
5. Build arnold-orchestrator-mcp to coordinate all workflows
