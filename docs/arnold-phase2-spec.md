# Arnold Phase 2: Personal Training Data Import

## Internal Codename: SKYNET-READER
> "I'll read everything. I'll learn your patterns. I'll be back... with insights."

---

## Overview

Phase 2 imports the user's 160+ historical workout logs into CYBERDYNE-CORE, enabling Arnold to reason about training history, trends, progression, and patterns.

**Two sub-phases:**
- **Phase 2a**: Raw import - get all data into the graph as-is
- **Phase 2b**: Normalization - clean tags, map exercises, standardize terminology

---

## Phase 2a: Raw Import

### Source Data

**Location**: `/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise/`

**Format**: Markdown files with YAML frontmatter

**Naming pattern**: `YYYY-MM-DD_workout.md`, `YYYY-MM-DD_long_run.md`, `YYYY-MM-DD_longrun.md`

**Count**: ~160 files (Dec 2024 - Nov 2025)

**Sample file structure**:
```markdown
---
date: 2025-11-10
type: strength
tags: [deadlift, sandbag, shouldering, renegade_rows, kettlebell_swings, straight_plane, technique_week]
sport: strength
goals: [groove_hinge, neural_drive, odd_object_skill, work_capacity]
periodization_phase: technique_week
equipment_used: [barbell, sandbag_100lb, dumbbells_20lb, kettlebell_60lb, airdyne]
injury_considerations: [meniscus_tear_preop, avoid_twist_lateral]
deviations: ["Condensed session; no cooldown"]
---

# Workout Card — Mon, Nov 10

**Overview**  
Straight-plane strength tune-up ahead of surgery: one deadlift wave, then a single sandbag/row/swing complex.

## Warm-Up
- Airdyne × **3:00** (easy)

## Main

### 1) Deadlift (straight bar)
- **135×1**, **225×1**, **315×2**, **275×5**, **225×5**, **135×5**  
- *Notes:* Clean wedge and return; form priority over volume.

### 2) Complex (single pass)
- **Sandbag Shouldering (100 lb):** **3/side**  
- **Renegade Rows (20 lb/hand):** **8 total**  
- **KB Swings (60 lb):** **12**

## Cooldown
- **Skipped (time)**

**Summary / Day Notes**  
- Kept everything linear; no knee irritation reported.  
- Simple, effective pre-op dial-in.
```

---

### Scripts to Create

#### 1. `scripts/parse_workout_log.py`

**Purpose**: Parse a single workout markdown file into structured data.

**Input**: Path to markdown file

**Output**: Dictionary with:
```python
{
    "filepath": str,
    "frontmatter": {
        "date": "2025-11-10",
        "type": "strength",
        "tags": ["deadlift", "sandbag", ...],
        "sport": "strength",
        "goals": ["groove_hinge", ...],
        "periodization_phase": "technique_week",
        "equipment_used": ["barbell", ...],
        "injury_considerations": ["meniscus_tear_preop", ...],
        "deviations": ["Condensed session; no cooldown"]
    },
    "sections": [
        {
            "name": "Warm-Up",
            "exercises": [
                {
                    "name_raw": "Airdyne",
                    "duration": "3:00",
                    "notes": "easy",
                    "order": 1
                }
            ]
        },
        {
            "name": "Main",
            "exercises": [
                {
                    "name_raw": "Deadlift (straight bar)",
                    "sets_raw": "135×1, 225×1, 315×2, 275×5, 225×5, 135×5",
                    "sets_parsed": [
                        {"weight": 135, "reps": 1},
                        {"weight": 225, "reps": 1},
                        {"weight": 315, "reps": 2},
                        {"weight": 275, "reps": 5},
                        {"weight": 225, "reps": 5},
                        {"weight": 135, "reps": 5}
                    ],
                    "total_sets": 6,
                    "notes": "Clean wedge and return; form priority over volume.",
                    "order": 2
                },
                {
                    "name_raw": "Sandbag Shouldering (100 lb)",
                    "sets_raw": "3/side",
                    "reps": "3/side",
                    "weight": 100,
                    "weight_unit": "lb",
                    "order": 3,
                    "complex_id": "complex_1"
                },
                ...
            ]
        }
    ],
    "summary": "Kept everything linear; no knee irritation reported..."
}
```

**Parsing challenges to handle:**

| Format | Example | Interpretation |
|--------|---------|----------------|
| Weight × Reps | `135×1` | 135 lbs, 1 rep |
| Multiple sets inline | `135×1, 225×1, 315×2` | 3 separate sets |
| Sets × Reps | `3×5` | 3 sets of 5 reps |
| Unilateral | `3/side` | 3 reps per side |
| Total reps | `8 total` | 8 reps total |
| Duration | `3:00` | 3 minutes |
| Bodyweight | No weight listed | "bodyweight" |
| Weight in name | `KB Swings (60 lb)` | Extract 60 lb |
| Weight in name | `sandbag_100lb` | Extract 100 lb |
| Range | `8-10` | Rep range |

**Libraries to use:**
- `pyyaml` or `python-frontmatter` for YAML parsing
- `re` for regex parsing of exercise notation
- `pathlib` for file handling

---

#### 2. `scripts/import_workout_history.py`

**Purpose**: Batch import all workout files into Neo4j.

**Process:**
1. Scan source directory for markdown files
2. Parse each file with `parse_workout_log.py`
3. Create nodes and relationships in Neo4j
4. Track statistics and failures

**Node creation:**

```cypher
// Workout node
CREATE (w:Workout {
    id: "2025-11-10_strength",
    date: date("2025-11-10"),
    type: "strength",
    sport: "strength",
    periodization_phase: "technique_week",
    tags_raw: ["deadlift", "sandbag", ...],
    goals_raw: ["groove_hinge", ...],
    equipment_raw: ["barbell", ...],
    injury_considerations: ["meniscus_tear_preop", ...],
    deviations: ["Condensed session; no cooldown"],
    summary: "Kept everything linear...",
    source_file: "2025-11-10_workout.md"
})

// ExerciseInstance nodes
CREATE (ei:ExerciseInstance {
    id: "2025-11-10_strength_ex_2",
    exercise_name_raw: "Deadlift (straight bar)",
    section: "main",
    sets_raw: "135×1, 225×1, 315×2, 275×5, 225×5, 135×5",
    total_sets: 6,
    total_reps: 19,
    max_weight: 315,
    weights: [135, 225, 315, 275, 225, 135],
    reps: [1, 1, 2, 5, 5, 5],
    notes: "Clean wedge and return; form priority over volume.",
    order_in_workout: 2
})

// Relationships
MATCH (w:Workout {id: "2025-11-10_strength"})
MATCH (ei:ExerciseInstance {id: "2025-11-10_strength_ex_2"})
CREATE (w)-[:CONTAINS]->(ei)
```

**Exercise linking (fuzzy match):**

```python
def find_matching_exercise(raw_name: str, graph: ArnoldGraph) -> Optional[str]:
    """
    Attempt to match raw exercise name to existing Exercise node.
    
    Returns exercise_id if match found, None otherwise.
    """
    # Normalize: lowercase, remove parentheticals, strip whitespace
    normalized = normalize_exercise_name(raw_name)
    
    # Try exact match first
    result = graph.execute_query("""
        MATCH (e:Exercise)
        WHERE toLower(e.name) = $name
        RETURN e.id
    """, {"name": normalized})
    
    if result:
        return result[0]["e.id"]
    
    # Try fuzzy match
    candidates = graph.execute_query("""
        MATCH (e:Exercise)
        RETURN e.id, e.name
    """)
    
    best_match = fuzzy_match(normalized, candidates, threshold=0.8)
    return best_match
```

**Temporal chain:**

```cypher
// After all workouts imported, create PREVIOUS relationships
MATCH (w:Workout)
WITH w ORDER BY w.date
WITH collect(w) as workouts
UNWIND range(1, size(workouts)-1) as i
WITH workouts[i] as current, workouts[i-1] as previous
CREATE (current)-[:PREVIOUS]->(previous)
```

**Output:**
- Print progress: "Imported 50/160 workouts..."
- Track failures: `{"file": "2025-01-15_workout.md", "error": "Parse error on line 23"}`
- Final summary: nodes created, relationships created, match rate, failures

---

#### 3. `scripts/validate_phase2.py`

**Purpose**: Verify Phase 2a import succeeded.

**Queries to run:**

```cypher
// 1. Total workouts
MATCH (w:Workout) RETURN count(w) as total_workouts

// 2. Date range
MATCH (w:Workout)
RETURN min(w.date) as earliest, max(w.date) as latest

// 3. Total exercise instances
MATCH (ei:ExerciseInstance) RETURN count(ei) as total_instances

// 4. Instances linked to Exercise nodes
MATCH (ei:ExerciseInstance)-[:INSTANCE_OF]->(e:Exercise)
RETURN count(ei) as linked_instances

// 5. Match rate
MATCH (ei:ExerciseInstance)
OPTIONAL MATCH (ei)-[:INSTANCE_OF]->(e:Exercise)
RETURN 
    count(ei) as total,
    count(e) as linked,
    round(100.0 * count(e) / count(ei), 1) as match_rate_pct

// 6. Unmatched exercises (for Phase 2b)
MATCH (ei:ExerciseInstance)
WHERE NOT (ei)-[:INSTANCE_OF]->(:Exercise)
RETURN ei.exercise_name_raw as raw_name, count(*) as occurrences
ORDER BY occurrences DESC
LIMIT 50

// 7. Volume by week (last 8 weeks from most recent workout)
MATCH (w:Workout)-[:CONTAINS]->(ei:ExerciseInstance)
WHERE w.date >= date() - duration('P56D')
WITH date.truncate('week', w.date) as week, count(ei) as sets
RETURN week, sets
ORDER BY week

// 8. Temporal chain intact
MATCH path = (w1:Workout)-[:PREVIOUS*]->(w2:Workout)
WHERE NOT ()-[:PREVIOUS]->(w1)
RETURN length(path) + 1 as chain_length

// 9. Workouts by type
MATCH (w:Workout)
RETURN w.type, count(*) as count
ORDER BY count DESC

// 10. Most common exercises
MATCH (ei:ExerciseInstance)
RETURN ei.exercise_name_raw as exercise, count(*) as times_performed
ORDER BY times_performed DESC
LIMIT 20
```

**Expected results (approximate):**
- ~160 workouts
- 800-1500 exercise instances
- 80%+ match rate (stretch goal)
- Complete temporal chain
- No parse failures (or <5%)

---

### Phase 2a Success Criteria

- [ ] All ~160 workout files processed
- [ ] Workout nodes contain all frontmatter fields
- [ ] ExerciseInstance nodes capture sets/reps/weight
- [ ] 70%+ instances linked to existing Exercise nodes
- [ ] Temporal chain complete (can traverse workout history)
- [ ] Parse failures logged (not crashed)
- [ ] Validation queries pass

---

## Phase 2b: Tag Normalization

> "Your tags are a mess. I'll fix them." — SKYNET-READER

### Purpose

Create a canonical taxonomy layer that maps messy user tags to standardized terms for consistent querying and analysis.

### Survey the Chaos

First, extract all unique values that need normalization:

```cypher
// All unique tags
MATCH (w:Workout)
UNWIND w.tags_raw as tag
RETURN tag, count(*) as freq
ORDER BY freq DESC

// All unique exercise names
MATCH (ei:ExerciseInstance)
RETURN ei.exercise_name_raw as name, count(*) as freq
ORDER BY freq DESC

// All unique goals
MATCH (w:Workout)
UNWIND w.goals_raw as goal
RETURN goal, count(*) as freq
ORDER BY freq DESC

// All unique periodization phases
MATCH (w:Workout)
RETURN w.periodization_phase as phase, count(*) as freq
ORDER BY freq DESC

// All unique equipment
MATCH (w:Workout)
UNWIND w.equipment_raw as equip
RETURN equip, count(*) as freq
ORDER BY freq DESC
```

Export these to CSV/JSON for review.

---

### Schema Additions

```cypher
// Canonical tag nodes
(:CanonicalTag {
    id: string,
    name: string,              // "kettlebell_swing"
    display_name: string,      // "Kettlebell Swing"
    category: string,          // "exercise", "intensity", "muscle_group", "equipment", "goal"
    description: string
})

// Alias relationships
(:RawTag {name: "KB Swings"})-[:ALIAS_OF]->(:CanonicalTag {name: "kettlebell_swing"})
(:RawTag {name: "kb swing"})-[:ALIAS_OF]->(:CanonicalTag {name: "kettlebell_swing"})
(:RawTag {name: "kettlebell swings"})-[:ALIAS_OF]->(:CanonicalTag {name: "kettlebell_swing"})

// Or simpler: just store aliases as array property
(:CanonicalTag {
    name: "kettlebell_swing",
    aliases: ["KB Swings", "kb swing", "kettlebell swings", "kb swings"]
})
```

---

### Normalization Categories

#### 1. Exercise Names

| Raw | Canonical |
|-----|-----------|
| Deadlift (straight bar) | conventional_deadlift |
| conventional DL | conventional_deadlift |
| deads | conventional_deadlift |
| KB Swings (60 lb) | kettlebell_swing |
| kettlebell swings | kettlebell_swing |
| Pull-Ups | pull_up |
| Pullups | pull_up |
| pull ups | pull_up |
| Sandbag Shouldering | sandbag_shoulder_to_shoulder |

#### 2. Intensity/Effort

| Raw | Canonical |
|-----|-----------|
| easy | intensity_light |
| light | intensity_light |
| medium | intensity_moderate |
| moderate | intensity_moderate |
| RPE 5-6 | intensity_moderate |
| hard | intensity_hard |
| heavy | intensity_hard |
| max effort | intensity_max |
| all out | intensity_max |

#### 3. Muscle Groups

| Raw | Canonical |
|-----|-----------|
| posterior_chain | muscle_group_posterior_chain |
| post chain | muscle_group_posterior_chain |
| glutes | muscle_group_glutes |
| hams | muscle_group_hamstrings |
| hammies | muscle_group_hamstrings |
| quads | muscle_group_quadriceps |

#### 4. Movement Patterns

| Raw | Canonical |
|-----|-----------|
| hinge | movement_hip_hinge |
| hip_hinge | movement_hip_hinge |
| groove_hinge | movement_hip_hinge |
| squat | movement_squat |
| push | movement_push |
| pull | movement_pull |
| carry | movement_carry |

#### 5. Periodization

| Raw | Canonical |
|-----|-----------|
| technique_week | phase_technique |
| build | phase_accumulation |
| build_week_1 | phase_accumulation |
| deload | phase_deload |
| recovery | phase_deload |
| peak | phase_realization |

#### 6. Goals

| Raw | Canonical |
|-----|-----------|
| groove_hinge | goal_movement_quality |
| neural_drive | goal_strength |
| work_capacity | goal_conditioning |
| odd_object_skill | goal_skill_acquisition |

---

### Scripts to Create

#### 1. `scripts/export_raw_tags.py`

Export all unique raw values to JSON for review:

```python
def export_raw_tags(graph: ArnoldGraph, output_path: str):
    """Export all unique tags/names for normalization review."""
    
    exports = {
        "exercise_names": query_unique_exercise_names(graph),
        "tags": query_unique_tags(graph),
        "goals": query_unique_goals(graph),
        "equipment": query_unique_equipment(graph),
        "phases": query_unique_phases(graph),
    }
    
    with open(output_path, 'w') as f:
        json.dump(exports, f, indent=2)
```

#### 2. `data/normalization/mappings.yaml`

Human-editable mapping file:

```yaml
# Normalization mappings for Arnold
# Edit this file to add/modify mappings

exercise_names:
  conventional_deadlift:
    display: "Conventional Deadlift"
    aliases:
      - "Deadlift (straight bar)"
      - "conventional DL"
      - "deads"
      - "deadlift"
      - "straight bar deadlift"
    links_to_exercise_id: "barbell_deadlift"  # from free-exercise-db
    
  kettlebell_swing:
    display: "Kettlebell Swing"
    aliases:
      - "KB Swings"
      - "kb swing"
      - "kettlebell swings"
      - "KB swings (60 lb)"
      - "KB swings (70 lb)"
    links_to_exercise_id: "kettlebell_swing"

intensity:
  intensity_light:
    display: "Light"
    aliases: ["easy", "light", "recovery", "RPE 1-3"]
    
  intensity_moderate:
    display: "Moderate"
    aliases: ["medium", "moderate", "RPE 4-6", "steady"]
    
  intensity_hard:
    display: "Hard"
    aliases: ["hard", "heavy", "challenging", "RPE 7-8"]
    
  intensity_max:
    display: "Maximum"
    aliases: ["max effort", "all out", "RPE 9-10", "PR attempt"]

# ... more categories
```

#### 3. `scripts/apply_normalization.py`

Apply mappings to graph:

```python
def apply_normalization(graph: ArnoldGraph, mappings_path: str):
    """
    Apply normalization mappings to the graph.
    
    1. Create CanonicalTag nodes
    2. Link ExerciseInstance nodes to Exercise nodes via normalized names
    3. Add normalized_tags array to Workout nodes
    """
    
    with open(mappings_path) as f:
        mappings = yaml.safe_load(f)
    
    # Create canonical nodes
    for category, items in mappings.items():
        for canonical_name, config in items.items():
            graph.execute_write("""
                MERGE (ct:CanonicalTag {name: $name})
                SET ct.display_name = $display,
                    ct.category = $category,
                    ct.aliases = $aliases
            """, {
                "name": canonical_name,
                "display": config["display"],
                "category": category,
                "aliases": config["aliases"]
            })
    
    # Update ExerciseInstance -> Exercise links
    for canonical_name, config in mappings.get("exercise_names", {}).items():
        if "links_to_exercise_id" in config:
            for alias in config["aliases"]:
                graph.execute_write("""
                    MATCH (ei:ExerciseInstance)
                    WHERE ei.exercise_name_raw =~ $pattern
                    MATCH (e:Exercise {id: $exercise_id})
                    MERGE (ei)-[:INSTANCE_OF]->(e)
                """, {
                    "pattern": f"(?i).*{re.escape(alias)}.*",
                    "exercise_id": config["links_to_exercise_id"]
                })
    
    # Add normalized tags to Workouts
    # ... similar pattern
```

#### 4. `scripts/suggest_mappings.py`

LLM-assisted mapping suggestions for unmapped items:

```python
def suggest_mappings(unmapped_items: List[str], existing_mappings: dict) -> dict:
    """
    Use Claude to suggest mappings for unmapped items.
    
    Returns dict of suggestions for human review.
    """
    
    prompt = f"""
    Given these existing canonical categories and their aliases:
    {json.dumps(existing_mappings, indent=2)}
    
    Suggest mappings for these unmapped items:
    {json.dumps(unmapped_items, indent=2)}
    
    For each item, either:
    1. Map to an existing canonical term
    2. Suggest a new canonical term if none fit
    
    Return JSON format:
    {{
        "raw_term": {{
            "canonical": "canonical_name",
            "confidence": 0.9,
            "is_new_canonical": false,
            "reasoning": "..."
        }}
    }}
    """
    
    # Call Claude API
    response = call_claude(prompt)
    return parse_suggestions(response)
```

#### 5. `scripts/validate_normalization.py`

Verify normalization coverage:

```cypher
// Coverage rate for exercises
MATCH (ei:ExerciseInstance)
OPTIONAL MATCH (ei)-[:INSTANCE_OF]->(e:Exercise)
RETURN 
    count(ei) as total,
    count(e) as normalized,
    round(100.0 * count(e) / count(ei), 1) as coverage_pct

// Remaining unmapped
MATCH (ei:ExerciseInstance)
WHERE NOT (ei)-[:INSTANCE_OF]->(:Exercise)
RETURN ei.exercise_name_raw as unmapped, count(*) as freq
ORDER BY freq DESC

// Tags normalized
MATCH (w:Workout)
WHERE w.tags_normalized IS NOT NULL
RETURN count(w) as workouts_with_normalized_tags
```

---

### Normalization Workflow

```
┌─────────────────────────────────────────────────────────┐
│  1. EXPORT                                              │
│     scripts/export_raw_tags.py                          │
│     → data/normalization/raw_tags.json                  │
└─────────────────────┬───────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────┐
│  2. REVIEW + SUGGEST                                    │
│     Manual review of raw_tags.json                      │
│     scripts/suggest_mappings.py (LLM-assisted)          │
│     → Human edits data/normalization/mappings.yaml      │
└─────────────────────┬───────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────┐
│  3. APPLY                                               │
│     scripts/apply_normalization.py                      │
│     Creates CanonicalTag nodes                          │
│     Links ExerciseInstance → Exercise                   │
│     Adds normalized_tags to Workouts                    │
└─────────────────────┬───────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────┐
│  4. VALIDATE                                            │
│     scripts/validate_normalization.py                   │
│     Check coverage rates                                │
│     Flag remaining unmapped                             │
│     Iterate until 95%+ coverage                         │
└─────────────────────────────────────────────────────────┘
```

---

### Phase 2b Success Criteria

- [ ] All unique raw values exported for review
- [ ] mappings.yaml created with initial mappings
- [ ] 90%+ ExerciseInstances linked to Exercise nodes
- [ ] CanonicalTag nodes created for all categories
- [ ] Workouts have normalized_tags array
- [ ] Validation shows <5% unmapped items
- [ ] LLM suggestion pipeline working for new items

---

## Directory Structure Additions

```
arnold/
├── scripts/
│   ├── parse_workout_log.py       # NEW: Parse single workout file
│   ├── import_workout_history.py  # NEW: Batch import workouts
│   ├── validate_phase2.py         # NEW: Phase 2a validation
│   ├── export_raw_tags.py         # NEW: Export for normalization
│   ├── suggest_mappings.py        # NEW: LLM-assisted suggestions
│   ├── apply_normalization.py     # NEW: Apply mappings to graph
│   └── validate_normalization.py  # NEW: Phase 2b validation
├── data/
│   ├── normalization/             # NEW
│   │   ├── raw_tags.json          # Exported unique values
│   │   ├── mappings.yaml          # Human-edited mappings
│   │   └── suggestions.json       # LLM suggestions for review
│   └── user/
│       └── workouts/              # Symlink or copy of workout logs
└── src/
    └── arnold/
        ├── parser.py              # NEW: Workout parsing utilities
        └── normalizer.py          # NEW: Normalization utilities
```

---

## Configuration Additions

```yaml
# config/arnold.yaml additions

import:
  workout_source_path: "/Users/brock/Documents/GitHub/infinite_exercise_planner/data/infinite_exercise/"
  # Or if symlinked:
  # workout_source_path: "data/user/workouts/"
  
normalization:
  mappings_path: "data/normalization/mappings.yaml"
  auto_suggest_threshold: 0.7  # Confidence threshold for auto-accepting LLM suggestions
  
parsing:
  # Regex patterns for exercise notation
  weight_reps_pattern: '(\d+)\s*[×x]\s*(\d+)'
  sets_reps_pattern: '(\d+)\s*[×x]\s*(\d+)'
  per_side_pattern: '(\d+)\s*/\s*side'
  duration_pattern: '(\d+):(\d+)'
```

---

## Testing

### Unit Tests for Parser

```python
# tests/test_parser.py

def test_parse_weight_reps():
    assert parse_set("135×1") == {"weight": 135, "reps": 1}
    assert parse_set("225x5") == {"weight": 225, "reps": 5}
    
def test_parse_per_side():
    assert parse_set("3/side") == {"reps": "3/side", "unilateral": True}
    
def test_parse_duration():
    assert parse_set("3:00") == {"duration": "3:00", "duration_seconds": 180}
    
def test_parse_bodyweight():
    assert parse_set("10") == {"reps": 10, "weight": "bodyweight"}
    
def test_extract_weight_from_name():
    assert extract_weight("KB Swings (60 lb)") == {"weight": 60, "unit": "lb"}
    assert extract_weight("sandbag_100lb") == {"weight": 100, "unit": "lb"}
    assert extract_weight("Pull-ups") == {"weight": "bodyweight"}
```

### Integration Tests

```python
# tests/test_import.py

def test_full_import_pipeline():
    """Test importing a sample workout file end-to-end."""
    # Parse
    parsed = parse_workout_log("tests/fixtures/sample_workout.md")
    assert parsed["frontmatter"]["date"] == "2025-11-10"
    assert len(parsed["sections"]) >= 2
    
    # Import
    import_workout(graph, parsed)
    
    # Verify
    result = graph.execute_query("""
        MATCH (w:Workout {date: date("2025-11-10")})
        RETURN w
    """)
    assert len(result) == 1
```

---

## Open Questions for Implementation

1. **Weight extraction priority**: If weight appears in both exercise name ("KB Swings (60 lb)") and set notation, which takes precedence?

2. **Complex/circuit handling**: Should exercises in a complex share a `complex_id`, or just track `section` and `order`?

3. **Failed parses**: Create partial nodes with `parse_error: true` flag, or skip entirely and log?

4. **Incremental import**: Support re-running import to add new workouts without duplicating existing ones?

5. **Backlinks**: Should ExerciseInstance link back to source file for easy reference?

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| parse_workout_log.py | 2-3 hours |
| import_workout_history.py | 2-3 hours |
| validate_phase2.py | 1 hour |
| Testing & debugging | 2-3 hours |
| **Phase 2a Total** | **7-10 hours** |
| | |
| export_raw_tags.py | 30 min |
| Initial mappings.yaml | 1-2 hours (manual) |
| apply_normalization.py | 1-2 hours |
| suggest_mappings.py (LLM) | 1-2 hours |
| validate_normalization.py | 30 min |
| Iteration & refinement | 2-3 hours |
| **Phase 2b Total** | **6-10 hours** |

---

## Appendix: Sample Workout Files for Testing

Recommend copying these specific files to `tests/fixtures/` for unit testing:

1. `2025-11-10_workout.md` - Standard strength session with complexes
2. `2025-11-07_workout.md` - Heavy assessment day with failures
3. `2025-11-04_workout.md` - Upper push/pull with deviations
4. `2024-12-08_long_run.md` - Endurance session (different format)
5. `2025-02-09_long_run.md` - Another run for format variation

These cover the main format variations in the dataset.

---

*"I need your clothes, your boots, and your workout logs."*
*— T-800, probably*
