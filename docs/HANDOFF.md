# Arnold Project - Thread Handoff

> **Last Updated**: January 4, 2026 (Unified Sync Pipeline + Ultrahuman API)
> **Previous Thread**: Data Quality Pipeline + Ultrahuman Integration
> **Compactions in Previous Thread**: 2

---

## New Thread Start Here

**Context**: You're continuing development of Arnold, an AI-native fitness coaching system. The analytics layer is now fully operational with Postgres backend, automated sync pipeline, and Ultrahuman API integration. Data quality infrastructure (sensor error detection, flag overrides) is in place.

**Quick Start**:
```
1. Read this file (you're doing it)
2. Call arnold-memory:load_briefing (gets athlete context, goals, current block)
3. Run sync pipeline: python scripts/sync_pipeline.py
4. Check red flags: arnold-analytics:check_red_flags
```

**If you need more context**: Read `/docs/ARCHITECTURE.md` and `/docs/issues/003-postgres-analytics-layer.md`

---

## Current System State

### Data Pipeline (Operational)

```bash
# Single command to sync all data sources
python scripts/sync_pipeline.py

# Steps executed:
# 1. polar      - Import new Polar HR exports
# 2. ultrahuman - Fetch from Ultrahuman API (daily)
# 3. apple      - Import Apple Health exports (periodic)
# 4. neo4j      - Sync workouts Neo4j → Postgres
# 5. clean      - Run sensor error detection on biometrics
# 6. refresh    - Refresh Postgres materialized views
```

### Data Sources & Priority

| Source | Method | Data | Frequency | Priority |
|--------|--------|------|-----------|----------|
| **Ultrahuman API** | Automated | Ring biometrics (HRV, RHR, sleep, temp) | Daily | Primary for ring data |
| **Polar Export** | Manual | HR sessions, TRIMP, zones | Weekly | Primary for workout HR |
| **Race History** | One-time | Historical performance | Done | Reference |
| **Apple Health** | Manual | Medical records, labs, BP, meds | Monthly | Secondary/archival |

**Key Decision**: Ultrahuman API wins over Apple Health for ring metrics. Same underlying data, but API is automated and we control the import.

### Database State

**Postgres (`arnold_analytics`)**:
| Table/View | Rows | Purpose |
|------------|------|---------|
| `workout_summaries` | 165 | Denormalized from Neo4j |
| `polar_sessions` | 61 | HR monitor data |
| `hr_samples` | 167K | Second-by-second HR |
| `biometric_readings` | 2,852 | HRV, RHR, sleep, temp, etc. |
| `race_history` | (new) | Historical race results |
| `flag_overrides` | 1 | Acknowledged issues (post-surgery ACWR) |
| `readiness_daily` | view | Aggregated readiness by date |
| `daily_status` | view | Everything combined |
| `trimp_acwr` | view | HR-based training load |

**Neo4j (`arnold`)**:
- 4,242 exercises with movement patterns
- 165 workouts with full block/set structure
- Training plans, observations, coaching context

### MCP Roster (All Operational)

| MCP | Status | Purpose |
|-----|--------|---------|
| arnold-profile-mcp | ✅ | Profile, equipment, activities |
| arnold-training-mcp | ✅ | Planning, logging, execution, exercise search |
| arnold-memory-mcp | ✅ | Context, observations, semantic search |
| arnold-analytics-mcp | ✅ | Readiness, training load, red flags (Postgres backend) |
| neo4j-mcp | ✅ | Direct graph queries |
| postgres-mcp | ✅ | Direct SQL, index tuning, health checks |

---

## Recent Completions

### Unified Sync Pipeline (Jan 4, 2026)

**Problem**: Multiple import scripts, manual execution, error-prone.

**Solution**: Single orchestration script with modular connectors.

**Files**:
- `scripts/sync_pipeline.py` — Orchestrator
- `scripts/sync_ultrahuman.py` — Ultrahuman API connector
- `scripts/import_polar_sessions.py` — Polar export parser
- `scripts/import_apple_health.py` — Apple Health parser
- `scripts/clean_biometrics.py` — Sensor error detection

**Usage**:
```bash
python scripts/sync_pipeline.py              # Full sync
python scripts/sync_pipeline.py --step polar # Single step
python scripts/sync_pipeline.py --skip apple # Skip step
python scripts/sync_pipeline.py --dry-run    # Preview
```

**Cron** (recommended):
```bash
0 6 * * * cd ~/Documents/GitHub/arnold && python scripts/sync_pipeline.py >> logs/sync.log 2>&1
```

### Ultrahuman API Integration (Jan 4, 2026)

**API**: `https://partner.ultrahuman.com/api/v1/metrics`

**Credentials** (in `.env`):
```
ULTRAHUMAN_AUTH_TOKEN=eyJhbGciOiJIUzI1NiJ9...
ULTRAHUMAN_USER_EMAIL=brockwebb45@gmail.com
```

**Data extracted**: HRV, resting HR, sleep stages, temperature, recovery score, VO2 max, steps, movement index.

**Manual fetch**:
```bash
python scripts/sync_ultrahuman.py --days 7 --dry-run
python scripts/sync_ultrahuman.py --test  # API connection test
```

### Data Quality Infrastructure (Jan 4, 2026)

**Sensor Error Detection** (`clean_biometrics.py`):
- Uses physiological bounds, NOT statistical outliers
- Only flags values outside human possibility (sensor errors)
- Preserves natural variance (HRV 50-167 is normal for endurance athlete)

| Metric | Bounds | Rationale |
|--------|--------|-----------|
| HRV | 15-250 ms | Below 15 = sensor failure |
| Resting HR | 35-100 bpm | Below 35 = bad contact |
| Temperature | 28-40°C | Outside = ambient/sensor |

**Schema additions**:
```sql
-- biometric_readings columns
is_outlier BOOLEAN DEFAULT FALSE
cleaned_value NUMERIC           -- Imputed value (original preserved in `value`)
imputation_method VARCHAR(50)
imputation_note TEXT
```

**Current sensor errors**: 7 flagged (out of 2,852 readings)

**Flag Overrides** (`flag_overrides` table):
```sql
-- Suppress expected warnings
INSERT INTO flag_overrides (flag_type, context, reason, expires_at)
VALUES ('acwr', 'post_surgery_ramp', 'Expected high ACWR during post-surgery rebuild', '2026-03-01');
```

### Source Deduplication (Jan 4, 2026)

**Problem**: Same data coming through two paths (Ultrahuman API + Apple Health import via Ultrahuman sync). Case mismatch: `'ultrahuman'` vs `'Ultrahuman'`.

**Solution**: Normalized all to lowercase, deleted duplicates, Ultrahuman API is canonical source for ring data.

**Result**: Single clean source (`ultrahuman`) with 2,852 readings.

### Analytics MCP Migration (Jan 4, 2026)

**Completed**: All 5 tools now query Postgres instead of DuckDB.

| Tool | Status |
|------|--------|
| `get_readiness_snapshot` | ✅ Postgres |
| `get_training_load` | ✅ Postgres |
| `get_exercise_history` | ✅ Postgres |
| `check_red_flags` | ✅ Postgres (respects flag_overrides) |
| `get_sleep_analysis` | ✅ Postgres |

---

## Data Lake Structure

```
data/
├── raw/                          # Device exports (git-ignored)
│   ├── polar/                    # YYYYMMDD--export/
│   ├── ultrahuman/               # manual_export_*.csv
│   └── apple_health/             # YYYYMMDD--export.xml
├── staging/                      # Parsed/cleaned, pre-Postgres
├── exports/                      # Generated reports
└── cache/                        # Temporary processing
```

**Naming convention**: `YYYYMMDD--source-description`

---

## Athlete Context (Brock)

- **Age**: 50 (turned 50 January 2, 2026)
- **Background**: 35 years martial arts, 18 years ultrarunning, desk job
- **Recent**: Knee surgery November 2025, cleared for normal activity
- **Goals**: Deadlift 405x5, Hellgate 100k, 10 pain-free ring dips by June 2026
- **Race history**: 40+ ultras including 100-milers (Old Dominion, Massanutten, Grindstone)
- **Training philosophy**: Evidence-based, prefers substance over engagement

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                │
├─────────────────────────────────────────────────────────────────┤
│ Ultrahuman API │ Polar Export │ Apple Health │ Race History    │
│    (daily)     │   (weekly)   │  (monthly)   │   (one-time)    │
└───────┬────────┴──────┬───────┴──────┬───────┴────────┬────────┘
        │               │              │                │
        └───────────────┴──────────────┴────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   sync_pipeline.py    │
                    │   (orchestrator)      │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Neo4j       │    │    Postgres      │    │ Materialized    │
│ (structure)   │    │  (time-series)   │    │    Views        │
├───────────────┤    ├──────────────────┤    ├─────────────────┤
│ • Exercises   │    │ • biometrics     │    │ • readiness     │
│ • Workouts    │    │ • HR samples     │    │ • training_load │
│ • Plans       │    │ • Polar sessions │    │ • daily_status  │
│ • Observations│    │ • workout_summaries│   │ • trimp_acwr    │
└───────────────┘    └──────────────────┘    └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    MCP Servers        │
                    │ (domain logic layer)  │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Claude Desktop      │
                    │   (orchestrator)      │
                    └───────────────────────┘
```

---

## Reference: Core Documents

```
/docs/
├── ARCHITECTURE.md              # System architecture (master reference)
├── HANDOFF.md                   # This file (thread continuity)
├── DATA_DICTIONARY.md           # Data lake reference
├── TRAINING_METRICS.md          # Evidence-based metrics
├── PLANNING.md                  # Planning system design
├── schema.md                    # Neo4j schema reference
├── mcps/                        # MCP documentation
│   ├── README.md               # MCP boundaries and patterns
│   ├── arnold-training.md      
│   ├── arnold-profile.md       
│   ├── arnold-analytics.md     
│   └── arnold-memory.md        
└── issues/                      # Architecture decisions
    ├── 001-planning-tool-integrity.md   → RESOLVED
    ├── 002-exercise-lookup-efficiency.md → RESOLVED  
    └── 003-postgres-analytics-layer.md  → Phase 4 (pipeline operational)
```

---

## Common Commands

### Daily Operations
```bash
# Full sync (run daily or after new data)
python scripts/sync_pipeline.py

# Test Ultrahuman API
python scripts/sync_ultrahuman.py --test

# Check database health
psql arnold_analytics -c "SELECT * FROM daily_status ORDER BY date DESC LIMIT 5;"
```

### Data Import
```bash
# Import new Polar export
python scripts/import_polar_sessions.py data/raw/polar/YYYYMMDD--export/

# Import Ultrahuman CSV (manual export)
python scripts/import_ultrahuman_csv.py data/raw/ultrahuman/*.csv

# Import race history
python scripts/import_race_history.py data/raw/old_race_info/brock_webb_race_history.csv

# Refresh materialized views
psql arnold_analytics -c "REFRESH MATERIALIZED VIEW readiness_daily; REFRESH MATERIALIZED VIEW training_load_daily;"
```

### Debugging
```bash
# Check biometric readings
psql arnold_analytics -c "SELECT metric_type, COUNT(*), MIN(reading_date), MAX(reading_date) FROM biometric_readings GROUP BY metric_type;"

# Check sensor errors
psql arnold_analytics -c "SELECT * FROM biometric_readings WHERE is_outlier = TRUE;"

# Check flag overrides
psql arnold_analytics -c "SELECT * FROM flag_overrides WHERE expires_at IS NULL OR expires_at > CURRENT_DATE;"
```

---

## Critical Notes for Future Claude

1. **Sync pipeline is the single entry point** - Don't run individual import scripts unless debugging. Use `python scripts/sync_pipeline.py`.

2. **Ultrahuman API > Apple Health for ring data** - Same underlying source, but API is automated and we control import. Apple Health is for medical/other data.

3. **Sensor error detection uses physiological bounds** - NOT statistical outliers. High variance in HRV/steps is normal. Only flag impossible values.

4. **Flag overrides suppress expected warnings** - Post-surgery high ACWR is expected through March 2026. Check `flag_overrides` table before adding new warnings.

5. **Race history available** - 40+ ultras in `race_history` table. Useful context for goal-setting and performance discussions.

6. **Materialized views need refresh** - After biometric imports, run `REFRESH MATERIALIZED VIEW readiness_daily`. Pipeline does this automatically.

7. **Source normalization** - All biometric sources are lowercase (`ultrahuman`, `polar`, `apple_health`). Don't introduce case variants.

8. **Post-surgery context** - Knee surgery November 2025, cleared for normal activity. High ACWR during ramp-up is expected, not a red flag.

---

## Next Steps (Optional)

### Short-term
- [ ] Set up cron for daily sync pipeline
- [ ] Import race history to Postgres
- [ ] Add more flag override types as needed

### Medium-term
- [ ] Apple Health importer: skip Ultrahuman metrics, focus on medical/other
- [ ] Incremental Ultrahuman sync (track last sync date, fetch only new)
- [ ] Suunto bulk dump import when available

### Long-term
- [ ] HRV algorithm investigation (why Ultrahuman ≠ Apple Health values?)
- [ ] Bayesian evidence framework for individualized pattern detection
- [ ] Integration with additional data sources (CGM, etc.)

---

## FAQ

**Q: Why both Neo4j and Postgres?**
A: Neo4j excels at relationships (exercise→muscle graphs, coaching). Postgres excels at time-series (ACWR, trends, aggregations).

**Q: Why Ultrahuman API instead of Apple Health?**
A: Same data (ring syncs to Health), but API is automated daily. Apple Health requires manual XML export.

**Q: What if ACWR is high?**
A: Check `flag_overrides` first. Post-surgery ramp-up means high ACWR is expected through March 2026.

**Q: How to add a new data source?**
A: Create connector in `scripts/`, add step to `sync_pipeline.py`, update this doc.

**Q: What if sensor error detection is wrong?**
A: Adjust bounds in `clean_biometrics.py`. Current bounds are conservative.
