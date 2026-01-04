#!/usr/bin/env python3
"""
Detect SENSOR ERRORS in biometric data (not statistical outliers).

Uses physiological bounds - if a value is outside what's humanly possible,
it's a sensor error. Natural variance (even if large) is preserved.

Run: python scripts/clean_biometrics.py
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from collections import defaultdict

PG_URI = os.environ.get(
    "DATABASE_URI",
    "postgresql://brock@localhost:5432/arnold_analytics"
)

# Physiological bounds for sensor error detection
# Values outside these ranges are almost certainly sensor errors, not real data
# Format: (min, max) - None means no bound
PHYSIOLOGICAL_BOUNDS = {
    'hrv_morning': (15, 250),      # HRV below 15 or above 250 is sensor error
    'resting_hr': (35, 100),       # RHR below 35 or above 100 (for athlete) is sensor error
    'sleep_rhr': (35, 100),        # Same for sleep RHR
    'avg_temperature': (28, 40),   # Skin temp in Celsius - outside this is sensor/ambient error
    'skin_temp_deviation': (-3, 3), # Deviation more than 3°C is likely error
}

# Window for calculating replacement value (use median of nearby valid readings)
WINDOW_SIZE = 7


def get_replacement_value(readings, idx, metric_type):
    """Get median of nearby VALID readings for imputation."""
    bounds = PHYSIOLOGICAL_BOUNDS.get(metric_type)
    if not bounds:
        return None
    
    min_val, max_val = bounds
    half = WINDOW_SIZE // 2
    start = max(0, idx - half)
    end = min(len(readings), idx + half + 1)
    
    # Get valid values in window (excluding current)
    valid_values = []
    for i in range(start, end):
        if i == idx:
            continue
        val = float(readings[i]['value'])
        if min_val <= val <= max_val:
            valid_values.append(val)
    
    if len(valid_values) >= 2:
        return float(np.median(valid_values))
    return None


def detect_sensor_errors():
    """Detect sensor errors using physiological bounds."""
    conn = psycopg2.connect(PG_URI, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    # Get all biometric readings
    cur.execute("""
        SELECT id, reading_date, metric_type, value, is_outlier, cleaned_value
        FROM biometric_readings
        ORDER BY metric_type, reading_date
    """)
    
    readings = cur.fetchall()
    
    # Group by metric type
    by_metric = defaultdict(list)
    for r in readings:
        if r['metric_type'] in PHYSIOLOGICAL_BOUNDS:
            by_metric[r['metric_type']].append(r)
    
    updates = []
    stats = {'checked': 0, 'errors': 0, 'imputed': 0}
    
    for metric_type, metric_readings in by_metric.items():
        bounds = PHYSIOLOGICAL_BOUNDS[metric_type]
        min_val, max_val = bounds
        
        for idx, reading in enumerate(metric_readings):
            stats['checked'] += 1
            
            current_value = float(reading['value'])
            is_error = current_value < min_val or current_value > max_val
            
            if is_error:
                stats['errors'] += 1
                
                # Only update if not already marked
                if not reading['is_outlier']:
                    replacement = get_replacement_value(metric_readings, idx, metric_type)
                    
                    if replacement is not None:
                        stats['imputed'] += 1
                        direction = "below" if current_value < min_val else "above"
                        bound = min_val if current_value < min_val else max_val
                        note = f"Sensor error: {current_value:.1f} {direction} physiological bound ({bound}), replaced with median {replacement:.1f}"
                        
                        updates.append({
                            'id': reading['id'],
                            'is_outlier': True,
                            'cleaned_value': replacement,
                            'imputation_method': 'physiological_bounds',
                            'imputation_note': note
                        })
                        
                        print(f"  {metric_type} on {reading['reading_date']}: {current_value:.1f} → {replacement:.1f} (outside {min_val}-{max_val})")
                    else:
                        # Flag but can't impute (not enough nearby valid data)
                        note = f"Sensor error: {current_value:.1f} outside bounds ({min_val}-{max_val}), no valid nearby data for imputation"
                        updates.append({
                            'id': reading['id'],
                            'is_outlier': True,
                            'cleaned_value': None,
                            'imputation_method': 'physiological_bounds',
                            'imputation_note': note
                        })
                        print(f"  {metric_type} on {reading['reading_date']}: {current_value:.1f} FLAGGED (outside {min_val}-{max_val}, no replacement)")
    
    # Apply updates
    if updates:
        print(f"\nApplying {len(updates)} updates...")
        for u in updates:
            cur.execute("""
                UPDATE biometric_readings
                SET is_outlier = %s,
                    cleaned_value = %s,
                    imputation_method = %s,
                    imputation_note = %s
                WHERE id = %s
            """, (u['is_outlier'], u['cleaned_value'], u['imputation_method'], 
                  u['imputation_note'], u['id']))
        
        conn.commit()
    
    # Clear any old flags that are no longer errors (in case bounds changed)
    cur.execute("""
        UPDATE biometric_readings
        SET is_outlier = FALSE, cleaned_value = NULL, 
            imputation_method = NULL, imputation_note = NULL
        WHERE is_outlier = TRUE 
          AND id NOT IN (SELECT unnest(%s::int[]))
    """, ([u['id'] for u in updates] if updates else [],))
    
    conn.commit()
    conn.close()
    
    print(f"\nSummary:")
    print(f"  Readings checked: {stats['checked']}")
    print(f"  Sensor errors found: {stats['errors']}")
    print(f"  Values imputed: {stats['imputed']}")


def show_current_errors():
    """Show currently flagged sensor errors."""
    conn = psycopg2.connect(PG_URI, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT reading_date, metric_type, value as raw_value, 
               cleaned_value, imputation_note
        FROM biometric_readings
        WHERE is_outlier = TRUE
        ORDER BY metric_type, reading_date
    """)
    
    errors = cur.fetchall()
    conn.close()
    
    if errors:
        print(f"\nCurrent sensor errors ({len(errors)}):")
        for e in errors:
            replacement = f"→ {e['cleaned_value']}" if e['cleaned_value'] else "(no replacement)"
            print(f"  {e['reading_date']} {e['metric_type']}: {e['raw_value']} {replacement}")
    else:
        print("\nNo sensor errors flagged.")


def main():
    print("Biometric Sensor Error Detection")
    print("=" * 50)
    print("Physiological bounds (values outside = sensor error):")
    for metric, (lo, hi) in sorted(PHYSIOLOGICAL_BOUNDS.items()):
        print(f"  {metric}: {lo} - {hi}")
    print()
    
    detect_sensor_errors()
    show_current_errors()


if __name__ == "__main__":
    main()
