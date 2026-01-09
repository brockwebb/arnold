#!/bin/bash
# Install Arnold sync launchd agents
# Run from project root: ./config/launchd/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "Installing Arnold sync agents..."

# Ensure LaunchAgents directory exists
mkdir -p "$LAUNCH_AGENTS"

# Unload if already loaded (ignore errors)
launchctl unload "$LAUNCH_AGENTS/com.arnold.sync-daily.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/com.arnold.sync-weekly.plist" 2>/dev/null || true

# Copy plist files
cp "$SCRIPT_DIR/com.arnold.sync-daily.plist" "$LAUNCH_AGENTS/"
cp "$SCRIPT_DIR/com.arnold.sync-weekly.plist" "$LAUNCH_AGENTS/"

# Load agents
launchctl load "$LAUNCH_AGENTS/com.arnold.sync-daily.plist"
launchctl load "$LAUNCH_AGENTS/com.arnold.sync-weekly.plist"

echo ""
echo "✓ Installed and loaded:"
echo "  - com.arnold.sync-daily  (6:00 AM daily, skips relationships)"
echo "  - com.arnold.sync-weekly (5:00 AM Sunday, full sync)"
echo ""
echo "Commands:"
echo "  Test daily:   launchctl start com.arnold.sync-daily"
echo "  Test weekly:  launchctl start com.arnold.sync-weekly"
echo "  Check logs:   tail -f ~/Documents/GitHub/arnold/logs/sync-daily.log"
echo "  Uninstall:    ./config/launchd/uninstall.sh"
