#!/usr/bin/env python3
"""
Import Apple Health Export

Streaming parser for Apple Health export.xml and clinical-records JSON.
Handles large files (200MB+) without loading into memory.

Outputs:
  - staging/apple_health_hr.parquet         Heart rate samples (aggregated hourly)
  - staging/apple_health_hr_raw.parquet     Heart rate samples (raw, if requested)
  - staging/apple_health_weight.parquet     Body mass measurements
  - staging/apple_health_sleep.parquet      Sleep analysis sessions
  - staging/apple_health_workouts.parquet   Workout sessions
  - staging/apple_health_hrv.parquet        HRV measurements
  - staging/apple_health_steps.parquet      Daily step counts
  - staging/clinical_labs.parquet           Lab results (FHIR)
  - staging/clinical_conditions.parquet     Diagnoses (FHIR)
  - staging/clinical_medications.parquet    Medications (FHIR)
  - staging/clinical_immunizations.parquet  Immunizations (FHIR)

Usage:
  python import_apple_health.py                    # Incremental import (from cutoff date)
  python import_apple_health.py --full             # Full import (all records)
  python import_apple_health.py --raw-hr           # Include raw HR (large!)
  python import_apple_health.py --verbose          # Show progress
  python import_apple_health.py --clinical-only    # Only clinical records

Incremental Import:
  By default, queries Postgres for the max date from Apple Health sources,
  subtracts 1 day for safety, and only processes records from that date forward.
  This dramatically reduces processing time for subsequent imports.
"""

import argparse
import json
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Optional, Generator, Any
from xml.etree.ElementTree import iterparse
from collections import defaultdict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import psycopg2

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "apple_health_export"
STAGING_DIR = DATA_DIR / "staging"

# Database config for cutoff query
DB_CONFIG = {
    "dbname": "arnold_analytics",
    "user": "brock",
    "host": "localhost",
    "port": 5432,
}

# Apple Health date format
# Example: "2025-05-15 18:31:17 -0500"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"

# Record types to extract from export.xml
RECORD_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierBodyMass": "weight",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierBodyMassIndex": "bmi",
    "HKQuantityTypeIdentifierBodyFatPercentage": "body_fat",
    "HKQuantityTypeIdentifierLeanBodyMass": "lean_mass",
    "HKQuantityTypeIdentifierBloodPressureSystolic": "bp_systolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic": "bp_diastolic",
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2",
    "HKQuantityTypeIdentifierRespiratoryRate": "resp_rate",
    "HKQuantityTypeIdentifierBodyTemperature": "body_temp",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
}


def parse_apple_date(date_str: str) -> datetime:
    """Parse Apple Health date format."""
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        # Try without timezone
        try:
            return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def get_cutoff_date(verbose: bool = False) -> Optional[date]:
    """Get cutoff date from Postgres: max Apple Health date minus 1 day.
    
    Returns None on cold start (no data yet) - will process everything.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT MAX(reading_date) 
            FROM biometric_readings 
            WHERE source ILIKE '%apple%' OR source ILIKE '%watch%' OR source ILIKE '%iphone%'
        """)
        result = cur.fetchone()[0]
        conn.close()
        
        if result is None:
            if verbose:
                print("  No existing Apple Health data - processing all records")
            return None
        
        # Subtract 1 day for safety margin (timezone edge cases, late arrivals)
        cutoff = result - timedelta(days=1)
        if verbose:
            print(f"  Cutoff date: {cutoff} (processing records from {cutoff} onwards)")
        return cutoff
        
    except Exception as e:
        if verbose:
            print(f"  Warning: Could not get cutoff date ({e}) - processing all records")
        return None


def stream_xml_records(xml_path: Path, verbose: bool = False, cutoff_date: Optional[date] = None) -> Generator[Dict, None, None]:
    """
    Stream parse Apple Health export.xml.
    Yields records one at a time without loading entire file.
    
    Args:
        xml_path: Path to export.xml
        verbose: Print progress
        cutoff_date: Only yield records on or after this date (None = all records)
    """
    record_count = 0
    skipped_count = 0
    workout_count = 0
    
    context = iterparse(str(xml_path), events=("end",))
    
    for event, elem in context:
        if elem.tag == "Record":
            record_type = elem.get("type")
            if record_type in RECORD_TYPES:
                # Check cutoff before building full record dict
                if cutoff_date is not None:
                    start_date_str = elem.get("startDate")
                    record_dt = parse_apple_date(start_date_str)
                    if record_dt and record_dt.date() < cutoff_date:
                        skipped_count += 1
                        elem.clear()
                        continue
                
                record = {
                    "type": RECORD_TYPES[record_type],
                    "original_type": record_type,
                    "value": elem.get("value"),
                    "unit": elem.get("unit"),
                    "source_name": elem.get("sourceName"),
                    "source_version": elem.get("sourceVersion"),
                    "device": elem.get("device"),
                    "start_date": elem.get("startDate"),
                    "end_date": elem.get("endDate"),
                    "creation_date": elem.get("creationDate"),
                }
                
                # Handle metadata entries
                metadata = {}
                for meta in elem.findall("MetadataEntry"):
                    metadata[meta.get("key")] = meta.get("value")
                if metadata:
                    record["metadata"] = metadata
                
                yield record
                record_count += 1
                
                if verbose and record_count % 50000 == 0:
                    print(f"  Processed {record_count:,} records...")
        
        elif elem.tag == "Workout":
            # Check cutoff for workouts too
            if cutoff_date is not None:
                start_date_str = elem.get("startDate")
                workout_dt = parse_apple_date(start_date_str)
                if workout_dt and workout_dt.date() < cutoff_date:
                    skipped_count += 1
                    elem.clear()
                    continue
            
            workout = {
                "type": "workout",
                "activity_type": elem.get("workoutActivityType"),
                "duration": elem.get("duration"),
                "duration_unit": elem.get("durationUnit"),
                "total_distance": elem.get("totalDistance"),
                "total_distance_unit": elem.get("totalDistanceUnit"),
                "total_energy": elem.get("totalEnergyBurned"),
                "total_energy_unit": elem.get("totalEnergyBurnedUnit"),
                "source_name": elem.get("sourceName"),
                "source_version": elem.get("sourceVersion"),
                "device": elem.get("device"),
                "start_date": elem.get("startDate"),
                "end_date": elem.get("endDate"),
                "creation_date": elem.get("creationDate"),
            }
            
            # Extract workout statistics
            stats = {}
            for stat in elem.findall("WorkoutStatistics"):
                stat_type = stat.get("type", "").replace("HKQuantityTypeIdentifier", "")
                stats[stat_type] = {
                    "avg": stat.get("average"),
                    "min": stat.get("minimum"),
                    "max": stat.get("maximum"),
                    "sum": stat.get("sum"),
                    "unit": stat.get("unit"),
                }
            if stats:
                workout["statistics"] = stats
            
            yield workout
            workout_count += 1
        
        elif elem.tag == "ActivitySummary":
            activity = {
                "type": "activity_summary",
                "date": elem.get("dateComponents"),
                "active_energy": elem.get("activeEnergyBurned"),
                "active_energy_goal": elem.get("activeEnergyBurnedGoal"),
                "exercise_time": elem.get("appleExerciseTime"),
                "exercise_time_goal": elem.get("appleExerciseTimeGoal"),
                "stand_hours": elem.get("appleStandHours"),
                "stand_hours_goal": elem.get("appleStandHoursGoal"),
            }
            yield activity
        
        # Clear element to free memory
        elem.clear()
    
    if verbose:
        print(f"  Total: {record_count:,} records, {workout_count:,} workouts")
        if skipped_count > 0:
            print(f"  Skipped: {skipped_count:,} records (before cutoff date)")


def process_hr_records(records: List[Dict], aggregate_hourly: bool = True) -> pd.DataFrame:
    """Process heart rate records, optionally aggregating to hourly."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["timestamp"] = df["start_date"].apply(parse_apple_date)
    df = df.dropna(subset=["timestamp", "value"])
    
    if aggregate_hourly and len(df) > 0:
        # Aggregate to hourly
        df["hour"] = df["timestamp"].dt.floor("H")
        df["date"] = df["timestamp"].dt.date
        
        hourly = df.groupby(["hour", "source_name"]).agg({
            "value": ["mean", "min", "max", "count"],
            "date": "first"
        }).reset_index()
        
        hourly.columns = ["hour", "source_name", "hr_avg", "hr_min", "hr_max", "hr_count", "date"]
        hourly["hr_avg"] = hourly["hr_avg"].round(1)
        return hourly
    else:
        return df[["timestamp", "value", "source_name", "unit"]].rename(
            columns={"value": "hr", "timestamp": "datetime"}
        )


def process_weight_records(records: List[Dict]) -> pd.DataFrame:
    """Process body mass records."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["timestamp"] = df["start_date"].apply(parse_apple_date)
    df = df.dropna(subset=["timestamp", "value"])
    
    # Convert to date for daily grain
    df["date"] = df["timestamp"].dt.date
    
    # Keep the latest measurement per day per source
    df = df.sort_values("timestamp").groupby(["date", "source_name"]).last().reset_index()
    
    return df[["date", "timestamp", "value", "unit", "source_name"]].rename(
        columns={"value": "weight_lbs", "timestamp": "measured_at"}
    )


def process_sleep_records(records: List[Dict]) -> pd.DataFrame:
    """Process sleep analysis records."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df["start_ts"] = df["start_date"].apply(parse_apple_date)
    df["end_ts"] = df["end_date"].apply(parse_apple_date)
    df = df.dropna(subset=["start_ts", "end_ts"])
    
    # Calculate duration
    df["duration_minutes"] = (df["end_ts"] - df["start_ts"]).dt.total_seconds() / 60
    
    # Extract sleep stage from value (e.g., "HKCategoryValueSleepAnalysisAsleepCore")
    df["sleep_stage"] = df["value"].str.replace("HKCategoryValueSleepAnalysis", "").str.lower()
    
    # Attribution date is wake date (end of sleep)
    df["date"] = df["end_ts"].dt.date
    
    return df[["date", "start_ts", "end_ts", "duration_minutes", "sleep_stage", "source_name"]]


def process_workout_records(records: List[Dict]) -> pd.DataFrame:
    """Process workout records."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df["start_ts"] = df["start_date"].apply(parse_apple_date)
    df["end_ts"] = df["end_date"].apply(parse_apple_date)
    df = df.dropna(subset=["start_ts"])
    
    # Parse numeric fields
    df["duration_min"] = pd.to_numeric(df["duration"], errors="coerce")
    df["distance"] = pd.to_numeric(df["total_distance"], errors="coerce")
    df["calories"] = pd.to_numeric(df["total_energy"], errors="coerce")
    
    # Clean activity type
    df["activity"] = df["activity_type"].str.replace("HKWorkoutActivityType", "")
    
    # Attribution date is start date
    df["date"] = df["start_ts"].dt.date
    
    return df[[
        "date", "start_ts", "end_ts", "activity", "duration_min",
        "distance", "total_distance_unit", "calories", "source_name"
    ]]


def process_hrv_records(records: List[Dict]) -> pd.DataFrame:
    """Process HRV records."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["timestamp"] = df["start_date"].apply(parse_apple_date)
    df = df.dropna(subset=["timestamp", "value"])
    
    df["date"] = df["timestamp"].dt.date
    
    return df[["date", "timestamp", "value", "unit", "source_name"]].rename(
        columns={"value": "hrv_ms", "timestamp": "measured_at"}
    )


def process_steps_records(records: List[Dict]) -> pd.DataFrame:
    """Process step count records, aggregating to daily."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["start_ts"] = df["start_date"].apply(parse_apple_date)
    df = df.dropna(subset=["start_ts", "value"])
    
    df["date"] = df["start_ts"].dt.date
    
    # Sum steps by day and source
    daily = df.groupby(["date", "source_name"]).agg({
        "value": "sum"
    }).reset_index()
    
    daily.columns = ["date", "source_name", "steps"]
    return daily


def process_bp_records(systolic_records: List[Dict], diastolic_records: List[Dict]) -> pd.DataFrame:
    """Process blood pressure records (matching systolic/diastolic by timestamp)."""
    if not systolic_records and not diastolic_records:
        return pd.DataFrame()
    
    # Process systolic
    sys_df = pd.DataFrame(systolic_records)
    sys_df["systolic"] = pd.to_numeric(sys_df["value"], errors="coerce")
    sys_df["timestamp"] = sys_df["start_date"].apply(parse_apple_date)
    sys_df = sys_df[["timestamp", "systolic", "source_name"]].dropna()
    
    # Process diastolic
    dia_df = pd.DataFrame(diastolic_records)
    dia_df["diastolic"] = pd.to_numeric(dia_df["value"], errors="coerce")
    dia_df["timestamp"] = dia_df["start_date"].apply(parse_apple_date)
    dia_df = dia_df[["timestamp", "diastolic", "source_name"]].dropna()
    
    # Merge on timestamp (within 1 minute tolerance)
    if len(sys_df) > 0 and len(dia_df) > 0:
        merged = pd.merge_asof(
            sys_df.sort_values("timestamp"),
            dia_df.sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("1min"),
            suffixes=("", "_dia")
        )
        merged["date"] = merged["timestamp"].dt.date
        return merged[["date", "timestamp", "systolic", "diastolic", "source_name"]]
    
    return pd.DataFrame()


def parse_clinical_labs(clinical_dir: Path, verbose: bool = False) -> pd.DataFrame:
    """Parse lab results from FHIR Observation JSON files."""
    records = []
    
    for filepath in sorted(clinical_dir.glob("Observation-*.json")):
        try:
            with open(filepath) as f:
                obs = json.load(f)
            
            # Only include lab results
            categories = obs.get("category", [])
            is_lab = any(
                c.get("text", "").lower() in ["laboratory", "lab"]
                or any(coding.get("code") == "laboratory" for coding in c.get("coding", []))
                for c in categories
            )
            
            if not is_lab:
                continue
            
            # Extract LOINC code
            code_info = obs.get("code", {})
            loinc_code = None
            test_name = code_info.get("text", "")
            
            for coding in code_info.get("coding", []):
                if coding.get("system") == "http://loinc.org":
                    loinc_code = coding.get("code")
                    if not test_name:
                        test_name = coding.get("display", "")
                    break
            
            # Extract value
            value_qty = obs.get("valueQuantity", {})
            value = value_qty.get("value")
            unit = value_qty.get("unit", "")
            
            # Extract reference range
            ref_range = obs.get("referenceRange", [{}])[0]
            ref_low = ref_range.get("low", {}).get("value")
            ref_high = ref_range.get("high", {}).get("value")
            ref_text = ref_range.get("text", "")
            
            # Extract date
            effective_date = obs.get("effectiveDateTime", "")
            if effective_date:
                try:
                    date = datetime.fromisoformat(effective_date.replace("Z", "+00:00")).date()
                except:
                    date = None
            else:
                date = None
            
            # Extract encounter info
            encounter = obs.get("encounter", {})
            encounter_type = encounter.get("display", "")
            
            records.append({
                "date": date,
                "test_name": test_name,
                "loinc_code": loinc_code,
                "value": value,
                "unit": unit,
                "ref_range_low": ref_low,
                "ref_range_high": ref_high,
                "ref_range_text": ref_text,
                "encounter_type": encounter_type,
                "status": obs.get("status", ""),
                "source_file": filepath.name
            })
            
        except Exception as e:
            if verbose:
                print(f"  Warning: Failed to parse {filepath.name}: {e}")
    
    if verbose:
        print(f"  Parsed {len(records)} lab results")
    
    return pd.DataFrame(records)


def parse_clinical_conditions(clinical_dir: Path, verbose: bool = False) -> pd.DataFrame:
    """Parse diagnoses from FHIR Condition JSON files."""
    records = []
    
    for filepath in sorted(clinical_dir.glob("Condition-*.json")):
        try:
            with open(filepath) as f:
                cond = json.load(f)
            
            # Extract condition info
            code_info = cond.get("code", {})
            condition_name = code_info.get("text", "")
            
            # Extract coding (ICD-10, SNOMED, etc.)
            icd_code = None
            snomed_code = None
            for coding in code_info.get("coding", []):
                system = coding.get("system", "")
                if "icd" in system.lower():
                    icd_code = coding.get("code")
                elif "snomed" in system.lower():
                    snomed_code = coding.get("code")
                if not condition_name:
                    condition_name = coding.get("display", "")
            
            # Extract dates
            onset = cond.get("onsetDateTime", "")
            abatement = cond.get("abatementDateTime", "")
            
            onset_date = None
            if onset:
                try:
                    onset_date = datetime.fromisoformat(onset.replace("Z", "+00:00")).date()
                except:
                    pass
            
            abatement_date = None
            if abatement:
                try:
                    abatement_date = datetime.fromisoformat(abatement.replace("Z", "+00:00")).date()
                except:
                    pass
            
            # Clinical status
            clinical_status = cond.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "")
            
            records.append({
                "condition_name": condition_name,
                "icd_code": icd_code,
                "snomed_code": snomed_code,
                "onset_date": onset_date,
                "abatement_date": abatement_date,
                "clinical_status": clinical_status,
                "source_file": filepath.name
            })
            
        except Exception as e:
            if verbose:
                print(f"  Warning: Failed to parse {filepath.name}: {e}")
    
    if verbose:
        print(f"  Parsed {len(records)} conditions")
    
    return pd.DataFrame(records)


def parse_clinical_medications(clinical_dir: Path, verbose: bool = False) -> pd.DataFrame:
    """Parse medications from FHIR MedicationRequest JSON files."""
    records = []
    
    for filepath in sorted(clinical_dir.glob("MedicationRequest-*.json")):
        try:
            with open(filepath) as f:
                med = json.load(f)
            
            # Extract medication info
            med_info = med.get("medicationCodeableConcept", {})
            med_name = med_info.get("text", "")
            
            # Extract coding (RxNorm, etc.)
            rxnorm_code = None
            for coding in med_info.get("coding", []):
                if "rxnorm" in coding.get("system", "").lower():
                    rxnorm_code = coding.get("code")
                if not med_name:
                    med_name = coding.get("display", "")
            
            # Extract dosage
            dosage_list = med.get("dosageInstruction", [])
            dosage_text = ""
            if dosage_list:
                dosage_text = dosage_list[0].get("text", "")
            
            # Extract dates
            authored = med.get("authoredOn", "")
            authored_date = None
            if authored:
                try:
                    authored_date = datetime.fromisoformat(authored.replace("Z", "+00:00")).date()
                except:
                    pass
            
            # Status
            status = med.get("status", "")
            
            records.append({
                "medication_name": med_name,
                "rxnorm_code": rxnorm_code,
                "dosage": dosage_text,
                "authored_date": authored_date,
                "status": status,
                "source_file": filepath.name
            })
            
        except Exception as e:
            if verbose:
                print(f"  Warning: Failed to parse {filepath.name}: {e}")
    
    if verbose:
        print(f"  Parsed {len(records)} medications")
    
    return pd.DataFrame(records)


def parse_clinical_immunizations(clinical_dir: Path, verbose: bool = False) -> pd.DataFrame:
    """Parse immunizations from FHIR Immunization JSON files."""
    records = []
    
    for filepath in sorted(clinical_dir.glob("Immunization-*.json")):
        try:
            with open(filepath) as f:
                imm = json.load(f)
            
            # Extract vaccine info
            vaccine_info = imm.get("vaccineCode", {})
            vaccine_name = vaccine_info.get("text", "")
            
            # Extract coding (CVX, etc.)
            cvx_code = None
            for coding in vaccine_info.get("coding", []):
                if "cvx" in coding.get("system", "").lower():
                    cvx_code = coding.get("code")
                if not vaccine_name:
                    vaccine_name = coding.get("display", "")
            
            # Extract date
            occurrence = imm.get("occurrenceDateTime", "")
            occurrence_date = None
            if occurrence:
                try:
                    occurrence_date = datetime.fromisoformat(occurrence.replace("Z", "+00:00")).date()
                except:
                    pass
            
            # Status
            status = imm.get("status", "")
            
            # Lot number
            lot_number = imm.get("lotNumber", "")
            
            records.append({
                "vaccine_name": vaccine_name,
                "cvx_code": cvx_code,
                "date": occurrence_date,
                "lot_number": lot_number,
                "status": status,
                "source_file": filepath.name
            })
            
        except Exception as e:
            if verbose:
                print(f"  Warning: Failed to parse {filepath.name}: {e}")
    
    if verbose:
        print(f"  Parsed {len(records)} immunizations")
    
    return pd.DataFrame(records)


def save_parquet(df: pd.DataFrame, name: str, verbose: bool = False) -> Optional[Path]:
    """Save DataFrame to Parquet in staging directory."""
    if df is None or len(df) == 0:
        if verbose:
            print(f"  Skipping {name} (no data)")
        return None
    
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STAGING_DIR / f"{name}.parquet"
    
    # Convert date columns
    for col in df.columns:
        if "date" in col.lower() and df[col].dtype == object:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_path)
    
    if verbose:
        print(f"  Saved {name}: {len(df):,} rows")
    
    return output_path


def update_catalog(tables: Dict[str, pd.DataFrame]):
    """Update catalog.json with Apple Health sources."""
    catalog_path = DATA_DIR / "catalog.json"
    
    if catalog_path.exists():
        with open(catalog_path) as f:
            catalog = json.load(f)
    else:
        catalog = {"version": "1.0", "sources": {}}
    
    if "sources" not in catalog:
        catalog["sources"] = {}
    
    now = datetime.now(tz=None).isoformat()  # Local time is fine for catalog metadata
    
    # Apple Health records
    for table_name, df in tables.items():
        if df is None or len(df) == 0:
            continue
        
        # Determine date range
        date_cols = [c for c in df.columns if "date" in c.lower()]
        date_range = [None, None]
        for col in date_cols:
            try:
                dates = pd.to_datetime(df[col], errors="coerce").dropna()
                if len(dates) > 0:
                    min_d = dates.min()
                    max_d = dates.max()
                    if date_range[0] is None or min_d < pd.to_datetime(date_range[0]):
                        date_range[0] = str(min_d.date())
                    if date_range[1] is None or max_d > pd.to_datetime(date_range[1]):
                        date_range[1] = str(max_d.date())
            except:
                pass
        
        # Build column metadata
        columns = {}
        for col in df.columns:
            dtype = str(df[col].dtype)
            if "int" in dtype:
                col_type = "int"
            elif "float" in dtype:
                col_type = "float"
            elif "datetime" in dtype or "date" in col.lower():
                col_type = "datetime"
            else:
                col_type = "string"
            columns[col] = {"type": col_type, "nullable": bool(df[col].isna().any())}
        
        catalog["sources"][table_name] = {
            "raw_path": "raw/apple_health_export/",
            "staging_table": f"staging/{table_name}.parquet",
            "grain": "varies",
            "row_count": len(df),
            "date_range": date_range if date_range[0] else None,
            "columns": columns,
            "updated_at": now
        }
    
    # Move apple_health from future_sources if present
    if "future_sources" in catalog and "apple_health" in catalog["future_sources"]:
        del catalog["future_sources"]["apple_health"]
    
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Import Apple Health data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show progress")
    parser.add_argument("--raw-hr", action="store_true", help="Include raw HR (not aggregated)")
    parser.add_argument("--clinical-only", action="store_true", help="Only process clinical records")
    parser.add_argument("--xml-only", action="store_true", help="Only process export.xml")
    parser.add_argument("--full", action="store_true", help="Process all records (ignore cutoff date)")
    args = parser.parse_args()
    
    print("Importing Apple Health data...")
    
    tables = {}
    
    # Process export.xml
    xml_path = RAW_DIR / "export.xml"
    if xml_path.exists() and not args.clinical_only:
        print(f"\nProcessing export.xml ({xml_path.stat().st_size / 1024 / 1024:.1f} MB)...")
        
        # Get cutoff date from Postgres (incremental import)
        if args.full:
            cutoff = None
            if args.verbose:
                print("  --full specified: processing all records")
        else:
            cutoff = get_cutoff_date(verbose=args.verbose)
        
        # Collect records by type
        records_by_type = defaultdict(list)
        workouts = []
        
        for record in stream_xml_records(xml_path, args.verbose, cutoff_date=cutoff):
            if record["type"] == "workout":
                workouts.append(record)
            else:
                records_by_type[record["type"]].append(record)
        
        # Process each type
        if args.verbose:
            print("\nProcessing record types...")
        
        # Heart rate
        hr_df = process_hr_records(records_by_type["hr"], aggregate_hourly=not args.raw_hr)
        if args.raw_hr:
            tables["apple_health_hr_raw"] = hr_df
        else:
            tables["apple_health_hr"] = hr_df
        save_parquet(hr_df, "apple_health_hr" if not args.raw_hr else "apple_health_hr_raw", args.verbose)
        
        # HRV
        hrv_df = process_hrv_records(records_by_type["hrv"])
        tables["apple_health_hrv"] = hrv_df
        save_parquet(hrv_df, "apple_health_hrv", args.verbose)
        
        # Weight
        weight_df = process_weight_records(records_by_type["weight"])
        tables["apple_health_weight"] = weight_df
        save_parquet(weight_df, "apple_health_weight", args.verbose)
        
        # Sleep
        sleep_df = process_sleep_records(records_by_type["sleep"])
        tables["apple_health_sleep"] = sleep_df
        save_parquet(sleep_df, "apple_health_sleep", args.verbose)
        
        # Steps
        steps_df = process_steps_records(records_by_type["steps"])
        tables["apple_health_steps"] = steps_df
        save_parquet(steps_df, "apple_health_steps", args.verbose)
        
        # Blood pressure
        bp_df = process_bp_records(records_by_type["bp_systolic"], records_by_type["bp_diastolic"])
        tables["apple_health_bp"] = bp_df
        save_parquet(bp_df, "apple_health_bp", args.verbose)
        
        # Workouts
        workout_df = process_workout_records(workouts)
        tables["apple_health_workouts"] = workout_df
        save_parquet(workout_df, "apple_health_workouts", args.verbose)
        
        # Resting HR
        resting_hr_df = process_hrv_records(records_by_type["resting_hr"])  # Same processing
        if len(resting_hr_df) > 0:
            resting_hr_df = resting_hr_df.rename(columns={"hrv_ms": "resting_hr"})
            tables["apple_health_resting_hr"] = resting_hr_df
            save_parquet(resting_hr_df, "apple_health_resting_hr", args.verbose)
    
    # Process clinical records
    clinical_dir = RAW_DIR / "clinical-records"
    if clinical_dir.exists() and not args.xml_only:
        print(f"\nProcessing clinical records...")
        
        # Labs
        labs_df = parse_clinical_labs(clinical_dir, args.verbose)
        tables["clinical_labs"] = labs_df
        save_parquet(labs_df, "clinical_labs", args.verbose)
        
        # Conditions
        conditions_df = parse_clinical_conditions(clinical_dir, args.verbose)
        tables["clinical_conditions"] = conditions_df
        save_parquet(conditions_df, "clinical_conditions", args.verbose)
        
        # Medications
        medications_df = parse_clinical_medications(clinical_dir, args.verbose)
        tables["clinical_medications"] = medications_df
        save_parquet(medications_df, "clinical_medications", args.verbose)
        
        # Immunizations
        immunizations_df = parse_clinical_immunizations(clinical_dir, args.verbose)
        tables["clinical_immunizations"] = immunizations_df
        save_parquet(immunizations_df, "clinical_immunizations", args.verbose)
    
    # Update catalog
    print("\nUpdating catalog...")
    update_catalog(tables)
    
    print("\n✓ Done")
    
    # Summary
    print("\nSummary:")
    for name, df in tables.items():
        if df is not None and len(df) > 0:
            print(f"  {name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
