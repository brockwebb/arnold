#!/usr/bin/env python3
"""
Analyze Functional Fitness Database Excel structure
"""

import pandas as pd
import sys
from pathlib import Path

EXCEL_FILE = "/Users/brock/Documents/GitHub/arnold/ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx"

def analyze_structure():
    """Examine Excel file structure"""

    print(f"\n{'='*70}")
    print("FUNCTIONAL FITNESS DATABASE ANALYSIS")
    print(f"{'='*70}\n")

    print(f"Loading Excel file: {EXCEL_FILE}")

    if not Path(EXCEL_FILE).exists():
        print(f"\n❌ ERROR: File not found!")
        print(f"Expected: {EXCEL_FILE}")
        return False

    try:
        xls = pd.ExcelFile(EXCEL_FILE)

        print(f"\n📊 Sheets found: {len(xls.sheet_names)}")
        for sheet_name in xls.sheet_names:
            print(f"  - {sheet_name}")

        # Find header row by looking for "Exercise Name" or similar
        print(f"\nSearching for header row...")
        for skip_rows in range(10):
            test_df = pd.read_excel(EXCEL_FILE, sheet_name=0, skiprows=skip_rows, nrows=1)
            if any('exercise' in str(col).lower() for col in test_df.columns):
                print(f"  ✓ Found header at row {skip_rows}")
                break

        # Load main sheet with proper header
        df = pd.read_excel(EXCEL_FILE, sheet_name=0, skiprows=skip_rows)

        print(f"\n📋 Main sheet: '{xls.sheet_names[0]}'")
        print(f"  Rows: {len(df)}")
        print(f"  Columns: {len(df.columns)}")

        print(f"\n🏷️  Columns ({len(df.columns)} total):")
        for i, col in enumerate(df.columns, 1):
            non_null = df[col].count()
            null_pct = (1 - non_null/len(df)) * 100
            print(f"  {i:2d}. {col:40s} ({non_null:4d} non-null, {null_pct:5.1f}% missing)")

        print(f"\n🔍 Sample (first 5 rows):")
        print(df.head(5).to_string())

        print(f"\n📈 Categorical columns (< 50 unique values):")
        for col in df.columns:
            unique = df[col].nunique()
            if unique < 50 and unique > 1:
                print(f"\n  {col} ({unique} unique values):")
                value_counts = df[col].value_counts().head(10)
                for val, count in value_counts.items():
                    print(f"    {str(val):40s}: {count:4d}")

        print(f"\n✅ Analysis complete.")
        print(f"\nNext step: Update column names in import_functional_fitness_db.py")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = analyze_structure()
    sys.exit(0 if success else 1)
