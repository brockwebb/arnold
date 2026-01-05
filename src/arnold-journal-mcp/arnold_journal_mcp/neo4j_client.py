"""Neo4j client for Arnold Journal MCP - handles relationships."""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import date

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Neo4jJournalClient:
    """Client for journal relationship operations in Neo4j."""
    
    def __init__(self):
        self.uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.environ.get("NEO4J_USER", "neo4j")
        self.password = os.environ.get("NEO4J_PASSWORD", "password")
        self.database = os.environ.get("NEO4J_DATABASE", "arnold")
        self._driver = None
    
    def _get_driver(self):
        """Get or create Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password)
            )
        return self._driver
    
    def _execute(self, query: str, params: dict = None) -> List[Dict]:
        """Execute a Cypher query and return results."""
        driver = self._get_driver()
        with driver.session(database=self.database) as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    
    def _execute_single(self, query: str, params: dict = None) -> Optional[Dict]:
        """Execute a Cypher query and return single result."""
        results = self._execute(query, params)
        return results[0] if results else None
    
    def create_log_entry_node(
        self,
        postgres_id: int,
        entry_date: date,
        entry_type: str,
        category: Optional[str],
        severity: str,
        summary: Optional[str],
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """Create a LogEntry node in Neo4j and return its UUID."""
        
        query = """
        MATCH (p:Person {name: 'Brock Webb'})
        CREATE (le:LogEntry {
            id: randomUUID(),
            postgres_id: $postgres_id,
            date: date($date),
            entry_type: $entry_type,
            category: $category,
            severity: $severity,
            summary: $summary,
            tags: $tags,
            created_at: datetime()
        })
        CREATE (p)-[:LOGGED]->(le)
        RETURN le.id as id
        """
        
        try:
            result = self._execute_single(query, {
                "postgres_id": postgres_id,
                "date": str(entry_date),
                "entry_type": entry_type,
                "category": category,
                "severity": severity,
                "summary": summary,
                "tags": tags or []
            })
            
            return result["id"] if result else None
        except Exception as e:
            logger.error(f"Failed to create LogEntry node: {e}")
            return None
    
    def link_to_workout(
        self,
        log_entry_id: str,
        workout_id: str,
        relationship_type: str = "EXPLAINS"
    ) -> bool:
        """Link a LogEntry to a Workout/EnduranceWorkout/StrengthWorkout."""
        
        query = f"""
        MATCH (le:LogEntry {{id: $log_entry_id}})
        MATCH (w) WHERE w.id = $workout_id 
          AND (w:Workout OR w:EnduranceWorkout OR w:StrengthWorkout)
        MERGE (le)-[:{relationship_type}]->(w)
        RETURN le.id as log_id, w.id as workout_id
        """
        
        result = self._execute_single(query, {
            "log_entry_id": log_entry_id,
            "workout_id": workout_id
        })
        
        return result is not None
    
    def link_to_plan(
        self,
        log_entry_id: str,
        plan_id: str
    ) -> bool:
        """Link a LogEntry to a PlannedWorkout (entry affects future plan)."""
        
        query = """
        MATCH (le:LogEntry {id: $log_entry_id})
        MATCH (p:PlannedWorkout {plan_id: $plan_id})
        MERGE (le)-[:AFFECTS]->(p)
        RETURN le.id as log_id, p.plan_id as plan_id
        """
        
        result = self._execute_single(query, {
            "log_entry_id": log_entry_id,
            "plan_id": plan_id
        })
        
        return result is not None
    
    def link_to_injury(
        self,
        log_entry_id: str,
        injury_id: str
    ) -> bool:
        """Link a LogEntry to an Injury."""
        
        query = """
        MATCH (le:LogEntry {id: $log_entry_id})
        MATCH (i:Injury {id: $injury_id})
        MERGE (le)-[:RELATED_TO]->(i)
        RETURN le.id as log_id, i.id as injury_id
        """
        
        result = self._execute_single(query, {
            "log_entry_id": log_entry_id,
            "injury_id": injury_id
        })
        
        return result is not None
    
    def link_to_goal(
        self,
        log_entry_id: str,
        goal_id: str
    ) -> bool:
        """Link a LogEntry to a Goal."""
        
        query = """
        MATCH (le:LogEntry {id: $log_entry_id})
        MATCH (g:Goal {id: $goal_id})
        MERGE (le)-[:INFORMS]->(g)
        RETURN le.id as log_id, g.id as goal_id
        """
        
        result = self._execute_single(query, {
            "log_entry_id": log_entry_id,
            "goal_id": goal_id
        })
        
        return result is not None
    
    def get_entries_for_workout(self, workout_id: str) -> List[Dict]:
        """Get all LogEntries that EXPLAIN a workout."""
        
        query = """
        MATCH (le:LogEntry)-[:EXPLAINS]->(w)
        WHERE w.id = $workout_id
        RETURN le.id as id,
               le.postgres_id as postgres_id,
               le.date as date,
               le.entry_type as entry_type,
               le.severity as severity,
               le.summary as summary
        ORDER BY le.date DESC
        """
        
        return self._execute(query, {"workout_id": workout_id})
    
    def get_entries_for_injury(self, injury_id: str) -> List[Dict]:
        """Get all LogEntries related to an injury."""
        
        query = """
        MATCH (le:LogEntry)-[:RELATED_TO]->(i:Injury {id: $injury_id})
        RETURN le.id as id,
               le.postgres_id as postgres_id,
               le.date as date,
               le.entry_type as entry_type,
               le.severity as severity,
               le.summary as summary
        ORDER BY le.date DESC
        """
        
        return self._execute(query, {"injury_id": injury_id})
    
    def get_entries_for_date_with_relationships(self, target_date: date) -> List[Dict]:
        """Get LogEntries for a date with their relationships."""
        
        query = """
        MATCH (le:LogEntry)
        WHERE le.date = date($date)
        OPTIONAL MATCH (le)-[r]->(related)
        RETURN le.id as id,
               le.postgres_id as postgres_id,
               le.entry_type as entry_type,
               le.severity as severity,
               le.summary as summary,
               collect({
                   type: type(r),
                   target_type: labels(related)[0],
                   target_id: related.id,
                   target_name: coalesce(related.name, related.goal, related.summary)
               }) as relationships
        """
        
        return self._execute(query, {"date": str(target_date)})
    
    def find_workout_by_date(
        self, 
        target_date: date,
        workout_type: Optional[str] = None
    ) -> List[Dict]:
        """Find workouts on a date to link entries to."""
        
        if workout_type == "endurance":
            label = "EnduranceWorkout"
        elif workout_type == "strength":
            label = "StrengthWorkout"
        else:
            label = None
        
        if label:
            query = f"""
            MATCH (w:{label})
            WHERE w.date = date($date)
            RETURN w.id as id,
                   labels(w)[0] as type,
                   w.name as name,
                   w.postgres_id as postgres_id
            """
        else:
            query = """
            MATCH (w)
            WHERE w.date = date($date)
              AND (w:Workout OR w:EnduranceWorkout OR w:StrengthWorkout)
            RETURN w.id as id,
                   labels(w)[0] as type,
                   w.name as name,
                   w.postgres_id as postgres_id
            """
        
        return self._execute(query, {"date": str(target_date)})
    
    def get_active_injuries(self) -> List[Dict]:
        """Get active injuries for linking."""
        
        query = """
        MATCH (i:Injury)
        WHERE i.status = 'active' OR i.resolved_date IS NULL
        RETURN i.id as id,
               i.name as name,
               i.body_part as body_part,
               i.onset_date as onset_date
        ORDER BY i.onset_date DESC
        """
        
        return self._execute(query)
    
    def get_active_goals(self) -> List[Dict]:
        """Get active goals for linking."""
        
        query = """
        MATCH (g:Goal)
        WHERE g.status = 'active'
        RETURN g.id as id,
               g.goal as name,
               g.target_date as target_date
        ORDER BY g.target_date
        """
        
        return self._execute(query)
    
    def close(self):
        """Close the Neo4j driver."""
        if self._driver:
            self._driver.close()
