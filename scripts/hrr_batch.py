#!/usr/bin/env python3
"""
DEPRECATED - DO NOT USE

This script has been deprecated as of January 2026.
It contained its own embedded detection logic that diverged from the 
modular hrr/ package, causing data quality issues.

Use instead:
    python scripts/hrr_feature_extraction.py --all --reprocess

The original script is archived at:
    scripts/archive/hrr_batch_DEPRECATED.py
"""

import sys

print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                         DEPRECATED SCRIPT                              ║
╠═══════════════════════════════════════════════════════════════════════╣
║  hrr_batch.py is DEPRECATED and should NOT be used.                   ║
║                                                                        ║
║  It contained duplicate detection logic that diverged from the         ║
║  modular hrr/ package, causing data quality issues.                    ║
║                                                                        ║
║  USE INSTEAD:                                                          ║
║    python scripts/hrr_feature_extraction.py --all --reprocess          ║
║                                                                        ║
║  For single session:                                                   ║
║    python scripts/hrr_feature_extraction.py --session-id <ID>          ║
║                                                                        ║
║  Original archived at: scripts/archive/hrr_batch_DEPRECATED.py         ║
╚═══════════════════════════════════════════════════════════════════════╝
""", file=sys.stderr)

sys.exit(1)
