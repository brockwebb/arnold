"""Neo4j client for Arnold profile management."""

import os
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

    def close(self):
        """Close Neo4j driver connection."""
        self.driver.close()
