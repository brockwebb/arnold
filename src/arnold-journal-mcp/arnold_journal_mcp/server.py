#!/usr/bin/env python3
"""Arnold Journal MCP Server.

This MCP server provides tools for:
- Logging subjective observations (fatigue, soreness, mood, symptoms)
- Capturing nutrition and supplement data
- Recording workout feedback
- Creating relationships to workouts, plans, injuries, goals
- Retrieving entries for coach/doc briefings

Architecture (per ADR-001):
- Postgres: Facts (raw_text, extracted data, severity, tags)
- Neo4j: Relationships (EXPLAINS workout, AFFECTS plan, RELATED_TO injury)
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from typing import Any
import asyncio
import json
import logging
from datetime import datetime, date

from postgres_client import PostgresJournalClient
from neo4j_client import Neo4jJournalClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/arnold-journal-mcp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize server and clients
server = Server("arnold-journal-mcp")
pg_client = PostgresJournalClient()
neo4j_client = Neo4jJournalClient()


def parse_date(date_str: str) -> date:
    """Parse date string to date object."""
    if date_str.lower() in ('today', 'now'):
        return date.today()
    if date_str.lower() == 'yesterday':
        from datetime import timedelta
        return date.today() - timedelta(days=1)
    return datetime.strptime(date_str, "%Y-%m-%d").date()


@server.list_tools()
async def list_tools_handler() -> list[types.Tool]:
    """List available tools."""
    return [
        # =====================================================================
        # ENTRY CREATION
        # =====================================================================
        types.Tool(
            name="log_entry",
            description="""Log a journal entry capturing subjective data.

Use this when the user shares observations about:
- Fatigue, energy levels, soreness
- Symptoms (pain, dizziness, cold extremities)
- Mood, stress, mental state  
- Nutrition, hydration, caffeine
- Supplements, medications
- Workout feedback (too easy, too hard, form issues)
- Sleep quality notes
- Any other subjective experience

Claude should:
1. Extract structured data from natural language
2. Determine appropriate category and severity
3. Generate a brief summary
4. Call this tool to create the entry

After creating the entry, use link_* tools to create relationships.

Entry types: observation, nutrition, supplement, symptom, mood, feedback
Categories: recovery, nutrition, mental, physical, medical, training
Severity: info (routine), notable (worth tracking), concerning (needs attention), urgent (immediate)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "entry_date": {
                        "type": "string",
                        "description": "Date being described (YYYY-MM-DD, 'today', 'yesterday')"
                    },
                    "entry_type": {
                        "type": "string",
                        "enum": ["observation", "nutrition", "supplement", "symptom", "mood", "feedback"],
                        "description": "Type of entry"
                    },
                    "raw_text": {
                        "type": "string",
                        "description": "Original user input (always preserve)"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["recovery", "nutrition", "mental", "physical", "medical", "training"],
                        "description": "Category for organization"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["info", "notable", "concerning", "urgent"],
                        "description": "Severity level (default: info)"
                    },
                    "extracted": {
                        "type": "object",
                        "description": "Structured data extracted by Claude (e.g., {fatigue: 8, soreness: [{area: 'legs', level: 7}]})"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary (1-2 sentences) for lists/reports"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for retrieval (e.g., ['fatigue', 'legs', 'post_surgery'])"
                    }
                },
                "required": ["entry_date", "entry_type", "raw_text"]
            }
        ),
        
        # =====================================================================
        # RELATIONSHIP TOOLS
        # =====================================================================
        types.Tool(
            name="link_to_workout",
            description="""Link a journal entry to a workout.

Use when an entry EXPLAINS what happened during a workout.
Example: "Legs felt heavy during today's run" → link to today's EnduranceWorkout

Can also use DOCUMENTS for symptom entries, FEEDBACK for feedback entries.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "log_entry_id": {
                        "type": "string",
                        "description": "Neo4j ID of the LogEntry (returned from log_entry)"
                    },
                    "workout_id": {
                        "type": "string",
                        "description": "Neo4j ID of the workout (from find_workouts_for_date)"
                    },
                    "relationship": {
                        "type": "string",
                        "enum": ["EXPLAINS", "DOCUMENTS", "FEEDBACK"],
                        "description": "Type of relationship (default: EXPLAINS)"
                    }
                },
                "required": ["log_entry_id", "workout_id"]
            }
        ),
        
        types.Tool(
            name="link_to_plan",
            description="""Link a journal entry to a planned workout.

Use when an entry should AFFECT a future plan.
Example: "Feeling too fatigued for heavy squats tomorrow" → link to tomorrow's plan""",
            inputSchema={
                "type": "object",
                "properties": {
                    "log_entry_id": {
                        "type": "string",
                        "description": "Neo4j ID of the LogEntry"
                    },
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID of the PlannedWorkout"
                    }
                },
                "required": ["log_entry_id", "plan_id"]
            }
        ),
        
        types.Tool(
            name="link_to_injury",
            description="""Link a journal entry to an injury.

Use when an entry is RELATED_TO an injury (pain, recovery progress).
Example: "Knee feeling better today, no pain on stairs" → link to knee injury""",
            inputSchema={
                "type": "object",
                "properties": {
                    "log_entry_id": {
                        "type": "string",
                        "description": "Neo4j ID of the LogEntry"
                    },
                    "injury_id": {
                        "type": "string",
                        "description": "Neo4j ID of the Injury"
                    }
                },
                "required": ["log_entry_id", "injury_id"]
            }
        ),
        
        types.Tool(
            name="link_to_goal",
            description="""Link a journal entry to a goal.

Use when an entry INFORMS a goal.
Example: "Making progress on pull-ups, got 3 clean reps" → link to ring dips goal""",
            inputSchema={
                "type": "object",
                "properties": {
                    "log_entry_id": {
                        "type": "string",
                        "description": "Neo4j ID of the LogEntry"
                    },
                    "goal_id": {
                        "type": "string",
                        "description": "Neo4j ID of the Goal"
                    }
                },
                "required": ["log_entry_id", "goal_id"]
            }
        ),
        
        # =====================================================================
        # RETRIEVAL - POSTGRES (Facts)
        # =====================================================================
        types.Tool(
            name="get_recent_entries",
            description="""Get recent journal entries from Postgres.

Use at conversation start to understand recent subjective state.
Returns entries from the last N days with summary, severity, and review status.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days_back": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 7)"
                    }
                }
            }
        ),
        
        types.Tool(
            name="get_unreviewed_entries",
            description="""Get journal entries that haven't been reviewed.

Use for coach/doc briefings to surface entries needing attention.
Returns entries ordered by severity (urgent first).""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        types.Tool(
            name="get_entries_by_severity",
            description="""Get entries at or above a severity level.

Use to surface concerning or urgent entries for medical attention.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_severity": {
                        "type": "string",
                        "enum": ["info", "notable", "concerning", "urgent"],
                        "description": "Minimum severity to include (default: notable)"
                    }
                }
            }
        ),
        
        types.Tool(
            name="get_entries_for_date",
            description="""Get all journal entries for a specific date.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date to query (YYYY-MM-DD, 'today', 'yesterday')"
                    }
                },
                "required": ["date"]
            }
        ),
        
        types.Tool(
            name="search_entries",
            description="""Search journal entries with filters.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to search for (matches any)"
                    },
                    "entry_type": {
                        "type": "string",
                        "enum": ["observation", "nutrition", "supplement", "symptom", "mood", "feedback"]
                    },
                    "category": {
                        "type": "string",
                        "enum": ["recovery", "nutrition", "mental", "physical", "medical", "training"]
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "Number of days to search (default: 30)"
                    }
                }
            }
        ),
        
        # =====================================================================
        # RETRIEVAL - NEO4J (Relationships)
        # =====================================================================
        types.Tool(
            name="get_entries_for_workout",
            description="""Get journal entries linked to a specific workout (via Neo4j).

Use when reviewing a workout to see associated subjective notes.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_id": {
                        "type": "string",
                        "description": "Neo4j ID of the workout"
                    }
                },
                "required": ["workout_id"]
            }
        ),
        
        types.Tool(
            name="get_entries_for_injury",
            description="""Get journal entries related to an injury (via Neo4j).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "injury_id": {
                        "type": "string",
                        "description": "Neo4j ID of the injury"
                    }
                },
                "required": ["injury_id"]
            }
        ),
        
        types.Tool(
            name="get_entries_with_relationships",
            description="""Get entries for a date with all their Neo4j relationships.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date to query (YYYY-MM-DD, 'today', 'yesterday')"
                    }
                },
                "required": ["date"]
            }
        ),
        
        # =====================================================================
        # DISCOVERY (Find things to link to)
        # =====================================================================
        types.Tool(
            name="find_workouts_for_date",
            description="""Find workouts on a date to link journal entries to.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date to search (YYYY-MM-DD, 'today', 'yesterday')"
                    },
                    "workout_type": {
                        "type": "string",
                        "enum": ["endurance", "strength"],
                        "description": "Filter by type (optional)"
                    }
                },
                "required": ["date"]
            }
        ),
        
        types.Tool(
            name="get_active_injuries",
            description="""Get active injuries for linking journal entries.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        types.Tool(
            name="get_active_goals",
            description="""Get active goals for linking journal entries.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        # =====================================================================
        # MANAGEMENT
        # =====================================================================
        types.Tool(
            name="update_entry",
            description="""Update an existing journal entry in Postgres.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": "Postgres ID of the entry to update"
                    },
                    "extracted": {"type": "object"},
                    "summary": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "notable", "concerning", "urgent"]
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["entry_id"]
            }
        ),
        
        types.Tool(
            name="mark_reviewed",
            description="""Mark a journal entry as reviewed by coach/doc.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": "Postgres ID of the entry"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional review notes"
                    }
                },
                "required": ["entry_id"]
            }
        ),
        
        # =====================================================================
        # DATA ANNOTATIONS (Explaining data gaps/anomalies)
        # =====================================================================
        types.Tool(
            name="create_annotation",
            description="""Create a data annotation explaining a data gap or anomaly.

Use when the user explains why data looks unusual:
- "My HRV will be off for a few days after that birthday workout"
- "Sleep data is missing because I forgot to wear my ring"
- "ACWR is high because I just started training again post-surgery"

Claude should:
1. Parse the natural language to extract date range, target metric, and reason
2. Determine appropriate reason_code
3. Generate a clear explanation
4. Call this tool to create the annotation

Reason codes:
- expected: Normal variation (hard workout, travel, life events)
- device_issue: Sensor problem, app not syncing, forgot to wear device
- surgery: Post-surgical recovery affecting metrics
- injury: Active injury affecting training/metrics
- illness: Sick, affecting all metrics
- travel: Travel affecting sleep, training, routine
- deload: Intentional reduced training
- data_quality: Known data issue, bad import, etc.

Target types: biometric, training, general
Target metrics: hrv, sleep, recovery_score, rhr, acwr, all, etc.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "annotation_date": {
                        "type": "string",
                        "description": "Start date (YYYY-MM-DD, 'today', 'yesterday')"
                    },
                    "date_range_end": {
                        "type": "string",
                        "description": "End date if range (YYYY-MM-DD, optional)"
                    },
                    "target_type": {
                        "type": "string",
                        "enum": ["biometric", "training", "general"],
                        "description": "Type of data being annotated"
                    },
                    "target_metric": {
                        "type": "string",
                        "description": "Specific metric (hrv, sleep, acwr, all, etc.)"
                    },
                    "reason_code": {
                        "type": "string",
                        "enum": ["expected", "device_issue", "surgery", "injury", "illness", "travel", "deload", "data_quality"],
                        "description": "Reason category"
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Human-readable explanation of why data looks this way"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for retrieval (optional)"
                    }
                },
                "required": ["annotation_date", "target_type", "reason_code", "explanation"]
            }
        ),
        
        types.Tool(
            name="get_active_annotations",
            description="""Get active data annotations.

Use to see what data explanations are currently in effect.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days_back": {
                        "type": "integer",
                        "description": "How far back to look (default: 30)"
                    }
                }
            }
        ),
        
        types.Tool(
            name="deactivate_annotation",
            description="""Mark an annotation as resolved/inactive.

Use when the condition being explained has passed.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "annotation_id": {
                        "type": "integer",
                        "description": "ID of the annotation to deactivate"
                    }
                },
                "required": ["annotation_id"]
            }
        ),
    ]


@server.call_tool()
async def call_tool_handler(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with args: {json.dumps(arguments, default=str)}")
    
    try:
        result = await _handle_tool(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _handle_tool(name: str, args: dict) -> Any:
    """Route tool calls to handlers."""
    
    # =========================================================================
    # ENTRY CREATION
    # =========================================================================
    if name == "log_entry":
        entry_date = parse_date(args.get("entry_date", "today"))
        
        # 1. Create in Postgres (facts)
        pg_result = pg_client.create_entry(
            entry_date=entry_date,
            entry_type=args["entry_type"],
            raw_text=args["raw_text"],
            category=args.get("category"),
            severity=args.get("severity", "info"),
            extracted=args.get("extracted"),
            summary=args.get("summary"),
            tags=args.get("tags"),
            source="chat"
        )
        
        postgres_id = pg_result["id"]
        
        # 2. Create in Neo4j (for relationships)
        neo4j_id = neo4j_client.create_log_entry_node(
            postgres_id=postgres_id,
            entry_date=entry_date,
            entry_type=args["entry_type"],
            category=args.get("category"),
            severity=args.get("severity", "info"),
            summary=args.get("summary"),
            tags=args.get("tags")
        )
        
        # 3. Update Postgres with Neo4j ID
        if neo4j_id:
            pg_client.update_entry(postgres_id, neo4j_id=neo4j_id)
        
        return {
            "status": "created",
            "postgres_id": postgres_id,
            "neo4j_id": neo4j_id,
            "entry_date": str(entry_date),
            "entry_type": args["entry_type"],
            "severity": args.get("severity", "info"),
            "summary": args.get("summary"),
            "message": f"Logged {args['entry_type']} entry. Use link_* tools to create relationships."
        }
    
    # =========================================================================
    # RELATIONSHIP CREATION
    # =========================================================================
    elif name == "link_to_workout":
        relationship = args.get("relationship", "EXPLAINS")
        success = neo4j_client.link_to_workout(
            args["log_entry_id"],
            args["workout_id"],
            relationship
        )
        return {
            "status": "linked" if success else "failed",
            "relationship": relationship,
            "log_entry_id": args["log_entry_id"],
            "workout_id": args["workout_id"]
        }
    
    elif name == "link_to_plan":
        success = neo4j_client.link_to_plan(
            args["log_entry_id"],
            args["plan_id"]
        )
        return {
            "status": "linked" if success else "failed",
            "relationship": "AFFECTS",
            "log_entry_id": args["log_entry_id"],
            "plan_id": args["plan_id"]
        }
    
    elif name == "link_to_injury":
        success = neo4j_client.link_to_injury(
            args["log_entry_id"],
            args["injury_id"]
        )
        return {
            "status": "linked" if success else "failed",
            "relationship": "RELATED_TO",
            "log_entry_id": args["log_entry_id"],
            "injury_id": args["injury_id"]
        }
    
    elif name == "link_to_goal":
        success = neo4j_client.link_to_goal(
            args["log_entry_id"],
            args["goal_id"]
        )
        return {
            "status": "linked" if success else "failed",
            "relationship": "INFORMS",
            "log_entry_id": args["log_entry_id"],
            "goal_id": args["goal_id"]
        }
    
    # =========================================================================
    # POSTGRES RETRIEVAL (Facts)
    # =========================================================================
    elif name == "get_recent_entries":
        days = args.get("days_back", 7)
        entries = pg_client.get_recent_entries(days)
        return {"count": len(entries), "days_back": days, "entries": entries}
    
    elif name == "get_unreviewed_entries":
        entries = pg_client.get_unreviewed_entries()
        return {"count": len(entries), "entries": entries}
    
    elif name == "get_entries_by_severity":
        min_severity = args.get("min_severity", "notable")
        entries = pg_client.get_entries_by_severity(min_severity)
        return {"min_severity": min_severity, "count": len(entries), "entries": entries}
    
    elif name == "get_entries_for_date":
        target_date = parse_date(args["date"])
        entries = pg_client.get_entries_for_date(target_date)
        return {"date": str(target_date), "count": len(entries), "entries": entries}
    
    elif name == "search_entries":
        entries = pg_client.search_entries(
            tags=args.get("tags"),
            entry_type=args.get("entry_type"),
            category=args.get("category"),
            days_back=args.get("days_back", 30)
        )
        return {"filters": args, "count": len(entries), "entries": entries}
    
    # =========================================================================
    # NEO4J RETRIEVAL (Relationships)
    # =========================================================================
    elif name == "get_entries_for_workout":
        entries = neo4j_client.get_entries_for_workout(args["workout_id"])
        return {"workout_id": args["workout_id"], "count": len(entries), "entries": entries}
    
    elif name == "get_entries_for_injury":
        entries = neo4j_client.get_entries_for_injury(args["injury_id"])
        return {"injury_id": args["injury_id"], "count": len(entries), "entries": entries}
    
    elif name == "get_entries_with_relationships":
        target_date = parse_date(args["date"])
        entries = neo4j_client.get_entries_for_date_with_relationships(target_date)
        return {"date": str(target_date), "count": len(entries), "entries": entries}
    
    # =========================================================================
    # DISCOVERY
    # =========================================================================
    elif name == "find_workouts_for_date":
        target_date = parse_date(args["date"])
        workouts = neo4j_client.find_workout_by_date(
            target_date,
            args.get("workout_type")
        )
        return {"date": str(target_date), "count": len(workouts), "workouts": workouts}
    
    elif name == "get_active_injuries":
        injuries = neo4j_client.get_active_injuries()
        return {"count": len(injuries), "injuries": injuries}
    
    elif name == "get_active_goals":
        goals = neo4j_client.get_active_goals()
        return {"count": len(goals), "goals": goals}
    
    # =========================================================================
    # MANAGEMENT
    # =========================================================================
    elif name == "update_entry":
        result = pg_client.update_entry(
            entry_id=args["entry_id"],
            extracted=args.get("extracted"),
            summary=args.get("summary"),
            severity=args.get("severity"),
            tags=args.get("tags")
        )
        return {"status": "updated", "entry": result}
    
    elif name == "mark_reviewed":
        success = pg_client.mark_reviewed(args["entry_id"], args.get("notes"))
        return {"status": "reviewed" if success else "not_found", "entry_id": args["entry_id"]}
    
    # =========================================================================
    # DATA ANNOTATIONS
    # =========================================================================
    elif name == "create_annotation":
        annotation_date = parse_date(args["annotation_date"])
        date_range_end = parse_date(args["date_range_end"]) if args.get("date_range_end") else None
        
        result = pg_client.create_annotation(
            annotation_date=annotation_date,
            target_type=args["target_type"],
            reason_code=args["reason_code"],
            explanation=args["explanation"],
            date_range_end=date_range_end,
            target_metric=args.get("target_metric"),
            tags=args.get("tags")
        )
        
        return {
            "status": "created",
            "annotation": result,
            "message": f"Created annotation for {args['target_type']}/{args.get('target_metric', 'all')} from {annotation_date}" + 
                       (f" to {date_range_end}" if date_range_end else "")
        }
    
    elif name == "get_active_annotations":
        days = args.get("days_back", 30)
        annotations = pg_client.get_active_annotations(days)
        return {"count": len(annotations), "days_back": days, "annotations": annotations}
    
    elif name == "deactivate_annotation":
        success = pg_client.deactivate_annotation(args["annotation_id"])
        return {"status": "deactivated" if success else "failed", "annotation_id": args["annotation_id"]}
    
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server."""
    logger.info("Starting Arnold Journal MCP server")
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise
    finally:
        pg_client.close()
        neo4j_client.close()
        logger.info("Arnold Journal MCP server stopped")


if __name__ == "__main__":
    asyncio.run(main())
