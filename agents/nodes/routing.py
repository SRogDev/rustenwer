"""Routing decisions for the supervisor graph.

Pure functions over state — no service calls, no LLM. `route_after_baselines`
is the conditional edge after the baselines node: the strategy node only runs
when the diagnosis concluded ML is necessary (Rule 2/13).
"""

from __future__ import annotations

from agents.state import SupervisorState


def route_after_baselines(state: SupervisorState) -> str:
    """Return the next node after baselines: 'strategy' or 'summarize'."""
    if (state.get("diagnosis") or {}).get("ml_necessary"):
        return "strategy"
    return "summarize"
