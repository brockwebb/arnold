#!/usr/bin/env python3
"""Arnold Memory MCP Server.

This MCP server provides context management and coaching continuity:
- load_briefing: Comprehensive context for conversation start
- store_observation: Persist coaching insights
- get_observations: Retrieve past observations
- get_block_summary: Get/generate block summaries
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from typing import Any
import asyncio
import json
import logging
import os

from neo4j_client import Neo4jMemoryClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/arnold-memory-mcp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize server
server = Server("arnold-memory-mcp")
neo4j_client = Neo4jMemoryClient()

# Default person_id (loaded from profile on first use)
_cached_person_id = None


def get_person_id() -> str:
    """Get person_id from profile or cache."""
    global _cached_person_id
    if _cached_person_id:
        return _cached_person_id
    
    # Try to load from profile.json
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
        types.Tool(
            name="load_briefing",
            description="""Load comprehensive coaching context for conversation start.

Call this FIRST in any training conversation. Returns everything needed for effective coaching:

- **Athlete identity**: Name, phenotype (lifelong athlete), total training age
- **Background**: Martial arts, endurance sports, running preferences  
- **Goals**: Active goals with required modalities, target dates, priorities
- **Training levels**: Per-modality level (novice/intermediate/advanced) and progression model
- **Current block**: Name, type, week X of Y, intent, volume/intensity targets
- **Medical**: Active injuries with constraints, resolved history
- **Recent workouts**: Last 14 days with patterns trained
- **Coaching observations**: Persistent notes from past conversations
- **Upcoming sessions**: Planned workouts
- **Equipment**: Available equipment

This establishes coaching continuity - Claude knows the full picture from message one.""",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        types.Tool(
            name="store_observation",
            description="""Store a coaching observation for future reference.

Use this to persist insights, patterns, preferences, or decisions that should inform future coaching:

- **pattern**: "Fatigue pattern emerges on deadlift set 3+ above 275lbs"
- **preference**: "Prefers compound movements over isolation work"
- **insight**: "Responds well to higher rep ranges on accessories"  
- **flag**: "Watch for form breakdown when fatigued"
- **decision**: "Agreed to prioritize deadlift over squat this block"

These observations are included in load_briefing for future conversations.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The observation content"
                    },
                    "observation_type": {
                        "type": "string",
                        "enum": ["pattern", "preference", "insight", "flag", "decision"],
                        "description": "Type of observation",
                        "default": "insight"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords for retrieval (e.g., ['deadlift', 'fatigue'])"
                    }
                },
                "required": ["content"]
            }
        ),
        types.Tool(
            name="get_observations",
            description="""Retrieve coaching observations from past conversations.

Optionally filter by:
- tags: Keywords to match
- observation_type: pattern/preference/insight/flag/decision

Returns most recent observations first.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags"
                    },
                    "observation_type": {
                        "type": "string",
                        "enum": ["pattern", "preference", "insight", "flag", "decision"],
                        "description": "Filter by type"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max observations to return",
                        "default": 20
                    }
                }
            }
        ),
        types.Tool(
            name="search_observations",
            description="""Semantic search over coaching observations using natural language.

Uses vector embeddings and cosine similarity to find relevant observations
even when exact keywords don't match.

Examples:
- "why does my deadlift break down?" → finds fatigue patterns, form notes
- "what works for recovery?" → finds sleep, nutrition, deload observations
- "shoulder issues" → finds mobility notes, pain patterns, modifications

This is the primary way to query coaching memory when you don't know
exact keywords or want to explore related insights.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                        "default": 5
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Minimum similarity score 0-1 (default 0.7)",
                        "default": 0.7
                    },
                    "observation_type": {
                        "type": "string",
                        "enum": ["pattern", "preference", "insight", "flag", "decision"],
                        "description": "Optional: filter by observation type"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_block_summary",
            description="""Get summary for a training block.

If summary exists, returns it. If not, returns block data for summarization.

Use at block end to capture what happened and what was learned.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "Block ID to get summary for"
                    }
                },
                "required": ["block_id"]
            }
        ),
        types.Tool(
            name="store_block_summary",
            description="""Store a summary for a completed training block.

Captures:
- content: Narrative summary of the block
- key_metrics: Important numbers (volume, PRs, compliance)
- key_learnings: What we learned for future blocks""",
            inputSchema={
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "Block ID to summarize"
                    },
                    "content": {
                        "type": "string",
                        "description": "Narrative summary"
                    },
                    "key_metrics": {
                        "type": "object",
                        "description": "Important metrics (e.g., {total_sessions: 12, compliance: 0.92})"
                    },
                    "key_learnings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key insights for future planning"
                    }
                },
                "required": ["block_id", "content"]
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
    # LOAD BRIEFING
    # =========================================================================
    
    if name == "load_briefing":
        try:
            logger.info(f"Loading briefing for {person_id}")
            briefing = neo4j_client.load_briefing(person_id)
            
            if not briefing:
                return [types.TextContent(
                    type="text",
                    text="❌ Could not load briefing. Check profile exists."
                )]
            
            # Format as readable briefing
            lines = []
            
            # ATHLETE
            athlete = briefing.get("athlete", {})
            lines.append(f"# COACHING CONTEXT: {athlete.get('name', 'Unknown')}")
            lines.append("")
            
            if athlete.get("phenotype"):
                lines.append(f"**Athlete Type:** {athlete.get('phenotype')} ({athlete.get('training_age_total', '?')} years total)")
                if athlete.get("phenotype_notes"):
                    lines.append(f"  {athlete.get('phenotype_notes')[:200]}...")
            
            # BACKGROUND
            bg = briefing.get("background", {})
            if any(bg.values()):
                lines.append("")
                lines.append("## Athletic Background")
                if bg.get("martial_arts"):
                    lines.append(f"- **Martial Arts:** {bg['martial_arts']}")
                if bg.get("triathlon"):
                    lines.append(f"- **Triathlon:** {bg['triathlon']}")
                if bg.get("cycling"):
                    lines.append(f"- **Cycling:** {bg['cycling']}")
                if bg.get("running_preference"):
                    lines.append(f"- **Running:** {bg['running_preference']}")
            
            # GOALS
            goals = briefing.get("goals", [])
            if goals:
                lines.append("")
                lines.append("## Active Goals")
                for g in goals:
                    target_str = ""
                    if g.get("target_date"):
                        target_str = f" (by {g['target_date']})"
                    lines.append(f"- **{g.get('name')}**{target_str} [{g.get('priority')}]")
                    for m in g.get("requires", []):
                        if m.get("modality"):
                            level_str = f"{m.get('level', '?')} level"
                            model_str = m.get('model', '?')
                            gaps_str = f", gaps: {m['gaps']}" if m.get('gaps') else ""
                            lines.append(f"  → {m['modality']}: {level_str}, {model_str}{gaps_str}")
            
            # TRAINING LEVELS
            levels = briefing.get("training_levels", {})
            if levels:
                lines.append("")
                lines.append("## Training Levels by Modality")
                for modality, data in levels.items():
                    gaps_str = f" | Gaps: {data['gaps']}" if data.get('gaps') else ""
                    lines.append(f"- **{modality}:** {data.get('level')} ({data.get('years', '?')} yrs) → {data.get('model', '?')}{gaps_str}")
            
            # CURRENT BLOCK
            block = briefing.get("current_block")
            if block:
                lines.append("")
                lines.append("## Current Block")
                lines.append(f"**{block.get('name')}** ({block.get('type')})")
                lines.append(f"- Week {block.get('week')} of {block.get('of_weeks')}")
                lines.append(f"- Dates: {block.get('dates')}")
                lines.append(f"- Intent: {block.get('intent')}")
                lines.append(f"- Volume: {block.get('volume')} | Intensity: {block.get('intensity')}")
                if block.get('serves'):
                    lines.append(f"- Serves: {', '.join(block['serves'])}")
            else:
                lines.append("")
                lines.append("## Current Block")
                lines.append("*No active block*")
            
            # MEDICAL
            medical = briefing.get("medical", {})
            active_injuries = medical.get("active_injuries", [])
            if active_injuries:
                lines.append("")
                lines.append("## Medical / Constraints")
                for inj in active_injuries:
                    status = inj.get('status', 'unknown')
                    side = f"{inj.get('side', '')} " if inj.get('side') else ""
                    lines.append(f"- **{inj.get('name')}** ({side}{inj.get('body_part')}) - {status}")
                    if inj.get('diagnosis'):
                        lines.append(f"  Dx: {inj['diagnosis']}")
                    if inj.get('weeks_post_surgery'):
                        lines.append(f"  {inj['weeks_post_surgery']} weeks post-surgery")
                    if inj.get('rehab_insights'):
                        lines.append(f"  Insight: {inj['rehab_insights']}")
                    if inj.get('constraints'):
                        lines.append(f"  Constraints: {', '.join(inj['constraints'])}")
            
            resolved = medical.get("resolved", [])
            if resolved:
                resolved_names = [f"{i.get('name')} ({i.get('outcome', 'resolved')})" for i in resolved]
                lines.append(f"- **Resolved:** {'; '.join(resolved_names)}")
            
            # RECENT WORKOUTS
            recent = briefing.get("recent_workouts", [])
            if recent:
                lines.append("")
                lines.append(f"## Recent Workouts ({briefing.get('workouts_this_week', 0)} this week)")
                for w in recent[:7]:  # Last 7
                    patterns = ", ".join(w.get("patterns", [])[:3]) or "—"
                    lines.append(f"- {w.get('date')}: {w.get('type', 'workout')} ({w.get('sets', 0)} sets) — {patterns}")
            
            # OBSERVATIONS
            observations = briefing.get("observations", [])
            if observations:
                lines.append("")
                lines.append("## Coaching Observations")
                for obs in observations[:5]:  # Most recent 5
                    obs_type = obs.get('observation_type', 'insight')
                    lines.append(f"- [{obs_type}] {obs.get('content')}")
            
            # UPCOMING
            upcoming = briefing.get("upcoming_sessions", [])
            if upcoming:
                lines.append("")
                lines.append("## Upcoming Sessions")
                for s in upcoming:
                    lines.append(f"- {s.get('date')}: {s.get('goal', 'Workout')} [{s.get('status')}]")
            
            # PATTERN GAPS
            pattern_gaps = briefing.get("pattern_gaps", [])
            if pattern_gaps:
                lines.append("")
                lines.append("## Pattern Gaps (7+ days)")
                for pg in pattern_gaps:
                    lines.append(f"- **{pg['pattern']}**: {pg['days']} days")
            
            # MUSCLE VOLUME THIS WEEK
            muscle_vol = briefing.get("muscle_volume_this_week", [])
            if muscle_vol:
                lines.append("")
                lines.append("## Muscle Volume This Week (Primary)")
                for mv in muscle_vol:
                    lines.append(f"- {mv['muscle']}: {mv['sets']} sets, {mv['reps']} reps")
            
            # EQUIPMENT
            equipment = briefing.get("equipment", [])
            if equipment:
                lines.append("")
                lines.append("## Equipment Available")
                eq_list = [e.get('equipment') for e in equipment if e.get('equipment')]
                lines.append(", ".join(eq_list[:10]))  # First 10
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error loading briefing: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # STORE OBSERVATION
    # =========================================================================
    
    elif name == "store_observation":
        try:
            content = arguments["content"]
            obs_type = arguments.get("observation_type", "insight")
            tags = arguments.get("tags", [])
            
            logger.info(f"Storing observation: {content[:50]}...")
            
            result = neo4j_client.store_observation(
                person_id=person_id,
                content=content,
                observation_type=obs_type,
                tags=tags
            )
            
            return [types.TextContent(
                type="text",
                text=f"✅ Observation stored\n\n**ID:** {result['id']}\n**Type:** {obs_type}\n**Tags:** {', '.join(tags) if tags else 'none'}"
            )]
            
        except Exception as e:
            logger.error(f"Error storing observation: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # GET OBSERVATIONS
    # =========================================================================
    
    elif name == "get_observations":
        try:
            tags = arguments.get("tags")
            obs_type = arguments.get("observation_type")
            limit = arguments.get("limit", 20)
            
            logger.info(f"Getting observations (tags={tags}, type={obs_type})")
            
            observations = neo4j_client.get_observations(
                person_id=person_id,
                tags=tags,
                observation_type=obs_type,
                limit=limit
            )
            
            if not observations:
                return [types.TextContent(
                    type="text",
                    text="No observations found matching criteria."
                )]
            
            lines = [f"**Found {len(observations)} observations:**\n"]
            for obs in observations:
                tags_str = f" [{', '.join(obs.get('tags', []))}]" if obs.get('tags') else ""
                lines.append(f"- **[{obs.get('observation_type')}]** {obs.get('content')}{tags_str}")
                lines.append(f"  _{obs.get('created_at')}_")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error getting observations: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # SEARCH OBSERVATIONS (Semantic)
    # =========================================================================
    
    elif name == "search_observations":
        try:
            query = arguments["query"]
            limit = arguments.get("limit", 5)
            threshold = arguments.get("threshold", 0.7)
            obs_type = arguments.get("observation_type")
            
            logger.info(f"Semantic search: '{query}' (limit={limit}, threshold={threshold})")
            
            observations = neo4j_client.search_observations(
                person_id=person_id,
                query=query,
                limit=limit,
                threshold=threshold,
                observation_type=obs_type
            )
            
            if not observations:
                return [types.TextContent(
                    type="text",
                    text=f"No observations found matching '{query}' (threshold: {threshold})"
                )]
            
            lines = [f"**Found {len(observations)} relevant observations:**\n"]
            for obs in observations:
                sim = obs.get('similarity', 0)
                sim_bar = "█" * int(sim * 10) + "░" * (10 - int(sim * 10))
                tags_str = f" [{', '.join(obs.get('tags', []))}]" if obs.get('tags') else ""
                lines.append(f"- **[{obs.get('observation_type')}]** {obs.get('content')}{tags_str}")
                lines.append(f"  {sim_bar} {sim:.1%} similarity | _{obs.get('created_at')}_")
                lines.append("")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error searching observations: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # GET BLOCK SUMMARY
    # =========================================================================
    
    elif name == "get_block_summary":
        try:
            block_id = arguments["block_id"]
            
            logger.info(f"Getting block summary for {block_id}")
            
            result = neo4j_client.get_block_summary(block_id)
            
            if not result:
                return [types.TextContent(
                    type="text",
                    text=f"Block not found: {block_id}"
                )]
            
            if result.get("needs_summarization"):
                return [types.TextContent(
                    type="text",
                    text=f"""**Block needs summarization:**

**Block:** {result['block'].get('name')} ({result['block'].get('block_type')})
**Dates:** {result['block'].get('start_date')} → {result['block'].get('end_date')}
**Intent:** {result['block'].get('intent')}
**Goals:** {', '.join(result.get('goals', []))}
**Workouts:** {result.get('workout_count')}
**Total Sets:** {result.get('total_sets')}

Use `store_block_summary` to create the summary."""
                )]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error getting block summary: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    # =========================================================================
    # STORE BLOCK SUMMARY
    # =========================================================================
    
    elif name == "store_block_summary":
        try:
            block_id = arguments["block_id"]
            content = arguments["content"]
            key_metrics = arguments.get("key_metrics")
            key_learnings = arguments.get("key_learnings")
            
            logger.info(f"Storing block summary for {block_id}")
            
            result = neo4j_client.store_block_summary(
                block_id=block_id,
                content=content,
                key_metrics=key_metrics,
                key_learnings=key_learnings
            )
            
            return [types.TextContent(
                type="text",
                text=f"✅ Block summary stored\n\n**ID:** {result['id']}"
            )]
            
        except Exception as e:
            logger.error(f"Error storing block summary: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    else:
        return [types.TextContent(
            type="text",
            text=f"❌ Unknown tool: {name}"
        )]


def main():
    """Run the MCP server."""
    logger.info("Starting Arnold Memory MCP Server")
    asyncio.run(run_server())


async def run_server():
    """Async server runner."""
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
        logger.info("Arnold Memory MCP Server stopped")


if __name__ == "__main__":
    main()
