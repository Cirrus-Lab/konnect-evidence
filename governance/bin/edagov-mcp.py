#!/usr/bin/env python3
"""Cross-platform launcher for the edagov governance MCP server (stdio)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "src"))
from edagov.mcp_server import serve  # noqa: E402

sys.exit(serve())
