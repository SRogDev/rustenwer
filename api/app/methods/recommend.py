"""HTTP-side entry to the recommendation engine.

The pure logic (recommend_methods, veto predicates, environment detection)
lives in `shared/services/methods.py` — framework-free so
`shared/services/strategy.py` (used by the LangGraph agents) calls the same
code. This module is a thin re-export for the router.
"""

from shared.services.methods import (  # noqa: F401
    detect_environment,
    recommend_methods,
)

__all__ = ["detect_environment", "recommend_methods"]
