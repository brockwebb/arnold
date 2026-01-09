# Automated Data Sync with macOS LaunchAgent

This guide shows how to set up automated daily data sync using macOS LaunchAgents.

## Overview

Arnold's sync pipeline pulls data from:
- Ultrahuman API (HRV, sleep, recovery)
- Polar exports (HR sessions)
- Apple Health exports
- FIT files

You can automate this to run daily.

## Setup

### 1. Create the LaunchAgent plist

Save this as `~/Library/LaunchAgents/com.arnold.sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arnold.sync</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/your/venv/bin/python</string>
        <string>/path/to/arnold/scripts/sync_pipeline.py</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>/tmp/arnold-sync.log</string>
    
    <key>StandardErrorPath</key>
    <string>/tmp/arnold-sync-error.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <!-- Environment variables loaded from .env file by script -->
        <!-- Or set them here if preferred -->
    </dict>
    
    <key>WorkingDirectory</key>
    <string>/path/to/arnold</string>
    
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

### 2. Update paths

Replace these placeholders with your actual paths:
- `/path/to/your/venv/bin/python` → Your Python interpreter
- `/path/to/arnold` → Your Arnold repo location

Example:
```xml
<string>/Users/yourname/Documents/GitHub/arnold/.venv/bin/python</string>
<string>/Users/yourname/Documents/GitHub/arnold/scripts/sync_pipeline.py</string>
```

### 3. Load the LaunchAgent

```bash
# Load (enables the schedule)
launchctl load ~/Library/LaunchAgents/com.arnold.sync.plist

# Unload (disables)
launchctl unload ~/Library/LaunchAgents/com.arnold.sync.plist

# Test run immediately
launchctl start com.arnold.sync

# Check if loaded
launchctl list | grep arnold
```

### 4. Check logs

```bash
# View output
tail -f /tmp/arnold-sync.log

# View errors
tail -f /tmp/arnold-sync-error.log
```

## Configuration Options

### Run at different times

Change `StartCalendarInterval`:

```xml
<!-- Every day at 6 AM -->
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>0</integer>
</dict>

<!-- Every hour -->
<key>StartCalendarInterval</key>
<dict>
    <key>Minute</key>
    <integer>0</integer>
</dict>

<!-- Every Monday at 7 AM -->
<key>StartCalendarInterval</key>
<dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>0</integer>
</dict>
```

### Run specific sync steps

Modify ProgramArguments to run specific steps:

```xml
<key>ProgramArguments</key>
<array>
    <string>/path/to/venv/bin/python</string>
    <string>/path/to/arnold/scripts/sync_pipeline.py</string>
    <string>--steps</string>
    <string>ultrahuman,neo4j</string>
</array>
```

Available steps: `polar`, `ultrahuman`, `fit`, `apple`, `neo4j`, `annotations`, `clean`, `refresh`

## Troubleshooting

### LaunchAgent not running

```bash
# Check if loaded
launchctl list | grep arnold

# Check for errors
launchctl error system/<error_code>

# View system log
log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h | grep arnold
```

### Permission issues

Ensure your Python script is executable:
```bash
chmod +x /path/to/arnold/scripts/sync_pipeline.py
```

### Environment variables

If your sync script needs API keys or database credentials, ensure they're available. Options:

1. **Use .env file** (recommended): The sync script loads from `.env` automatically
2. **Set in plist**: Add to `EnvironmentVariables` dict (less secure, visible in plist)
3. **Use macOS Keychain**: For sensitive credentials

## Security Notes

- **Never commit your plist with credentials** to version control
- The example above uses environment variables loaded from `.env`
- API keys should be stored in `.env` (gitignored) or macOS Keychain
- Log files may contain sensitive data; review before sharing

## See Also

- `scripts/sync_pipeline.py` — The sync script
- `docs/mcps/arnold-analytics.md` — Data sources documentation
- Apple's [launchd documentation](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
