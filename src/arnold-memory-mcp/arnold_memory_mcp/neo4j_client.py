"""Neo4j client for Arnold memory/context operations."""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from neo4j import GraphDatabase
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)


class Neo4jMemoryClient:
    """Neo4j database client for memory and context operations."""

    def __init__(self):
        """Initialize Neo4j driver and OpenAI client."""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "arnold")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        
        # OpenAI client for embeddings
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.embedding_model = "text-embedding-3-small"  # 1536 dimensions, cheaper than ada-002

    def load_briefing(self, person_id: str) -> Dict[str, Any]:
        """
        Load comprehensive coaching context for conversation start.
        
        This is the foundation of coaching continuity - everything Claude needs
        to know to coach effectively from message one.
        
        Returns structured context covering:
        - Who the athlete is (identity, phenotype, background)
        - What they're training for (goals with modality requirements)
        - Where they are in the plan (current block, week)
        - What constraints exist (injuries, gaps)
        - How to progress each modality (training levels + models)
        - What they've done recently (last 14 days)
        - Coaching observations from past conversations
        - What's next (upcoming planned sessions)
        """
        with self.driver.session(database=self.database) as session:
            briefing = {}
            
            # =========================================================
            # ATHLETE IDENTITY & BACKGROUND
            # =========================================================
            person_result = session.run("""
                MATCH (p:Person {id: $person_id})
                RETURN p {
                    .name,
                    .birth_date,
                    .sex,
                    .athlete_phenotype,
                    .athlete_phenotype_notes,
                    .training_age_total_years,
                    .martial_arts_years,
                    .martial_arts_notes,
                    .triathlon_history,
                    .cycling_history,
                    .running_preference
                } as person
            """, person_id=person_id).single()
            
            if not person_result:
                return None
            
            person = person_result["person"]
            
            briefing["athlete"] = {
                "name": person.get("name"),
                "phenotype": person.get("athlete_phenotype"),
                "phenotype_notes": person.get("athlete_phenotype_notes"),
                "training_age_total": person.get("training_age_total_years")
            }
            
            briefing["background"] = {
                "martial_arts": person.get("martial_arts_notes"),
                "triathlon": person.get("triathlon_history"),
                "cycling": person.get("cycling_history"),
                "running_preference": person.get("running_preference")
            }
            
            # =========================================================
            # GOALS WITH MODALITY REQUIREMENTS
            # =========================================================
            goals_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_GOAL]->(g:Goal)
                WHERE g.status = 'active'
                OPTIONAL MATCH (g)-[req:REQUIRES]->(m:Modality)
                OPTIONAL MATCH (p)-[:HAS_LEVEL]->(tl:TrainingLevel)-[:FOR_MODALITY]->(m)
                OPTIONAL MATCH (tl)-[:USES_MODEL]->(pm:PeriodizationModel)
                WITH g, collect(DISTINCT {
                    modality: m.name,
                    priority: req.priority,
                    level: tl.current_level,
                    years: tl.training_age_years,
                    model: pm.name,
                    gaps: tl.known_gaps
                }) as modalities
                RETURN g {
                    .name,
                    .type,
                    .target_value,
                    .target_unit,
                    .target_reps,
                    .priority,
                    target_date: toString(g.target_date)
                } as goal,
                modalities
                ORDER BY CASE g.priority 
                    WHEN 'high' THEN 1 
                    WHEN 'medium' THEN 2 
                    WHEN 'meta' THEN 3 
                    ELSE 4 
                END
            """, person_id=person_id)
            
            briefing["goals"] = []
            for record in goals_result:
                goal_data = dict(record["goal"])
                # Filter out null modality entries
                modalities = [m for m in record["modalities"] if m.get("modality")]
                goal_data["requires"] = modalities
                briefing["goals"].append(goal_data)
            
            # =========================================================
            # ALL TRAINING LEVELS
            # =========================================================
            levels_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_LEVEL]->(tl:TrainingLevel)-[:FOR_MODALITY]->(m:Modality)
                OPTIONAL MATCH (tl)-[:USES_MODEL]->(pm:PeriodizationModel)
                RETURN m.name as modality,
                       tl.current_level as level,
                       tl.training_age_years as years,
                       pm.name as model,
                       tl.known_gaps as gaps,
                       tl.strong_planes as strong_planes,
                       tl.evidence_notes as evidence
                ORDER BY m.name
            """, person_id=person_id)
            
            briefing["training_levels"] = {}
            for record in levels_result:
                briefing["training_levels"][record["modality"]] = {
                    "level": record["level"],
                    "years": record["years"],
                    "model": record["model"],
                    "gaps": record["gaps"],
                    "strong_planes": record["strong_planes"],
                    "evidence": record["evidence"]
                }
            
            # =========================================================
            # CURRENT BLOCK
            # =========================================================
            block_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_BLOCK]->(b:Block)
                WHERE b.status = 'active'
                OPTIONAL MATCH (b)-[:SERVES]->(g:Goal)
                WITH b, collect(g.name) as serves
                RETURN b {
                    .name,
                    .block_type,
                    .week_count,
                    .intent,
                    .volume_target,
                    .intensity_target,
                    .loading_pattern,
                    .focus,
                    start_date: toString(b.start_date),
                    end_date: toString(b.end_date)
                } as block,
                serves
            """, person_id=person_id).single()
            
            if block_result and block_result["block"]:
                block = dict(block_result["block"])
                
                # Calculate current week
                current_week = None
                if block.get("start_date"):
                    start = date.fromisoformat(block["start_date"])
                    days_in = (date.today() - start).days
                    current_week = max(1, (days_in // 7) + 1)
                
                briefing["current_block"] = {
                    "name": block.get("name"),
                    "type": block.get("block_type"),
                    "week": current_week,
                    "of_weeks": block.get("week_count"),
                    "dates": f"{block.get('start_date')} → {block.get('end_date')}",
                    "intent": block.get("intent"),
                    "volume": block.get("volume_target"),
                    "intensity": block.get("intensity_target"),
                    "loading": block.get("loading_pattern"),
                    "focus": block.get("focus"),
                    "serves": block_result["serves"]
                }
            else:
                briefing["current_block"] = None
            
            # =========================================================
            # MEDICAL: INJURIES & CONSTRAINTS
            # =========================================================
            injuries_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_INJURY]->(i:Injury)
                OPTIONAL MATCH (i)-[:CREATES]->(c:Constraint)
                WITH i, collect(c.description) as constraints
                RETURN i {
                    .name,
                    .status,
                    .body_part,
                    .side,
                    .diagnosis,
                    .surgery_type,
                    .recovery_notes,
                    .rehab_insights,
                    .outcome,
                    surgery_date: toString(i.surgery_date),
                    injury_date: toString(i.injury_date)
                } as injury,
                constraints
                ORDER BY CASE i.status 
                    WHEN 'active' THEN 1 
                    WHEN 'recovering' THEN 2 
                    ELSE 3 
                END
            """, person_id=person_id)
            
            active_injuries = []
            resolved_injuries = []
            for record in injuries_result:
                injury = dict(record["injury"])
                injury["constraints"] = record["constraints"]
                
                # Calculate weeks post-surgery if applicable
                if injury.get("surgery_date"):
                    surgery_date = date.fromisoformat(injury["surgery_date"])
                    weeks_post = (date.today() - surgery_date).days // 7
                    injury["weeks_post_surgery"] = weeks_post
                
                if injury.get("status") in ["active", "recovering"]:
                    active_injuries.append(injury)
                else:
                    resolved_injuries.append(injury)
            
            briefing["medical"] = {
                "active_injuries": active_injuries,
                "resolved": resolved_injuries
            }
            
            # =========================================================
            # RECENT WORKOUTS (Last 14 days)
            # Match all workout types - :Workout, :StrengthWorkout, :EnduranceWorkout
            # Deduplicate by date, preferring nodes with actual structure (sets > 0)
            # =========================================================
            recent_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:PERFORMED]->(w)
                WHERE (w:Workout OR w:StrengthWorkout OR w:EnduranceWorkout)
                  AND w.date >= date() - duration('P14D')
                OPTIONAL MATCH (w)-[:HAS_BLOCK]->(wb:WorkoutBlock)-[:CONTAINS]->(s:Set)
                OPTIONAL MATCH (s)-[:OF_EXERCISE]->(e:Exercise)-[:INVOLVES]->(mp:MovementPattern)
                WITH w, count(DISTINCT s) as sets, collect(DISTINCT mp.name) as patterns
                WITH w.date as workout_date,
                     collect({name: coalesce(w.name, w.type), type: w.type, 
                              duration: w.duration_minutes, sets: sets, patterns: patterns}) as workouts
                // Pick the workout with most sets (prefers :Workout with structure over reference nodes)
                WITH workout_date, 
                     reduce(best = workouts[0], w IN workouts | 
                         CASE WHEN w.sets > best.sets THEN w ELSE best END) as best
                RETURN toString(workout_date) as date,
                       best.name as name,
                       best.type as type,
                       best.duration as duration,
                       best.sets as sets,
                       best.patterns as patterns
                ORDER BY workout_date DESC
            """, person_id=person_id)
            
            briefing["recent_workouts"] = [dict(r) for r in recent_result]
            briefing["workouts_this_week"] = len([
                w for w in briefing["recent_workouts"] 
                if w["date"] and date.fromisoformat(w["date"]) >= date.today() - timedelta(days=7)
            ])
            
            # =========================================================
            # COACHING OBSERVATIONS (from past conversations)
            # =========================================================
            obs_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_OBSERVATION]->(o)
                WHERE o:Observation OR o:CoachingObservation
                RETURN o {
                    .content,
                    .observation_type,
                    .tags,
                    created_at: toString(o.created_at)
                } as observation
                ORDER BY o.created_at DESC
                LIMIT 20
            """, person_id=person_id)
            
            briefing["observations"] = [dict(r["observation"]) for r in obs_result]
            
            # =========================================================
            # UPCOMING PLANNED SESSIONS
            # =========================================================
            planned_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_PLANNED_WORKOUT]->(pw:PlannedWorkout)
                WHERE pw.status IN ['draft', 'confirmed'] AND pw.date >= date()
                RETURN pw {
                    .id,
                    .goal,
                    .status,
                    .focus,
                    .estimated_duration_minutes,
                    date: toString(pw.date)
                } as plan
                ORDER BY pw.date ASC
                LIMIT 5
            """, person_id=person_id)
            
            briefing["upcoming_sessions"] = [dict(r["plan"]) for r in planned_result]
            
            # =========================================================
            # ACTIVITIES (sports/practices)
            # =========================================================
            activities_result = session.run("""
                MATCH (p:Person {id: $person_id})-[pr:PRACTICES]->(a:Activity)
                RETURN a.name as activity,
                       pr.current_role as role,
                       pr.years as years,
                       pr.frequency as frequency
            """, person_id=person_id)
            
            briefing["activities"] = [dict(r) for r in activities_result]
            
            # =========================================================
            # EQUIPMENT AVAILABLE
            # =========================================================
            equipment_result = session.run("""
                MATCH (p:Person {id: $person_id})-[:HAS_ACCESS_TO]->(inv:EquipmentInventory)
                MATCH (inv)-[c:CONTAINS]->(eq:EquipmentCategory)
                RETURN eq.name as equipment,
                       c.weight_lbs as weight,
                       c.weight_range_min as weight_min,
                       c.weight_range_max as weight_max,
                       c.adjustable as adjustable
            """, person_id=person_id)
            
            briefing["equipment"] = [dict(r) for r in equipment_result]
            
            # =========================================================
            # PATTERN GAPS (from Postgres cache via direct query)
            # =========================================================
            try:
                import psycopg2
                pg_conn = psycopg2.connect(
                    dbname='arnold_analytics',
                    host='localhost',
                    port=5432
                )
                with pg_conn.cursor() as cur:
                    # Pattern gaps - patterns not trained in 7+ days
                    cur.execute("""
                        SELECT movement_pattern, days_since
                        FROM pattern_last_trained
                        WHERE days_since >= 7
                        ORDER BY days_since DESC
                        LIMIT 5
                    """)
                    pattern_gaps = [{'pattern': r[0], 'days': r[1]} for r in cur.fetchall()]
                    briefing["pattern_gaps"] = pattern_gaps
                    
                    # Muscle volume this week (primary only)
                    cur.execute("""
                        SELECT muscle_name, total_sets, total_reps
                        FROM muscle_volume_weekly
                        WHERE role = 'primary' 
                          AND week_start = date_trunc('week', CURRENT_DATE)::date
                        ORDER BY total_sets DESC
                        LIMIT 8
                    """)
                    muscle_volume = [{'muscle': r[0], 'sets': r[1], 'reps': r[2]} for r in cur.fetchall()]
                    briefing["muscle_volume_this_week"] = muscle_volume
                    
                pg_conn.close()
            except Exception as e:
                logger.warning(f"Could not load pattern/muscle data from Postgres: {e}")
                briefing["pattern_gaps"] = []
                briefing["muscle_volume_this_week"] = []
            
            return briefing

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text using OpenAI.
        
        Returns 1536-dimension vector for text-embedding-3-small.
        """
        try:
            response = self.openai.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    def store_observation(
        self, 
        person_id: str, 
        content: str, 
        observation_type: str = "insight",
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """
        Store a coaching observation with embedding for semantic search.
        
        observation_type: pattern | preference | insight | flag | decision
        tags: keywords for retrieval (e.g., ["deadlift", "fatigue"])
        """
        # Generate embedding for the observation content
        embedding = self.generate_embedding(content)
        logger.info(f"Generated embedding ({len(embedding)} dimensions) for observation")
        
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                CREATE (o:Observation {
                    id: 'OBS:' + randomUUID(),
                    content: $content,
                    observation_type: $observation_type,
                    tags: $tags,
                    embedding: $embedding,
                    created_at: datetime()
                })
                CREATE (p)-[:HAS_OBSERVATION]->(o)
                RETURN o.id as id, o.content as content
            """, 
                person_id=person_id,
                content=content,
                observation_type=observation_type,
                tags=tags or [],
                embedding=embedding
            )
            
            record = result.single()
            return {
                "id": record["id"], 
                "content": record["content"],
                "embedding_generated": True
            }

    def get_observations(
        self, 
        person_id: str, 
        tags: List[str] = None,
        observation_type: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieve coaching observations, optionally filtered.
        """
        with self.driver.session(database=self.database) as session:
            # Handle both old CoachingObservation and new Observation labels
            query = """
                MATCH (p:Person {id: $person_id})-[:HAS_OBSERVATION]->(o)
                WHERE o:Observation OR o:CoachingObservation
            """
            
            conditions = []
            if tags:
                conditions.append("any(tag IN $tags WHERE tag IN o.tags)")
            if observation_type:
                conditions.append("o.observation_type = $observation_type")
            
            if conditions:
                query += " AND " + " AND ".join(conditions)
            
            query += """
                RETURN o {
                    .id,
                    .content,
                    .observation_type,
                    .tags,
                    created_at: toString(o.created_at)
                } as observation
                ORDER BY o.created_at DESC
                LIMIT $limit
            """
            
            result = session.run(
                query,
                person_id=person_id,
                tags=tags,
                observation_type=observation_type,
                limit=limit
            )
            
            return [dict(r["observation"]) for r in result]

    def search_observations(
        self,
        person_id: str,
        query: str,
        limit: int = 5,
        threshold: float = 0.7,
        observation_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over coaching observations using vector similarity.
        
        Uses Neo4j native vector index (obs_embedding_index) with cosine similarity.
        
        Args:
            person_id: Person to search observations for
            query: Natural language query
            limit: Max results to return (default 5)
            threshold: Minimum similarity score 0-1 (default 0.7)
            observation_type: Optional filter by type
            
        Returns:
            List of observations with similarity scores, ordered by relevance
        """
        # Generate embedding for the query
        query_embedding = self.generate_embedding(query)
        logger.info(f"Generated query embedding for: '{query[:50]}...'")
        
        with self.driver.session(database=self.database) as session:
            # Use Neo4j vector index for similarity search
            # Filter to only observations belonging to this person
            cypher = """
                CALL db.index.vector.queryNodes('obs_embedding_index', $limit * 2, $query_embedding)
                YIELD node, score
                WHERE score >= $threshold
                MATCH (p:Person {id: $person_id})-[:HAS_OBSERVATION]->(node)
            """
            
            if observation_type:
                cypher += " AND node.observation_type = $observation_type"
            
            cypher += """
                RETURN node {
                    .id,
                    .content,
                    .observation_type,
                    .tags,
                    created_at: toString(node.created_at)
                } as observation,
                score
                ORDER BY score DESC
                LIMIT $limit
            """
            
            result = session.run(
                cypher,
                person_id=person_id,
                query_embedding=query_embedding,
                limit=limit,
                threshold=threshold,
                observation_type=observation_type
            )
            
            observations = []
            for record in result:
                obs = dict(record["observation"])
                obs["similarity"] = round(record["score"], 3)
                observations.append(obs)
            
            logger.info(f"Found {len(observations)} observations above threshold {threshold}")
            return observations

    def get_block_summary(self, block_id: str) -> Optional[Dict[str, Any]]:
        """Get or generate summary for a training block."""
        with self.driver.session(database=self.database) as session:
            # First check if summary exists
            existing = session.run("""
                MATCH (b:Block {id: $block_id})-[:HAS_SUMMARY]->(s:Summary)
                RETURN s {
                    .content,
                    .key_metrics,
                    .key_learnings,
                    created_at: toString(s.created_at)
                } as summary
            """, block_id=block_id).single()
            
            if existing:
                return dict(existing["summary"])
            
            # If no summary, return block data for summarization
            block_result = session.run("""
                MATCH (b:Block {id: $block_id})
                OPTIONAL MATCH (b)-[:SERVES]->(g:Goal)
                OPTIONAL MATCH (:Person)-[:PERFORMED]->(w:Workout)
                WHERE w.date >= b.start_date AND w.date <= b.end_date
                OPTIONAL MATCH (w)-[:HAS_BLOCK]->(:WorkoutBlock)-[:CONTAINS]->(s:Set)
                WITH b, collect(DISTINCT g.name) as goals, 
                     count(DISTINCT w) as workout_count,
                     count(DISTINCT s) as total_sets
                RETURN b {
                    .name,
                    .block_type,
                    .intent,
                    start_date: toString(b.start_date),
                    end_date: toString(b.end_date)
                } as block,
                goals,
                workout_count,
                total_sets
            """, block_id=block_id).single()
            
            if not block_result:
                return None
            
            return {
                "needs_summarization": True,
                "block": dict(block_result["block"]),
                "goals": block_result["goals"],
                "workout_count": block_result["workout_count"],
                "total_sets": block_result["total_sets"]
            }

    def store_block_summary(
        self, 
        block_id: str, 
        content: str,
        key_metrics: Dict[str, Any] = None,
        key_learnings: List[str] = None
    ) -> Dict[str, Any]:
        """Store a summary for a completed block."""
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (b:Block {id: $block_id})
                CREATE (s:Summary {
                    id: 'SUM:' + randomUUID(),
                    summary_type: 'block',
                    content: $content,
                    key_metrics: $key_metrics,
                    key_learnings: $key_learnings,
                    created_at: datetime()
                })
                CREATE (b)-[:HAS_SUMMARY]->(s)
                RETURN s.id as id
            """,
                block_id=block_id,
                content=content,
                key_metrics=key_metrics or {},
                key_learnings=key_learnings or []
            )
            
            return {"id": result.single()["id"]}

    def close(self):
        """Close Neo4j driver connection."""
        self.driver.close()
