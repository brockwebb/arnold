# Handoff: Annotation System Architecture Fix

**Date:** 2025-01-06
**Previous Thread:** annotation-system-analytics-gaps
**Status:** Architecture clarified, implementation needed

## Key Insight

We built the wrong thing. The annotation system was implemented as suppression logic in the analytics layer. This violates the core architecture principle:

| Layer | Role | What it does |
|-------|------|--------------|
| **Analytics (Postgres)** | Reports facts | Numbers without judgment |
| **Graph (Neo4j)** | Shows relationships | Annotation EXPLAINS Reading |
| **Intelligence (Arnold)** | Interprets | Synthesizes data + context, decides what matters |

**The WBC Example:** User's white blood cell count is always just below "normal" range. Has been stable for 15 years. Every lab flags it as "abnormal." But that IS his normal - a change FROM that baseline would be concerning, not the value itself.

Two types of annotations:
- **Suppress:** "Data is gone, stop mentioning it" → Still wrong to hide at tool level
- **Contextualize:** "This is my baseline" → Critical context for interpretation

Both are FACTS that should be visible. Arnold (intelligence layer) decides what to say about them.

## What Needs to Change

### 1. Revert `check_red_flags()` to Dumb Reporting

**File:** `/Users/brock/Documents/GitHub/arnold/src/arnold-analytics-mcp/arnold_analytics/server.py`

Remove:
- `check_before_warning()` function (lines ~128-175)
- All suppression logic in `check_red_flags()`
- The `acknowledged` array concept

The function should just report observations:
```python
async def check_red_flags():
    """Report observations for Arnold to interpret."""
    # ... query data ...
    
    observations = []
    
    # HRV trend
    if hrv_declined_15_pct:
        observations.append({
            "type": "hrv_trend",
            "observation": f"HRV down {pct}% over recent days",
            "data": {"recent_avg": 45, "prior_avg": 52}
        })
    
    # Data gaps
    if days_since_hrv > 3:
        observations.append({
            "type": "data_gap", 
            "observation": f"No HRV data for {days} days",
            "last_reading": "2025-01-01"
        })
    
    # Pattern gaps
    if missing_patterns:
        observations.append({
            "type": "pattern_gap",
            "observation": f"No recent work: {patterns}",
            "days_since": 10
        })
    
    return {"observations": observations}
```

No suppression. No "acknowledged." Just facts.

### 2. Migrate Annotations to Neo4j

Current Postgres table `data_annotations` should become Neo4j nodes:

```cypher
// Create Annotation nodes
CREATE (a:Annotation {
    id: 'ann_001',
    annotation_type: 'data_gap',  // or 'baseline', 'expected', 'context'
    explanation: 'Sleep data unrecoverable - Ultrahuman app not opened Dec 7-31',
    created_at: datetime(),
    date_start: date('2024-12-07'),
    date_end: date('2024-12-31'),
    tags: ['sleep', 'ultrahuman', 'data_gap']
})

// Link to what it explains
MATCH (a:Annotation {id: 'ann_001'})
MATCH (b:BiometricReading) 
WHERE b.metric = 'sleep' AND b.date >= date('2024-12-07') AND b.date <= date('2024-12-31')
CREATE (a)-[:EXPLAINS]->(b)
```

Annotation types:
- `suppress` - Known gap, can't recover
- `baseline` - This IS normal for this person (like WBC example)
- `expected` - Temporary known deviation (post-surgery HRV)
- `context` - General explanation

### 3. Journal System Already Does This

`LogEntry` nodes with `EXPLAINS`, `DOCUMENTS`, `FEEDBACK` relationships are the same pattern. Annotations and LogEntries both provide context.

```cypher
// LogEntry explaining an observation
(:LogEntry {summary: "Birthday workout - expected HRV suppression"})-[:EXPLAINS]->(:BiometricReading)
```

### 4. Briefing Tools Should Include Context

When Arnold calls `load_briefing` or `check_red_flags`, the response should include:
- The raw observations
- Any related annotations/log entries (as additional facts, not filters)

Arnold then synthesizes: "HRV is down 15%, but there's an annotation noting this is expected post-surgery recovery."

## Files to Modify

1. **`/Users/brock/Documents/GitHub/arnold/src/arnold-analytics-mcp/arnold_analytics/server.py`**
   - Remove `check_before_warning()` 
   - Simplify `check_red_flags()` to report observations without suppression
   - Keep `get_annotations_for_period()` if useful for queries, but don't use for filtering

2. **Neo4j Schema**
   - Add `:Annotation` node type
   - Add `EXPLAINS` relationship from Annotation to data nodes
   - Migration script for existing `data_annotations` rows

3. **`/Users/brock/Documents/GitHub/arnold/src/arnold-memory-mcp/`**
   - `load_briefing` should query for annotations related to current period
   - Include them in briefing as context, not filters

## Existing Annotations to Migrate

From `data_annotations` table:
```
#3: Jan 3-5 HRV - birthday workout
#5: Dec 7-31 sleep gap - Ultrahuman app
#6: Dec 7-31 recovery score gap
```

Plus the `flag_overrides` table has:
```
acwr override - post-surgery baseline expected high
```

## Design Principle

> "Data is data. Annotations are data about data. Both are just facts. No judgment at the storage layer."

The Census analogy: "Seasonally adjusted" doesn't hide the raw number. It's additional context sitting alongside. An analyst sees both and synthesizes.

Tools can be smart (imputation, calculation, aggregation). Tools should NOT hide information. That's interpretation disguised as data.

## Questions for Next Thread

1. Should we keep `data_annotations` in Postgres as source of truth and sync to Neo4j? Or move entirely to Neo4j?
2. Do we need an MCP tool for creating annotations, or is that done manually/via journal?
3. Should annotations have an `active` flag, or is that also interpretation that belongs in the intelligence layer?

## Related Files

- Transcript: `/mnt/transcripts/2026-01-06-03-16-54-annotation-system-analytics-gaps.txt`
- Training metrics doc: `/Users/brock/Documents/GitHub/arnold/docs/TRAINING_METRICS.md`
- ADR-001 (hybrid architecture): `/Users/brock/Documents/GitHub/arnold/docs/adr/`
