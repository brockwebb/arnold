// Arnold Kernel: Anatomy (FMA)

// ===== MUSCLES =====
MERGE (m:Muscle {fma_id: "fma0323774"})
SET m.name = "Lumbosacral erector spinae muscle group";
MERGE (m:Muscle {fma_id: "fma0327086"})
SET m.name = "Vein to gastrocnemius muscle";
MERGE (m:Muscle {fma_id: "fma0328098"})
SET m.name = "Fetal muscle organ";
MERGE (m:Muscle {fma_id: "fma0328100"})
SET m.name = "Muscle of limb";
MERGE (m:Muscle {fma_id: "fma0328101"})
SET m.name = "Muscle of fetal neck";
MERGE (m:Muscle {fma_id: "fma0329099"})
SET m.name = "Muscle of abdominal part of trunk";
MERGE (m:Muscle {fma_id: "fma14069"})
SET m.name = "Skeletal muscle tissue";
MERGE (m:Muscle {fma_id: "fma20278"})
SET m.name = "Muscle of anterior abdominal wall";
MERGE (m:Muscle {fma_id: "fma23198"})
SET m.name = "Long head of triceps muscle branch of posterior circumflex humeral artery";
MERGE (m:Muscle {fma_id: "fma261732"})
SET m.name = "Skeletal muscle tissue of deltoid";
MERGE (m:Muscle {fma_id: "fma261998"})
SET m.name = "Skeletal muscle tissue of quadriceps femoris";
MERGE (m:Muscle {fma_id: "fma262000"})
SET m.name = "Skeletal muscle tissue of right quadriceps femoris";
MERGE (m:Muscle {fma_id: "fma297498"})
SET m.name = "Muscle body";
MERGE (m:Muscle {fma_id: "fma297500"})
SET m.name = "Skeletal muscle body";
MERGE (m:Muscle {fma_id: "fma297516"})
SET m.name = "Muscle body of trapezius";
MERGE (m:Muscle {fma_id: "fma297518"})
SET m.name = "Muscle body of latissimus dorsi";
MERGE (m:Muscle {fma_id: "fma297522"})
SET m.name = "Muscle body of rhomboid major";
MERGE (m:Muscle {fma_id: "fma297566"})
SET m.name = "Muscle body of biceps femoris";
MERGE (m:Muscle {fma_id: "fma297710"})
SET m.name = "Muscle body of right trapezius";
MERGE (m:Muscle {fma_id: "fma37347"})
SET m.name = "Muscle of pectoral girdle";
MERGE (m:Muscle {fma_id: "fma37349"})
SET m.name = "Pectoral muscle";
MERGE (m:Muscle {fma_id: "fma37367"})
SET m.name = "Muscle of pelvic girdle";
MERGE (m:Muscle {fma_id: "fma58274"})
SET m.name = "Muscle of trunk";
MERGE (m:Muscle {fma_id: "fma64922"})
SET m.name = "Gluteal muscle";
MERGE (m:Muscle {fma_id: "fma67905"})
SET m.name = "Striated muscle tissue";
MERGE (m:Muscle {fma_id: "fma9620"})
SET m.name = "Muscle of abdomen";
MERGE (m:Muscle {fma_id: "fma9621"})
SET m.name = "Muscle of upper limb";
MERGE (m:Muscle {fma_id: "fma9622"})
SET m.name = "Muscle of lower limb";
MERGE (m:Muscle {fma_id: "fma9641"})
SET m.name = "Portion of muscle tissue";

// ===== MUSCLE GROUPS =====
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:abductors"})
SET mg.name = "Hip Abductors", mg.common_name = "abductors";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:adductors"})
SET mg.name = "Hip Adductors", mg.common_name = "adductors";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:arms"})
SET mg.name = "Arms", mg.common_name = "arms";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:back"})
SET mg.name = "Back", mg.common_name = "back";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:chest"})
SET mg.name = "Chest", mg.common_name = "chest";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:core"})
SET mg.name = "Core", mg.common_name = "core";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:forearms"})
SET mg.name = "Forearms", mg.common_name = "forearms";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:glutes"})
SET mg.name = "Glutes", mg.common_name = "glutes";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:hamstrings"})
SET mg.name = "Hamstrings", mg.common_name = "hamstrings";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:legs"})
SET mg.name = "Legs", mg.common_name = "legs";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:quadriceps"})
SET mg.name = "Quadriceps", mg.common_name = "quadriceps";
MERGE (mg:MuscleGroup {id: "MUSCLE_GROUP:shoulders"})
SET mg.name = "Shoulders", mg.common_name = "shoulders";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "core", mg.common_name = "";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "chest", mg.common_name = "";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "back", mg.common_name = "";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "shoulders", mg.common_name = "";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "arms", mg.common_name = "";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "legs", mg.common_name = "";
MERGE (mg:MuscleGroup {id: "None"})
SET mg.name = "neck", mg.common_name = "";

// ===== BODY PARTS =====
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of anterior abdominal wall";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of abdomen";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of abdominal part of trunk";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of trunk";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle body of biceps femoris";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Skeletal muscle body";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle body";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Organ component";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Vein to gastrocnemius muscle";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Tributary of popliteal vein";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Tributary of deep femoral vein";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Tributary of femoral vein";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Pectoral muscle";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of pectoral girdle";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of upper limb";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of limb";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Gluteal muscle";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of pelvic girdle";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of lower limb";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle body of latissimus dorsi";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Lumbosacral erector spinae muscle group";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Musculature";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Set of heterogeneous anatomical structures";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Set of anatomical clusters";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle body of rhomboid major";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle of fetal neck";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Fetal muscle organ";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Fetal organ";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Developmental organ";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Skeletal muscle tissue of right quadriceps femoris";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Skeletal muscle tissue of quadriceps femoris";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Skeletal muscle tissue";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Striated muscle tissue";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Skeletal muscle tissue of deltoid";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Portion of muscle tissue";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle body of right trapezius";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Muscle body of trapezius";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Long head of triceps muscle branch of posterior circumflex humeral artery";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Branch of posterior circumflex humeral artery";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Branch of subclavian artery";
MERGE (bp:BodyPart {uberon_id: ""})
SET bp.name = "Systemic artery";

// ===== MUSCLE GROUP RELATIONSHIPS =====
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:glutes"}), (m:Muscle {fma_id: "fma64922"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:chest"}), (m:Muscle {fma_id: "fma37349"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:back"}), (m:Muscle {fma_id: "fma297518"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:back"}), (m:Muscle {fma_id: "fma0323774"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:back"}), (m:Muscle {fma_id: "fma297522"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:back"}), (m:Muscle {fma_id: "fma297710"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:shoulders"}), (m:Muscle {fma_id: "fma261732"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:arms"}), (m:Muscle {fma_id: "fma297566"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:arms"}), (m:Muscle {fma_id: "fma23198"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:legs"}), (m:Muscle {fma_id: "fma297566"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:legs"}), (m:Muscle {fma_id: "fma0327086"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:legs"}), (m:Muscle {fma_id: "fma262000"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:core"}), (m:Muscle {fma_id: "fma20278"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:core"}), (m:Muscle {fma_id: "fma0323774"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:hamstrings"}), (m:Muscle {fma_id: "fma297566"})
MERGE (mg)-[:INCLUDES]->(m);
MATCH (mg:MuscleGroup {id: "MUSCLE_GROUP:quadriceps"}), (m:Muscle {fma_id: "fma262000"})
MERGE (mg)-[:INCLUDES]->(m);

// ===== ANATOMY HIERARCHY =====
MATCH (p:BodyPart {uberon_id: "fma20278"}), (c:BodyPart {uberon_id: "fma9620"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma9620"}), (c:BodyPart {uberon_id: "fma0329099"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma0329099"}), (c:BodyPart {uberon_id: "fma58274"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297566"}), (c:BodyPart {uberon_id: "fma297500"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297500"}), (c:BodyPart {uberon_id: "fma297498"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297498"}), (c:BodyPart {uberon_id: "fma14065"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma0327086"}), (c:BodyPart {uberon_id: "fma44330"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma44330"}), (c:BodyPart {uberon_id: "fma44324"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma44324"}), (c:BodyPart {uberon_id: "fma44323"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma37349"}), (c:BodyPart {uberon_id: "fma37347"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma37347"}), (c:BodyPart {uberon_id: "fma9621"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma9621"}), (c:BodyPart {uberon_id: "fma0328100"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma64922"}), (c:BodyPart {uberon_id: "fma37367"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma37367"}), (c:BodyPart {uberon_id: "fma9622"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma9622"}), (c:BodyPart {uberon_id: "fma0328100"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297518"}), (c:BodyPart {uberon_id: "fma297500"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma0323774"}), (c:BodyPart {uberon_id: "fma32558"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma32558"}), (c:BodyPart {uberon_id: "fma78590"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma78590"}), (c:BodyPart {uberon_id: "fma0329058"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297522"}), (c:BodyPart {uberon_id: "fma297500"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma0328101"}), (c:BodyPart {uberon_id: "fma0328098"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma0328098"}), (c:BodyPart {uberon_id: "fma63929"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma63929"}), (c:BodyPart {uberon_id: "fma292326"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma262000"}), (c:BodyPart {uberon_id: "fma261998"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma261998"}), (c:BodyPart {uberon_id: "fma14069"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma14069"}), (c:BodyPart {uberon_id: "fma67905"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma67905"}), (c:BodyPart {uberon_id: "fma9641"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma261732"}), (c:BodyPart {uberon_id: "fma14069"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297710"}), (c:BodyPart {uberon_id: "fma297516"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma297516"}), (c:BodyPart {uberon_id: "fma297500"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma23198"}), (c:BodyPart {uberon_id: "fma23194"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma23194"}), (c:BodyPart {uberon_id: "fma70345"}) MERGE (p)-[:IS_A]->(c);
MATCH (p:BodyPart {uberon_id: "fma70345"}), (c:BodyPart {uberon_id: "fma66464"}) MERGE (p)-[:IS_A]->(c);
