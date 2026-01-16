"""Neo4j client for Arnold training/coach operations."""

import os
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class Neo4jTrainingClient:
    """Neo4j database client for training operations."""

    def __init__(self):
        """Initialize Neo4j driver."""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "arnold")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    # =========================================================================
    # CONTEXT QUERIES
    # =========================================================================

    def get_training_context(self, person_id: str) -> Dict[str, Any]:
        """
        Get all context needed for training decisions.
        
        Returns:
            - active_injuries with constraints
            - equipment available
            - recent workout summary
            - active goals
        
        Optimized: Single query with CALL {} subqueries (was 5 round-trips).
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Collect injuries with constraints
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_INJURY]->(i:Injury)
                    WHERE i.status IN ['active', 'recovering']
                    OPTIONAL MATCH (i)-[:CREATES]->(c:Constraint)
                    WITH i, collect(c.description) as constraints
                    WHERE i IS NOT NULL
                    RETURN collect({
                        injury: i.name,
                        status: i.status,
                        body_part: i.body_part,
                        constraints: constraints
                    }) as injuries
                }
                
                // Collect equipment
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_ACCESS_TO]->(inv:EquipmentInventory)
                    OPTIONAL MATCH (inv)-[contains:CONTAINS]->(eq:EquipmentCategory)
                    WHERE eq IS NOT NULL
                    RETURN collect(DISTINCT {
                        name: eq.name,
                        type: eq.type,
                        weight_lbs: contains.weight_lbs,
                        weight_range_min: contains.weight_range_min,
                        weight_range_max: contains.weight_range_max,
                        adjustable: contains.adjustable
                    }) as equipment
                }
                
                // Collect recent workouts (last 7 days)
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:PERFORMED]->(w:Workout)
                    WHERE w.date >= date() - duration('P7D')
                    WITH w ORDER BY w.date DESC
                    WHERE w IS NOT NULL
                    RETURN collect({
                        date: w.date,
                        type: w.type,
                        duration: w.duration_minutes
                    }) as recent_workouts
                }
                
                // Collect active goals
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_GOAL]->(g:Goal)
                    WHERE g.status = 'active'
                    RETURN collect({
                        id: g.id,
                        description: g.description,
                        type: g.goal_type,
                        target_date: g.target_date
                    }) as goals
                }
                
                RETURN p,
                       injuries,
                       equipment,
                       recent_workouts,
                       goals
            """, person_id=person_id)
            
            record = result.single()
            if not record:
                return None
            
            # Filter out null entries from collections
            injuries = [i for i in record["injuries"] if i.get("injury")]
            equipment = [e for e in record["equipment"] if e.get("name")]
            recent_workouts = [w for w in record["recent_workouts"] if w.get("date")]
            goals = [g for g in record["goals"] if g.get("id")]
            
            return {
                "person": dict(record["p"]),
                "injuries": injuries,
                "equipment": equipment,
                "recent_workouts": recent_workouts,
                "goals": goals,
                "last_workout_date": str(recent_workouts[0]["date"]) if recent_workouts else None,
                "workouts_this_week": len(recent_workouts)
            }

    def get_active_constraints(self, person_id: str) -> List[Dict[str, Any]]:
        """Get all active constraints from injuries. Person direct, no Athlete."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_INJURY]->(i:Injury)
                WHERE i.status IN ['active', 'recovering']
                MATCH (i)-[:CREATES]->(c:Constraint)
                RETURN i.name as injury, 
                       i.status as status,
                       c.id as constraint_id,
                       c.constraint_type as type,
                       c.description as description
            """, person_id=person_id)
            
            return [dict(r) for r in result]

    # =========================================================================
    # EXERCISE SEARCH & SELECTION
    # =========================================================================

    def search_exercises(self, query: str, limit: int = 5) -> list:
        """
        Search exercises using full-text index with fuzzy matching.
        Returns candidates for Claude to select from.
        
        IMPORTANT: Claude should normalize the query first (semantic layer),
        then this tool handles string matching (retrieval layer).
        
        Args:
            query: NORMALIZED search query (e.g., "kettlebell swing" not "KB swing")
            limit: Maximum number of results to return
            
        Returns:
            List of dicts with exercise_id, name, score
        """
        with self.driver.session(database=self.database) as session:
            # Use full-text index with fuzzy matching
            # Note: parameter named 'search_term' to avoid conflict with driver's 'query' arg
            result = session.run("""
                CALL db.index.fulltext.queryNodes('exercise_search', $search_term + '~')
                YIELD node, score
                RETURN node.id as exercise_id, node.name as name, score
                ORDER BY score DESC
                LIMIT $limit
            """, search_term=query, limit=limit)
            
            results = []
            for record in result:
                results.append({
                    'exercise_id': record['exercise_id'],
                    'name': record['name'],
                    'score': record['score']
                })
            
            return results

    def resolve_exercises(self, names: List[str], confidence_threshold: float = 0.3) -> Dict[str, Any]:
        """
        Batch resolve exercise names to IDs.
        
        IMPORTANT: Claude should normalize ALL names first (semantic layer),
        then call this once for the entire plan.
        
        Args:
            names: List of NORMALIZED exercise names
            confidence_threshold: Minimum score to auto-accept (0-1 normalized)
            
        Returns:
            Dict with:
            - resolved: {name: {id, name, score, confidence}} for matches above threshold
            - needs_clarification: {name: [candidates]} for matches below threshold
            - not_found: [names] with no matches at all
        """
        with self.driver.session(database=self.database) as session:
            resolved = {}
            needs_clarification = {}
            not_found = []
            
            for name in names:
                # Search for each name
                result = session.run("""
                    CALL db.index.fulltext.queryNodes('exercise_search', $search_term + '~')
                    YIELD node, score
                    RETURN node.id as exercise_id, node.name as name, score
                    ORDER BY score DESC
                    LIMIT 5
                """, search_term=name)
                
                candidates = [dict(r) for r in result]
                
                if not candidates:
                    not_found.append(name)
                elif candidates[0]['score'] >= confidence_threshold * 10:  # Lucene scores ~0-10
                    # High confidence match
                    best = candidates[0]
                    resolved[name] = {
                        'id': best['exercise_id'],
                        'name': best['name'],
                        'score': best['score'],
                        'confidence': 'high' if best['score'] > 7 else 'medium'
                    }
                else:
                    # Low confidence - needs human input
                    needs_clarification[name] = [
                        {'id': c['exercise_id'], 'name': c['name'], 'score': c['score']}
                        for c in candidates[:3]
                    ]
            
            return {
                'resolved': resolved,
                'needs_clarification': needs_clarification,
                'not_found': not_found,
                'summary': {
                    'total': len(names),
                    'resolved': len(resolved),
                    'needs_clarification': len(needs_clarification),
                    'not_found': len(not_found)
                }
            }

    def suggest_exercises(
        self,
        movement_patterns: List[str] = None,
        muscle_targets: List[str] = None,
        equipment_filter: List[str] = None,
        exclude_exercises: List[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find exercises matching criteria.
        """
        with self.driver.session(database=self.database) as session:
            params = {"limit": limit}
            
            # Build query based on filters
            if movement_patterns:
                # Required match on pattern when filtering by pattern
                params["patterns"] = movement_patterns
                
                if muscle_targets:
                    params["muscles"] = muscle_targets
                    query = """
                        MATCH (e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
                        WHERE mp.name IN $patterns
                        OPTIONAL MATCH (e)-[:TARGETS]->(m:Muscle)
                        OPTIONAL MATCH (e)-[:TARGETS]->(mg:MuscleGroup)
                        WITH e, mp, collect(DISTINCT m.name) + collect(DISTINCT mg.name) as all_muscles
                        WHERE any(muscle IN all_muscles WHERE muscle IN $muscles)
                        OPTIONAL MATCH (e)-[:INVOLVES]->(all_mp:MovementPattern)
                        WITH e, collect(DISTINCT all_mp.name) as patterns, all_muscles as muscles
                        RETURN e.id as id, e.name as name, e.source as source, patterns, muscles
                        LIMIT $limit
                    """
                else:
                    query = """
                        MATCH (e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
                        WHERE mp.name IN $patterns
                        OPTIONAL MATCH (e)-[:TARGETS]->(m:Muscle)
                        OPTIONAL MATCH (e)-[:TARGETS]->(mg:MuscleGroup)
                        WITH e, collect(DISTINCT mp.name) as patterns,
                             collect(DISTINCT m.name) + collect(DISTINCT mg.name) as muscles
                        RETURN e.id as id, e.name as name, e.source as source, patterns, muscles
                        LIMIT $limit
                    """
            elif muscle_targets:
                params["muscles"] = muscle_targets
                query = """
                    MATCH (e:Exercise)-[:TARGETS]->(target)
                    WHERE (target:Muscle OR target:MuscleGroup) AND target.name IN $muscles
                    OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
                    WITH e, collect(DISTINCT mp.name) as patterns, collect(DISTINCT target.name) as muscles
                    RETURN e.id as id, e.name as name, e.source as source, patterns, muscles
                    LIMIT $limit
                """
            else:
                # No filters - just return exercises
                query = """
                    MATCH (e:Exercise)
                    OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
                    OPTIONAL MATCH (e)-[:TARGETS]->(m:Muscle)
                    WITH e, collect(DISTINCT mp.name) as patterns, collect(DISTINCT m.name) as muscles
                    RETURN e.id as id, e.name as name, e.source as source, patterns, muscles
                    LIMIT $limit
                """
            
            # Add exclusion filter if needed
            if exclude_exercises:
                params["excluded"] = exclude_exercises
                query = query.replace("MATCH (e:Exercise)", "MATCH (e:Exercise) WHERE NOT e.id IN $excluded")
            
            result = session.run(query, **params)
            return [dict(r) for r in result]

    def check_exercise_safety(self, exercise_id: str, person_id: str) -> Dict[str, Any]:
        """
        Check if exercise is safe given current constraints.
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (e:Exercise {id: $exercise_id})
                OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
                OPTIONAL MATCH (e)-[:TARGETS]->(m:Muscle)
                
                // Get person's constraints (Person direct, no Athlete)
                MATCH (p:Person {id: $person_id})-[:HAS_INJURY]->(i:Injury)
                WHERE i.status IN ['active', 'recovering']
                MATCH (i)-[:CREATES]->(c:Constraint)
                
                RETURN e.name as exercise,
                       collect(DISTINCT mp.name) as patterns,
                       collect(DISTINCT m.name) as muscles,
                       collect(DISTINCT {
                           injury: i.name,
                           constraint: c.description,
                           type: c.constraint_type
                       }) as constraints
            """, exercise_id=exercise_id, person_id=person_id)
            
            record = result.single()
            if not record:
                return {"safe": True, "concerns": [], "exercise": None}
            
            # Simple keyword matching for constraint violations
            # TODO: Make this smarter with graph relationships
            concerns = []
            exercise_name = record["exercise"].lower()
            patterns = [p.lower() for p in record["patterns"]]
            
            for c in record["constraints"]:
                constraint_desc = c["constraint"].lower()
                
                # Check for obvious conflicts
                if "avoid" in constraint_desc:
                    # Extract what to avoid
                    if "deep flexion" in constraint_desc and "squat" in exercise_name:
                        concerns.append(c)
                    elif "rotation" in constraint_desc and any("rotation" in p for p in patterns):
                        concerns.append(c)
                    elif "impact" in constraint_desc and "jump" in exercise_name:
                        concerns.append(c)
                    elif "overhead" in constraint_desc and ("press" in exercise_name or "overhead" in exercise_name):
                        concerns.append(c)
            
            return {
                "exercise": record["exercise"],
                "safe": len(concerns) == 0,
                "concerns": concerns,
                "patterns": record["patterns"],
                "muscles": record["muscles"]
            }

    def find_substitutes(
        self, 
        exercise_id: str, 
        preserve: List[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find alternative exercises that preserve specified characteristics.
        
        Optimized: Single query (was 2 round-trips, but second query
        already re-fetched original characteristics anyway).
        """
        preserve = preserve or ["movement_pattern", "primary_muscles"]
        
        with self.driver.session(database=self.database) as session:
            # Single query: get original characteristics and find similar exercises
            result = session.run("""
                MATCH (e:Exercise {id: $exercise_id})
                OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
                OPTIONAL MATCH (e)-[:TARGETS {role: 'primary'}]->(m:Muscle)
                
                WITH e, collect(DISTINCT mp) as orig_patterns, collect(DISTINCT m) as orig_muscles,
                     e.name as original_name
                
                // Find alternatives
                MATCH (alt:Exercise)
                WHERE alt.id <> e.id
                OPTIONAL MATCH (alt)-[:INVOLVES]->(alt_mp:MovementPattern)
                OPTIONAL MATCH (alt)-[:TARGETS {role: 'primary'}]->(alt_m:Muscle)
                
                WITH alt, orig_patterns, orig_muscles, original_name,
                     collect(DISTINCT alt_mp) as alt_patterns,
                     collect(DISTINCT alt_m) as alt_muscles
                
                // Score similarity
                WITH alt, original_name,
                     size([p IN orig_patterns WHERE p IN alt_patterns]) as pattern_match,
                     size([m IN orig_muscles WHERE m IN alt_muscles]) as muscle_match,
                     size(orig_patterns) as total_patterns,
                     size(orig_muscles) as total_muscles
                
                WHERE pattern_match > 0 OR muscle_match > 0
                
                RETURN alt.id as id,
                       alt.name as name,
                       alt.source as source,
                       pattern_match,
                       muscle_match,
                       toFloat(pattern_match + muscle_match) / (total_patterns + total_muscles) as similarity_score
                
                ORDER BY similarity_score DESC
                LIMIT $limit
            """, exercise_id=exercise_id, limit=limit)
            
            return [dict(r) for r in result]

    # =========================================================================
    # PLANNING
    # =========================================================================

    def create_planned_workout(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a PlannedWorkout with blocks and sets.
        
        Validates:
        - Date is not in the distant past (warns if >7 days ago)
        - Date year makes sense (warns if previous year)
        """
        # Date validation
        plan_date_str = plan_data["date"]
        plan_date = date.fromisoformat(plan_date_str) if isinstance(plan_date_str, str) else plan_date_str
        today = date.today()
        
        # Check for obviously wrong year (last year or earlier)
        if plan_date.year < today.year:
            raise ValueError(
                f"Plan date {plan_date} appears to be in the wrong year. "
                f"Current year is {today.year}. Did you mean {plan_date.replace(year=today.year)}?"
            )
        
        # Warn if date is more than 7 days in the past
        days_ago = (today - plan_date).days
        if days_ago > 7:
            raise ValueError(
                f"Plan date {plan_date} is {days_ago} days in the past. "
                f"Use log_adhoc_workout for past workouts, or confirm this date is correct."
            )
        
        # Prepare blocks data for UNWIND (flatten structure)
        blocks_data = []
        for block in plan_data.get("blocks", []):
            blocks_data.append({
                "id": block["id"],
                "name": block["name"],
                "block_type": block["block_type"],
                "order": block["order"],
                "protocol_notes": block.get("protocol_notes"),
                "notes": block.get("notes"),
                "sets": block.get("sets", [])
            })
        
        with self.driver.session(database=self.database) as session:
            # Single atomic operation: create workout, blocks, and sets
            # If any part fails (e.g., exercise not found), nothing is committed
            result = session.run("""
                // First, verify all exercises exist before creating anything
                WITH $blocks as blocks
                UNWIND blocks as block
                UNWIND block.sets as s
                WITH collect(DISTINCT s.exercise_id) as exercise_ids
                
                // Check all exercises exist
                CALL {
                    WITH exercise_ids
                    UNWIND exercise_ids as eid
                    OPTIONAL MATCH (e:Exercise {id: eid})
                    WITH eid, e
                    WHERE e IS NULL AND eid IS NOT NULL
                    RETURN collect(eid) as missing
                }
                
                // Fail if any exercises are missing
                WITH missing
                WHERE size(missing) > 0
                CALL apoc.util.validate(true, 'Exercises not found: ' + apoc.text.join(missing, ', '), [0])
                
                RETURN null
            """, blocks=blocks_data)
            
            # If we get here without APOC, do the check manually
            # (APOC may not be installed)
            
            # Verify exercises exist first
            exercise_ids = set()
            for block in blocks_data:
                for s in block.get("sets", []):
                    if s.get("exercise_id"):
                        exercise_ids.add(s["exercise_id"])
            
            if exercise_ids:
                check_result = session.run("""
                    UNWIND $ids as eid
                    OPTIONAL MATCH (e:Exercise {id: eid})
                    WITH eid, e
                    WHERE e IS NULL
                    RETURN collect(eid) as missing
                """, ids=list(exercise_ids))
                
                missing = check_result.single()["missing"]
                if missing:
                    raise ValueError(f"Exercises not found: {', '.join(missing)}")
            
            # Now create everything in one statement
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Create the workout
                CREATE (pw:PlannedWorkout {
                    plan_id: $plan_id,
                    date: date($date),
                    status: 'draft',
                    goal: $goal,
                    focus: $focus,
                    estimated_duration_minutes: $duration,
                    notes: $notes,
                    created_at: datetime()
                })
                CREATE (p)-[:HAS_PLANNED_WORKOUT]->(pw)
                
                // Create blocks
                WITH pw
                UNWIND $blocks as block
                CREATE (pb:PlannedBlock {
                    id: block.id,
                    name: block.name,
                    block_type: block.block_type,
                    order: block.order,
                    protocol_notes: block.protocol_notes,
                    notes: block.notes
                })
                CREATE (pw)-[:HAS_PLANNED_BLOCK {order: block.order}]->(pb)
                
                // Create sets for this block
                WITH pw, pb, block
                UNWIND block.sets as s
                MATCH (e:Exercise {id: s.exercise_id})
                CREATE (ps:PlannedSet {
                    id: s.id,
                    order: s.order,
                    round: s.round,
                    prescribed_reps: s.prescribed_reps,
                    prescribed_load_lbs: s.prescribed_load_lbs,
                    prescribed_rpe: s.prescribed_rpe,
                    prescribed_duration_seconds: s.prescribed_duration_seconds,
                    prescribed_distance_miles: s.prescribed_distance_miles,
                    intensity_zone: s.intensity_zone,
                    notes: s.notes
                })
                CREATE (pb)-[:CONTAINS_PLANNED {order: s.order, round: s.round}]->(ps)
                CREATE (ps)-[:PRESCRIBES]->(e)
                
                RETURN DISTINCT pw.plan_id as plan_id
            """,
                person_id=plan_data["person_id"],
                plan_id=plan_data["id"],
                date=plan_data["date"],
                goal=plan_data.get("goal"),
                focus=plan_data.get("focus", []),
                duration=plan_data.get("estimated_duration_minutes"),
                notes=plan_data.get("notes"),
                blocks=blocks_data
            )
            
            record = result.single()
            if not record:
                raise ValueError("Failed to create workout plan - no blocks/sets provided?")
            
            return {"id": record["plan_id"], "status": "draft"}

    def get_planned_workout(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get a planned workout with all blocks and sets."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pw:PlannedWorkout)
                WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                OPTIONAL MATCH (pw)-[hpb:HAS_PLANNED_BLOCK]->(pb:PlannedBlock)
                OPTIONAL MATCH (pb)-[cp:CONTAINS_PLANNED]->(ps:PlannedSet)
                OPTIONAL MATCH (ps)-[:PRESCRIBES]->(e:Exercise)
                
                WITH pw, pb, ps, e, hpb, cp
                ORDER BY hpb.order, cp.order, cp.round
                
                WITH pw, pb, hpb,
                     collect({
                         id: ps.id,
                         order: ps.order,
                         round: ps.round,
                         prescribed_reps: ps.prescribed_reps,
                         prescribed_load_lbs: ps.prescribed_load_lbs,
                         prescribed_rpe: ps.prescribed_rpe,
                         intensity_zone: ps.intensity_zone,
                         exercise_id: e.id,
                         exercise_name: e.name,
                         notes: ps.notes
                     }) as sets
                
                WITH pw, collect({
                    id: pb.id,
                    name: pb.name,
                    block_type: pb.block_type,
                    order: hpb.order,
                    protocol_notes: pb.protocol_notes,
                    sets: sets
                }) as blocks
                
                RETURN pw, blocks
            """, plan_id=plan_id)
            
            record = result.single()
            if not record:
                return None
            
            pw = dict(record["pw"])
            blocks = [b for b in record["blocks"] if b["id"] is not None]
            
            return {
                "id": pw.get("plan_id") or pw.get("id"),  # Support both for migration
                "date": str(pw["date"]),
                "status": pw["status"],
                "goal": pw.get("goal"),
                "focus": pw.get("focus"),
                "estimated_duration_minutes": pw.get("estimated_duration_minutes"),
                "notes": pw.get("notes"),
                "blocks": blocks
            }

    def get_plan_for_date(self, person_id: str, plan_date: str) -> Optional[Dict[str, Any]]:
        """Get planned workout for a specific date.
        
        When multiple plans exist for the same date (e.g., after modifications),
        returns the most recently created one.
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                WHERE pw.date = date($date)
                RETURN COALESCE(pw.plan_id, pw.id) as plan_id
                ORDER BY pw.created_at DESC
                LIMIT 1
            """, person_id=person_id, date=plan_date)
            
            record = result.single()
            if not record:
                return None
            
            return self.get_planned_workout(record["plan_id"])

    def update_plan_status(self, plan_id: str, status: str) -> Dict[str, Any]:
        """Update plan status (draft, confirmed, completed, skipped)."""
        with self.driver.session(database=self.database) as session:
            timestamp_field = {
                "confirmed": "confirmed_at",
                "completed": "completed_at",
                "skipped": "skipped_at"
            }.get(status)
            
            if timestamp_field:
                result = session.run(f"""
                    MATCH (pw:PlannedWorkout)
                    WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                    SET pw.status = $status,
                        pw.{timestamp_field} = datetime()
                    RETURN COALESCE(pw.plan_id, pw.id) as id, pw.status as status
                """, plan_id=plan_id, status=status)
            else:
                result = session.run("""
                    MATCH (pw:PlannedWorkout)
                    WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                    SET pw.status = $status
                    RETURN COALESCE(pw.plan_id, pw.id) as id, pw.status as status
                """, plan_id=plan_id, status=status)
            
            return dict(result.single())

    # =========================================================================
    # EXECUTION / RECONCILIATION
    # =========================================================================

    def complete_workout_as_written(self, plan_id: str) -> Dict[str, Any]:
        """
        Convert a planned workout to an executed workout (no deviations).
        """
        with self.driver.session(database=self.database) as session:
            # Get the plan
            plan = self.get_planned_workout(plan_id)
            if not plan:
                return {"error": "Plan not found"}
            
            # Create Workout node from plan - Person direct, no Athlete
            result = session.run("""
                MATCH (pw:PlannedWorkout)
                WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                WITH pw
                LIMIT 1
                MATCH (pw)  // Re-anchor after WITH
                MATCH (p:Person)-[:HAS_PLANNED_WORKOUT]->(pw)
                
                CREATE (w:Workout {
                    id: randomUUID(),
                    name: pw.goal,
                    date: pw.date,
                    type: 'strength',
                    duration_minutes: pw.estimated_duration_minutes,
                    notes: pw.notes,
                    source: 'planned',
                    imported_at: datetime()
                })
                
                CREATE (w)-[:EXECUTED_FROM {
                    completed_at: datetime(),
                    compliance: 'as_written'
                }]->(pw)
                
                CREATE (p)-[:PERFORMED]->(w)
                
                // Copy blocks
                WITH w, pw
                MATCH (pw)-[hpb:HAS_PLANNED_BLOCK]->(pb:PlannedBlock)
                CREATE (wb:WorkoutBlock {
                    id: randomUUID(),
                    name: pb.name,
                    phase: pb.block_type,
                    order: hpb.order
                })
                CREATE (w)-[:HAS_BLOCK {order: hpb.order}]->(wb)
                
                // Copy sets
                WITH w, wb, pb
                MATCH (pb)-[cp:CONTAINS_PLANNED]->(ps:PlannedSet)
                MATCH (ps)-[:PRESCRIBES]->(e:Exercise)
                CREATE (s:Set {
                    id: randomUUID(),
                    order: ps.order,
                    round: ps.round,
                    set_number: ps.order,
                    reps: ps.prescribed_reps,
                    load_lbs: ps.prescribed_load_lbs,
                    duration_seconds: ps.prescribed_duration_seconds,
                    distance_miles: ps.prescribed_distance_miles,
                    notes: ps.notes
                })
                CREATE (wb)-[:CONTAINS {order: ps.order}]->(s)
                CREATE (s)-[:OF_EXERCISE]->(e)
                
                RETURN w.id as workout_id
            """, plan_id=plan_id)
            
            workout_record = result.single()
            
            # Update plan status
            self.update_plan_status(plan_id, "completed")
            
            return {
                "workout_id": workout_record["workout_id"],
                "plan_id": plan_id,
                "compliance": "as_written"
            }

    def complete_workout_with_deviations(
        self, 
        plan_id: str, 
        deviations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Convert planned workout to executed with recorded deviations.
        
        Atomically creates workout and applies all deviations.
        
        deviations format:
        [{
            "planned_set_id": "PLANSET:xxx",
            "actual_reps": 4,
            "actual_load_lbs": 175,
            "substitute_exercise_id": "CUSTOM:Sandbag_Box_Squat",  # optional
            "reason": "fatigue",
            "notes": "Form breaking down"
        }]
        """
        with self.driver.session(database=self.database) as session:
            # First complete as written
            base_result = self.complete_workout_as_written(plan_id)
            
            if "error" in base_result:
                return base_result
            
            if deviations:
                # Separate deviations into exercise substitutions vs rep/load changes
                substitutions = [d for d in deviations if d.get("substitute_exercise_id")]
                rep_load_changes = [d for d in deviations if not d.get("substitute_exercise_id")]
                
                # Handle exercise substitutions first
                # Delete old OF_EXERCISE relationship, create new one
                if substitutions:
                    session.run("""
                        UNWIND $substitutions as sub
                        MATCH (ps:PlannedSet {id: sub.planned_set_id})
                        MATCH (ps)-[:PRESCRIBES]->(old_ex:Exercise)
                        MATCH (s:Set)-[old_rel:OF_EXERCISE]->(old_ex)
                        WHERE EXISTS { (s)<-[:CONTAINS]-(:WorkoutBlock)<-[:HAS_BLOCK]-(:Workout)-[:EXECUTED_FROM]->(:PlannedWorkout)-[:HAS_PLANNED_BLOCK]->(:PlannedBlock)-[:CONTAINS_PLANNED]->(ps) }
                        
                        // Find the substitute exercise
                        MATCH (new_ex:Exercise {id: sub.substitute_exercise_id})
                        
                        // Delete old relationship, create new one
                        DELETE old_rel
                        CREATE (s)-[:OF_EXERCISE]->(new_ex)
                        
                        // Update set properties
                        SET s.reps = COALESCE(sub.actual_reps, s.reps),
                            s.load_lbs = COALESCE(sub.actual_load_lbs, s.load_lbs),
                            s.notes = COALESCE(sub.notes, s.notes)
                        
                        // Create deviation relationship with substitution info
                        CREATE (s)-[:DEVIATED_FROM {
                            reason: sub.reason,
                            substituted_from: old_ex.id,
                            substituted_to: new_ex.id,
                            rep_deviation: CASE WHEN sub.actual_reps IS NOT NULL THEN sub.actual_reps - ps.prescribed_reps ELSE null END,
                            load_deviation_lbs: CASE WHEN sub.actual_load_lbs IS NOT NULL THEN sub.actual_load_lbs - ps.prescribed_load_lbs ELSE null END,
                            notes: sub.notes
                        }]->(ps)
                    """, substitutions=substitutions)
                
                # Handle rep/load changes (no exercise substitution)
                if rep_load_changes:
                    session.run("""
                        UNWIND $deviations as dev
                        MATCH (ps:PlannedSet {id: dev.planned_set_id})
                        MATCH (s:Set)-[:OF_EXERCISE]->(:Exercise)<-[:PRESCRIBES]-(ps)
                        
                        // Update actual values
                        SET s.reps = COALESCE(dev.actual_reps, s.reps),
                            s.load_lbs = COALESCE(dev.actual_load_lbs, s.load_lbs),
                            s.notes = COALESCE(dev.notes, s.notes)
                        
                        // Create deviation relationship
                        CREATE (s)-[:DEVIATED_FROM {
                            reason: dev.reason,
                            rep_deviation: CASE WHEN dev.actual_reps IS NOT NULL THEN dev.actual_reps - ps.prescribed_reps ELSE null END,
                            load_deviation_lbs: CASE WHEN dev.actual_load_lbs IS NOT NULL THEN dev.actual_load_lbs - ps.prescribed_load_lbs ELSE null END,
                            notes: dev.notes
                        }]->(ps)
                    """, deviations=rep_load_changes)
                
                # Update execution compliance
                session.run("""
                    MATCH (w:Workout)-[ef:EXECUTED_FROM]->(pw:PlannedWorkout)
                    WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                    SET ef.compliance = 'with_deviations'
                """, plan_id=plan_id)
            
            return {
                "workout_id": base_result["workout_id"],
                "plan_id": plan_id,
                "compliance": "with_deviations" if deviations else "as_written",
                "deviations_recorded": len(deviations)
            }

    def skip_workout(self, plan_id: str, reason: str) -> Dict[str, Any]:
        """Mark a planned workout as skipped."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pw:PlannedWorkout)
                WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                SET pw.status = 'skipped',
                    pw.skipped_at = datetime(),
                    pw.skip_reason = $reason
                RETURN COALESCE(pw.plan_id, pw.id) as id, pw.status as status
            """, plan_id=plan_id, reason=reason)
            
            return dict(result.single())

    # =========================================================================
    # AD-HOC WORKOUT LOGGING (migrated from arnold-profile)
    # =========================================================================

    def log_adhoc_workout(self, workout_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log an unplanned/ad-hoc workout atomically.
        
        Either the entire workout is created, or nothing is (no orphans).
        Exercises that don't exist are created as CUSTOM: exercises.
        """
        # Prepare exercises data for UNWIND
        exercises_data = []
        for exercise in workout_data.get("exercises", []):
            exercises_data.append({
                "exercise_id": exercise.get("exercise_id"),
                "exercise_name": exercise.get("exercise_name"),
                "sets": exercise.get("sets", [])
            })
        
        with self.driver.session(database=self.database) as session:
            # Step 1: Resolve all exercise IDs (find existing or create custom)
            # This is separate so we can report which exercises were created
            exercises_resolved = []
            exercises_needing_mapping = []
            
            for ex in exercises_data:
                exercise_id = ex.get("exercise_id")
                exercise_name = ex.get("exercise_name")
                
                if not exercise_id and exercise_name:
                    # Try to find by name
                    find_result = session.run("""
                        MATCH (e:Exercise)
                        WHERE toLower(e.name) = toLower($name)
                        RETURN e.id as id
                        LIMIT 1
                    """, name=exercise_name)
                    
                    record = find_result.single()
                    if record:
                        exercise_id = record["id"]
                    else:
                        # Create custom exercise
                        custom_id = 'CUSTOM:' + exercise_name.replace(' ', '_')
                        session.run("""
                            MERGE (e:Exercise {id: $id})
                            ON CREATE SET 
                                e.name = $name,
                                e.source = 'user_workout_log',
                                e.created_at = datetime()
                        """, id=custom_id, name=exercise_name)
                        exercise_id = custom_id
                        exercises_needing_mapping.append({
                            "id": exercise_id,
                            "name": exercise_name
                        })
                
                exercises_resolved.append({
                    "exercise_id": exercise_id,
                    "exercise_name": exercise_name,
                    "sets": ex.get("sets", [])
                })
            
            # Step 2: Create workout, block, and all sets in one atomic statement
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Create workout
                CREATE (w:Workout {
                    id: $workout_id,
                    name: $name,
                    date: date($date),
                    type: $type,
                    duration_minutes: $duration_minutes,
                    notes: $notes,
                    source: 'adhoc',
                    imported_at: datetime()
                })
                CREATE (p)-[:PERFORMED]->(w)
                
                // Create single block for ad-hoc workouts
                CREATE (b:WorkoutBlock {
                    id: randomUUID(),
                    name: 'Main',
                    phase: 'main',
                    order: 1
                })
                CREATE (w)-[:HAS_BLOCK {order: 1}]->(b)
                
                // Create all sets
                WITH w, b
                UNWIND $exercises as ex
                UNWIND ex.sets as s
                MATCH (e:Exercise {id: ex.exercise_id})
                CREATE (set:Set {
                    id: randomUUID(),
                    order: s.set_number,
                    set_number: s.set_number,
                    reps: s.reps,
                    load_lbs: s.load_lbs,
                    duration_seconds: s.duration_seconds,
                    distance_miles: s.distance_miles,
                    rpe: s.rpe,
                    notes: s.notes
                })
                CREATE (b)-[:CONTAINS {order: s.set_number}]->(set)
                CREATE (set)-[:OF_EXERCISE]->(e)
                
                RETURN DISTINCT w.id as workout_id
            """,
                person_id=workout_data["person_id"],
                workout_id=workout_data["workout_id"],
                name=workout_data.get("name"),
                date=workout_data["date"],
                type=workout_data.get("type", "strength"),
                duration_minutes=workout_data.get("duration_minutes"),
                notes=workout_data.get("notes"),
                exercises=exercises_resolved
            )
            
            record = result.single()
            if not record:
                raise ValueError("Failed to create workout - no exercises/sets provided?")
            
            return {
                "workout_id": record["workout_id"],
                "date": workout_data["date"],
                "exercises_logged": len(exercises_resolved),
                "exercises_needing_mapping": exercises_needing_mapping
            }

    # =========================================================================
    # HISTORY QUERIES
    # =========================================================================

    def get_workout_by_date(self, person_id: str, workout_date: str) -> Optional[Dict[str, Any]]:
        """Get workout by date. Person direct, no Athlete."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w:Workout {date: date($date)})
                
                OPTIONAL MATCH (w)-[:HAS_BLOCK]->(b:WorkoutBlock)
                OPTIONAL MATCH (b)-[:CONTAINS]->(s:Set)
                OPTIONAL MATCH (s)-[:OF_EXERCISE]->(ex:Exercise)
                
                WITH w, b, s, ex
                ORDER BY b.order, s.order
                
                RETURN w,
                    collect({
                        block_name: b.name,
                        set_number: s.set_number,
                        reps: s.reps,
                        load_lbs: s.load_lbs,
                        exercise_id: ex.id,
                        exercise_name: ex.name
                    }) as sets
            """, person_id=person_id, date=workout_date)

            record = result.single()
            if not record:
                return None

            return {
                "workout": dict(record["w"]),
                "sets": [s for s in record["sets"] if s["set_number"] is not None]
            }

    def get_recent_workouts(self, person_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get workouts from the last N days. Person direct, no Athlete."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w:Workout)
                WHERE w.date >= date() - duration('P' + $days + 'D')
                
                OPTIONAL MATCH (w)-[:HAS_BLOCK]->(b:WorkoutBlock)-[:CONTAINS]->(s:Set)
                OPTIONAL MATCH (s)-[:OF_EXERCISE]->(e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
                
                WITH w, count(DISTINCT s) as set_count, 
                     collect(DISTINCT mp.name) as patterns
                
                RETURN w.id as id,
                       w.date as date,
                       w.type as type,
                       w.duration_minutes as duration,
                       set_count,
                       patterns
                ORDER BY w.date DESC
            """, person_id=person_id, days=str(days))

            return [dict(r) for r in result]

    def get_coach_briefing(self, person_id: str) -> Dict[str, Any]:
        """
        Get everything the coach needs to know at conversation start.
        
        New architecture (Dec 2025):
        - Person -[:HAS_BLOCK]-> Block (no TrainingPlan intermediary)
        - Person -[:HAS_GOAL]-> Goal
        - Person -[:HAS_LEVEL]-> TrainingLevel -[:FOR_MODALITY]-> Modality
        - Person -[:PERFORMED]-> Workout (no Athlete intermediary)
        - Block -[:SERVES]-> Goal
        
        Optimized: Single query with CALL {} subqueries (was 6 round-trips).
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Get active block
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_BLOCK]->(b:Block {status: 'active'})
                    OPTIONAL MATCH (b)-[:SERVES]->(g:Goal)
                    WITH b, collect(g.name) as served_goals
                    RETURN {
                        name: b.name,
                        block_type: b.block_type,
                        week_count: b.week_count,
                        intent: b.intent,
                        volume_target: b.volume_target,
                        intensity_target: b.intensity_target,
                        start_date: toString(b.start_date),
                        end_date: toString(b.end_date),
                        served_goals: served_goals
                    } as block_info
                }
                
                // Get active goals with modalities
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_GOAL]->(g:Goal {status: 'active'})
                    OPTIONAL MATCH (g)-[:REQUIRES]->(m:Modality)
                    OPTIONAL MATCH (p)-[:HAS_LEVEL]->(tl:TrainingLevel)-[:FOR_MODALITY]->(m)
                    OPTIONAL MATCH (tl)-[:USES_MODEL]->(pm:PeriodizationModel)
                    WITH g, collect(DISTINCT {
                        modality: m.name,
                        level: tl.current_level,
                        model: pm.name
                    }) as modality_info
                    WHERE g IS NOT NULL
                    WITH g, modality_info
                    ORDER BY CASE g.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'meta' THEN 3 ELSE 4 END
                    RETURN collect({
                        name: g.name,
                        priority: g.priority,
                        target_date: toString(g.target_date),
                        modality_info: modality_info
                    }) as goals
                }
                
                // Get recent workouts (last 7 days)
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:PERFORMED]->(w:Workout)
                    WHERE w.date >= date() - duration('P7D')
                    OPTIONAL MATCH (w)-[:HAS_BLOCK]->(b:WorkoutBlock)-[:CONTAINS]->(s:Set)
                    OPTIONAL MATCH (s)-[:OF_EXERCISE]->(e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
                    WITH w, count(DISTINCT s) as sets, collect(DISTINCT mp.name) as patterns
                    WHERE w IS NOT NULL
                    WITH w, sets, patterns ORDER BY w.date DESC LIMIT 5
                    RETURN collect({
                        date: toString(w.date),
                        type: w.type,
                        sets: sets,
                        patterns: patterns
                    }) as recent_workouts
                }
                
                // Get next planned workout
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                    WHERE pw.status IN ['draft', 'confirmed'] AND pw.date >= date()
                    WITH pw ORDER BY pw.date ASC LIMIT 1
                    RETURN {
                        name: pw.goal,
                        date: toString(pw.date),
                        status: pw.status,
                        goal: pw.goal
                    } as next_plan
                }
                
                // Get active injuries
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_INJURY]->(i:Injury)
                    WHERE i.status IN ['active', 'recovering']
                    RETURN collect({
                        injury: i.name,
                        status: i.status,
                        body_part: i.body_part
                    }) as injuries
                }
                
                RETURN p.name as athlete_name,
                       block_info,
                       goals,
                       recent_workouts,
                       next_plan,
                       injuries
            """, person_id=person_id)
            
            record = result.single()
            if not record:
                return None
            
            # Filter nulls from collections
            goals = [g for g in record["goals"] if g.get("name")]
            recent_workouts = [w for w in record["recent_workouts"] if w.get("date")]
            injuries = [i for i in record["injuries"] if i.get("injury")]
            
            block_info = record["block_info"]
            next_plan = record["next_plan"]
            
            # Calculate current week in block
            current_week = None
            if block_info and block_info.get("start_date"):
                from datetime import date
                block_start = date.fromisoformat(block_info["start_date"])
                days_in = (date.today() - block_start).days
                current_week = (days_in // 7) + 1
            
            # Build briefing
            briefing = {
                "athlete": record["athlete_name"],
                "goals": goals,
                "current_block": None,
                "recent_workouts": recent_workouts,
                "next_planned": None,
                "injuries": injuries,
                "workouts_this_week": len(recent_workouts)
            }
            
            if block_info and block_info.get("name"):
                briefing["current_block"] = {
                    "name": block_info["name"],
                    "type": block_info["block_type"],
                    "week": current_week,
                    "of_weeks": block_info["week_count"],
                    "intent": block_info["intent"],
                    "volume": block_info["volume_target"],
                    "intensity": block_info["intensity_target"],
                    "start": block_info["start_date"],
                    "end": block_info["end_date"],
                    "serves_goals": block_info["served_goals"]
                }
            
            if next_plan and next_plan.get("date"):
                briefing["next_planned"] = {
                    "name": next_plan["name"],
                    "date": next_plan["date"],
                    "status": next_plan["status"],
                    "goal": next_plan["goal"]
                }
            
            return briefing

    # =========================================================================
    # PLANNING VISIBILITY
    # =========================================================================

    def get_upcoming_plans(self, person_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get all planned workouts for the next N days.
        
        Returns plans with their status (draft, confirmed, completed, skipped).
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                WHERE pw.date >= date() AND pw.date <= date() + duration('P' + $days + 'D')
                
                OPTIONAL MATCH (pw)-[:HAS_PLANNED_BLOCK]->(pb:PlannedBlock)
                OPTIONAL MATCH (pb)-[:CONTAINS_PLANNED]->(ps:PlannedSet)
                
                WITH pw, count(DISTINCT pb) as block_count, count(DISTINCT ps) as set_count
                
                RETURN COALESCE(pw.plan_id, pw.id) as plan_id,
                       toString(pw.date) as date,
                       pw.status as status,
                       pw.goal as goal,
                       pw.focus as focus,
                       pw.estimated_duration_minutes as duration_minutes,
                       block_count,
                       set_count
                ORDER BY pw.date ASC
            """, person_id=person_id, days=str(days))
            
            return [dict(r) for r in result]

    def get_planning_status(self, person_id: str, days: int = 7) -> Dict[str, Any]:
        """
        Get planning status for next N days.
        
        Shows:
        - Days with plans (and their status)
        - Days without plans (gaps)
        - Current block context for gap-filling recommendations
        
        Optimized: Single query with CALL {} subqueries (was 3 round-trips).
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Get all plans in date range
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                    WHERE pw.date >= date() AND pw.date <= date() + duration('P' + $days + 'D')
                    WITH pw WHERE pw IS NOT NULL
                    RETURN collect({
                        date: toString(pw.date),
                        plan_id: COALESCE(pw.plan_id, pw.id),
                        status: pw.status,
                        goal: pw.goal
                    }) as plans
                }
                
                // Get current block for context
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:HAS_BLOCK]->(b:Block {status: 'active'})
                    RETURN {
                        name: b.name,
                        type: b.block_type,
                        sessions_per_week: b.sessions_per_week,
                        intent: b.intent
                    } as block_info
                }
                
                // Get recent workout dates (last 14 days)
                CALL {
                    WITH p
                    OPTIONAL MATCH (p)-[:PERFORMED]->(w:Workout)
                    WHERE w.date >= date() - duration('P14D')
                    RETURN collect(toString(w.date)) as recent_dates
                }
                
                RETURN plans, block_info, recent_dates
            """, person_id=person_id, days=str(days))
            
            record = result.single()
            if not record:
                return None
            
            # Convert plans list to dict keyed by date
            plans = {p["date"]: p for p in record["plans"] if p.get("date")}
            block_info = record["block_info"]
            recent_dates = record["recent_dates"]
            
            # Build day-by-day status
            from datetime import date as dt_date, timedelta
            today = dt_date.today()
            day_status = []
            planned_count = 0
            gap_count = 0
            
            for i in range(days + 1):  # Include today
                check_date = today + timedelta(days=i)
                date_str = check_date.isoformat()
                
                if date_str in plans:
                    day_status.append({
                        "date": date_str,
                        "day_name": check_date.strftime("%A"),
                        "has_plan": True,
                        "plan_id": plans[date_str]["plan_id"],
                        "status": plans[date_str]["status"],
                        "goal": plans[date_str]["goal"]
                    })
                    planned_count += 1
                else:
                    day_status.append({
                        "date": date_str,
                        "day_name": check_date.strftime("%A"),
                        "has_plan": False,
                        "plan_id": None,
                        "status": "unplanned",
                        "goal": None
                    })
                    gap_count += 1
            
            # Calculate expected sessions based on block
            expected_sessions = None
            coverage_pct = None
            if block_info and block_info.get("sessions_per_week"):
                expected_sessions = block_info["sessions_per_week"]
                # Rough calculation: expected per week * (days/7)
                expected_in_range = expected_sessions * (days / 7)
                coverage_pct = round((planned_count / expected_in_range) * 100) if expected_in_range > 0 else None
            
            return {
                "horizon_days": days,
                "planned_count": planned_count,
                "gap_count": gap_count,
                "coverage_percent": coverage_pct,
                "current_block": {
                    "name": block_info["name"],
                    "type": block_info["type"],
                    "sessions_per_week": block_info["sessions_per_week"],
                    "intent": block_info["intent"]
                } if block_info and block_info.get("name") else None,
                "days": day_status,
                "recent_training_dates": recent_dates
            }

    # =========================================================================
    # ADR-002: STRENGTH WORKOUT REFERENCES
    # =========================================================================

    def create_strength_workout_ref(
        self,
        workout_id: str,
        date: str,
        name: str,
        person_id: str,
        plan_id: str = None,
        total_volume_lbs: float = None,
        total_sets: int = None
    ) -> dict:
        """
        Create lightweight StrengthWorkout reference node in Neo4j.
        
        Per ADR-002: Facts live in Postgres, but we need Neo4j references
        for relationship queries (goals, blocks, injuries, etc.)
        
        Updated for v2 schema: uses workout_id (UUID) from workouts_v2 table.
        
        Args:
            workout_id: The workouts_v2.workout_id UUID from Postgres
            date: Workout date YYYY-MM-DD
            name: Workout name/goal
            person_id: Person ID for PERFORMED relationship
            plan_id: Optional PlannedWorkout ID if from plan
            total_volume_lbs: Optional volume for quick queries
            total_sets: Optional set count
            
        Returns:
            Dict with id (Neo4j node UUID), workout_id (Postgres UUID)
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Create StrengthWorkout reference node
                CREATE (sw:StrengthWorkout {
                    id: randomUUID(),
                    workout_id: $workout_id,
                    date: date($date),
                    name: $name,
                    total_volume_lbs: $total_volume_lbs,
                    total_sets: $total_sets,
                    created_at: datetime()
                })
                
                // Link to person
                CREATE (p)-[:PERFORMED]->(sw)
                
                // Link to plan if provided
                WITH sw
                OPTIONAL MATCH (pw:PlannedWorkout)
                WHERE pw.plan_id = $plan_id OR pw.id = $plan_id
                FOREACH (_ IN CASE WHEN pw IS NOT NULL THEN [1] ELSE [] END |
                    CREATE (sw)-[:EXECUTED_FROM]->(pw)
                )
                
                RETURN sw.id as id, sw.workout_id as workout_id
            """,
                person_id=person_id,
                workout_id=workout_id,
                date=date,
                name=name,
                plan_id=plan_id,
                total_volume_lbs=total_volume_lbs,
                total_sets=total_sets
            )
            
            record = result.single()
            if record:
                return {"id": record["id"], "workout_id": record["workout_id"]}
            return None

    def create_endurance_workout_ref(
        self,
        workout_id: str,
        date: str,
        name: str,
        sport: str,
        person_id: str,
        distance_miles: float = None,
        duration_minutes: float = None
    ) -> dict:
        """
        Create lightweight EnduranceWorkout reference node in Neo4j.
        
        Per ADR-002: Facts live in Postgres, but we need Neo4j references
        for relationship queries (goals, blocks, injuries, etc.)
        
        Updated for v2 schema: uses workout_id (UUID) from workouts_v2 table.
        
        Args:
            workout_id: The workouts_v2.workout_id UUID from Postgres
            date: Workout date YYYY-MM-DD
            name: Workout name
            sport: running, cycling, hiking, etc.
            person_id: Person ID for PERFORMED relationship
            distance_miles: Optional distance for quick queries
            duration_minutes: Optional duration
            
        Returns:
            Dict with id (Neo4j node UUID), workout_id (Postgres UUID)
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                
                // Create EnduranceWorkout reference node
                CREATE (ew:EnduranceWorkout {
                    id: randomUUID(),
                    workout_id: $workout_id,
                    date: date($date),
                    name: $name,
                    sport: $sport,
                    distance_miles: $distance_miles,
                    duration_minutes: $duration_minutes,
                    created_at: datetime()
                })
                
                // Link to person
                CREATE (p)-[:PERFORMED]->(ew)
                
                RETURN ew.id as id, ew.workout_id as workout_id
            """,
                person_id=person_id,
                workout_id=workout_id,
                date=date,
                name=name,
                sport=sport,
                distance_miles=distance_miles,
                duration_minutes=duration_minutes
            )
            
            record = result.single()
            if record:
                return {"id": record["id"], "workout_id": record["workout_id"]}
            return None

    def create_custom_exercise(self, exercise_id: str, name: str) -> dict:
        """
        Create a custom exercise node for user-logged exercises.
        
        Used when logging ad-hoc workouts with exercises not in the database.
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MERGE (e:Exercise {id: $id})
                ON CREATE SET 
                    e.name = $name,
                    e.source = 'user_custom',
                    e.created_at = datetime()
                RETURN e.id as id, e.name as name
            """, id=exercise_id, name=name)
            
            record = result.single()
            if record:
                return {"id": record["id"], "name": record["name"]}
            return None

    def close(self):
        """Close Neo4j driver connection."""
        self.driver.close()
