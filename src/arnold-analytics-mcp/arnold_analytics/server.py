"""
Arnold Analytics MCP Server

Codename: T-1000

This is Arnold's eyes into the data. These tools are called by Arnold
automatically as part of coaching, not by the athlete directly.

Tools return coaching-ready summaries, not raw data.
"""

import os
import json
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import duckdb
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Database path from environment or default
DB_PATH = os.environ.get(
    "ARNOLD_DB_PATH",
    os.path.expanduser("~/Documents/GitHub/arnold/data/arnold_analytics.duckdb")
)

server = Server("arnold-analytics")


def get_db():
    """Get read-only database connection."""
    return duckdb.connect(DB_PATH, read_only=True)


def parse_date(date_str: str) -> str:
    """Parse date string, supporting 'today', '7d', '30d', etc."""
    if date_str == "today":
        return datetime.now().strftime("%Y-%m-%d")
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
    
    # Get today's metrics
    today_row = conn.execute("""
        SELECT 
            date,
            hrv_avg,
            resting_hr,
            sleep_min,
            sleep_score,
            recovery_score,
            deep_min,
            workout_types,
            total_sets,
            volume_lbs,
            has_hrv,
            has_sleep,
            has_ultrahuman,
            has_training,
            data_completeness
        FROM daily_metrics
        WHERE date = ?
    """, [target_date]).fetchone()
    
    # Get 7-day averages
    seven_day = conn.execute("""
        SELECT 
            AVG(hrv_avg) as hrv_7d,
            AVG(sleep_min) as sleep_7d,
            AVG(recovery_score) as recovery_7d,
            AVG(total_sets) as sets_7d
        FROM daily_metrics
        WHERE date BETWEEN CAST(? AS DATE) - INTERVAL '7 days' AND CAST(? AS DATE) - INTERVAL '1 day'
    """, [target_date, target_date]).fetchone()
    
    # Get baseline (30-day)
    baseline = conn.execute("""
        SELECT 
            AVG(hrv_avg) as hrv_baseline,
            AVG(sleep_min) as sleep_baseline
        FROM daily_metrics
        WHERE date BETWEEN CAST(? AS DATE) - INTERVAL '30 days' AND CAST(? AS DATE) - INTERVAL '1 day'
          AND hrv_avg IS NOT NULL
    """, [target_date, target_date]).fetchone()
    
    # Get recent HRV trend (last 7 readings)
    hrv_trend_data = conn.execute("""
        SELECT hrv_avg
        FROM daily_metrics
        WHERE date <= ? AND hrv_avg IS NOT NULL
        ORDER BY date DESC
        LIMIT 7
    """, [target_date]).fetchall()
    
    # Get yesterday's training
    yesterday = conn.execute("""
        SELECT total_sets, volume_lbs
        FROM daily_metrics
        WHERE date = CAST(? AS DATE) - INTERVAL '1 day'
    """, [target_date]).fetchone()
    
    conn.close()
    
    # Build response
    coaching_notes = []
    
    result = {
        "date": target_date,
        "hrv": None,
        "sleep": None,
        "recovery_score": None,
        "resting_hr": None,
        "recent_load": None,
        "data_completeness": 0,
        "data_sources": [],
        "missing": [],
        "coaching_notes": []
    }
    
    if today_row:
        result["data_completeness"] = today_row[14] or 0
        
        # Data sources
        if today_row[10]:  # has_hrv
            result["data_sources"].append("hrv")
        else:
            result["missing"].append("hrv")
            
        if today_row[11]:  # has_sleep
            result["data_sources"].append("sleep")
        else:
            result["missing"].append("sleep")
            
        if today_row[12]:  # has_ultrahuman
            result["data_sources"].append("ultrahuman")
        else:
            result["missing"].append("ultrahuman")
            
        if today_row[13]:  # has_training
            result["data_sources"].append("training")
        
        # HRV
        if today_row[1]:
            hrv_val = round(today_row[1])
            hrv_7d = seven_day[0] if seven_day and seven_day[0] else None
            hrv_baseline = baseline[0] if baseline and baseline[0] else None
            
            hrv_values = [r[0] for r in hrv_trend_data if r[0]]
            trend = calc_trend(list(reversed(hrv_values)))
            
            result["hrv"] = {
                "value": hrv_val,
                "vs_7d_avg": round((hrv_val - hrv_7d) / hrv_7d * 100) if hrv_7d else None,
                "vs_baseline": round((hrv_val - hrv_baseline) / hrv_baseline * 100) if hrv_baseline else None,
                "trend": trend
            }
            
            if trend == "declining" and len(hrv_values) >= 3:
                coaching_notes.append("HRV declining over recent days")
            if hrv_7d and hrv_val < hrv_7d * 0.85:
                coaching_notes.append("HRV significantly below 7-day average")
        
        # Sleep
        if today_row[3]:
            sleep_hrs = round(today_row[3] / 60, 1)
            deep_pct = round(today_row[6] / today_row[3] * 100) if today_row[6] and today_row[3] else None
            
            result["sleep"] = {
                "hours": sleep_hrs,
                "quality_score": today_row[4],
                "deep_pct": deep_pct,
                "trend": "stable"  # Would need more data to calculate
            }
            
            if sleep_hrs < 6:
                coaching_notes.append("Sleep under 6 hours - recovery compromised")
            elif sleep_hrs < 7:
                coaching_notes.append("Sleep below 7hr threshold")
        
        # Recovery & RHR
        result["recovery_score"] = today_row[5]
        result["resting_hr"] = round(today_row[2]) if today_row[2] else None
        
        if today_row[5] and today_row[5] < 60:
            coaching_notes.append("Recovery score below 60 - consider lighter session")
    
    # Recent load
    if yesterday:
        result["recent_load"] = {
            "yesterday_sets": yesterday[0],
            "yesterday_volume_lbs": round(yesterday[1]) if yesterday[1] else None,
            "3d_avg_sets": round(seven_day[3]) if seven_day and seven_day[3] else None,
            "7d_avg_sets": round(seven_day[3]) if seven_day and seven_day[3] else None
        }
    
    result["coaching_notes"] = coaching_notes
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def get_training_load(days: int):
    """Get training load summary."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    
    # Overall summary
    summary = conn.execute("""
        SELECT 
            SUM(workout_count) as workouts,
            SUM(total_sets) as total_sets,
            SUM(total_reps) as total_reps,
            SUM(volume_lbs) as total_volume,
            AVG(avg_rpe) as avg_rpe
        FROM daily_metrics
        WHERE date BETWEEN ? AND ?
          AND workout_types IS NOT NULL
    """, [start_date, end_date]).fetchone()
    
    # Weekly trend
    weekly = conn.execute("""
        SELECT 
            week_start,
            workouts,
            total_sets,
            ROUND(total_volume_lbs / 1000, 1) as volume_klbs
        FROM weekly_training
        WHERE week_start >= ?
        ORDER BY week_start DESC
        LIMIT 8
    """, [start_date]).fetchall()
    
    # Pattern distribution
    patterns = conn.execute("""
        SELECT 
            pattern,
            SUM(sets) as total_sets
        FROM pattern_volume
        WHERE week_start >= ?
        GROUP BY pattern
        ORDER BY total_sets DESC
    """, [start_date]).fetchall()
    
    # Find pattern gaps (no work in 10+ days)
    recent_patterns = conn.execute("""
        SELECT DISTINCT pattern
        FROM pattern_volume
        WHERE week_start >= CURRENT_DATE - INTERVAL '10 days'
    """).fetchall()
    recent_pattern_set = {r[0] for r in recent_patterns}
    
    all_patterns = conn.execute("""
        SELECT DISTINCT pattern
        FROM pattern_volume
        WHERE week_start >= ?
    """, [start_date]).fetchall()
    all_pattern_set = {r[0] for r in all_patterns}
    
    pattern_gaps = list(all_pattern_set - recent_pattern_set)
    
    conn.close()
    
    # Calculate totals for percentages
    total_pattern_sets = sum(p[1] for p in patterns) if patterns else 1
    
    coaching_notes = []
    
    if pattern_gaps:
        coaching_notes.append(f"Pattern gaps (no recent work): {', '.join(pattern_gaps)}")
    
    # Build response
    result = {
        "period": {"start": start_date, "end": end_date},
        "summary": {
            "workouts": summary[0] if summary else 0,
            "total_sets": summary[1] if summary else 0,
            "total_reps": summary[2] if summary else 0,
            "total_volume_lbs": round(summary[3]) if summary and summary[3] else 0,
            "avg_rpe": round(summary[4], 1) if summary and summary[4] else None
        },
        "weekly_trend": [
            {
                "week": str(w[0])[:10],
                "workouts": w[1],
                "sets": w[2],
                "volume_klbs": w[3]
            }
            for w in weekly
        ] if weekly else [],
        "pattern_distribution": {
            p[0]: {
                "sets": p[1],
                "pct": round(p[1] / total_pattern_sets * 100)
            }
            for p in patterns
        } if patterns else {},
        "pattern_gaps": pattern_gaps,
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def get_exercise_history(exercise: str, days: int):
    """Get exercise progression history."""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    
    # Fuzzy match exercise name
    exercise_lower = exercise.lower()
    
    progression = conn.execute("""
        SELECT 
            date,
            exercise_name,
            max_load,
            max_reps,
            sets_performed,
            avg_rpe
        FROM exercise_progression
        WHERE LOWER(exercise_name) LIKE ?
          AND date >= ?
        ORDER BY date DESC
    """, [f"%{exercise_lower}%", start_date]).fetchall()
    
    conn.close()
    
    if not progression:
        return [TextContent(type="text", text=json.dumps({
            "exercise": exercise,
            "error": "No matching exercise found in history",
            "sessions": 0
        }, indent=2))]
    
    # Get canonical name from first result
    canonical_name = progression[0][1]
    
    # Calculate estimated 1RM for each session (Brzycki formula)
    def e1rm(weight, reps):
        if not weight or not reps or reps > 12:
            return None
        return round(weight * (36 / (37 - reps)))
    
    # Find PR
    pr = max(
        [(p[2], p[3], p[0], e1rm(p[2], p[3])) for p in progression if p[2] and p[3]],
        key=lambda x: x[3] or 0,
        default=None
    )
    
    coaching_notes = []
    
    # Check for recent vs historical comparison
    if len(progression) >= 2:
        recent = progression[0]
        older = progression[-1]
        recent_e1rm = e1rm(recent[2], recent[3])
        older_e1rm = e1rm(older[2], older[3])
        
        if recent_e1rm and older_e1rm:
            if recent_e1rm > older_e1rm:
                coaching_notes.append(f"Estimated 1RM improving: {older_e1rm} → {recent_e1rm}")
            elif recent_e1rm < older_e1rm * 0.9:
                coaching_notes.append(f"Strength below previous levels (rebuilding?)")
    
    result = {
        "exercise": canonical_name,
        "sessions": len(progression),
        "date_range": {
            "first": str(progression[-1][0]) if progression else None,
            "last": str(progression[0][0]) if progression else None
        },
        "progression": [
            {
                "date": str(p[0]),
                "max_load": p[2],
                "reps_at_max": p[3],
                "e1rm": e1rm(p[2], p[3]),
                "sets": p[4]
            }
            for p in progression[:10]  # Last 10 sessions
        ],
        "current_pr": {
            "load": pr[0],
            "reps": pr[1],
            "date": str(pr[2]),
            "e1rm": pr[3]
        } if pr else None,
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def check_red_flags():
    """Check for concerns Arnold should proactively address."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db()
    
    flags = []
    
    # Check HRV trend
    hrv_data = conn.execute("""
        SELECT date, hrv_avg
        FROM daily_metrics
        WHERE hrv_avg IS NOT NULL
        ORDER BY date DESC
        LIMIT 7
    """).fetchall()
    
    if hrv_data and len(hrv_data) >= 3:
        recent_avg = sum(h[1] for h in hrv_data[:3]) / 3
        older_avg = sum(h[1] for h in hrv_data[3:]) / max(1, len(hrv_data[3:]))
        
        if older_avg > 0 and (recent_avg / older_avg) < 0.85:
            flags.append({
                "type": "recovery",
                "severity": "moderate",
                "message": f"HRV down {round((1 - recent_avg/older_avg) * 100)}% over recent days",
                "recommendation": "Consider lighter session or rest"
            })
    
    # Check for data gap
    last_hrv = conn.execute("""
        SELECT MAX(date)
        FROM daily_metrics
        WHERE has_hrv = TRUE
    """).fetchone()
    
    if last_hrv and last_hrv[0]:
        days_since = (datetime.now().date() - last_hrv[0]).days
        if days_since > 3:
            flags.append({
                "type": "data_gap",
                "severity": "low",
                "message": f"No biometric data for {days_since} days",
                "recommendation": "Check ring charging / wear"
            })
    
    # Check pattern gaps
    recent_patterns = conn.execute("""
        SELECT DISTINCT pattern
        FROM pattern_volume
        WHERE week_start >= CURRENT_DATE - INTERVAL '10 days'
    """).fetchall()
    recent_set = {r[0] for r in recent_patterns}
    
    # Core patterns we expect to see
    core_patterns = {"Hip Hinge", "Squat", "Horizontal Pull", "Horizontal Push", "Vertical Pull", "Vertical Push"}
    missing = core_patterns - recent_set
    
    if missing and len(missing) <= 3:  # Only flag if 1-3 missing (not if we just started)
        flags.append({
            "type": "pattern_gap",
            "severity": "low",
            "message": f"No recent work: {', '.join(sorted(missing))}",
            "recommendation": "Consider adding these patterns"
        })
    
    # Check sleep trend
    sleep_data = conn.execute("""
        SELECT AVG(sleep_min)
        FROM daily_metrics
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
          AND sleep_min IS NOT NULL
    """).fetchone()
    
    if sleep_data and sleep_data[0] and sleep_data[0] < 360:  # Under 6 hours avg
        flags.append({
            "type": "recovery",
            "severity": "moderate",
            "message": f"Sleep averaging {round(sleep_data[0]/60, 1)} hours",
            "recommendation": "Prioritize sleep for recovery"
        })
    
    conn.close()
    
    result = {
        "flags": flags,
        "all_clear": len(flags) == 0,
        "summary": f"{len(flags)} concerns to address" if flags else "All clear"
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def get_sleep_analysis(days: int):
    """Analyze sleep patterns."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    
    # Get daily sleep data
    sleep_data = conn.execute("""
        SELECT 
            date,
            sleep_min,
            deep_min,
            rem_min,
            sleep_score,
            sleep_efficiency_calc
        FROM daily_metrics
        WHERE date BETWEEN ? AND ?
          AND sleep_min IS NOT NULL
        ORDER BY date
    """, [start_date, end_date]).fetchall()
    
    # Get baseline (prior 30 days)
    baseline = conn.execute("""
        SELECT 
            AVG(sleep_min) as avg_sleep,
            AVG(sleep_score) as avg_score
        FROM daily_metrics
        WHERE date BETWEEN CAST(? AS DATE) - INTERVAL '30 days' AND CAST(? AS DATE) - INTERVAL '1 day'
          AND sleep_min IS NOT NULL
    """, [start_date, start_date]).fetchone()
    
    conn.close()
    
    if not sleep_data:
        return [TextContent(type="text", text=json.dumps({
            "error": "No sleep data available for this period",
            "days_requested": days
        }, indent=2))]
    
    # Calculate stats
    sleep_mins = [s[1] for s in sleep_data if s[1]]
    deep_mins = [s[2] for s in sleep_data if s[2]]
    rem_mins = [s[3] for s in sleep_data if s[3]]
    scores = [s[4] for s in sleep_data if s[4]]
    efficiencies = [s[5] for s in sleep_data if s[5]]
    
    avg_hours = sum(sleep_mins) / len(sleep_mins) / 60 if sleep_mins else None
    avg_deep_pct = sum(deep_mins) / sum(sleep_mins) * 100 if sleep_mins and deep_mins else None
    avg_rem_pct = sum(rem_mins) / sum(sleep_mins) * 100 if sleep_mins and rem_mins else None
    
    # Find best/worst
    best = max(sleep_data, key=lambda s: s[1] or 0) if sleep_data else None
    worst = min(sleep_data, key=lambda s: s[1] or float('inf')) if sleep_data else None
    
    # Count below thresholds
    below_7 = sum(1 for s in sleep_mins if s < 420)
    below_6 = sum(1 for s in sleep_mins if s < 360)
    
    coaching_notes = []
    
    if avg_hours and avg_hours < 6.5:
        coaching_notes.append(f"Averaging {round(avg_hours, 1)} hrs - below optimal for recovery")
    
    if avg_deep_pct and avg_deep_pct < 15:
        coaching_notes.append("Deep sleep percentage low")
    
    if below_6 > days / 3:
        coaching_notes.append(f"{below_6} nights under 6 hours in {len(sleep_data)} days")
    
    result = {
        "period": {"start": start_date, "end": end_date},
        "nights_analyzed": len(sleep_data),
        "averages": {
            "total_hours": round(avg_hours, 1) if avg_hours else None,
            "deep_pct": round(avg_deep_pct) if avg_deep_pct else None,
            "rem_pct": round(avg_rem_pct) if avg_rem_pct else None,
            "efficiency": round(sum(efficiencies) / len(efficiencies)) if efficiencies else None,
            "score": round(sum(scores) / len(scores)) if scores else None
        },
        "vs_baseline": {
            "hours_delta": round((avg_hours - baseline[0]/60), 1) if avg_hours and baseline and baseline[0] else None,
            "score_delta": round(sum(scores)/len(scores) - baseline[1]) if scores and baseline and baseline[1] else None
        } if baseline else None,
        "trend": calc_trend(sleep_mins),
        "nights_below_7hr": below_7,
        "nights_below_6hr": below_6,
        "best_night": {
            "date": str(best[0]),
            "hours": round(best[1] / 60, 1),
            "score": best[4]
        } if best else None,
        "worst_night": {
            "date": str(worst[0]),
            "hours": round(worst[1] / 60, 1),
            "score": worst[4]
        } if worst else None,
        "coaching_notes": coaching_notes
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


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
