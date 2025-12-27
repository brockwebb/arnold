"""
Process the 102 failed exercises using Claude Sonnet 4.5
"""

from neo4j import GraphDatabase
from anthropic import Anthropic
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
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-5-20250929"
NUM_WORKERS = 6

class FailureRecoveryMapper:
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

    def map_failures(self):
        print(f"\n🔄 Failure Recovery with Claude Sonnet 4.5")
        print(f"   Model: {MODEL}")
        print(f"   Workers: {NUM_WORKERS}\n")

        # Get exercises that failed (no MAPS_TO and no llm_assigned_muscles)
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (ex:Exercise)
                WHERE ex.id STARTS WITH 'CUSTOM:'
                  AND NOT EXISTS {
                      MATCH (ex)-[:MAPS_TO]->()
                  }
                  AND (ex.llm_assigned_muscles IS NULL OR ex.llm_assigned_muscles = false)
                RETURN ex.id as id, ex.name as name
            """)
            failures = [dict(r) for r in result]

        print(f"Processing {len(failures)} failed exercises...\n")

        mapped_canonical = 0
        mapped_llm = 0
        still_failed = 0

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(self._map_one, ex): ex
                for ex in failures
            }

            with tqdm(total=len(failures), desc="Recovering") as pbar:
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result == "canonical":
                            mapped_canonical += 1
                        elif result == "llm":
                            mapped_llm += 1
                        else:
                            still_failed += 1
                    except Exception as e:
                        print(f"\n  ❌ Error: {e}")
                        still_failed += 1
                    pbar.update(1)

        print(f"\n✅ Recovered to canonicals: {mapped_canonical}")
        print(f"✅ Recovered via LLM knowledge: {mapped_llm}")
        print(f"⚠️  Still failed: {still_failed}")
        print(f"📊 Recovery rate: {mapped_canonical + mapped_llm}/{len(failures)} ({100*(mapped_canonical + mapped_llm)/len(failures) if failures else 0:.1f}%)")

        # Final totals
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (ex:Exercise)
                WHERE ex.id STARTS WITH 'CUSTOM:'
                WITH count(ex) as total
                MATCH (mapped:Exercise)
                WHERE mapped.id STARTS WITH 'CUSTOM:'
                  AND (EXISTS {MATCH (mapped)-[:MAPS_TO]->()}
                       OR mapped.llm_assigned_muscles = true)
                RETURN total, count(mapped) as mapped
            """)
            stats = result.single()
            total = stats['total']
            mapped = stats['mapped']

        print(f"\n📈 FINAL TOTALS:")
        print(f"   Total custom exercises: {total}")
        print(f"   Successfully mapped: {mapped}")
        print(f"   Failed: {total - mapped}")
        print(f"   **Final coverage: {100*mapped/total:.1f}%**")

    def _map_one(self, exercise):
        mapping = self._claude_process(exercise["name"])

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
                            m.model = $model,
                            m.recovery = true
                    """, custom_id=exercise["id"], canonical_id=canonical["id"],
                        confidence=mapping.get("confidence", 0.8), model=MODEL)

                return "canonical"

        if mapping.get("primary_muscles") or mapping.get("secondary_muscles"):
            with self.driver.session(database=NEO4J_DATABASE) as session:
                for muscle_name in mapping.get("primary_muscles", []):
                    self._link_muscle(session, exercise["id"], muscle_name, "primary")

                for muscle_name in mapping.get("secondary_muscles", []):
                    self._link_muscle(session, exercise["id"], muscle_name, "secondary")

                session.run("""
                    MATCH (ex:Exercise {id: $id})
                    SET ex.llm_assigned_muscles = true,
                        ex.movement_pattern = $pattern,
                        ex.default_intensity = $intensity,
                        ex.recovery_model = $model
                """, id=exercise["id"],
                    pattern=mapping.get("movement_pattern"),
                    intensity=mapping.get("intensity", "moderate"),
                    model=MODEL)

            return "llm"

        return False

    def _claude_process(self, custom_name):
        canonical_names = '\n'.join([f"- {c['name']}" for c in self.canonicals[:500]])

        prompt = f"""You are an exercise expert. This exercise failed to map with GPT-5.2. Please try again with your superior reasoning.

User logged: "{custom_name}"

Available canonical exercises (first 500 of {len(self.canonicals)}):
{canonical_names}

TASK:
1. Clean the name (remove tags, counts, warmup/cooldown markers)
2. Match to canonical if ANY reasonable match exists
3. If truly no match, use exercise science knowledge to assign muscles

EXAMPLES of what failed before:
- Warmup/cooldown activities
- Uncommon sports (rugby, ultimate frisbee)
- Yoga/mobility work
- Recovery activities

Be CREATIVE but ACCURATE. If it's a real exercise, assign muscles.

Respond JSON only:
{{
  "cleaned_name": "Running",
  "canonical_match": "Running" or null,
  "confidence": 0.90,
  "primary_muscles": ["quadriceps", "hamstrings", "glutes"],
  "secondary_muscles": ["calves"],
  "movement_pattern": "locomotion",
  "intensity": "moderate",
  "reasoning": "Brief explanation"
}}
"""

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            content = response.content[0].text.strip()

            # Remove markdown if present
            if content.startswith("```"):
                content = content[content.find("\n")+1:]
            if content.endswith("```"):
                content = content[:content.rfind("```")]

            return json.loads(content.strip())
        except Exception as e:
            print(f"\n  ⚠️ Claude error for '{custom_name}': {e}")
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
                    t.model = $model,
                    t.recovery = true
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
                    t.model = $model,
                    t.recovery = true
            """, ex_id=exercise_id, mg_id=record["id"],
                role=role, model=MODEL)

if __name__ == "__main__":
    mapper = FailureRecoveryMapper()
    try:
        mapper.map_failures()
    finally:
        mapper.close()
