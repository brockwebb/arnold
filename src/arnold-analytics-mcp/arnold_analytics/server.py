"""
Arnold Analytics MCP Server

Codename: T-1000

This is Arnold's eyes into the data. These tools are called by Arnold
automatically as part of coaching, not by the athlete directly.

Tools return coaching-ready summaries, not raw data.

Database: Postgres (arnold_analytics)
"""

import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from dateutil import parser as date_parser
import psycopg2
from psycopg2.extras import RealDictCursor
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Postgres connection
PG_URI = os.environ.get(
    "DATABASE_URI",
    "postgresql://brock@localhost:5432/arnold_analytics"
)

server = Server("arnold-analytics")


def get_db():
    """Get database connection."""
    return psycopg2.connect(PG_URI, cursor_factory=RealDictCursor)


def parse_date(date_str: str) -> str:
    """Parse date string, supporting 'today', 'yesterday', '7d', '30d', etc."""
    if date_str == "today":
        return datetime.now().strftime("%Y-%m-%d")
    elif date_str == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_str.endswith("d"):
        days = int(date_str[:-1])
        return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        return date_parser.parse(date_str).strftime("%Y-%m-%d")


def calc_trend(values: list, threshold: float = 0.05) -> str:
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


def decimal_default(obj):
    """JSON serializer for Decimal types."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def get_annotations_for_period(cur, start_date: str, end_date: str = None):
    """
    Get active annotations that cover a date range.
    
    Returns annotations as facts - does NOT suppress or filter.
    The intelligence layer (Arnold) interprets these.
    """
    if end_date is None:
        end_date = start_date
    
    cur.execute("""
        SELECT 
            id, annotation_date, date_range_end, target_type, target_metric,
            reason_code, explanation, tags
        FROM data_annotations
        WHERE is_active = true
          AND (
              -- Single date annotation covers our range
              (date_range_end IS NULL AND annotation_date BETWEEN %s AND %s)
              OR
              -- Range annotation overlaps our range  
              (date_range_end IS NOT NULL AND annotation_date <= %s AND date_range_end >= %s)
          )
        ORDER BY annotation_date DESC
    """, [start_date, end_date, end_date, start_date])
    
    return cur.fetchall()


@server.list_tools()
async def list_tools():
    """List available analytics tools."""
    return [
        Tool(
            name="get_hrr_trend",
            description="""Get HRR (Heart Rate Recovery) trend analysis with EWMA/CUSUM detection.
            
Returns per-stratum baselines, recent trends, and any warning/action alerts.
Uses confidence-weighted HRR60 values for robust trend detection.
Key for assessing cardiovascular recovery and overtraining risk.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days of history to analyze (default: 28)",
                        "default": 28
                    },
                    "stratum": {
                        "type": "string",
                        "description": "Filter to specific stratum: STRENGTH, ENDURANCE, or OTHER (default: all)",
                        "enum": ["STRENGTH", "ENDURANCE", "OTHER"]
                    }
                }
            }
        ),
        Tool(
            name="get_readiness_snapshot",
            description="""Get current readiness data with computed insights.
            
Returns HRV (with 7d/30d comparisons), sleep, resting HR, recent load, ACWR.
Includes coaching_notes with pre-computed threshold checks.
Reports data completeness (0-4).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date to check (default: today). Supports 'today', 'yesterday', or 'YYYY-MM-DD'",
                        "default": "today"
                    }
                }
            }
        ),
        Tool(
            name="get_training_load",
            description="""Get training load summary for programming decisions.
            
Returns workout count, volume trends, pattern distribution, and identifies
gaps in movement patterns. Used for overtraining assessment and balance.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze (default: 28)",
                        "default": 28
                    }
                }
            }
        ),
        Tool(
            name="get_exercise_history",
            description="""Get progression history for a specific exercise.
            
Returns PR, current working weights, estimated 1RM, and distance to goal.
Used when programming specific lifts or assessing progress.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "exercise": {
                        "type": "string",
                        "description": "Exercise name (fuzzy matched, e.g., 'deadlift', 'chin-up')"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Days of history to include (default: 180)",
                        "default": 180
                    }
                },
                "required": ["exercise"]
            }
        ),
        Tool(
            name="check_red_flags",
            description="""Get observations and annotations for Arnold to synthesize.
            
Reports: HRV trend, data gaps, sleep stats, ACWR, pattern coverage.
Includes active annotations covering recent period as context.
No suppression - Arnold sees all data and decides what to surface.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_sleep_analysis",
            description="""Analyze sleep patterns when fatigue or recovery is a concern.
            
Returns averages, trends, comparison to baseline, and identifies
problematic patterns.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to analyze (default: 14)",
                        "default": 14
                    }
                }
            }
        ),
        Tool(
            name="run_sync",
            description="""Run the data sync pipeline to pull latest data from all sources.
            
Triggers sync from Ultrahuman, Polar, FIT files, etc. Returns sync status and any errors.
Use when user asks to refresh data or when data seems stale.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific steps to run (default: all). Options: polar, ultrahuman, fit, apple, neo4j, annotations, clean, refresh"
                    }
                }
            }
        ),
        Tool(
            name="get_sync_history",
            description="""Get recent sync history to check for data pipeline issues.
            
Returns last N sync runs with status, steps run, and any errors.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent syncs to return (default: 5)",
                        "default": 5
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    
    if name == "get_hrr_trend":
        return await get_hrr_trend(
            arguments.get("days", 28),
            arguments.get("stratum")
        )
    
    elif name == "get_readiness_snapshot":
        return await get_readiness_snapshot(arguments.get("date", "today"))
    
    elif name == "get_training_load":
        return await get_training_load(arguments.get("days", 28))
    
    elif name == "get_exercise_history":
        return await get_exercise_history(
            arguments["exercise"],
            arguments.get("days", 180)
        )
    
    elif name == "check_red_flags":
        return await check_red_flags()
    
    elif name == "get_sleep_analysis":
        return await get_sleep_analysis(arguments.get("days", 14))
    
    elif name == "run_sync":
        return await run_sync(arguments.get("steps"))
    
    elif name == "get_sync_history":
        return await get_sync_history(arguments.get("limit", 5))
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def get_readiness_snapshot(date_str: str):
    """Get readiness snapshot - facts only, no interpretation.
    
    Reports biometric and training load data. Arnold interprets.
    """
    target_date = parse_date(date_str)
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get today's status from daily_status view
    cur.execute("""
        SELECT date, workout_name, workout_type, daily_sets, daily_volume_lbs,
               duration_min, avg_hr, trimp, edwards_trimp, intensity_factor,
               hrv_ms, rhr_bpm, sleep_hours, sleep_deep_min, sleep_rem_min,
               sleep_quality_pct, data_coverage
        FROM daily_status
        WHERE date = %s
    """, [target_date])
    today_row = cur.fetchone()
    
    # Get 7-day averages from readiness_daily
    cur.execute("""
        SELECT 
            AVG(hrv_ms) as hrv_7d,
            AVG(sleep_hours) as sleep_7d,
            AVG(rhr_bpm) as rhr_7d
        FROM readiness_daily
        WHERE reading_date BETWEEN %s::date - INTERVAL '7 days' AND %s::date - INTERVAL '1 day'
    """, [target_date, target_date])
    seven_day = cur.fetchone()
    
    # Get baseline (30-day) HRV
    cur.execute("""
        SELECT AVG(hrv_ms) as hrv_baseline
        FROM readiness_daily
        WHERE reading_date BETWEEN %s::date - INTERVAL '30 days' AND %s::date - INTERVAL '1 day'
          AND hrv_ms IS NOT NULL
    """, [target_date, target_date])
    baseline = cur.fetchone()
    
    # Get recent HRV trend (last 7 readings)
    cur.execute("""
        SELECT hrv_ms
        FROM readiness_daily
        WHERE reading_date <= %s AND hrv_ms IS NOT NULL
        ORDER BY reading_date DESC
        LIMIT 7
    """, [target_date])
    hrv_trend_data = cur.fetchall()
    
    # Get yesterday's training from training_load_daily
    cur.execute("""
        SELECT daily_sets, daily_volume, acwr
        FROM training_load_daily
        WHERE workout_date = %s::date - INTERVAL '1 day'
    """, [target_date])
    yesterday = cur.fetchone()
    
    # Get recent ACWR from trimp_acwr
    cur.execute("""
        SELECT trimp_acwr, daily_trimp
        FROM trimp_acwr
        WHERE session_date <= %s
        ORDER BY session_date DESC
        LIMIT 1
    """, [target_date])
    acwr_row = cur.fetchone()
    
    # Build response - facts only
    result = {
        "date": target_date,
        "hrv": None,
        "sleep": None,
        "resting_hr": None,
        "recent_load": None,
        "acwr": None,
        "data_completeness": 0,
        "data_sources": [],
        "missing": [],
        "coaching_notes": []  # Computed insights, not interpretation
    }
    
    coaching_notes = []
    
    if today_row:
        coverage = today_row['data_coverage'] or ''
        
        # Data sources based on coverage
        if 'training' in coverage or 'full' in coverage:
            result["data_sources"].append("training")
        if 'hr' in coverage or 'full' in coverage:
            result["data_sources"].append("hr")
        if 'readiness' in coverage or 'full' in coverage:
            result["data_sources"].append("readiness")
        
        # Calculate completeness
        result["data_completeness"] = len(result["data_sources"])
        
        # What's missing
        if 'training' not in coverage and 'full' not in coverage:
            result["missing"].append("training")
        if today_row['hrv_ms'] is None:
            result["missing"].append("hrv")
        if today_row['sleep_hours'] is None:
            result["missing"].append("sleep")
        
        # HRV - facts with comparisons
        if today_row['hrv_ms']:
            hrv_val = float(today_row['hrv_ms'])
            hrv_7d = float(seven_day['hrv_7d']) if seven_day and seven_day['hrv_7d'] else None
            hrv_baseline = float(baseline['hrv_baseline']) if baseline and baseline['hrv_baseline'] else None
            
            hrv_values = [float(r['hrv_ms']) for r in hrv_trend_data if r['hrv_ms']]
            trend = calc_trend(list(reversed(hrv_values)))
            
            result["hrv"] = {
                "value": round(hrv_val),
                "avg_7d": round(hrv_7d) if hrv_7d else None,
                "avg_30d": round(hrv_baseline) if hrv_baseline else None,
                "vs_7d_pct": round((hrv_val - hrv_7d) / hrv_7d * 100) if hrv_7d else None,
                "vs_30d_pct": round((hrv_val - hrv_baseline) / hrv_baseline * 100) if hrv_baseline else None,
                "trend": trend
            }
            
            # Computed insights (not suppressed - Arnold decides relevance)
            if trend == "declining" and len(hrv_values) >= 3:
                coaching_notes.append("HRV declining over recent days")
            if hrv_7d and hrv_val < hrv_7d * 0.85:
                coaching_notes.append(f"HRV {round(hrv_val)} is {round((1 - hrv_val/hrv_7d) * 100)}% below 7-day avg")
        
        # Sleep - facts only
        if today_row['sleep_hours']:
            sleep_hrs = float(today_row['sleep_hours'])
            total_min = sleep_hrs * 60
            deep_min = float(today_row['sleep_deep_min']) if today_row['sleep_deep_min'] else None
            deep_pct = round(deep_min / total_min * 100) if deep_min and total_min else None
            
            result["sleep"] = {
                "hours": round(sleep_hrs, 1),
                "quality_pct": float(today_row['sleep_quality_pct']) if today_row['sleep_quality_pct'] else None,
                "deep_pct": deep_pct
            }
            
            # Computed insights
            if sleep_hrs < 6:
                coaching_notes.append(f"Sleep {round(sleep_hrs, 1)}hrs - under 6hr recovery threshold")
            elif sleep_hrs < 7:
                coaching_notes.append(f"Sleep {round(sleep_hrs, 1)}hrs - below 7hr optimal")
        
        # Resting HR
        if today_row['rhr_bpm']:
            result["resting_hr"] = round(float(today_row['rhr_bpm']))
    
    # Recent load - facts only
    if yesterday:
        result["recent_load"] = {
            "yesterday_sets": yesterday['daily_sets'],
            "yesterday_volume_lbs": round(float(yesterday['daily_volume'])) if yesterday['daily_volume'] else None,
            "volume_acwr": round(float(yesterday['acwr']), 2) if yesterday['acwr'] else None
        }
    
    # ACWR - facts with zone classification
    if acwr_row and acwr_row['trimp_acwr']:
        acwr_val = float(acwr_row['trimp_acwr'])
        zone = "high_risk" if acwr_val > 1.5 else "optimal" if 0.8 <= acwr_val <= 1.3 else "low"
        result["acwr"] = {
            "trimp_based": round(acwr_val, 2),
            "zone": zone
        }
        
        # Computed insights (no suppression - Arnold has annotations for context)
        if acwr_val > 1.5:
            coaching_notes.append(f"ACWR {round(acwr_val, 2)} - elevated injury risk zone")
        elif acwr_val < 0.8:
            coaching_notes.append(f"ACWR {round(acwr_val, 2)} - detraining risk, can increase load")
    
    conn.close()
    
    result["coaching_notes"] = coaching_notes
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=decimal_default))]


async def get_training_load(days: int):
    """Get training load summary."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Overall summary from workout_summaries
    cur.execute("""
        SELECT 
            COUNT(*) as workouts,
            SUM(set_count) as total_sets,
            SUM(total_volume_lbs) as total_volume
        FROM workout_summaries
        WHERE workout_date BETWEEN %s AND %s
    """, [start_date, end_date])
    summary = cur.fetchone()
    
    # Weekly trend
    cur.execute("""
        SELECT 
            DATE_TRUNC('week', workout_date)::date as week_start,
            COUNT(*) as workouts,
            SUM(set_count) as total_sets,
            ROUND(SUM(total_volume_lbs) / 1000, 1) as volume_klbs
        FROM workout_summaries
        WHERE workout_date >= %s
        GROUP BY DATE_TRUNC('week', workout_date)
        ORDER BY week_start DESC
        LIMIT 8
    """, [start_date])
    weekly = cur.fetchall()
    
    # Pattern distribution from JSONB
    cur.execute("""
        SELECT 
            pattern,
            COUNT(*) as workout_count
        FROM workout_summaries,
             jsonb_array_elements_text(patterns) as pattern
        WHERE workout_date >= %s
        GROUP BY pattern
        ORDER BY workout_count DESC
    """, [start_date])
    patterns = cur.fetchall()
    
    # Find pattern gaps (no work in 10+ days)
    cur.execute("""
        SELECT DISTINCT pattern
        FROM workout_summaries,
             jsonb_array_elements_text(patterns) as pattern
        WHERE workout_date >= CURRENT_DATE - INTERVAL '10 days'
    """)
    recent_patterns = {r['pattern'] for r in cur.fetchall()}
    
    cur.execute("""
        SELECT DISTINCT pattern
        FROM workout_summaries,
             jsonb_array_elements_text(patterns) as pattern
        WHERE workout_date >= %s
    """, [start_date])
    all_patterns = {r['pattern'] for r in cur.fetchall()}
    
    pattern_gaps = list(all_patterns - recent_patterns)
    
    # Get latest ACWR values
    cur.execute("""
        SELECT acwr as volume_acwr
        FROM training_load_daily
        ORDER BY workout_date DESC
        LIMIT 1
    """)
    volume_acwr = cur.fetchone()
    
    cur.execute("""
        SELECT trimp_acwr
        FROM trimp_acwr
        WHERE daily_trimp > 0
        ORDER BY session_date DESC
        LIMIT 1
    """)
    trimp_acwr = cur.fetchone()
    
    conn.close()
    
    # Computed insights for coach
    coaching_notes = []
    
    if pattern_gaps:
        # Flag core movement pattern gaps
        core_gaps = [p for p in pattern_gaps if p in 
                     {'Hip Hinge', 'Squat', 'Horizontal Pull', 'Horizontal Push', 
                      'Vertical Pull', 'Vertical Push'}]
        if core_gaps:
            coaching_notes.append(f"Pattern gaps (no work in 10d): {', '.join(core_gaps)}")
    
    # ACWR insights
    if trimp_acwr and trimp_acwr['trimp_acwr']:
        acwr_val = float(trimp_acwr['trimp_acwr'])
        if acwr_val > 1.5:
            coaching_notes.append(f"ACWR {round(acwr_val, 2)} - elevated load")
        elif acwr_val < 0.8:
            coaching_notes.append(f"ACWR {round(acwr_val, 2)} - can increase load")
    
    # Build response
    result = {
        "period": {"start": start_date, "end": end_date},
        "summary": {
            "workouts": summary['workouts'] if summary else 0,
            "total_sets": summary['total_sets'] if summary else 0,
            "total_volume_lbs": round(float(summary['total_volume'])) if summary and summary['total_volume'] else 0
        },
        "acwr": {
            "volume_based": round(float(volume_acwr['volume_acwr']), 2) if volume_acwr and volume_acwr['volume_acwr'] else None,
            "trimp_based": round(float(trimp_acwr['trimp_acwr']), 2) if trimp_acwr and trimp_acwr['trimp_acwr'] else None
        },
        "weekly_trend": [
            {
                "week": str(w['week_start']),
                "workouts": w['workouts'],
                "sets": w['total_sets'],
                "volume_klbs": float(w['volume_klbs']) if w['volume_klbs'] else 0
            }
            for w in weekly
        ] if weekly else [],
        "pattern_distribution": {
            p['pattern']: p['workout_count']
            for p in patterns
        } if patterns else {},
        "pattern_gaps": pattern_gaps,
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=decimal_default))]


async def get_exercise_history(exercise: str, days: int):
    """Get exercise progression history."""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Query exercise data from JSONB
    exercise_lower = exercise.lower()
    
    cur.execute("""
        SELECT 
            ws.workout_date,
            ex->>'name' as exercise_name,
            (ex->>'max_load')::numeric as max_load,
            (ex->>'total_reps')::int as total_reps,
            (ex->>'sets')::int as sets,
            ex->'set_details' as set_details
        FROM workout_summaries ws,
             jsonb_array_elements(ws.exercises) as ex
        WHERE LOWER(ex->>'name') LIKE %s
          AND ws.workout_date >= %s
        ORDER BY ws.workout_date DESC
    """, [f"%{exercise_lower}%", start_date])
    
    progression = cur.fetchall()
    conn.close()
    
    if not progression:
        return [TextContent(type="text", text=json.dumps({
            "exercise": exercise,
            "error": "No matching exercise found in history",
            "sessions": 0
        }, indent=2))]
    
    # Get canonical name from first result
    canonical_name = progression[0]['exercise_name']
    
    # Calculate estimated 1RM for each session (Brzycki formula)
    def e1rm(weight, reps):
        if not weight or not reps or reps > 12:
            return None
        return round(float(weight) * (36 / (37 - reps)))
    
    # Find best set from set_details for each session
    def get_best_set(set_details):
        """Find the set with highest e1RM."""
        if not set_details:
            return None, None
        best_load = None
        best_reps = None
        best_e1rm = 0
        for s in set_details:
            load = s.get('load_lbs')
            reps = s.get('reps')
            if load and reps:
                est = e1rm(load, reps)
                if est and est > best_e1rm:
                    best_e1rm = est
                    best_load = load
                    best_reps = reps
        return best_load, best_reps
    
    # Process progression data
    sessions = []
    pr = None
    pr_e1rm = 0
    
    for p in progression:
        load = float(p['max_load']) if p['max_load'] else None
        set_details = p['set_details'] if p['set_details'] else []
        
        # Find best set for e1RM calculation
        best_load, best_reps = get_best_set(set_details)
        if not best_load:
            best_load = load
            best_reps = p['total_reps'] // p['sets'] if p['sets'] and p['total_reps'] else None
        
        est_1rm = e1rm(best_load, best_reps)
        
        sessions.append({
            "date": str(p['workout_date']),
            "max_load": load,
            "sets": p['sets'],
            "total_reps": p['total_reps'],
            "e1rm": est_1rm
        })
        
        # Track PR
        if est_1rm and est_1rm > pr_e1rm:
            pr_e1rm = est_1rm
            pr = {
                "load": best_load,
                "reps": best_reps,
                "date": str(p['workout_date']),
                "e1rm": est_1rm
            }
    
    coaching_notes = []
    
    # Compare recent vs historical
    if len(sessions) >= 2:
        recent_e1rm = sessions[0]['e1rm']
        older_e1rm = sessions[-1]['e1rm']
        
        if recent_e1rm and older_e1rm:
            if recent_e1rm > older_e1rm:
                coaching_notes.append(f"Estimated 1RM improving: {older_e1rm} → {recent_e1rm}")
            elif recent_e1rm < older_e1rm * 0.9:
                coaching_notes.append("Strength below previous levels (rebuilding?)")
    
    result = {
        "exercise": canonical_name,
        "sessions": len(sessions),
        "date_range": {
            "first": sessions[-1]['date'] if sessions else None,
            "last": sessions[0]['date'] if sessions else None
        },
        "progression": sessions[:10],  # Last 10 sessions
        "current_pr": pr,
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=decimal_default))]


async def check_red_flags():
    """Report observations for Arnold to interpret.
    
    This tool reports FACTS only. No suppression, no filtering, no recommendations.
    Arnold (the intelligence layer) interprets and synthesizes with annotations.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    conn = get_db()
    cur = conn.cursor()
    
    observations = []
    
    # === HRV TREND ===
    cur.execute("""
        SELECT reading_date, hrv_ms
        FROM readiness_daily
        WHERE hrv_ms IS NOT NULL
        ORDER BY reading_date DESC
        LIMIT 7
    """)
    hrv_data = cur.fetchall()
    
    if hrv_data and len(hrv_data) >= 3:
        recent_avg = sum(float(h['hrv_ms']) for h in hrv_data[:3]) / 3
        older_vals = [float(h['hrv_ms']) for h in hrv_data[3:]]
        older_avg = sum(older_vals) / len(older_vals) if older_vals else recent_avg
        
        if older_avg > 0:
            pct_change = round((recent_avg / older_avg - 1) * 100)
            trend = "declining" if pct_change < -10 else "improving" if pct_change > 10 else "stable"
            
            observations.append({
                "type": "hrv_trend",
                "observation": f"HRV {trend}: {pct_change:+d}% vs prior days",
                "data": {
                    "recent_avg": round(recent_avg),
                    "prior_avg": round(older_avg),
                    "pct_change": pct_change,
                    "trend": trend,
                    "dates": [str(h['reading_date']) for h in hrv_data]
                }
            })
    
    # === DATA GAPS ===
    cur.execute("""
        SELECT MAX(reading_date) as last_date
        FROM readiness_daily
        WHERE hrv_ms IS NOT NULL
    """)
    last_hrv = cur.fetchone()
    
    if last_hrv and last_hrv['last_date']:
        days_since = (datetime.now().date() - last_hrv['last_date']).days
        if days_since > 1:  # Report any gap, even 2 days
            observations.append({
                "type": "data_gap",
                "metric": "hrv",
                "observation": f"No HRV data for {days_since} days",
                "data": {
                    "last_reading": str(last_hrv['last_date']),
                    "days_since": days_since
                }
            })
    
    # Check sleep gap separately
    cur.execute("""
        SELECT MAX(reading_date) as last_date
        FROM readiness_daily
        WHERE sleep_hours IS NOT NULL
    """)
    last_sleep = cur.fetchone()
    
    if last_sleep and last_sleep['last_date']:
        days_since = (datetime.now().date() - last_sleep['last_date']).days
        if days_since > 1:
            observations.append({
                "type": "data_gap",
                "metric": "sleep",
                "observation": f"No sleep data for {days_since} days",
                "data": {
                    "last_reading": str(last_sleep['last_date']),
                    "days_since": days_since
                }
            })
    
    # === PATTERN DISTRIBUTION ===
    cur.execute("""
        SELECT DISTINCT pattern
        FROM workout_summaries,
             jsonb_array_elements_text(patterns) as pattern
        WHERE workout_date >= CURRENT_DATE - INTERVAL '10 days'
    """)
    recent_patterns = {r['pattern'] for r in cur.fetchall()}
    
    core_patterns = {"Hip Hinge", "Squat", "Horizontal Pull", "Horizontal Push", "Vertical Pull", "Vertical Push"}
    missing = core_patterns - recent_patterns
    
    if missing:
        observations.append({
            "type": "pattern_gap",
            "observation": f"No recent work (10d): {', '.join(sorted(missing))}",
            "data": {
                "missing_patterns": sorted(list(missing)),
                "recent_patterns": sorted(list(recent_patterns)),
                "window_days": 10
            }
        })
    
    # === SLEEP STATS ===
    cur.execute("""
        SELECT 
            AVG(sleep_hours) as avg_sleep,
            MIN(sleep_hours) as min_sleep,
            MAX(sleep_hours) as max_sleep,
            COUNT(*) as nights
        FROM readiness_daily
        WHERE reading_date >= CURRENT_DATE - INTERVAL '7 days'
          AND sleep_hours IS NOT NULL
    """)
    sleep_stats = cur.fetchone()
    
    if sleep_stats and sleep_stats['avg_sleep']:
        avg = float(sleep_stats['avg_sleep'])
        observations.append({
            "type": "sleep_summary",
            "observation": f"Sleep averaging {round(avg, 1)} hrs over {sleep_stats['nights']} nights",
            "data": {
                "avg_hours": round(avg, 1),
                "min_hours": round(float(sleep_stats['min_sleep']), 1) if sleep_stats['min_sleep'] else None,
                "max_hours": round(float(sleep_stats['max_sleep']), 1) if sleep_stats['max_sleep'] else None,
                "nights": sleep_stats['nights']
            }
        })
    
    # === ACWR ===
    cur.execute("""
        SELECT trimp_acwr, session_date
        FROM trimp_acwr
        WHERE daily_trimp > 0
        ORDER BY session_date DESC
        LIMIT 1
    """)
    acwr_row = cur.fetchone()
    
    if acwr_row and acwr_row['trimp_acwr']:
        acwr = float(acwr_row['trimp_acwr'])
        zone = "high_risk" if acwr > 1.5 else "optimal" if 0.8 <= acwr <= 1.3 else "low"
        observations.append({
            "type": "acwr",
            "observation": f"ACWR at {round(acwr, 2)} ({zone})",
            "data": {
                "value": round(acwr, 2),
                "zone": zone,
                "as_of": str(acwr_row['session_date']) if acwr_row['session_date'] else None
            }
        })
    
    # === RELEVANT ANNOTATIONS ===
    # Include active annotations covering recent period as context
    annotations = get_annotations_for_period(cur, seven_days_ago, today)
    annotation_list = []
    for a in annotations:
        annotation_list.append({
            "id": a['id'],
            "date": str(a['annotation_date']),
            "date_end": str(a['date_range_end']) if a['date_range_end'] else None,
            "target": f"{a['target_type']}/{a['target_metric']}",
            "reason": a['reason_code'],
            "explanation": a['explanation']
        })
    
    conn.close()
    
    result = {
        "observations": observations,
        "annotations": annotation_list,
        "observation_count": len(observations)
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def get_sleep_analysis(days: int):
    """Analyze sleep patterns."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get daily sleep data
    cur.execute("""
        SELECT 
            reading_date,
            sleep_hours,
            sleep_deep_min,
            sleep_rem_min,
            sleep_quality_pct
        FROM readiness_daily
        WHERE reading_date BETWEEN %s AND %s
          AND sleep_hours IS NOT NULL
        ORDER BY reading_date
    """, [start_date, end_date])
    sleep_data = cur.fetchall()
    
    # Get baseline (prior 30 days)
    cur.execute("""
        SELECT 
            AVG(sleep_hours) as avg_sleep,
            AVG(sleep_quality_pct) as avg_quality
        FROM readiness_daily
        WHERE reading_date BETWEEN %s::date - INTERVAL '30 days' AND %s::date - INTERVAL '1 day'
          AND sleep_hours IS NOT NULL
    """, [start_date, start_date])
    baseline = cur.fetchone()
    
    if not sleep_data:
        # No data in requested period - check if there's an annotation explaining why
        gap_annotation = check_annotation_covers_gap(
            cur, 'biometric', 'sleep', start_date, end_date
        )
        
        # Try to get most recent available sleep data instead
        cur.execute("""
            SELECT 
                reading_date,
                sleep_hours,
                sleep_deep_min,
                sleep_rem_min,
                sleep_quality_pct
            FROM readiness_daily
            WHERE sleep_hours IS NOT NULL
            ORDER BY reading_date DESC
            LIMIT %s
        """, [days])
        sleep_data = cur.fetchall()
        
        if not sleep_data:
            conn.close()
            result = {"nights_analyzed": 0}
            if gap_annotation:
                result["data_gap_context"] = gap_annotation
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    conn.close()
    
    # Calculate stats
    sleep_hrs = [float(s['sleep_hours']) for s in sleep_data if s['sleep_hours']]
    deep_mins = [float(s['sleep_deep_min']) for s in sleep_data if s['sleep_deep_min']]
    rem_mins = [float(s['sleep_rem_min']) for s in sleep_data if s['sleep_rem_min']]
    qualities = [float(s['sleep_quality_pct']) for s in sleep_data if s['sleep_quality_pct']]
    
    avg_hours = sum(sleep_hrs) / len(sleep_hrs) if sleep_hrs else None
    total_min = avg_hours * 60 if avg_hours else None
    avg_deep_pct = sum(deep_mins) / (total_min * len(deep_mins)) * 100 if total_min and deep_mins else None
    avg_rem_pct = sum(rem_mins) / (total_min * len(rem_mins)) * 100 if total_min and rem_mins else None
    
    # Find best/worst
    best = max(sleep_data, key=lambda s: float(s['sleep_hours']) if s['sleep_hours'] else 0) if sleep_data else None
    worst = min(sleep_data, key=lambda s: float(s['sleep_hours']) if s['sleep_hours'] else float('inf')) if sleep_data else None
    
    # Count below thresholds
    below_7 = sum(1 for s in sleep_hrs if s < 7)
    below_6 = sum(1 for s in sleep_hrs if s < 6)
    
    coaching_notes = []
    
    if avg_hours and avg_hours < 6.5:
        coaching_notes.append(f"Averaging {round(avg_hours, 1)} hrs - below optimal for recovery")
    
    if avg_deep_pct and avg_deep_pct < 15:
        coaching_notes.append("Deep sleep percentage low")
    
    if below_6 > len(sleep_data) / 3:
        coaching_notes.append(f"{below_6} nights under 6 hours in {len(sleep_data)} days")
    
    result = {
        "period": {"start": start_date, "end": end_date},
        "nights_analyzed": len(sleep_data),
        "averages": {
            "total_hours": round(avg_hours, 1) if avg_hours else None,
            "deep_pct": round(avg_deep_pct) if avg_deep_pct else None,
            "rem_pct": round(avg_rem_pct) if avg_rem_pct else None,
            "quality_pct": round(sum(qualities) / len(qualities)) if qualities else None
        },
        "vs_baseline": {
            "hours_delta": round(avg_hours - float(baseline['avg_sleep']), 1) if avg_hours and baseline and baseline['avg_sleep'] else None,
            "quality_delta": round(sum(qualities)/len(qualities) - float(baseline['avg_quality'])) if qualities and baseline and baseline['avg_quality'] else None
        } if baseline else None,
        "trend": calc_trend(sleep_hrs),
        "nights_below_7hr": below_7,
        "nights_below_6hr": below_6,
        "best_night": {
            "date": str(best['reading_date']),
            "hours": round(float(best['sleep_hours']), 1),
            "quality_pct": float(best['sleep_quality_pct']) if best['sleep_quality_pct'] else None
        } if best else None,
        "worst_night": {
            "date": str(worst['reading_date']),
            "hours": round(float(worst['sleep_hours']), 1),
            "quality_pct": float(worst['sleep_quality_pct']) if worst['sleep_quality_pct'] else None
        } if worst else None,
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=decimal_default))]


async def run_sync(steps: list = None):
    """Run the data sync pipeline."""
    import subprocess
    from pathlib import Path
    
    # Find the sync pipeline script
    # MCP server runs from src/arnold-analytics-mcp, so go up to project root
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "sync_pipeline.py"
    
    if not script_path.exists():
        return [TextContent(type="text", text=json.dumps({
            "error": f"Sync pipeline not found at {script_path}",
            "status": "failed"
        }, indent=2))]
    
    # Use conda env Python - bare 'python' not in MCP PATH
    python_path = "/opt/anaconda3/envs/arnold/bin/python"
    
    # Build command
    cmd = [python_path, str(script_path), "--trigger", "mcp"]
    if steps:
        for step in steps:
            cmd.extend(["--step", step])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=script_path.parent.parent  # Project root
        )
        
        output = {
            "status": "success" if result.returncode == 0 else "failed",
            "return_code": result.returncode,
            "output": result.stdout[-2000:] if result.stdout else None,  # Last 2000 chars
            "errors": result.stderr[-1000:] if result.stderr else None
        }
        
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
        
    except subprocess.TimeoutExpired:
        return [TextContent(type="text", text=json.dumps({
            "status": "timeout",
            "error": "Pipeline timed out after 5 minutes"
        }, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "status": "error",
            "error": str(e)
        }, indent=2))]


async def get_sync_history(limit: int = 5):
    """Get recent sync history."""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            id,
            started_at,
            completed_at,
            status,
            steps_run,
            records_synced,
            error_message,
            triggered_by,
            EXTRACT(EPOCH FROM (completed_at - started_at))::int as duration_seconds
        FROM sync_history
        ORDER BY started_at DESC
        LIMIT %s
    """, [limit])
    
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return [TextContent(type="text", text=json.dumps({
            "message": "No sync history found",
            "syncs": []
        }, indent=2))]
    
    syncs = []
    for r in rows:
        syncs.append({
            "id": r['id'],
            "started_at": r['started_at'].isoformat() if r['started_at'] else None,
            "completed_at": r['completed_at'].isoformat() if r['completed_at'] else None,
            "duration_seconds": r['duration_seconds'],
            "status": r['status'],
            "triggered_by": r['triggered_by'],
            "steps": r['steps_run'],
            "records_synced": r['records_synced'],
            "error": r['error_message']
        })
    
    # Summary stats
    successful = sum(1 for s in syncs if s['status'] == 'success')
    failed = sum(1 for s in syncs if s['status'] == 'failed')
    
    result = {
        "recent_syncs": syncs,
        "summary": {
            "total": len(syncs),
            "successful": successful,
            "failed": failed,
            "last_success": next((s['started_at'] for s in syncs if s['status'] == 'success'), None)
        }
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=decimal_default))]


async def get_hrr_trend(days: int = 28, stratum: str = None):
    """
    Get HRR trend analysis with EWMA/CUSUM detection.
    
    Returns per-stratum baselines, recent trends, and alerts.
    Uses confidence-weighted HRR60 for robust trend detection.
    
    EWMA: λ=0.2, warning=1.0×SDD, action=2.0×SDD
    CUSUM: k=0.5×SDD, h=4.0×SDD
    """
    import pandas as pd
    import numpy as np
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    conn = get_db()
    cur = conn.cursor()
    
    # Query actionable intervals
    query = """
        SELECT 
            start_time,
            stratum,
            hrr60_abs,
            weighted_hrr60,
            confidence,
            tau_fit_r2,
            peak_minus_local,
            polar_session_id
        FROM hr_recovery_intervals
        WHERE actionable = true
          AND start_time >= %s
          AND start_time <= %s
    """
    params = [start_date, end_date]
    
    if stratum:
        query += " AND stratum = %s"
        params.append(stratum)
    
    query += " ORDER BY start_time"
    cur.execute(query, params)
    rows = cur.fetchall()
    
    if not rows:
        conn.close()
        return [TextContent(type="text", text=json.dumps({
            "intervals": 0,
            "message": "No actionable HRR intervals found in period",
            "period": {"start": start_date.strftime("%Y-%m-%d"), "end": end_date.strftime("%Y-%m-%d")}
        }, indent=2))]
    
    # Convert to DataFrame
    df = pd.DataFrame(rows)
    df['start_time'] = pd.to_datetime(df['start_time'])
    df = df.set_index('start_time').sort_index()
    
    # Per-stratum analysis
    strata_results = {}
    all_alerts = []
    
    for strat in df['stratum'].unique():
        sdf = df[df['stratum'] == strat].copy()
        
        if len(sdf) < 5:
            strata_results[strat] = {
                "intervals": len(sdf),
                "status": "insufficient_data",
                "message": f"Need ≥5 intervals for trend detection, have {len(sdf)}"
            }
            continue
        
        # Compute baseline and SDD from full history
        # TE (Typical Error) ≈ SD / sqrt(2) for test-retest
        # SDD = 2.77 × TE (Smallest Detectable Difference at 95% CI)
        hrr_vals = sdf['hrr60_abs'].dropna().astype(float)
        if len(hrr_vals) < 5:
            continue
            
        baseline = float(hrr_vals.mean())
        sd = float(hrr_vals.std())
        te = sd / np.sqrt(2)  # typical error
        sdd = 2.77 * te  # smallest detectable difference
        
        # Get weighted values for trend detection
        weighted = sdf['weighted_hrr60'].dropna().astype(float)
        if len(weighted) < 5:
            weighted = hrr_vals  # fall back to raw
        
        ts = weighted.index
        x = weighted.values
        
        # EWMA detection
        ewma_alerts = []
        warning_threshold = baseline - 1.0 * sdd
        action_threshold = baseline - 2.0 * sdd
        
        # Simple EWMA with gap reset
        lam = 0.2
        gap_seconds = 3600  # 1 hour
        z_prev = baseline
        ewma_vals = []
        min_events = 5
        events_since_reset = 0
        
        for i, (t, val) in enumerate(zip(ts, x)):
            if i > 0:
                gap = (t - ts[i-1]).total_seconds()
                if gap > gap_seconds:
                    z_prev = baseline
                    events_since_reset = 0
            
            z_prev = lam * val + (1 - lam) * z_prev
            ewma_vals.append(z_prev)
            events_since_reset += 1
            
            if events_since_reset >= min_events:
                if z_prev <= action_threshold:
                    ewma_alerts.append({
                        "time": t.isoformat(),
                        "level": "action",
                        "ewma": round(z_prev, 1),
                        "threshold": round(action_threshold, 1)
                    })
                elif z_prev <= warning_threshold:
                    ewma_alerts.append({
                        "time": t.isoformat(),
                        "level": "warning",
                        "ewma": round(z_prev, 1),
                        "threshold": round(warning_threshold, 1)
                    })
        
        # CUSUM detection (one-sided downward)
        cusum_alerts = []
        k = 0.5 * sdd  # allowance
        h = 4.0 * sdd  # threshold
        s = 0.0
        
        for i, (t, val) in enumerate(zip(ts, x)):
            if i > 0:
                gap = (t - ts[i-1]).total_seconds()
                if gap > gap_seconds:
                    s = 0.0
            
            incr = (baseline - val) - k
            s = max(0.0, s + incr)
            
            if s >= h:
                cusum_alerts.append({
                    "time": t.isoformat(),
                    "level": "action",
                    "cusum": round(s, 1),
                    "threshold": round(h, 1)
                })
                s = 0.0  # reset after alert
        
        # Recent trend (last 7 values vs prior)
        recent_n = min(7, len(hrr_vals) // 2)
        if recent_n >= 3:
            recent_avg = float(hrr_vals.iloc[-recent_n:].mean())
            prior_avg = float(hrr_vals.iloc[:-recent_n].mean())
            trend_pct = round((recent_avg / prior_avg - 1) * 100) if prior_avg > 0 else 0
            trend = "declining" if trend_pct < -10 else "improving" if trend_pct > 10 else "stable"
        else:
            recent_avg = float(hrr_vals.mean())
            trend_pct = 0
            trend = "insufficient_data"
        
        strata_results[strat] = {
            "intervals": len(sdf),
            "sessions": int(sdf['polar_session_id'].nunique()),
            "baseline": {
                "mean_hrr60": round(baseline, 1),
                "sd": round(sd, 1),
                "sdd": round(sdd, 1),
                "warning_below": round(warning_threshold, 1),
                "action_below": round(action_threshold, 1)
            },
            "current": {
                "recent_avg": round(recent_avg, 1),
                "vs_baseline_pct": trend_pct,
                "trend": trend,
                "latest_ewma": round(ewma_vals[-1], 1) if ewma_vals else None
            },
            "confidence": {
                "mean": round(float(sdf['confidence'].mean()), 2),
                "min": round(float(sdf['confidence'].min()), 2)
            },
            "alerts": {
                "ewma": ewma_alerts[-3:] if ewma_alerts else [],  # last 3
                "cusum": cusum_alerts[-3:] if cusum_alerts else []
            }
        }
        
        # Collect for summary
        for a in ewma_alerts:
            all_alerts.append({"stratum": strat, "detector": "ewma", **a})
        for a in cusum_alerts:
            all_alerts.append({"stratum": strat, "detector": "cusum", **a})
    
    conn.close()
    
    # Coaching notes
    coaching_notes = []
    
    # Check for recent alerts (last 7 days)
    recent_cutoff = (end_date - timedelta(days=7)).isoformat()
    recent_alerts = [a for a in all_alerts if a.get('time', '') >= recent_cutoff]
    
    if recent_alerts:
        action_alerts = [a for a in recent_alerts if a['level'] == 'action']
        if action_alerts:
            coaching_notes.append(f"{len(action_alerts)} action-level HRR alert(s) in past 7 days - recovery may be compromised")
        else:
            coaching_notes.append(f"{len(recent_alerts)} warning-level HRR alert(s) in past 7 days - monitor recovery")
    
    # Check per-stratum trends
    for strat, data in strata_results.items():
        if isinstance(data, dict) and data.get('current', {}).get('trend') == 'declining':
            coaching_notes.append(f"{strat} HRR declining {abs(data['current']['vs_baseline_pct'])}% vs baseline")
    
    result = {
        "period": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "days": days
        },
        "total_intervals": len(df),
        "strata": strata_results,
        "recent_alerts": recent_alerts[-5:] if recent_alerts else [],
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=decimal_default))]


async def run():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Entry point."""
    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
