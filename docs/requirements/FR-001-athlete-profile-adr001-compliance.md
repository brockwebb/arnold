# FR-001: Athlete Profile ADR-001 Compliance

## Metadata
- **Priority**: High
- **Status**: Proposed
- **Created**: 2026-01-09
- **Dependencies**: ADR-001 (Data Layer Separation)

## Description

Migrate athlete profile data from the current flat-file storage (`data/profile.json`) to a proper dual-database architecture compliant with ADR-001:

- **Postgres**: Store facts (demographics, measurements, preferences, sensor configurations)
- **Neo4j**: Store relationships (Person → Goal, Person → Equipment, Person → Sensor)

Currently, profile data is:
1. Stored in a JSON file (not queryable, not auditable)
2. Partially duplicated in Neo4j Person node (demographics in wrong layer)
3. Missing from Postgres entirely

## Rationale

1. **ADR-001 Compliance**: Facts belong in Postgres, relationships in Neo4j
2. **Queryability**: Postgres enables SQL queries on profile attributes
3. **Audit Trail**: Database tables support `created_at`, `updated_at` tracking
4. **Sensor Configuration**: HR session linking (FR-003) requires knowing which sensors the athlete uses and their priority order
5. **Multi-athlete Future**: Current JSON approach doesn't scale to multiple users

## Current State

```
data/profile.json
├── person_id: "73d17934-..."
├── demographics: {name, age, sex, height_inches, birth_date}
├── preferences: {default_units, communication_style, time_zone}
├── check_in: {last_check_in, frequency_days}
├── exercise_aliases: {}
└── neo4j_refs: {current_primary_equipment_inventory}

Neo4j Person Node (DUPLICATED)
├── id, name, age, sex, height_inches (SHOULD NOT BE HERE)
├── athlete_phenotype, athlete_phenotype_notes
├── martial_arts_years, martial_arts_notes
├── training_age_total_years
├── running_preference, cycling_history, triathlon_history
└── profile_updated
```

## Target State

### Postgres Tables

```sql
-- Core athlete profile (facts)
CREATE TABLE athlete_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    birth_date DATE,
    sex TEXT CHECK (sex IN ('male', 'female', 'other')),
    height_inches NUMERIC(4,1),
    weight_lbs NUMERIC(5,1),  -- current weight (observations track history)
    
    -- Preferences
    default_units TEXT DEFAULT 'imperial',
    time_zone TEXT DEFAULT 'America/New_York',
    communication_style TEXT DEFAULT 'direct',
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sensor configuration (which devices, priority order)
CREATE TABLE athlete_sensors (
    id SERIAL PRIMARY KEY,
    athlete_id UUID REFERENCES athlete_profile(id),
    sensor_type TEXT NOT NULL,  -- 'hr_monitor', 'gps_watch', 'ring', etc.
    sensor_brand TEXT NOT NULL, -- 'polar', 'suunto', 'ultrahuman', 'apple'
    sensor_model TEXT,          -- 'H10', 'Race S', 'Ring Air'
    priority_rank INTEGER NOT NULL,  -- 1 = highest priority for this type
    use_for TEXT[],             -- ['exercise_hr', 'resting_hr', 'sleep', 'gps']
    active BOOLEAN DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Athletic background (facts, not relationships)
CREATE TABLE athlete_background (
    id SERIAL PRIMARY KEY,
    athlete_id UUID REFERENCES athlete_profile(id),
    sport_activity TEXT NOT NULL,  -- 'martial_arts', 'ultrarunning', 'triathlon'
    years_experience INTEGER,
    current_status TEXT,  -- 'active', 'maintenance', 'inactive'
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Neo4j Changes

```cypher
// Person node retains ONLY relationship-relevant properties
(:Person {
    id: "uuid",
    athlete_phenotype: "lifelong",  // Affects programming decisions
    athlete_phenotype_notes: "..."
})

// Relationships (these already exist, just formalize)
(:Person)-[:HAS_GOAL]->(:Goal)
(:Person)-[:OWNS_EQUIPMENT]->(:EquipmentInventory)
(:Person)-[:HAS_INJURY]->(:Injury)
(:Person)-[:TRAINS_MODALITY]->(:Modality)

// NEW: Sensor relationships (for future multi-sensor scenarios)
(:Person)-[:USES_SENSOR {priority: 1, use_for: ['exercise_hr']}]->(:Sensor)
```

## Acceptance Criteria

- [ ] `athlete_profile` table created in Postgres with all demographic data
- [ ] `athlete_sensors` table created with sensor priority configuration
- [ ] `athlete_background` table created for athletic history
- [ ] Data migrated from `data/profile.json` to Postgres tables
- [ ] Neo4j Person node stripped of duplicate demographic properties
- [ ] `arnold-profile-mcp` updated to read/write from Postgres (not JSON)
- [ ] Profile CRUD operations work through MCP tools
- [ ] Existing workflows (load_briefing, etc.) continue to function

## Technical Notes

1. **Migration Order**:
   - Create tables first
   - Migrate JSON → Postgres
   - Update MCP to use Postgres
   - Clean Neo4j Person node
   - Archive/delete JSON file

2. **Sensor Priority Logic**:
   ```
   For exercise HR: Polar H10 (1) > Suunto watch (2) > Apple Watch (3)
   For resting HR: Ultrahuman Ring (1) > Apple Watch (2)
   For GPS: Suunto watch (1) > Apple Watch (2)
   ```

3. **MCP Changes**:
   - `get_profile` → query Postgres
   - `update_profile` → update Postgres + trigger Neo4j sync if needed
   - New: `get_sensor_priority(sensor_type)` → returns ranked list

## Open Questions

- [ ] Do we need `athlete_background` as a separate table, or just a JSONB column in `athlete_profile`?
- [ ] Should sensor priority be per-activity-type (different priorities for strength vs running)?
- [ ] How do we handle Suunto data import? (currently only Polar + Ultrahuman + Apple Health)
