# Issue 005: Apple Health Data Expansion

> **Created**: January 7, 2026
> **Status**: Backlog
> **Priority**: Medium (data completeness)

## Opportunity

Apple Health exports contain additional metrics beyond HRV that could enrich Arnold's readiness assessment:

### Currently Imported
- HRV (as `hrv_apple_rmssd`)
- Resting HR
- Sleep metrics (total, deep, REM)

### Potentially Available (Needs Investigation)
- **VO2max estimates** - Apple Watch calculates from outdoor workouts
- **Walking/running distance** - Daily activity
- **Step count** - Activity baseline
- **Active/resting energy** - Caloric expenditure
- **Stand hours** - Sedentary behavior
- **Respiratory rate** - Sleep quality indicator
- **Blood oxygen (SpO2)** - Overnight patterns
- **Workout records** - Cross-reference with Polar/FIT data
- **Mindfulness minutes** - Recovery indicator
- **Caffeine intake** - If tracked via third-party apps
- **Water intake** - Hydration

## Investigation Required

1. Export fresh Apple Health data
2. Examine XML structure for available record types
3. Assess data quality and coverage
4. Identify which metrics add value to existing pipeline
5. Avoid duplicating data already captured by Ultrahuman or Polar

## Architecture Considerations

Per ADR-001, any new metrics should:
- Store in Postgres `biometric_readings` with `source = 'apple_health'`
- Use distinct `metric_type` values (e.g., `vo2max_apple`, `steps_daily`)
- Not conflict with device-native sources

## Decision Needed

Which Apple Health metrics provide unique value not already captured by:
- Ultrahuman Ring (sleep, HRV, recovery)
- Polar HR monitor (workout HR, zones)
- FIT files (detailed workout data)
