"""
Final simple custom exercise mapper using GPT-5.2
Maps customs to canonicals OR assigns muscles from LLM knowledge
"""

from neo4j import GraphDatabase
from openai import OpenAI
import os
from dotenv import load_dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "arnold")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

MODEL = "gpt-5.2"
NUM_WORKERS = 6

class FinalCustomMapper:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.canonicals = self._load_canonicals()

    def close(self):
        self.driver.close()

    def _load_canonicals(self):
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (ex:Exercise)-[:SOURCED_FROM]->()
                RETURN ex.id as id, ex.name as name
            """)
            canonicals = [dict(r) for r in result]
            print(f"Loaded {len(canonicals)} canonical exercises")
            return canonicals

    def map_all(self):
        print(f"\n🔄 Final Custom Exercise Mapping")
        print(f"   Model: {MODEL}")
        print(f"   Workers: {NUM_WORKERS}\n")

        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (ex:Exercise)
                WHERE ex.id STARTS WITH 'CUSTOM:'
                RETURN ex.id as id, ex.name as name
            """)
            customs = [dict(r) for r in result]

        print(f"Processing {len(customs)} custom exercises...\n")

        with self.driver.session(database=NEO4J_DATABASE) as session:
            session.run("""
                MATCH (custom:Exercise)-[m:MAPS_TO]->()
                WHERE custom.id STARTS WITH 'CUSTOM:'
                DELETE m
            """)
            session.run("""
                MATCH (custom:Exercise)-[t:TARGETS]->()
                WHERE custom.id STARTS WITH 'CUSTOM:' AND t.llm_assigned = true
                DELETE t
            """)

        mapped_canonical = 0
        mapped_llm = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(self._map_one, custom): custom
                for custom in customs
            }

            with tqdm(total=len(customs), desc="Mapping") as pbar:
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result == "canonical":
                            mapped_canonical += 1
                        elif result == "llm":
                            mapped_llm += 1
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1
                    pbar.update(1)

        print(f"\n✅ Mapped to canonicals: {mapped_canonical}")
        print(f"✅ Mapped via LLM knowledge: {mapped_llm}")
        print(f"⚠️  Failed: {failed}")
        print(f"📊 Total coverage: {mapped_canonical + mapped_llm}/{len(customs)} ({100*(mapped_canonical + mapped_llm)/len(customs):.1f}%)")

    def _map_one(self, custom):
        mapping = self._llm_process(custom["name"])

        if not mapping:
            return False

        if mapping.get("canonical_match"):
            canonical_name = mapping["canonical_match"]
            canonical = next((c for c in self.canonicals
                             if c["name"].lower() == canonical_name.lower()), None)

            if not canonical:
                canonical = next((c for c in self.canonicals
                                 if canonical_name.lower() in c["name"].lower()
                                 or c["name"].lower() in canonical_name.lower()), None)

            if canonical:
                with self.driver.session(database=NEO4J_DATABASE) as session:
                    session.run("""
                        MATCH (custom:Exercise {id: $custom_id})
                        MATCH (canonical:Exercise {id: $canonical_id})
                        MERGE (custom)-[m:MAPS_TO]->(canonical)
                        SET m.confidence = $confidence,
                            m.model = $model
                    """, custom_id=custom["id"], canonical_id=canonical["id"],
                        confidence=mapping.get("confidence", 0.8), model=MODEL)

                return "canonical"

        if mapping.get("primary_muscles") or mapping.get("secondary_muscles"):
            with self.driver.session(database=NEO4J_DATABASE) as session:
                for muscle_name in mapping.get("primary_muscles", []):
                    self._link_muscle(session, custom["id"], muscle_name, "primary")

                for muscle_name in mapping.get("secondary_muscles", []):
                    self._link_muscle(session, custom["id"], muscle_name, "secondary")

                session.run("""
                    MATCH (ex:Exercise {id: $id})
                    SET ex.llm_assigned_muscles = true,
                        ex.movement_pattern = $pattern,
                        ex.default_intensity = $intensity
                """, id=custom["id"],
                    pattern=mapping.get("movement_pattern"),
                    intensity=mapping.get("intensity", "moderate"))

            return "llm"

        return False

    def _llm_process(self, custom_name):
        canonical_names = '\n'.join([f"- {c['name']}" for c in self.canonicals])

        prompt = f"""You are an exercise expert. Process this user exercise log entry.

User logged: "{custom_name}"

Available canonical exercises (all {len(self.canonicals)}):
{canonical_names}

TASK:
1. Clean the name (remove warmup/finisher/cooldown tags, remove rep counts)
2. Match to canonical exercise if possible
3. If no match, use your exercise science knowledge to assign muscles

RULES:
- "1 mile run (final push)" = just "Running"
- "Band Dislocates" = "Band Shoulder Dislocates"
- "67 tire flips" = "Tire Flip" (ignore count)
- Default intensity to "moderate" (zone 2-3) if unknown
- Use common sense

Respond JSON only:
{{
  "cleaned_name": "Running",
  "canonical_match": "Running" or null,
  "confidence": 0.90,
  "primary_muscles": ["quadriceps", "hamstrings", "glutes"],
  "secondary_muscles": ["calves", "hip_flexors"],
  "movement_pattern": "locomotion",
  "intensity": "moderate"
}}
"""

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content[content.find("\n")+1:]
            if content.endswith("```"):
                content = content[:content.rfind("```")]

            return json.loads(content.strip())
        except Exception as e:
            return None

    def _link_muscle(self, session, exercise_id, muscle_name, role):
        result = session.run("""
            MATCH (m:Muscle)
            WHERE toLower(m.name) CONTAINS toLower($name)
            RETURN m.fma_id as id
            LIMIT 1
        """, name=muscle_name)

        record = result.single()

        if record:
            session.run("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (m:Muscle {fma_id: $muscle_id})
                MERGE (ex)-[t:TARGETS]->(m)
                SET t.role = $role,
                    t.llm_assigned = true,
                    t.model = $model
            """, ex_id=exercise_id, muscle_id=record["id"],
                role=role, model=MODEL)
            return

        result = session.run("""
            MATCH (mg:MuscleGroup)
            WHERE toLower(mg.name) CONTAINS toLower($name)
               OR toLower(mg.common_name) CONTAINS toLower($name)
            RETURN mg.id as id
            LIMIT 1
        """, name=muscle_name)

        record = result.single()

        if record:
            session.run("""
                MATCH (ex:Exercise {id: $ex_id})
                MATCH (mg:MuscleGroup {id: $mg_id})
                MERGE (ex)-[t:TARGETS]->(mg)
                SET t.role = $role,
                    t.llm_assigned = true,
                    t.model = $model
            """, ex_id=exercise_id, mg_id=record["id"],
                role=role, model=MODEL)

if __name__ == "__main__":
    mapper = FinalCustomMapper()
    try:
        mapper.map_all()
    finally:
        mapper.close()
