#!/bin/bash
# Uninstall Arnold sync launchd agents

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "Uninstalling Arnold sync agents..."

# Unload agents
launchctl unload "$LAUNCH_AGENTS/com.arnold.sync-daily.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/com.arnold.sync-weekly.plist" 2>/dev/null || true

# Remove plist files
rm -f "$LAUNCH_AGENTS/com.arnold.sync-daily.plist"
rm -f "$LAUNCH_AGENTS/com.arnold.sync-weekly.plist"

echo "✓ Uninstalled Arnold sync agents"
