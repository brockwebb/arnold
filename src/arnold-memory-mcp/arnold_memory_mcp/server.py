#!/usr/bin/env python3
"""Arnold Memory MCP Server.

This MCP server provides context management and coaching continuity:
- load_briefing: Comprehensive context for conversation start (CONSOLIDATED)
- store_observation: Persist coaching insights
- get_observations: Retrieve past observations
- search_observations: Semantic search over observations
- debrief_session: End-of-session knowledge capture protocol
- get_block_summary: Get/generate block summaries
- store_block_summary: Store block summaries

ARCHITECTURE NOTE (Jan 2026):
load_briefing consolidates context from BOTH databases:
- Neo4j: Goals, block, injuries, observations, relationships
- Postgres: Readiness (HRV, sleep), training load (ACWR), HRR trends

This eliminates the need to call multiple tools at conversation start.
One call gets everything the coach needs.
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from typing import Any, List, Dict
import asyncio
import json
import logging
import os

from neo4j_client import Neo4jMemoryClient
from postgres_client import PostgresAnalyticsClient

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
postgres_client = PostgresAnalyticsClient()

# Default person_id (loaded from profile on first use)
_cached_person_id = None


# =============================================================================
# PERSONALITY ASSEMBLY
# =============================================================================

# Tags that indicate observations relevant to coaching personality
PERSONALITY_TAGS = {
    # Physical patterns
    'physical': {'asymmetry', 'fatigue', 'form', 'grip', 'balance', 'mobility', 
                 'flexibility', 'rom', 'technique', 'breakdown'},
    # Programming preferences
    'programming': {'programming', 'loading', 'autoregulation', 'pyramid', 
                   'progression', 'rep_scheme', 'volume', 'intensity'},
    # Communication/interaction
    'communication': {'communication', 'feedback', 'coaching_style', 'trust', 
                     'interaction', 'preference'},
    # Baselines and reference points
    'baselines': {'baseline', 'progression', 'pr', 'working_weight', 'capacity'},
    # Flags and constraints
    'flags': {'surgery', 'injury', 'clearance', 'recovery', 'pain', 'watch', 'caution'}
}


def categorize_observation(obs: Dict) -> str:
    """Determine which category an observation belongs to based on type and tags."""
    obs_type = obs.get('observation_type', '')
    tags = set(obs.get('tags', []) or [])
    
    # Flags are always flags
    if obs_type == 'flag':
        return 'flags'
    
    # Check tag overlap with each category
    scores = {}
    for category, category_tags in PERSONALITY_TAGS.items():
        overlap = len(tags & category_tags)
        if overlap > 0:
            scores[category] = overlap
    
    if scores:
        return max(scores, key=scores.get)
    
    # Default based on type
    if obs_type == 'pattern':
        return 'physical'
    elif obs_type == 'preference':
        return 'programming'
    elif obs_type == 'decision':
        return 'programming'
    
    return 'other'


def truncate_observation(content: str, max_len: int = 150) -> str:
    """Truncate observation to actionable summary."""
    if len(content) <= max_len:
        return content
    # Find a good break point
    truncated = content[:max_len]
    # Try to break at sentence or phrase boundary
    for sep in ['. ', ' - ', ', ', ' ']:
        last_sep = truncated.rfind(sep)
        if last_sep > max_len // 2:
            return truncated[:last_sep + 1].strip()
    return truncated.strip() + '...'


def assemble_coaching_notes(observations: List[Dict]) -> List[str]:
    """
    Assemble observations into categorized coaching notes.
    
    Instead of listing raw observations, organizes them into actionable
    coaching guidance by category.
    
    Returns list of formatted lines for the briefing.
    """
    if not observations:
        return []
    
    # Categorize observations
    categorized = {
        'physical': [],
        'programming': [],
        'communication': [],
        'baselines': [],
        'flags': [],
        'other': []
    }
    
    for obs in observations:
        category = categorize_observation(obs)
        categorized[category].append(obs)
    
    lines = []
    lines.append("")
    lines.append(f"## Athlete-Specific Coaching Notes")
    lines.append(f"*Based on {len(observations)} observations from past sessions*")
    
    # Physical Patterns
    physical = categorized['physical'][:4]  # Limit to 4
    if physical:
        lines.append("")
        lines.append("### Physical Patterns")
        for obs in physical:
            content = truncate_observation(obs.get('content', ''))
            lines.append(f"- {content}")
    
    # Programming Approach
    programming = categorized['programming'][:4]
    if programming:
        lines.append("")
        lines.append("### Programming Approach")
        for obs in programming:
            content = truncate_observation(obs.get('content', ''))
            lines.append(f"- {content}")
    
    # Communication Style
    communication = categorized['communication'][:3]
    if communication:
        lines.append("")
        lines.append("### Communication")
        for obs in communication:
            content = truncate_observation(obs.get('content', ''))
            lines.append(f"- {content}")
    
    # Active Flags (always show all)
    flags = categorized['flags']
    if flags:
        lines.append("")
        lines.append("### ⚠️ Active Flags")
        for obs in flags:
            content = truncate_observation(obs.get('content', ''), max_len=200)
            lines.append(f"- {content}")
    
    # Reference Points / Baselines
    baselines = categorized['baselines'][:3]
    if baselines:
        lines.append("")
        lines.append("### Reference Points")
        for obs in baselines:
            content = truncate_observation(obs.get('content', ''))
            lines.append(f"- {content}")
    
    return lines


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

Call this FIRST in any training conversation. Returns EVERYTHING needed for effective coaching in ONE call:

**From Neo4j (relationships/context):**
- Athlete identity: Name, phenotype (lifelong athlete), total training age
- Background: Martial arts, endurance sports, running preferences  
- Goals: Active goals with required modalities, target dates, priorities
- Training levels: Per-modality level (novice/intermediate/advanced) and progression model
- Current block: Name, type, week X of Y, intent, volume/intensity targets
- Medical: Active injuries with constraints, resolved history
- Coaching observations: Patterns, preferences, flags assembled from past sessions
- Upcoming sessions: Planned workouts
- Equipment: Available equipment

**From Postgres (analytics/measurements):**
- Readiness: Today's HRV (with 7d/30d comparisons), sleep, resting HR
- Training load: ACWR (injury risk zone), 28-day volume, pattern gaps
- HRR trends: Per-stratum recovery trends and alerts
- Data gaps: Missing sensor data, active annotations

**Coaching notes:** Pre-computed insights surfaced for coach attention

This is THE consolidated briefing. No need to call multiple tools.""",
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
        ),
        types.Tool(
            name="debrief_session",
            description="""End-of-session knowledge capture protocol.

Trigger: User says "Coach, let's debrief" or similar.

This tool captures learnings from the current session and stores them in the 
knowledge graph. It batches multiple observations and creates relationship links.

**The collaborative flow:**
1. Claude reviews the session and proposes observations to capture
2. User confirms, corrects, or adds ("don't forget X")
3. Claude calls this tool with the agreed observations
4. Tool stores observations and creates graph relationships

**What to look for (guidelines, not checklist):**
- **Emergent preferences**: Athlete keeps adding warmups? That's a preference.
- **Deviations from plan**: Changed exercises, adjusted loads, skipped sets — and WHY
- **Patterns noticed**: HRV correlations, fatigue signatures, time-of-day effects
- **Feedback received**: How athlete responded to coaching cues or suggestions
- **Medical/symptoms**: Pain, discomfort, or recovery notes not captured elsewhere
- **What worked**: Cues that clicked, progressions that felt right
- **What didn't**: Approaches to avoid next time

Use your judgment. Not everything needs capturing — focus on what will inform 
future coaching. Quality over quantity.

Returns summary of stored observations and created links.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "observations": {
                        "type": "array",
                        "description": "List of observations to store",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "The observation content"
                                },
                                "observation_type": {
                                    "type": "string",
                                    "enum": ["pattern", "preference", "insight", "flag", "decision"],
                                    "description": "Type of observation"
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Keywords for retrieval"
                                },
                                "link_to_workout": {
                                    "type": "string",
                                    "description": "Optional: workout date (YYYY-MM-DD) to link this observation to"
                                },
                                "link_to_goal": {
                                    "type": "string",
                                    "description": "Optional: goal name to link this observation to"
                                },
                                "link_to_injury": {
                                    "type": "string",
                                    "description": "Optional: injury name to link this observation to"
                                }
                            },
                            "required": ["content", "observation_type"]
                        }
                    },
                    "session_summary": {
                        "type": "string",
                        "description": "Optional brief narrative of the session"
                    }
                },
                "required": ["observations"]
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
    # LOAD BRIEFING (CONSOLIDATED)
    # =========================================================================
    
    if name == "load_briefing":
        try:
            logger.info(f"Loading consolidated briefing for {person_id}")
            
            # Get Neo4j context (relationships, goals, block, etc.)
            briefing = neo4j_client.load_briefing(person_id)
            
            if not briefing:
                return [types.TextContent(
                    type="text",
                    text="❌ Could not load briefing. Check profile exists."
                )]
            
            # Get Postgres analytics (readiness, training load, HRR)
            analytics = postgres_client.get_analytics_for_briefing()
            
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
            
            # =================================================================
            # ANALYTICS SECTION (NEW - from Postgres)
            # =================================================================
            lines.append("")
            lines.append("## Today's Status")
            
            readiness = analytics.get("readiness", {})
            training_load = analytics.get("training_load", {})
            hrr = analytics.get("hrr", {})
            
            # HRV
            if readiness.get("hrv"):
                hrv = readiness["hrv"]
                trend_emoji = "📈" if hrv.get("trend") == "improving" else "📉" if hrv.get("trend") == "declining" else "➡️"
                vs_7d = f" ({hrv['vs_7d_pct']:+d}% vs 7d)" if hrv.get('vs_7d_pct') else ""
                lines.append(f"- **HRV:** {hrv['value']} ms{vs_7d} {trend_emoji}")
            else:
                lines.append("- **HRV:** No data")
            
            # Sleep
            if readiness.get("sleep"):
                sleep = readiness["sleep"]
                quality_str = f" ({sleep['quality_pct']}% quality)" if sleep.get('quality_pct') else ""
                lines.append(f"- **Sleep:** {sleep['hours']} hrs{quality_str}")
            else:
                lines.append("- **Sleep:** No data")
            
            # RHR
            if readiness.get("resting_hr"):
                lines.append(f"- **Resting HR:** {readiness['resting_hr']} bpm")
            
            # ACWR
            if training_load.get("acwr"):
                acwr = training_load["acwr"]
                zone_emoji = "🔴" if acwr['zone'] == 'high_risk' else "🟢" if acwr['zone'] == 'optimal' else "🟡"
                lines.append(f"- **ACWR:** {acwr['value']} ({acwr['zone']}) {zone_emoji}")
            
            # HRR summary
            if hrr.get("intervals") and hrr.get("strata"):
                hrr_summary = []
                for strat, data in hrr["strata"].items():
                    if isinstance(data, dict) and data.get("baseline_hrr60"):
                        trend = data.get("trend", "stable")
                        alert = "⚠️" if data.get("has_alert") else ""
                        hrr_summary.append(f"{strat}: {data['current_avg']} bpm ({trend}){alert}")
                if hrr_summary:
                    lines.append(f"- **HRR:** {'; '.join(hrr_summary)}")
            
            # Training load summary
            lines.append(f"- **28d Volume:** {training_load.get('workouts_28d', 0)} workouts, {training_load.get('total_sets_28d', 0)} sets")
            
            # Pattern gaps
            if training_load.get("pattern_gaps"):
                lines.append(f"- **Pattern Gaps (10d):** {', '.join(training_load['pattern_gaps'])}")
            
            # Data completeness
            completeness = readiness.get("data_completeness", 0)
            if completeness < 3:
                lines.append(f"- **Data:** {completeness}/4 sources available")
            
            # =================================================================
            # NEO4J CONTEXT (existing)
            # =================================================================
            
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
                    workout_name = w.get('name') or w.get('type') or 'workout'
                    lines.append(f"- {w.get('date')}: {workout_name} ({w.get('sets', 0)} sets) — {patterns}")
            
            # COACHING NOTES (assembled from observations)
            observations = briefing.get("observations", [])
            coaching_notes = assemble_coaching_notes(observations)
            lines.extend(coaching_notes)
            
            # UPCOMING
            upcoming = briefing.get("upcoming_sessions", [])
            if upcoming:
                lines.append("")
                lines.append("## Upcoming Sessions")
                for s in upcoming:
                    lines.append(f"- {s.get('date')}: {s.get('goal', 'Workout')} [{s.get('status')}]")
            
            # EQUIPMENT
            equipment = briefing.get("equipment", [])
            if equipment:
                lines.append("")
                lines.append("## Equipment Available")
                eq_list = [e.get('equipment') for e in equipment if e.get('equipment')]
                lines.append(", ".join(eq_list[:10]))  # First 10
            
            # =================================================================
            # COACHING NOTES (from analytics)
            # =================================================================
            analytics_notes = analytics.get("coaching_notes", [])
            if analytics_notes:
                lines.append("")
                lines.append("## ⚡ Coaching Alerts")
                for note in analytics_notes:
                    lines.append(f"- {note}")
            
            # ANNOTATIONS (context for unusual data)
            annotations = analytics.get("annotations", [])
            if annotations:
                lines.append("")
                lines.append("## Active Annotations")
                for a in annotations[:3]:  # Top 3
                    lines.append(f"- [{a['reason']}] {a.get('explanation', '')[:80]}")
            
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

    # =========================================================================
    # DEBRIEF SESSION
    # =========================================================================
    
    elif name == "debrief_session":
        try:
            observations_input = arguments.get("observations", [])
            session_summary = arguments.get("session_summary")
            
            if not observations_input:
                return [types.TextContent(
                    type="text",
                    text="❌ No observations provided. Review the session and propose observations first."
                )]
            
            logger.info(f"Debriefing session: {len(observations_input)} observations")
            
            stored = []
            links_created = []
            
            for obs in observations_input:
                content = obs.get("content")
                obs_type = obs.get("observation_type", "insight")
                tags = obs.get("tags", [])
                
                if not content:
                    continue
                
                # Store the observation
                result = neo4j_client.store_observation(
                    person_id=person_id,
                    content=content,
                    observation_type=obs_type,
                    tags=tags
                )
                
                obs_id = result["id"]
                stored.append({
                    "id": obs_id,
                    "type": obs_type,
                    "content": content[:60] + "..." if len(content) > 60 else content
                })
                
                # Create relationship links if specified
                with neo4j_client.driver.session(database=neo4j_client.database) as session:
                    
                    # Link to workout by date
                    if obs.get("link_to_workout"):
                        workout_date = obs["link_to_workout"]
                        link_result = session.run("""
                            MATCH (o:Observation {id: $obs_id})
                            MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w:Workout)
                            WHERE toString(w.date) = $workout_date
                            MERGE (o)-[r:ABOUT_WORKOUT]->(w)
                            RETURN w.date as linked_date
                        """, obs_id=obs_id, person_id=person_id, workout_date=workout_date).single()
                        
                        if link_result:
                            links_created.append(f"→ Workout ({workout_date})")
                    
                    # Link to goal by name
                    if obs.get("link_to_goal"):
                        goal_name = obs["link_to_goal"]
                        link_result = session.run("""
                            MATCH (o:Observation {id: $obs_id})
                            MATCH (p:Person {id: $person_id})-[:HAS_GOAL]->(g:Goal)
                            WHERE toLower(g.name) CONTAINS toLower($goal_name)
                            MERGE (o)-[r:INFORMS]->(g)
                            RETURN g.name as linked_goal
                        """, obs_id=obs_id, person_id=person_id, goal_name=goal_name).single()
                        
                        if link_result:
                            links_created.append(f"→ Goal ({link_result['linked_goal']})")
                    
                    # Link to injury by name
                    if obs.get("link_to_injury"):
                        injury_name = obs["link_to_injury"]
                        link_result = session.run("""
                            MATCH (o:Observation {id: $obs_id})
                            MATCH (p:Person {id: $person_id})-[:HAS_INJURY]->(i:Injury)
                            WHERE toLower(i.name) CONTAINS toLower($injury_name)
                            MERGE (o)-[r:RELATED_TO]->(i)
                            RETURN i.name as linked_injury
                        """, obs_id=obs_id, person_id=person_id, injury_name=injury_name).single()
                        
                        if link_result:
                            links_created.append(f"→ Injury ({link_result['linked_injury']})")
            
            # Build response
            lines = [f"✅ **Session Debriefed**\n"]
            lines.append(f"**Stored {len(stored)} observations:**\n")
            
            for s in stored:
                lines.append(f"- [{s['type']}] {s['content']}")
            
            if links_created:
                lines.append(f"\n**Links created:** {len(links_created)}")
                for link in links_created:
                    lines.append(f"  {link}")
            
            if session_summary:
                lines.append(f"\n**Session summary:** {session_summary}")
            
            lines.append(f"\n_These observations will inform future coaching via load_briefing()._")
            
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
        except Exception as e:
            logger.error(f"Error debriefing session: {str(e)}", exc_info=True)
            return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]

    else:
        return [types.TextContent(
            type="text",
            text=f"❌ Unknown tool: {name}"
        )]


def main():
    """Run the MCP server."""
    logger.info("Starting Arnold Memory MCP Server (consolidated briefing)")
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
        postgres_client.close()
        logger.info("Arnold Memory MCP Server stopped")


if __name__ == "__main__":
    main()
