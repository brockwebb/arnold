# Handoff: HR Data Pipeline + Recovery Detection

> **Date**: January 10, 2026  
> **Topic**: Issue #23 (FIT HR Extraction) + FR-004 prep  
> **Status**: Ready for implementation

---

## Context

User wants 60-second HR recovery metric. Investigation revealed:

1. **FIT files DO contain per-second HR data** (2,000+ samples per session)
2. **Current importer discards this data** — only extracts session/lap summaries
3. **FR-004 (Recovery Interval Detection)** is already documented but blocked by missing data

---

## Current State

### Data Inventory

| Table | Rows | Date Range | Notes |
|-------|------|------------|-------|
| `polar_sessions` | 65 | May 2025 - Jan 2026 | Session summaries |
| `hr_samples` | 175,756 | May 2025 - Jan 2026 | **Polar only** — FK to polar_sessions |
| `endurance_sessions` | 2 | Jan 2026 | Suunto FIT imports |
| `strength_sessions` | 168 | Apr 2024 - Jan 2026 | Manual/planned |

### Gap

Suunto FIT files have HR samples, but they're not extracted:

```
# FIT file contains:
record (2376 records):
  - heart_rate: 90
  - cadence: 36
  - timestamp: 2026-01-07 20:40:44
  - altitude: 32.0
  - speed: 1.01
```

Current `import_fit_workouts.py` only reads `session` and `lap` messages, not `record` messages.

---

## Implementation Plan

### Step 1: Schema — Multi-source HR samples

Current `hr_samples` has FK only to `polar_sessions`. Generalize it:

```sql
-- Migration: 0XX_multi_source_hr_samples.sql

-- Add source tracking
ALTER TABLE hr_samples ADD COLUMN source VARCHAR(20) DEFAULT 'polar_api';

-- Add FK to endurance_sessions (for FIT data)
ALTER TABLE hr_samples ADD COLUMN endurance_session_id INTEGER REFERENCES endurance_sessions(id);

-- Make polar FK nullable (was required before)
ALTER TABLE hr_samples ALTER COLUMN session_id DROP NOT NULL;

-- Add constraint: must have at least one FK
ALTER TABLE hr_samples ADD CONSTRAINT hr_samples_session_check 
    CHECK (session_id IS NOT NULL OR endurance_session_id IS NOT NULL);

-- Backfill source for existing polar data
UPDATE hr_samples SET source = 'polar_api' WHERE source IS NULL;

-- Index for FIT lookups
CREATE INDEX idx_hr_samples_endurance ON hr_samples(endurance_session_id) WHERE endurance_session_id IS NOT NULL;
```

### Step 2: Update FIT Importer

Add to `scripts/import_fit_workouts.py`:

```python
def extract_hr_samples(filepath: Path) -> list:
    """Extract per-second HR samples from FIT file 'record' messages."""
    fit = fitparse.FitFile(str(filepath))
    samples = []
    
    for record in fit.get_messages('record'):
        sample = {'hr_value': None, 'sample_time': None, 'cadence': None, 'speed': None, 'altitude': None}
        
        for field in record:
            if field.name == 'heart_rate' and field.value:
                sample['hr_value'] = int(field.value)
            elif field.name == 'timestamp':
                sample['sample_time'] = field.value
            elif field.name == 'cadence':
                sample['cadence'] = field.value
            elif field.name == 'enhanced_speed' or field.name == 'speed':
                sample['speed'] = field.value
            elif field.name == 'enhanced_altitude' or field.name == 'altitude':
                sample['altitude'] = field.value
        
        if sample['hr_value'] and sample['sample_time']:
            samples.append(sample)
    
    return samples


def insert_hr_samples(conn, endurance_session_id: int, samples: list, source: str):
    """Batch insert HR samples."""
    if not samples:
        return 0
    
    query = """
    INSERT INTO hr_samples (endurance_session_id, sample_time, hr_value, source)
    VALUES %s
    """
    values = [(endurance_session_id, s['sample_time'], s['hr_value'], source) for s in samples]
    
    with conn.cursor() as cur:
        execute_values(cur, query, values, page_size=1000)
    conn.commit()
    
    return len(samples)
```

Integrate into `main()` flow after session insert.

### Step 3: Update Polar Importer

Add source to inserts in `scripts/sync/polar_api.py`:

```python
# In insert code, add source='polar_api' to INSERT statement
sample_data = [
    (session_id, s["sample_time"], s["hr_value"], 'polar_api')  # Added source
    for s in samples
]
```

### Step 4: Backfill Existing Sessions

```bash
# Re-run importer with --force on existing files
python scripts/import_fit_workouts.py --force
```

Or create a dedicated backfill script.

---

## After #23: FR-004 Implementation

Once HR samples are available for all sessions, FR-004 can proceed:

1. **Find HR peaks** in continuous stream
2. **Detect recovery intervals** (60+ seconds of declining HR)
3. **Calculate HRR metrics** (1-min, 2-min drop)
4. **Store in** `hr_recovery_intervals` table
5. **Aggregate to** session-level summary

See: `docs/requirements/FR-004-recovery-interval-detection.md` — full algorithm spec.

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/import_fit_workouts.py` | FIT importer — needs HR extraction |
| `scripts/sync/polar_api.py` | Polar API sync — add source column |
| `docs/requirements/FR-004-recovery-interval-detection.md` | Full recovery spec |
| `config/sources.yaml` | Source priorities (informational) |

---

## Provenance Model

After changes, `hr_samples` will track:

| Column | Purpose |
|--------|---------|
| `session_id` | FK to `polar_sessions` (nullable) |
| `endurance_session_id` | FK to `endurance_sessions` (nullable) |
| `source` | 'polar_api', 'suunto_fit', 'garmin_fit', etc. |
| `sample_time` | Timestamp of reading |
| `hr_value` | Heart rate in bpm |

Sport type comes from the linked session (`polar_sessions.sport_type` or `endurance_sessions.sport`).

---

## Notes from Discussion

1. **Multiple sources OK** — keep provenance, normalize to common schema
2. **Suunto uses Polar H10** — same sensor, data quality equivalent
3. **Auto-pause** may create gaps — handle gracefully, don't break on gaps
4. **Manual export** for Suunto — user exports FIT files from Suunto app
5. **FR-003 (session linking)** is related but separate scope

---

## Acceptance Criteria (Issue #23)

- [ ] `hr_samples` table supports multiple sources with provenance
- [ ] `import_fit_workouts.py` extracts "record" messages
- [ ] New FIT imports populate HR samples
- [ ] Existing 2 Suunto sessions backfilled with HR samples
- [ ] Query works: `SELECT * FROM hr_samples WHERE endurance_session_id = 1`
