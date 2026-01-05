# Claude Desktop Setup for Arnold Journal MCP

## Prerequisites

1. PostgreSQL running with `arnold_analytics` database
2. Neo4j running with `arnold` database
3. Migration 009 applied: `psql arnold_analytics < scripts/migrations/009_journal_system.sql`
4. Python 3.12+ with virtual environment

## Installation

```bash
# Navigate to the MCP directory
cd ~/Documents/GitHub/arnold/src/arnold-journal-mcp

# Install in development mode
pip install -e .

# Verify installation
which arnold-journal-mcp
```

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arnold-journal": {
      "command": "/path/to/your/venv/bin/arnold-journal-mcp",
      "env": {
        "POSTGRES_DSN": "postgresql://brock@localhost:5432/arnold_analytics",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

Replace `/path/to/your/venv/bin/arnold-journal-mcp` with the actual path from `which arnold-journal-mcp`.

## Verify Setup

1. Restart Claude Desktop
2. Check MCP connection in Claude Desktop settings
3. Test with: "Log that my legs are sore today"

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DSN` | `postgresql://brock@localhost:5432/arnold_analytics` | Postgres connection |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password |

## Logs

Logs are written to `/tmp/arnold-journal-mcp.log`

## Troubleshooting

### MCP not connecting
- Check that migration 009 has been applied
- Verify both POSTGRES_DSN and NEO4J_* are correct
- Check logs at `/tmp/arnold-journal-mcp.log`

### Entries not saving
- Verify `log_entries` table exists: `\d log_entries` in psql
- Check Postgres connection

### Relationships not creating
- Verify Neo4j is running and accessible
- Check that Person node exists: `MATCH (p:Person {name: 'Brock Webb'}) RETURN p`
