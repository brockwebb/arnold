// Arnold Kernel: Reference Nodes
// Scientific concepts and standards

// ===== ENERGY SYSTEMS (Margaria-Morton Model) =====

MERGE (es:EnergySystem {type: "Glycolytic"})
SET es.description = "Anaerobic glycolysis - lactate production (10s-2min)",
    es.metabolic_pathway = "glycolysis_without_oxidation",
    es.time_domain = "10-120_seconds",
    es.paper_reference = "Margaria-Morton, Boillet 2024";

MERGE (es:EnergySystem {type: "Oxidative"})
SET es.description = "Aerobic metabolism - sustainable energy (>2min)",
    es.metabolic_pathway = "mitochondrial_oxidative_phosphorylation",
    es.time_domain = ">120_seconds",
    es.paper_reference = "Margaria-Morton, Boillet 2024";

MERGE (es:EnergySystem {type: "Phosphagen"})
SET es.description = "ATP-PCr system - immediate energy (<10 seconds)",
    es.metabolic_pathway = "phosphocreatine_breakdown",
    es.time_domain = "0-10_seconds",
    es.paper_reference = "Margaria-Morton, Boillet 2024";

// ===== OBSERVATION CONCEPTS (LOINC) =====

MERGE (oc:ObservationConcept {loinc_code: "29463-7"})
SET oc.friendly_name = "body_weight",
    oc.display_name = "Body Weight",
    oc.unit = "lbs",
    oc.category = "vital_sign";

MERGE (oc:ObservationConcept {loinc_code: "80404-7"})
SET oc.friendly_name = "heart_rate_variability",
    oc.display_name = "Heart Rate Variability (RMSSD)",
    oc.unit = "ms",
    oc.category = "recovery_metric";

MERGE (oc:ObservationConcept {loinc_code: "8867-4"})
SET oc.friendly_name = "resting_heart_rate",
    oc.display_name = "Resting Heart Rate",
    oc.unit = "bpm",
    oc.category = "vital_sign";

// ===== EQUIPMENT CATEGORIES =====

MERGE (eq:EquipmentCategory {id: "EQ_CAT:barbell"})
SET eq.name = "Barbell";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:bodyweight"})
SET eq.name = "Bodyweight";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:cable"})
SET eq.name = "Cable";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:clubbell"})
SET eq.name = "Clubbell";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:dumbbell"})
SET eq.name = "Dumbbell";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:ez_bar"})
SET eq.name = "e-z curl bar";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:foam_roller"})
SET eq.name = "foam roll";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:gymnastic_rings"})
SET eq.name = "Gymnastic Rings";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:kettlebell"})
SET eq.name = "Kettlebell";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:macebell"})
SET eq.name = "Macebell";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:machine"})
SET eq.name = "machine";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:medicine_ball"})
SET eq.name = "medicine ball";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:other"})
SET eq.name = "other";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:resistance_band"})
SET eq.name = "Band";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:sliders"})
SET eq.name = "Sliders";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:stability_ball"})
SET eq.name = "exercise ball";

MERGE (eq:EquipmentCategory {id: "EQ_CAT:suspension_trainer"})
SET eq.name = "Suspension Trainer";
