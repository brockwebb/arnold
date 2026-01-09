# Arnold MCP Architecture - Specialist Team Roster

## Philosophy: Olympic Athlete Support Model

Like a world-class athlete has a specialized support team (strength coach, nutritionist, physical therapist, team doctor, performance analyst), Arnold uses a roster of domain-specific MCP servers. Each MCP is a specialist with deep expertise in one area, coordinated by the head coach (orchestrator).

**Principles:**
- **Separation of Concerns**: Each MCP owns one domain
- **Graph-First Thinking**: Journey and relationships live in Neo4j, not flat files
- **Minimal State**: MCPs query fresh data, don't cache stale context
- **Incremental Complexity**: Build Phase 2 foundation, expand to Phase 3+ specialists

---

## MCP Roster

### Phase 2 (Active Development)

**arnold-orchestrator-mcp** (Head Coach)
- **Role**: Daily coordination and system awareness
- **Responsibilities**:
  - System context (current user, principles, alerts)
  - Tool routing guidance ("use neo4j-mcp for graph queries")
  - Real-time alert surfacing (check-in overdue, concerning patterns)
  - Journey map query builder (phases/goals/checkpoints from Neo4j)
- **State**: Minimal (`/data/orchestrator/user_session.json`, `system_principles.txt`)
- **Queries**: Neo4j + profile.json for fresh context

**arnold-checkin-mcp** (Team Meeting Facilitator)
- **Role**: Periodic holistic review across all domains
- **Responsibilities**:
  - 14-day check-in workflow (configurable frequency)
  - Cross-domain synthesis (training + medical + recovery + nutrition)
  - Goal adjustment conversations
  - Training phase transitions
- **Consumes Tools From**: All specialist MCPs
- **Workflow**:
  1. Gather summaries from training, medical, recovery (future), nutrition (future)
  2. Lead structured conversation
  3. Adjust goals/phases based on feedback
  4. Update check-in timestamp

**arnold-training-mcp** (Strength & Conditioning Coach)
- **Role**: Workout logging, programming, exercise selection
- **Responsibilities**:
  - Parse messy workout notes → structured JSON
  - Log workouts (write to JSON + Neo4j)
  - Retrieve/update past workouts
  - Training phase execution
  - Volume/intensity progression tracking
  - Exercise variation management
- **Tools**: Parse, log, query, update workouts; set training phases

**arnold-profile-mcp** (Administrative Support)
- **Role**: Manage Person digital twin and baseline data
- **Responsibilities**:
  - Profile CRUD (create, read, update demographics)
  - Equipment inventory management
  - Goals and constraints (create, update, archive)
  - Observations (body weight, HR, HRV time-series)
  - Data export/backup (Neo4j → JSON)
- **Storage**: `/data/profile.json`, `/data/observations.json`

**arnold-medical-mcp** (Team Doctor)
- **Phase 2 Scope**: Injury and constraint tracking only
  - Log injuries with body part, severity, status
  - Track rehab protocols (TRAK ontology foundation)
  - Constraint state (active, resolved, monitoring)
- **Phase 3+ Scope** (see ROADMAP):
  - Medical record integration
  - Lab result analysis
  - Medication/supplement tracking
  - Vital signs monitoring
- **Storage**: Part of profile.json (Phase 2), separate medical graph (Phase 3+)

### Phase 3+ (Future Specialists)

**arnold-nutrition-mcp** (Nutritionist)
- Meal logging and macro tracking
- Supplement protocols
- Nutrition timing strategies
- Adherence scoring

**arnold-recovery-mcp** (Physical Therapist)
- Sleep quality analysis
- Mobility and flexibility work
- Soreness and readiness scoring
- Recovery protocol recommendations

**arnold-analytics-mcp** (Performance Analyst)
- Progression metrics and visualization
- Pattern detection (overtraining, plateau identification)
- Predictive modeling (injury risk, performance peaks)
- Dashboard generation

---

## Tool Distribution

### arnold-orchestrator-mcp
```python
get_system_context(person_id) → user, alerts, principles, system stats
get_journey_map(person_id) → query Neo4j for phases/goals/checkpoints
get_tool_usage_guide() → routing instructions for which MCP handles what
check_alerts(person_id) → overdue check-ins, concerning patterns
```

### arnold-checkin-mcp
```python
start_checkin(person_id) → holistic 14-day review workflow
review_training_compliance(person_id, days) → volume, intensity, adherence
review_injury_status(person_id) → rehab progress, new constraints
adjust_goals(person_id, goal_id, updates) → modify or archive goals
set_next_checkin(person_id, days_from_now) → snooze or reschedule
```

### arnold-training-mcp
```python
parse_workout_input(person_id, raw_text) → LLM parse → structured JSON
log_workout(person_id, workout_json) → write JSON file + Neo4j nodes
get_workout(workout_id) → retrieve specific workout
update_workout(workout_id, changes) → modify past workout
set_training_phase(person_id, phase, start, end, target_goal) → macro cycle
get_training_summary(person_id, window_days) → volume, intensity, compliance
get_progression_metrics(person_id, metric_type) → strength, endurance trends
```

### arnold-profile-mcp
```python
create_profile(name, age, sex, ...) → initialize Person digital twin
update_profile(person_id, field, value) → demographics, preferences
get_profile(person_id) → full profile data

add_goal(person_id, type, description, target_date, priority)
update_goal(goal_id, updates)
get_active_goals(person_id)

add_constraint(person_id, type, description, severity, body_part)
update_constraint(constraint_id, updates)
get_active_constraints(person_id)

set_equipment_access(person_id, equipment_list)
get_equipment_access(person_id)

record_observation(person_id, concept, value, date) → weight, HR, HRV
get_observation_history(person_id, concept, start, end) → time-series

export_profile(person_id, output_path) → backup to JSON
export_workouts(person_id, output_dir) → Neo4j → JSON files
```

### arnold-medical-mcp (Phase 2 - Limited Scope)
```python
add_injury(person_id, body_part, description, severity, date)
update_injury_status(injury_id, status, notes)
get_injury_status(person_id) → active injuries and rehab progress
add_rehab_protocol(injury_id, protocol_description, exercises)
```

### arnold-medical-mcp (Phase 3+ - Full Scope)
```python
import_medical_record(person_id, file_path) → parse visit notes, diagnoses
import_lab_results(person_id, file_path) → LOINC-coded bloodwork
add_medication(person_id, drug_name, dosage, start_date)
add_supplement(person_id, supplement, dosage, timing)
check_interactions(person_id) → drug-drug, drug-supplement warnings
record_vital_sign(person_id, type, value, date) → BP, temp, SpO2
```

---

## Data Storage Architecture

### Git Repository Structure
```
/kernel/              # Committed - shareable ontology (exercises, anatomy)
/schemas/             # Committed - data models and graph schemas
/scripts/             # Committed - import/export/analysis scripts
/docs/                # Committed - architecture and roadmap

/data/                # .gitignored - PRIVATE, PII/PHI
  profile.json        # Person demographics, equipment, preferences
  observations.json   # Time-series: weight, HR, HRV
  workouts/           # One JSON file per workout
    2024-01-15.json
    2024-01-16.json
    ...
  orchestrator/       # Minimal state for orchestrator MCP
    user_session.json
    system_principles.txt
```

### Neo4j Graph Schema (Journey Structure)

**Person → Goals → Phases → Checkpoints**

```cypher
// Person with roles
(p:Person {id: "uuid", name: "Brock", age: 34})
(p)-[:HAS_ROLE]->(ath:Athlete {id: "ROLE:athlete:uuid"})

// Goals with target dates
(p)-[:HAS_GOAL]->(g:Goal {
  id: "uuid",
  type: "endurance",
  description: "Complete ultramarathon",
  target_date: "2025-06-15",
  priority: 1,
  status: "active"
})

// Training phases (macro cycle structure)
(p)-[:IN_PHASE]->(phase:TrainingPhase {
  id: "uuid",
  type: "base_building",
  start_date: "2025-01-01",
  end_date: "2025-03-31",
  focus: "aerobic capacity"
})
(phase)-[:TARGETS]->(g)

// Checkpoints (assessments, races, milestones)
(p)-[:HAS_CHECKPOINT]->(cp:Checkpoint {
  id: "uuid",
  date: "2025-02-15",
  type: "assessment",
  description: "5K time trial",
  result: null  // filled after completion
})
(cp)-[:VALIDATES_PROGRESS_TOWARD]->(g)

// Constraints (injuries, limitations)
(p)-[:HAS_CONSTRAINT]->(c:Constraint {
  id: "uuid",
  type: "injury",
  description: "Right knee ACL reconstruction",
  severity: "moderate",
  status: "active",
  started: "2024-10-01"
})
(c)-[:AFFECTS]->(bp:BodyPart {uberon_id: "UBERON:0001465"})

// Equipment access
(p)-[:HAS_ACCESS_TO {started: "2024-01-01"}]->(eq:EquipmentCategory)
```

**Journey Map Query Example:**
```cypher
MATCH (p:Person {id: $person_id})
OPTIONAL MATCH (p)-[:HAS_GOAL]->(g:Goal {status: "active"})
OPTIONAL MATCH (p)-[:IN_PHASE]->(phase:TrainingPhase)
OPTIONAL MATCH (p)-[:HAS_CHECKPOINT]->(cp:Checkpoint)
WHERE cp.date >= date()
RETURN p, collect(DISTINCT g) as goals, 
       collect(DISTINCT phase) as phases,
       collect(DISTINCT cp) as upcoming_checkpoints
ORDER BY cp.date
```

---

## Tool Routing Logic

```
System context and alerts → arnold-orchestrator-mcp
Profile CRUD → arnold-profile-mcp
Workout logging → arnold-training-mcp
Injury tracking → arnold-medical-mcp
Periodic review → arnold-checkin-mcp
Graph queries → neo4j-mcp (direct)
File I/O → filesystem-mcp (indirect via MCPs)
Medical import → arnold-medical-mcp (Phase 3+)
Email output → STUB (console text output for now)
```

---

## Orchestrator vs Check-In Distinction

### arnold-orchestrator-mcp (Reactive, Real-Time)
- **Trigger**: Every Claude Desktop interaction
- **Function**: Route requests to appropriate specialist
- **Context**: Current state, active alerts, system principles
- **Examples**:
  - "Log today's workout" → routes to training-mcp
  - "Update my knee status" → routes to medical-mcp
  - "What's my current training phase?" → queries Neo4j via journey_map

### arnold-checkin-mcp (Proactive, Periodic)
- **Trigger**: Every 14 days (configurable), or user-initiated
- **Function**: Cross-domain synthesis and strategic adjustment
- **Context**: Multi-week trends across training, recovery, medical
- **Examples**:
  - Volume down 20% last 2 weeks → discuss recovery needs
  - Knee rehab progress → adjust exercise selection constraints
  - Goal target date approaching → evaluate readiness, adjust phase

**Clean separation**: Orchestrator = daily traffic cop, Check-in = weekly team meeting

---

## Consumed MCPs (Not Owned by Arnold)

**neo4j-mcp** (Graph Database)
- Read/write Cypher queries
- Schema introspection
- Direct graph operations

**filesystem-mcp** (File Operations)
- Used internally by arnold-profile-mcp and arnold-training-mcp
- Read/write JSON backup files
- Not exposed directly to user

**gmail-mcp** (Email Integration) - FUTURE
- Phase 2: Stubbed (outputs text to console)
- Phase 3+: Actual email send/receive for summaries

---

## Implementation Sequence

### Phase 2A: Foundation
1. Define data schemas (profile.json, workout.json, observations.json)
2. Define Neo4j journey schema (Goal, TrainingPhase, Checkpoint nodes)
3. Export existing 160 workouts → JSON (validates workout schema)
4. Build arnold-profile-mcp (person CRUD, equipment, goals, constraints)
5. Build arnold-orchestrator-mcp (system context, tool routing)

### Phase 2B: Training & Review
6. Build arnold-training-mcp (workout logging, parsing, progression)
7. Build arnold-medical-mcp (injury tracking only)
8. Build arnold-checkin-mcp (14-day holistic review)

### Phase 2C: Integration Testing
9. Test full workflow: create profile → log workouts → check-in → adjust goals
10. Validate Neo4j ↔ JSON sync
11. User acceptance testing with Brock's actual training

### Phase 3+: Specialist Expansion
- arnold-nutrition-mcp
- arnold-recovery-mcp
- arnold-analytics-mcp
- Full arnold-medical-mcp (per ROADMAP)

---

## Success Criteria

**Phase 2 Complete When:**
- Profile exists in Neo4j + profile.json
- 160 historical workouts in JSON + Neo4j
- Can log new workout via natural language
- Can update past workout ("add bar weight to Friday")
- Check-in workflow runs and adjusts goals
- Journey map query returns phases/goals/checkpoints
- System context loads fresh on every new Claude Desktop thread

**Phase 3+ Triggers:**
- User requests nutrition tracking
- User uploads medical records
- User wants predictive analytics/dashboards

---

## Notes

- **Graph-First**: Journey is relationships, not files
- **Minimal State**: Orchestrator doesn't cache, queries fresh
- **LLM Superpower**: Workout parsing, medical record extraction (Phase 3+)
- **Good Enough > Perfect**: Ship Phase 2, iterate
- **Terminator Theme**: Internal codenames only, not user-facing
