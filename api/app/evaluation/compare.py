"""Candidate comparison (plan §56): baselines vs candidates vs incumbent.

``build_comparison_report`` scores each subject, flags who beats the
baseline bar and who beats the incumbent (both per the spec's priority
order — no global weights), picks the winner, and explains every verdict
in plain language in ``notes``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shared.domain import (
    Benchmark,
    ComparisonReport,
    ComparisonSubjectResult,
    EvaluationSubject,
    IntelligenceSpec,
    QualityBar,
    QualityVector,
    SubjectKind,
)

from app.evaluation import quality as quality_module


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def subject_label(subject: EvaluationSubject) -> str:
    """Stable human label for a subject: 'baseline:deterministic_rule' etc."""
    ref = subject.ref or "unnamed"
    if subject.kind == SubjectKind.MODEL_VERSION:
        ref = ref[:8]
    return f"{subject.kind.value}:{ref}"


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "unmeasured"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _verdict_note(
    label: str,
    vector: QualityVector | None,
    error: str | None,
    beats_bar: bool | None,
    beats_incumbent: bool | None,
    priority: list[str],
) -> str:
    if vector is None:
        return (
            f"'{label}' could not be scored ({error or 'no quality vector'}); "
            "it is excluded from the ranking."
        )
    parts = [
        f"'{label}': task_quality={_fmt(vector.task_quality)}, "
        f"latency_p50={_fmt(vector.latency_ms_p50)}ms, "
        f"cost_per_1k=${_fmt(vector.inference_cost_usd_per_1k)} "
        f"(ranked by {', '.join(priority)})"
    ]
    if beats_bar is True:
        parts.append("beats the baseline bar")
    elif beats_bar is False:
        parts.append("does not beat the baseline bar")
    if beats_incumbent is True:
        parts.append("beats the incumbent")
    elif beats_incumbent is False:
        parts.append("does not beat the incumbent")
    return "; ".join(parts) + "."


def build_comparison_report(
    benchmark: Benchmark,
    subject_results: list[ComparisonSubjectResult],
    bar: QualityBar | None,
    incumbent: ComparisonSubjectResult | None,
    spec: IntelligenceSpec,
) -> ComparisonReport:
    """Score subjects against the bar and the incumbent; pick the winner."""
    requirements = spec.quality_requirements or {}
    priority = list(requirements.get("priority") or ["task_quality"])

    incumbent_vector = incumbent.quality_vector if incumbent else None
    for result in subject_results:
        vector = result.quality_vector
        result.beats_bar = (
            quality_module.beats_bar(vector, bar) if (vector and bar) else None
        )
        result.beats_incumbent = (
            quality_module.is_better_per_priorities(vector, incumbent_vector, spec)
            if (vector and incumbent_vector)
            else None
        )

    scored = [
        (subject_label(r.subject), r.quality_vector)
        for r in subject_results
        if r.quality_vector is not None
    ]
    winner: str | None = None
    if scored:
        winner = quality_module.rank_by_spec_priority(scored, spec)[0]

    notes: list[str] = []
    if bar is not None:
        notes.append(
            f"Baseline bar to beat: accuracy={_fmt(bar.accuracy)}, "
            f"latency_p50={_fmt(bar.latency_ms_p50)}ms, "
            f"cost_per_1k=${_fmt(bar.cost_usd_per_1k)}."
        )
    for result in subject_results:
        notes.append(
            _verdict_note(
                subject_label(result.subject),
                result.quality_vector,
                result.metrics.get("error"),
                result.beats_bar,
                result.beats_incumbent,
                priority,
            )
        )
    if incumbent is not None:
        notes.append(
            f"Incumbent '{subject_label(incumbent.subject)}': "
            f"task_quality={_fmt(incumbent_vector.task_quality if incumbent_vector else None)}."
        )
    if winner is not None:
        notes.append(
            f"Winner: '{winner}' — best subject per the spec's priority order "
            f"({', '.join(priority)})."
        )
    else:
        notes.append("No winner: no subject produced a quality vector.")

    return ComparisonReport(
        benchmark_id=benchmark.id,
        generated_at=_utc_now(),
        results=subject_results,
        baseline_bar=bar,
        incumbent=incumbent,
        winner=winner,
        notes=notes,
    )
