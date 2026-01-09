# Issue 007: Exercise Pattern Classification - Replace Regex with LLM

> **Created**: January 7, 2026
> **Status**: Backlog
> **Priority**: Medium (data quality)

## Problem

On December 29, 2025, a pattern classification script ran using naive keyword matching to assign movement patterns to exercises. The script used regex to match words like "Grip" and "Hang" without semantic understanding.

**Result:** 253 exercises incorrectly linked to "Grip / Hang" pattern, including:
- "Close Grip Bench Press" — "grip" means hand spacing
- "Hang Power Clean" — "hang" means starting position
- "Wide Grip Lat Pulldown" — "grip" means handle width

This corrupted pattern tracking analytics and required manual review of all 253 exercises.

## Root Cause

```python
# BAD: Naive keyword matching
if 'grip' in exercise_name.lower() or 'hang' in exercise_name.lower():
    patterns.append('Grip / Hang')
```

The script outsourced semantic understanding to dumb regex when an LLM should have been used.

## Solution

Replace keyword-based classification with Claude API call:

```python
# GOOD: LLM-powered semantic classification
prompt = f"""
Classify the movement pattern for this exercise: "{exercise_name}"

Available patterns: {pattern_list}

Consider:
- "Grip" in exercise names often means hand width (close, medium, wide), NOT grip training
- "Hang" in Olympic lifts means starting position (bar at hip), NOT hanging exercises
- True Grip/Hang exercises involve sustained grip under load (dead hangs, farmer carries)

Return the primary movement pattern(s) as JSON.
"""
```

## Implementation Notes

1. Batch exercises to reduce API calls
2. Cache results with `source: 'llm_classification'` and timestamp
3. Include confidence scores for review
4. Flag low-confidence classifications for manual review
5. Add negative examples to prompt for common false positives

## Related

- Manual review file: `data/review/grip_hang_pattern_review.csv`
- Fix script: `scripts/apply_grip_hang_review.py`
- Original bad script: (find and document or delete)

## Validation

After implementing:
```cypher
// No naive name_inference relationships should remain
MATCH ()-[r:INVOLVES {source: 'name_inference'}]->()
RETURN count(r)  // Should be 0
```
