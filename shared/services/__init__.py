"""Deterministic domain services (product plan Rule 3: agents decide, services execute).

Pure-Python package: NO FastAPI/LangGraph imports. Both the API routers
(`api/app/`) and the LangGraph agents (`agents/`) call these functions.

Signatures are frozen by the Phase 1 brief — the agents builder codes
against them in parallel. Do not rename or reshape them.
"""

from __future__ import annotations
