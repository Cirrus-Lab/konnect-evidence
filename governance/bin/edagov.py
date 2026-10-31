#!/usr/bin/env python3
"""Cross-platform edagov launcher (no install needed): python edagov.py <command> ..."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "src"))
from edagov.cli import main  # noqa: E402

sys.exit(main())
