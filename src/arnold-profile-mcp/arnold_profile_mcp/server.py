#!/usr/bin/env python3
"""Arnold Profile Management MCP Server.

This MCP server provides tools for creating and managing user profiles in Arnold.
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from typing import Any
import asyncio
import json
import logging
import uuid
from datetime import datetime, date

from profile_manager import ProfileManager
from neo4j_client import Neo4jClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/arnold-mcp-server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize server
server = Server("arnold-profile-mcp")
profile_mgr = ProfileManager()
neo4j_client = Neo4jClient()


@server.list_tools()
async def list_tools_handler() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="intake_profile",
            description="Start the profile creation intake workflow. This tool initiates a guided conversation to collect profile information.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="complete_intake",
            description="Process the user's intake questionnaire response and create their profile.",
            inputSchema={
                "type": "object",
                "properties": {
                    "intake_response": {"type": "string", "description": "User's completed questionnaire with profile information"}
                },
                "required": ["intake_response"]
            }
        ),
        types.Tool(
            name="create_profile",
            description="[Advanced] Directly create a new user profile. Prefer using intake_profile for guided workflow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "User's name"},
                    "age": {"type": "integer", "description": "User's age"},
                    "sex": {"type": "string", "enum": ["male", "female", "intersex"], "description": "Biological sex"},
                    "height_inches": {"type": "number", "description": "Height in inches (optional)"},
                    "birth_date": {"type": "string", "format": "date", "description": "Birth date YYYY-MM-DD (optional)"}
                },
                "required": ["name", "age", "sex"]
            }
        ),
        types.Tool(
            name="get_profile",
            description="Retrieve the current user profile.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="update_profile",
            description="Update a specific field in the profile using dot notation (e.g., demographics.age).",
            inputSchema={
                "type": "object",
                "properties": {
                    "field_path": {"type": "string", "description": "Dot-notation field path"},
                    "value": {"description": "New value for the field"}
                },
                "required": ["field_path", "value"]
            }
        ),
        types.Tool(
            name="find_canonical_exercise",
            description="Search for canonical exercise by name. Use this to map user's exercise names to canonical exercise IDs before logging workouts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "exercise_name": {"type": "string", "description": "Name of exercise to search for"}
                },
                "required": ["exercise_name"]
            }
        ),
        types.Tool(
            name="search_exercises",
            description="""Search exercises using full-text search with fuzzy matching. Returns multiple candidates for Claude to select from.

Use this when you need to find exercises by name or alias. The tool returns up to 5 candidates with relevance scores.
Claude should:
1. Normalize the query first (e.g., 'KB swing' → 'kettlebell swing')
2. Review the candidates and select the best match
3. If no good match exists, create a custom exercise

The full-text index searches exercise names AND aliases (common alternative names).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (exercise name or common alias)"},
                    "limit": {"type": "integer", "description": "Max results to return (default 5)", "default": 5}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="log_workout",
            description="""Save a pre-structured workout. Claude Desktop interprets user's natural language and structures it into the workout schema BEFORE calling this tool. This tool is DUMB - it just saves data.

Required fields in workout_data:
- person_id: UUID of person (auto-filled from profile if not provided)
- date: YYYY-MM-DD
- exercises: Array of exercise objects with sets

Optional fields:
- workout_id: UUID (auto-generated if not provided)
- type: strength/endurance/mobility/sport/mixed
- duration_minutes: Integer
- notes: String

Exercise object structure:
- exercise_name: String (required)
- exercise_id: UUID or null (use find_canonical_exercise to get this)
- purpose: warm-up/main-work/accessory/cool-down/active-recovery
- sets: Array of set objects
- notes: String

Set object structure:
- set_number: Integer
- reps: Integer or null
- load_lbs: Number or null
- duration_seconds: Integer or null
- distance_miles: Number or null
- rpe: Number (1-10) or null
- notes: String or null""",
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_data": {
                        "type": "object",
                        "description": "Fully structured workout following workout_schema.json"
                    }
                },
                "required": ["workout_data"]
            }
        ),
        types.Tool(
            name="get_workout_by_date",
            description="Retrieve a logged workout by date (YYYY-MM-DD).",
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_date": {"type": "string", "format": "date", "description": "Workout date in YYYY-MM-DD format"}
                },
                "required": ["workout_date"]
            }
        ),
        types.Tool(
            name="record_observation",
            description="""Record a body metric observation.

Common observations:
- body_weight (LOINC: 29463-7, unit: lbs)
- resting_hr (LOINC: 8867-4, unit: bpm)
- hrv (unit: ms)

Use this to track weight, heart rate, HRV, and other body metrics over time.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Type of observation (e.g., body_weight, resting_hr, hrv)"},
                    "value": {"type": "number", "description": "Numeric value"},
                    "recorded_date": {"type": "string", "description": "Date recorded (YYYY-MM-DD or 'today')"},
                    "unit": {"type": "string", "description": "Unit of measurement (e.g., lbs, bpm, ms)"},
                    "loinc_code": {"type": "string", "description": "LOINC code if applicable (optional)"},
                    "notes": {"type": "string", "description": "Optional notes"}
                },
                "required": ["concept", "value", "recorded_date"]
            }
        ),
        types.Tool(
            name="setup_equipment_inventory",
            description="""Create equipment inventory with all equipment. Claude conducts conversational intake and structures data before calling this tool.

This is a DUMB tool - Claude does ALL the interpretation and structuring.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "inventory_data": {
                        "type": "object",
                        "description": "Fully structured inventory data from Claude"
                    }
                },
                "required": ["inventory_data"]
            }
        ),
        types.Tool(
            name="add_activity",
            description="""Add sport/activity. Claude structures data from conversational intake before calling this tool.

This is a DUMB tool - Claude does ALL the interpretation.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_data": {
                        "type": "object",
                        "description": "Fully structured activity data from Claude"
                    }
                },
                "required": ["activity_data"]
            }
        ),
        types.Tool(
            name="list_equipment",
            description="List all equipment inventories.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="list_activities",
            description="List all activities/sports.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool_handler(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls."""

    if name == "intake_profile":
        try:
            # Check if profile already exists
            try:
                profile = profile_mgr.get_profile()
                return [types.TextContent(
                    type="text",
                    text=f"❌ Profile already exists for {profile['demographics']['name']} (ID: {profile['person_id']})\n\nUse update_profile to modify existing profile."
                )]
            except FileNotFoundError:
                pass  # No profile exists, proceed with intake

            # Return clear, unambiguous questionnaire
            intake_questions = """Arnold Profile Creation

Please provide the following information (copy and fill in):

Name: [your name]
Age: [your age]
Sex: [male/female/intersex]
Weight: [lbs]
Date weighed: [YYYY-MM-DD or 'today']
Height: [inches, or 'skip']
Birth Date: [YYYY-MM-DD, or 'skip']

Just fill in the brackets and respond."""

            return [types.TextContent(
                type="text",
                text=intake_questions.strip()
            )]

        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Error starting intake: {str(e)}"
            )]

    elif name == "complete_intake":
        try:
            intake_response = arguments["intake_response"]

            logger.info("Processing intake response")

            # Parse the intake response
            profile_data = profile_mgr.parse_intake_response(intake_response)

            # Extract weight data
            initial_weight = profile_data.pop('weight_lbs')
            weight_date = profile_data.pop('weight_date')

            # Create profile with parsed data
            profile = profile_mgr.create_profile(
                name=profile_data['name'],
                age=profile_data['age'],
                sex=profile_data['sex'],
                height_inches=profile_data.get('height_inches'),
                birth_date=profile_data.get('birth_date')
            )

            # Create Person node in Neo4j
            neo4j_client.create_person_node(profile)

            # Create weight observation structure
            observation = {
                "id": str(uuid.uuid4()),
                "person_id": profile["person_id"],
                "concept": "body_weight",
                "value": initial_weight,
                "unit": "lbs",
                "loinc_code": "29463-7",
                "recorded_at": weight_date,
                "created_at": datetime.now().isoformat(),
                "notes": None
            }

            # Write to Neo4j ONLY
            neo4j_client.create_observation_node(observation)

            logger.info(f"Profile created successfully via intake: {profile['person_id']}")

            return [types.TextContent(
                type="text",
                text=f"""✅ Profile created!

**Person ID:** {profile['person_id']}
**Name:** {profile_data['name']}
**Age:** {profile_data['age']}
**Sex:** {profile_data['sex']}
**Weight:** {initial_weight} lbs (recorded {weight_date})

Profile saved to /data/profile.json
Initial weight saved to Neo4j.

Ready to set up equipment and log workouts!"""
            )]

        except ValueError as e:
            logger.error(f"Invalid intake response: {str(e)}")
            return [types.TextContent(
                type="text",
                text=f"❌ Invalid intake response: {str(e)}\n\nRequired: Name, Age, Sex, Weight, Date weighed"
            )]
        except Exception as e:
            logger.error(f"Error completing intake: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error creating profile: {str(e)}"
            )]

    elif name == "create_profile":
        try:
            logger.info(f"Creating profile for {arguments.get('name')}")

            # Create profile JSON
            profile = profile_mgr.create_profile(
                name=arguments["name"],
                age=arguments["age"],
                sex=arguments["sex"],
                height_inches=arguments.get("height_inches"),
                birth_date=arguments.get("birth_date")
            )

            # Create Person node in Neo4j
            neo4j_result = neo4j_client.create_person_node(profile)

            logger.info(f"Profile created successfully: {profile['person_id']}")

            return [types.TextContent(
                type="text",
                text=f"✅ Profile created successfully!\n\nPerson ID: {profile['person_id']}\nName: {arguments['name']}\nAge: {arguments['age']}\nSex: {arguments['sex']}\n\nProfile saved to /data/profile.json and Neo4j Person node created."
            )]

        except ValueError as e:
            logger.error(f"Profile creation failed: {str(e)}")
            return [types.TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Unexpected error creating profile: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error creating profile: {str(e)}"
            )]

    elif name == "get_profile":
        try:
            logger.info("Retrieving profile")
            profile = profile_mgr.get_profile()

            return [types.TextContent(
                type="text",
                text=json.dumps(profile, indent=2)
            )]

        except FileNotFoundError:
            logger.warning("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Run create_profile first."
            )]
        except Exception as e:
            logger.error(f"Error retrieving profile: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error retrieving profile: {str(e)}"
            )]

    elif name == "update_profile":
        try:
            field_path = arguments["field_path"]
            value = arguments["value"]

            logger.info(f"Updating profile field: {field_path} = {value}")

            # Update JSON profile
            profile = profile_mgr.update_profile(field_path, value)

            # If updating demographics fields, sync to Neo4j
            if field_path.startswith("demographics."):
                field_name = field_path.split(".")[-1]
                person_id = profile["person_id"]

                # Map profile fields to Neo4j fields
                if field_name in ["name", "age", "sex", "height_inches"]:
                    neo4j_client.update_person_node(person_id, field_name, value)
                    logger.info(f"Synced {field_name} to Neo4j")

            return [types.TextContent(
                type="text",
                text=f"✅ Updated {field_path} = {value}\n\nProfile updated in /data/profile.json"
            )]

        except KeyError as e:
            logger.error(f"Invalid field path: {str(e)}")
            return [types.TextContent(
                type="text",
                text=f"❌ Invalid field path: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Error updating profile: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error updating profile: {str(e)}"
            )]

    elif name == "find_canonical_exercise":
        try:
            exercise_name = arguments["exercise_name"]

            logger.info(f"Searching for canonical exercise: {exercise_name}")

            exercise_id = neo4j_client.find_exercise_by_name(exercise_name)

            if exercise_id:
                return [types.TextContent(
                    type="text",
                    text=f"Found canonical exercise: {exercise_id}"
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"No canonical exercise found for '{exercise_name}'. Use null for exercise_id."
                )]

        except Exception as e:
            logger.error(f"Error searching exercises: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error searching exercises: {str(e)}"
            )]

    elif name == "search_exercises":
        try:
            query = arguments["query"]
            limit = arguments.get("limit", 5)

            logger.info(f"Searching exercises with query: {query}")

            results = neo4j_client.search_exercises(query, limit=limit)

            if results:
                # Format results as a table
                output = f"Found {len(results)} exercise(s) matching '{query}':\n\n"
                for i, r in enumerate(results, 1):
                    output += f"{i}. **{r['name']}**\n"
                    output += f"   ID: `{r['exercise_id']}`\n"
                    output += f"   Score: {r['score']:.2f}\n\n"
                
                return [types.TextContent(
                    type="text",
                    text=output
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"No exercises found matching '{query}'. Consider creating a custom exercise."
                )]

        except Exception as e:
            logger.error(f"Error searching exercises: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error searching exercises: {str(e)}"
            )]

    elif name == "log_workout":
        try:
            workout_data = arguments["workout_data"]

            # Parse if it's a JSON string
            if isinstance(workout_data, str):
                workout_data = json.loads(workout_data)

            logger.info(f"Logging workout for {workout_data.get('date', 'unknown date')}")

            # Validate person_id or auto-fill from profile
            if "person_id" not in workout_data:
                profile = profile_mgr.get_profile()
                workout_data["person_id"] = profile["person_id"]

            # Auto-generate workout_id if not provided
            if "workout_id" not in workout_data:
                workout_data["workout_id"] = str(uuid.uuid4())

            # Write to Neo4j ONLY
            result = neo4j_client.create_workout_node(workout_data)
            
            logger.info(f"Workout logged successfully: {workout_data['workout_id']}")

            # Format summary
            exercise_summary = "\n".join([
                f"- {ex['exercise_name']}: {len(ex['sets'])} sets"
                for ex in workout_data['exercises']
            ])
            
            # Check if any exercises need muscle mapping
            exercises_needing_mapping = result.get('exercises_needing_mapping', [])
            mapping_note = ""
            if exercises_needing_mapping:
                mapping_note = f"\n\n⚠️ **{len(exercises_needing_mapping)} exercise(s) need muscle mapping:**\n"
                mapping_note += "\n".join([f"- {ex['name']}" for ex in exercises_needing_mapping])
                mapping_note += "\n\nWould you like to map these exercises to muscles now?"

            return [types.TextContent(
                type="text",
                text=f"""✅ Workout logged!

**Date:** {workout_data['date']}
**Exercises:**
{exercise_summary}

Saved to Neo4j.{mapping_note}"""
            )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error logging workout: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error logging workout: {str(e)}"
            )]

    elif name == "get_workout_by_date":
        try:
            workout_date = arguments["workout_date"]

            logger.info(f"Retrieving workout for {workout_date}")

            # Get profile
            profile = profile_mgr.get_profile()

            # Query Neo4j directly
            workout = neo4j_client.get_workout_by_date(profile["person_id"], workout_date)

            if workout:
                return [types.TextContent(
                    type="text",
                    text=json.dumps(workout, indent=2)
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"❌ No workout found for {workout_date}"
                )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error retrieving workout: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error retrieving workout: {str(e)}"
            )]

    elif name == "record_observation":
        try:
            concept = arguments["concept"]
            value = arguments["value"]
            recorded_date = arguments["recorded_date"]
            unit = arguments.get("unit")
            loinc_code = arguments.get("loinc_code")
            notes = arguments.get("notes")

            logger.info(f"Recording observation: {concept} = {value}")

            # Get profile
            profile = profile_mgr.get_profile()

            # Handle 'today'
            if recorded_date.lower() == 'today':
                recorded_date = date.today().isoformat()

            # Create observation structure
            observation = {
                "id": str(uuid.uuid4()),
                "person_id": profile["person_id"],
                "concept": concept,
                "value": value,
                "unit": unit,
                "loinc_code": loinc_code,
                "recorded_at": recorded_date,
                "created_at": datetime.now().isoformat(),
                "notes": notes
            }

            # Write to Neo4j ONLY
            neo4j_client.create_observation_node(observation)

            logger.info(f"Observation recorded: {observation['id']}")

            return [types.TextContent(
                type="text",
                text=f"""✅ Observation recorded!

**Type:** {concept}
**Value:** {value} {unit if unit else ''}
**Date:** {recorded_date}

Saved to Neo4j."""
            )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error recording observation: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error recording observation: {str(e)}"
            )]

    elif name == "setup_equipment_inventory":
        try:
            # DEBUG: Log raw input
            logger.error(f"DEBUG arguments type: {type(arguments)}")
            logger.error(f"DEBUG arguments keys: {list(arguments.keys()) if isinstance(arguments, dict) else 'NOT A DICT'}")
            logger.error(f"DEBUG arguments content: {str(arguments)[:500]}")  # First 500 chars

            inventory_data = arguments["inventory_data"]

            logger.error(f"DEBUG inventory_data type: {type(inventory_data)}")
            logger.error(f"DEBUG inventory_data content (first 500 chars): {str(inventory_data)[:500]}")

            # Parse if it's a JSON string
            if isinstance(inventory_data, str):
                logger.error("DEBUG: inventory_data is a string, parsing as JSON")
                inventory_data = json.loads(inventory_data)
                logger.error(f"DEBUG: After parsing, type is now: {type(inventory_data)}")
            else:
                logger.error(f"DEBUG: inventory_data is already type {type(inventory_data)}, no parsing needed")

            logger.info(f"Setting up equipment inventory: {inventory_data.get('name')}")

            # Get profile
            profile = profile_mgr.get_profile()
            inventory_data["person_id"] = profile["person_id"]
            inventory_data["id"] = str(uuid.uuid4())

            # Write to Neo4j ONLY
            neo4j_client.create_equipment_inventory(inventory_data)

            # Add equipment items
            equipment_list = inventory_data.get("equipment", [])
            for eq in equipment_list:
                neo4j_client.add_equipment_to_inventory(inventory_data["id"], eq)

            # Update profile if primary
            if inventory_data.get("is_primary"):
                profile_mgr.update_profile(
                    "neo4j_refs.current_primary_equipment_inventory",
                    inventory_data["id"]
                )

            # Build equipment summary
            equipment_summary = "\n".join([
                f"- {eq['name']}" +
                (f" ({eq.get('weight_range_min')}-{eq.get('weight_range_max')} lbs)" if eq.get('adjustable') else
                 f" ({eq.get('weight_lbs')} lbs)" if eq.get('weight_lbs') else "")
                for eq in equipment_list
            ])

            logger.info(f"Equipment inventory created: {inventory_data['id']}")

            return [types.TextContent(
                type="text",
                text=f"""✅ Equipment inventory created!

**{inventory_data['name']}** ({inventory_data['location']})
{equipment_summary}

Saved to Neo4j."""
            )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error setting up equipment: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error setting up equipment: {str(e)}"
            )]

    elif name == "add_activity":
        try:
            activity_data = arguments["activity_data"]

            # Parse if it's a JSON string
            if isinstance(activity_data, str):
                activity_data = json.loads(activity_data)

            logger.info(f"Adding activity: {activity_data.get('name')}")

            # Get profile
            profile = profile_mgr.get_profile()
            activity_data["person_id"] = profile["person_id"]
            activity_data["id"] = str(uuid.uuid4())

            # Write to Neo4j ONLY
            neo4j_client.create_activity(activity_data)

            logger.info(f"Activity added: {activity_data['id']}")

            return [types.TextContent(
                type="text",
                text=f"""✅ Activity added!

**{activity_data['name']}**
Type: {activity_data.get('type')}
Frequency: {activity_data.get('frequency_per_week')}x per week
Location: {activity_data.get('location')}

Saved to Neo4j."""
            )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error adding activity: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error adding activity: {str(e)}"
            )]

    elif name == "list_equipment":
        try:
            logger.info("Listing equipment inventories")

            # Get profile
            profile = profile_mgr.get_profile()

            # Query Neo4j directly
            inventories = neo4j_client.get_equipment_inventories(profile["person_id"])

            if not inventories:
                return [types.TextContent(
                    type="text",
                    text="No equipment inventories set up yet."
                )]

            summary = []
            for inv in inventories:
                equipment_list = "\n  ".join([
                    f"- {eq['name']}" for eq in inv.get("equipment", [])
                ])
                summary.append(f"""**{inv['name']}** ({inv['location']})
  {equipment_list}""")

            return [types.TextContent(
                type="text",
                text="\n\n".join(summary)
            )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error listing equipment: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error listing equipment: {str(e)}"
            )]

    elif name == "list_activities":
        try:
            logger.info("Listing activities")

            # Get profile
            profile = profile_mgr.get_profile()

            # Query Neo4j directly
            activities = neo4j_client.get_activities(profile["person_id"])

            if not activities:
                return [types.TextContent(
                    type="text",
                    text="No activities set up yet."
                )]

            summary = "\n".join([
                f"- {act['name']}: {act.get('frequency_per_week')}x per week"
                for act in activities
            ])

            return [types.TextContent(
                type="text",
                text=summary
            )]

        except FileNotFoundError:
            logger.error("Profile not found")
            return [types.TextContent(
                type="text",
                text="❌ No profile found. Create your profile first using intake_profile."
            )]
        except Exception as e:
            logger.error(f"Error listing activities: {str(e)}", exc_info=True)
            return [types.TextContent(
                type="text",
                text=f"❌ Error listing activities: {str(e)}"
            )]

    else:
        return [types.TextContent(
            type="text",
            text=f"❌ Unknown tool: {name}"
        )]


async def main():
    """Run the MCP server."""
    logger.info("Starting Arnold Profile MCP Server")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server error: {str(e)}", exc_info=True)
        raise
    finally:
        neo4j_client.close()
        logger.info("Arnold Profile MCP Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
