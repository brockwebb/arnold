# Arnold Profile MCP v0.1

Minimal MCP server for creating and managing user profiles in Arnold.

## Features

- **intake_profile**: Start guided profile creation workflow
- **complete_intake**: Process questionnaire and create profile
- **create_profile**: [Advanced] Direct profile creation (prefer intake workflow)
- **get_profile**: Retrieve the current profile
- **update_profile**: Update specific profile fields

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
Name: Brock
Age: 34
Sex: male
Height: 73
Time Zone: America/New_York

Claude calls: arnold-profile.complete_intake(user_response)

Profile created with provided information
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

- **Person** node with demographic info
- **Athlete** node (role)
- **HAS_ROLE** relationship between Person and Athlete

Updates to demographic fields are automatically synced to Neo4j.

## Testing

1. Install the MCP
2. Add to Claude Desktop config
3. Restart Claude Desktop
4. Test create_profile, get_profile, update_profile

## Next Steps (v0.2+)

- Goal management tools
- Constraint management tools
- Equipment management tools
- Exercise alias management
- Check-in reminders

## Version

v0.1.0 - Minimal profile management foundation
