#!/usr/bin/env python3
"""
Import user profile and equipment into Arnold graph.

This script:
1. Reads user profile YAML
2. Creates Goal nodes
3. Creates Injury and Constraint nodes
4. Updates Equipment nodes with user_has=true
5. Creates injury-exercise constraint relationships

Usage:
    python scripts/import_user_profile.py
    python scripts/import_user_profile.py --profile path/to/profile.yaml
"""

import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph


def load_arnold_config():
    """Load Arnold configuration."""
    config_path = Path(__file__).parent.parent / "config" / "arnold.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_user_profile(profile_path: Path) -> dict:
    """Load user profile YAML."""
    with open(profile_path) as f:
        return yaml.safe_load(f)


def import_goals(profile: dict, graph: ArnoldGraph):
    """Import user goals as Goal nodes."""
    print("\nImporting goals...")

    goals_imported = 0

    # Short-term goals
    for goal in profile.get('goals', {}).get('short_term', []):
        goal_id = f"GOAL:{goal.upper()}"
        query = """
        MERGE (g:Goal {id: $id})
        SET g.description = $description,
            g.goal_type = 'short_term',
            g.status = 'active'
        """
        graph.execute_write(query, {
            'id': goal_id,
            'description': goal.replace('_', ' ').title()
        })
        goals_imported += 1

    # Long-term goals
    for goal in profile.get('goals', {}).get('long_term', []):
        goal_id = f"GOAL:{goal.upper()}"
        query = """
        MERGE (g:Goal {id: $id})
        SET g.description = $description,
            g.goal_type = 'long_term',
            g.status = 'active'
        """
        graph.execute_write(query, {
            'id': goal_id,
            'description': goal.replace('_', ' ').title()
        })
        goals_imported += 1

    print(f"  ✓ Imported {goals_imported} goals")


def import_injuries(profile: dict, graph: ArnoldGraph):
    """Import injuries and create constraints."""
    print("\nImporting injuries and constraints...")

    injuries = profile.get('injuries', [])
    injuries_imported = 0
    constraints_created = 0

    for injury_data in injuries:
        injury_id = f"INJURY:{injury_data['name'].upper()}"

        # Create injury node
        injury_params = {
            'id': injury_id,
            'name': injury_data['name'],
            'status': injury_data.get('status', 'active'),
            'notes': injury_data.get('notes', '')
        }

        if 'onset_date' in injury_data:
            injury_params['onset_date'] = str(injury_data['onset_date'])

        query = """
        MERGE (i:Injury {id: $id})
        SET i.name = $name,
            i.status = $status,
            i.notes = $notes
        """
        if 'onset_date' in injury_params:
            query += ", i.onset_date = date($onset_date)"

        graph.execute_write(query, injury_params)
        injuries_imported += 1

        # Create constraint nodes
        for constraint_desc in injury_data.get('constraints', []):
            constraint_id = f"CONSTRAINT:{injury_data['name'].upper()}_{constraint_desc.upper()}"

            query = """
            MERGE (c:Constraint {id: $id})
            SET c.description = $description,
                c.constraint_type = $constraint_type
            """
            # Determine constraint type
            constraint_type = 'avoid'
            if 'avoid' in constraint_desc.lower():
                constraint_type = 'avoid'
            elif 'reduce' in constraint_desc.lower() or 'limit' in constraint_desc.lower():
                constraint_type = 'limit'
            elif 'monitor' in constraint_desc.lower():
                constraint_type = 'monitor'
            elif 'prefer' in constraint_desc.lower():
                constraint_type = 'modify'

            graph.execute_write(query, {
                'id': constraint_id,
                'description': constraint_desc,
                'constraint_type': constraint_type
            })

            # Link injury to constraint
            query = """
            MATCH (i:Injury {id: $injury_id})
            MATCH (c:Constraint {id: $constraint_id})
            MERGE (i)-[:CREATES]->(c)
            """
            graph.execute_write(query, {
                'injury_id': injury_id,
                'constraint_id': constraint_id
            })

            constraints_created += 1

    print(f"  ✓ Imported {injuries_imported} injuries")
    print(f"  ✓ Created {constraints_created} constraints")


def import_equipment(profile: dict, graph: ArnoldGraph):
    """Mark user's equipment as owned."""
    print("\nImporting equipment...")

    equipment_marked = 0

    # Process different equipment categories
    equipment_data = profile.get('equipment', {})

    # Barbells
    for barbell in equipment_data.get('barbells', []):
        if barbell.get('owned'):
            equipment_id = f"EQUIPMENT:{barbell['name'].upper().replace(' ', '_')}"
            query = """
            MERGE (eq:Equipment {id: $id})
            SET eq.name = $name,
                eq.user_has = true,
                eq.category = 'barbell'
            """
            if 'weight_lbs' in barbell:
                query += ", eq.weight_lbs = $weight_lbs"

            graph.execute_write(query, {
                'id': equipment_id,
                'name': barbell['name'],
                'weight_lbs': barbell.get('weight_lbs')
            })
            equipment_marked += 1

    # Dumbbells
    for dumbbell_set in equipment_data.get('dumbbells', []):
        if dumbbell_set.get('owned'):
            equipment_id = "EQUIPMENT:DUMBBELL"
            query = """
            MERGE (eq:Equipment {id: $id})
            SET eq.name = 'dumbbell',
                eq.user_has = true,
                eq.category = 'dumbbell',
                eq.weights_available = $weights
            """
            graph.execute_write(query, {
                'id': equipment_id,
                'weights': dumbbell_set.get('weight_lbs', [])
            })
            equipment_marked += 1

    # Kettlebells
    for kb_set in equipment_data.get('kettlebells', []):
        if kb_set.get('owned'):
            equipment_id = "EQUIPMENT:KETTLEBELL"
            query = """
            MERGE (eq:Equipment {id: $id})
            SET eq.name = 'kettlebell',
                eq.user_has = true,
                eq.category = 'kettlebell',
                eq.weights_available = $weights
            """
            graph.execute_write(query, {
                'id': equipment_id,
                'weights': kb_set.get('weight_lbs', [])
            })
            equipment_marked += 1

    # Sandbags
    for sb_set in equipment_data.get('sandbags', []):
        if sb_set.get('owned'):
            equipment_id = "EQUIPMENT:SANDBAG"
            query = """
            MERGE (eq:Equipment {id: $id})
            SET eq.name = 'sandbag',
                eq.user_has = true,
                eq.category = 'sandbag',
                eq.weights_available = $weights
            """
            graph.execute_write(query, {
                'id': equipment_id,
                'weights': sb_set.get('weight_lbs', [])
            })
            equipment_marked += 1

    # Other equipment
    for item in equipment_data.get('other', []):
        if item.get('owned'):
            equipment_id = f"EQUIPMENT:{item['name'].upper().replace(' ', '_')}"
            query = """
            MERGE (eq:Equipment {id: $id})
            SET eq.name = $name,
                eq.user_has = true,
                eq.category = 'other'
            """
            if 'weight_lbs' in item:
                query += ", eq.weight_lbs = $weight_lbs"

            params = {
                'id': equipment_id,
                'name': item['name']
            }
            if 'weight_lbs' in item:
                params['weight_lbs'] = item['weight_lbs']

            graph.execute_write(query, params)
            equipment_marked += 1

    print(f"  ✓ Marked {equipment_marked} equipment items as owned")


def main():
    parser = argparse.ArgumentParser(description="Import user profile")
    parser.add_argument(
        "--profile",
        type=str,
        help="Path to user profile YAML file"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("User Profile Importer")
    print("=" * 60)

    # Determine profile path
    if args.profile:
        profile_path = Path(args.profile)
    else:
        config = load_arnold_config()
        profile_path = Path(config['user']['profile_path'])

    if not profile_path.exists():
        print(f"❌ Profile not found: {profile_path}")
        print("\nCreate a profile by copying the example:")
        print("  cp data/user/profile.yaml.example data/user/profile.yaml")
        sys.exit(1)

    print(f"Loading profile from: {profile_path}")

    # Load profile
    try:
        profile = load_user_profile(profile_path)
    except Exception as e:
        print(f"❌ Failed to load profile: {e}")
        sys.exit(1)

    # Connect to graph
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Import data
    import_goals(profile, graph)
    import_injuries(profile, graph)
    import_equipment(profile, graph)

    # Show statistics
    from arnold.graph import print_stats
    stats = graph.get_stats()
    print_stats(stats)

    graph.close()

    print("\n" + "=" * 60)
    print("✓ Profile import complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
