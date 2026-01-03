"""
Arnold Muscle Heatmap Dashboard
================================
Anatomical load visualization.

Stack: Streamlit + DuckDB
Math: Weber-Fechner logarithmic normalization

Usage:
    streamlit run src/muscle_heatmap.py
"""

import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta

# =============================================================================
# Configuration
# =============================================================================

DATA_DIR = Path(__file__).parent.parent / "data"
STAGING_DIR = DATA_DIR / "staging"
STATIC_DIR = DATA_DIR / "static"

SETS_PARQUET = STAGING_DIR / "sets.parquet"
MUSCLE_TARGETING_CSV = STAGING_DIR / "muscle_targeting.csv"
MUSCLE_MAPPING_JSON = STATIC_DIR / "muscle_svg_mapping.json"


# =============================================================================
# Data Loading
# =============================================================================

@st.cache_data
def load_muscle_mapping():
    """Load muscle name -> SVG ID mapping with log factors."""
    with open(MUSCLE_MAPPING_JSON) as f:
        data = json.load(f)
    return pd.DataFrame(data["muscles"])


@st.cache_data
def load_muscle_targeting():
    """Load exercise -> muscle targeting relationships."""
    return pd.read_csv(MUSCLE_TARGETING_CSV)


@st.cache_data
def get_date_range():
    """Get min/max dates from workout data."""
    conn = duckdb.connect()
    result = conn.execute(f"""
        SELECT MIN(date) as min_date, MAX(date) as max_date
        FROM '{SETS_PARQUET}'
        WHERE date IS NOT NULL
    """).fetchone()
    conn.close()
    return (
        datetime.strptime(result[0], "%Y-%m-%d").date(),
        datetime.strptime(result[1], "%Y-%m-%d").date()
    )


def query_muscle_volume(start_date: str, end_date: str, role_weight: dict) -> pd.DataFrame:
    """
    Query volume per muscle with role weighting.
    """
    conn = duckdb.connect()
    
    conn.execute(f"""
        CREATE OR REPLACE TABLE muscle_targeting AS 
        SELECT * FROM '{MUSCLE_TARGETING_CSV}'
    """)
    
    query = f"""
        WITH set_volume AS (
            SELECT 
                exercise_id,
                COALESCE(reps, 1) * COALESCE(load_lbs, 0) as volume
            FROM '{SETS_PARQUET}'
            WHERE date >= '{start_date}' 
              AND date <= '{end_date}'
              AND load_lbs > 0
        ),
        muscle_volume AS (
            SELECT 
                mt.muscle_name,
                mt.target_role,
                SUM(sv.volume) as raw_volume
            FROM set_volume sv
            JOIN muscle_targeting mt ON sv.exercise_id = mt.exercise_id
            GROUP BY mt.muscle_name, mt.target_role
        )
        SELECT 
            muscle_name,
            SUM(
                CASE 
                    WHEN target_role = 'primary' THEN raw_volume * {role_weight['primary']}
                    WHEN target_role = 'secondary' THEN raw_volume * {role_weight['secondary']}
                    ELSE raw_volume * 0.25
                END
            ) as weighted_volume
        FROM muscle_volume
        GROUP BY muscle_name
    """
    
    df = conn.execute(query).df()
    conn.close()
    return df


def compute_intensities(volume_df: pd.DataFrame, mapping_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply logarithmic scaling with per-muscle log_factor.
    """
    merged = volume_df.merge(
        mapping_df,
        left_on="muscle_name",
        right_on="neo4j_name",
        how="inner"
    )
    
    if merged.empty:
        return pd.DataFrame(columns=["muscle_name", "group", "view", "intensity", "log_volume"])
    
    merged["adjusted_volume"] = merged["weighted_volume"] * merged["log_factor"]
    merged["log_volume"] = np.log10(merged["adjusted_volume"].clip(lower=1))
    
    if merged["log_volume"].max() > merged["log_volume"].min():
        merged["intensity"] = (merged["log_volume"] - merged["log_volume"].min()) / \
                              (merged["log_volume"].max() - merged["log_volume"].min())
    else:
        merged["intensity"] = 0.5
    
    return merged[["muscle_name", "group", "view", "intensity", "log_volume", "weighted_volume"]]


def intensity_to_color(intensity: float) -> str:
    """Map 0-1 intensity to a color gradient."""
    if intensity < 0.33:
        r = int(200 + (255 - 200) * (intensity / 0.33))
        g = int(200 + (255 - 200) * (intensity / 0.33))
        b = int(200 - 200 * (intensity / 0.33))
    elif intensity < 0.66:
        adj = (intensity - 0.33) / 0.33
        r = 255
        g = int(255 - (255 - 165) * adj)
        b = 0
    else:
        adj = (intensity - 0.66) / 0.34
        r = 255
        g = int(165 - 165 * adj)
        b = 0
    return f"#{r:02x}{g:02x}{b:02x}"


# =============================================================================
# Streamlit UI
# =============================================================================

def main():
    st.set_page_config(
        page_title="Arnold: Muscle Heatmap",
        page_icon="💪",
        layout="wide"
    )
    
    st.title("💪 Arnold: Anatomical Load Map")
    st.caption("Visualize training stress across muscle groups")
    
    # Check for required files
    missing = []
    if not SETS_PARQUET.exists():
        missing.append(str(SETS_PARQUET))
    if not MUSCLE_TARGETING_CSV.exists():
        missing.append(str(MUSCLE_TARGETING_CSV))
    if not MUSCLE_MAPPING_JSON.exists():
        missing.append(str(MUSCLE_MAPPING_JSON))
    
    if missing:
        st.error(f"Missing required files:\n" + "\n".join(missing))
        return
    
    mapping_df = load_muscle_mapping()
    min_date, max_date = get_date_range()
    
    # Sidebar controls
    st.sidebar.header("Controls")
    
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(max_date - timedelta(days=7), max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    if len(date_range) != 2:
        st.warning("Select both start and end dates")
        return
    
    start_date, end_date = date_range
    
    use_rolling = st.sidebar.checkbox("Use Rolling Window", value=False)
    if use_rolling:
        window_days = st.sidebar.slider("Window (days)", 3, 28, 7)
        days_range = (max_date - min_date).days
        offset = st.sidebar.slider(
            "Slide through time",
            0, max(0, days_range - window_days),
            days_range - window_days
        )
        start_date = min_date + timedelta(days=offset)
        end_date = start_date + timedelta(days=window_days)
        st.sidebar.caption(f"Showing: {start_date} to {end_date}")
    
    st.sidebar.subheader("Muscle Role Weights")
    primary_weight = st.sidebar.slider("Primary muscle", 0.5, 1.5, 1.0, 0.1)
    secondary_weight = st.sidebar.slider("Secondary muscle", 0.1, 1.0, 0.5, 0.1)
    
    role_weight = {"primary": primary_weight, "secondary": secondary_weight}
    
    # Query and compute
    with st.spinner("Computing muscle volumes..."):
        volume_df = query_muscle_volume(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            role_weight
        )
        
        if volume_df.empty:
            st.warning("No workout data in selected date range")
            return
        
        intensity_df = compute_intensities(volume_df, mapping_df)
    
    if intensity_df.empty:
        st.warning("No muscle targeting data found for exercises in this range")
        return
    
    # =========================================================================
    # Visualization: Grouped Bar Chart by Muscle Group
    # =========================================================================
    
    st.subheader("📊 Muscle Load by Group")
    
    # Aggregate by group
    group_data = intensity_df.groupby("group").agg({
        "weighted_volume": "sum",
        "log_volume": "sum",
        "intensity": "mean"
    }).reset_index().sort_values("weighted_volume", ascending=False)
    
    # Create colored bars using Streamlit columns
    for _, row in group_data.iterrows():
        col1, col2, col3 = st.columns([1, 3, 1])
        with col1:
            st.write(f"**{row['group'].title()}**")
        with col2:
            color = intensity_to_color(row['intensity'])
            bar_width = int(row['intensity'] * 100)
            st.markdown(
                f'<div style="background: linear-gradient(90deg, {color} {bar_width}%, #e0e0e0 {bar_width}%); '
                f'height: 25px; border-radius: 4px; margin: 2px 0;"></div>',
                unsafe_allow_html=True
            )
        with col3:
            st.write(f"{row['weighted_volume']:,.0f} lbs")
    
    st.markdown("---")
    
    # =========================================================================
    # Detailed View: Anterior vs Posterior
    # =========================================================================
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔵 Anterior (Front)")
        anterior = intensity_df[intensity_df["view"] == "anterior"].sort_values("weighted_volume", ascending=False)
        if not anterior.empty:
            for _, row in anterior.iterrows():
                color = intensity_to_color(row['intensity'])
                st.markdown(
                    f'<div style="display:flex; align-items:center; margin:4px 0;">'
                    f'<div style="width:20px; height:20px; background:{color}; border-radius:3px; margin-right:10px;"></div>'
                    f'<span style="flex:1;">{row["muscle_name"]}</span>'
                    f'<span style="color:#666;">{row["weighted_volume"]:,.0f} lbs</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No anterior muscle data")
    
    with col2:
        st.subheader("🔴 Posterior (Back)")
        posterior = intensity_df[intensity_df["view"] == "posterior"].sort_values("weighted_volume", ascending=False)
        if not posterior.empty:
            for _, row in posterior.iterrows():
                color = intensity_to_color(row['intensity'])
                st.markdown(
                    f'<div style="display:flex; align-items:center; margin:4px 0;">'
                    f'<div style="width:20px; height:20px; background:{color}; border-radius:3px; margin-right:10px;"></div>'
                    f'<span style="flex:1;">{row["muscle_name"]}</span>'
                    f'<span style="color:#666;">{row["weighted_volume"]:,.0f} lbs</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No posterior muscle data")
    
    # =========================================================================
    # Color Legend
    # =========================================================================
    
    st.markdown("---")
    st.subheader("Intensity Legend (Log-Normalized)")
    legend_cols = st.columns(5)
    labels = ["Low", "Low-Med", "Medium", "Med-High", "High"]
    for i, (col, label) in enumerate(zip(legend_cols, labels)):
        intensity = i / 4
        color = intensity_to_color(intensity)
        col.markdown(
            f'<div style="background:{color}; padding:10px; text-align:center; border-radius:4px;">'
            f'{label}</div>',
            unsafe_allow_html=True
        )
    
    # =========================================================================
    # Raw Data Expander
    # =========================================================================
    
    with st.expander("📋 Raw Volume Data"):
        st.dataframe(
            intensity_df[["muscle_name", "group", "view", "weighted_volume", "intensity"]]
            .sort_values("weighted_volume", ascending=False)
            .rename(columns={
                "muscle_name": "Muscle",
                "group": "Group", 
                "view": "View",
                "weighted_volume": "Volume (lbs)",
                "intensity": "Intensity"
            }),
            use_container_width=True
        )


if __name__ == "__main__":
    main()
