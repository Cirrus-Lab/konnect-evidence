#!/usr/bin/env python3
"""Cross-platform launcher for the edagov review console (needs Flask): python edagov-review.py --root <design> ..."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "src"))
from edagov.review.app import main  # noqa: E402

sys.exit(main())
