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

from profile_manager import ProfileManager
from neo4j_client import Neo4jClient

# Configure logging
logging.basicConfig(level=logging.INFO)
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
                    "sex": {"type": "string", "enum": ["male", "female", "other"], "description": "Biological sex"},
                    "height_inches": {"type": "number", "description": "Height in inches (optional)"},
                    "birth_date": {"type": "string", "format": "date", "description": "Birth date YYYY-MM-DD (optional)"},
                    "time_zone": {"type": "string", "description": "User's time zone (default: America/New_York)"}
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
Sex: [male/female/other]
Height: [inches, or type 'skip']
Birth Date: [YYYY-MM-DD, or type 'skip']
Time Zone: [e.g. America/New_York, or type 'skip']

Just fill in the brackets and respond - that's it."""

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

            # Create profile with parsed data
            profile = profile_mgr.create_profile(
                name=profile_data['name'],
                age=profile_data['age'],
                sex=profile_data['sex'],
                height_inches=profile_data.get('height_inches'),
                birth_date=profile_data.get('birth_date'),
                time_zone=profile_data.get('time_zone', 'America/New_York')
            )

            # Create Person node in Neo4j
            neo4j_client.create_person_node(profile)

            logger.info(f"Profile created successfully via intake: {profile['person_id']}")

            return [types.TextContent(
                type="text",
                text=f"""✅ Profile created successfully!

**Person ID:** {profile['person_id']}
**Name:** {profile_data['name']}
**Age:** {profile_data['age']}
**Sex:** {profile_data['sex']}

Your Arnold digital twin is now initialized!

Profile saved to /data/profile.json and Neo4j Person node created.

Next steps:
- Add equipment inventory (home gym, commercial gym access)
- Set training goals (strength, hypertrophy, endurance, sport-specific)
- Add constraints (injuries, limitations)
- Create exercise aliases (personal shorthand)"""
            )]

        except ValueError as e:
            logger.error(f"Invalid intake response: {str(e)}")
            return [types.TextContent(
                type="text",
                text=f"❌ Invalid intake response: {str(e)}\n\nPlease provide all required fields:\n- Name\n- Age\n- Biological Sex"
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
                birth_date=arguments.get("birth_date"),
                time_zone=arguments.get("time_zone", "America/New_York")
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
