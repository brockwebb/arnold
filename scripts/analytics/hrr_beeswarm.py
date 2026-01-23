#!/usr/bin/env python3
"""
HRR Beeswarm Plot - Heart Rate Recovery Distribution by Timepoint

Generates a beeswarm/swarm plot showing HRR distribution at each standard
timepoint (30s, 60s, 120s, 180s, 240s, 300s).
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2
import seaborn as sns
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent / '.env')


def get_db_connection():
    """Get connection to arnold_analytics database."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'arnold_analytics'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '')
    )


def fetch_hrr_data() -> pd.DataFrame:
    """Fetch HRR data for pass/flagged intervals."""
    query = """
        SELECT
            id,
            hrr30_abs,
            hrr60_abs,
            hrr120_abs,
            hrr180_abs,
            hrr240_abs,
            hrr300_abs
        FROM hr_recovery_intervals
        WHERE quality_status IN ('pass', 'flagged')
    """

    with get_db_connection() as conn:
        df = pd.read_sql(query, conn)

    return df


def reshape_for_beeswarm(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape wide data to long format for seaborn."""
    # Melt the dataframe to long format
    timepoint_cols = {
        'hrr30_abs': 'HRR30',
        'hrr60_abs': 'HRR60',
        'hrr120_abs': 'HRR120',
        'hrr180_abs': 'HRR180',
        'hrr240_abs': 'HRR240',
        'hrr300_abs': 'HRR300'
    }

    # Rename columns for display
    df_renamed = df.rename(columns=timepoint_cols)

    # Melt to long format
    df_long = df_renamed.melt(
        id_vars=['id'],
        value_vars=list(timepoint_cols.values()),
        var_name='Timepoint',
        value_name='HR Drop (bpm)'
    )

    # Drop null values (intervals shorter than the timepoint)
    df_long = df_long.dropna(subset=['HR Drop (bpm)'])

    # Order timepoints correctly
    timepoint_order = ['HRR30', 'HRR60', 'HRR120', 'HRR180', 'HRR240', 'HRR300']
    df_long['Timepoint'] = pd.Categorical(
        df_long['Timepoint'],
        categories=timepoint_order,
        ordered=True
    )

    return df_long


def compute_summary_stats(df_long: pd.DataFrame) -> pd.DataFrame:
    """Compute summary statistics per timepoint."""
    stats = df_long.groupby('Timepoint', observed=True)['HR Drop (bpm)'].agg([
        ('n', 'count'),
        ('median', 'median'),
        ('q25', lambda x: x.quantile(0.25)),
        ('q75', lambda x: x.quantile(0.75)),
        ('min', 'min'),
        ('max', 'max')
    ]).reset_index()

    stats['IQR'] = stats['q75'] - stats['q25']

    return stats


def create_beeswarm_plot(df_long: pd.DataFrame, stats: pd.DataFrame, output_path: Path):
    """Create and save the beeswarm plot."""
    # Set up the figure
    fig, ax = plt.subplots(figsize=(12, 8))

    # Create swarm plot with jitter
    sns.stripplot(
        data=df_long,
        x='Timepoint',
        y='HR Drop (bpm)',
        ax=ax,
        alpha=0.5,
        size=4,
        jitter=0.3,
        color='steelblue'
    )

    # Add median markers
    timepoints = stats['Timepoint'].tolist()
    medians = stats['median'].tolist()

    for i, (tp, med) in enumerate(zip(timepoints, medians)):
        ax.hlines(med, i - 0.3, i + 0.3, colors='red', linewidths=2, zorder=10)

    # Add n= annotations at top
    y_max = df_long['HR Drop (bpm)'].max()
    y_padding = y_max * 0.05

    for i, row in stats.iterrows():
        ax.annotate(
            f'n={int(row["n"])}',
            xy=(i, y_max + y_padding),
            ha='center',
            va='bottom',
            fontsize=9,
            color='gray'
        )

    # Formatting
    ax.set_title('Heart Rate Recovery Distribution by Timepoint', fontsize=14, fontweight='bold')
    ax.set_xlabel('Recovery Timepoint', fontsize=12)
    ax.set_ylabel('HR Drop (bpm)', fontsize=12)
    ax.set_ylim(bottom=0, top=y_max + y_padding * 3)

    # Add legend for median line
    from matplotlib.lines import Line2D
    legend_elements = [Line2D([0], [0], color='red', linewidth=2, label='Median')]
    ax.legend(handles=legend_elements, loc='upper right')

    # Grid for readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\nPlot saved to: {output_path}")


def print_summary_stats(stats: pd.DataFrame):
    """Print summary statistics to console."""
    print("\n" + "=" * 70)
    print("Heart Rate Recovery Summary Statistics")
    print("=" * 70)
    print(f"{'Timepoint':<10} {'n':>6} {'Median':>8} {'IQR':>10} {'Range':>15}")
    print("-" * 70)

    for _, row in stats.iterrows():
        range_str = f"{int(row['min'])}-{int(row['max'])}"
        print(f"{row['Timepoint']:<10} {int(row['n']):>6} {row['median']:>8.1f} "
              f"{row['IQR']:>10.1f} {range_str:>15}")

    print("=" * 70)


def main():
    """Main entry point."""
    # Fetch data
    print("Fetching HRR data from database...")
    df = fetch_hrr_data()
    print(f"Found {len(df)} pass/flagged intervals")

    # Reshape for plotting
    df_long = reshape_for_beeswarm(df)

    # Compute stats
    stats = compute_summary_stats(df_long)

    # Print summary
    print_summary_stats(stats)

    # Create plot
    output_path = Path(__file__).parent.parent.parent / 'outputs' / 'hrr_beeswarm.png'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    create_beeswarm_plot(df_long, stats, output_path)


if __name__ == '__main__':
    main()
