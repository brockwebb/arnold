#!/usr/bin/env python3
"""Arnold Training Coach MCP Server.

This MCP server provides tools for:
- Training context (injuries, equipment, recent history)
- Workout planning and programming
- Exercise selection and safety checking
- Workout logging (planned and ad-hoc)
- Execution tracking with deviation recording
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

from neo4j_client import Neo4jTrainingClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/arnold-training-mcp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize server
server = Server("arnold-training-mcp")
neo4j_client = Neo4jTrainingClient()

# Default person_id (loaded from profile on first use)
_cached_person_id = None


def get_person_id() -> str:
    """Get person_id from profile or cache."""
    global _cached_person_id
    if _cached_person_id:
        return _cached_person_id
    
    # Try to load from profile.json
    import os
    profile_path = os.path.expanduser("~/Documents/GitHub/arnold/data/profile.json")
    if os.path.exists(profile_path):
        with open(profile_path, 'r') as f:
            profile = json.load(f)
            _cached_person_id = profile.get("person_id")
            return _cached_person_id
    
    raise ValueError("No profile found. Create profile using arnold-profile-mcp first.")


@server.list_tools()
async def list_tools_handler() -> list[types.Tool]:
    """List available tools."""
    return [
        # =====================================================================
        # CONTEXT TOOLS
        # =====================================================================
        types.Tool(
            name="get_coach_briefing",
            description="""Get everything the coach needs to know at conversation start.

Returns:
- Active training plan and goal
- Current block (type, week N of M, intent)
- Recent workouts (last 5)
- Next planned session
- Active injuries
- Workouts this week

Call this FIRST in any training conversation to load context.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="get_training_context",
            description="""Get all context needed for training decisions.

Returns:
- Active injuries and constraints
- Available equipment
- Recent workout summary (last 7 days)
- Active goals

Use this before creating a plan to understand current state.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="get_active_constraints",
            description="Get all active constraints from current injuries. Use to filter unsafe exercises.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        # =====================================================================
        # EXERCISE SELECTION TOOLS
        # =====================================================================
        types.Tool(
            name="suggest_exercises",
            description="""Find exercises matching criteria.

Filter by:
- movement_patterns: ["Hip Hinge", "Horizontal Push", etc.]
- muscle_targets: ["Gluteus Maximus", "Quadriceps", etc.]
- exclude_exercises: IDs to exclude

Returns ranked list of matching exercises with their patterns and target muscles.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "movement_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by movement patterns (e.g., Hip Hinge, Squat, Vertical Push)"
                    },
                    "muscle_targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by target muscles (e.g., Gluteus Maximus, Latissimus Dorsi)"
                    },
                    "exclude_exercises": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exercise IDs to exclude from results"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 10)",
                        "default": 10
                    }
                }
            }
        ),
        types.Tool(
            name="check_exercise_safety",
            description="""Check if an exercise is safe given current injuries/constraints.

Returns:
- safe: boolean
- concerns: list of constraint violations
- modifications: suggested adaptations""",
            inputSchema={
                "type": "object",
                "properties": {
                    "exercise_id": {
                        "type": "string",
                        "description": "Exercise ID to check"
                    }
                },
                "required": ["exercise_id"]
            }
        ),
        types.Tool(
            name="find_substitutes",
            description="""Find alternative exercises that preserve key characteristics.

Use when:
- Original exercise is contraindicated
- Equipment not available
- User preference

Returns ranked alternatives with similarity scores.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "exercise_id": {
                        "type": "string",
                        "description": "Original exercise ID to find substitutes for"
                    },
                    "preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Characteristics to preserve: movement_pattern, primary_muscles",
                        "default": ["movement_pattern", "primary_muscles"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 5)",
                        "default": 5
                    }
                },
                "required": ["exercise_id"]
            }
        ),
        
        # =====================================================================
        # PLANNING TOOLS
        # =====================================================================
        types.Tool(
            name="create_workout_plan",
            description="""Create a new workout plan for a specific date.

Claude interprets the coaching intent and structures it into blocks and sets.
This tool saves the structured plan to Neo4j.

Plan structure:
- date: YYYY-MM-DD
- goal: "Lower body strength", "Push/Pull", etc.
- focus: ["strength", "hypertrophy", "conditioning"]
- blocks: Array of workout blocks with sets

Block structure:
- name: "Warm-Up", "Main Work", "Finisher"
- block_type: warmup/main/accessory/finisher/cooldown
- sets: Array of prescribed sets

Set structure:
- exercise_id: Exercise to perform
- prescribed_reps, prescribed_load_lbs, prescribed_rpe
- intensity_zone: light/moderate/heavy/max""",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_data": {
                        "type": "object",
                        "description": "Fully structured plan from Claude",
                        "properties": {
                            "date": {"type": "string", "format": "date"},
                            "goal": {"type": "string"},
                            "focus": {"type": "array", "items": {"type": "string"}},
                            "estimated_duration_minutes": {"type": "integer"},
                            "notes": {"type": "string"},
                            "blocks": {"type": "array"}
                        },
                        "required": ["date", "blocks"]
                    }
                },
                "required": ["plan_data"]
            }
        ),
        types.Tool(
            name="get_plan_for_date",
            description="Get the planned workout for a specific date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Date to get plan for (YYYY-MM-DD)"
                    }
                },
                "required": ["date"]
            }
        ),
        types.Tool(
            name="get_planned_workout",
            description="Get a planned workout by ID with all blocks and sets.",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID"
                    }
                },
                "required": ["plan_id"]
            }
        ),
        types.Tool(
            name="confirm_plan",
            description="Lock in a plan, marking it ready to execute.",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID to confirm"
                    }
                },
                "required": ["plan_id"]
            }
        ),
        
        # =====================================================================
        # EXECUTION TOOLS
        # =====================================================================
        types.Tool(
            name="complete_as_written",
            description="""Mark a planned workout as completed exactly as written.

Converts the plan to an executed workout with no deviations.
Use when user reports "done" or "completed as planned".""",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID that was completed"
                    }
                },
                "required": ["plan_id"]
            }
        ),
        types.Tool(
            name="complete_with_deviations",
            description="""Mark a planned workout as completed with recorded deviations.

Use when user reports changes from the plan:
- "Had to drop weight on last set"
- "Only got 4 reps instead of 5"
- "Skipped the finisher"

Deviation structure:
- planned_set_id: Which set deviated
- actual_reps: What they actually did
- actual_load_lbs: Actual weight used
- reason: fatigue/pain/equipment/time/technique
- notes: User's explanation""",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID that was completed"
                    },
                    "deviations": {
                        "type": "array",
                        "description": "List of deviations from plan",
                        "items": {
                            "type": "object",
                            "properties": {
                                "planned_set_id": {"type": "string"},
                                "actual_reps": {"type": "integer"},
                                "actual_load_lbs": {"type": "number"},
                                "reason": {
                                    "type": "string",
                                    "enum": ["fatigue", "pain", "equipment", "time", "technique"]
                                },
                                "notes": {"type": "string"}
                            },
                            "required": ["planned_set_id", "reason"]
                        }
                    }
                },
                "required": ["plan_id", "deviations"]
            }
        ),
        types.Tool(
            name="skip_workout",
            description="Mark a planned workout as skipped with reason.",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID to skip"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why workout was skipped (illness, travel, rest day, etc.)"
                    }
                },
                "required": ["plan_id", "reason"]
            }
        ),
        types.Tool(
            name="log_workout",
            description="""Log an ad-hoc/unplanned workout.

Use when user did a workout that wasn't planned in advance.
Claude interprets natural language and structures it before calling.

Structure same as arnold-profile log_workout:
- date: YYYY-MM-DD
- exercises: Array with exercise_name, sets
- Set: reps, load_lbs, duration_seconds, etc.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_data": {
                        "type": "object",
                        "description": "Structured workout data from Claude"
                    }
                },
                "required": ["workout_data"]
            }
        ),
        
        # =====================================================================
        # HISTORY TOOLS
        # =====================================================================
        types.Tool(
            name="get_workout_by_date",
            description="Get an executed workout by date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Workout date (YYYY-MM-DD)"
                    }
                },
                "required": ["date"]
            }
        ),
        types.Tool(
            name="get_recent_workouts",
            description="Get summary of recent workouts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                        "default": 7
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool_handler(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls."""
    
    try:
        person_id = get_person_id()
    except ValueError as e:
        return [types.TextContent(type="text", text=f"❌ {str(e)}")]

    # =========================================================================
    # CONTEXT TOOLS
    # =========================================================================
    
    if name == "get_coach_briefing":
        try:
            logger.info(f"Getting coach briefing for {person_id}")
            briefing = neo4j_client.get_coach_briefing(person_id)
            
            if not briefing:
                return [types.TextContent(
                    type="text",
                    text="❌ Could not load briefing. Check profile exists."
                )]
            
            # Format as readable briefing
            lines = [f"**Athlete:** {briefing['athlete']}"]
            lines.append(f"**Workouts this week:** {briefing['workouts_this_week']}")
            
            # Goals with modality info
            if briefing.get('goals'):
                lines.append("\n**Active Goals:**")
                for g in briefing['goals']:
                    target = f" (by {g['target_date']})" if g.get('target_date') else ""
                    lines.append(f"  • {g['name']}{target} [{g['priority']}]")
                    # Show modality/level/model info
                    for m in g.get('modality_info', []):
                        if m.get('modality'):
                            lines.append(f"    → {m['modality']}: {m.get('level', '?')} level, {m.get('model', '?')}")
            else:
                lines.append("\n**Active Goals:** None")
            
            if briefing.get('current_block'):
                block = briefing['current_block']
                lines.append(f"\n**Current Block:** {block['name']} ({block['type']})")
                lines.append(f"**Week:** {block['week']} of {block['of_weeks']}")
                lines.append(f"**Dates:** {block['start']} → {block['end']}")
                lines.append(f"**Intent:** {block['intent']}")
                lines.append(f"**Volume/Intensity:** {block['volume']} / {block['intensity']}")
                if block.get('serves_goals'):
                    lines.append(f"**Serves:** {', '.join(block['serves_goals'])}")
            else:
                lines.append("\n**Current Block:** None")
            
            if briefing.get('next_planned'):
                nxt = briefing['next_planned']
                lines.append(f"\n**Next Planned:** {nxt['name']}")
                lines.append(f"**Date:** {nxt['date']} | **Status:** {nxt['status']}")
            
            if briefing.get('recent_workouts'):
                lines.append("\n**Recent Workouts:**")
                for w in briefing['recent_workouts']:
                    patterns = ", ".join(w.get('patterns', [])[:3]) or "—"
                    lines.append(f"  • {w['date']}: {w.get('type', 'workout')} ({w['sets']} sets) — {patterns}")
            
            if briefing.get('injuries'):
                lines.append("\n**Active Injuries:**")
                for inj in briefing['injuries']:
                    lines.append(f"  ⚠️ {inj['injury']} ({inj['body_part']}) - {inj['status']}")
            else:
                lines.append("\n**Injuries:** None")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error getting briefing: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "get_training_context":
        try:
            logger.info(f"Getting training context for {person_id}")
            context = neo4j_client.get_training_context(person_id)
            
            if not context:
                return [types.TextContent(
                    type="text",
                    text="❌ Could not load training context. Check profile exists."
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(context, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error getting context: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "get_active_constraints":
        try:
            logger.info(f"Getting active constraints for {person_id}")
            constraints = neo4j_client.get_active_constraints(person_id)
            
            if not constraints:
                return [types.TextContent(
                    type="text",
                    text="No active constraints found."
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(constraints, indent=2)
            )]
            
        except Exception as e:
            logger.error(f"Error getting constraints: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # EXERCISE SELECTION TOOLS
    # =========================================================================
    
    elif name == "suggest_exercises":
        try:
            logger.info(f"Suggesting exercises with filters: {arguments}")
            
            exercises = neo4j_client.suggest_exercises(
                movement_patterns=arguments.get("movement_patterns"),
                muscle_targets=arguments.get("muscle_targets"),
                exclude_exercises=arguments.get("exclude_exercises"),
                limit=arguments.get("limit", 10)
            )
            
            if not exercises:
                return [types.TextContent(
                    type="text",
                    text="No exercises found matching criteria."
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(exercises, indent=2)
            )]
            
        except Exception as e:
            logger.error(f"Error suggesting exercises: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "check_exercise_safety":
        try:
            exercise_id = arguments["exercise_id"]
            logger.info(f"Checking safety for {exercise_id}")
            
            result = neo4j_client.check_exercise_safety(exercise_id, person_id)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
            
        except Exception as e:
            logger.error(f"Error checking safety: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "find_substitutes":
        try:
            exercise_id = arguments["exercise_id"]
            logger.info(f"Finding substitutes for {exercise_id}")
            
            substitutes = neo4j_client.find_substitutes(
                exercise_id=exercise_id,
                preserve=arguments.get("preserve"),
                limit=arguments.get("limit", 5)
            )
            
            if not substitutes:
                return [types.TextContent(
                    type="text",
                    text="No suitable substitutes found."
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(substitutes, indent=2)
            )]
            
        except Exception as e:
            logger.error(f"Error finding substitutes: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # PLANNING TOOLS
    # =========================================================================
    
    elif name == "create_workout_plan":
        try:
            plan_data = arguments["plan_data"]
            
            # Parse if string
            if isinstance(plan_data, str):
                plan_data = json.loads(plan_data)
            
            logger.info(f"Creating plan for {plan_data.get('date')}")
            
            # Add IDs
            plan_data["person_id"] = person_id
            plan_data["id"] = f"PLAN:{uuid.uuid4()}"
            
            for i, block in enumerate(plan_data.get("blocks", [])):
                block["id"] = f"PLANBLOCK:{uuid.uuid4()}"
                block["order"] = i + 1
                
                for j, set_data in enumerate(block.get("sets", [])):
                    set_data["id"] = f"PLANSET:{uuid.uuid4()}"
                    set_data["order"] = j + 1
            
            result = neo4j_client.create_planned_workout(plan_data)
            
            # Build summary
            block_summary = "\n".join([
                f"  • {b['name']}: {len(b.get('sets', []))} sets"
                for b in plan_data.get("blocks", [])
            ])
            
            return [types.TextContent(
                type="text",
                text=f"""✅ Workout plan created!

**Plan ID:** {result['id']}
**Date:** {plan_data['date']}
**Goal:** {plan_data.get('goal', 'Not specified')}
**Status:** {result['status']}

**Blocks:**
{block_summary}

Use `confirm_plan` when ready to lock it in."""
            )]
            
        except Exception as e:
            logger.error(f"Error creating plan: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "get_plan_for_date":
        try:
            plan_date = arguments["date"]
            logger.info(f"Getting plan for {plan_date}")
            
            plan = neo4j_client.get_plan_for_date(person_id, plan_date)
            
            if not plan:
                return [types.TextContent(
                    type="text",
                    text=f"No plan found for {plan_date}"
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(plan, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error getting plan: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "get_planned_workout":
        try:
            plan_id = arguments["plan_id"]
            logger.info(f"Getting plan {plan_id}")
            
            plan = neo4j_client.get_planned_workout(plan_id)
            
            if not plan:
                return [types.TextContent(
                    type="text",
                    text=f"Plan not found: {plan_id}"
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(plan, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error getting plan: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "confirm_plan":
        try:
            plan_id = arguments["plan_id"]
            logger.info(f"Confirming plan {plan_id}")
            
            result = neo4j_client.update_plan_status(plan_id, "confirmed")
            
            return [types.TextContent(
                type="text",
                text=f"✅ Plan confirmed!\n\n**Plan ID:** {result['id']}\n**Status:** {result['status']}"
            )]
            
        except Exception as e:
            logger.error(f"Error confirming plan: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # EXECUTION TOOLS
    # =========================================================================
    
    elif name == "complete_as_written":
        try:
            plan_id = arguments["plan_id"]
            logger.info(f"Completing plan as written: {plan_id}")
            
            result = neo4j_client.complete_workout_as_written(plan_id)
            
            if "error" in result:
                return [types.TextContent(
                    type="text",
                    text=f"❌ {result['error']}"
                )]
            
            return [types.TextContent(
                type="text",
                text=f"""✅ Workout completed!

**Workout ID:** {result['workout_id']}
**From Plan:** {result['plan_id']}
**Compliance:** {result['compliance']}

Great work! 💪"""
            )]
            
        except Exception as e:
            logger.error(f"Error completing workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "complete_with_deviations":
        try:
            plan_id = arguments["plan_id"]
            deviations = arguments["deviations"]
            
            logger.info(f"Completing plan with {len(deviations)} deviations: {plan_id}")
            
            result = neo4j_client.complete_workout_with_deviations(plan_id, deviations)
            
            if "error" in result:
                return [types.TextContent(
                    type="text",
                    text=f"❌ {result['error']}"
                )]
            
            return [types.TextContent(
                type="text",
                text=f"""✅ Workout completed with deviations recorded!

**Workout ID:** {result['workout_id']}
**From Plan:** {result['plan_id']}
**Compliance:** {result['compliance']}
**Deviations:** {result['deviations_recorded']}

Deviations tracked for coaching adjustments."""
            )]
            
        except Exception as e:
            logger.error(f"Error completing workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "skip_workout":
        try:
            plan_id = arguments["plan_id"]
            reason = arguments["reason"]
            
            logger.info(f"Skipping plan {plan_id}: {reason}")
            
            result = neo4j_client.skip_workout(plan_id, reason)
            
            return [types.TextContent(
                type="text",
                text=f"""⏭️ Workout skipped

**Plan ID:** {result['id']}
**Status:** {result['status']}
**Reason:** {reason}

Rest is part of training too."""
            )]
            
        except Exception as e:
            logger.error(f"Error skipping workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "log_workout":
        try:
            workout_data = arguments["workout_data"]
            
            # Parse if string
            if isinstance(workout_data, str):
                workout_data = json.loads(workout_data)
            
            logger.info(f"Logging ad-hoc workout for {workout_data.get('date')}")
            
            # Add IDs
            workout_data["person_id"] = person_id
            workout_data["workout_id"] = str(uuid.uuid4())
            
            result = neo4j_client.log_adhoc_workout(workout_data)
            
            # Format summary
            mapping_note = ""
            if result.get("exercises_needing_mapping"):
                mapping_note = f"\n\n⚠️ **{len(result['exercises_needing_mapping'])} new exercise(s)** need muscle mapping."
            
            return [types.TextContent(
                type="text",
                text=f"""✅ Workout logged!

**Date:** {result['date']}
**Workout ID:** {result['workout_id']}
**Exercises:** {result['exercises_logged']}{mapping_note}"""
            )]
            
        except Exception as e:
            logger.error(f"Error logging workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # HISTORY TOOLS
    # =========================================================================
    
    elif name == "get_workout_by_date":
        try:
            workout_date = arguments["date"]
            logger.info(f"Getting workout for {workout_date}")
            
            workout = neo4j_client.get_workout_by_date(person_id, workout_date)
            
            if not workout:
                return [types.TextContent(
                    type="text",
                    text=f"No workout found for {workout_date}"
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(workout, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error getting workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "get_recent_workouts":
        try:
            days = arguments.get("days", 7)
            logger.info(f"Getting workouts for last {days} days")
            
            workouts = neo4j_client.get_recent_workouts(person_id, days)
            
            if not workouts:
                return [types.TextContent(
                    type="text",
                    text=f"No workouts in the last {days} days."
                )]
            
            # Format summary
            summary = []
            for w in workouts:
                patterns_str = ", ".join(w.get("patterns", [])[:3]) or "N/A"
                summary.append(
                    f"• **{w['date']}**: {w.get('type', 'workout')} - "
                    f"{w['set_count']} sets ({patterns_str})"
                )
            
            return [types.TextContent(
                type="text",
                text=f"**Last {days} Days:**\n\n" + "\n".join(summary)
            )]
            
        except Exception as e:
            logger.error(f"Error getting workouts: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    else:
        return [types.TextContent(
            type="text",
            text=f"❌ Unknown tool: {name}"
        )]


async def main():
    """Run the MCP server."""
    logger.info("Starting Arnold Training Coach MCP Server")

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
        logger.info("Arnold Training Coach MCP Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
