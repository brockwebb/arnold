# Data Sources and Provenance

> **Last Updated**: January 10, 2026  
> **Owner**: Arnold System  
> **Status**: Config-driven source priority (see `config/sources.yaml`)

---

## Overview

Arnold integrates data from multiple sources (wearables, manual entry, clinical records). 
Source priority is now **config-driven** rather than hardcoded in importers.

**Key principle**: Importers pull ALL data. Resolution happens downstream.

---

## Configuration

### Source Priority Config

All source priorities are defined in:
```
config/sources.yaml
```

This file is self-documenting with instructions for both humans and AI assistants.

### Key Commands

```bash
# Validate configuration
python scripts/sync/validate_config.py

# Show config for a specific metric
python scripts/sync/source_resolver.py --show hrv

# List all registered sources
python scripts/sync/source_resolver.py --list-sources

# List all configured metrics
python scripts/sync/source_resolver.py --list-metrics
```

---

## Current Source Hierarchy

From `config/sources.yaml`:

### Biometric Data

| Metric | Primary Source | Fallback | Notes |
|--------|---------------|----------|-------|
| **HRV** | Ultrahuman | *none* | RMSSD algorithm. Apple uses SDNN — incompatible. |
| **Resting HR** | Ultrahuman | Apple Watch | Overnight measurement preferred. |
| **Sleep** | Ultrahuman | Apple Watch | Ring-based detection more accurate. |
| **Skin Temp** | Ultrahuman | *none* | Ring placement more consistent. |
| **Workout HR** | Polar H10 | Apple Watch | Chest strap is gold standard. |
| **Ambient HR** | Apple Watch | *none* | Daytime HR when not exercising. |
| **Steps** | Apple Watch | Ultrahuman | Watch always on wrist. |
| **Weight** | Apple Health | manual | Manual scale entries. |
| **Blood Pressure** | Apple Health | manual | Manual cuff readings. |

### Training Data

| Data Type | Source |
|-----------|--------|
| Strength workouts | Arnold (manual logging) |
| Endurance workouts | Polar Flow (FIT files) |
| Race history | Manual import |

### Clinical Data

| Data Type | Source | Coding |
|-----------|--------|--------|
| Lab results | Apple Health (FHIR) | LOINC |
| Conditions | Apple Health (FHIR) | ICD-10/SNOMED |
| Medications | Apple Health (FHIR) | RxNorm |
| Immunizations | Apple Health (FHIR) | CVX |

---

## Algorithm Compatibility

### HRV: SDNN vs RMSSD

**Critical**: Apple Watch and ring devices use different HRV algorithms:

| Device | Algorithm | Measures |
|--------|-----------|----------|
| Apple Watch | SDNN | Standard deviation of all NN intervals |
| Ultrahuman | RMSSD | Root mean square of successive differences |
| Oura | RMSSD | Root mean square of successive differences |

**These are NOT interchangeable.** A "50ms" reading from each means different things.
Mixing them would corrupt trend analysis.

The config enforces this by setting `fallback: []` for HRV.

---

## Changing Devices

### To switch primary source for a metric:

1. Edit `config/sources.yaml`
2. Change the `primary` field
3. Run `python scripts/sync/validate_config.py`
4. Run sync pipeline

### To add a new device:

1. Add to `registered_sources` in `config/sources.yaml`
2. Add to relevant metrics (primary or fallback)
3. Create importer in `scripts/sync/` if needed
4. Run validation

### To retire a device:

1. Move to fallback list (historical data remains useful)
2. Set new primary
3. Consider adding a data annotation for the transition date

---

## Importer Architecture

Importers are **dumb pipes**:
- Pull ALL available data
- Tag with source attribution
- Save to staging (Parquet)
- NO filtering, NO opinions

Source resolution happens in:
- `scripts/sync/source_resolver.py` — resolution logic
- Analytics queries — pick preferred source per metric

---

## Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Ultrahuman │     │ Apple Watch │     │   Polar H10 │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────┐
│                    IMPORTERS                         │
│  (Pull ALL data, tag with source, save to staging)  │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│              config/sources.yaml                     │
│         (Defines source priority per metric)         │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│              SOURCE RESOLVER                         │
│   get_preferred_source(metric, available_sources)    │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│              ANALYTICS LAYER                         │
│        (Uses resolved source for queries)            │
└─────────────────────────────────────────────────────┘
```

---

## Version History

| Date | Change |
|------|--------|
| 2026-01-10 | Migrated to config-driven source priority |
| 2025-05-13 | Started using Ultrahuman Ring |

See `config/sources.yaml` changelog for detailed history.
