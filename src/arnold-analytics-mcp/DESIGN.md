# arnold-analytics-mcp Design (v2)

> **Status**: Implementation  
> **Codename**: T-1000  
> **Last Updated**: January 2, 2026

## Philosophy

This is **Arnold's eyes**, not a query tool for the athlete.

Arnold calls these tools automatically as part of coaching. The athlete says "What's today's workout?" and Arnold internally checks readiness, recent load, and red flags before responding.

**Tools should return coaching-ready summaries, not raw data.**

## Tool Definitions

### 1. get_readiness_snapshot

**Called by Arnold before any training decision.**

Returns current day's readiness state with context.

```python
def get_readiness_snapshot(date: str = "today") -> dict:
    """
    Returns:
    {
        "date": "2026-01-02",
        "hrv": {
            "value": 82,
            "vs_7d_avg": -8,        # percentage
            "vs_baseline": -12,
            "trend": "declining"    # stable, improving, declining
        },
        "sleep": {
            "hours": 6.2,
            "quality_score": 72,
            "deep_pct": 18,
            "trend": "stable"
        },
        "recovery_score": 68,
        "resting_hr": 62,
        "recent_load": {
            "yesterday_sets": 15,
            "yesterday_volume_lbs": 8500,
            "3d_avg_sets": 12,
            "7d_avg_sets": 8
        },
        "data_completeness": 3,      # 0-4
        "data_sources": ["hrv", "sleep", "ultrahuman"],
        "missing": ["training"],
        "coaching_notes": [
            "HRV declining over 3 days",
            "Sleep below 7hr threshold"
        ]
    }
    """
```

### 2. get_training_load

**Called for programming and overtraining assessment.**

```python
def get_training_load(days: int = 28) -> dict:
    """
    Returns:
    {
        "period": {"start": "2025-12-05", "end": "2026-01-02"},
        "summary": {
            "workouts": 12,
            "total_sets": 180,
            "total_reps": 1800,
            "total_volume_lbs": 125000,
            "avg_rpe": 7.2
        },
        "weekly_trend": [
            {"week": "2025-12-30", "sets": 45, "volume_klbs": 50.6},
            {"week": "2025-12-23", "sets": 15, "volume_klbs": 1.3},
            ...
        ],
        "pattern_distribution": {
            "Hip Hinge": {"sets": 24, "pct": 40},
            "Vertical Pull": {"sets": 12, "pct": 20},
            ...
        },
        "pattern_gaps": ["Horizontal Pull"],  # No work in 10+ days
        "coaching_notes": [
            "Volume trending up after surgery gap",
            "Hip Hinge dominant - appropriate for deadlift goal",
            "Consider adding horizontal pull work"
        ]
    }
    """
```

### 3. get_exercise_history

**Called when programming specific lifts or assessing progress.**

```python
def get_exercise_history(
    exercise: str,           # "Deadlift" - fuzzy matched
    days: int = 180
) -> dict:
    """
    Returns:
    {
        "exercise": "Deadlift (Barbell)",
        "canonical_id": "EX:deadlift-barbell",
        "sessions": 12,
        "date_range": {"first": "2025-07-15", "last": "2025-12-23"},
        "progression": [
            {"date": "2025-12-23", "max_load": 245, "reps_at_max": 10, "e1rm": 327},
            {"date": "2025-12-22", "max_load": 135, "reps_at_max": 10, "e1rm": 180},
            {"date": "2025-11-11", "max_load": 315, "reps_at_max": 5, "e1rm": 354},
            ...
        ],
        "current_pr": {"load": 345, "reps": 5, "date": "2025-11-07", "e1rm": 388},
        "goal": {"target": 405, "reps": 5, "e1rm": 456},
        "distance_to_goal": {
            "lbs_needed": 60,
            "pct_there": 85
        },
        "coaching_notes": [
            "Pre-surgery peak: 345x5",
            "Currently rebuilding: 245x10",
            "Estimated 4-6 months to goal at linear progression"
        ]
    }
    """
```

### 4. check_red_flags

**Called proactively at conversation start.**

Surfaces anything Arnold should address without being asked.

```python
def check_red_flags() -> dict:
    """
    Returns:
    {
        "flags": [
            {
                "type": "recovery",
                "severity": "moderate",  # low, moderate, high
                "message": "HRV down 15% over 3 days",
                "recommendation": "Consider lighter session or rest"
            },
            {
                "type": "pattern_gap",
                "severity": "low",
                "message": "No horizontal pull in 10 days",
                "recommendation": "Add rows or face pulls"
            },
            {
                "type": "data_gap",
                "severity": "low",
                "message": "No biometric data since Dec 6",
                "recommendation": "Check ring charging"
            }
        ],
        "all_clear": false,
        "summary": "2 concerns to address"
    }
    """
```

### 5. get_sleep_analysis

**Called when fatigue or recovery is a concern.**

```python
def get_sleep_analysis(days: int = 14) -> dict:
    """
    Returns:
    {
        "period": {"start": "2025-12-19", "end": "2026-01-02"},
        "averages": {
            "total_hours": 6.4,
            "deep_pct": 15,
            "rem_pct": 22,
            "efficiency": 88
        },
        "vs_baseline": {
            "hours_delta": -0.8,
            "quality_delta": -5
        },
        "trend": "declining",
        "nights_below_7hr": 10,
        "nights_below_6hr": 4,
        "best_night": {"date": "2025-12-25", "hours": 8.2, "score": 92},
        "worst_night": {"date": "2025-12-28", "hours": 5.1, "score": 58},
        "coaching_notes": [
            "Averaging 6.4 hrs - below optimal",
            "Deep sleep percentage low",
            "Recovery scores correlate with sleep in your data"
        ]
    }
    """
```

### 6. query_daily_metrics (internal use)

**For generating views and ad-hoc coaching analysis.**

Returns the unified daily view for a date range.

```python
def query_daily_metrics(
    start_date: str,
    end_date: str = "today",
    include_incomplete: bool = False
) -> list[dict]:
    """
    Returns daily_metrics view rows.
    Filtering by data_completeness unless include_incomplete=True.
    """
```

## Implementation

```
/src/arnold-analytics-mcp/
├── __init__.py
├── __main__.py              # MCP entry point
├── server.py                # Tool definitions
├── db.py                    # DuckDB connection
├── queries/
│   ├── readiness.py         # get_readiness_snapshot
│   ├── training_load.py     # get_training_load
│   ├── exercise.py          # get_exercise_history
│   ├── red_flags.py         # check_red_flags
│   └── sleep.py             # get_sleep_analysis
└── utils.py                 # Date parsing, fuzzy matching
```

## MCP Configuration

```json
{
  "mcpServers": {
    "arnold-analytics": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/arnold/src/arnold-analytics-mcp", "arnold-analytics"],
      "env": {
        "ARNOLD_DB_PATH": "/path/to/arnold/data/arnold_analytics.duckdb"
      }
    }
  }
}
```
