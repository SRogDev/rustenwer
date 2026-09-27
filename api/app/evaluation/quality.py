"""Quality vectors (plan §30).

A QualityVector is the multi-objective score of one evaluated subject.
There are NO global weights anywhere in this module: the
IntelligenceSpec's `quality_requirements["priority"]` — an ordered list of
QualityVector field names — is the only thing that orders subjects.
"""

from __future__ import annotations

from typing import Any

from shared.domain import IntelligenceSpec, QualityBar, QualityVector

#: Fields where lower is better; every other numeric field is higher-better.
LOWER_IS_BETTER = frozenset(
    {
        "latency_ms_p50",
        "latency_ms_p99",
        "inference_cost_usd_per_1k",
        "training_cost_usd",
        "model_size_bytes",
    }
)

_DEFAULT_PRIORITY = ["task_quality"]


def assemble_quality_vector(m: dict[str, Any]) -> QualityVector:
    """Map a flat metric dict onto the plan §30 QualityVector.

    Recognized keys: accuracy, ece, robustness, latency_ms_p50,
    latency_ms_p99, cost_usd_per_1k, training_cost_usd, model_size_bytes,
    reliability. Missing keys become None (unmeasured, never zero-filled).
    calibration is defined as 1 - ECE (higher is better).
    """
    ece = m.get("ece")
    return QualityVector(
        task_quality=m.get("accuracy"),
        calibration=(1.0 - ece) if ece is not None else None,
        robustness=m.get("robustness"),
        latency_ms_p50=m.get("latency_ms_p50"),
        latency_ms_p99=m.get("latency_ms_p99"),
        inference_cost_usd_per_1k=m.get("cost_usd_per_1k"),
        training_cost_usd=m.get("training_cost_usd"),
        model_size_bytes=m.get("model_size_bytes"),
        reliability=m.get("reliability"),
    )


def beats_bar(vector: QualityVector, bar: QualityBar) -> bool:
    """True when the vector beats the baseline bar on all three axes.

    Rule 9: task_quality >= bar.accuracy AND latency_p50 <= bar.latency AND
    cost <= bar.cost. An unmeasured field can never beat the bar — it
    compares as infinitely bad.
    """
    quality = vector.task_quality if vector.task_quality is not None else float("-inf")
    latency = (
        vector.latency_ms_p50 if vector.latency_ms_p50 is not None else float("inf")
    )
    cost = (
        vector.inference_cost_usd_per_1k
        if vector.inference_cost_usd_per_1k is not None
        else float("inf")
    )
    return (
        quality >= bar.accuracy
        and latency <= bar.latency_ms_p50
        and cost <= bar.cost_usd_per_1k
    )


def _priority_fields(spec: IntelligenceSpec) -> list[str]:
    requirements = spec.quality_requirements or {}
    priority = requirements.get("priority") or _DEFAULT_PRIORITY
    fields = list(priority)
    valid = set(QualityVector.model_fields)
    for field in fields:
        if field not in valid:
            raise ValueError(
                f"unknown QualityVector field in spec priority: {field!r}"
            )
    return fields


def _sort_key(
    vector: QualityVector, fields: list[str]
) -> tuple[tuple[int, float], ...]:
    """Lexicographic key: (is-None, signed value) per priority field.

    None always sorts last. Lower-is-better fields are negated so that a
    plain ascending tuple comparison implements "best first".
    """
    key: list[tuple[int, float]] = []
    for field in fields:
        value = getattr(vector, field)
        if value is None:
            key.append((1, 0.0))
            continue
        # Ascending tuple order = best first: keep lower-is-better as-is,
        # negate higher-is-better so the larger value sorts first.
        signed = float(value) if field in LOWER_IS_BETTER else -float(value)
        key.append((0, signed))
    return tuple(key)


def rank_by_spec_priority(
    subjects: list[tuple[str, QualityVector]], spec: IntelligenceSpec
) -> list[str]:
    """Order subject labels best-first per the spec's priority list.

    No global weights: the comparison is lexicographic over the priority
    fields (e.g. ["task_quality", "latency_ms_p50"]). Ties break by label
    for determinism.
    """
    fields = _priority_fields(spec)
    return [
        label
        for label, _ in sorted(
            subjects, key=lambda item: (_sort_key(item[1], fields), item[0])
        )
    ]


def is_better_per_priorities(
    a: QualityVector, b: QualityVector, spec: IntelligenceSpec
) -> bool:
    """True when `a` strictly beats `b` on the spec's priority order.

    Lexicographic over the priority fields; a tie on every field is not
    "better" (returns False).
    """
    fields = _priority_fields(spec)
    return _sort_key(a, fields) < _sort_key(b, fields)
