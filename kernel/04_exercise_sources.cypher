// Arnold Kernel: Exercise Sources


MERGE (src:ExerciseSource {id: "SOURCE:free-exercise-db"})
SET src.name = "Free Exercise DB",
    src.short_name = "free-exercise-db",
    src.license = "CC0",
    src.url = "https://github.com/yuhonas/free-exercise-db",
    src.version = "",
    src.description = "Open source exercise database with good muscle mappings";

MERGE (src:ExerciseSource {id: "SOURCE:functional-fitness-db"})
SET src.name = "Functional Fitness Database",
    src.short_name = "functional-fitness-db",
    src.license = "",
    src.url = "",
    src.version = "2.9",
    src.description = "Comprehensive fitness database with detailed muscle mappings";
