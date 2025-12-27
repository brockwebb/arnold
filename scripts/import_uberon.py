#!/usr/bin/env python3
"""
Import UBERON anatomy ontology into Arnold graph.

This script:
1. Downloads UBERON OBO file if not present
2. Parses the ontology to extract musculoskeletal structures
3. Creates Muscle, Joint, and Bone nodes
4. Creates anatomical relationships

Usage:
    python scripts/import_uberon.py
    python scripts/import_uberon.py --download  # Force re-download
"""

import sys
import argparse
import requests
import yaml
from pathlib import Path
from typing import Set

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arnold.graph import ArnoldGraph

try:
    import pronto
except ImportError:
    print("Error: pronto library not installed")
    print("Install with: pip install pronto")
    sys.exit(1)


def load_config():
    """Load Arnold configuration."""
    config_path = Path(__file__).parent.parent / "config" / "arnold.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def download_uberon(url: str, local_path: Path) -> bool:
    """Download UBERON OBO file."""
    print(f"Downloading UBERON from {url}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"✓ Downloaded to {local_path}")
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


def is_musculoskeletal(term: pronto.Term) -> tuple[bool, str]:
    """
    Determine if a term is musculoskeletal and categorize it.

    Returns:
        (is_relevant, category) where category is 'muscle', 'joint', 'bone', or None
    """
    name_lower = term.name.lower() if term.name else ""
    desc_lower = term.desc.lower() if term.desc else ""

    # Keywords for each category
    muscle_keywords = ['muscle', 'muscular']
    joint_keywords = ['joint', 'articulation']
    bone_keywords = ['bone', 'skeletal', 'vertebra', 'femur', 'tibia', 'humerus',
                     'radius', 'ulna', 'scapula', 'clavicle', 'pelvis', 'patella']

    # Check name and description
    text = f"{name_lower} {desc_lower}"

    if any(kw in text for kw in muscle_keywords):
        return True, 'muscle'
    elif any(kw in text for kw in joint_keywords):
        return True, 'joint'
    elif any(kw in text for kw in bone_keywords):
        return True, 'bone'

    # Check if it's part of musculoskeletal system via relationships
    for parent in term.superclasses():
        parent_name = parent.name.lower() if parent.name else ""
        if 'musculoskeletal' in parent_name or 'skeletal' in parent_name:
            # Default to bone if unclear
            return True, 'bone'

    return False, None


def import_uberon_to_graph(obo_path: Path, graph: ArnoldGraph):
    """Parse UBERON and import musculoskeletal structures."""
    print(f"\nLoading UBERON ontology from {obo_path}...")

    try:
        ontology = pronto.Ontology(str(obo_path))
    except Exception as e:
        print(f"❌ Failed to load ontology: {e}")
        return

    print(f"✓ Loaded {len(ontology)} terms")

    # Filter to musculoskeletal terms
    print("\nFiltering musculoskeletal terms...")
    muscles = []
    joints = []
    bones = []

    for term in ontology.terms():
        is_relevant, category = is_musculoskeletal(term)
        if is_relevant:
            node_data = {
                'id': term.id,
                'name': term.name or 'Unknown',
                'synonyms': [str(syn) for syn in term.synonyms] if term.synonyms else [],
            }

            if category == 'muscle':
                muscles.append(node_data)
            elif category == 'joint':
                joints.append(node_data)
            elif category == 'bone':
                bones.append(node_data)

    print(f"Found:")
    print(f"  Muscles: {len(muscles)}")
    print(f"  Joints: {len(joints)}")
    print(f"  Bones: {len(bones)}")

    # Import to Neo4j
    print("\nImporting to Neo4j...")

    # Import muscles
    if muscles:
        print(f"  Importing {len(muscles)} muscles...")
        for muscle in muscles:
            query = """
            MERGE (m:Muscle {id: $id})
            SET m.name = $name,
                m.synonyms = $synonyms,
                m.source = 'UBERON'
            """
            graph.execute_write(query, muscle)

    # Import joints
    if joints:
        print(f"  Importing {len(joints)} joints...")
        for joint in joints:
            query = """
            MERGE (j:Joint {id: $id})
            SET j.name = $name,
                j.synonyms = $synonyms,
                j.source = 'UBERON'
            """
            graph.execute_write(query, joint)

    # Import bones
    if bones:
        print(f"  Importing {len(bones)} bones...")
        for bone in bones:
            query = """
            MERGE (b:Bone {id: $id})
            SET b.name = $name,
                b.synonyms = $synonyms,
                b.source = 'UBERON'
            """
            graph.execute_write(query, bone)

    # Create relationships based on ontology structure
    print("\nCreating anatomical relationships...")
    rel_count = 0

    for term in ontology.terms():
        if term.id.startswith('UBERON:'):
            # part_of relationships
            for parent in term.superclasses(distance=1):
                if parent.id != term.id and parent.id.startswith('UBERON:'):
                    query = """
                    MATCH (child {id: $child_id})
                    MATCH (parent {id: $parent_id})
                    MERGE (child)-[:PART_OF]->(parent)
                    """
                    try:
                        graph.execute_write(query, {
                            'child_id': term.id,
                            'parent_id': parent.id
                        })
                        rel_count += 1
                    except:
                        pass  # Skip if nodes don't exist

    print(f"  Created {rel_count} PART_OF relationships")

    print("\n✓ UBERON import complete")


def main():
    parser = argparse.ArgumentParser(description="Import UBERON anatomy ontology")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Force re-download of UBERON file"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("UBERON Anatomy Importer")
    print("=" * 60)

    # Load configuration
    config = load_config()
    uberon_config = config['data_sources']['uberon']
    local_path = Path(uberon_config['local_path'])

    # Download if needed
    if args.download or not local_path.exists():
        if not download_uberon(uberon_config['url'], local_path):
            sys.exit(1)
    else:
        print(f"Using existing file: {local_path}")

    # Connect to graph
    print("\nConnecting to Neo4j...")
    graph = ArnoldGraph()
    if not graph.verify_connectivity():
        print("❌ Could not connect to Neo4j")
        sys.exit(1)
    print("✓ Connected")

    # Import
    import_uberon_to_graph(local_path, graph)

    # Show statistics
    from arnold.graph import print_stats
    stats = graph.get_stats()
    print_stats(stats)

    graph.close()

    print("\n" + "=" * 60)
    print("✓ Import complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
