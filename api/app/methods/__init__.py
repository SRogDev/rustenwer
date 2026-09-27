"""Phase 5 method catalog subsystem (plan §10, §11, §52–§54).

Importable as ``from app.methods import router``. The router is mounted
by the application entrypoint; this package itself wires nothing.

New Phase-5 modules:
  registry   — method→adapter linkage + assert_registered() consistency check
  recommend  — thin re-export of the pure recommendation engine
               (shared/services/methods.py)
  research   — in-memory research-finding store behind a Protocol
"""

from app.methods.recommend import detect_environment, recommend_methods  # noqa: F401
from app.methods.registry import (  # noqa: F401
    METHOD_ADAPTERS,
    RegistryInconsistencyError,
    assert_registered,
)
from app.methods.research import (  # noqa: F401
    InMemoryResearchRepository,
    ResearchFindingRepository,
    get_research_repository,
)
from app.methods.router import router  # noqa: F401
