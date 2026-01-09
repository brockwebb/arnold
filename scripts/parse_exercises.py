#!/usr/bin/env python3
"""
Parse exercise enrichment data from markdown and generate structured JSON files.

Reads: data/enrichment/batches/*.md (all batch files)
Uses: Claude API to extract structured muscle/pattern data
Writes: data/enrichment/exercises/<exercise_name>.json

Usage:
    python scripts/parse_exercises.py              # Process all batch files
    python scripts/parse_exercises.py --batch 002  # Process only batch_002.md
    python scripts/parse_exercises.py --dry-run    # Show what would be processed
    python scripts/parse_exercises.py --force      # Reprocess even if JSON exists
"""

import os
import re
import json
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / '.env')

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENRICHMENT_DIR = PROJECT_ROOT / "data" / "enrichment"
BATCHES_DIR = ENRICHMENT_DIR / "batches"
SCHEMA_FILE = ENRICHMENT_DIR / "schema_reference.json"
OUTPUT_DIR = ENRICHMENT_DIR / "exercises"


def load_schema():
    """Load the schema reference for valid patterns/muscles."""
    with open(SCHEMA_FILE) as f:
        return json.load(f)


def parse_markdown_sections(content: str, source_file: str = None) -> list[dict]:
    """Parse markdown into exercise sections."""
    exercises = []
    
    # Split on ## headers
    sections = re.split(r'\n## ', content)
    
    for section in sections[1:]:  # Skip header/intro
        lines = section.strip().split('\n')
        if not lines:
            continue
            
        exercise_name = lines[0].strip()
        section_text = '\n'.join(lines[1:])
        
        # Extract metadata
        exercise_id_match = re.search(r'\*\*exercise_id:\*\*\s*(\S+)', section_text)
        query_match = re.search(r'\*\*search_query:\*\*\s*(.+)', section_text)
        date_match = re.search(r'\*\*retrieved_at:\*\*\s*(\S*)', section_text)
        
        # Check if this section has actual content (not just placeholder)
        has_content = '[PASTE GOOGLE AI OVERVIEW HERE]' not in section_text
        
        # Extract citations
        citations = []
        citation_section = re.search(r'\*\*Citations:\*\*\n((?:\d+\.\s+https?://[^\n]+\n?)+)', section_text)
        if citation_section:
            citation_lines = citation_section.group(1).strip().split('\n')
            for line in citation_lines:
                url_match = re.search(r'https?://[^\s]+', line)
                if url_match:
                    citations.append(url_match.group(0))
        
        # Get the raw content (everything between metadata and citations)
        raw_text = section_text
        # Remove metadata lines
        raw_text = re.sub(r'\*\*exercise_id:\*\*.*\n?', '', raw_text)
        raw_text = re.sub(r'\*\*search_query:\*\*.*\n?', '', raw_text)
        raw_text = re.sub(r'\*\*retrieved_at:\*\*.*\n?', '', raw_text)
        raw_text = re.sub(r'\*\*Citations:\*\*\n((?:\d+\.\s+https?://[^\n]+\n?)+)', '', raw_text)
        raw_text = raw_text.strip()
        
        exercises.append({
            'name': exercise_name,
            'exercise_id': exercise_id_match.group(1) if exercise_id_match else None,
            'search_query': query_match.group(1).strip() if query_match else None,
            'retrieved_at': date_match.group(1) if date_match and date_match.group(1) else None,
            'has_content': has_content,
            'raw_text': raw_text if has_content else None,
            'citations': citations if has_content else [],
            'source_file': source_file
        })
    
    return exercises


def load_all_batches(batches_dir: Path, batch_filter: str = None) -> list[dict]:
    """Load exercises from all batch files (or a specific one)."""
    all_exercises = []
    
    if batch_filter:
        # Load specific batch
        batch_file = batches_dir / f"batch_{batch_filter}.md"
        if not batch_file.exists():
            print(f"ERROR: Batch file not found: {batch_file}")
            return []
        batch_files = [batch_file]
    else:
        # Load all batch files
        batch_files = sorted(batches_dir.glob("batch_*.md"))
    
    for batch_file in batch_files:
        print(f"  Loading {batch_file.name}...")
        with open(batch_file) as f:
            content = f.read()
        exercises = parse_markdown_sections(content, source_file=batch_file.name)
        all_exercises.extend(exercises)
        print(f"    Found {len(exercises)} exercises")
    
    return all_exercises


def build_prompt(exercise: dict, schema: dict) -> str:
    """Build the Claude API prompt for exercise extraction."""
    
    return f"""You are extracting structured exercise data for a fitness knowledge graph.

EXERCISE: {exercise['name']}
EXERCISE_ID: {exercise['exercise_id']}

RAW DATA FROM GOOGLE AI OVERVIEW:
{exercise['raw_text']}

VALID MOVEMENT PATTERNS (use exact names):
{json.dumps(schema['movement_patterns'], indent=2)}

VALID MUSCLES (prefer specific muscles over muscle groups):
{json.dumps(schema['muscles']['list'], indent=2)}

MUSCLE GROUPS (use only when specific muscle not determinable):
{json.dumps(schema['muscle_groups']['list'], indent=2)}

MAPPING GUIDANCE:
{json.dumps(schema['mapping_guidance'], indent=2)}

TASK: Extract and return a JSON object with:
1. movement_patterns: Array of {{name, confidence (0.0-1.0)}} - which patterns this exercise involves
2. muscles.primary: Array of muscle names that are primary movers
3. muscles.secondary: Array of muscle names that are synergists/stabilizers

RULES:
- Only use exact names from the valid lists above
- Map common terms to specific anatomical muscles using the guidance
- Confidence should reflect how central the pattern is to the exercise
- Primary muscles do the main work; secondary muscles assist/stabilize
- Be conservative - only include muscles that are meaningfully engaged

Return ONLY valid JSON, no markdown or explanation:
{{
  "movement_patterns": [
    {{"name": "Pattern Name", "confidence": 0.9}}
  ],
  "muscles": {{
    "primary": ["Muscle 1", "Muscle 2"],
    "secondary": ["Muscle 3", "Muscle 4"]
  }}
}}"""


def extract_with_claude(exercise: dict, schema: dict, client: anthropic.Anthropic) -> dict:
    """Call Claude API to extract structured data."""
    
    prompt = build_prompt(exercise, schema)
    
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    response_text = message.content[0].text.strip()
    
    # Parse JSON response
    try:
        # Handle potential markdown code blocks
        if response_text.startswith('```'):
            response_text = re.sub(r'^```json?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
        
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: Failed to parse Claude response as JSON: {e}")
        print(f"  Response was: {response_text[:200]}...")
        return None


def write_exercise_json(exercise: dict, extracted: dict, output_dir: Path):
    """Write the complete exercise JSON file."""
    
    # Build filename from exercise name
    filename = re.sub(r'[^a-zA-Z0-9]+', '_', exercise['name'].lower()).strip('_') + '.json'
    filepath = output_dir / filename
    
    output = {
        "exercise_id": exercise['exercise_id'],
        "exercise_name": exercise['name'],
        "source": {
            "type": "google_ai_overview",
            "query": exercise['search_query'],
            "retrieved_at": exercise['retrieved_at'],
            "raw_text": exercise['raw_text'],
            "citations": [{"index": i+1, "url": url} for i, url in enumerate(exercise['citations'])],
            "batch_file": exercise.get('source_file')
        },
        "movement_patterns": extracted['movement_patterns'],
        "muscles": extracted['muscles'],
        "processed_at": datetime.now().isoformat()
    }
    
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    
    return filepath


def main():
    parser = argparse.ArgumentParser(description='Parse exercise enrichment data')
    parser.add_argument('--batch', type=str, help='Process only this batch (e.g., "002" for batch_002.md)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    parser.add_argument('--force', action='store_true', help='Reprocess even if JSON exists')
    args = parser.parse_args()
    
    # Load schema
    schema = load_schema()
    
    # Load exercises from batch files
    print(f"Loading batch files from {BATCHES_DIR}...")
    exercises = load_all_batches(BATCHES_DIR, batch_filter=args.batch)
    
    if not exercises:
        print("No exercises found!")
        return
    
    print(f"\nTotal: {len(exercises)} exercise sections")
    
    # Filter to exercises with content
    to_process = [e for e in exercises if e['has_content']]
    print(f"  {len(to_process)} have content to process")
    
    if not args.force:
        # Skip exercises that already have JSON
        existing = set(f.stem for f in OUTPUT_DIR.glob('*.json'))
        to_process = [
            e for e in to_process 
            if re.sub(r'[^a-zA-Z0-9]+', '_', e['name'].lower()).strip('_') not in existing
        ]
        print(f"  {len(to_process)} need processing (skipping existing)")
    
    if args.dry_run:
        print("\nDRY RUN - Would process:")
        for e in to_process:
            print(f"  - {e['name']} ({e['exercise_id']}) from {e.get('source_file', 'unknown')}")
        return
    
    if not to_process:
        print("\nNothing to process!")
        return
    
    # Initialize Claude client
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
    
    # Process each exercise
    print(f"\nProcessing {len(to_process)} exercises...")
    for i, exercise in enumerate(to_process, 1):
        print(f"\n[{i}/{len(to_process)}] {exercise['name']}")
        
        extracted = extract_with_claude(exercise, schema, client)
        if extracted is None:
            print(f"  SKIPPED due to extraction error")
            continue
        
        filepath = write_exercise_json(exercise, extracted, OUTPUT_DIR)
        print(f"  Wrote: {filepath.name}")
        print(f"  Patterns: {[p['name'] for p in extracted['movement_patterns']]}")
        print(f"  Primary: {extracted['muscles']['primary']}")
        print(f"  Secondary: {extracted['muscles']['secondary']}")
    
    print(f"\nDone! JSON files in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
