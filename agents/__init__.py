"""Rustenwer agents package."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the monorepo's `shared/` package (hand-synced domain types) importable
# so `python demo.py` and `pytest` work from the `agents/` directory without
# PYTHONPATH — same trick as `api/app/__init__.py`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
