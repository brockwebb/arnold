// ============================================================
// DATABASE HEALTH CHECK QUERIES
// Run these in Neo4j Browser after imports
// ============================================================

// 1. CHECK FOR DUPLICATE MUSCLE NODES
// ============================================================
// Muscles without FMA ID are duplicates from old imports
MATCH (m:Muscle)
WHERE m.fma_id IS NULL
RETURN count(m) as duplicates, collect(m.name)[0..10] as sample_names;

// 2. ORPHANED EXERCISES (no muscle targets)
// ============================================================
MATCH (ex:Exercise)
WHERE NOT EXISTS {
    MATCH (ex)-[:TARGETS]->(:Muscle)
}
RETURN ex.source as source, count(ex) as orphaned_count
ORDER BY orphaned_count DESC;

// 3. VARIATION RELATIONSHIP QUALITY
// ============================================================
MATCH ()-[v:VARIATION_OF]->()
RETURN count(v) as total_variations,
       avg(v.confidence) as avg_confidence,
       collect(v.variation_type)[0..10] as variation_types;

// 4. MUSCLE GROUP COMPLETENESS
// ============================================================
MATCH (mg:MuscleGroup)
OPTIONAL MATCH (mg)-[:INCLUDES]->(m:Muscle)
RETURN mg.name as group_name,
       count(m) as muscle_count
ORDER BY muscle_count DESC;

// 5. LOW CONFIDENCE MAPPINGS
// ============================================================
MATCH (ex:Exercise)-[t:TARGETS]->(m:Muscle)
WHERE t.llm_inferred = true
  AND t.confidence < 0.7
RETURN ex.name as exercise,
       m.name as muscle,
       t.confidence as confidence,
       t.role as role
ORDER BY confidence ASC
LIMIT 20;

// 6. NOVEL vs VARIATION RATIO
// ============================================================
MATCH (ex:Exercise)
WHERE ex.source IS NULL OR ex.source <> 'free-exercise-db'
RETURN
    count(CASE WHEN ex.is_novel = true THEN 1 END) as novel_exercises,
    count(CASE WHEN EXISTS {(ex)-[:VARIATION_OF]->()} THEN 1 END) as variations,
    count(ex) as total_custom;

// 7. CANONICAL EXERCISES WITHOUT MUSCLES
// ============================================================
MATCH (ex:Exercise)
WHERE ex.is_canonical = true
  AND NOT EXISTS {
      MATCH (ex)-[:TARGETS]->(:Muscle)
  }
RETURN count(ex) as canonical_orphans,
       collect(ex.name)[0..10] as sample_names;

// 8. EQUIPMENT CATEGORIES
// ============================================================
MATCH (eq:EquipmentCategory)
RETURN count(eq) as equipment_categories,
       collect(eq.name) as category_names;

// 9. OVERALL GRAPH STATS
// ============================================================
MATCH (m:Muscle)
WITH count(m) as muscles
MATCH (bp:BodyPart)
WITH muscles, count(bp) as body_parts
MATCH (mg:MuscleGroup)
WITH muscles, body_parts, count(mg) as muscle_groups
MATCH (ex:Exercise WHERE ex.is_canonical = true)
WITH muscles, body_parts, muscle_groups, count(ex) as canonical
MATCH (cust:Exercise WHERE (cust.source IS NULL OR cust.source <> 'free-exercise-db'))
WITH muscles, body_parts, muscle_groups, canonical, count(cust) as custom
MATCH ()-[t:TARGETS]->()
WITH muscles, body_parts, muscle_groups, canonical, custom, count(t) as targets
MATCH ()-[v:VARIATION_OF]->()
RETURN
    muscles,
    body_parts,
    muscle_groups,
    canonical as canonical_exercises,
    custom as custom_exercises,
    targets as target_relationships,
    count(v) as variation_relationships;

// 10. CLEANUP QUERY: REMOVE DUPLICATE MUSCLES
// ============================================================
// Run this ONLY after verifying duplicates exist
// This removes muscle nodes that don't have FMA IDs
// (These are from old imports using common names)

// UNCOMMENT TO RUN CLEANUP:
// MATCH (m:Muscle)
// WHERE m.fma_id IS NULL
// DETACH DELETE m;

// After cleanup, verify:
// MATCH (m:Muscle) RETURN count(m) as remaining_muscles;
