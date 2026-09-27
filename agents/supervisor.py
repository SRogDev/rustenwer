"""Phase-0 supervisor graph — skeleton only.

Phase-0 skeleton — Phase 1 agents (Specification, Dataset, Training
Strategy, Evaluation, Supervisor) plug in as new nodes/edges here.
Until then every node below is a placeholder: it logs, appends a note,
and returns a state update. Nothing here does real work.
"""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from state import SupervisorState

logger = structlog.get_logger(__name__)

_ROUTE_NOTE = "route: Phase-1 routing not implemented"
_SUMMARIZE_NOTE = "summarize: Phase-1 summarization not implemented"


def _append_note(state: SupervisorState, note: str) -> dict[str, list[str]]:
    """Return a state update with `note` appended to `notes`."""
    return {"notes": [*state.get("notes", []), note]}


def intake(state: SupervisorState) -> dict[str, list[str]]:
    """Placeholder node: accept the problem statement into the graph."""
    logger.info("supervisor.intake", phase=state.get("phase"))
    return _append_note(state, "intake: accepted problem statement (placeholder)")


def route(state: SupervisorState) -> dict[str, list[str]]:
    """Placeholder node: pick the next agent (Phase 1 implements this)."""
    logger.info("supervisor.route", phase=state.get("phase"))
    return _append_note(state, _ROUTE_NOTE)


def summarize(state: SupervisorState) -> dict[str, list[str]]:
    """Placeholder node: summarize the outcome (Phase 1 implements this)."""
    logger.info("supervisor.summarize", phase=state.get("phase"))
    return _append_note(state, _SUMMARIZE_NOTE)


def build_supervisor_graph() -> StateGraph:
    """Build and compile the Phase-0 supervisor graph: intake -> route -> summarize -> END."""
    graph = StateGraph(SupervisorState)
    graph.add_node("intake", intake)
    graph.add_node("route", route)
    graph.add_node("summarize", summarize)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "route")
    graph.add_edge("route", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()
