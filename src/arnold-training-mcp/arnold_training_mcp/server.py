#!/usr/bin/env python3
"""Arnold Training Coach MCP Server.

This MCP server provides tools for:
- Training context (injuries, equipment, recent history)
- Workout planning and programming (Neo4j)
- Exercise selection and safety checking (Neo4j)
- Workout logging and execution (Postgres per ADR-002)
- Execution tracking with deviation recording

Architecture (ADR-002):
- Plans (intentions) → Neo4j
- Executed workouts (facts) → Postgres
- Lightweight StrengthWorkout refs in Neo4j for relationship queries
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
from postgres_client import PostgresTrainingClient

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
postgres_client = PostgresTrainingClient()

# Default person_id (loaded from profile on first use)
_cached_person_id = None



def ensure_exercise_name(exercise_id: str | None, exercise_name: str | None, neo4j_client) -> str:
    """Resolve exercise_name from Neo4j if missing but exercise_id exists."""
    if exercise_name:
        return exercise_name
    if not exercise_id:
        return "Unknown"
    result = neo4j_client.get_exercise_by_id(exercise_id)
    return result['name'] if result else exercise_id


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
            description="""[DEPRECATED] Use memory:load_briefing instead.

This tool is deprecated as of Jan 2026. The consolidated briefing in arnold-memory-mcp
provides everything this tool did PLUS analytics (HRV, sleep, ACWR, HRR trends).

If called, returns a deprecation notice directing to load_briefing.""",
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
        # EXERCISE SEARCH & SELECTION TOOLS
        # =====================================================================
        types.Tool(
            name="search_exercises",
            description="""Search exercises using full-text search with fuzzy matching.
Returns multiple candidates with relevance scores for Claude to select from.

IMPORTANT: Claude should NORMALIZE the query first (semantic layer).
Example: "KB swing" → "kettlebell swing" BEFORE calling this tool.

The tool handles string matching variations (swing vs swings).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (exercise name or common alias)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="resolve_exercises",
            description="""Batch resolve exercise names to IDs in a single call.

Use this when building workout plans to resolve ALL exercises at once
instead of making individual search_exercises calls.

IMPORTANT: Claude should NORMALIZE all names first (semantic layer).
Example: ["KB swing", "RDL"] → ["kettlebell swing", "romanian deadlift"]

Returns:
- resolved: High-confidence matches ready to use
- needs_clarification: Low-confidence matches requiring user input
- not_found: Names with no matches

If needs_clarification or not_found are non-empty, discuss with user before proceeding.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of NORMALIZED exercise names to resolve"
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "description": "Minimum score (0-1) to auto-accept (default 0.3)",
                        "default": 0.3
                    }
                },
                "required": ["names"]
            }
        ),
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
        # PLANNING TOOLS (Neo4j - intentions)
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
        types.Tool(
            name="get_upcoming_plans",
            description="""Get all planned workouts for the next N days.

Returns list of plans with:
- plan_id, date, status (draft/confirmed/completed/skipped)
- goal, focus, estimated duration
- block and set counts

Use to see what's already scheduled before creating new plans.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default 7)",
                        "default": 7
                    }
                }
            }
        ),
        types.Tool(
            name="get_planning_status",
            description="""Get planning status overview for the next N days.

Returns:
- Day-by-day breakdown (planned vs gaps)
- Planned count vs gap count
- Coverage percentage based on block's sessions_per_week
- Current block context (name, type, sessions_per_week, intent)
- Recent training dates for context

Use at conversation start to identify planning gaps that need filling.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to check (default 7)",
                        "default": 7
                    }
                }
            }
        ),
        
        # =====================================================================
        # EXECUTION TOOLS (Postgres - facts, per ADR-002)
        # =====================================================================
        types.Tool(
            name="complete_as_written",
            description="""Mark a planned workout as completed exactly as written.

Converts the plan to an executed workout with no deviations.
Writes to Postgres (facts) and creates Neo4j reference.
Use when user reports "done" or "completed as planned".

IMPORTANT: Always ask user for session_rpe (1-10) and actual duration if not provided.
These are critical for sRPE-based training load calculations.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID that was completed"
                    },
                    "session_rpe": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Overall session RPE (1-10). ALWAYS ask user: 'How hard was that session?'"
                    },
                    "actual_duration_minutes": {
                        "type": "integer",
                        "description": "Actual workout duration in minutes. Ask user or use Polar data if available."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional session notes"
                    }
                },
                "required": ["plan_id"]
            }
        ),
        types.Tool(
            name="complete_with_deviations",
            description="""Mark a planned workout as completed with recorded deviations.

Writes to Postgres with deviation tracking.
Use when user reports changes from the plan:
- "Had to drop weight on last set"
- "Only got 4 reps instead of 5"
- "Skipped the finisher"
- "Swapped exercise X for exercise Y"

IMPORTANT: Always ask user for session_rpe (1-10) and actual duration if not provided.
These are critical for sRPE-based training load calculations.

Deviation structure:
- planned_set_id: Which set deviated
- actual_reps: What they actually did
- actual_load_lbs: Actual weight used
- substitute_exercise_id: If they did a DIFFERENT exercise (optional)
- reason: fatigue/pain/equipment/time/technique
- notes: User's explanation""",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID that was completed"
                    },
                    "session_rpe": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Overall session RPE (1-10). ALWAYS ask user: 'How hard was that session?'"
                    },
                    "actual_duration_minutes": {
                        "type": "integer",
                        "description": "Actual workout duration in minutes. Ask user or use Polar data if available."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional session notes"
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
                                "substitute_exercise_id": {
                                    "type": "string",
                                    "description": "If they did a different exercise, the ID of the substitute"
                                },
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
Writes directly to Postgres (facts) and creates Neo4j reference.
Claude interprets natural language and structures it before calling.

Structure:
- date: YYYY-MM-DD
- name: Workout name/goal
- exercises: Array with exercise_id/name, sets
- Set: reps, load_lbs, rpe, etc.""",
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
        # HISTORY TOOLS (Postgres - facts, per ADR-002)
        # =====================================================================
        types.Tool(
            name="get_workout_by_date",
            description="Get an executed workout by date from Postgres.",
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
            description="Get summary of recent workouts from Postgres.",
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
    # CONTEXT TOOLS (Hybrid: Neo4j context + Postgres workouts)
    # =========================================================================
    
    if name == "get_coach_briefing":
        try:
            logger.info(f"Getting coach briefing for {person_id}")
            
            # Get context from Neo4j (goals, block, injuries, next plan)
            briefing = neo4j_client.get_coach_briefing(person_id)
            
            if not briefing:
                return [types.TextContent(
                    type="text",
                    text="❌ Could not load briefing. Check profile exists."
                )]
            
            # Get recent workouts from Postgres (ADR-002)
            recent_workouts = postgres_client.get_sessions_for_briefing(days=7)
            workouts_this_week = postgres_client.get_workouts_this_week()
            
            # Format as readable briefing
            lines = [f"**Athlete:** {briefing['athlete']}"]
            lines.append(f"**Workouts this week:** {workouts_this_week}")
            
            # Goals with modality info
            if briefing.get('goals'):
                lines.append("\n**Active Goals:**")
                for g in briefing['goals']:
                    target = f" (by {g['target_date']})" if g.get('target_date') else ""
                    lines.append(f"  • {g['name']}{target} [{g['priority']}]")
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
            
            # Use Postgres workouts instead of Neo4j
            if recent_workouts:
                lines.append("\n**Recent Workouts (Postgres):**")
                for w in recent_workouts:
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
            
            # Replace Neo4j recent_workouts with Postgres
            context['recent_workouts'] = postgres_client.get_recent_sessions(days=7)
            context['workouts_this_week'] = postgres_client.get_workouts_this_week()
            
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
    # EXERCISE SEARCH & SELECTION TOOLS (Neo4j)
    # =========================================================================
    
    elif name == "search_exercises":
        try:
            query = arguments["query"]
            limit = arguments.get("limit", 5)
            
            logger.info(f"Searching exercises for: {query}")
            
            results = neo4j_client.search_exercises(query, limit)
            
            if not results:
                return [types.TextContent(
                    type="text",
                    text=f"No exercises found matching '{query}'."
                )]
            
            lines = [f"Found {len(results)} exercise(s) matching '{query}':\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r['name']}**")
                lines.append(f"   ID: `{r['exercise_id']}`")
                lines.append(f"   Score: {r['score']:.2f}\n")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error searching exercises: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "resolve_exercises":
        try:
            names = arguments["names"]
            threshold = arguments.get("confidence_threshold", 0.5)
            
            logger.info(f"Resolving {len(names)} exercises")
            
            result = neo4j_client.resolve_exercises(names, threshold)
            
            lines = ["**Exercise Resolution Results:**\n"]
            lines.append(f"Total: {result['summary']['total']} | "
                        f"Resolved: {result['summary']['resolved']} | "
                        f"Needs Clarification: {result['summary']['needs_clarification']} | "
                        f"Not Found: {result['summary']['not_found']}\n")
            
            if result['resolved']:
                lines.append("\n✅ **Resolved (ready to use):**")
                for name, match in result['resolved'].items():
                    lines.append(f"  • '{name}' → `{match['id']}` ({match['name']}) [{match['confidence']}]")
            
            if result['needs_clarification']:
                lines.append("\n⚠️ **Needs Clarification:**")
                for name, candidates in result['needs_clarification'].items():
                    lines.append(f"  • '{name}' - top matches:")
                    for c in candidates:
                        lines.append(f"    - `{c['id']}` ({c['name']}) score: {c['score']:.2f}")
            
            if result['not_found']:
                lines.append("\n❌ **Not Found:**")
                for name in result['not_found']:
                    lines.append(f"  • '{name}'")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error resolving exercises: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

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
    # PLANNING TOOLS (Neo4j - intentions)
    # =========================================================================
    
    elif name == "create_workout_plan":
        try:
            plan_data = arguments["plan_data"]
            
            if isinstance(plan_data, str):
                plan_data = json.loads(plan_data)
            
            logger.info(f"Creating plan for {plan_data.get('date')}")
            
            plan_data["person_id"] = person_id
            plan_data["id"] = f"PLAN:{uuid.uuid4()}"
            
            for i, block in enumerate(plan_data.get("blocks", [])):
                block["id"] = f"PLANBLOCK:{uuid.uuid4()}"
                block["order"] = i + 1
                
                for j, set_data in enumerate(block.get("sets", [])):
                    set_data["id"] = f"PLANSET:{uuid.uuid4()}"
                    set_data["order"] = j + 1
            
            result = neo4j_client.create_planned_workout(plan_data)

            # Mirror planned sets to Postgres for FK joins (Phase 6b)
            try:
                planned_set_count = postgres_client.insert_planned_sets(
                    plan_id=plan_data["id"],
                    blocks=plan_data.get("blocks", [])
                )
                logger.info(f"Mirrored {planned_set_count} planned sets to Postgres")
            except Exception as pg_err:
                logger.warning(f"Failed to mirror planned sets to Postgres: {pg_err}")
                # Don't fail the whole operation - Neo4j is source of truth

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

    elif name == "get_upcoming_plans":
        try:
            days = arguments.get("days", 7)
            logger.info(f"Getting upcoming plans for next {days} days")
            
            plans = neo4j_client.get_upcoming_plans(person_id, days)
            
            if not plans:
                return [types.TextContent(
                    type="text",
                    text=f"No plans found for the next {days} days."
                )]
            
            lines = [f"**Upcoming Plans (next {days} days):**\n"]
            for p in plans:
                status_emoji = {
                    "draft": "📝",
                    "confirmed": "✅",
                    "completed": "☑️",
                    "skipped": "⏭️"
                }.get(p["status"], "❓")
                
                lines.append(
                    f"{status_emoji} **{p['date']}** — {p.get('goal', 'No goal')} "
                    f"({p['status']}) [{p['block_count']} blocks, {p['set_count']} sets]"
                )
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error getting upcoming plans: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "get_planning_status":
        try:
            days = arguments.get("days", 7)
            logger.info(f"Getting planning status for next {days} days")
            
            status = neo4j_client.get_planning_status(person_id, days)
            
            lines = [f"**Planning Status (next {days} days):**\n"]
            
            lines.append(f"📊 **Coverage:** {status['planned_count']} planned / {status['gap_count']} gaps")
            if status.get('coverage_percent') is not None:
                lines.append(f"📈 **Block Coverage:** {status['coverage_percent']}%")
            
            if status.get('current_block') and status['current_block'].get('name'):
                block = status['current_block']
                lines.append(f"\n**Current Block:** {block['name']} ({block['type']})")
                if block.get('sessions_per_week'):
                    lines.append(f"**Target:** {block['sessions_per_week']} sessions/week")
                if block.get('intent'):
                    lines.append(f"**Intent:** {block['intent']}")
            
            lines.append("\n**Day-by-Day:**")
            for day in status['days']:
                if day['has_plan']:
                    status_emoji = {
                        "draft": "📝",
                        "confirmed": "✅",
                        "completed": "☑️",
                        "skipped": "⏭️"
                    }.get(day['status'], "❓")
                    lines.append(f"  {status_emoji} {day['day_name'][:3]} {day['date']}: {day.get('goal', 'planned')}")
                else:
                    lines.append(f"  ⬜ {day['day_name'][:3]} {day['date']}: **UNPLANNED**")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error getting planning status: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # EXECUTION TOOLS (Postgres - facts, per ADR-002)
    # =========================================================================
    
    elif name == "complete_as_written":
        try:
            plan_id = arguments["plan_id"]
            session_rpe = arguments.get("session_rpe")  # Critical for sRPE load
            actual_duration = arguments.get("actual_duration_minutes")  # Critical for sRPE load
            session_notes = arguments.get("notes")
            
            logger.info(f"Completing plan as written: {plan_id} (RPE={session_rpe}, dur={actual_duration}min)")
            
            # 1. Get the plan from Neo4j
            plan = neo4j_client.get_planned_workout(plan_id)
            if not plan:
                return [types.TextContent(
                    type="text",
                    text=f"❌ Plan not found: {plan_id}"
                )]

            # 1b. Idempotency guard - prevent double-insert
            if plan.get('status') == 'completed':
                return [types.TextContent(
                    type="text",
                    text=f"⚠️ Plan {plan_id} is already completed. No action taken."
                )]

            # 2. Transform plan to Postgres format - PRESERVE BLOCK STRUCTURE (ADR-007)
            blocks = []
            for block in plan.get('blocks', []):
                block_sets = []
                for s in block.get('sets', []):
                    block_sets.append({
                        'exercise_id': s.get('exercise_id'),
                        'exercise_name': ensure_exercise_name(s.get('exercise_id'), s.get('exercise_name'), neo4j_client),
                        'reps': s.get('prescribed_reps'),  # As written
                        'load_lbs': s.get('prescribed_load_lbs'),
                        'rpe': s.get('prescribed_rpe'),
                        'planned_set_id': s.get('id'),  # FK to planned_sets
                        'notes': s.get('notes')
                    })
                blocks.append({
                    'name': block.get('name', 'Block'),
                    'block_type': block.get('block_type', 'main'),
                    'modality': block.get('modality'),  # Per-block override
                    'sets': block_sets
                })

            # 3. Write to Postgres with proper block structure
            result = postgres_client.log_workout_session(
                session_date=plan['date'],
                name=plan.get('goal', 'Workout'),
                blocks=blocks,
                sport_type=plan.get('sport_type', 'strength'),
                duration_minutes=actual_duration or plan.get('estimated_duration_minutes'),
                notes=session_notes or plan.get('notes'),
                session_rpe=session_rpe,  # Critical for sRPE-based training load
                source='from_plan',
                plan_id=plan_id
            )
            
            # 4. Create Neo4j reference node
            neo4j_ref = None
            neo4j_warning = ""
            try:
                neo4j_ref = neo4j_client.create_strength_workout_ref(
                    workout_id=result['session_id'],
                    date=plan['date'],
                    name=plan.get('goal', 'Workout'),
                    plan_id=plan_id,
                    person_id=person_id,
                    total_sets=result.get('set_count'),
                    total_volume_lbs=result.get('total_volume')
                )
                if not neo4j_ref:
                    logger.warning(f"Neo4j ref creation returned None for workout {result['session_id']}")
                    neo4j_warning = "\n⚠️ Neo4j sync failed (returned None) - run backfill_neo4j_workout_refs.py"
            except Exception as neo4j_err:
                logger.error(f"Failed to create Neo4j ref for workout {result['session_id']}: {neo4j_err}", exc_info=True)
                neo4j_warning = f"\n⚠️ Neo4j sync failed: {neo4j_err} - run backfill_neo4j_workout_refs.py"

            # 5. Update Postgres with Neo4j ID
            if neo4j_ref:
                postgres_client.update_session_neo4j_id(
                    result['session_id'],
                    neo4j_ref.get('id')
                )

            # 6. Update plan status
            neo4j_client.update_plan_status(plan_id, "completed")

            # Build sRPE info string
            srpe_info = ""
            if session_rpe and (actual_duration or plan.get('estimated_duration_minutes')):
                dur = actual_duration or plan.get('estimated_duration_minutes')
                srpe_load = session_rpe * dur
                srpe_info = f"\n**sRPE Load:** {srpe_load} AU (RPE {session_rpe} × {dur} min)"
            elif not session_rpe:
                srpe_info = "\n⚠️ **No session RPE provided** - sRPE load will be imputed"

            # Build block info
            block_info = f"\n**Blocks:** {result['block_count']}" if result.get('block_count', 0) > 1 else ""

            return [types.TextContent(
                type="text",
                text=f"""✅ Workout completed!

**Session ID:** {result['session_id']} (Postgres)
**Neo4j Ref:** {neo4j_ref.get('id') if neo4j_ref else 'N/A'}
**From Plan:** {plan_id}{block_info}
**Sets:** {result['set_count']}
**Compliance:** as_written{srpe_info}{neo4j_warning}

Great work! 💪"""
            )]

        except Exception as e:
            logger.error(f"Error completing workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    elif name == "complete_with_deviations":
        try:
            plan_id = arguments["plan_id"]
            deviations = arguments.get("deviations", [])
            session_rpe = arguments.get("session_rpe")  # Critical for sRPE load
            actual_duration = arguments.get("actual_duration_minutes")  # Critical for sRPE load
            session_notes = arguments.get("notes")
            
            logger.info(f"Completing plan with {len(deviations)} deviations: {plan_id} (RPE={session_rpe}, dur={actual_duration}min)")
            
            # 1. Get the plan from Neo4j
            plan = neo4j_client.get_planned_workout(plan_id)
            if not plan:
                return [types.TextContent(
                    type="text",
                    text=f"❌ Plan not found: {plan_id}"
                )]

            # 1b. Idempotency guard - prevent double-insert
            if plan.get('status') == 'completed':
                return [types.TextContent(
                    type="text",
                    text=f"⚠️ Plan {plan_id} is already completed. No action taken."
                )]

            # 2. Build deviation lookup
            deviation_map = {d['planned_set_id']: d for d in deviations}

            # 3. Transform plan to Postgres format - PRESERVE BLOCK STRUCTURE with deviations
            blocks = []
            for block in plan.get('blocks', []):
                block_sets = []
                for s in block.get('sets', []):
                    set_id = s.get('id')
                    dev = deviation_map.get(set_id, {})

                    # Use deviation values if provided, else use prescribed (as written)
                    exercise_id = dev.get('substitute_exercise_id') or s.get('exercise_id')
                    exercise_name = s.get('exercise_name')
                    if dev.get('substitute_exercise_id'):
                        exercise_name = ensure_exercise_name(dev['substitute_exercise_id'], None, neo4j_client)
                    else:
                        exercise_name = ensure_exercise_name(s.get('exercise_id'), s.get('exercise_name'), neo4j_client)

                    block_sets.append({
                        'exercise_id': exercise_id,
                        'exercise_name': exercise_name,
                        'reps': dev.get('actual_reps') or s.get('prescribed_reps'),
                        'load_lbs': dev.get('actual_load_lbs') or s.get('prescribed_load_lbs'),
                        'rpe': dev.get('actual_rpe') or s.get('prescribed_rpe'),
                        'planned_set_id': set_id,
                        'notes': dev.get('notes') or s.get('notes')
                    })
                blocks.append({
                    'name': block.get('name', 'Block'),
                    'block_type': block.get('block_type', 'main'),
                    'modality': block.get('modality'),
                    'sets': block_sets
                })

            # 4. Write to Postgres with proper block structure
            result = postgres_client.log_workout_session(
                session_date=plan['date'],
                name=plan.get('goal', 'Workout'),
                blocks=blocks,
                sport_type=plan.get('sport_type', 'strength'),
                duration_minutes=actual_duration or plan.get('estimated_duration_minutes'),
                notes=session_notes or plan.get('notes'),
                session_rpe=session_rpe,  # Critical for sRPE-based training load
                source='from_plan',
                plan_id=plan_id
            )

            # 5. Create Neo4j reference node
            neo4j_ref = None
            neo4j_warning = ""
            try:
                neo4j_ref = neo4j_client.create_strength_workout_ref(
                    workout_id=result['session_id'],
                    date=plan['date'],
                    name=plan.get('goal', 'Workout'),
                    plan_id=plan_id,
                    person_id=person_id,
                    total_sets=result.get('set_count'),
                    total_volume_lbs=result.get('total_volume')
                )
                if not neo4j_ref:
                    logger.warning(f"Neo4j ref creation returned None for workout {result['session_id']}")
                    neo4j_warning = "\n⚠️ Neo4j sync failed (returned None) - run backfill_neo4j_workout_refs.py"
            except Exception as neo4j_err:
                logger.error(f"Failed to create Neo4j ref for workout {result['session_id']}: {neo4j_err}", exc_info=True)
                neo4j_warning = f"\n⚠️ Neo4j sync failed: {neo4j_err} - run backfill_neo4j_workout_refs.py"

            # 6. Update Postgres with Neo4j ID
            if neo4j_ref:
                postgres_client.update_session_neo4j_id(
                    result['session_id'],
                    neo4j_ref.get('id')
                )

            # 7. Update plan status
            neo4j_client.update_plan_status(plan_id, "completed")

            # Build sRPE info string
            srpe_info = ""
            if session_rpe and (actual_duration or plan.get('estimated_duration_minutes')):
                dur = actual_duration or plan.get('estimated_duration_minutes')
                srpe_load = session_rpe * dur
                srpe_info = f"\n**sRPE Load:** {srpe_load} AU (RPE {session_rpe} × {dur} min)"
            elif not session_rpe:
                srpe_info = "\n⚠️ **No session RPE provided** - sRPE load will be imputed"

            # Build block info
            block_info = f"\n**Blocks:** {result['block_count']}" if result.get('block_count', 0) > 1 else ""

            return [types.TextContent(
                type="text",
                text=f"""✅ Workout completed with deviations recorded!

**Session ID:** {result['session_id']} (Postgres)
**Neo4j Ref:** {neo4j_ref.get('id') if neo4j_ref else 'N/A'}
**From Plan:** {plan_id}{block_info}
**Sets:** {result['set_count']}
**Deviations:** {len(deviations)}{srpe_info}{neo4j_warning}

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
            
            if isinstance(workout_data, str):
                workout_data = json.loads(workout_data)
            
            logger.info(f"Logging ad-hoc workout for {workout_data.get('date')}")
            
            # ================================================================
            # WORKOUT TYPE DETECTION
            # Route to endurance if: sport, distance_miles, or endurance-y name
            # ================================================================
            is_endurance = (
                workout_data.get('sport') or
                workout_data.get('distance_miles') or
                workout_data.get('distance_km') or
                workout_data.get('avg_pace') or
                any(kw in workout_data.get('name', '').lower() 
                    for kw in ['run', 'walk', 'hike', 'bike', 'cycle', 'swim', 'row', 'ruck'])
            )
            
            if is_endurance:
                # ============================================================
                # ENDURANCE WORKOUT PATH
                # ============================================================
                logger.info(f"Detected endurance workout, routing to endurance_sessions")
                
                # Normalize distance to miles if km provided
                distance_miles = workout_data.get('distance_miles')
                if not distance_miles and workout_data.get('distance_km'):
                    distance_miles = float(workout_data['distance_km']) * 0.621371
                
                # Infer sport from name if not provided
                sport = workout_data.get('sport', 'running')
                name_lower = workout_data.get('name', '').lower()
                if not workout_data.get('sport'):
                    if any(k in name_lower for k in ['bike', 'cycle', 'cycling']):
                        sport = 'cycling'
                    elif any(k in name_lower for k in ['swim', 'swimming', 'pool']):
                        sport = 'swimming'
                    elif any(k in name_lower for k in ['hike', 'hiking', 'backpack']):
                        sport = 'hiking'
                    elif any(k in name_lower for k in ['walk', 'walking', 'ruck']):
                        sport = 'walking'
                    elif any(k in name_lower for k in ['row', 'rowing', 'erg']):
                        sport = 'rowing'
                    else:
                        sport = 'running'  # Default
                
                result = postgres_client.log_endurance_session(
                    session_date=workout_data['date'],
                    name=workout_data.get('name'),
                    sport=sport,
                    distance_miles=distance_miles,
                    duration_minutes=workout_data.get('duration_minutes'),
                    avg_pace=workout_data.get('avg_pace'),
                    avg_hr=workout_data.get('avg_hr'),
                    max_hr=workout_data.get('max_hr'),
                    elevation_gain_m=workout_data.get('elevation_gain_m'),
                    rpe=workout_data.get('rpe') or workout_data.get('session_rpe'),
                    notes=workout_data.get('notes'),
                    source='logged'
                )
                
                # Create Neo4j reference for endurance workout
                neo4j_ref = None
                neo4j_warning = ""
                try:
                    neo4j_ref = neo4j_client.create_endurance_workout_ref(
                        workout_id=result['session_id'],
                        date=workout_data['date'],
                        name=workout_data.get('name', f'{sport.title()} session'),
                        sport=sport,
                        person_id=person_id
                    )
                    if not neo4j_ref:
                        logger.warning(f"Neo4j ref creation returned None for endurance workout {result['session_id']}")
                        neo4j_warning = "\n⚠️ Neo4j sync failed (returned None) - run backfill_neo4j_workout_refs.py"
                except Exception as neo4j_err:
                    logger.error(f"Failed to create Neo4j ref for endurance workout {result['session_id']}: {neo4j_err}", exc_info=True)
                    neo4j_warning = f"\n⚠️ Neo4j sync failed: {neo4j_err} - run backfill_neo4j_workout_refs.py"

                if neo4j_ref:
                    postgres_client.update_endurance_session_neo4j_id(
                        result['session_id'],
                        neo4j_ref.get('id')
                    )

                # Build distance string
                dist_str = f"{result['distance_miles']:.1f} mi" if result.get('distance_miles') else "N/A"

                return [types.TextContent(
                    type="text",
                    text=f"""✅ Endurance workout logged!

**Date:** {workout_data['date']}
**Sport:** {result['sport']}
**Distance:** {dist_str}
**Session ID:** {result['session_id']} (Postgres)
**Neo4j Ref:** {neo4j_ref.get('id') if neo4j_ref else 'N/A'}{neo4j_warning}"""
                )]
            
            else:
                # ============================================================
                # STRENGTH WORKOUT PATH (original behavior)
                # ============================================================
                logger.info(f"Detected strength workout, routing to strength_sessions")

                # Detect input format: blocks (preferred) vs exercises (legacy)
                has_blocks = bool(workout_data.get("blocks"))
                has_exercises = bool(workout_data.get("exercises"))

                if has_blocks:
                    # --------------------------------------------------------
                    # NEW: Block-aware path - proper workouts → blocks → sets
                    # --------------------------------------------------------
                    logger.info("Using block-aware logging path")

                    # Resolve exercise IDs/names within blocks
                    resolved_blocks = []
                    for block in workout_data['blocks']:
                        resolved_sets = []
                        for s in block.get('sets', []):
                            exercise_id = s.get('exercise_id')
                            exercise_name = s.get('exercise_name') or s.get('name')

                            # Resolve if needed
                            if not exercise_id and exercise_name:
                                results = neo4j_client.search_exercises(exercise_name, limit=1)
                                if results and results[0]['score'] > 3.0:
                                    exercise_id = results[0]['exercise_id']
                                    exercise_name = results[0]['name']
                                else:
                                    exercise_id = 'CUSTOM:' + exercise_name.replace(' ', '_')
                                    neo4j_client.create_custom_exercise(exercise_id, exercise_name)

                            resolved_sets.append({
                                **s,
                                'exercise_id': exercise_id,
                                'exercise_name': exercise_name
                            })

                        resolved_blocks.append({
                            'name': block.get('name', 'Block'),
                            'block_type': block.get('block_type', 'main'),
                            'sets': resolved_sets
                        })

                    result = postgres_client.log_workout_session(
                        session_date=workout_data['date'],
                        name=workout_data.get('name', 'Ad-hoc Workout'),
                        blocks=resolved_blocks,
                        sport_type=workout_data.get('sport_type', 'strength'),
                        duration_minutes=workout_data.get('duration_minutes'),
                        notes=workout_data.get('notes'),
                        session_rpe=workout_data.get('session_rpe') or workout_data.get('rpe'),
                        source='logged'
                    )

                elif has_exercises:
                    # --------------------------------------------------------
                    # LEGACY: Flat exercise path - single block for all sets
                    # --------------------------------------------------------
                    logger.info("Using legacy flat exercise logging path")

                    sets = []
                    set_order = 1

                    for exercise in workout_data.get("exercises", []):
                        exercise_id = exercise.get("exercise_id")
                        exercise_name = exercise.get("exercise_name") or exercise.get("name")

                        if not exercise_id and exercise_name:
                            results = neo4j_client.search_exercises(exercise_name, limit=1)
                            if results and results[0]['score'] > 3.0:
                                exercise_id = results[0]['exercise_id']
                                exercise_name = results[0]['name']
                            else:
                                exercise_id = 'CUSTOM:' + exercise_name.replace(' ', '_')
                                neo4j_client.create_custom_exercise(exercise_id, exercise_name)

                        for s in exercise.get("sets", []):
                            sets.append({
                                'exercise_id': exercise_id,
                                'exercise_name': exercise_name,
                                'block_name': 'Main',
                                'block_type': 'main',
                                'set_order': set_order,
                                'actual_reps': s.get('reps'),
                                'actual_load_lbs': s.get('load_lbs'),
                                'actual_rpe': s.get('rpe'),
                                'notes': s.get('notes')
                            })
                            set_order += 1

                    result = postgres_client.log_strength_session(
                        session_date=workout_data['date'],
                        name=workout_data.get('name', 'Ad-hoc Workout'),
                        sets=sets,
                        duration_minutes=workout_data.get('duration_minutes'),
                        notes=workout_data.get('notes'),
                        session_rpe=workout_data.get('session_rpe') or workout_data.get('rpe'),
                        source='logged'
                    )

                else:
                    return [types.TextContent(
                        type="text",
                        text="❌ Error: workout_data must contain 'blocks' or 'exercises' array"
                    )]

                # Create Neo4j reference (common to both paths)
                neo4j_ref = None
                neo4j_warning = ""
                try:
                    neo4j_ref = neo4j_client.create_strength_workout_ref(
                        workout_id=result['session_id'],
                        date=workout_data['date'],
                        name=workout_data.get('name', 'Ad-hoc Workout'),
                        person_id=person_id,
                        total_sets=result.get('set_count'),
                        total_volume_lbs=result.get('total_volume')
                    )
                    if not neo4j_ref:
                        logger.warning(f"Neo4j ref creation returned None for workout {result['session_id']}")
                        neo4j_warning = "\n⚠️ Neo4j sync failed (returned None) - run backfill_neo4j_workout_refs.py"
                except Exception as neo4j_err:
                    logger.error(f"Failed to create Neo4j ref for workout {result['session_id']}: {neo4j_err}", exc_info=True)
                    neo4j_warning = f"\n⚠️ Neo4j sync failed: {neo4j_err} - run backfill_neo4j_workout_refs.py"

                if neo4j_ref:
                    postgres_client.update_session_neo4j_id(
                        result['session_id'],
                        neo4j_ref.get('id')
                    )

                # Build response with block count if available
                block_info = f"\n**Blocks:** {result['block_count']}" if result.get('block_count', 0) > 1 else ""

                return [types.TextContent(
                    type="text",
                    text=f"""✅ Strength workout logged!

**Date:** {workout_data['date']}
**Session ID:** {result['session_id']} (Postgres)
**Neo4j Ref:** {neo4j_ref.get('id') if neo4j_ref else 'N/A'}{block_info}
**Sets:** {result['set_count']}{neo4j_warning}"""
                )]

        except Exception as e:
            logger.error(f"Error logging workout: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # HISTORY TOOLS (Postgres - facts, per ADR-002)
    # =========================================================================
    
    elif name == "get_workout_by_date":
        try:
            workout_date = arguments["date"]
            logger.info(f"Getting workout for {workout_date}")
            
            workout = postgres_client.get_session_by_date(workout_date)
            
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
            
            workouts = postgres_client.get_recent_sessions(days)
            
            if not workouts:
                return [types.TextContent(
                    type="text",
                    text=f"No workouts in the last {days} days."
                )]
            
            summary = []
            for w in workouts:
                summary.append(
                    f"• **{w['session_date']}**: {w.get('name', 'workout')} - "
                    f"{w['total_sets']} sets, {w['total_volume_lbs']:.0f} lbs"
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
    logger.info("Starting Arnold Training Coach MCP Server (ADR-002 compliant)")

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
        postgres_client.close()
        logger.info("Arnold Training Coach MCP Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
