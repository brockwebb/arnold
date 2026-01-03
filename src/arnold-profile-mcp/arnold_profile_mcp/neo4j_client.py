"""Neo4j client for Arnold profile management."""

import os
from typing import Optional
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Neo4jClient:
    """Neo4j database client for profile management."""

    def __init__(self):
        """Initialize Neo4j driver."""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "arnold")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    def create_person_node(self, profile: dict) -> dict:
        """
        Create Person node in Neo4j.

        Args:
            profile: Profile dictionary from ProfileManager

        Returns:
            Dictionary with created Person and Athlete node info
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                CREATE (p:Person {
                    id: $person_id,
                    name: $name,
                    age: $age,
                    sex: $sex,
                    height_inches: $height_inches,
                    created_at: datetime($created_at)
                })
                CREATE (ath:Athlete {
                    id: 'ROLE:athlete:' + $person_id,
                    name: $name
                })
                CREATE (p)-[:HAS_ROLE]->(ath)
                RETURN p, ath
            """,
                person_id=profile["person_id"],
                name=profile["demographics"]["name"],
                age=profile["demographics"]["age"],
                sex=profile["demographics"]["sex"],
                height_inches=profile["demographics"]["height_inches"],
                created_at=profile["created_at"]
            )

            record = result.single()
            if record:
                return {
                    "person": dict(record["p"]),
                    "athlete": dict(record["ath"])
                }
            return {}

    def get_person_node(self, person_id: str) -> dict:
        """
        Retrieve Person node from Neo4j.

        Args:
            person_id: UUID of the person

        Returns:
            Person node properties or None if not found
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                RETURN p
            """, person_id=person_id)

            record = result.single()
            return dict(record["p"]) if record else None

    def update_person_node(self, person_id: str, field: str, value) -> dict:
        """
        Update Person node field in Neo4j.

        Args:
            person_id: UUID of the person
            field: Field name to update
            value: New value

        Returns:
            Updated Person node properties
        """
        with self.driver.session(database=self.database) as session:
            # Build dynamic SET clause
            result = session.run(f"""
                MATCH (p:Person {{id: $person_id}})
                SET p.{field} = $value
                RETURN p
            """, person_id=person_id, value=value)

            record = result.single()
            return dict(record["p"]) if record else None

    def create_workout_node(self, workout_data: dict) -> dict:
        """
        Create Workout node and relationships in Neo4j.
        Expects pre-structured data from Claude.

        Args:
            workout_data: Fully structured workout from Claude Desktop

        Returns:
            Dictionary with created Workout node info
        """
        with self.driver.session(database=self.database) as session:
            # Create workout node
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                OPTIONAL MATCH (a:Athlete)<-[:HAS_ROLE]-(p)
                WITH COALESCE(a, p) as performer
                CREATE (w:Workout {
                    id: $workout_id,
                    date: date($date),
                    type: $type,
                    duration_minutes: $duration_minutes,
                    notes: $notes,
                    created_at: datetime()
                })
                CREATE (performer)-[:PERFORMED]->(w)
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

            # Create sets and link to exercises
            exercises_needing_mapping = []
            
            for exercise in workout_data["exercises"]:
                exercise_id = exercise.get("exercise_id")  # Claude provides this or None
                exercise_name = exercise.get("exercise_name")  # Always present from Claude

                # If no exercise_id, create a user exercise node
                if not exercise_id:
                    result = session.run("""
                        MERGE (ex:Exercise {name: $exercise_name, source: 'user'})
                        ON CREATE SET ex.id = randomUUID(), ex.created_at = datetime()
                        RETURN ex.id as exercise_id
                    """, exercise_name=exercise_name)
                    exercise_id = result.single()["exercise_id"]
                
                # Check if exercise has muscle mappings
                has_mappings = session.run("""
                    MATCH (ex:Exercise {id: $exercise_id})-[:TARGETS]->(:Muscle)
                    RETURN count(*) > 0 as has_mappings
                """, exercise_id=exercise_id).single()["has_mappings"]
                
                if not has_mappings:
                    exercises_needing_mapping.append({
                        "id": exercise_id,
                        "name": exercise_name
                    })

                for set_data in exercise["sets"]:
                    session.run("""
                        MATCH (w:Workout {id: $workout_id})
                        MATCH (ex:Exercise {id: $exercise_id})
                        CREATE (s:Set {
                            id: randomUUID(),
                            set_number: $set_number,
                            reps: $reps,
                            load_lbs: $load_lbs,
                            duration_seconds: $duration_seconds,
                            distance_miles: $distance_miles,
                            rpe: $rpe,
                            notes: $notes
                        })
                        CREATE (w)-[:CONTAINS]->(s)
                        CREATE (s)-[:OF_EXERCISE]->(ex)
                    """,
                        workout_id=workout_data["workout_id"],
                        exercise_id=exercise_id,
                        set_number=set_data["set_number"],
                        reps=set_data.get("reps"),
                        load_lbs=set_data.get("load_lbs"),
                        duration_seconds=set_data.get("duration_seconds"),
                        distance_miles=set_data.get("distance_miles"),
                        rpe=set_data.get("rpe"),
                        notes=set_data.get("notes")
                    )

            result = {
                "workout": dict(workout_record["w"]) if workout_record else {},
                "exercises_needing_mapping": exercises_needing_mapping
            }
            
            return result

    def find_exercise_by_name(self, exercise_name: str) -> Optional[str]:
        """
        Fuzzy search for canonical exercise by name.
        Returns exercise ID if found, None otherwise.
        Claude can call this to map exercises.

        Args:
            exercise_name: Name of exercise to search for

        Returns:
            Exercise ID (UUID) or None if not found
        """
        # Use full-text search first
        results = self.search_exercises(exercise_name, limit=1)
        if results:
            return results[0]['exercise_id']
        return None

    def search_exercises(self, query: str, limit: int = 5) -> list:
        """
        Search exercises using full-text index with fuzzy matching.
        Returns candidates for Claude to select from.

        Args:
            query: Search query (exercise name or alias)
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

    def create_observation_node(self, observation: dict):
        """
        Create Observation node in Neo4j.

        Args:
            observation: Observation dictionary from ObservationManager

        Returns:
            Created observation and concept nodes
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})

                // Create or get ObservationConcept node
                MERGE (oc:ObservationConcept {
                    concept: $concept,
                    loinc_code: $loinc_code
                })

                // Create Observation node
                CREATE (obs:Observation {
                    id: $obs_id,
                    value: $value,
                    unit: $unit,
                    recorded_at: date($recorded_date),
                    created_at: datetime($created_at),
                    notes: $notes
                })

                // Link relationships
                CREATE (p)-[:HAS_OBSERVATION]->(obs)
                CREATE (obs)-[:HAS_CONCEPT]->(oc)

                RETURN obs, oc
            """,
                person_id=observation["person_id"],
                obs_id=observation["id"],
                concept=observation["concept"],
                loinc_code=observation.get("loinc_code"),
                value=observation["value"],
                unit=observation.get("unit"),
                recorded_date=observation["recorded_at"],
                created_at=observation["created_at"],
                notes=observation.get("notes")
            )
            return result.single()

    def create_equipment_inventory(self, inventory_data: dict):
        """
        Create EquipmentInventory node and relationships.

        Args:
            inventory_data: Inventory dictionary from EquipmentManager

        Returns:
            Created inventory node
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                CREATE (inv:EquipmentInventory {
                    id: $inv_id,
                    name: $name,
                    type: $type
                })
                CREATE (p)-[:HAS_ACCESS_TO {
                    context: $context,
                    location: $location,
                    started: date($started),
                    is_primary: $is_primary
                }]->(inv)
                RETURN inv
            """,
                person_id=inventory_data["person_id"],
                inv_id=inventory_data["id"],
                name=inventory_data["name"],
                type=inventory_data.get("type", "personal"),
                context=inventory_data["context"],
                location=inventory_data["location"],
                started=inventory_data.get("started", "2025-01-01"),
                is_primary=inventory_data["is_primary"]
            )
            return result.single()

    def add_equipment_to_inventory(self, inventory_id: str, equipment_data: dict):
        """
        Add equipment to inventory with CONTAINS relationship.

        Args:
            inventory_id: UUID of inventory
            equipment_data: Equipment details from Claude

        Returns:
            Created equipment category node
        """
        with self.driver.session(database=self.database) as session:
            # Get or create EquipmentCategory
            result = session.run("""
                MATCH (inv:EquipmentInventory {id: $inv_id})
                MERGE (eq:EquipmentCategory {name: $name, type: $eq_type})
                CREATE (inv)-[:CONTAINS {
                    quantity: $quantity,
                    weight_lbs: $weight_lbs,
                    weight_range_min: $weight_range_min,
                    weight_range_max: $weight_range_max,
                    adjustable: $adjustable,
                    acquired: date($acquired),
                    condition: $condition,
                    notes: $notes
                }]->(eq)
                RETURN eq
            """,
                inv_id=inventory_id,
                name=equipment_data["name"],
                eq_type=equipment_data.get("type", "general"),
                quantity=equipment_data.get("quantity", 1),
                weight_lbs=equipment_data.get("weight_lbs"),
                weight_range_min=equipment_data.get("weight_range_min"),
                weight_range_max=equipment_data.get("weight_range_max"),
                adjustable=equipment_data.get("adjustable", False),
                acquired=equipment_data.get("acquired", "2025-01-01"),
                condition=equipment_data.get("condition", "good"),
                notes=equipment_data.get("notes")
            )
            return result.single()

    def create_activity(self, activity_data: dict):
        """
        Create Activity node.

        Args:
            activity_data: Activity dictionary from ActivitiesManager

        Returns:
            Created activity node
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                CREATE (act:Activity {
                    id: $act_id,
                    name: $name,
                    type: $type,
                    frequency_per_week: $frequency,
                    location: $location,
                    skill_level: $skill_level,
                    active: $active
                })
                CREATE (p)-[:PARTICIPATES_IN]->(act)
                RETURN act
            """,
                person_id=activity_data["person_id"],
                act_id=activity_data["id"],
                name=activity_data["name"],
                type=activity_data.get("type", "sport"),
                frequency=activity_data.get("frequency_per_week"),
                location=activity_data.get("location"),
                skill_level=activity_data.get("skill_level"),
                active=activity_data.get("active", True)
            )
            return result.single()

    def get_equipment_inventories(self, person_id: str):
        """
        Get all equipment inventories for a person.

        Args:
            person_id: UUID of person

        Returns:
            List of inventory dictionaries with equipment
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[r:HAS_ACCESS_TO]->(inv:EquipmentInventory)
                OPTIONAL MATCH (inv)-[c:CONTAINS]->(eq:EquipmentCategory)
                RETURN inv, r, collect({
                    name: eq.name,
                    type: eq.type,
                    quantity: c.quantity,
                    weight_lbs: c.weight_lbs,
                    weight_range_min: c.weight_range_min,
                    weight_range_max: c.weight_range_max,
                    adjustable: c.adjustable,
                    condition: c.condition,
                    notes: c.notes
                }) as equipment
            """, person_id=person_id)

            inventories = []
            for record in result:
                inv_node = dict(record["inv"])
                rel = dict(record["r"])
                equipment_list = [eq for eq in record["equipment"] if eq["name"] is not None]

                inventories.append({
                    "id": inv_node["id"],
                    "name": inv_node["name"],
                    "type": inv_node.get("type", "personal"),
                    "location": rel.get("location"),
                    "context": rel.get("context"),
                    "is_primary": rel.get("is_primary", False),
                    "equipment": equipment_list
                })

            return inventories

    def get_activities(self, person_id: str):
        """
        Get all activities for a person.

        Args:
            person_id: UUID of person

        Returns:
            List of activity dictionaries
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})-[:PARTICIPATES_IN]->(act:Activity)
                RETURN act
                ORDER BY act.name
            """, person_id=person_id)

            activities = []
            for record in result:
                act_node = dict(record["act"])
                activities.append(act_node)

            return activities

    def get_workout_by_date(self, person_id: str, workout_date: str):
        """
        Get workout by date.

        Args:
            person_id: UUID of person
            workout_date: Date in YYYY-MM-DD format

        Returns:
            Workout dictionary or None if not found
        """
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:Person {id: $person_id})
                OPTIONAL MATCH (a:Athlete)<-[:HAS_ROLE]-(p)
                WITH COALESCE(a, p) as performer
                MATCH (performer)-[:PERFORMED]->(w:Workout {date: date($date)})
                OPTIONAL MATCH (w)-[:CONTAINS]->(s:Set)
                OPTIONAL MATCH (s)-[:OF_EXERCISE]->(ex:Exercise)
                RETURN w, collect({
                    set_number: s.set_number,
                    reps: s.reps,
                    load_lbs: s.load_lbs,
                    duration_seconds: s.duration_seconds,
                    distance_miles: s.distance_miles,
                    rpe: s.rpe,
                    notes: s.notes,
                    exercise_id: ex.id,
                    exercise_name: ex.name
                }) as sets
            """, person_id=person_id, date=workout_date)

            record = result.single()
            if not record:
                return None

            workout_node = dict(record["w"])
            sets_data = record["sets"]

            # Group sets by exercise
            exercises = {}
            for set_info in sets_data:
                if set_info["set_number"] is None:
                    continue

                exercise_name = set_info.get("exercise_name", "Unknown Exercise")
                exercise_id = set_info.get("exercise_id")

                if exercise_name not in exercises:
                    exercises[exercise_name] = {
                        "exercise_name": exercise_name,
                        "exercise_id": exercise_id,
                        "sets": []
                    }

                exercises[exercise_name]["sets"].append({
                    "set_number": set_info["set_number"],
                    "reps": set_info.get("reps"),
                    "load_lbs": set_info.get("load_lbs"),
                    "duration_seconds": set_info.get("duration_seconds"),
                    "distance_miles": set_info.get("distance_miles"),
                    "rpe": set_info.get("rpe"),
                    "notes": set_info.get("notes")
                })

            return {
                "workout_id": workout_node["id"],
                "person_id": person_id,
                "date": str(workout_node["date"]),
                "type": workout_node.get("type"),
                "duration_minutes": workout_node.get("duration_minutes"),
                "notes": workout_node.get("notes"),
                "exercises": list(exercises.values())
            }

    def close(self):
        """Close Neo4j driver connection."""
        self.driver.close()
