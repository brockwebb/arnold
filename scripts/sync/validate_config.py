#!/usr/bin/env python3
"""
Validate source configuration file.

Checks:
  - All metric sources are registered
  - No circular references
  - Required fields present
  - Algorithm compatibility warnings

Usage:
  python validate_config.py
  python validate_config.py --config /path/to/sources.yaml
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from source_resolver import SourceResolver


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate sources.yaml configuration")
    parser.add_argument("--config", type=Path, help="Path to config file")
    args = parser.parse_args()
    
    print("Validating source configuration...")
    print()
    
    try:
        resolver = SourceResolver(args.config)
    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error loading config: {e}")
        sys.exit(1)
    
    # Run validation
    errors = resolver.validate()
    
    if errors:
        print("✗ Validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        print()
        sys.exit(1)
    
    # Show summary
    print("✓ Configuration valid")
    print()
    print(f"Registered Sources: {len(resolver.registered_sources)}")
    for name, info in resolver.registered_sources.items():
        print(f"  - {name}: {info.get('name', 'N/A')} ({info.get('type', 'unknown')})")
    
    print()
    print(f"Configured Metrics: {len(resolver.metrics)}")
    for name, config in resolver.metrics.items():
        primary = config.get('primary', 'N/A')
        fallback = config.get('fallback', [])
        algo = config.get('algorithm', '')
        
        fallback_str = ""
        if fallback:
            fallback_str = f" → {', '.join(fallback)}"
        
        algo_str = ""
        if algo:
            algo_str = f" [{algo}]"
        
        print(f"  - {name}: {primary}{fallback_str}{algo_str}")
    
    # Check for algorithm warnings
    print()
    print("Algorithm Compatibility Notes:")
    hrv_config = resolver.get_metric_config('hrv')
    if hrv_config and not hrv_config.get('fallback'):
        print("  ⚠ HRV has no fallback (SDNN/RMSSD incompatibility - this is correct)")
    
    print()
    print("✓ All checks passed")


if __name__ == "__main__":
    main()
