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
        """
        with self.driver.session(database=self.database) as session:
            # Get person
            person_result = session.run("""
                MATCH (p:Person {id: $person_id})
                RETURN p
            """, person_id=person_id)
            person_record = person_result.single()
            if not person_record:
                return None
            
            # Get injuries with constraints (Person direct, no Athlete)
            injuries_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_INJURY]->(i:Injury)
                WHERE i.status IN ['active', 'recovering']
                OPTIONAL MATCH (i)-[:CREATES]->(c:Constraint)
                WITH i, collect(c.description) as constraints
                RETURN i.name as injury, 
                       i.status as status, 
                       i.body_part as body_part,
                       constraints
            """, person_id=person_id)
            injuries = [dict(r) for r in injuries_result]
            
            # Get equipment
            equipment_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_ACCESS_TO]->(inv:EquipmentInventory)
                MATCH (inv)-[contains:CONTAINS]->(eq:EquipmentCategory)
                RETURN DISTINCT eq.name as name,
                       eq.type as type,
                       contains.weight_lbs as weight_lbs,
                       contains.weight_range_min as weight_range_min,
                       contains.weight_range_max as weight_range_max,
                       contains.adjustable as adjustable
            """, person_id=person_id)
            equipment = [dict(r) for r in equipment_result]
            
            # Get recent workouts (last 7 days) - Person direct
            workouts_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w:Workout)
                WHERE w.date >= date() - duration('P7D')
                RETURN DISTINCT w.date as date,
                       w.type as type,
                       w.duration_minutes as duration
                ORDER BY w.date DESC
            """, person_id=person_id)
            recent_workouts = [dict(r) for r in workouts_result]
            
            # Get active goals
            goals_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_GOAL]->(g:Goal)
                WHERE g.status = 'active'
                RETURN g.id as id,
                       g.description as description,
                       g.goal_type as type,
                       g.target_date as target_date
            """, person_id=person_id)
            goals = [dict(r) for r in goals_result]
            
            return {
                "person": dict(person_record["p"]),
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
    # EXERCISE SELECTION
    # =========================================================================

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
        """
        preserve = preserve or ["movement_pattern", "primary_muscles"]
        
        with self.driver.session(database=self.database) as session:
            # Get original exercise characteristics
            original = session.run("""
                MATCH (e:Exercise {id: $exercise_id})
                OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
                OPTIONAL MATCH (e)-[:TARGETS {role: 'primary'}]->(m:Muscle)
                RETURN e.name as name,
                       collect(DISTINCT mp.name) as patterns,
                       collect(DISTINCT m.name) as primary_muscles
            """, exercise_id=exercise_id).single()
            
            if not original:
                return []
            
            # Find exercises with similar characteristics
            result = session.run("""
                MATCH (e:Exercise {id: $exercise_id})
                OPTIONAL MATCH (e)-[:INVOLVES]->(mp:MovementPattern)
                OPTIONAL MATCH (e)-[:TARGETS {role: 'primary'}]->(m:Muscle)
                
                WITH e, collect(DISTINCT mp) as orig_patterns, collect(DISTINCT m) as orig_muscles
                
                // Find alternatives
                MATCH (alt:Exercise)
                WHERE alt.id <> e.id
                OPTIONAL MATCH (alt)-[:INVOLVES]->(alt_mp:MovementPattern)
                OPTIONAL MATCH (alt)-[:TARGETS {role: 'primary'}]->(alt_m:Muscle)
                
                WITH alt, orig_patterns, orig_muscles,
                     collect(DISTINCT alt_mp) as alt_patterns,
                     collect(DISTINCT alt_m) as alt_muscles
                
                // Score similarity
                WITH alt,
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
        """
        with self.driver.session(database=self.database) as session:
            # Create PlannedWorkout node
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                CREATE (pw:PlannedWorkout {
                    id: $plan_id,
                    date: date($date),
                    status: 'draft',
                    goal: $goal,
                    focus: $focus,
                    estimated_duration_minutes: $duration,
                    notes: $notes,
                    created_at: datetime()
                })
                CREATE (p)-[:HAS_PLANNED_WORKOUT]->(pw)
                RETURN pw
            """,
                person_id=plan_data["person_id"],
                plan_id=plan_data["id"],
                date=plan_data["date"],
                goal=plan_data.get("goal"),
                focus=plan_data.get("focus", []),
                duration=plan_data.get("estimated_duration_minutes"),
                notes=plan_data.get("notes")
            )
            
            plan_record = result.single()
            
            # Create blocks and sets
            for block in plan_data.get("blocks", []):
                block_result = session.run("""
                    MATCH (pw:PlannedWorkout {id: $plan_id})
                    CREATE (pb:PlannedBlock {
                        id: $block_id,
                        name: $name,
                        block_type: $block_type,
                        order: $order,
                        protocol_notes: $protocol_notes,
                        notes: $notes
                    })
                    CREATE (pw)-[:HAS_PLANNED_BLOCK {order: $order}]->(pb)
                    RETURN pb
                """,
                    plan_id=plan_data["id"],
                    block_id=block["id"],
                    name=block["name"],
                    block_type=block["block_type"],
                    order=block["order"],
                    protocol_notes=block.get("protocol_notes"),
                    notes=block.get("notes")
                )
                
                # Create sets
                for set_data in block.get("sets", []):
                    session.run("""
                        MATCH (pb:PlannedBlock {id: $block_id})
                        MATCH (e:Exercise {id: $exercise_id})
                        CREATE (ps:PlannedSet {
                            id: $set_id,
                            order: $order,
                            round: $round,
                            prescribed_reps: $reps,
                            prescribed_load_lbs: $load,
                            prescribed_rpe: $rpe,
                            prescribed_duration_seconds: $duration,
                            prescribed_distance_miles: $distance,
                            intensity_zone: $intensity,
                            notes: $notes
                        })
                        CREATE (pb)-[:CONTAINS_PLANNED {order: $order, round: $round}]->(ps)
                        CREATE (ps)-[:PRESCRIBES]->(e)
                    """,
                        block_id=block["id"],
                        set_id=set_data["id"],
                        exercise_id=set_data["exercise_id"],
                        order=set_data["order"],
                        round=set_data.get("round"),
                        reps=set_data.get("prescribed_reps"),
                        load=set_data.get("prescribed_load_lbs"),
                        rpe=set_data.get("prescribed_rpe"),
                        duration=set_data.get("prescribed_duration_seconds"),
                        distance=set_data.get("prescribed_distance_miles"),
                        intensity=set_data.get("intensity_zone"),
                        notes=set_data.get("notes")
                    )
            
            return {"id": plan_data["id"], "status": "draft"}

    def get_planned_workout(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get a planned workout with all blocks and sets."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pw:PlannedWorkout {id: $plan_id})
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
                "id": pw["id"],
                "date": str(pw["date"]),
                "status": pw["status"],
                "goal": pw.get("goal"),
                "focus": pw.get("focus"),
                "estimated_duration_minutes": pw.get("estimated_duration_minutes"),
                "notes": pw.get("notes"),
                "blocks": blocks
            }

    def get_plan_for_date(self, person_id: str, plan_date: str) -> Optional[Dict[str, Any]]:
        """Get planned workout for a specific date."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                WHERE pw.date = date($date)
                RETURN pw.id as plan_id
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
                    MATCH (pw:PlannedWorkout {{id: $plan_id}})
                    SET pw.status = $status,
                        pw.{timestamp_field} = datetime()
                    RETURN pw.id as id, pw.status as status
                """, plan_id=plan_id, status=status)
            else:
                result = session.run("""
                    MATCH (pw:PlannedWorkout {id: $plan_id})
                    SET pw.status = $status
                    RETURN pw.id as id, pw.status as status
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
                MATCH (pw:PlannedWorkout {id: $plan_id})
                MATCH (p:Person)-[:HAS_PLANNED_WORKOUT]->(pw)
                
                CREATE (w:Workout {
                    id: randomUUID(),
                    date: pw.date,
                    type: 'strength',
                    duration_minutes: pw.estimated_duration_minutes,
                    notes: pw.notes,
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
        
        deviations format:
        [{
            "planned_set_id": "PLANSET:xxx",
            "actual_reps": 4,
            "actual_load_lbs": 175,
            "reason": "fatigue",
            "notes": "Form breaking down"
        }]
        """
        with self.driver.session(database=self.database) as session:
            # First complete as written
            base_result = self.complete_workout_as_written(plan_id)
            
            if "error" in base_result:
                return base_result
            
            # Now apply deviations
            for dev in deviations:
                session.run("""
                    MATCH (ps:PlannedSet {id: $planned_set_id})
                    MATCH (s:Set)-[:OF_EXERCISE]->(:Exercise)<-[:PRESCRIBES]-(ps)
                    
                    // Update actual values
                    SET s.reps = COALESCE($actual_reps, s.reps),
                        s.load_lbs = COALESCE($actual_load, s.load_lbs),
                        s.notes = COALESCE($notes, s.notes)
                    
                    // Create deviation relationship
                    CREATE (s)-[:DEVIATED_FROM {
                        reason: $reason,
                        rep_deviation: $actual_reps - ps.prescribed_reps,
                        load_deviation_lbs: $actual_load - ps.prescribed_load_lbs,
                        notes: $notes
                    }]->(ps)
                """,
                    planned_set_id=dev["planned_set_id"],
                    actual_reps=dev.get("actual_reps"),
                    actual_load=dev.get("actual_load_lbs"),
                    reason=dev.get("reason", "unspecified"),
                    notes=dev.get("notes")
                )
            
            # Update execution compliance
            session.run("""
                MATCH (w:Workout)-[ef:EXECUTED_FROM]->(pw:PlannedWorkout {id: $plan_id})
                SET ef.compliance = 'with_deviations'
            """, plan_id=plan_id)
            
            return {
                "workout_id": base_result["workout_id"],
                "plan_id": plan_id,
                "compliance": "with_deviations",
                "deviations_recorded": len(deviations)
            }

    def skip_workout(self, plan_id: str, reason: str) -> Dict[str, Any]:
        """Mark a planned workout as skipped."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pw:PlannedWorkout {id: $plan_id})
                SET pw.status = 'skipped',
                    pw.skipped_at = datetime(),
                    pw.skip_reason = $reason
                RETURN pw.id as id, pw.status as status
            """, plan_id=plan_id, reason=reason)
            
            return dict(result.single())

    # =========================================================================
    # AD-HOC WORKOUT LOGGING (migrated from arnold-profile)
    # =========================================================================

    def log_adhoc_workout(self, workout_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log an unplanned/ad-hoc workout.
        This is the migrated log_workout from arnold-profile.
        """
        with self.driver.session(database=self.database) as session:
            # Create workout node - Person direct, no Athlete
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                CREATE (w:Workout {
                    id: $workout_id,
                    date: date($date),
                    type: $type,
                    duration_minutes: $duration_minutes,
                    notes: $notes,
                    source: 'adhoc',
                    imported_at: datetime()
                })
                CREATE (p)-[:PERFORMED]->(w)
                RETURN w
            """,
                person_id=workout_data["person_id"],
                workout_id=workout_data["workout_id"],
                date=workout_data["date"],
                type=workout_data.get("type", "strength"),
                duration_minutes=workout_data.get("duration_minutes"),
                notes=workout_data.get("notes")
            )

            workout_record = result.single()

            # Create WorkoutBlock for organization
            session.run("""
                MATCH (w:Workout {id: $workout_id})
                CREATE (b:WorkoutBlock {
                    id: randomUUID(),
                    name: 'Main',
                    phase: 'main',
                    order: 1
                })
                CREATE (w)-[:HAS_BLOCK {order: 1}]->(b)
            """, workout_id=workout_data["workout_id"])

            # Create sets and link to exercises
            exercises_needing_mapping = []
            set_order = 0
            
            for exercise in workout_data.get("exercises", []):
                exercise_id = exercise.get("exercise_id")
                exercise_name = exercise.get("exercise_name")

                # If no exercise_id, create/find exercise node
                if not exercise_id:
                    find_result = session.run("""
                        MATCH (ex:Exercise)
                        WHERE toLower(ex.name) = toLower($name)
                        RETURN ex.id as id
                        LIMIT 1
                    """, name=exercise_name)
                    
                    find_record = find_result.single()
                    if find_record:
                        exercise_id = find_record["id"]
                    else:
                        # Create custom exercise
                        create_result = session.run("""
                            CREATE (ex:Exercise {
                                id: 'CUSTOM:' + replace($name, ' ', '_'),
                                name: $name,
                                source: 'user_workout_log',
                                created_at: datetime()
                            })
                            RETURN ex.id as id
                        """, name=exercise_name)
                        exercise_id = create_result.single()["id"]
                        
                        exercises_needing_mapping.append({
                            "id": exercise_id,
                            "name": exercise_name
                        })

                # Create sets
                for set_data in exercise.get("sets", []):
                    set_order += 1
                    session.run("""
                        MATCH (w:Workout {id: $workout_id})-[:HAS_BLOCK]->(b:WorkoutBlock)
                        MATCH (ex:Exercise {id: $exercise_id})
                        CREATE (s:Set {
                            id: randomUUID(),
                            order: $order,
                            set_number: $set_number,
                            reps: $reps,
                            load_lbs: $load_lbs,
                            duration_seconds: $duration_seconds,
                            distance_miles: $distance_miles,
                            notes: $notes
                        })
                        CREATE (b)-[:CONTAINS {order: $order}]->(s)
                        CREATE (s)-[:OF_EXERCISE]->(ex)
                    """,
                        workout_id=workout_data["workout_id"],
                        exercise_id=exercise_id,
                        order=set_order,
                        set_number=set_data.get("set_number", set_order),
                        reps=set_data.get("reps"),
                        load_lbs=set_data.get("load_lbs"),
                        duration_seconds=set_data.get("duration_seconds"),
                        distance_miles=set_data.get("distance_miles"),
                        notes=set_data.get("notes")
                    )

            return {
                "workout_id": workout_data["workout_id"],
                "date": workout_data["date"],
                "exercises_logged": len(workout_data.get("exercises", [])),
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
        """
        with self.driver.session(database=self.database) as session:
            # Get person basics
            person_result = session.run("""
                MATCH (p:Person {id: $person_id})
                RETURN p.name as name
            """, person_id=person_id).single()
            
            if not person_result:
                return None
            
            # Get active block and goals it serves
            block_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_BLOCK]->(b:Block {status: 'active'})
                OPTIONAL MATCH (b)-[:SERVES]->(g:Goal)
                WITH b, collect(g.name) as goals
                RETURN b.name as block_name,
                       b.block_type as block_type,
                       b.week_count as block_weeks,
                       b.intent as block_intent,
                       b.volume_target as volume_target,
                       b.intensity_target as intensity_target,
                       toString(b.start_date) as block_start,
                       toString(b.end_date) as block_end,
                       goals
            """, person_id=person_id).single()
            
            # Calculate current week in block
            current_week = None
            if block_result and block_result["block_start"]:
                from datetime import date
                block_start = date.fromisoformat(block_result["block_start"])
                days_in = (date.today() - block_start).days
                current_week = (days_in // 7) + 1
            
            # Get active goals with modalities and training levels
            goals_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_GOAL]->(g:Goal {status: 'active'})
                OPTIONAL MATCH (g)-[:REQUIRES]->(m:Modality)
                OPTIONAL MATCH (p)-[:HAS_LEVEL]->(tl:TrainingLevel)-[:FOR_MODALITY]->(m)
                OPTIONAL MATCH (tl)-[:USES_MODEL]->(pm:PeriodizationModel)
                WITH g, collect(DISTINCT {
                    modality: m.name,
                    level: tl.current_level,
                    model: pm.name
                }) as modality_info
                RETURN g.name as name,
                       g.priority as priority,
                       toString(g.target_date) as target_date,
                       modality_info
                ORDER BY CASE g.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'meta' THEN 3 ELSE 4 END
            """, person_id=person_id)
            goals = [dict(r) for r in goals_result]
            
            # Get recent workouts (last 7 days) - Person now directly PERFORMED
            recent_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w:Workout)
                WHERE w.date >= date() - duration('P7D')
                OPTIONAL MATCH (w)-[:HAS_BLOCK]->(b:WorkoutBlock)-[:CONTAINS]->(s:Set)
                OPTIONAL MATCH (s)-[:OF_EXERCISE]->(e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
                WITH w, count(DISTINCT s) as sets, collect(DISTINCT mp.name) as patterns
                RETURN toString(w.date) as date, w.type as type, sets, patterns
                ORDER BY w.date DESC
                LIMIT 5
            """, person_id=person_id)
            recent_workouts = [dict(r) for r in recent_result]
            
            # Get next planned workout
            next_plan_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                WHERE pw.status IN ['draft', 'confirmed'] AND pw.date >= date()
                RETURN pw.goal as name,
                       toString(pw.date) as date,
                       pw.status as status,
                       pw.goal as goal
                ORDER BY pw.date ASC
                LIMIT 1
            """, person_id=person_id).single()
            
            # Get active injuries (Person direct, no Athlete)
            injuries_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_INJURY]->(i:Injury)
                WHERE i.status IN ['active', 'recovering']
                RETURN i.name as injury, i.status as status, i.body_part as body_part
            """, person_id=person_id)
            injuries = [dict(r) for r in injuries_result]
            
            # Build briefing
            briefing = {
                "athlete": person_result["name"],
                "goals": goals,
                "current_block": None,
                "recent_workouts": recent_workouts,
                "next_planned": None,
                "injuries": injuries,
                "workouts_this_week": len(recent_workouts)
            }
            
            if block_result and block_result["block_name"]:
                briefing["current_block"] = {
                    "name": block_result["block_name"],
                    "type": block_result["block_type"],
                    "week": current_week,
                    "of_weeks": block_result["block_weeks"],
                    "intent": block_result["block_intent"],
                    "volume": block_result["volume_target"],
                    "intensity": block_result["intensity_target"],
                    "start": block_result["block_start"],
                    "end": block_result["block_end"],
                    "serves_goals": block_result["goals"]
                }
            
            if next_plan_result:
                briefing["next_planned"] = {
                    "name": next_plan_result["name"],
                    "date": next_plan_result["date"],
                    "status": next_plan_result["status"],
                    "goal": next_plan_result["goal"]
                }
            
            return briefing

    def close(self):
        """Close Neo4j driver connection."""
        self.driver.close()
