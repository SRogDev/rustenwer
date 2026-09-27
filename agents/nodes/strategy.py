"""Training-strategy agent node.

Orchestrates `shared.services.strategy.propose_strategy` (Rule 3). The node
decides nothing by itself: it reconstructs the spec/diagnosis/baseline
models from state and stores the resulting `TrainingStrategy`. The
no-training path (`training_method="none-deterministic"`, Rule 2/13) is a
first-class representable outcome.
"""

from __future__ import annotations

import structlog
from shared.domain import BaselineReport, DiagnosisResult, IntelligenceSpec

from agents.nodes._common import append_note
from agents.state import SupervisorState

logger = structlog.get_logger(__name__)


def strategy_node(state: SupervisorState) -> dict:
    """Propose a training strategy from the diagnosis and the baseline bar."""
    from shared.services.strategy import propose_strategy  # lazy: backend builder delivers it

    spec = IntelligenceSpec(**state["spec"])
    diagnosis = DiagnosisResult(**state["diagnosis"])
    baseline_report = (
        BaselineReport(**state["baseline_report"]) if state.get("baseline_report") else None
    )

    strategy = propose_strategy(spec, diagnosis, baseline_report)
    logger.info(
        "strategy.proposed",
        training_method=strategy.training_method,
        model_family=strategy.model_family,
    )
    return {
        "strategy": strategy.model_dump(mode="json"),
        "phase": "strategy",
        **append_note(
            state,
            f"strategy: proposed training_method='{strategy.training_method}' "
            f"(model_family={strategy.model_family})",
        ),
    }
