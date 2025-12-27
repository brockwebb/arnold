"""
Export Arnold kernel (shared knowledge) to Cypher files
Creates importable .cypher files for fresh Neo4j instances
"""

from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")

OUTPUT_DIR = "/Users/brock/Documents/GitHub/arnold/kernel"

class KernelExporter:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def close(self):
        self.driver.close()

    def export_all(self):
        """Export complete kernel"""

        print("🔄 Exporting Arnold Kernel...\n")

        self.export_constraints()
        self.export_reference_nodes()
        self.export_anatomy()
        self.export_exercise_sources()
        self.export_canonical_exercises()
        self.export_exercise_relationships()

        print(f"\n✅ Kernel exported to {OUTPUT_DIR}")
        print("\nImport order:")
        print("1. 01_constraints.cypher")
        print("2. 02_reference_nodes.cypher")
        print("3. 03_anatomy.cypher")
        print("4. 04_exercise_sources.cypher")
        print("5. 05_canonical_exercises.cypher")
        print("6. 06_exercise_relationships.cypher")

    def export_constraints(self):
        """Export database constraints"""

        cypher = """// Arnold Kernel: Database Constraints
// Run FIRST on fresh Neo4j instance

// Reference Node Constraints
CREATE CONSTRAINT energy_system_type IF NOT EXISTS FOR (es:EnergySystem) REQUIRE es.type IS UNIQUE;
CREATE CONSTRAINT observation_concept_loinc IF NOT EXISTS FOR (oc:ObservationConcept) REQUIRE oc.loinc_code IS UNIQUE;
CREATE CONSTRAINT equipment_category_id IF NOT EXISTS FOR (eq:EquipmentCategory) REQUIRE eq.id IS UNIQUE;
CREATE CONSTRAINT exercise_source_id IF NOT EXISTS FOR (src:ExerciseSource) REQUIRE src.id IS UNIQUE;

// Anatomy Constraints
CREATE CONSTRAINT muscle_fma_id IF NOT EXISTS FOR (m:Muscle) REQUIRE m.fma_id IS UNIQUE;
CREATE CONSTRAINT muscle_group_id IF NOT EXISTS FOR (mg:MuscleGroup) REQUIRE mg.id IS UNIQUE;
CREATE CONSTRAINT bodypart_uberon_id IF NOT EXISTS FOR (bp:BodyPart) REQUIRE bp.uberon_id IS UNIQUE;

// Exercise Constraints
CREATE CONSTRAINT exercise_id IF NOT EXISTS FOR (ex:Exercise) REQUIRE ex.id IS UNIQUE;

// Person/Role Constraints (for future use)
CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT athlete_id IF NOT EXISTS FOR (a:Athlete) REQUIRE a.id IS UNIQUE;
"""

        with open(f"{OUTPUT_DIR}/01_constraints.cypher", 'w') as f:
            f.write(cypher)

        print("✓ Exported constraints")

    def export_reference_nodes(self):
        """Export EnergySystem, ObservationConcept, EquipmentCategory"""

        with self.driver.session(database=NEO4J_DATABASE) as session:

            cypher = "// Arnold Kernel: Reference Nodes\n// Scientific concepts and standards\n\n"

            # Energy Systems
            cypher += "// ===== ENERGY SYSTEMS (Margaria-Morton Model) =====\n"
            result = session.run("MATCH (es:EnergySystem) RETURN es ORDER BY es.type")
            for record in result:
                es = record["es"]
                cypher += f"""
MERGE (es:EnergySystem {{type: "{es['type']}"}})
SET es.description = "{es.get('description', '')}",
    es.metabolic_pathway = "{es.get('metabolic_pathway', '')}",
    es.time_domain = "{es.get('time_domain', '')}",
    es.paper_reference = "{es.get('paper_reference', '')}";
"""

            # Observation Concepts
            cypher += "\n// ===== OBSERVATION CONCEPTS (LOINC) =====\n"
            result = session.run("MATCH (oc:ObservationConcept) RETURN oc ORDER BY oc.loinc_code")
            for record in result:
                oc = record["oc"]
                cypher += f"""
MERGE (oc:ObservationConcept {{loinc_code: "{oc['loinc_code']}"}})
SET oc.friendly_name = "{oc.get('friendly_name', '')}",
    oc.display_name = "{oc.get('display_name', '')}",
    oc.unit = "{oc.get('unit', '')}",
    oc.category = "{oc.get('category', '')}";
"""

            # Equipment Categories
            cypher += "\n// ===== EQUIPMENT CATEGORIES =====\n"
            result = session.run("MATCH (eq:EquipmentCategory) RETURN eq ORDER BY eq.id")
            for record in result:
                eq = record["eq"]
                cypher += f"""
MERGE (eq:EquipmentCategory {{id: "{eq['id']}"}})
SET eq.name = "{eq.get('name', '')}";
"""

        with open(f"{OUTPUT_DIR}/02_reference_nodes.cypher", 'w') as f:
            f.write(cypher)

        print("✓ Exported reference nodes")

    def export_anatomy(self):
        """Export FMA anatomy nodes"""

        with self.driver.session(database=NEO4J_DATABASE) as session:

            cypher = "// Arnold Kernel: Anatomy (FMA)\n\n"

            # Muscles
            cypher += "// ===== MUSCLES =====\n"
            result = session.run("MATCH (m:Muscle) RETURN m ORDER BY m.fma_id")
            for record in result:
                m = record["m"]
                name = m.get('name', '').replace('"', '\\"')
                cypher += f'MERGE (m:Muscle {{fma_id: "{m["fma_id"]}"}})\nSET m.name = "{name}";\n'

            # MuscleGroups
            cypher += "\n// ===== MUSCLE GROUPS =====\n"
            result = session.run("MATCH (mg:MuscleGroup) RETURN mg ORDER BY mg.id")
            for record in result:
                mg = record["mg"]
                name = mg.get('name', '').replace('"', '\\"')
                common = mg.get('common_name', '').replace('"', '\\"')
                cypher += f'MERGE (mg:MuscleGroup {{id: "{mg["id"]}"}})\nSET mg.name = "{name}", mg.common_name = "{common}";\n'

            # BodyParts
            cypher += "\n// ===== BODY PARTS =====\n"
            result = session.run("MATCH (bp:BodyPart) RETURN bp ORDER BY bp.uberon_id")
            for record in result:
                bp = record["bp"]
                name = bp.get('name', '').replace('"', '\\"')
                cypher += f'MERGE (bp:BodyPart {{uberon_id: "{bp.get("uberon_id", "")}"}})\nSET bp.name = "{name}";\n'

            # MuscleGroup → Muscle relationships
            cypher += "\n// ===== MUSCLE GROUP RELATIONSHIPS =====\n"
            result = session.run("""
                MATCH (mg:MuscleGroup)-[:INCLUDES]->(m:Muscle)
                RETURN mg.id as mg_id, m.fma_id as muscle_fma_id
            """)
            for record in result:
                cypher += f'MATCH (mg:MuscleGroup {{id: "{record["mg_id"]}"}}), (m:Muscle {{fma_id: "{record["muscle_fma_id"]}"}})\nMERGE (mg)-[:INCLUDES]->(m);\n'

            # BodyPart hierarchy
            cypher += "\n// ===== ANATOMY HIERARCHY =====\n"
            result = session.run("""
                MATCH (parent)-[r:IS_A]->(child)
                WHERE parent:BodyPart OR parent:Muscle
                RETURN parent, type(r) as rel_type, child
                LIMIT 100
            """)
            for record in result:
                parent_label = list(record["parent"].labels)[0]
                child_label = list(record["child"].labels)[0]
                parent_id = record["parent"].get("uberon_id") or record["parent"].get("fma_id")
                child_id = record["child"].get("uberon_id") or record["child"].get("fma_id")
                if parent_id and child_id:
                    id_field_parent = "fma_id" if parent_label == "Muscle" else "uberon_id"
                    id_field_child = "fma_id" if child_label == "Muscle" else "uberon_id"
                    cypher += f'MATCH (p:{parent_label} {{{id_field_parent}: "{parent_id}"}}), (c:{child_label} {{{id_field_child}: "{child_id}"}}) MERGE (p)-[:IS_A]->(c);\n'

        with open(f"{OUTPUT_DIR}/03_anatomy.cypher", 'w') as f:
            f.write(cypher)

        print("✓ Exported anatomy")

    def export_exercise_sources(self):
        """Export ExerciseSource nodes"""

        with self.driver.session(database=NEO4J_DATABASE) as session:
            cypher = "// Arnold Kernel: Exercise Sources\n\n"

            result = session.run("MATCH (src:ExerciseSource) RETURN src ORDER BY src.id")
            for record in result:
                src = record["src"]
                name = src.get('name', '').replace('"', '\\"')
                url = src.get('url', '').replace('"', '\\"')
                desc = src.get('description', '').replace('"', '\\"')
                short_name = src.get('short_name', '').replace('"', '\\"')
                cypher += f"""
MERGE (src:ExerciseSource {{id: "{src['id']}"}})
SET src.name = "{name}",
    src.short_name = "{short_name}",
    src.license = "{src.get('license', '')}",
    src.url = "{url}",
    src.version = "{src.get('version', '')}",
    src.description = "{desc}";
"""

        with open(f"{OUTPUT_DIR}/04_exercise_sources.cypher", 'w') as f:
            f.write(cypher)

        print("✓ Exported exercise sources")

    def export_canonical_exercises(self):
        """Export canonical exercises (FEDB + FFDB)"""

        with self.driver.session(database=NEO4J_DATABASE) as session:
            cypher = "// Arnold Kernel: Canonical Exercises\n// WARNING: Large file (~5000 exercises)\n\n"

            result = session.run("""
                MATCH (ex:Exercise)-[:SOURCED_FROM]->(src:ExerciseSource)
                RETURN ex.id as id, ex.name as name, ex.source as source,
                       ex.category as category, ex.difficulty as difficulty,
                       ex.is_canonical as is_canonical,
                       ex.body_region as body_region, ex.mechanics as mechanics,
                       ex.force_type as force_type
                ORDER BY ex.id
            """)

            count = 0
            for record in result:
                name = record["name"].replace('"', '\\"').replace("'", "\\'")
                category = (record.get("category") or "").replace('"', '\\"')
                difficulty = (record.get("difficulty") or "").replace('"', '\\"')
                body_region = (record.get("body_region") or "").replace('"', '\\"')
                mechanics = (record.get("mechanics") or "").replace('"', '\\"')
                force_type = (record.get("force_type") or "").replace('"', '\\"')

                cypher += f'MERGE (ex:Exercise {{id: "{record["id"]}"}})\n'
                cypher += f'SET ex.name = "{name}", ex.source = "{record["source"]}", ex.is_canonical = true'
                if category:
                    cypher += f', ex.category = "{category}"'
                if difficulty:
                    cypher += f', ex.difficulty = "{difficulty}"'
                if body_region:
                    cypher += f', ex.body_region = "{body_region}"'
                if mechanics:
                    cypher += f', ex.mechanics = "{mechanics}"'
                if force_type:
                    cypher += f', ex.force_type = "{force_type}"'
                cypher += ';\n'
                count += 1

            print(f"  ({count} exercises)")

        with open(f"{OUTPUT_DIR}/05_canonical_exercises.cypher", 'w') as f:
            f.write(cypher)

        print("✓ Exported canonical exercises")

    def export_exercise_relationships(self):
        """Export exercise relationships (SOURCED_FROM, TARGETS, SAME_AS, etc.)"""

        with self.driver.session(database=NEO4J_DATABASE) as session:
            cypher = "// Arnold Kernel: Exercise Relationships\n\n"

            # SOURCED_FROM
            cypher += "// ===== SOURCED_FROM =====\n"
            result = session.run("""
                MATCH (ex:Exercise)-[:SOURCED_FROM]->(src:ExerciseSource)
                RETURN ex.id as ex_id, src.id as src_id
            """)
            for record in result:
                cypher += f'MATCH (ex:Exercise {{id: "{record["ex_id"]}"}}), (src:ExerciseSource {{id: "{record["src_id"]}"}}) MERGE (ex)-[:SOURCED_FROM]->(src);\n'

            # TARGETS (Exercise → Muscle/MuscleGroup)
            cypher += "\n// ===== TARGETS (Exercise → Muscle) =====\n"
            result = session.run("""
                MATCH (ex:Exercise)-[t:TARGETS]->(m:Muscle)
                WHERE ex.source IN ['free-exercise-db', 'functional-fitness-db']
                RETURN ex.id as ex_id, m.fma_id as muscle_fma_id, t.role as role
            """)
            for record in result:
                role = record.get("role", "primary")
                cypher += f'MATCH (ex:Exercise {{id: "{record["ex_id"]}"}}), (m:Muscle {{fma_id: "{record["muscle_fma_id"]}"}}) MERGE (ex)-[:TARGETS {{role: "{role}"}}]->(m);\n'

            cypher += "\n// ===== TARGETS (Exercise → MuscleGroup) =====\n"
            result = session.run("""
                MATCH (ex:Exercise)-[t:TARGETS]->(mg:MuscleGroup)
                WHERE ex.source IN ['free-exercise-db', 'functional-fitness-db']
                RETURN ex.id as ex_id, mg.id as mg_id, t.role as role
            """)
            for record in result:
                role = record.get("role", "primary")
                cypher += f'MATCH (ex:Exercise {{id: "{record["ex_id"]}"}}), (mg:MuscleGroup {{id: "{record["mg_id"]}"}}) MERGE (ex)-[:TARGETS {{role: "{role}"}}]->(mg);\n'

            # SAME_AS relationships
            cypher += "\n// ===== SAME_AS (Cross-source duplicates) =====\n"
            result = session.run("""
                MATCH (ex1:Exercise)-[s:SAME_AS]->(ex2:Exercise)
                WHERE ex1.id < ex2.id
                RETURN ex1.id as ex1_id, ex2.id as ex2_id, s.confidence as confidence
            """)
            for record in result:
                conf = record.get("confidence", 0.8)
                cypher += f'MATCH (ex1:Exercise {{id: "{record["ex1_id"]}"}}), (ex2:Exercise {{id: "{record["ex2_id"]}"}}) MERGE (ex1)-[:SAME_AS {{confidence: {conf}}}]->(ex2) MERGE (ex2)-[:SAME_AS {{confidence: {conf}}}]->(ex1);\n'

            # HIGHER_QUALITY_THAN
            cypher += "\n// ===== HIGHER_QUALITY_THAN =====\n"
            result = session.run("""
                MATCH (better:Exercise)-[h:HIGHER_QUALITY_THAN]->(worse:Exercise)
                RETURN better.id as better_id, worse.id as worse_id, h.reasoning as reasoning, h.confidence as confidence
            """)
            for record in result:
                reasoning = (record.get("reasoning") or "").replace('"', '\\"').replace('\n', ' ')
                conf = record.get("confidence", 0.8)
                cypher += f'MATCH (better:Exercise {{id: "{record["better_id"]}"}}), (worse:Exercise {{id: "{record["worse_id"]}"}}) MERGE (better)-[:HIGHER_QUALITY_THAN {{reasoning: "{reasoning}", confidence: {conf}}}]->(worse);\n'

        with open(f"{OUTPUT_DIR}/06_exercise_relationships.cypher", 'w') as f:
            f.write(cypher)

        print("✓ Exported exercise relationships")

if __name__ == "__main__":
    exporter = KernelExporter()
    try:
        exporter.export_all()
    finally:
        exporter.close()
