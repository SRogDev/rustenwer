"""Training Strategy agent logic (product plan §12).

The strategy agent DECIDES; the executor (Phase 2) executes (Rule 3).
Rule 2: never assume fine-tuning is the answer — the strategy may be
"none-deterministic" (Rule 13).

Phase 5: method choice is a registry query, not a hardcoded branch. The
recommendation engine (shared/services/methods.py — pure, framework-free,
importable from both the agents and the API) ranks the method catalog and
records vetoes as data.
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


def _recommend(spec, diagnosis, baseline_report):
    """Consult the method recommendation engine (lazy import: shared/services
    must stay framework-free so the LangGraph agents can import it)."""
    from shared.services.methods import detect_environment, recommend_methods

    return recommend_methods(spec, diagnosis, baseline_report, detect_environment())


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
            method_citations=[],
            vetoed_methods=[],
        )

    n_rows = _row_count(baseline_report)
    primitive = diagnosis.primitive.value

    # Phase 5: the engine ranks the catalog; the agent takes the winner.
    recommendation = _recommend(spec, diagnosis, baseline_report)
    top = recommendation.recommended[0]
    method = top.slug

    from shared.services.methods import strategy_defaults_for

    defaults = strategy_defaults_for(method)
    model_family = defaults["model_family"]
    architecture: dict[str, Any] | None = defaults["architecture"]
    hyperparameters = dict(defaults["hyperparameters"])

    if bar is not None:
        objective = (
            f"Beat the baseline bar ({bar.accuracy:.3f} accuracy, "
            f"{bar.latency_ms_p50:.3f}ms p50, ${bar.cost_usd_per_1k:.4f}/1k) "
            f"with {primitive} intelligence."
        )
    else:
        objective = f"Produce {primitive} intelligence meeting the spec."

    vetoed_methods = [
        {"slug": v.slug, "version": v.version, "reason": v.reason}
        for v in recommendation.vetoed
    ]
    rationale = (
        f"Diagnosis found ML necessary for primitive '{primitive}'. "
        f"Method '{method}' (citation {method}@{top.version}) ranked first by "
        f"the method recommendation engine: {'; '.join(top.reasons)}. "
        f"{len(vetoed_methods)} methods vetoed with reasons. "
        "Baselines must be beaten before any candidate is accepted (Rule 9)."
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
        method_citations=list(recommendation.citations),
        vetoed_methods=vetoed_methods,
    )
