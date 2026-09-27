"""Rustenwer API package."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the monorepo's `shared/` package (hand-synced domain types) importable
# so `uvicorn app.main:app` works from the `api/` directory without PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
