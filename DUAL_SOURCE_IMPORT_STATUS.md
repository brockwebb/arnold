# Dual-Source Exercise Import - Status Report

## Summary

Successfully implemented dual-source exercise import strategy combining Free-Exercise-DB and Functional Fitness Database.

## Results

### Phase 1: Free-Exercise-DB (COMPLETE ✅)
- **873 canonical exercises** imported
- Source: `ontologies/exercises/free-exercise-db/dist/exercises.json`
- Features: Good muscle mappings, categories, equipment, difficulty

### Phase 2: Functional Fitness DB (COMPLETE ✅)
- **3,251 exercises** imported
- **2,319 muscle links** created
- Source: `ontologies/exercises/Functional+Fitness+Exercise+Database+(version+2.9).xlsx`
- Features: Detailed muscle mappings (primary/secondary/tertiary), body regions, mechanics

### Combined Canonical Set
- **Total: 4,124 canonical exercises**
- **4.7x increase** in exercise coverage vs Free-Exercise-DB alone
- All exercises tagged with `source` provenance field
- All marked `provenance_verified: false` (pending deduplication)

## Next Steps (NOT YET COMPLETE)

### Step 3: LLM Deduplication
**Script:** `scripts/importers/deduplicate_exercises_llm.py`

**Objective:** Find exercises that appear in both sources and use LLM to judge which version is higher quality.

**Process:**
1. Find exact name matches across sources
2. For each duplicate pair, LLM compares:
   - Muscle target completeness
   - Difficulty rating presence
   - Category/classification detail
   - Source reputation
3. Winner: Mark `is_canonical: true, provenance_verified: true, won_deduplication: true`
4. Loser: Mark `is_canonical: false, is_duplicate: true, duplicate_of: <winner_id>`

**Expected Results:**
- ~500-800 duplicate pairs identified
- Best version of each exercise retained
- ~3,500 unique canonical exercises after dedup

### Step 4: Re-Map Custom Exercises
**Script:** `scripts/importers/map_custom_exercises_v2.py` (update loader)

**Change Required:**
```python
def _load_canonical_exercises(self):
    """Load ALL canonical exercises from BOTH sources (excluding duplicates)"""
    result = self.graph.execute_query("""
        MATCH (ex:Exercise)
        WHERE ex.is_canonical = true
          AND (ex.is_duplicate IS NULL OR ex.is_duplicate = false)
        RETURN ex.name as name, ex.id as id
        ORDER BY ex.name
    """)
    return result
```

**Expected Results:**
- **Novel exercises:** 699 → <200 (70% reduction)
- **Variations:** 149 → 500+ (3x increase)
- **Coverage:** More gym-focused exercises (Bulgarian Split Squat, Bird Dog, etc.) should now match

## Files Created

### Importers
- ✅ `scripts/importers/analyze_functional_fitness_db.py` - Excel structure analysis
- ✅ `scripts/importers/import_functional_fitness_db.py` - FFDB import with provenance
- ⏸️ `scripts/importers/deduplicate_exercises_llm.py` - LLM deduplication (not yet run)

### Mappers
- ⏸️ `scripts/importers/map_custom_exercises_v2.py` - Update to load from both sources

## Database State

### Before Dual Import
```
Canonical exercises: 873 (Free-Exercise-DB only)
Custom exercises: 849
Novel exercises: 699 (82%)
Variations: 149
```

### After Dual Import (Current)
```
Canonical exercises: 4,124 (both sources)
  - free-exercise-db: 873
  - functional-fitness-db: 3,251
Custom exercises: 849 (unchanged)
Novel exercises: Still 699 (pending re-mapping)
Variations: Still 149 (pending re-mapping)
```

### After Deduplication (Expected)
```
Canonical exercises: ~3,500 (duplicates removed)
Provenance verified: 100%
```

### After Re-Mapping (Expected)
```
Custom exercises: 849
Novel exercises: <200 (70% reduction)
Variations: 500+ (3x increase)
Coverage: 90%+ of gym exercises
```

## Architecture Benefits

### 1. Provenance Tracking
All exercises have `source` field:
- `free-exercise-db` - Open source, CC0 license
- `functional-fitness-db` - Comprehensive coverage

### 2. Quality Competition
LLM judges best version when same exercise appears in both sources based on:
- Muscle target completeness
- Metadata richness (difficulty, category, etc.)
- Data quality

### 3. No Data Loss
Losing duplicate entries are kept in database:
- Marked `is_duplicate: true`
- Linked via `duplicate_of: <winner_id>`
- Available for audit/review

### 4. Coverage Expansion
Examples of exercises likely now covered:
- ✅ Bulgarian Split Squat
- ✅ Bird Dog
- ✅ Shoulder Dislocate
- ✅ Deadhang
- ✅ Kettlebell swings/carries
- ✅ Gymnastic ring exercises
- ✅ Club bell/Macebell exercises

## Performance

### Import Speed
- Functional Fitness DB: 3,251 exercises in 37 seconds
- **Rate:** ~88 exercises/second
- **Muscle linking:** 2,319 successful links (71% coverage)

### Database Size
- **Before:** 873 canonical + 849 custom = 1,722 exercises
- **After:** 4,124 canonical + 849 custom = 4,973 exercises
- **Growth:** 2.9x total exercises

## Next Commands

```bash
# 1. Run LLM deduplication (uses gpt-4o-mini, 6 parallel workers)
cd /Users/brock/Documents/GitHub/arnold/scripts/importers/
python deduplicate_exercises_llm.py

# 2. Update custom exercise mapper to load from both sources
# (code change required - see Step 4 above)

# 3. Re-map custom exercises against combined canonical set
python map_custom_exercises_v2.py --clear

# 4. Validate results
# Run queries from scripts/validation/check_database_health.cypher
```

---
*Status: Phase 2 Complete, Phase 3-4 Pending*
*Generated: 2025-12-26*
