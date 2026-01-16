# Issue 014: Ingest Suunto Historical Data (2019+)

## Status: Open
## Priority: High
## Created: 2025-01-15

## Context
Currently only 4 valid endurance HRR intervals vs 216 polar. Full Suunto history is downloaded locally but not ingested into Arnold.

## Scope
- Ingest historical Suunto data (potentially back to 2019)
- Parse FIT/JSON exports from Suunto app
- Extract HR time-series for HRR analysis
- Map to EnduranceWorkout nodes in Neo4j

## Value
- Dramatically expand endurance HRR sample size
- Enable longitudinal HRR trend analysis across years of running data
- Better stratum balance for STRENGTH vs ENDURANCE recovery comparisons
- Historical ultramarathon HR data (100-milers, etc.)

## Technical Notes
- Check Suunto export format (FIT vs proprietary JSON)
- May need new sync pipeline step or extend existing FIT processor
- Consider one-time historical import vs ongoing sync
- Suunto app may have different export options (Moves, workouts, etc.)

## Questions
- Where is the downloaded Suunto data located?
- What format(s) are available?
- Date range of available data?

## Blocked By
Nothing - ready to investigate

## Blocks
- Meaningful endurance HRR trend analysis
- Stratum-balanced recovery comparisons
