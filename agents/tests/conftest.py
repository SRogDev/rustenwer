"""Test doubles for `shared.services.*`.

The backend builder owns `shared/services/` (delivered in parallel). These
fakes mirror the EXACT documented signatures in `docs/PHASE1.md` §3 so the
agents' orchestration logic is testable via strict TDD *now*; they are test
doubles only — no deterministic domain logic is duplicated here (Rule 3).
Real services replace these in `demo.py` integration runs.
"""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from shared.domain import (
    BaselineMetrics,
    BaselineReport,
    DatasetReport,
    DiagnosisResult,
    IntelligencePrimitive,
    IntelligenceSpec,
    QualityBar,
    TrainingStrategy,
)

_SERVICES_PKG = "shared.services"


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


# --- Deterministic keyword rules, mirroring the documented behavior of the
# --- real services (PHASE1.md §3), used only to make the doubles plausible.
_DETERMINISTIC_PATTERNS = (
    "sort by",
    "filter by",
    "lookup",
    "count",
    "deduplicate",
    "format",
    "threshold",
    "validate",
)
_LEARNING_SIGNALS = ("learn", "predict", "classify", "fuzzy", "ambiguous")


def _ml_necessary(problem_statement: str) -> bool:
    text = problem_statement.lower()
    if any(s in text for s in _LEARNING_SIGNALS):
        return True
    return not any(p in text for p in _DETERMINISTIC_PATTERNS)


def _fake_diagnose_spec(spec: IntelligenceSpec) -> DiagnosisResult:
    ml = _ml_necessary(spec.problem_statement)
    approaches = ["majority_class", "keyword_heuristic", "deterministic_rule"]
    if ml:
        approaches += ["embedding-ft", "lora"]
    return DiagnosisResult(
        spec_id=spec.id,
        ml_necessary=ml,
        primitive=spec.intelligence_primitive,
        rationale=(
            f"1) Problem: {spec.problem_statement[:60]}. 2) Behavior: decide/output "
            "per spec. 3) Inputs: input_schema. 4) Outputs: output_schema. "
            f"5) Primitive: {spec.intelligence_primitive.value}. "
            f"6) ML necessary: {ml}. 7) Approaches: {', '.join(approaches)}. "
            "8) Data: labeled examples. 9) Success: spec evaluation_definition. "
            "10) Constraints: spec constraints."
        ),
        candidate_approaches=approaches,
        data_requirements=["labeled examples"],
        success_metrics=["accuracy", "p50 latency"],
        key_constraints=list(spec.constraints),
        diagnosed_at=_utcnow(),
    )


def _fake_validate_dataset_version(
    dataset_id: UUID,
    version: int,
    rows: list[dict[str, Any]],
    label_column: str | None,
) -> DatasetReport:
    schema: dict[str, str] = {}
    missing: dict[str, int] = {}
    for row in rows:
        for k, v in row.items():
            missing.setdefault(k, 0)
            if v is None:
                missing[k] += 1
            schema.setdefault(
                k,
                "int"
                if isinstance(v, bool) is False and isinstance(v, int)
                else "float"
                if isinstance(v, float)
                else "bool"
                if isinstance(v, bool)
                else "str"
                if isinstance(v, str)
                else "null",
            )
    balance: dict[str, int] | None = None
    if label_column and any(label_column in r for r in rows):
        balance = {}
        for r in rows:
            if label_column in r:
                balance[str(r[label_column])] = balance.get(str(r[label_column]), 0) + 1
    return DatasetReport(
        dataset_id=dataset_id,
        version=version,
        row_count=len(rows),
        column_schema=schema,
        class_balance=balance,
        missing_values=missing,
        leakage_flags=[],
        imbalance_detected=False,
        ready_for_training=len(rows) >= 10 and bool(balance),
        notes=["test double"],
    )


def _fake_run_baselines(
    spec: IntelligenceSpec,
    dataset_version_id: UUID,
    rows: list[dict[str, Any]],
    label_column: str = "label",
) -> BaselineReport:
    del spec, rows  # the double returns plausible fixed numbers
    baselines = [
        BaselineMetrics(
            name="majority_class",
            description="Always predict the most frequent label.",
            accuracy=0.67,
            latency_ms_p50=0.01,
            cost_usd_per_1k=0.0,
            size_bytes=64,
            predictions_evaluated=12,
        ),
        BaselineMetrics(
            name="keyword_heuristic",
            description="Predict by label-token presence in text.",
            accuracy=0.83,
            latency_ms_p50=0.05,
            cost_usd_per_1k=0.0,
            size_bytes=128,
            predictions_evaluated=12,
        ),
        BaselineMetrics(
            name="deterministic_rule",
            description="Best numeric threshold by exhaustive scan.",
            accuracy=0.92,
            latency_ms_p50=0.03,
            cost_usd_per_1k=0.0,
            size_bytes=96,
            predictions_evaluated=12,
        ),
    ]
    return BaselineReport(
        spec_id=uuid4(),
        dataset_version_id=dataset_version_id,
        baselines=baselines,
        best_baseline="deterministic_rule",
        bar_to_beat=QualityBar(accuracy=0.92, latency_ms_p50=0.03, cost_usd_per_1k=0.0),
        evaluated_at=_utcnow(),
    )


def _fake_propose_strategy(
    spec: IntelligenceSpec,
    diagnosis: DiagnosisResult,
    baseline_report: BaselineReport | None,
) -> TrainingStrategy:
    if not diagnosis.ml_necessary:
        return TrainingStrategy(
            model_family=None,
            architecture=None,
            training_method="none-deterministic",
            objective="solve deterministically without training",
            rationale="no ML required per diagnosis (Rule 13)",
            no_training_justification=(
                "The problem matches deterministic patterns with no learning signal; "
                "a trained model adds cost without capability (Rule 2/13)."
            ),
            baseline_bar=baseline_report.bar_to_beat if baseline_report else None,
            evaluation_plan=spec.evaluation_definition or "",
        )
    return TrainingStrategy(
        model_family="embedding-ft",
        architecture={"type": "embedding-ft", "base": "small-embedding", "head": "linear"},
        training_method="embedding-ft",
        objective="maximize accuracy on labeled examples",
        hyperparameters={"rank": 16, "epochs": 3, "lr": 2e-4},
        evaluation_plan=spec.evaluation_definition or "holdout accuracy",
        compute_budget={"max_gpu_hours": 2.0, "max_cost_usd": 5.0},
        baseline_bar=baseline_report.bar_to_beat if baseline_report else None,
        rationale="ML necessary per diagnosis; cheapest method that can beat the baseline bar",
    )


def _fake_termination_spec_fields() -> dict[str, Any]:
    return {
        "name": "Search termination intelligence",
        "intelligence_primitive": IntelligencePrimitive.TERMINATION,
        "input_schema": {"search_state": {"type": "object"}},
        "output_schema": {
            "decision": {"enum": ["continue", "stop"]},
            "confidence": {"type": "number"},
        },
        "latency_requirements": {"latency_budget_ms": 50},
        "evaluation_definition": "maximize useful discoveries",
    }


def _fake_termination_dataset_rows() -> list[dict[str, Any]]:
    return [
        {"state_summary": f"state {i}", "depth": i, "progress_score": 0.1 * i, "label": lab}
        for i, lab in enumerate(
            [
                "continue",
                "continue",
                "stop",
                "continue",
                "continue",
                "stop",
                "continue",
                "stop",
                "continue",
                "continue",
                "stop",
                "continue",
            ]
        )
    ]


def install_service_doubles() -> None:
    """Install `shared.services.*` test doubles into `sys.modules`."""
    if _SERVICES_PKG not in sys.modules:
        pkg = types.ModuleType(_SERVICES_PKG)
        pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules[_SERVICES_PKG] = pkg

    def _module(name: str, **attrs: Any) -> None:
        key = f"{_SERVICES_PKG}.{name}"
        mod = types.ModuleType(key)
        for attr_name, attr in attrs.items():
            setattr(mod, attr_name, attr)
        sys.modules[key] = mod

    _module("diagnosis", diagnose_spec=_fake_diagnose_spec)
    _module("datasets", validate_dataset_version=_fake_validate_dataset_version)
    _module("baselines", run_baselines=_fake_run_baselines)
    _module("strategy", propose_strategy=_fake_propose_strategy)
    _module(
        "fixtures",
        termination_spec_fields=_fake_termination_spec_fields,
        termination_dataset_rows=_fake_termination_dataset_rows,
    )


install_service_doubles()
