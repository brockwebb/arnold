"""
Neo4j graph database connection and query utilities.

Internal Codename: CYBERDYNE-CORE
The neural net processor - a knowledge graph at the core of Arnold's reasoning.
"""

import os
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver, Session
import yaml
from pathlib import Path
from dotenv import load_dotenv


class ArnoldGraph:
    """
    Main interface to the Arnold knowledge graph.

    Internal Codename: CYBERDYNE-CORE
    "The more contact I have with humans, the more I learn."
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize connection to Neo4j.

        Args:
            config_path: Path to neo4j.yaml config file. If None, uses default.
        """
        load_dotenv()

        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "neo4j.yaml"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        self.uri = os.getenv("NEO4J_URI", config.get("uri"))
        self.user = os.getenv("NEO4J_USER", config.get("user"))
        self.password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE", config.get("database", "neo4j"))

        if not self.password:
            raise ValueError("NEO4J_PASSWORD environment variable must be set")

        self.driver: Driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )

    def close(self):
        """Close the database connection."""
        if self.driver:
            self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def verify_connectivity(self) -> bool:
        """
        Verify that we can connect to Neo4j.

        Returns:
            True if connection successful
        """
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of result records as dictionaries
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute a write transaction.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            Query result summary
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return result.consume()

    def create_constraints(self):
        """Create uniqueness constraints and indexes for the schema."""
        constraints = [
            # Anatomy layer
            "CREATE CONSTRAINT muscle_id IF NOT EXISTS FOR (m:Muscle) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT joint_id IF NOT EXISTS FOR (j:Joint) REQUIRE j.id IS UNIQUE",
            "CREATE CONSTRAINT bone_id IF NOT EXISTS FOR (b:Bone) REQUIRE b.id IS UNIQUE",
            "CREATE CONSTRAINT tissue_id IF NOT EXISTS FOR (ct:ConnectiveTissue) REQUIRE ct.id IS UNIQUE",

            # Exercise layer
            "CREATE CONSTRAINT exercise_id IF NOT EXISTS FOR (e:Exercise) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT equipment_id IF NOT EXISTS FOR (eq:Equipment) REQUIRE eq.id IS UNIQUE",
            "CREATE CONSTRAINT pattern_id IF NOT EXISTS FOR (mp:MovementPattern) REQUIRE mp.id IS UNIQUE",

            # Injury layer
            "CREATE CONSTRAINT injury_id IF NOT EXISTS FOR (i:Injury) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT constraint_id IF NOT EXISTS FOR (c:Constraint) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT phase_id IF NOT EXISTS FOR (rp:RehabPhase) REQUIRE rp.id IS UNIQUE",

            # Personal training layer
            "CREATE CONSTRAINT workout_id IF NOT EXISTS FOR (w:Workout) REQUIRE w.id IS UNIQUE",
            "CREATE CONSTRAINT instance_id IF NOT EXISTS FOR (ei:ExerciseInstance) REQUIRE ei.id IS UNIQUE",
            "CREATE CONSTRAINT goal_id IF NOT EXISTS FOR (g:Goal) REQUIRE g.id IS UNIQUE",
            "CREATE CONSTRAINT period_id IF NOT EXISTS FOR (pp:PeriodizationPhase) REQUIRE pp.id IS UNIQUE",
            "CREATE CONSTRAINT signal_id IF NOT EXISTS FOR (ss:SubjectiveSignal) REQUIRE ss.id IS UNIQUE",
        ]

        indexes = [
            "CREATE INDEX muscle_name IF NOT EXISTS FOR (m:Muscle) ON (m.name)",
            "CREATE INDEX exercise_name IF NOT EXISTS FOR (e:Exercise) ON (e.name)",
            "CREATE INDEX workout_date IF NOT EXISTS FOR (w:Workout) ON (w.date)",
        ]

        print("Creating constraints and indexes...")
        for constraint in constraints:
            try:
                self.execute_write(constraint)
                print(f"  ✓ {constraint.split('FOR')[1].split('REQUIRE')[0].strip()}")
            except Exception as e:
                print(f"  ! Error: {e}")

        for index in indexes:
            try:
                self.execute_write(index)
                print(f"  ✓ {index.split('FOR')[1].split('ON')[0].strip()}")
            except Exception as e:
                print(f"  ! Error: {e}")

    def clear_database(self, confirm: bool = False):
        """
        Clear all nodes and relationships. Use with caution!

        Args:
            confirm: Must be True to actually clear
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to clear database")

        print("Clearing database...")
        self.execute_write("MATCH (n) DETACH DELETE n")
        print("Database cleared.")

    def get_stats(self) -> Dict[str, int]:
        """
        Get basic statistics about the graph.

        Returns:
            Dictionary with node and relationship counts
        """
        stats = {}

        # Total nodes
        result = self.execute_query("MATCH (n) RETURN count(n) as count")
        stats["total_nodes"] = result[0]["count"]

        # Total relationships
        result = self.execute_query("MATCH ()-[r]->() RETURN count(r) as count")
        stats["total_relationships"] = result[0]["count"]

        # Node type counts
        node_types = [
            "Muscle", "Joint", "Bone", "ConnectiveTissue",
            "Exercise", "Equipment", "MovementPattern",
            "Injury", "Constraint", "RehabPhase",
            "Workout", "ExerciseInstance", "Goal", "PeriodizationPhase", "SubjectiveSignal"
        ]

        for node_type in node_types:
            result = self.execute_query(f"MATCH (n:{node_type}) RETURN count(n) as count")
            stats[f"{node_type.lower()}_count"] = result[0]["count"]

        return stats


def print_stats(stats: Dict[str, int]):
    """Pretty print graph statistics."""
    print("\n=== Arnold Graph Statistics ===")
    print(f"Total Nodes: {stats['total_nodes']}")
    print(f"Total Relationships: {stats['total_relationships']}")
    print("\nNode Counts:")

    categories = {
        "Anatomy": ["muscle", "joint", "bone", "connectivetissue"],
        "Exercise": ["exercise", "equipment", "movementpattern"],
        "Injury/Rehab": ["injury", "constraint", "rehabphase"],
        "Training": ["workout", "exerciseinstance", "goal", "periodizationphase", "subjectivesignal"]
    }

    for category, nodes in categories.items():
        print(f"\n{category}:")
        for node in nodes:
            key = f"{node}_count"
            if key in stats:
                print(f"  {node.title()}: {stats[key]}")
