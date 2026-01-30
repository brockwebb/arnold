"""Postgres client for Arnold Memory MCP analytics integration.

Consolidates analytics data into load_briefing per architectural decision
to provide one-call coaching context.

ADR-001: Postgres owns measurements/facts, Neo4j owns relationships.
This client queries Postgres analytics for the consolidated briefing.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PostgresAnalyticsClient:
    """Postgres client for analytics data in briefings."""

    def __init__(self):
        """Initialize Postgres connection."""
        self.dsn = os.environ.get(
            "POSTGRES_DSN",
            os.environ.get(
                "DATABASE_URI",
                "postgresql://brock@localhost:5432/arnold_analytics"
            )
        )
        self._conn = None

    @property
    def conn(self):
        """Lazy connection with autocommit to avoid transaction state issues."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = True  # Prevent "transaction aborted" cascading failures
        return self._conn

    def close(self):
        """Close connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    def _decimal_to_float(self, d: Dict) -> Dict:
        """Convert Decimal types to float for JSON serialization."""
        return {
            k: float(v) if isinstance(v, Decimal) else v
            for k, v in d.items()
        }

    def _calc_trend(self, values: list, threshold: float = 0.05) -> str:
        """Calculate trend from list of values."""
        if len(values) < 3:
            return "insufficient_data"
        
        first_half = sum(values[:len(values)//2]) / (len(values)//2)
        second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
        
        if first_half == 0:
            return "stable"
        
        pct_change = (second_half - first_half) / first_half
        
        if pct_change > threshold:
            return "improving"
        elif pct_change < -threshold:
            return "declining"
        else:
            return "stable"

    def get_readiness_snapshot(self, target_date: str = None) -> Dict[str, Any]:
        """
        Get readiness data for briefing.
        
        Returns HRV (with comparisons), sleep, RHR, and coaching notes.
        """
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")
        
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        
        result = {
            "hrv": None,
            "sleep": None,
            "resting_hr": None,
            "data_completeness": 0,
            "coaching_notes": []
        }
        coaching_notes = []
        
        try:
            # Get today's biometrics
            # Note: sleep_deep_min, sleep_rem_min, sleep_quality_pct not in daily_status view
            cur.execute("""
                SELECT date, hrv_ms, rhr_bpm, sleep_hours, data_coverage
                FROM daily_status
                WHERE date = %s
            """, [target_date])
            today = cur.fetchone()
            
            # Get 7-day averages
            cur.execute("""
                SELECT 
                    AVG(hrv_ms) as hrv_7d,
                    AVG(sleep_hours) as sleep_7d,
                    AVG(rhr_bpm) as rhr_7d
                FROM readiness_daily
                WHERE reading_date BETWEEN %s::date - INTERVAL '7 days' AND %s::date - INTERVAL '1 day'
            """, [target_date, target_date])
            seven_day = cur.fetchone()
            
            # Get 30-day baseline HRV
            cur.execute("""
                SELECT AVG(hrv_ms) as hrv_baseline
                FROM readiness_daily
                WHERE reading_date BETWEEN %s::date - INTERVAL '30 days' AND %s::date - INTERVAL '1 day'
                  AND hrv_ms IS NOT NULL
            """, [target_date, target_date])
            baseline = cur.fetchone()
            
            # Get recent HRV trend
            cur.execute("""
                SELECT hrv_ms
                FROM readiness_daily
                WHERE reading_date <= %s AND hrv_ms IS NOT NULL
                ORDER BY reading_date DESC
                LIMIT 7
            """, [target_date])
            hrv_trend_data = cur.fetchall()
            
            if today:
                # Count data sources
                coverage = today.get('data_coverage') or ''
                sources = 0
                if 'training' in coverage or 'full' in coverage:
                    sources += 1
                if 'readiness' in coverage or 'full' in coverage:
                    sources += 1
                if today.get('hrv_ms'):
                    sources += 1
                if today.get('sleep_hours'):
                    sources += 1
                result["data_completeness"] = sources
                
                # HRV
                if today.get('hrv_ms'):
                    hrv_val = float(today['hrv_ms'])
                    hrv_7d = float(seven_day['hrv_7d']) if seven_day and seven_day['hrv_7d'] else None
                    hrv_baseline = float(baseline['hrv_baseline']) if baseline and baseline['hrv_baseline'] else None
                    
                    hrv_values = [float(r['hrv_ms']) for r in hrv_trend_data if r['hrv_ms']]
                    trend = self._calc_trend(list(reversed(hrv_values)))
                    
                    result["hrv"] = {
                        "value": round(hrv_val),
                        "avg_7d": round(hrv_7d) if hrv_7d else None,
                        "avg_30d": round(hrv_baseline) if hrv_baseline else None,
                        "vs_7d_pct": round((hrv_val - hrv_7d) / hrv_7d * 100) if hrv_7d else None,
                        "trend": trend
                    }
                    
                    if trend == "declining" and len(hrv_values) >= 3:
                        coaching_notes.append("HRV declining over recent days")
                    if hrv_7d and hrv_val < hrv_7d * 0.85:
                        coaching_notes.append(f"HRV {round(hrv_val)} is {round((1 - hrv_val/hrv_7d) * 100)}% below 7-day avg")
                
                # Sleep
                # Note: sleep_deep_min, sleep_rem_min, sleep_quality_pct not synced yet
                if today.get('sleep_hours'):
                    sleep_hrs = float(today['sleep_hours'])

                    result["sleep"] = {
                        "hours": round(sleep_hrs, 1),
                        "quality_pct": None,  # Not available in daily_status
                        "deep_pct": None      # Not available in daily_status
                    }

                    if sleep_hrs < 6:
                        coaching_notes.append(f"Sleep {round(sleep_hrs, 1)}hrs - under 6hr recovery threshold")
                    elif sleep_hrs < 7:
                        coaching_notes.append(f"Sleep {round(sleep_hrs, 1)}hrs - below 7hr optimal")
                
                # Resting HR
                if today.get('rhr_bpm'):
                    result["resting_hr"] = round(float(today['rhr_bpm']))
            
            result["coaching_notes"] = coaching_notes
            
        except Exception as e:
            logger.error(f"Error getting readiness: {e}")
        
        return result

    def get_training_load_summary(self, days: int = 28) -> Dict[str, Any]:
        """
        Get training load summary for briefing.
        
        Returns ACWR, volume trends, pattern gaps.
        """
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        logger.debug(f"get_training_load_summary: querying {start_date} to {end_date}")
        logger.debug(f"DSN: {self.dsn}")
        
        result = {
            "workouts": 0,
            "total_sets": 0,
            "acwr": None,
            "pattern_gaps": [],
            "coaching_notes": []
        }
        coaching_notes = []
        
        try:
            cur = self.conn.cursor(cursor_factory=RealDictCursor)
            logger.debug(f"Postgres connection established, closed={self.conn.closed}")
            
            # Test connection
            cur.execute("SELECT 1 as test")
            test_result = cur.fetchone()
            logger.debug(f"Connection test: {test_result}")
            
            # Overall summary
            logger.debug("Executing workout_summaries query...")
            cur.execute("""
                SELECT 
                    COUNT(*) as workouts,
                    COALESCE(SUM(set_count), 0) as total_sets,
                    COALESCE(SUM(total_volume_lbs), 0) as total_volume
                FROM workout_summaries
                WHERE workout_date BETWEEN %s AND %s
            """, [start_date, end_date])
            summary = cur.fetchone()
            logger.debug(f"workout_summaries result: {summary}")
            
            if summary:
                result["workouts"] = summary['workouts'] or 0
                result["total_sets"] = summary['total_sets'] or 0
            
            # ACWR - prefer volume-based (from training_monotony_strain) since TRIMP pipeline is stale
            cur.execute("""
                SELECT acwr as volume_acwr
                FROM training_monotony_strain
                ORDER BY workout_date DESC
                LIMIT 1
            """)
            volume_acwr_row = cur.fetchone()
            
            cur.execute("""
                SELECT trimp_acwr
                FROM trimp_acwr
                WHERE daily_trimp > 0
                ORDER BY session_date DESC
                LIMIT 1
            """)
            trimp_acwr_row = cur.fetchone()
            
            # Use volume-based as primary, trimp as fallback
            volume_acwr_val = float(volume_acwr_row['volume_acwr']) if volume_acwr_row and volume_acwr_row['volume_acwr'] else None
            trimp_acwr_val = float(trimp_acwr_row['trimp_acwr']) if trimp_acwr_row and trimp_acwr_row['trimp_acwr'] else None
            
            primary_acwr = volume_acwr_val or trimp_acwr_val
            if primary_acwr:
                zone = "high_risk" if primary_acwr > 1.5 else "optimal" if 0.8 <= primary_acwr <= 1.3 else "low"
                result["acwr"] = {
                    "value": round(primary_acwr, 2),
                    "zone": zone,
                    "source": "volume" if volume_acwr_val else "trimp"
                }
                
                if primary_acwr > 1.5:
                    coaching_notes.append(f"ACWR {round(primary_acwr, 2)} (volume) - elevated injury risk")
                elif primary_acwr < 0.8:
                    coaching_notes.append(f"ACWR {round(primary_acwr, 2)} (volume) - can increase load")
            
            # Pattern gaps (no work in 10+ days)
            cur.execute("""
                SELECT DISTINCT pattern
                FROM workout_summaries,
                     jsonb_array_elements_text(patterns) as pattern
                WHERE workout_date >= CURRENT_DATE - INTERVAL '10 days'
            """)
            recent_patterns = {r['pattern'] for r in cur.fetchall()}
            
            core_patterns = {"Hip Hinge", "Squat", "Horizontal Pull", "Horizontal Push", 
                           "Vertical Pull", "Vertical Push"}
            missing = core_patterns - recent_patterns
            
            if missing:
                result["pattern_gaps"] = sorted(list(missing))
                coaching_notes.append(f"Pattern gaps (10d): {', '.join(sorted(missing))}")
            
            result["coaching_notes"] = coaching_notes
            
        except Exception as e:
            logger.error(f"Error getting training load: {e}", exc_info=True)
        
        return result

    def get_hrr_trend_summary(self, days: int = 28) -> Dict[str, Any]:
        """
        Get HRR trend summary for briefing.
        
        Returns per-stratum status and any recent alerts.
        """
        import numpy as np
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        
        result = {
            "intervals": 0,
            "strata": {},
            "has_alerts": False,
            "coaching_notes": []
        }
        coaching_notes = []
        
        try:
            # Query actionable intervals
            cur.execute("""
                SELECT 
                    start_time,
                    stratum,
                    hrr60_abs,
                    weighted_hrr60,
                    confidence
                FROM hr_recovery_intervals
                WHERE actionable = true
                  AND start_time >= %s
                  AND start_time <= %s
                ORDER BY start_time
            """, [start_date, end_date])
            rows = cur.fetchall()
            
            if not rows:
                return result
            
            result["intervals"] = len(rows)
            
            # Group by stratum
            strata_data = {}
            for r in rows:
                strat = r['stratum']
                if strat not in strata_data:
                    strata_data[strat] = []
                strata_data[strat].append(r)
            
            # Analyze each stratum
            for strat, data in strata_data.items():
                if len(data) < 5:
                    result["strata"][strat] = {
                        "intervals": len(data),
                        "status": "insufficient_data"
                    }
                    continue
                
                hrr_vals = [float(d['hrr60_abs']) for d in data if d['hrr60_abs']]
                if len(hrr_vals) < 5:
                    continue
                
                baseline = np.mean(hrr_vals)
                sd = np.std(hrr_vals)
                te = sd / np.sqrt(2)
                sdd = 2.77 * te
                
                # Recent vs prior
                recent_n = min(7, len(hrr_vals) // 2)
                if recent_n >= 3:
                    recent_avg = np.mean(hrr_vals[-recent_n:])
                    prior_avg = np.mean(hrr_vals[:-recent_n])
                    trend_pct = round((recent_avg / prior_avg - 1) * 100) if prior_avg > 0 else 0
                    trend = "declining" if trend_pct < -10 else "improving" if trend_pct > 10 else "stable"
                else:
                    recent_avg = baseline
                    trend_pct = 0
                    trend = "stable"
                
                # Check for alerts (recent values below warning threshold)
                warning_threshold = baseline - 1.0 * sdd
                recent_below_warning = sum(1 for v in hrr_vals[-7:] if v < warning_threshold)
                has_alert = recent_below_warning >= 2
                
                result["strata"][strat] = {
                    "intervals": len(data),
                    "baseline_hrr60": round(baseline, 1),
                    "current_avg": round(recent_avg, 1),
                    "trend": trend,
                    "trend_pct": trend_pct,
                    "has_alert": has_alert
                }
                
                if has_alert:
                    result["has_alerts"] = True
                    coaching_notes.append(f"{strat} HRR below warning threshold - recovery may be compromised")
                elif trend == "declining":
                    coaching_notes.append(f"{strat} HRR declining {abs(trend_pct)}%")
            
            result["coaching_notes"] = coaching_notes
            
        except Exception as e:
            logger.error(f"Error getting HRR trend: {e}")
        
        return result

    def get_red_flags(self) -> Dict[str, Any]:
        """
        Get red flags and data observations for briefing.
        
        Returns data gaps, concerning trends, and active annotations.
        KEY: Annotations SUPPRESS alerts for gaps they explain.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        
        result = {
            "observations": [],
            "annotations": [],
            "coaching_notes": []
        }
        coaching_notes = []
        
        try:
            # FIRST: Load annotations to know what gaps are already explained
            # For ongoing annotations (date_range_end IS NULL), include all active
            # For bounded annotations, include if they ended recently
            cur.execute("""
                SELECT 
                    id, annotation_date, date_range_end, target_type, target_metric,
                    reason_code, explanation
                FROM data_annotations
                WHERE is_active = true
                  AND (
                      date_range_end IS NULL  -- ongoing indefinitely
                      OR
                      date_range_end >= %s    -- ended recently
                  )
                ORDER BY annotation_date DESC
                LIMIT 10
            """, [seven_days_ago])
            
            annotations = cur.fetchall()
            
            # Build set of metrics covered by annotations
            annotated_metrics = set()
            for a in annotations:
                metric = a['target_metric']
                if metric:
                    annotated_metrics.add(metric.lower())
                    # 'all' covers everything
                    if metric.lower() == 'all':
                        annotated_metrics.update(['hrv', 'sleep', 'rhr', 'training'])
                
                result["annotations"].append({
                    "date": str(a['annotation_date']),
                    "target": f"{a['target_type']}/{a['target_metric']}",
                    "reason": a['reason_code'],
                    "explanation": a['explanation'][:100] if a['explanation'] else None
                })
            
            # Check HRV gap - only alert if NOT covered by annotation
            cur.execute("""
                SELECT MAX(reading_date) as last_date
                FROM readiness_daily
                WHERE hrv_ms IS NOT NULL
            """)
            last_hrv = cur.fetchone()
            
            if last_hrv and last_hrv['last_date']:
                days_since = (datetime.now().date() - last_hrv['last_date']).days
                if days_since > 2:
                    is_annotated = 'hrv' in annotated_metrics
                    result["observations"].append({
                        "type": "data_gap",
                        "metric": "hrv",
                        "days_since": days_since,
                        "annotated": is_annotated
                    })
                    if not is_annotated:
                        coaching_notes.append(f"No HRV data for {days_since} days")
            
            # Check sleep gap - only alert if NOT covered by annotation
            cur.execute("""
                SELECT MAX(reading_date) as last_date
                FROM readiness_daily
                WHERE sleep_hours IS NOT NULL
            """)
            last_sleep = cur.fetchone()
            
            if last_sleep and last_sleep['last_date']:
                days_since = (datetime.now().date() - last_sleep['last_date']).days
                if days_since > 2:
                    is_annotated = 'sleep' in annotated_metrics
                    result["observations"].append({
                        "type": "data_gap",
                        "metric": "sleep",
                        "days_since": days_since,
                        "annotated": is_annotated
                    })
                    if not is_annotated:
                        coaching_notes.append(f"No sleep data for {days_since} days")
            
            result["coaching_notes"] = coaching_notes
            
        except Exception as e:
            logger.error(f"Error getting red flags: {e}")
        
        return result

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Get diagnostic info for debugging connection issues.
        """
        diag = {
            "dsn": self.dsn,
            "dsn_source": "unknown",
            "connection_ok": False,
            "test_query": None,
            "workout_summaries_count": None,
            "error": None
        }
        
        # Determine DSN source
        if os.environ.get("POSTGRES_DSN"):
            diag["dsn_source"] = "POSTGRES_DSN env var"
        elif os.environ.get("DATABASE_URI"):
            diag["dsn_source"] = "DATABASE_URI env var"
        else:
            diag["dsn_source"] = "default fallback"
        
        try:
            cur = self.conn.cursor(cursor_factory=RealDictCursor)
            diag["connection_ok"] = True
            
            cur.execute("SELECT 1 as test")
            diag["test_query"] = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) as cnt FROM workout_summaries")
            diag["workout_summaries_count"] = cur.fetchone()
            
        except Exception as e:
            diag["error"] = str(e)
            logger.error(f"Diagnostics error: {e}", exc_info=True)
        
        return diag

    def get_analytics_for_briefing(self) -> Dict[str, Any]:
        """
        Get all analytics data for consolidated briefing.
        
        Returns:
            - readiness: HRV, sleep, RHR with comparisons
            - training_load: ACWR, volume, pattern gaps
            - hrr: Trend summary and alerts
            - red_flags: Data gaps, annotations
            - combined coaching_notes
        """
        readiness = self.get_readiness_snapshot()
        training_load = self.get_training_load_summary()
        hrr = self.get_hrr_trend_summary()
        red_flags = self.get_red_flags()
        
        # Combine all coaching notes (deduplicated)
        all_notes = []
        seen = set()
        for source in [readiness, training_load, hrr, red_flags]:
            for note in source.get("coaching_notes", []):
                if note not in seen:
                    all_notes.append(note)
                    seen.add(note)
        
        # Get diagnostics for debugging
        diagnostics = self.get_diagnostics()
        
        return {
            "readiness": {
                "hrv": readiness.get("hrv"),
                "sleep": readiness.get("sleep"),
                "resting_hr": readiness.get("resting_hr"),
                "data_completeness": readiness.get("data_completeness", 0)
            },
            "training_load": {
                "workouts_28d": training_load.get("workouts", 0),
                "total_sets_28d": training_load.get("total_sets", 0),
                "acwr": training_load.get("acwr"),
                "pattern_gaps": training_load.get("pattern_gaps", [])
            },
            "hrr": {
                "intervals": hrr.get("intervals", 0),
                "strata": hrr.get("strata", {}),
                "has_alerts": hrr.get("has_alerts", False)
            },
            "annotations": red_flags.get("annotations", []),
            "data_gaps": red_flags.get("observations", []),
            "coaching_notes": all_notes,
            "_diagnostics": diagnostics
        }
