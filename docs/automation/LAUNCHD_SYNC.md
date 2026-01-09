# macOS Automation: Daily Data Sync

This documents how to set up automated daily syncs using macOS launchd.

## Overview

Arnold's sync pipeline pulls data from external sources (Ultrahuman, Polar, etc.) and loads it into Postgres. Rather than running manually, you can schedule this to run automatically.

## The Sync Script

Location: `scripts/sync_pipeline.py`

What it does:
1. Pulls biometric data from Ultrahuman API
2. Imports any new FIT files from Polar
3. Syncs Neo4j workout refs to Postgres
4. Refreshes materialized views
5. Runs data quality checks

## launchd Setup (macOS)

### 1. Create the plist file

Save to `~/Library/LaunchAgents/com.arnold.sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arnold.sync</string>
    
    <key>ProgramArguments</key>
    <array>
        <!-- Path to your Python interpreter -->
        <string>/usr/local/bin/python3</string>
        <!-- Path to sync script - UPDATE THIS -->
        <string>/path/to/arnold/scripts/sync_pipeline.py</string>
    </array>
    
    <!-- Run daily at 6:00 AM -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <!-- Environment variables (if needed) -->
    <key>EnvironmentVariables</key>
    <dict>
        <!-- Add any required env vars here -->
        <!-- Example: <key>POSTGRES_DSN</key><string>postgresql://...</string> -->
    </dict>
    
    <!-- Working directory -->
    <key>WorkingDirectory</key>
    <string>/path/to/arnold</string>
    
    <!-- Log output -->
    <key>StandardOutPath</key>
    <string>/tmp/arnold-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/arnold-sync-error.log</string>
    
    <!-- Run even if logged out -->
    <key>RunAtLoad</key>
    <false/>
    
    <!-- Don't retry on failure -->
    <key>StartInterval</key>
    <integer>0</integer>
</dict>
</plist>
```

### 2. Update paths

Replace these placeholders:
- `/path/to/arnold/scripts/sync_pipeline.py` → Your actual script path
- `/path/to/arnold` → Your repo directory
- `/usr/local/bin/python3` → Your Python path (run `which python3` to find it)

### 3. Load the job

```bash
# Load the plist
launchctl load ~/Library/LaunchAgents/com.arnold.sync.plist

# Verify it's loaded
launchctl list | grep arnold

# Test run immediately (optional)
launchctl start com.arnold.sync

# Check logs
tail -f /tmp/arnold-sync.log
```

### 4. Managing the job

```bash
# Stop the job
launchctl unload ~/Library/LaunchAgents/com.arnold.sync.plist

# Reload after changes
launchctl unload ~/Library/LaunchAgents/com.arnold.sync.plist
launchctl load ~/Library/LaunchAgents/com.arnold.sync.plist

# Check if running
launchctl list com.arnold.sync
```

## Environment Variables

The sync script may need these environment variables. Add to the plist or use a wrapper script:

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_DSN` | Postgres connection string | Yes |
| `ULTRAHUMAN_API_KEY` | Ultrahuman API key | If using Ultrahuman |
| `NEO4J_URI` | Neo4j connection URI | Yes |
| `NEO4J_USER` | Neo4j username | Yes |
| `NEO4J_PASSWORD` | Neo4j password | Yes |

### Option: Wrapper script

If you have many env vars, create a wrapper script:

```bash
#!/bin/bash
# ~/scripts/arnold-sync-wrapper.sh

# Load environment
source ~/.arnold-env  # File with exports

# Run sync
cd /path/to/arnold
python3 scripts/sync_pipeline.py
```

Then update the plist to call the wrapper instead.

## Troubleshooting

### Job not running?

```bash
# Check job status
launchctl list com.arnold.sync
# Status 0 = success, non-zero = error code

# Check system log
log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h | grep arnold
```

### Permission issues?

```bash
# Check plist permissions
ls -la ~/Library/LaunchAgents/com.arnold.sync.plist
# Should be -rw-r--r--

# Fix if needed
chmod 644 ~/Library/LaunchAgents/com.arnold.sync.plist
```

### Script errors?

Check the error log:
```bash
cat /tmp/arnold-sync-error.log
```

## Security Notes

⚠️ **Do NOT commit the plist with real credentials**

- Use environment variables or a separate `.env` file
- The plist in this repo is a template only
- Keep API keys and passwords out of version control
