"""Postgres client for Arnold Journal MCP - handles facts/measurements."""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import json

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PostgresJournalClient:
    """Client for journal fact storage in Postgres."""
    
    def __init__(self):
        self.dsn = os.environ.get(
            "POSTGRES_DSN", 
            "postgresql://brock@localhost:5432/arnold_analytics"
        )
        self._conn = None
    
    def _get_connection(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
        return self._conn
    
    def _execute(self, query: str, params: tuple = None, fetch: bool = True) -> Optional[List[Dict]]:
        """Execute a query and optionally fetch results."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch:
                    return [dict(row) for row in cur.fetchall()]
                conn.commit()
                return None
        except Exception as e:
            conn.rollback()
            logger.error(f"Query failed: {e}")
            raise
    
    def _execute_returning(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Execute a query and return the first row (for INSERT RETURNING)."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()
                return dict(result) if result else None
        except Exception as e:
            conn.rollback()
            logger.error(f"Query failed: {e}")
            raise
    
    def create_entry(
        self,
        entry_date: date,
        entry_type: str,
        raw_text: str,
        category: Optional[str] = None,
        severity: str = "info",
        extracted: Optional[Dict] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source: str = "chat"
    ) -> Dict:
        """Create a new journal entry (facts only - relationships in Neo4j)."""
        
        query = """
        INSERT INTO log_entries (
            entry_date, entry_type, raw_text, category, severity,
            extracted, summary, tags, source
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id, entry_date, entry_type, category, severity, summary, tags
        """
        
        return self._execute_returning(query, (
            entry_date,
            entry_type,
            raw_text,
            category,
            severity,
            json.dumps(extracted) if extracted else None,
            summary,
            tags,
            source
        ))
    
    def get_recent_entries(self, days_back: int = 7) -> List[Dict]:
        """Get recent journal entries."""
        return self._execute(
            "SELECT * FROM recent_log_entries(%s)",
            (days_back,)
        )
    
    def get_unreviewed_entries(self) -> List[Dict]:
        """Get entries that haven't been reviewed."""
        return self._execute("SELECT * FROM unreviewed_entries()")
    
    def get_entries_by_severity(self, min_severity: str = "notable") -> List[Dict]:
        """Get entries at or above a severity level."""
        return self._execute(
            "SELECT * FROM entries_by_severity(%s)",
            (min_severity,)
        )
    
    def get_entries_for_date(self, target_date: date) -> List[Dict]:
        """Get all entries for a specific date."""
        return self._execute(
            """
            SELECT id, entry_date, entry_type, category, severity, 
                   summary, raw_text, extracted, tags, reviewed, neo4j_id
            FROM log_entries 
            WHERE entry_date = %s
            ORDER BY recorded_at DESC
            """,
            (target_date,)
        )
    
    def get_entry_by_id(self, entry_id: int) -> Optional[Dict]:
        """Get a single entry by ID."""
        results = self._execute(
            "SELECT * FROM log_entries WHERE id = %s",
            (entry_id,)
        )
        return results[0] if results else None
    
    def update_entry(
        self,
        entry_id: int,
        extracted: Optional[Dict] = None,
        summary: Optional[str] = None,
        severity: Optional[str] = None,
        tags: Optional[List[str]] = None,
        neo4j_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Update an existing entry."""
        
        updates = []
        params = []
        
        if extracted is not None:
            updates.append("extracted = %s")
            params.append(json.dumps(extracted))
        if summary is not None:
            updates.append("summary = %s")
            params.append(summary)
        if severity is not None:
            updates.append("severity = %s")
            params.append(severity)
        if tags is not None:
            updates.append("tags = %s")
            params.append(tags)
        if neo4j_id is not None:
            updates.append("neo4j_id = %s")
            params.append(neo4j_id)
        
        if not updates:
            return self.get_entry_by_id(entry_id)
        
        updates.append("updated_at = NOW()")
        params.append(entry_id)
        
        query = f"""
        UPDATE log_entries 
        SET {', '.join(updates)}
        WHERE id = %s
        RETURNING id, entry_date, entry_type, category, severity, summary, tags, neo4j_id
        """
        
        return self._execute_returning(query, tuple(params))
    
    def mark_reviewed(self, entry_id: int, notes: Optional[str] = None) -> bool:
        """Mark an entry as reviewed."""
        result = self._execute(
            "SELECT mark_reviewed(%s, %s)",
            (entry_id, notes),
            fetch=True
        )
        return result[0]['mark_reviewed'] if result else False
    
    def search_entries(
        self,
        tags: Optional[List[str]] = None,
        entry_type: Optional[str] = None,
        category: Optional[str] = None,
        days_back: int = 30
    ) -> List[Dict]:
        """Search entries with filters."""
        
        conditions = ["entry_date >= CURRENT_DATE - %s"]
        params = [days_back]
        
        if tags:
            conditions.append("tags && %s")
            params.append(tags)
        if entry_type:
            conditions.append("entry_type = %s")
            params.append(entry_type)
        if category:
            conditions.append("category = %s")
            params.append(category)
        
        query = f"""
        SELECT id, entry_date, entry_type, category, severity, 
               summary, tags, reviewed, neo4j_id
        FROM log_entries
        WHERE {' AND '.join(conditions)}
        ORDER BY entry_date DESC, recorded_at DESC
        """
        
        return self._execute(query, tuple(params))
    
    def close(self):
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
    
    # =========================================================================
    # DATA ANNOTATIONS (for explaining data gaps/anomalies)
    # =========================================================================
    
    def create_annotation(
        self,
        annotation_date: date,
        target_type: str,
        reason_code: str,
        explanation: str,
        date_range_end: Optional[date] = None,
        target_metric: Optional[str] = None,
        target_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict:
        """Create a data annotation explaining a data gap or anomaly.
        
        Args:
            annotation_date: Start date of the period being explained
            target_type: Type of data (biometric, training, general)
            reason_code: Why the anomaly exists (expected, device_issue, surgery, etc.)
            explanation: Human-readable explanation
            date_range_end: End date if annotation covers a range
            target_metric: Specific metric (hrv, sleep, all, etc.)
            target_id: Optional ID of specific record
            tags: Optional tags for retrieval
        
        Returns:
            The created annotation record
        """
        query = """
        INSERT INTO data_annotations (
            annotation_date, date_range_end, target_type, target_metric,
            target_id, reason_code, explanation, tags, created_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, 'arnold'
        )
        RETURNING id, annotation_date, date_range_end, target_type, target_metric,
                  reason_code, explanation, tags, is_active
        """
        
        return self._execute_returning(query, (
            annotation_date,
            date_range_end,
            target_type,
            target_metric,
            target_id,
            reason_code,
            explanation,
            tags
        ))
    
    def get_active_annotations(self, days_back: int = 30) -> List[Dict]:
        """Get active annotations from recent period."""
        return self._execute(
            """
            SELECT id, annotation_date, date_range_end, target_type, target_metric,
                   reason_code, explanation, tags
            FROM data_annotations
            WHERE is_active = true
              AND (date_range_end IS NULL OR date_range_end >= CURRENT_DATE - %s)
            ORDER BY annotation_date DESC
            """,
            (days_back,)
        )
    
    def deactivate_annotation(self, annotation_id: int) -> bool:
        """Mark an annotation as inactive (resolved)."""
        self._execute(
            "UPDATE data_annotations SET is_active = false WHERE id = %s",
            (annotation_id,),
            fetch=False
        )
        return True
