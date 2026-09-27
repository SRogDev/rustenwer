"""Phase 3 evaluation subsystem (plan §56, §57, §30).

Importable as ``from app.evaluation import router``. The router is mounted
by the application entrypoint; this package itself wires nothing.
"""

from app.evaluation.router import router  # noqa: F401
