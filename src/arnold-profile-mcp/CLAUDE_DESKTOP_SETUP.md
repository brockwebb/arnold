# Arnold Profile MCP - Claude Desktop Setup

## Prerequisites

1. ✅ MCP package installed (`arnold-profile-mcp`)
2. ✅ Neo4j running at `bolt://localhost:7687`
3. ✅ Arnold conda environment active

## Installation Steps

### 1. Locate Claude Desktop Config

The config file is at:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

### 2. Add Arnold Profile MCP

Edit the config file and add this to the `mcpServers` section:

```json
{
  "mcpServers": {
    "arnold-profile": {
      "command": "/opt/anaconda3/envs/arnold/bin/python",
      "args": [
        "/Users/brock/Documents/GitHub/arnold/src/arnold-profile-mcp/arnold_profile_mcp/server.py"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "YOUR_PASSWORD_HERE",
        "NEO4J_DATABASE": "arnold"
      }
    }
  }
}
```

**IMPORTANT:** Replace `YOUR_PASSWORD_HERE` with your actual Neo4j password.

### 3. Full Example Config

If this is your first MCP, your complete config should look like:

```json
{
  "mcpServers": {
    "arnold-profile": {
      "command": "/opt/anaconda3/envs/arnold/bin/python",
      "args": [
        "/Users/brock/Documents/GitHub/arnold/src/arnold-profile-mcp/arnold_profile_mcp/server.py"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "YOUR_PASSWORD_HERE",
        "NEO4J_DATABASE": "arnold"
      }
    }
  }
}
```

### 4. Restart Claude Desktop

After saving the config:
1. **Quit Claude Desktop completely** (Cmd+Q)
2. **Reopen Claude Desktop**

### 5. Verify MCP is Loaded

In Claude Desktop, check the bottom status bar for a hammer icon 🔨 indicating MCP tools are available.

## Testing in Claude Desktop

### Test 1: Create Profile

```
User: "Create my profile. Name: Brock, Age: 34, Sex: male, Height: 73 inches"
```

Expected response:
```
✅ Profile created successfully!

Person ID: [uuid]
Name: Brock
Age: 34
Sex: male

Profile saved to /data/profile.json and Neo4j Person node created.
```

### Test 2: Get Profile

```
User: "Show me my profile"
```

Expected: Full JSON profile returned.

### Test 3: Update Profile

```
User: "Update my age to 35"
```

Expected: Confirmation that `demographics.age` was updated to 35.

## Troubleshooting

### MCP Not Appearing

1. Check config file syntax (valid JSON)
2. Verify Python path: `/opt/anaconda3/envs/arnold/bin/python`
3. Verify server.py path is correct
4. Check Claude Desktop logs:
   ```
   tail -f ~/Library/Logs/Claude/mcp*.log
   ```

### Connection Errors

1. Verify Neo4j is running: `http://localhost:7474`
2. Check Neo4j password in config
3. Verify database name: `arnold`

### Import Errors

If you see module import errors:
```bash
cd /Users/brock/Documents/GitHub/arnold/src/arnold-profile-mcp
/opt/anaconda3/envs/arnold/bin/pip install -e .
```

## Next Steps

Once the profile MCP is working:
1. ✅ Create your profile in Claude Desktop
2. Add goals management tools (v0.2)
3. Add constraints management tools (v0.2)
4. Add equipment management tools (v0.2)
5. Build arnold-orchestrator-mcp

## Support

For issues:
- Check Neo4j is running
- Verify all paths in config
- Check Claude Desktop logs
- Test standalone: `python arnold_profile_mcp/server.py`
