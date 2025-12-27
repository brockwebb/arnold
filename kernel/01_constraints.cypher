// Arnold Kernel: Database Constraints
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
