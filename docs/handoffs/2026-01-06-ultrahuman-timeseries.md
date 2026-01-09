# Handoff: Ultrahuman Time-Series Sync

**Date**: January 6, 2026  
**Status**: Partially complete - needs rate limiting & testing

---

## What Was Done

### 1. Fixed Sleep Data Parsing (COMPLETE)
The Ultrahuman API returns nested structures we weren't parsing correctly:
```python
# WRONG - what we had
obj.get("total_sleep_minutes")

# RIGHT - actual structure  
obj.get("total_sleep", {}).get("minutes")
```

Fixed parsing for: `total_sleep`, `deep_sleep`, `rem_sleep`, `light_sleep`, `sleep_score`, `sleep_efficiency`, `spo2`

### 2. Added SpO2 Daily Average (COMPLETE)
Now captures `Sleep.spo2.value` — critical health metric (should stay ≥97%)

### 3. Created biometric_samples Table (COMPLETE)
```sql
CREATE TABLE biometric_samples (
    id BIGSERIAL PRIMARY KEY,
    sample_time TIMESTAMPTZ NOT NULL,
    metric_type VARCHAR(50) NOT NULL,  -- hr, hrv, skin_temp, night_rhr, sleep_stage
    value NUMERIC,
    text_value VARCHAR(100),           -- for sleep_stage labels
    source VARCHAR(50) DEFAULT 'ultrahuman',
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_bio_samples_time ON biometric_samples(sample_time);
CREATE INDEX idx_bio_samples_type_time ON biometric_samples(metric_type, sample_time);
CREATE UNIQUE INDEX idx_bio_samples_unique ON biometric_samples(sample_time, metric_type, source);
```

### 4. Updated sync_ultrahuman.py (COMPLETE but needs rate limiting)
- `extract_samples()` — pulls time-series from hr, hrv, temp, night_rhr
- `upsert_samples()` — bulk inserts with deduplication
- Main loop now processes both daily aggregates AND time-series

**Metrics captured per day:**
- ~15 daily aggregates → `biometric_readings`
- ~100-300 time-series samples → `biometric_samples`

---

## What Needs Work

### 1. API Rate Limiting (HIGH PRIORITY)
Ultrahuman API is timing out when hitting it too fast. Need to add:
```python
import time
# Between API calls
time.sleep(0.5)  # or whatever they allow
```

Also consider:
- Retry logic with exponential backoff
- Catching timeout exceptions gracefully
- Maybe batch by week instead of day-by-day

### 2. Test Full Sync
Once rate limiting is in place:
```bash
python3 scripts/sync_ultrahuman.py --days 31
```

Verify:
- Daily readings in `biometric_readings` (including new sleep metrics + spo2)
- Time-series in `biometric_samples`

### 3. Backfill Historical Data
May want to sync back further than 31 days to capture historical patterns.

### 4. Sleep Stage Granularity (OPTIONAL)
Current implementation captures sleep cycle boundaries from `sleep_cycles.cycles[]`. 
The 5-minute granular sleep stage data is embedded in PowerPlug environmental readings 
(each PM2.5/noise reading has a `sleep_stage` annotation). Could extract that for 
richer sleep architecture analysis.

---

## Files Modified

| File | Change |
|------|--------|
| `scripts/sync_ultrahuman.py` | Fixed sleep parsing, added SpO2, added time-series extraction |
| `biometric_samples` table | New table for time-series data |

---

## Testing Commands

```bash
# Test with rate limiting (after adding sleep)
python3 scripts/sync_ultrahuman.py --days 7

# Verify daily readings
psql arnold_analytics -c "SELECT reading_date, metric_type, value FROM biometric_readings WHERE metric_type = 'spo2' ORDER BY reading_date DESC LIMIT 5"

# Verify time-series
psql arnold_analytics -c "SELECT COUNT(*), metric_type FROM biometric_samples GROUP BY metric_type"

# Check sample density
psql arnold_analytics -c "SELECT DATE(sample_time), metric_type, COUNT(*) FROM biometric_samples GROUP BY 1, 2 ORDER BY 1 DESC, 2 LIMIT 20"
```

---

## Earlier Session Work (Same Day)

Also completed earlier:
- Annotation tools in arnold-journal-mcp (tested & working)
- Analytics "compute vs interpret" pattern documented
- Coaching_notes restored to analytics tools
- launchd automation documented

See: `docs/handoffs/2026-01-06-analytics-compute-vs-interpret.md`
