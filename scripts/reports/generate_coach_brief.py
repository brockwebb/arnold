#!/usr/bin/env python3
"""
Coach Brief Report Generator
============================

Generates a PDF report with key metrics for coaching decisions.
This is a "worker" script - Claude orchestrates, this computes.

Design principles:
- Graceful degradation: Works with whatever data exists
- Pre-computed metrics: Queries materialized views, not raw data
- Static output: PDF is deterministic given the same data
- No LLM in the loop: Pure Python, runs locally

Usage:
    python generate_coach_brief.py                    # Generate for today
    python generate_coach_brief.py --date 2026-01-04  # Specific date
    python generate_coach_brief.py --output /path/to/report.pdf
    python generate_coach_brief.py --dry-run          # Preview without PDF
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor

# Optional imports - graceful degradation
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_pdf import PdfPages
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# =============================================================================
# Configuration
# =============================================================================

DB_CONFIG = {
    'dbname': 'arnold_analytics',
    'host': 'localhost',
    'port': 5432,
}

# Reports go in data/, not scripts/ - keep data out of git
REPORT_DIR = Path(__file__).parent.parent.parent / 'data' / 'reports'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Color scheme
COLORS = {
    'primary': '#2563eb',      # Blue
    'secondary': '#64748b',    # Slate
    'success': '#22c55e',      # Green
    'warning': '#f59e0b',      # Amber
    'danger': '#ef4444',       # Red
    'background': '#f8fafc',   # Light gray
    'text': '#1e293b',         # Dark slate
}


# =============================================================================
# Data Access Layer
# =============================================================================

class CoachBriefData:
    """Encapsulates all data needed for the coach brief report."""
    
    def __init__(self, conn, report_date: datetime.date):
        self.conn = conn
        self.report_date = report_date
        self.snapshot = None
        self.biometric_history = None
        self.training_history = None
        self.upcoming_sessions = None
        self.annotations = []        # Active annotations for context
        self.data_gaps = []          # Issues without explanation
        self.explained_gaps = []     # Issues with annotation context
        
    def load(self):
        """Load all data needed for the report."""
        self._load_snapshot()
        self._load_biometric_history()
        self._load_training_history()
        self._load_annotations()
        self._check_data_gaps()
        return self
    
    def _load_snapshot(self):
        """Load the coach brief snapshot (current state)."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM coach_brief_snapshot LIMIT 1")
            self.snapshot = cur.fetchone()
            
        if not self.snapshot:
            # Fallback: build snapshot from raw data
            self.snapshot = self._build_fallback_snapshot()
            
    def _build_fallback_snapshot(self) -> Dict[str, Any]:
        """Build snapshot when materialized view is empty/stale."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get latest biometrics
            cur.execute("""
                SELECT 
                    MAX(CASE WHEN metric_type = 'hrv_morning' THEN value END) as today_hrv,
                    MAX(CASE WHEN metric_type = 'resting_hr' THEN value END) as today_rhr
                FROM biometric_readings
                WHERE reading_date = (SELECT MAX(reading_date) FROM biometric_readings)
            """)
            result = cur.fetchone()
            
        return {
            'report_date': self.report_date,
            'today_hrv': result.get('today_hrv') if result else None,
            'today_rhr': result.get('today_rhr') if result else None,
            'hrv_7d_avg': None,
            'hrv_30d_avg': None,
            'acwr': None,
            'workouts_7d': None,
        }
    
    def _load_biometric_history(self, days: int = 90):
        """Load biometric trend history for charts."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    reading_date,
                    hrv_ms,
                    rhr_bpm,
                    sleep_hours,
                    hrv_7d_avg,
                    hrv_30d_avg,
                    rhr_7d_avg
                FROM biometric_trends
                WHERE reading_date >= %s
                ORDER BY reading_date
            """, (self.report_date - timedelta(days=days),))
            self.biometric_history = cur.fetchall()
            
    def _load_training_history(self, weeks: int = 12):
        """Load training trend history."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    week_start,
                    workouts,
                    volume_lbs,
                    volume_wow_pct,
                    volume_4wk_avg
                FROM training_trends
                WHERE week_start >= %s
                ORDER BY week_start
            """, (self.report_date - timedelta(weeks=weeks),))  # Fixed: was weeks*7
            self.training_history = cur.fetchall()
    
    def _load_annotations(self):
        """Load active annotations that apply to report date."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Try the function first, fall back to direct query
            try:
                cur.execute("SELECT * FROM annotations_for_date(%s)", (self.report_date,))
                self.annotations = cur.fetchall()
            except Exception:
                # Function may not exist yet - direct query
                cur.execute("""
                    SELECT 
                        id, target_type, target_metric, reason_code, explanation,
                        annotation_date, date_range_end,
                        (date_range_end IS NULL AND annotation_date <= %s) as is_ongoing
                    FROM data_annotations
                    WHERE is_active = TRUE
                      AND annotation_date <= %s
                      AND (date_range_end IS NULL OR date_range_end >= %s)
                    ORDER BY annotation_date DESC
                """, (self.report_date, self.report_date, self.report_date))
                self.annotations = cur.fetchall()
            
    def _check_data_gaps(self):
        """Identify data quality issues, cross-referencing with annotations."""
        # Build lookup of annotated metrics
        annotated_metrics = {a['target_metric'] for a in self.annotations if a.get('target_metric')}
        
        def add_gap(metric: str, message: str):
            """Add gap to appropriate list based on whether it's annotated."""
            if metric in annotated_metrics or 'all' in annotated_metrics:
                # Find the relevant annotation
                for a in self.annotations:
                    if a.get('target_metric') in (metric, 'all'):
                        self.explained_gaps.append({
                            'message': message,
                            'reason': a.get('reason_code'),
                            'explanation': a.get('explanation', '')[:100]  # Truncate for display
                        })
                        break
            else:
                self.data_gaps.append(message)
        
        if self.snapshot:
            days_since_hrv = self.snapshot.get('days_since_hrv')
            if days_since_hrv and days_since_hrv > 2:
                add_gap('hrv', f"HRV data is {days_since_hrv} days old")
                
            days_since_sleep = self.snapshot.get('days_since_sleep')
            if days_since_sleep and days_since_sleep > 2:
                add_gap('sleep', f"Sleep data is {days_since_sleep} days old")
                
        if not self.biometric_history:
            add_gap('all', "No biometric history available")
            
        if not self.training_history:
            add_gap('training', "No training history available")


# =============================================================================
# Report Generator
# =============================================================================

class CoachBriefReport:
    """Generates the coach brief PDF report."""
    
    def __init__(self, data: CoachBriefData, output_path: Path):
        self.data = data
        self.output_path = output_path
        
    def generate(self):
        """Generate the complete PDF report."""
        if not HAS_MATPLOTLIB:
            raise RuntimeError("matplotlib required for PDF generation")
            
        with PdfPages(self.output_path) as pdf:
            self._page_summary(pdf)
            self._page_biometrics(pdf)
            self._page_training(pdf)
            
        return self.output_path
    
    def _page_summary(self, pdf: PdfPages):
        """Page 1: Executive summary."""
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
        fig.suptitle(
            f'Coach Brief - {self.data.report_date.strftime("%A, %B %d, %Y")}',
            fontsize=16, fontweight='bold', y=0.98
        )
        
        s = self.data.snapshot or {}
        
        # Quadrant 1: Today's readiness
        ax = axes[0, 0]
        ax.set_title('Today\'s Readiness', fontweight='bold', loc='left')
        ax.axis('off')
        
        metrics = [
            ('HRV', s.get('today_hrv'), 'ms', s.get('hrv_7d_avg')),
            ('RHR', s.get('today_rhr'), 'bpm', s.get('rhr_7d_avg')),
            ('Sleep', s.get('today_sleep_hours'), 'hrs', None),
            ('Recovery', s.get('today_recovery'), '%', None),
        ]
        
        y = 0.9
        for name, value, unit, avg in metrics:
            if value is not None:
                text = f"{name}: {value:.0f} {unit}"
                if avg:
                    diff = value - avg
                    arrow = '↑' if diff > 0 else '↓' if diff < 0 else '→'
                    text += f" ({arrow} vs 7d avg {avg:.0f})"
                color = COLORS['text']
            else:
                text = f"{name}: --"
                color = COLORS['secondary']
            ax.text(0.05, y, text, fontsize=12, color=color, transform=ax.transAxes)
            y -= 0.2
            
        # Quadrant 2: Training load
        ax = axes[0, 1]
        ax.set_title('Training Load', fontweight='bold', loc='left')
        ax.axis('off')
        
        acwr = s.get('acwr')
        if acwr:
            color = COLORS['success'] if 0.8 <= acwr <= 1.3 else COLORS['warning'] if 0.5 <= acwr <= 1.5 else COLORS['danger']
            ax.text(0.05, 0.8, f"ACWR: {acwr:.2f}", fontsize=14, color=color, transform=ax.transAxes, fontweight='bold')
            ax.text(0.05, 0.6, self._acwr_interpretation(acwr), fontsize=10, color=COLORS['secondary'], transform=ax.transAxes)
        else:
            ax.text(0.05, 0.8, "ACWR: Insufficient data", fontsize=12, color=COLORS['secondary'], transform=ax.transAxes)
            
        workouts_7d = s.get('workouts_7d', 0)
        ax.text(0.05, 0.4, f"Workouts this week: {workouts_7d}", fontsize=12, transform=ax.transAxes)
        
        # Quadrant 3: Trends summary
        ax = axes[1, 0]
        ax.set_title('Trend Indicators', fontweight='bold', loc='left')
        ax.axis('off')
        
        hrv_trend = s.get('hrv_trend_pct')
        rhr_trend = s.get('rhr_trend_pct')
        
        y = 0.8
        if hrv_trend is not None:
            arrow = '↑' if hrv_trend > 0 else '↓' if hrv_trend < 0 else '→'
            color = COLORS['success'] if hrv_trend > 5 else COLORS['danger'] if hrv_trend < -5 else COLORS['text']
            ax.text(0.05, y, f"HRV: {arrow} {abs(hrv_trend):.1f}% vs last week", fontsize=12, color=color, transform=ax.transAxes)
            y -= 0.2
            
        if rhr_trend is not None:
            # For RHR, we inverted in the view (lower is better)
            arrow = '↓' if rhr_trend > 0 else '↑' if rhr_trend < 0 else '→'
            color = COLORS['success'] if rhr_trend > 2 else COLORS['danger'] if rhr_trend < -2 else COLORS['text']
            ax.text(0.05, y, f"RHR: {arrow} {abs(rhr_trend):.1f}% vs last week", fontsize=12, color=color, transform=ax.transAxes)
            
        # Quadrant 4: Data gaps / alerts
        ax = axes[1, 1]
        ax.set_title('Data Quality & Alerts', fontweight='bold', loc='left')
        ax.axis('off')
        
        y = 0.9
        
        # Show unexplained gaps first (warnings)
        if self.data.data_gaps:
            for gap in self.data.data_gaps[:2]:  # Max 2 unexplained
                ax.text(0.05, y, f"! {gap}", fontsize=10, color=COLORS['danger'], transform=ax.transAxes)
                y -= 0.12
        
        # Show explained gaps (info, not warnings)
        if self.data.explained_gaps:
            for gap in self.data.explained_gaps[:2]:  # Max 2 explained
                msg = gap['message']
                reason = gap.get('reason', 'noted')
                ax.text(0.05, y, f"* {msg} ({reason})", fontsize=9, color=COLORS['secondary'], transform=ax.transAxes)
                y -= 0.12
        
        # Show active annotations (context)
        if self.data.annotations:
            for a in self.data.annotations[:2]:
                if a.get('reason_code') == 'expected':
                    label = a.get('explanation', '')[:60]
                    ax.text(0.05, y, f"i {label}...", fontsize=8, color=COLORS['primary'], transform=ax.transAxes)
                    y -= 0.12
        
        if not self.data.data_gaps and not self.data.explained_gaps:
            ax.text(0.05, 0.8, "All data current", fontsize=12, color=COLORS['success'], transform=ax.transAxes)
            
        # Add completeness at bottom
        completeness = s.get('hrv_7d_completeness', 0)
        ax.text(0.05, 0.1, f"7-day data completeness: {completeness:.0f}%", fontsize=9, color=COLORS['secondary'], transform=ax.transAxes)
            
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        pdf.savefig(fig)
        plt.close()
        
    def _page_biometrics(self, pdf: PdfPages):
        """Page 2: Biometric trends charts."""
        if not self.data.biometric_history:
            return
            
        fig, axes = plt.subplots(3, 1, figsize=(11, 8.5))
        fig.suptitle('Biometric Trends (90 days)', fontsize=14, fontweight='bold', y=0.98)
        
        dates = [row['reading_date'] for row in self.data.biometric_history]
        
        # HRV chart
        ax = axes[0]
        hrv_values = [row['hrv_ms'] for row in self.data.biometric_history]
        hrv_7d = [row['hrv_7d_avg'] for row in self.data.biometric_history]
        hrv_30d = [row['hrv_30d_avg'] for row in self.data.biometric_history]
        
        if any(v is not None for v in hrv_values):
            ax.scatter(dates, hrv_values, alpha=0.4, s=20, color=COLORS['primary'], label='Daily')
            ax.plot(dates, hrv_7d, color=COLORS['primary'], linewidth=2, label='7-day avg')
            ax.plot(dates, hrv_30d, color=COLORS['secondary'], linewidth=1.5, linestyle='--', label='30-day avg')
            ax.set_ylabel('HRV (ms)')
            ax.legend(loc='upper left', fontsize=8)
            ax.set_title('Heart Rate Variability', loc='left', fontsize=10)
        else:
            ax.text(0.5, 0.5, 'No HRV data available', ha='center', va='center', transform=ax.transAxes)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        
        # RHR chart
        ax = axes[1]
        rhr_values = [row['rhr_bpm'] for row in self.data.biometric_history]
        rhr_7d = [row['rhr_7d_avg'] for row in self.data.biometric_history]
        
        if any(v is not None for v in rhr_values):
            ax.scatter(dates, rhr_values, alpha=0.4, s=20, color=COLORS['danger'], label='Daily')
            ax.plot(dates, rhr_7d, color=COLORS['danger'], linewidth=2, label='7-day avg')
            ax.set_ylabel('RHR (bpm)')
            ax.legend(loc='upper left', fontsize=8)
            ax.set_title('Resting Heart Rate', loc='left', fontsize=10)
        else:
            ax.text(0.5, 0.5, 'No RHR data available', ha='center', va='center', transform=ax.transAxes)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        
        # Sleep chart
        ax = axes[2]
        sleep_values = [row['sleep_hours'] for row in self.data.biometric_history]
        
        if any(v is not None for v in sleep_values):
            ax.bar(dates, sleep_values, alpha=0.6, color=COLORS['secondary'], width=0.8)
            ax.axhline(y=7, color=COLORS['success'], linestyle='--', alpha=0.5, label='7hr target')
            ax.axhline(y=8, color=COLORS['success'], linestyle='--', alpha=0.3, label='8hr optimal')
            ax.set_ylabel('Sleep (hours)')
            ax.set_title('Sleep Duration', loc='left', fontsize=10)
            ax.legend(loc='upper left', fontsize=8)
        else:
            ax.text(0.5, 0.5, 'No sleep data available', ha='center', va='center', transform=ax.transAxes)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        pdf.savefig(fig)
        plt.close()
        
    def _page_training(self, pdf: PdfPages):
        """Page 3: Training load trends."""
        if not self.data.training_history:
            return
            
        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5))
        fig.suptitle('Training Load Trends (12 weeks)', fontsize=14, fontweight='bold', y=0.98)
        
        weeks = [row['week_start'] for row in self.data.training_history]
        
        # Volume chart
        ax = axes[0]
        volume = [row['volume_lbs'] or 0 for row in self.data.training_history]
        volume_avg = [row['volume_4wk_avg'] or 0 for row in self.data.training_history]
        
        bars = ax.bar(weeks, volume, alpha=0.7, color=COLORS['primary'], width=5, label='Weekly Volume')
        ax.plot(weeks, volume_avg, color=COLORS['danger'], linewidth=2, marker='o', markersize=4, label='4-week avg')
        ax.set_ylabel('Volume (lbs)')
        ax.legend(loc='upper left')
        ax.set_title('Weekly Training Volume', loc='left', fontsize=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        
        # Workouts per week
        ax = axes[1]
        workouts = [row['workouts'] or 0 for row in self.data.training_history]
        
        ax.bar(weeks, workouts, alpha=0.7, color=COLORS['secondary'], width=5)
        ax.axhline(y=3, color=COLORS['success'], linestyle='--', alpha=0.5, label='3x/week target')
        ax.set_ylabel('Workouts')
        ax.set_xlabel('Week Starting')
        ax.set_title('Workout Frequency', loc='left', fontsize=10)
        ax.legend(loc='upper left')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        pdf.savefig(fig)
        plt.close()
        
    def _acwr_interpretation(self, acwr: float) -> str:
        """Return interpretation of ACWR value."""
        if acwr < 0.8:
            return "Undertraining - consider increasing load"
        elif acwr <= 1.0:
            return "Sweet spot - optimal adaptation zone"
        elif acwr <= 1.3:
            return "Productive overreach - monitor recovery"
        elif acwr <= 1.5:
            return "Caution - elevated injury risk"
        else:
            return "Warning - high injury risk, reduce load"


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Generate Coach Brief PDF Report')
    parser.add_argument('--date', type=str, help='Report date (YYYY-MM-DD), default: today')
    parser.add_argument('--output', type=str, help='Output path for PDF')
    parser.add_argument('--dry-run', action='store_true', help='Preview without generating PDF')
    args = parser.parse_args()
    
    # Determine report date
    if args.date:
        report_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        report_date = datetime.now().date()
        
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = REPORT_DIR / f"coach_brief_{report_date.strftime('%Y%m%d')}.pdf"
        
    print(f"Generating coach brief for {report_date}...")
    
    # Connect and load data
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        data = CoachBriefData(conn, report_date).load()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)
        
    # Report on data availability
    print(f"\nData loaded:")
    print(f"  - Snapshot: {'Yes' if data.snapshot else 'No'}")
    print(f"  - Biometric history: {len(data.biometric_history) if data.biometric_history else 0} days")
    print(f"  - Training history: {len(data.training_history) if data.training_history else 0} weeks")
    print(f"  - Active annotations: {len(data.annotations) if data.annotations else 0}")
    
    if data.data_gaps:
        print(f"\nUnexplained data gaps:")
        for gap in data.data_gaps:
            print(f"  ! {gap}")
    
    if data.explained_gaps:
        print(f"\nExplained gaps (annotated):")
        for gap in data.explained_gaps:
            print(f"  * {gap['message']} ({gap.get('reason', 'noted')})")
    
    if data.annotations:
        print(f"\nActive annotations:")
        for a in data.annotations:
            status = "ongoing" if a.get('is_ongoing') else f"until {a.get('date_range_end')}"
            print(f"  - [{a.get('reason_code')}] {a.get('target_metric', 'general')}: {a.get('explanation', '')[:60]}... ({status})")
    
    if not data.data_gaps and not data.explained_gaps:
        print(f"\n✓ No data quality issues detected")
            
    if args.dry_run:
        print("\nDry run - no PDF generated")
        return
        
    if not HAS_MATPLOTLIB:
        print("\nError: matplotlib required for PDF generation")
        print("Install with: pip install matplotlib")
        sys.exit(1)
        
    # Generate report
    report = CoachBriefReport(data, output_path)
    output_file = report.generate()
    
    print(f"\n✓ Report generated: {output_file}")
    
    conn.close()


if __name__ == '__main__':
    main()
