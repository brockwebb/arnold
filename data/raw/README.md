# Data Lake - Raw Layer

Raw exports from devices and services. Organized by source and date.

## Structure

```
raw/
├── polar/                    # Polar HR monitor exports
│   └── YYYYMMDD--polar-user-data-export_UUID/
│       ├── training-session-*.json
│       └── ...
├── apple_health/             # Apple Health XML exports  
│   └── YYYYMMDD--export.xml
├── ultrahuman/               # Ultrahuman API responses (or exports)
│   └── YYYYMMDD--*.json
└── clinical/                 # FHIR bundles, lab results
    └── *.json
```

## Conventions

- Prefix folders with `YYYYMMDD--` for easy sorting
- Keep original filenames from exports
- Never modify raw files - transform in staging layer
- Import scripts should be idempotent (safe to re-run)

## Import Commands

```bash
# Polar HR data
python scripts/import_polar_sessions.py data/raw/YYYYMMDD--polar-export/

# Apple Health biometrics
python scripts/import_apple_health.py

# Full pipeline (preferred)
python scripts/sync_pipeline.py
```
