"""Training Strategy agent logic (product plan §12).

The strategy agent DECIDES; the executor (Phase 2) executes (Rule 3).
Rule 2: never assume fine-tuning is the answer — the strategy may be
"none-deterministic" (Rule 13).
"""

from __future__ import annotations

from typing import Any

from shared.domain import (
    BaselineReport,
    DiagnosisResult,
    IntelligenceSpec,
    TrainingStrategy,
)


def _row_count(baseline_report: BaselineReport | None) -> int:
    if baseline_report is None or not baseline_report.baselines:
        return 0
    return max(b.predictions_evaluated for b in baseline_report.baselines)


def propose_strategy(
    spec: IntelligenceSpec,
    diagnosis: DiagnosisResult,
    baseline_report: BaselineReport | None,
) -> TrainingStrategy:
    """Propose how (or whether) to obtain the required intelligence."""
    bar = baseline_report.bar_to_beat if baseline_report is not None else None
    dataset_ref = (
        {"dataset_version_id": str(baseline_report.dataset_version_id)}
        if baseline_report is not None
        else None
    )
    # NOTE: BaselineReport only carries dataset_version_id (not dataset_id),
    # so dataset_ref cannot include the dataset id — signature limitation,
    # reported to the coordinator.

    if spec.evaluation_definition:
        evaluation_plan = f"Evaluate against the spec: {spec.evaluation_definition}"
    else:
        evaluation_plan = (
            "Hold-out accuracy vs the baseline bar; p50 latency and "
            "cost per 1k predictions within budget."
        )

    if not diagnosis.ml_necessary:
        justification = (
            "Diagnosis concluded ML is not necessary (Rule 13): the problem "
            "matches deterministic patterns with no learning signal words. "
            "Ship a hand-written deterministic implementation instead of "
            "training a model."
        )
        return TrainingStrategy(
            model_family=None,
            architecture=None,
            training_method="none-deterministic",
            objective=spec.evaluation_definition
            or "Satisfy the spec with a deterministic implementation.",
            dataset_ref=dataset_ref,
            hyperparameters={},
            evaluation_plan=evaluation_plan,
            compute_budget={"max_gpu_hours": 0.0, "max_cost_usd": 0.0},
            baseline_bar=bar,
            rationale=justification,
            no_training_justification=justification,
        )

    n_rows = _row_count(baseline_report)
    primitive = diagnosis.primitive.value
    if primitive in ("classification", "termination"):
        # Small labeled sets favor embedding fine-tunes; larger ones LoRA.
        method = "embedding-ft" if n_rows < 1000 else "lora"
    else:
        method = "lora"

    if method == "embedding-ft":
        model_family = "small-encoder"
        architecture: dict[str, Any] | None = {
            "type": "embedding-ft",
            "backbone": "MiniLM-class sentence encoder",
            "head": "linear classifier",
        }
        hyperparameters = {"epochs": 5, "lr": 5e-5, "batch_size": 16}
    else:
        model_family = "llama-3-8b-class"
        architecture = {
            "type": "lora",
            "base": "Llama-3-8B-class instruct model",
        }
        hyperparameters = {"rank": 16, "epochs": 3, "lr": 2e-4}

    if bar is not None:
        objective = (
            f"Beat the baseline bar ({bar.accuracy:.3f} accuracy, "
            f"{bar.latency_ms_p50:.3f}ms p50, ${bar.cost_usd_per_1k:.4f}/1k) "
            f"with {primitive} intelligence."
        )
    else:
        objective = f"Produce {primitive} intelligence meeting the spec."

    rationale = (
        f"Diagnosis found ML necessary for primitive '{primitive}'. "
        f"Method '{method}' chosen for primitive '{primitive}'; "
        "baselines must be beaten before any candidate is accepted (Rule 9)."
    )

    return TrainingStrategy(
        model_family=model_family,
        architecture=architecture,
        training_method=method,
        objective=objective,
        dataset_ref=dataset_ref,
        hyperparameters=hyperparameters,
        evaluation_plan=evaluation_plan,
        compute_budget={
            "max_gpu_hours": min(10.0, 0.5 + n_rows / 200.0),
            "max_cost_usd": min(50.0, 5.0 + n_rows / 100.0),
        },
        baseline_bar=bar,
        rationale=rationale,
        no_training_justification=None,
    )
