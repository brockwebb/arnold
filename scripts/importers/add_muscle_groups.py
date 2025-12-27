#!/usr/bin/env python3
"""
Add 4 missing muscle groups that caused 496 failed exercise links
Creates MuscleGroup aggregation nodes
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from arnold.graph import ArnoldGraph
from dotenv import load_dotenv

load_dotenv()


class MuscleGroupCreator:
    def __init__(self):
        self.graph = ArnoldGraph()

    def close(self):
        self.graph.close()

    def create_muscle_groups(self):
        """Create 4 missing muscle groups and link to individual muscles"""

        print("Creating MuscleGroup nodes...")

        # 1. HAMSTRINGS
        self._create_hamstrings()

        # 2. QUADRICEPS
        self._create_quadriceps()

        # 3. FOREARMS
        self._create_forearms()

        # 4. ABDUCTORS
        self._create_abductors()

        # 5. ADDUCTORS
        self._create_adductors()

        # Verify creation
        result = self.graph.execute_query("""
            MATCH (mg:MuscleGroup)
            OPTIONAL MATCH (mg)-[:INCLUDES]->(m:Muscle)
            RETURN mg.name as group_name, count(m) as muscle_count
            ORDER BY group_name
        """)

        print("\n✅ Muscle Groups Created:")
        for record in result:
            print(f"  - {record['group_name']}: {record['muscle_count']} muscles")

    def _create_hamstrings(self):
        """Hamstrings = biceps femoris + semitendinosus + semimembranosus"""

        # Create MuscleGroup node
        self.graph.execute_query("""
            MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:hamstrings"})
            ON CREATE SET
                mg.name = "Hamstrings",
                mg.region = "posterior_thigh",
                mg.common_name = "hamstrings"
        """)

        # Link to individual muscles (fuzzy match from FMA)
        muscle_terms = ["biceps femoris", "semitendinosus", "semimembranosus"]

        for term in muscle_terms:
            result = self.graph.execute_query("""
                MATCH (m:Muscle)
                WHERE toLower(m.name) CONTAINS toLower($term)
                RETURN m.fma_id as fma_id, m.name as name
                LIMIT 1
            """, parameters={'term': term})

            if result:
                record = result[0]
                self.graph.execute_query("""
                    MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:hamstrings"})
                    MATCH (m:Muscle {fma_id: $fma_id})
                    MERGE (mg)-[:INCLUDES]->(m)
                """, parameters={'fma_id': record["fma_id"]})
                print(f"  ✓ Hamstrings includes: {record['name']}")

    def _create_quadriceps(self):
        """Quadriceps = 4 heads of quad"""

        self.graph.execute_query("""
            MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:quadriceps"})
            ON CREATE SET
                mg.name = "Quadriceps",
                mg.region = "anterior_thigh",
                mg.common_name = "quads"
        """)

        muscle_terms = ["vastus lateralis", "vastus medialis", "rectus femoris", "vastus intermedius"]

        for term in muscle_terms:
            result = self.graph.execute_query("""
                MATCH (m:Muscle)
                WHERE toLower(m.name) CONTAINS toLower($term)
                RETURN m.fma_id as fma_id, m.name as name
                LIMIT 1
            """, parameters={'term': term})

            if result:
                record = result[0]
                self.graph.execute_query("""
                    MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:quadriceps"})
                    MATCH (m:Muscle {fma_id: $fma_id})
                    MERGE (mg)-[:INCLUDES]->(m)
                """, parameters={'fma_id': record["fma_id"]})
                print(f"  ✓ Quadriceps includes: {record['name']}")

    def _create_forearms(self):
        """Forearms = flexors + extensors + brachioradialis"""

        self.graph.execute_query("""
            MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:forearms"})
            ON CREATE SET
                mg.name = "Forearms",
                mg.region = "forearm",
                mg.common_name = "forearms"
        """)

        muscle_terms = ["flexor carpi", "extensor carpi", "brachioradialis"]

        for term in muscle_terms:
            result = self.graph.execute_query("""
                MATCH (m:Muscle)
                WHERE toLower(m.name) CONTAINS toLower($term)
                RETURN m.fma_id as fma_id, m.name as name
            """, parameters={'term': term})

            for record in result:
                self.graph.execute_query("""
                    MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:forearms"})
                    MATCH (m:Muscle {fma_id: $fma_id})
                    MERGE (mg)-[:INCLUDES]->(m)
                """, parameters={'fma_id': record["fma_id"]})
                print(f"  ✓ Forearms includes: {record['name']}")

    def _create_abductors(self):
        """Hip abductors = gluteus medius + gluteus minimus + TFL"""

        self.graph.execute_query("""
            MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:abductors"})
            ON CREATE SET
                mg.name = "Hip Abductors",
                mg.region = "hip",
                mg.common_name = "abductors"
        """)

        muscle_terms = ["gluteus medius", "gluteus minimus", "tensor fasciae latae"]

        for term in muscle_terms:
            result = self.graph.execute_query("""
                MATCH (m:Muscle)
                WHERE toLower(m.name) CONTAINS toLower($term)
                RETURN m.fma_id as fma_id, m.name as name
                LIMIT 1
            """, parameters={'term': term})

            if result:
                record = result[0]
                self.graph.execute_query("""
                    MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:abductors"})
                    MATCH (m:Muscle {fma_id: $fma_id})
                    MERGE (mg)-[:INCLUDES]->(m)
                """, parameters={'fma_id': record["fma_id"]})
                print(f"  ✓ Abductors includes: {record['name']}")

    def _create_adductors(self):
        """Hip adductors = adductor longus + brevis + magnus"""

        self.graph.execute_query("""
            MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:adductors"})
            ON CREATE SET
                mg.name = "Hip Adductors",
                mg.region = "hip",
                mg.common_name = "adductors"
        """)

        muscle_terms = ["adductor longus", "adductor brevis", "adductor magnus"]

        for term in muscle_terms:
            result = self.graph.execute_query("""
                MATCH (m:Muscle)
                WHERE toLower(m.name) CONTAINS toLower($term)
                RETURN m.fma_id as fma_id, m.name as name
                LIMIT 1
            """, parameters={'term': term})

            if result:
                record = result[0]
                self.graph.execute_query("""
                    MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:adductors"})
                    MATCH (m:Muscle {fma_id: $fma_id})
                    MERGE (mg)-[:INCLUDES]->(m)
                """, parameters={'fma_id': record["fma_id"]})
                print(f"  ✓ Adductors includes: {record['name']}")

    def link_exercises_to_groups(self):
        """Update exercises that reference muscle groups to link properly"""

        print("\nLinking exercises to muscle groups...")

        # Find exercises that target "hamstrings" (string) and link to group
        self.graph.execute_query("""
            MATCH (mg:MuscleGroup {common_name: "hamstrings"})
            MATCH (ex:Exercise)
            WHERE NOT EXISTS((ex)-[:TARGETS]->(:Muscle))
              AND toLower(ex.name) CONTAINS 'hamstring'
            MERGE (ex)-[:TARGETS {
                role: "primary",
                llm_inferred: true,
                confidence: 0.9,
                human_verified: false
            }]->(mg)
        """)

        # Same for other groups
        for group_name in ["quadriceps", "forearms", "abductors", "adductors"]:
            common = group_name if group_name != "quadriceps" else "quad"
            self.graph.execute_query("""
                MATCH (mg:MuscleGroup {common_name: $common})
                MATCH (ex:Exercise)
                WHERE NOT EXISTS((ex)-[:TARGETS]->(:Muscle))
                  AND (toLower(ex.name) CONTAINS toLower($common)
                       OR toLower(ex.name) CONTAINS toLower($group_name))
                MERGE (ex)-[:TARGETS {
                    role: "primary",
                    llm_inferred: true,
                    confidence: 0.9,
                    human_verified: false
                }]->(mg)
            """, parameters={'common': common, 'group_name': group_name})

        print("✅ Exercises linked to muscle groups")


if __name__ == "__main__":
    print("Starting muscle group creation...")

    creator = MuscleGroupCreator()
    try:
        creator.create_muscle_groups()
        creator.link_exercises_to_groups()
    finally:
        creator.close()

    print("\n✅ Muscle group creation complete!")
