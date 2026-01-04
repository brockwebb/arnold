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


def get_active_overrides(cur):
    """Get active flag overrides (not expired)."""
    cur.execute("""
        SELECT flag_type, context, reason, expires_at
        FROM flag_overrides
        WHERE expires_at IS NULL OR expires_at > CURRENT_DATE
    """)
    return {r['flag_type']: r for r in cur.fetchall()}


@server.list_tools()
async def list_tools():
    """List available analytics tools."""
    return [
        Tool(
            name="get_readiness_snapshot",
            description="""Get current readiness state for coaching decisions.
            
Called by Arnold before any training recommendation. Returns HRV, sleep, 
recovery score, recent training load, and coaching notes.

Returns data completeness indicator (0-4) so Arnold knows confidence level.""",
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
            description="""Check for any concerns Arnold should proactively address.
            
Called at conversation start. Surfaces recovery issues, pattern gaps,
data problems, and anything else requiring attention.""",
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
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    
    if name == "get_readiness_snapshot":
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
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def get_readiness_snapshot(date_str: str):
    """Get readiness snapshot for coaching decisions."""
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
    
    # Build response
    coaching_notes = []
    
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
        "coaching_notes": []
    }
    
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
        
        # HRV
        if today_row['hrv_ms']:
            hrv_val = float(today_row['hrv_ms'])
            hrv_7d = float(seven_day['hrv_7d']) if seven_day and seven_day['hrv_7d'] else None
            hrv_baseline = float(baseline['hrv_baseline']) if baseline and baseline['hrv_baseline'] else None
            
            hrv_values = [float(r['hrv_ms']) for r in hrv_trend_data if r['hrv_ms']]
            trend = calc_trend(list(reversed(hrv_values)))
            
            result["hrv"] = {
                "value": round(hrv_val),
                "vs_7d_avg": round((hrv_val - hrv_7d) / hrv_7d * 100) if hrv_7d else None,
                "vs_baseline": round((hrv_val - hrv_baseline) / hrv_baseline * 100) if hrv_baseline else None,
                "trend": trend
            }
            
            if trend == "declining" and len(hrv_values) >= 3:
                coaching_notes.append("HRV declining over recent days")
            if hrv_7d and hrv_val < hrv_7d * 0.85:
                coaching_notes.append("HRV significantly below 7-day average")
        
        # Sleep
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
            
            if sleep_hrs < 6:
                coaching_notes.append("Sleep under 6 hours - recovery compromised")
            elif sleep_hrs < 7:
                coaching_notes.append("Sleep below 7hr threshold")
        
        # Resting HR
        if today_row['rhr_bpm']:
            result["resting_hr"] = round(float(today_row['rhr_bpm']))
    
    # Recent load
    if yesterday:
        result["recent_load"] = {
            "yesterday_sets": yesterday['daily_sets'],
            "yesterday_volume_lbs": round(float(yesterday['daily_volume'])) if yesterday['daily_volume'] else None,
            "volume_acwr": round(float(yesterday['acwr']), 2) if yesterday['acwr'] else None
        }
    
    # TRIMP-based ACWR (better than volume ACWR)
    if acwr_row and acwr_row['trimp_acwr']:
        acwr_val = float(acwr_row['trimp_acwr'])
        result["acwr"] = {
            "trimp_based": round(acwr_val, 2),
            "interpretation": "high_risk" if acwr_val > 1.5 else "optimal" if 0.8 <= acwr_val <= 1.3 else "low"
        }
        
        # Check for ACWR override before adding to coaching notes
        overrides = get_active_overrides(cur)
        if acwr_val > 1.5:
            if 'acwr' in overrides:
                result["acwr"]["override"] = overrides['acwr']['context']
            else:
                coaching_notes.append(f"ACWR {round(acwr_val, 2)} - elevated injury risk, consider recovery")
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
    
    coaching_notes = []
    
    if pattern_gaps:
        # Filter out non-essential patterns for gap reporting
        core_gaps = [p for p in pattern_gaps if p in 
                     {'Hip Hinge', 'Squat', 'Horizontal Pull', 'Horizontal Push', 
                      'Vertical Pull', 'Vertical Push'}]
        if core_gaps:
            coaching_notes.append(f"Pattern gaps (no recent work): {', '.join(core_gaps)}")
    
    # Build response
    total_pattern_workouts = sum(p['workout_count'] for p in patterns) if patterns else 1
    
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
    """Check for concerns Arnold should proactively address."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get active overrides
    overrides = get_active_overrides(cur)
    
    flags = []
    acknowledged = []
    
    # Check HRV trend
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
        
        if older_avg > 0 and (recent_avg / older_avg) < 0.85:
            flags.append({
                "type": "recovery",
                "severity": "moderate",
                "message": f"HRV down {round((1 - recent_avg/older_avg) * 100)}% over recent days",
                "recommendation": "Consider lighter session or rest"
            })
    
    # Check for data gap
    cur.execute("""
        SELECT MAX(reading_date) as last_date
        FROM readiness_daily
        WHERE hrv_ms IS NOT NULL
    """)
    last_hrv = cur.fetchone()
    
    if last_hrv and last_hrv['last_date']:
        days_since = (datetime.now().date() - last_hrv['last_date']).days
        if days_since > 3:
            flags.append({
                "type": "data_gap",
                "severity": "low",
                "message": f"No biometric data for {days_since} days",
                "recommendation": "Check ring charging / wear"
            })
    
    # Check pattern gaps
    cur.execute("""
        SELECT DISTINCT pattern
        FROM workout_summaries,
             jsonb_array_elements_text(patterns) as pattern
        WHERE workout_date >= CURRENT_DATE - INTERVAL '10 days'
    """)
    recent_patterns = {r['pattern'] for r in cur.fetchall()}
    
    # Core patterns we expect to see
    core_patterns = {"Hip Hinge", "Squat", "Horizontal Pull", "Horizontal Push", "Vertical Pull", "Vertical Push"}
    missing = core_patterns - recent_patterns
    
    if missing and len(missing) <= 3:  # Only flag if 1-3 missing
        flags.append({
            "type": "pattern_gap",
            "severity": "low",
            "message": f"No recent work: {', '.join(sorted(missing))}",
            "recommendation": "Consider adding these patterns"
        })
    
    # Check sleep trend
    cur.execute("""
        SELECT AVG(sleep_hours) as avg_sleep
        FROM readiness_daily
        WHERE reading_date >= CURRENT_DATE - INTERVAL '7 days'
          AND sleep_hours IS NOT NULL
    """)
    sleep_data = cur.fetchone()
    
    if sleep_data and sleep_data['avg_sleep'] and float(sleep_data['avg_sleep']) < 6:
        flags.append({
            "type": "recovery",
            "severity": "moderate",
            "message": f"Sleep averaging {round(float(sleep_data['avg_sleep']), 1)} hours",
            "recommendation": "Prioritize sleep for recovery"
        })
    
    # Check ACWR
    cur.execute("""
        SELECT trimp_acwr
        FROM trimp_acwr
        WHERE daily_trimp > 0
        ORDER BY session_date DESC
        LIMIT 1
    """)
    acwr_row = cur.fetchone()
    
    if acwr_row and acwr_row['trimp_acwr']:
        acwr = float(acwr_row['trimp_acwr'])
        if acwr > 1.5:
            flag_data = {
                "type": "acwr",
                "severity": "moderate",
                "message": f"ACWR at {round(acwr, 2)} - elevated injury risk",
                "recommendation": "Consider deload or recovery session"
            }
            # Check for override
            if 'acwr' in overrides:
                override = overrides['acwr']
                flag_data["acknowledged"] = True
                flag_data["override_reason"] = override['reason']
                flag_data["override_context"] = override['context']
                flag_data["override_expires"] = str(override['expires_at']) if override['expires_at'] else None
                acknowledged.append(flag_data)
            else:
                flags.append(flag_data)
    
    conn.close()
    
    result = {
        "flags": flags,
        "acknowledged": acknowledged,
        "all_clear": len(flags) == 0,
        "summary": f"{len(flags)} concerns to address" if flags else "All clear"
    }
    
    if acknowledged:
        result["summary"] += f" ({len(acknowledged)} acknowledged)"
    
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
    
    conn.close()
    
    if not sleep_data:
        return [TextContent(type="text", text=json.dumps({
            "error": "No sleep data available for this period",
            "days_requested": days
        }, indent=2))]
    
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
