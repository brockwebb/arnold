# Issue 011: Ultrahuman HRV Sync LaunchAgent Not Running

**Created:** 2026-01-13  
**Status:** CLOSED (Misdiagnosed)  
**Priority:** N/A

## Resolution (2026-01-13)

The plist is working correctly. Investigation revealed:

1. **Plist IS loaded and running** - logs show successful runs at 6 AM
2. **Ultrahuman sync reported success** - but API returned incomplete data
3. **Real cause: API data gaps** - not a sync infrastructure issue

### Evidence

```sql
-- biometric_readings from Ultrahuman shows:
-- Jan 12: Only vo2_max (no HRV, sleep, recovery)
-- Jan 11: Only resting_hr + vo2_max (no HRV)
-- Jan 10 and earlier: Full data
```

The script correctly fetches what the API returns, but the API returned incomplete data for Jan 11-12. This is either:
- Ring wasn't worn those nights
- Ultrahuman API data processing latency

### Recommendation

Add verbose logging to `ultrahuman_to_postgres.py` to print API responses when data is sparse, making it easier to distinguish between "no data available" vs "sync failure".

---

## Original Problem (Misdiagnosed)

The macOS LaunchAgent plist for automated Ultrahuman data sync is not running in the morning as expected. This causes HRV data gaps (currently 3 days missing).

HRV is a critical readiness metric - gaps break the coaching feedback loop.

## Expected Behavior

- LaunchAgent runs daily (e.g., 6:00 AM)
- Pulls HRV, sleep, and recovery data from Ultrahuman API
- Writes to `readiness_daily` table in Postgres
- Data available for morning briefing

## Current Behavior (ACTUALLY WORKING)

- Sync IS running automatically
- API IS returning data, but it's incomplete
- Gaps in HRV are from source (Ultrahuman), not sync infrastructure

## Investigation Needed

1. Check if plist is loaded:
   ```bash
   launchctl list | grep ultrahuman
   ```

2. Check plist location and syntax:
   ```bash
   ls -la ~/Library/LaunchAgents/*ultrahuman*
   plutil -lint ~/Library/LaunchAgents/com.arnold.ultrahuman-sync.plist
   ```

3. Check logs for errors:
   ```bash
   cat /tmp/ultrahuman-sync.log
   # or wherever logs are configured
   ```

4. Test manual execution of the sync script

## Common plist Issues

- **Not loaded after reboot** - Need to `launchctl load` again
- **Script path wrong** - Absolute paths required
- **Python env not activated** - Need full path to conda/venv python
- **Permissions** - Script not executable
- **Working directory** - Script expects specific cwd
- **Network timing** - Runs before network is up

## Potential Fixes

1. **Reload the agent:**
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.arnold.ultrahuman-sync.plist
   launchctl load ~/Library/LaunchAgents/com.arnold.ultrahuman-sync.plist
   ```

2. **Add KeepAlive or retry logic** in plist

3. **Add StartInterval** as backup to StartCalendarInterval

4. **Log everything** - add stdout/stderr paths to plist for debugging

## Immediate Workaround

Run manual sync:
```bash
cd ~/Documents/GitHub/arnold
python scripts/sync_ultrahuman.py
```

Or use MCP:
```
arnold-analytics:run_sync with steps=['ultrahuman']
```

## Related

- Ultrahuman API integration
- `readiness_daily` table
- Morning briefing data completeness
