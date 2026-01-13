# FR-004: Recovery Interval Detection (Heart Rate Recovery)

## Metadata
- **Priority**: Medium
- **Status**: Proposed
- **Created**: 2026-01-09
- **Dependencies**: FR-003 (HR Session Linking)

## Description

Analyze HR time-series data to detect recovery intervals (rest periods between sets) and calculate Heart Rate Recovery (HRR) metrics. This provides:

1. **HRR1** (1-minute recovery): Validated cardiovascular fitness marker
2. **Rest period patterns**: How long athlete actually rests between sets
3. **Recovery trend**: Is recovery capacity improving over time?

## Scientific Background

### Heart Rate Recovery (HRR)

HRR measures how quickly heart rate drops after exercise cessation. It's a proxy for **parasympathetic reactivation** (vagal tone).

**HRR1 Benchmarks** (1-minute post-exercise drop):
| Drop (bpm) | Interpretation |
|------------|----------------|
| < 12 | Poor recovery — flag for attention |
| 12-20 | Normal |
| 20-30 | Good |
| > 30 | Excellent |

**Clinical Significance**:
- Cole et al. (1999): HRR1 < 12 bpm associated with increased mortality risk
- Jouven et al. (2005): HRR correlates with cardiovascular fitness
- Daanen et al. (2012): HRR improves with training, declines with overreaching

**Arnold Application**: 
- Track HRR trend over weeks/months
- Flag abnormally poor recovery (possible fatigue/illness)
- Compare recovery across workout types

### Rest Period Detection

In strength training, rest periods appear as:
1. **HR peak** at set completion
2. **Steady decline** during rest
3. **Next peak** at next set start

Algorithm detects these patterns to:
- Calculate actual rest duration (vs prescribed)
- Measure per-interval recovery (drop in bpm)
- Identify when athlete is rushing or over-resting

## Algorithm

### Step 1: Find Local Maxima (Set Peaks)

```python
def find_peaks(hr_samples: List[HRSample], min_prominence: int = 10) -> List[Peak]:
    """
    Find HR peaks that likely correspond to set completions.
    
    Args:
        hr_samples: Time-ordered HR readings (1Hz)
        min_prominence: Minimum rise from surrounding values to qualify as peak
    
    Returns:
        List of peaks with timestamp and HR value
    """
    # Use scipy.signal.find_peaks or rolling window approach
    pass
```

### Step 2: Detect Recovery Intervals

```python
def detect_recovery_intervals(
    hr_samples: List[HRSample], 
    peaks: List[Peak],
    min_duration_sec: int = 50,
    max_duration_sec: int = 300
) -> List[RecoveryInterval]:
    """
    For each peak, scan forward while HR is declining.
    Mark as recovery interval if duration >= min_duration_sec.
    
    Returns:
        List of intervals with:
        - start_time, end_time
        - peak_hr, nadir_hr
        - duration_sec
        - total_drop_bpm
        - drop_rate_bpm_per_min
    """
    intervals = []
    for peak in peaks:
        # Scan forward from peak
        # Track HR decline
        # Stop when HR starts rising (next set) or max_duration reached
        # If duration >= 50 sec, record interval
        pass
    return intervals
```

### Step 3: Calculate HRR Metrics

```python
def calculate_hrr(interval: RecoveryInterval) -> HRRMetrics:
    """
    Calculate standard HRR metrics for an interval.
    """
    return HRRMetrics(
        hrr_30sec = interval.hr_at_30sec - interval.peak_hr if interval.duration >= 30 else None,
        hrr_60sec = interval.hr_at_60sec - interval.peak_hr if interval.duration >= 60 else None,
        hrr_120sec = interval.hr_at_120sec - interval.peak_hr if interval.duration >= 120 else None,
        drop_rate = interval.total_drop / (interval.duration / 60),  # bpm per minute
    )
```

## Data Model

### Recovery Intervals Table

```sql
CREATE TABLE hr_recovery_intervals (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id),
    strength_session_id INTEGER REFERENCES strength_sessions(id),  -- nullable
    
    -- Interval timing
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL,
    
    -- HR values
    peak_hr SMALLINT NOT NULL,
    nadir_hr SMALLINT NOT NULL,
    hr_at_30sec SMALLINT,
    hr_at_60sec SMALLINT,
    hr_at_120sec SMALLINT,
    
    -- Calculated metrics
    total_drop_bpm SMALLINT NOT NULL,
    drop_rate_bpm_per_min NUMERIC(4,1),
    hrr_60sec SMALLINT,  -- Standard HRR1 metric
    
    -- Quality flags
    is_clean BOOLEAN DEFAULT true,  -- No artifacts detected
    interval_order INTEGER,         -- 1st, 2nd, 3rd rest period in session
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hr_recovery_session ON hr_recovery_intervals(polar_session_id);
CREATE INDEX idx_hr_recovery_strength ON hr_recovery_intervals(strength_session_id);
```

### Session-Level Aggregates

```sql
CREATE TABLE hr_recovery_session_summary (
    id SERIAL PRIMARY KEY,
    polar_session_id INTEGER REFERENCES polar_sessions(id) UNIQUE,
    
    -- Aggregate metrics
    interval_count INTEGER,
    avg_hrr_60sec NUMERIC(4,1),
    min_hrr_60sec SMALLINT,
    max_hrr_60sec SMALLINT,
    avg_rest_duration_sec INTEGER,
    avg_drop_rate NUMERIC(4,1),
    
    -- Flags
    has_poor_recovery BOOLEAN,  -- Any interval with HRR1 < 12
    
    computed_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Acceptance Criteria

- [ ] Peak detection algorithm implemented and tested
- [ ] Recovery interval detection works on sample session
- [ ] HRR metrics calculated correctly (validated against manual calculation)
- [ ] `hr_recovery_intervals` table populated for linked sessions
- [ ] Session summary computed and stored
- [ ] Poor recovery flagged (HRR1 < 12) in red flags report
- [ ] Trend query works: "Show my HRR trend over last 30 days"
- [ ] Visualization: HR curve with rest intervals highlighted

## MCP Interface

```typescript
// Analyze a session's recovery intervals
analyze_recovery_intervals(polar_session_id: number)
  → {
      interval_count: 8,
      intervals: [
        { start: '17:05:30', duration: 65, peak_hr: 145, nadir_hr: 112, hrr_60sec: 33 },
        { start: '17:08:15', duration: 58, peak_hr: 148, nadir_hr: 118, hrr_60sec: 28 },
        ...
      ],
      summary: {
        avg_hrr_60sec: 29.5,
        avg_rest_duration: 62,
        poor_recovery_count: 0
      }
    }

// Get HRR trend
get_hrr_trend(days: number = 30)
  → {
      data_points: [
        { date: '2026-01-09', avg_hrr_60sec: 29.5, session_type: 'strength' },
        { date: '2026-01-08', avg_hrr_60sec: 25.2, session_type: 'strength' },
        ...
      ],
      trend: 'stable',  // or 'improving', 'declining'
      baseline_hrr: 27.3
    }
```

## Technical Notes

### Noise Handling

HR data can have artifacts:
- Motion artifacts (sudden spikes)
- Sensor dropouts (gaps in data)
- Ectopic beats (abnormal single readings)

**Approach**:
1. Apply median filter (window=3) to smooth spikes
2. Interpolate short gaps (< 5 sec)
3. Mark intervals with artifacts as `is_clean = false`

### Edge Cases

1. **Very short rest (< 50 sec)**: Don't record — too short for meaningful HRR
2. **Very long rest (> 5 min)**: Cap at 300 sec — likely workout pause, not inter-set rest
3. **No clear peaks**: Session may be steady-state cardio — skip recovery analysis
4. **Continuous decline**: Cooldown period — don't count as rest interval

### Integration with Workout Plan

Future enhancement: Compare actual rest duration to prescribed rest
```sql
-- Did athlete follow prescribed rest periods?
SELECT 
    ps.set_order,
    ps.notes as prescribed_rest,  -- "90 sec rest"
    ri.duration_seconds as actual_rest
FROM planned_sets ps
JOIN hr_recovery_intervals ri ON ...  -- Time-based join
```

## Open Questions

- [ ] Should we detect rest intervals for endurance sessions too? (Between intervals in HIIT)
- [ ] How to handle supersets? (Rest after pair, not after each exercise)
- [ ] Store raw HR samples permanently, or just computed intervals?
- [ ] What's the minimum data quality for reliable HRR? (% clean samples)

## References

1. Cole CR, et al. (1999). Heart-rate recovery immediately after exercise as a predictor of mortality. *NEJM*. 341(18):1351-7.
2. Jouven X, et al. (2005). Heart-rate profile during exercise as a predictor of sudden death. *NEJM*. 352(19):1951-8.
3. Daanen HA, et al. (2012). The effect of heart rate recovery on endurance exercise performance. *Sports Med*. 42(5):395-410.
