"""Intelligence registry (Phase 3, plan §31/§32).

Intelligence is a first-class artifact, separate from Model: one model may
power many intelligences and one intelligence may combine many models.
"""

from app.registry.intelligences import get_intelligence_repository, router

__all__ = ["get_intelligence_repository", "router"]
