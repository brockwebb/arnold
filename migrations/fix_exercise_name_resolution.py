#!/usr/bin/env python3
"""
Fix #41: Ensure exercise_name is resolved from exercise_id during workout logging

Run with: python migrations/fix_exercise_name_resolution.py
"""

import re

NEO4J_CLIENT = "/Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp/arnold_training_mcp/neo4j_client.py"
SERVER = "/Users/brock/Documents/GitHub/arnold/src/arnold-training-mcp/arnold_training_mcp/server.py"

def add_neo4j_lookup():
    """Add get_exercise_by_id to neo4j_client.py"""
    
    new_method = '''
    def get_exercise_by_id(self, exercise_id: str) -> dict | None:
        """Get exercise name by ID. Used to resolve missing names during logging."""
        if not exercise_id:
            return None
        query = """
        MATCH (e:Exercise {exercise_id: $exercise_id})
        RETURN e.name as name, e.exercise_id as exercise_id
        LIMIT 1
        """
        with self.driver.session() as session:
            result = session.run(query, exercise_id=exercise_id)
            record = result.single()
            return dict(record) if record else None
'''
    
    with open(NEO4J_CLIENT, 'r') as f:
        content = f.read()
    
    # Check if already exists
    if 'get_exercise_by_id' in content:
        print("  get_exercise_by_id already exists in neo4j_client.py")
        return False
    
    # Find search_exercises method and add after it
    # Look for the end of search_exercises (next def or end of class)
    pattern = r'(def search_exercises\(self.*?)((?=\n    def |\nclass |\Z))'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("  ERROR: Could not find search_exercises method")
        return False
    
    # Insert after search_exercises
    insert_pos = match.end(1)
    new_content = content[:insert_pos] + new_method + content[insert_pos:]
    
    with open(NEO4J_CLIENT, 'w') as f:
        f.write(new_content)
    
    print("  Added get_exercise_by_id to neo4j_client.py")
    return True


def add_server_helper():
    """Add helper function and apply to server.py"""
    
    helper_function = '''
def ensure_exercise_name(exercise_id: str | None, exercise_name: str | None, neo4j_client) -> str:
    """Resolve exercise_name from Neo4j if missing but exercise_id exists."""
    if exercise_name:
        return exercise_name
    if not exercise_id:
        return "Unknown"
    result = neo4j_client.get_exercise_by_id(exercise_id)
    return result['name'] if result else exercise_id


'''
    
    with open(SERVER, 'r') as f:
        content = f.read()
    
    # Check if already exists
    if 'def ensure_exercise_name' in content:
        print("  ensure_exercise_name already exists in server.py")
        return False
    
    # Add helper after imports (find the get_person_id function and add before it)
    pattern = r'(def get_person_id\(\))'
    match = re.search(pattern, content)
    
    if not match:
        print("  ERROR: Could not find insertion point")
        return False
    
    insert_pos = match.start()
    content = content[:insert_pos] + helper_function + content[insert_pos:]
    
    # Now apply the helper - replace s.get('exercise_name') with ensure call
    # Pattern: 'exercise_name': s.get('exercise_name'),
    old_pattern = r"'exercise_name': s\.get\('exercise_name'\),"
    new_value = "'exercise_name': ensure_exercise_name(s.get('exercise_id'), s.get('exercise_name'), neo4j_client),"
    
    count = len(re.findall(old_pattern, content))
    content = re.sub(old_pattern, new_value, content)
    
    with open(SERVER, 'w') as f:
        f.write(content)
    
    print(f"  Added ensure_exercise_name helper to server.py")
    print(f"  Replaced {count} occurrences of exercise_name assignment")
    return True


def main():
    print("Fix #41: exercise_name resolution\n")
    
    print("[1/2] Updating neo4j_client.py...")
    add_neo4j_lookup()
    
    print("[2/2] Updating server.py...")
    add_server_helper()
    
    print("\nDone! Restart training-mcp to apply.")
    print("Test with: Create a plan, complete it, verify exercise names are populated.")


if __name__ == "__main__":
    main()
