# Changelog

All notable changes to arnold-profile-mcp will be documented in this file.

## [0.1.5] - 2025-12-27

### Changed
- **Neo4j as Single Source of Truth**: Removed dual-write pattern
  - Deleted `observation_manager.py` - observations write directly to Neo4j
  - Deleted `equipment_manager.py` - equipment writes directly to Neo4j
  - Deleted `activities_manager.py` - activities write directly to Neo4j
  - Deleted `workout_manager.py` - workouts write directly to Neo4j
  - All operations now write to Neo4j only (no JSON file writes)
  - Simpler codebase, faster writes, no sync issues
  - Added `get_equipment_inventories()` to Neo4jClient for listing equipment
  - Added `get_activities()` to Neo4jClient for listing activities
  - Added `get_workout_by_date()` to Neo4jClient for retrieving workouts

### Benefits
- **Faster**: Single write operation instead of two (JSON + Neo4j)
- **Simpler**: No manager layer, tools call Neo4j directly
- **Safer**: No risk of JSON/Neo4j getting out of sync
- **Cleaner**: Neo4j is the authoritative data source

### Removed
- JSON file writes for observations, equipment, activities, and workouts
- Manager classes: ObservationManager, EquipmentManager, ActivitiesManager, WorkoutManager
- Dual storage complexity

## [0.1.4] - 2025-12-27

### Added
- **Equipment & Activities Tracking** (LLM-Native Design)
  - `setup_equipment_inventory()` tool for equipment tracking
  - `add_activity()` tool for sports/activities tracking
  - `list_equipment()` and `list_activities()` tools for viewing
  - EquipmentManager class for inventory management
  - ActivitiesManager class for activity management
  - Support for multiple inventories (home gym, commercial gym, etc.)
  - Temporal access tracking with context and location
  - Equipment details: quantity, weight, adjustable ranges, condition

### Neo4j Nodes Added
- **EquipmentInventory**: Training location inventories
- **EquipmentCategory**: Equipment types (barbell, dumbbells, etc.)
- **Activity**: Sports and activities tracking
- **HAS_ACCESS_TO**: Person → EquipmentInventory (with context, location, temporal data)
- **CONTAINS**: EquipmentInventory → EquipmentCategory (with quantity, weight specs)
- **PARTICIPATES_IN**: Person → Activity

### Design Philosophy
- Claude conducts conversational intake
- Tools are dumb data savers (no interpretation)
- Equipment: barbell, dumbbells, racks, machines, etc.
- Activities: tennis, running, swimming, etc.
- Temporal tracking: when equipment acquired, when access started

## [0.1.3] - 2025-12-27

### Added
- **Observation Tracking**: Complete observation system with LOINC codes
  - `record_observation()` tool for tracking body metrics (weight, HR, HRV, etc.)
  - ObservationManager class for time-series data management
  - Observations stored in `/data/observations.json` + Neo4j graph
  - LOINC code support for standardized medical observations
  - Neo4j ObservationConcept and Observation nodes
  - Weight date tracking: "Date weighed" field captures observation timestamp

### Changed
- **Removed timezone from intake**: Unnecessary complexity removed
  - Timezone removed from profile schema
  - Timezone removed from intake questionnaire
  - Timezone removed from create_profile function
- **Weight observation automatically recorded during intake**
  - Weight + date captured during profile creation
  - Initial weight saved as observation with LOINC code 29463-7
  - Confirmation message shows weight with recorded date

### Neo4j Nodes Added
- **Observation**: Time-series observation data (value, unit, recorded_at)
- **ObservationConcept**: Observation types (concept, loinc_code)
- **HAS_OBSERVATION**: Person → Observation
- **HAS_CONCEPT**: Observation → ObservationConcept

## [0.1.2] - 2025-12-27

### Added
- **Weight as Required Field**: Intake now captures baseline weight (lbs)
  - Essential for metabolic calculations, strength norms, bodyweight exercises
  - Weight captured during intake and acknowledged in confirmation
  - Prepares for future observation tracking (LOINC code 29463-7)

### Changed
- Updated `intake_profile()` questionnaire to include weight as required field
- Updated `parse_intake_response()` to extract and validate weight
- Updated `complete_intake()` to acknowledge weight in confirmation
- Changed sex field from "male/female/other" to "male/female/intersex" for inclusivity
- Updated all documentation to reflect weight requirement

## [0.1.1] - 2025-12-27

### Added
- **Workout Logging (LLM-Native Design)**: Revolutionary architecture where Claude Desktop interprets natural language and tools just save data
  - `find_canonical_exercise(exercise_name)` tool for exercise ID lookup
  - `log_workout(workout_data)` tool that accepts pre-structured JSON (NO parsing in tool)
  - `get_workout_by_date(workout_date)` tool for retrieving workouts
  - Claude Desktop handles ALL interpretation: any format, context, aliases, edge cases
  - Dual storage: JSON files (`/data/workouts/YYYY-MM-DD.json`) + Neo4j graph
  - Fuzzy exercise matching via `find_canonical_exercise` tool
  - Unmapped exercises save successfully with `exercise_id: null`

- **New Components**:
  - `workout_manager.py`: WorkoutManager class (NO parsing logic - just saves/retrieves JSON)
  - `workout_schema.json`: Complete JSON schema for workout data structure
  - `neo4j_client.create_workout_node()`: Creates Workout → Set → Exercise graph structure
  - `neo4j_client.find_exercise_by_name()`: Fuzzy search for canonical exercises

- **Neo4j Relationships**:
  - PERFORMED: Athlete → Workout
  - CONTAINS: Workout → Set
  - OF_EXERCISE: Set → Exercise (only if exercise_id provided by Claude)

- **Documentation**:
  - WORKOUT_LOGGING_TESTING.md: Comprehensive testing guide for LLM-native design
  - Updated README.md with LLM-native workflow examples
  - Added workout schema documentation

### Changed
- Updated README.md to explain LLM-native architecture
- Updated Neo4j Integration section with workout-related nodes
- Bumped version to 0.1.1

### Architecture Philosophy
**LLM-Native Design:**
- User → Claude interprets → Claude structures → Tool saves → Storage
- **NO REGEX** in tools
- **NO PARSING** in tools
- Claude Desktop is the intelligence layer
- Tools are dumb data writers
- Adding new formats NEVER requires code changes
- This is the future of AI-native applications

## [0.1.0] - 2025-12-26

### Added
- **Profile Management**: Core profile creation and management
  - `intake_profile()` tool for guided profile creation workflow
  - `complete_intake(intake_response)` tool for processing questionnaire responses
  - `create_profile()` tool for direct profile creation (advanced)
  - `get_profile()` tool for retrieving current profile
  - `update_profile(field_path, value)` tool for updating profile fields

- **Components**:
  - `profile_manager.py`: ProfileManager class with CRUD operations
  - `neo4j_client.py`: Neo4jClient class for Neo4j database operations
  - `server.py`: MCP server with tool handlers
  - `profile_schema.json`: JSON schema for profile structure

- **Neo4j Integration**:
  - Person node creation with demographic info
  - Athlete node creation with HAS_ROLE relationship
  - Auto-sync of demographic fields to Neo4j

- **Documentation**:
  - README.md: Complete usage guide
  - CLAUDE_DESKTOP_SETUP.md: Claude Desktop integration guide
  - INTAKE_WORKFLOW_TESTING.md: Profile creation testing guide

### Changed
- Fixed import issues: Changed from relative to absolute imports
- Simplified intake questionnaire format for clarity

### Technical Notes
- Python 3.10+ required
- Dependencies: mcp>=0.1.0, neo4j>=5.0.0, python-dotenv>=1.0.0
- Profile storage: `/data/profile.json`
- Workout storage: `/data/workouts/*.json`
- Neo4j database: "arnold" (configurable via env)
