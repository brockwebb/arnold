#!/usr/bin/env python3
"""Export muscle targeting relationships from Neo4j to CSV."""
import csv
from neo4j import GraphDatabase

# Connection details
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "i'llbeback"
DATABASE = "arnold"

OUTPUT_PATH = "/Users/brock/Documents/GitHub/arnold/data/staging/muscle_targeting.csv"

def export_muscle_targeting():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    query = """
    MATCH (e:Exercise)-[t:TARGETS]->(m:Muscle)
    RETURN e.id as exercise_id, m.name as muscle_name, t.role as target_role
    ORDER BY exercise_id, muscle_name
    """
    
    with driver.session(database=DATABASE) as session:
        result = session.run(query)
        records = list(result)
        
    driver.close()
    
    with open(OUTPUT_PATH, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['exercise_id', 'muscle_name', 'target_role'])
        for record in records:
            writer.writerow([record['exercise_id'], record['muscle_name'], record['target_role']])
    
    print(f"Exported {len(records)} rows to {OUTPUT_PATH}")

if __name__ == "__main__":
    export_muscle_targeting()
