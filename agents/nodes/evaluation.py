"""Evaluation (baselines) agent node.

Orchestrates `shared.services.baselines.run_baselines` (Rule 3, Rule 9:
baselines run BEFORE any training is proposed; the best baseline sets the
`bar_to_beat`). Writes a `recommendation`: promote the best baseline when no
ML is needed, otherwise train a candidate to beat the bar (Rule 11: the
evaluator only sees row data, never model internals).
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from shared.domain import IntelligenceSpec

from agents.nodes._common import append_note
from agents.state import SupervisorState

logger = structlog.get_logger(__name__)


def _recommendation(state: SupervisorState, report) -> str:
    bar = report.bar_to_beat
    best = report.best_baseline
    if (state.get("diagnosis") or {}).get("ml_necessary"):
        return (
            f"Train a candidate to beat the baseline bar set by '{best}': "
            f"accuracy {bar.accuracy:.2f}, p50 latency {bar.latency_ms_p50:.2f}ms, "
            f"cost ${bar.cost_usd_per_1k:.4f}/1k predictions."
        )
    return (
        f"Promote best baseline '{best}' (accuracy {bar.accuracy:.2f}, "
        f"p50 latency {bar.latency_ms_p50:.2f}ms) — no training required (Rule 13)."
    )


def evaluation_node(state: SupervisorState) -> dict:
    """Run the cheap baselines and write the recommendation."""
    from shared.services.baselines import run_baselines  # lazy: backend builder delivers it

    spec = IntelligenceSpec(**state["spec"])
    report = run_baselines(
        spec=spec,
        dataset_version_id=uuid4(),
        rows=list(state.get("dataset_rows") or []),
        label_column=state.get("label_column") or "label",
    )
    recommendation = _recommendation(state, report)
    logger.info(
        "evaluation.baselines",
        best=report.best_baseline,
        bar_accuracy=report.bar_to_beat.accuracy,
    )
    return {
        "baseline_report": report.model_dump(mode="json"),
        "recommendation": recommendation,
        "phase": "baselines",
        **append_note(
            state,
            f"baselines: best='{report.best_baseline}' "
            f"(accuracy={report.bar_to_beat.accuracy:.2f}); recommendation written",
        ),
    }
