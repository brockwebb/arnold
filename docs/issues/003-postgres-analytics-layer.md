# Issue 003: Analytics Layer — DuckDB → Postgres

> **Status**: Phase 2 Complete (Polar HR + Apple Health loaded)
> **Priority**: High
> **Created**: January 3, 2026
> **Related**: ARCHITECTURE.md (Analytics Architecture section)

---

## Problem Statement

Current design (from ARCHITECTURE.md):
```
Raw (native) → Staging (Parquet) → DuckDB (analytics)
```

**The gap:** DuckDB is file-based. Every change requires full rebuild. Can't do incremental updates. Can't pre-compute views that stay fresh.

---

## What Already Exists (Don't Rebuild)

The architecture doc already defines:

1. **Data Lake Philosophy**
   - Raw stays raw
   - Staging is dumb (Parquet)
   - Intelligence is external (catalog)
   - Transform at runtime OR pre-build

2. **Directory Structure**
   ```
   /data/raw/           # Native format (XML, JSON, FIT)
   /data/staging/       # Parquet files
   /data/catalog.json   # Data registry
   ```

3. **Data Sources**
   - Apple Health (292K records)
   - Ultrahuman biometrics
   - Neo4j workout exports
   - Lab results, FHIR records

This stays. The change is what happens AFTER staging.

---

## The Fix: Postgres as Analytical Frames Layer

Like Census builds different products for different questions, we build **frames**:

| Frame | Grain | Purpose | Refresh |
|-------|-------|---------|---------|
| `readiness_daily` | date | Morning check-in | Daily |
| `training_load_weekly` | year-week | ACWR, monotony, strain | After workout |
| `progression_by_modality` | modality × date | Goal tracking | Weekly |
| `pattern_balance_28d` | pattern × rolling | Gap detection | Weekly |
| `biometric_series` | date × metric | Long-term trends | On import |
| `workout_summaries` | workout_id | Quick reference | After workout |

**Frames are materialized views or summary tables.** Arnold queries frames, not raw data.

---

## Architecture Change

**Before:**
```
Raw → Staging (Parquet) → DuckDB (file, full rebuild)
```

**After:**
```
Raw → Staging (Parquet) → Postgres (server, incremental)
                              ↓
                         Frames (materialized views)
                              ↓
                         Arnold queries frames
```

Neo4j remains source of truth for:
- Person, goals, blocks, plans
- Exercise graph (relationships)
- Workout structure (blocks, sets)
- Coaching observations

Postgres holds:
- Time-series biometrics (bulk data)
- Denormalized workout summaries
- Pre-computed training metrics
- Analytical frames

---

## Data Flow

### On Workout Complete
```
1. Neo4j gets the workout (plan → execution)
2. Sync script extracts summary → Postgres workout_summaries
3. Postgres triggers refresh of training_load_weekly frame
4. Arnold's next readiness query hits fresh data
```

### On Biometric Import
```
1. Apple Health XML → Parquet (staging)
2. Parquet → Postgres biometric_series (incremental UPSERT)
3. Postgres triggers refresh of readiness_daily frame
```

### Arnold Queries
```python
# Instead of: rebuild DuckDB, then query
# Now: query Postgres frame directly

get_readiness_snapshot(date) → SELECT * FROM readiness_daily WHERE date = ?
get_training_load(days) → SELECT * FROM training_load_weekly WHERE week >= ?
```

---

## Postgres Schema (Draft)

```sql
-- ============================================
-- RAW TIME-SERIES (bulk biometric data)
-- ============================================

CREATE TABLE biometric_readings (
    id SERIAL PRIMARY KEY,
    reading_date DATE NOT NULL,
    metric_type VARCHAR(50) NOT NULL,  -- 'hrv', 'rhr', 'sleep_hours', 'sleep_score'
    value DECIMAL(10,2) NOT NULL,
    source VARCHAR(50),  -- 'apple_health', 'ultrahuman', 'manual'
    imported_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(reading_date, metric_type, source)
);

CREATE INDEX idx_biometric_date ON biometric_readings(reading_date);
CREATE INDEX idx_biometric_type_date ON biometric_readings(metric_type, reading_date);

-- ============================================
-- WORKOUT SUMMARIES (denormalized from Neo4j)
-- ============================================

CREATE TABLE workout_summaries (
    neo4j_id VARCHAR(50) PRIMARY KEY,
    workout_date DATE NOT NULL,
    workout_type VARCHAR(50),
    duration_minutes INT,
    set_count INT,
    total_volume_lbs DECIMAL(12,2),
    patterns JSONB,  -- ["Hip Hinge", "Vertical Pull"]
    exercises JSONB, -- [{name, sets, reps, load}]
    tss DECIMAL(6,2),
    source VARCHAR(20),  -- 'planned', 'adhoc', 'imported'
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_workout_date ON workout_summaries(workout_date);

-- ============================================
-- FRAMES (materialized views)
-- ============================================

-- Frame: Daily readiness (morning check-in)
CREATE MATERIALIZED VIEW readiness_daily AS
SELECT 
    reading_date,
    MAX(CASE WHEN metric_type = 'hrv' THEN value END) as hrv_ms,
    MAX(CASE WHEN metric_type = 'rhr' THEN value END) as rhr_bpm,
    MAX(CASE WHEN metric_type = 'sleep_hours' THEN value END) as sleep_hours,
    MAX(CASE WHEN metric_type = 'sleep_score' THEN value END) as sleep_score,
    MAX(CASE WHEN metric_type = 'recovery_score' THEN value END) as recovery_score
FROM biometric_readings
GROUP BY reading_date;

CREATE UNIQUE INDEX idx_readiness_date ON readiness_daily(reading_date);

-- Frame: Weekly training load
CREATE MATERIALIZED VIEW training_load_weekly AS
WITH daily_load AS (
    SELECT 
        workout_date,
        SUM(total_volume_lbs) as daily_volume,
        SUM(set_count) as daily_sets
    FROM workout_summaries
    GROUP BY workout_date
),
rolling AS (
    SELECT 
        workout_date,
        daily_volume,
        daily_sets,
        AVG(daily_volume) OVER (ORDER BY workout_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as acute_7d,
        AVG(daily_volume) OVER (ORDER BY workout_date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) as chronic_28d
    FROM daily_load
)
SELECT 
    workout_date,
    daily_volume,
    daily_sets,
    acute_7d,
    chronic_28d,
    CASE WHEN chronic_28d > 0 THEN acute_7d / chronic_28d ELSE NULL END as acwr
FROM rolling;

CREATE UNIQUE INDEX idx_training_load_date ON training_load_weekly(workout_date);

-- Refresh functions
CREATE OR REPLACE FUNCTION refresh_readiness()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY readiness_daily;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refresh_training_load()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY training_load_weekly;
END;
$$ LANGUAGE plpgsql;
```

---

## Implementation Status

### Phase 1: Postgres Setup ✅ COMPLETE (Jan 3, 2026)

**What was built:**
- Database `arnold_analytics` created
- `workout_summaries` table (165 workouts synced)
- `biometric_readings` table (schema ready, no data yet)
- `training_load_daily` materialized view (ACWR, volume tracking)
- `readiness_daily` materialized view (ready for biometrics)
- `postgres-mcp` installed and connected
- Sync script: `scripts/sync_neo4j_to_postgres.py`

**Verified working:**
```sql
SELECT * FROM training_load_daily ORDER BY workout_date DESC LIMIT 5;
-- Returns ACWR, acute_7d, chronic_28d, daily_volume
```

**Python env upgraded:** arnold conda env → Python 3.12 (was 3.10)

---

### Phase 2: Polar HR Data Load ✅ COMPLETE (Jan 4, 2026)

**What was built:**

| Table/View | Rows | Purpose |
|------------|------|--------|
| `polar_sessions` | 61 | Raw session data (May 2025 - Jan 2026) |
| `hr_samples` | 167,670 | Second-by-second HR |
| `polar_session_metrics` | (view) | TRIMP, Edwards TRIMP, Intensity Factor |
| `hr_training_load_daily` | (view) | Daily aggregates, zone distribution |
| `trimp_acwr` | (view) | HR-based ACWR |
| `combined_training_load` | (view) | Unified volume + HR metrics |

**Data coverage:**
- Complete (volume + HR): 51 days
- Volume only: 114 days
- HR only: 7 days

**Key metrics:**
- Banister TRIMP (HR reserve-based)
- Edwards TRIMP (zone-weighted)
- Intensity Factor
- Polarization (% low/high intensity)
- TRIMP-based ACWR

**Files created:**
- `scripts/migrations/002_polar_sessions.sql`
- `scripts/import_polar_sessions.py`

**Linkage established:**
- `workout_summaries.polar_session_id` → FK to `polar_sessions`
- Match by date + duration similarity
- 51 workouts linked (confidence 0.6-1.0)
- 10 orphaned Polar sessions (runs/walks not logged in Arnold)

### Apple Health Import (Jan 4, 2026)

**Imported to `biometric_readings`:**

| Metric | Records | Range |
|--------|---------|-------|
| HRV (morning avg) | 97 | May-Dec 2025 |
| Resting HR | 158 | May-Dec 2025 |
| Sleep total | 188 | May-Dec 2025 |
| Sleep deep | 181 | May-Dec 2025 |
| Sleep REM | 176 | May-Dec 2025 |

**Views created:**
- `readiness_daily` — Materialized view aggregating biometrics by date
- `daily_status` — Comprehensive view joining training + HR + readiness

**Data coverage:**

| Type | Days |
|------|------|
| Full (training + HR + readiness) | 50 |
| Readiness only | 119 |
| Training only | 95 |
| Training + readiness | 19 |
| Training + HR | 1 |

**Files created:**
- `scripts/import_apple_health.py`

---

## Remaining Implementation

### Phase 3: MCP Integration
- [ ] Update arnold-analytics-mcp to query Postgres instead of DuckDB
- [ ] Validate existing tools work with new backend
- [ ] Remove DuckDB dependency

### Phase 4: Incremental Sync
- [ ] Post-workout hook in training-mcp → sync to Postgres
- [ ] Biometric import scripts → upsert to Postgres
- [ ] Scheduled frame refresh (cron or trigger-based)

### Ongoing Maintenance
- Re-export Polar data periodically (manual process)
- Re-export Apple Health to refresh biometrics (manual process)
- Run `REFRESH MATERIALIZED VIEW readiness_daily` after biometric imports

---

## Migration from DuckDB

1. Keep DuckDB files for reference (don't delete)
2. Build Postgres in parallel
3. Validate outputs match
4. Switch arnold-analytics-mcp
5. Stop running DuckDB rebuild scripts

---

## Questions Resolved

1. **Sync direction?** → Neo4j → Postgres (one-way). Writes hit Neo4j, sync copies to Postgres.

2. **What goes to Postgres?** → Time-series biometrics, workout summaries, computed frames. Exercise graph, plan structure, observations stay Neo4j.

3. **MySQL vs Postgres?** → Postgres. Better window functions, JSONB, materialized views. Already installed.

4. **"Denormalized"?** → Pre-joined, pre-aggregated tables optimized for reads. Like Census subject tables vs microdata.

---

## Success Criteria

1. **Fresh data**: Workout completed → queryable in < 5 minutes
2. **Fast queries**: Readiness check < 100ms
3. **No rebuilds**: Incremental updates, not full exports
4. **Frame coverage**: All standard coaching queries have a pre-built frame

