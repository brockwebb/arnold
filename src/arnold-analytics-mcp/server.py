#!/usr/bin/env python3
"""Entry point for arnold-analytics MCP server."""

import sys
import os

# Add the package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arnold_analytics.server import main

if __name__ == "__main__":
    main()
