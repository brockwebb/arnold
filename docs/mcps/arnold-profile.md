# arnold-profile-mcp

> **Purpose:** Athlete identity, equipment inventory, and biometric observations

## What This MCP Owns

- **Person** node and demographics
- **EquipmentInventory** and equipment items
- **Activity** (sports/activities the athlete participates in)
- **Observation** (body weight, HRV, resting HR, etc.)
- Exercise search/lookup

## Boundaries

| This MCP Does | This MCP Does NOT |
|---------------|-------------------|
| Create/update athlete profile | Create workout plans |
| Manage equipment inventory | Log workouts |
| Record biometric observations | Calculate training metrics |
| Search canonical exercises | Check exercise safety |
| Track activities/sports | Manage coaching memory |

## Tools

### Profile Management
| Tool | Purpose |
|------|---------|
| `intake_profile` | Guided profile creation workflow |
| `complete_intake` | Process intake questionnaire |
| `create_profile` | Direct profile creation |
| `get_profile` | Retrieve current profile |
| `update_profile` | Update profile field |

### Exercise Lookup
| Tool | Purpose |
|------|---------|
| `find_canonical_exercise` | Find exercise by name (returns single match) |
| `search_exercises` | Full-text search with fuzzy matching (returns candidates) |

### Equipment
| Tool | Purpose |
|------|---------|
| `setup_equipment_inventory` | Create inventory with all equipment |
| `list_equipment` | List all equipment inventories |

### Activities
| Tool | Purpose |
|------|---------|
| `add_activity` | Add sport/activity |
| `list_activities` | List all activities |

### Observations
| Tool | Purpose |
|------|---------|
| `record_observation` | Record body metric (weight, HRV, etc.) |

## Key Decisions

### Full-Text Search with Aliases (Jan 2026)

**Context:** Original `find_canonical_exercise` used exact string matching (`toLower`). Failed on common variations like "KB swing" or "pull up".

**Decision:** Implement three-layer architecture:
1. **Semantic layer (Claude)** — Normalizes user input, selects from candidates
2. **Retrieval layer (Neo4j)** — Full-text index + vector index return candidates
3. **Enrichment layer (Graph)** — Exercise nodes have `aliases` property

**Consequence:** Claude can find exercises even with abbreviations, typos, or alternate names. `search_exercises` returns candidates; Claude picks the best match.

### Exercise Search Index

**Index:** `exercise_search` (full-text on `[name, aliases]`)

```cypher
CALL db.index.fulltext.queryNodes('exercise_search', 'kettlebell swing~')
YIELD node, score
```

### LOINC Codes for Observations

**Context:** Need standard terminology for biometric data.

**Decision:** Use LOINC codes for common observations:
- Body weight: `29463-7`
- Resting heart rate: `8867-4`
- HRV: (no standard code, use concept name)

**Consequence:** Observations can be mapped to clinical standards if needed. FHIR-compatible export possible.

### Profile as JSON + Graph

**Context:** Profile data needs to be accessible without Neo4j (for person_id resolution).

**Decision:** Store profile in both:
- `data/profile.json` — Quick local access
- Neo4j Person node — Graph relationships

**Consequence:** Slight duplication, but enables MCPs to resolve person_id without Neo4j query.

## Data Model

```
(Person)-[:HAS_ROLE]->(Athlete)
(Person)-[:HAS_ACCESS_TO]->(EquipmentInventory)
(EquipmentInventory)-[:CONTAINS]->(EquipmentCategory)
(Person)-[:PARTICIPATES_IN]->(Activity)
(Person)-[:HAS_OBSERVATION]->(Observation)
(Observation)-[:HAS_CONCEPT]->(ObservationConcept)
```

## Dependencies

- **Neo4j** — All data storage
- **data/profile.json** — Local profile cache

## Known Issues / Tech Debt

1. **Person vs Athlete** — Some queries check for Athlete role, others go direct to Person. Inconsistent. Should standardize on Person with optional roles.
