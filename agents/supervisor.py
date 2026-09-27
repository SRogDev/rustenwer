"""Phase-1 supervisor graph — Original Rustenwer MVP Core.

intake → specification → dataset_check → baselines → route →
    (strategy → summarize | summarize)

All node functions live in `agents/nodes/` and stay importable for unit
tests. The graph only wires them; Rule 3 keeps deterministic logic in
`shared/services/`.
"""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from agents.nodes.dataset import dataset_node
from agents.nodes.evaluation import evaluation_node
from agents.nodes.routing import route_after_baselines
from agents.nodes.specification import specification_node
from agents.nodes.strategy import strategy_node
from agents.state import SupervisorState

logger = structlog.get_logger(__name__)


def intake(state: SupervisorState) -> dict:
    """Accept the problem statement into the graph."""
    logger.info("supervisor.intake", phase=state.get("phase"))
    return {
        "phase": "intake",
        "notes": [
            *state.get("notes", []),
            f"intake: accepted problem statement "
            f"({len(state.get('problem_statement') or '')} chars)",
        ],
    }


def summarize(state: SupervisorState) -> dict:
    """Compose the final outcome summary from the agent artifacts."""
    diagnosis = state.get("diagnosis") or {}
    recommendation = state.get("recommendation") or "no recommendation produced"
    strategy = state.get("strategy")
    note = (
        f"summarize: primitive={diagnosis.get('primitive')}, "
        f"ml_necessary={diagnosis.get('ml_necessary')}, "
        f"strategy={strategy['training_method'] if strategy else 'skipped (no-ML path)'}, "
        f"recommendation={recommendation}"
    )
    logger.info("supervisor.summarize", note=note)
    return {"phase": "done", "notes": [*state.get("notes", []), note]}


def build_supervisor_graph():
    """Build and compile the Phase-1 supervisor graph."""
    graph = StateGraph(SupervisorState)
    graph.add_node("intake", intake)
    graph.add_node("specification", specification_node)
    graph.add_node("dataset_check", dataset_node)
    graph.add_node("baselines", evaluation_node)
    graph.add_node("strategy", strategy_node)
    graph.add_node("summarize", summarize)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "specification")
    graph.add_edge("specification", "dataset_check")
    graph.add_edge("dataset_check", "baselines")
    graph.add_conditional_edges(
        "baselines",
        route_after_baselines,
        {"strategy": "strategy", "summarize": "summarize"},
    )
    graph.add_edge("strategy", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()
