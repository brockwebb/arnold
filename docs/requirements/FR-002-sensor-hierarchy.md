# FR-002: Sensor Hierarchy & Preferences

## Metadata
- **Priority**: High
- **Status**: Proposed
- **Created**: 2026-01-09
- **Dependencies**: FR-001 (Athlete Profile), ADR-001

## Description

Define and implement a configurable sensor hierarchy that determines which data source to use when multiple sensors provide overlapping data types. The system must know:

1. Which sensors the athlete owns/uses
2. For each data type, which sensor is authoritative
3. How to resolve conflicts when multiple sources exist

## Rationale

Arnold ingests data from multiple sources with overlapping capabilities:

| Data Type | Polar H10 | Suunto Watch | Apple Health | Ultrahuman Ring |
|-----------|-----------|--------------|--------------|-----------------|
| Exercise HR | ⭐ Gold | ✓ Good | ✓ Variable | ✗ Poor |
| Resting HR | ✗ N/A | ✓ OK | ✓ OK | ⭐ Gold |
| HRV | ✗ N/A | ? | ✓ Different algo | ⭐ Gold |
| Sleep | ✗ N/A | ✗ N/A | ✓ OK | ⭐ Gold |
| GPS/Distance | ✗ N/A | ⭐ Gold | ✓ OK | ✗ N/A |
| Steps | ✗ N/A | ✓ OK | ✓ OK | ✓ OK |

**Current Problem**: No formal hierarchy. Code makes ad-hoc decisions. Ultrahuman HRV is the standard, but Apple Health HRV uses a different algorithm — mixing them corrupts trend analysis.

## Sensor Priority Matrix (Default)

| Data Type | Priority 1 | Priority 2 | Priority 3 | Never Use |
|-----------|------------|------------|------------|-----------|
| **Exercise HR** | Polar H10 | Suunto | Apple Watch | Ultrahuman |
| **Resting HR** | Ultrahuman | Apple Watch | Polar (if session) | — |
| **HRV** | Ultrahuman | — | — | Apple (different algo) |
| **Sleep** | Ultrahuman | Apple Watch | — | — |
| **GPS/Route** | Suunto | Apple Watch | — | — |
| **Steps** | Apple Health | Ultrahuman | Suunto | — |
| **Gait/Balance** | Apple Health | — | — | — |

## Data Model (from FR-001)

```sql
CREATE TABLE athlete_sensors (
    id SERIAL PRIMARY KEY,
    athlete_id UUID REFERENCES athlete_profile(id),
    sensor_type TEXT NOT NULL,      -- 'hr_chest', 'hr_wrist', 'ring', 'watch'
    sensor_brand TEXT NOT NULL,     -- 'polar', 'suunto', 'ultrahuman', 'apple'
    sensor_model TEXT,              -- 'H10', 'Race S', 'Ring Air'
    data_capabilities TEXT[],       -- ['exercise_hr', 'resting_hr', 'hrv', 'sleep', 'gps']
    priority_overrides JSONB,       -- {exercise_hr: 1, sleep: 2} - athlete-specific
    active BOOLEAN DEFAULT true,
    acquired_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- System-wide defaults (not per-athlete)
CREATE TABLE sensor_data_priorities (
    id SERIAL PRIMARY KEY,
    data_type TEXT NOT NULL,        -- 'exercise_hr', 'resting_hr', 'hrv', 'sleep', 'gps', 'steps'
    sensor_brand TEXT NOT NULL,
    default_priority INTEGER NOT NULL,
    reliability_notes TEXT,
    exclude_reason TEXT             -- If set, never use this sensor for this data type
);
```

## API / MCP Interface

```typescript
// Get the best sensor for a data type
get_sensor_for_data_type(data_type: 'exercise_hr' | 'resting_hr' | 'hrv' | 'sleep' | 'gps')
  → { brand: 'polar', model: 'H10', priority: 1 }

// Check if a specific source should be used
should_use_source(source: 'ultrahuman', data_type: 'hrv')
  → { use: true, priority: 1, notes: 'Primary HRV source' }

should_use_source(source: 'apple_health', data_type: 'hrv')
  → { use: false, reason: 'Different algorithm - incompatible with Ultrahuman baseline' }

// Get all valid sources for a data type, ranked
get_ranked_sources(data_type: 'exercise_hr')
  → [
      { brand: 'polar', priority: 1 },
      { brand: 'suunto', priority: 2 },
      { brand: 'apple', priority: 3 }
    ]
```

## Acceptance Criteria

- [ ] `athlete_sensors` table populated with Brock's current sensors
- [ ] `sensor_data_priorities` table populated with default hierarchy
- [ ] MCP function `get_sensor_for_data_type()` implemented
- [ ] Sync pipeline respects sensor hierarchy (doesn't import excluded data)
- [ ] Analytics queries use hierarchy when multiple sources exist for same timestamp
- [ ] Apple Health HRV explicitly excluded from HRV analytics (different algorithm)
- [ ] Documentation of why each priority was set (evidence-based)

## Technical Notes

### Brock's Current Sensors

| Sensor | Brand | Model | Use For |
|--------|-------|-------|---------|
| Chest strap | Polar | H10 | Exercise HR |
| Smart ring | Ultrahuman | Ring Air | Resting HR, HRV, Sleep |
| Watch | Apple | Watch (older) | Steps, fallback |
| Phone | Apple | iPhone | Apple Health aggregation |

**Note**: Suunto watch mentioned but not currently integrated. GPS from Suunto would be valuable for trail runs.

### Sync Pipeline Changes

Current: Imports all data from all sources
Target: Check sensor hierarchy before import

```python
def should_import(source: str, data_type: str) -> bool:
    hierarchy = get_sensor_hierarchy(data_type)
    if source in hierarchy.excluded:
        return False
    # Only import if this is the highest-priority available source
    return True
```

### Conflict Resolution

When multiple sources provide data for the same timestamp:

1. **Same data type**: Use highest priority source, ignore others
2. **Different data types**: Keep both (e.g., Polar HR + Ultrahuman sleep)
3. **Logging**: Record when conflicts occur for audit

## Open Questions

- [x] Should we store rejected data with a flag, or not import at all?
  **Answer**: Import everything to raw/data lake. ETL into tables with `source` column. Hierarchy determines what analytics USE, not what gets imported.
- [x] How to handle Apple Health HRV that's already in the system?
  **Answer**: 97 readings exist (May-Dec 2025). Analytics must filter to `source = 'ultrahuman'` for HRV. Apple HRV uses different algorithm (SDNN vs RMSSD) — not comparable.
- [x] Is Suunto integration on the roadmap? What data would it provide?
  **Answer**: Already integrated. FIT files import to `endurance_sessions` + `endurance_laps`. Provides: distance, pace, TSS, per-lap HR, elevation. GPS track data available but not extracted. HR from Polar H10 paired to Suunto watch.
- [x] Should steps be a training load input, or just lifestyle context?
  **Answer**: Lifestyle context. Includes running steps + daily walking (Murray walks). Good trend indicator for overall activity level. Not a training load metric.
- [x] What's the step data hierarchy?
  **Answer**: Apple Health primary (phone carried more consistently than ring). Ultrahuman is backup. Apple also provides gait analysis and balance metrics from phone motion sensors — relevant to left/right asymmetry tracking.
