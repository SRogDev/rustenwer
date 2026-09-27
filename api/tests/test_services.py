"""Tests for shared/services/ — deterministic domain services (Rule 3).

TDD: these tests were written BEFORE the services existed (RED), then the
implementation made them pass (GREEN). The agents builder codes against
these exact signatures in parallel — do not rename them.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared.domain import (
    IntelligenceSpec,
    JobStatus,
    UsageEvent,
    UsageKind,
    UsageScope,
)
from shared.services.baselines import run_baselines
from shared.services.costing import summarize_usage
from shared.services.datasets import (
    detect_leakage,
    infer_column_schema,
    recommend_split,
    validate_dataset_version,
)
from shared.services.diagnosis import diagnose_spec
from shared.services.fixtures import termination_dataset_rows, termination_spec_fields
from shared.services.jobs import ALLOWED_TRANSITIONS, InvalidTransitionError, transition
from shared.services.strategy import propose_strategy


def _spec(**overrides) -> IntelligenceSpec:
    """Build an IntelligenceSpec from the termination fixture kwargs."""
    fields: dict = {"id": uuid4(), "project_id": uuid4(), **termination_spec_fields()}
    fields.update(overrides)
    return IntelligenceSpec(**fields)


# --------------------------------------------------------------------------
# diagnosis
# --------------------------------------------------------------------------


def test_diagnose_termination_ml_necessary() -> None:
    spec = _spec()
    result = diagnose_spec(spec)
    assert result.spec_id == spec.id
    assert result.ml_necessary is True
    assert result.primitive == spec.intelligence_primitive
    # Rule 9: candidate approaches always start with the cheap baselines.
    assert result.candidate_approaches[:3] == [
        "majority_class baseline",
        "keyword_heuristic baseline",
        "deterministic_rule baseline",
    ]
    assert len(result.candidate_approaches) > 3  # ML options appended
    assert result.data_requirements
    assert result.success_metrics
    assert result.key_constraints is not None
    assert result.diagnosed_at


def test_diagnose_rationale_answers_ten_questions() -> None:
    result = diagnose_spec(_spec())
    for i in range(1, 11):
        assert f"{i}." in result.rationale, f"rationale missing question {i}"


def test_diagnose_no_ml_conclusion() -> None:
    """Rule 13: the platform may conclude 'you do not need a trained model'."""
    spec = _spec(
        problem_statement="Sort by timestamp, filter by language, and validate the output format."
    )
    result = diagnose_spec(spec)
    assert result.ml_necessary is False
    assert "no ML" in result.rationale or "not necessary" in result.rationale.lower()


def test_diagnose_learning_signal_beats_deterministic_pattern() -> None:
    spec = _spec(problem_statement="Classify support tickets by urgency; sort by date for display.")
    assert diagnose_spec(spec).ml_necessary is True


# --------------------------------------------------------------------------
# datasets
# --------------------------------------------------------------------------


def test_infer_column_schema_types() -> None:
    rows = [
        {"i": 1, "f": 1.5, "b": True, "s": "x", "n": None, "m": 1},
        {"i": 2, "f": 2.5, "b": False, "s": "y", "n": None, "m": "mixed!"},
    ]
    assert infer_column_schema(rows) == {
        "i": "int",
        "f": "float",
        "b": "bool",
        "s": "str",
        "n": "null",
        "m": "mixed",
    }


def test_infer_column_schema_int_float_mix_is_float() -> None:
    rows = [{"v": 1}, {"v": 2.5}]
    assert infer_column_schema(rows) == {"v": "float"}


def test_detect_leakage_flags_label_copy() -> None:
    rows = [
        {"f": "a", "label_copy": "x", "label": "x"},
        {"f": "b", "label_copy": "y", "label": "y"},
        {"f": "c", "label_copy": "x", "label": "x"},
        {"f": "d", "label_copy": "y", "label": "y"},
    ]
    flags = detect_leakage(rows, "label")
    assert any("label_copy" in flag for flag in flags)


def test_detect_leakage_ignores_unique_identifiers() -> None:
    rows = [
        {"id": f"row-{i}", "label": ("x" if i % 2 == 0 else "y")} for i in range(6)
    ]
    assert detect_leakage(rows, "label") == []


def test_detect_leakage_no_label_column() -> None:
    assert detect_leakage([{"a": 1}], None) == []


def test_recommend_split_sums_to_one() -> None:
    split = recommend_split(12)
    assert split == {"train": 0.7, "validation": 0.15, "test": 0.15}
    assert abs(sum(split.values()) - 1.0) < 1e-9


def test_validate_dataset_version_termination_fixture() -> None:
    dataset_id = uuid4()
    rows = termination_dataset_rows()
    report = validate_dataset_version(dataset_id, 1, rows, "label")
    assert report.dataset_id == dataset_id
    assert report.version == 1
    assert report.row_count == 12
    assert report.column_schema == {
        "state_summary": "str",
        "depth": "int",
        "progress_score": "float",
        "label": "str",
    }
    assert report.class_balance == {"continue": 8, "stop": 4}
    assert report.missing_values == {
        "state_summary": 0,
        "depth": 0,
        "progress_score": 0,
        "label": 0,
    }
    assert report.leakage_flags == []
    assert report.imbalance_detected is False
    assert report.ready_for_training is True


def test_validate_dataset_version_detects_imbalance() -> None:
    dataset_id = uuid4()
    rows = [{"x": i, "label": "a"} for i in range(10)] + [{"x": 99, "label": "b"}]
    report = validate_dataset_version(dataset_id, 1, rows, "label")
    assert report.imbalance_detected is True
    assert report.ready_for_training is True  # imbalance alone does not block


def test_validate_dataset_version_too_few_rows_not_ready() -> None:
    dataset_id = uuid4()
    rows = [{"x": i, "label": "a"} for i in range(5)]
    report = validate_dataset_version(dataset_id, 1, rows, "label")
    assert report.ready_for_training is False


# --------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------


def test_run_baselines_termination_fixture() -> None:
    spec = _spec()
    version_id = uuid4()
    rows = termination_dataset_rows()
    report = run_baselines(spec, version_id, rows, label_column="label")

    assert report.spec_id == spec.id
    assert report.dataset_version_id == version_id
    assert len(report.baselines) == 3
    by_name = {b.name: b for b in report.baselines}

    assert by_name["majority_class"].accuracy == pytest.approx(8 / 12)
    assert by_name["keyword_heuristic"].accuracy == pytest.approx(10 / 12)
    assert by_name["deterministic_rule"].accuracy == pytest.approx(11 / 12)

    for baseline in report.baselines:
        assert baseline.cost_usd_per_1k == 0.0
        assert baseline.size_bytes > 0
        assert baseline.latency_ms_p50 >= 0.0
        assert baseline.predictions_evaluated == 12

    assert report.best_baseline == "deterministic_rule"
    assert report.bar_to_beat.accuracy == pytest.approx(11 / 12)
    assert report.bar_to_beat.cost_usd_per_1k == 0.0
    assert report.evaluated_at


def test_run_baselines_without_labels_reports_none() -> None:
    spec = _spec()
    rows = [{"a": 1}, {"a": 2}, {"a": 3}]
    report = run_baselines(spec, uuid4(), rows, label_column="label")
    for baseline in report.baselines:
        assert baseline.accuracy is None
        assert baseline.predictions_evaluated == 0
    assert report.best_baseline == ""
    assert report.bar_to_beat.accuracy == 0.0
    assert report.bar_to_beat.latency_ms_p50 == 0.0
    assert report.bar_to_beat.cost_usd_per_1k == 0.0


# --------------------------------------------------------------------------
# strategy
# --------------------------------------------------------------------------


def test_propose_strategy_ml_path() -> None:
    spec = _spec()
    diagnosis = diagnose_spec(spec)
    baselines = run_baselines(spec, uuid4(), termination_dataset_rows(), label_column="label")
    strategy = propose_strategy(spec, diagnosis, baselines)

    assert strategy.training_method == "embedding-ft"  # termination + small data
    assert strategy.model_family is not None
    assert strategy.architecture is not None
    assert strategy.hyperparameters  # {rank/epochs/lr}-style defaults
    assert strategy.no_training_justification is None
    assert strategy.baseline_bar is not None
    assert strategy.baseline_bar.accuracy == pytest.approx(11 / 12)  # Rule 9
    assert strategy.compute_budget["max_cost_usd"] == pytest.approx(5 + 12 / 100)
    assert "Accuracy" in strategy.evaluation_plan  # references evaluation_definition


def test_propose_strategy_no_training_path() -> None:
    """Rule 2/13: 'no training' is a first-class strategy outcome."""
    spec = _spec(
        problem_statement="Sort by timestamp, filter by language, and validate the output format."
    )
    diagnosis = diagnose_spec(spec)
    assert diagnosis.ml_necessary is False
    strategy = propose_strategy(spec, diagnosis, None)

    assert strategy.training_method == "none-deterministic"
    assert strategy.model_family is None
    assert strategy.architecture is None
    assert strategy.no_training_justification  # must be set
    assert strategy.compute_budget["max_cost_usd"] == 0.0


# --------------------------------------------------------------------------
# jobs
# --------------------------------------------------------------------------


def test_allowed_transitions_cover_all_states() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(JobStatus)


def test_job_transitions_valid_chain() -> None:
    assert transition(JobStatus.CREATED, JobStatus.QUEUED) == JobStatus.QUEUED
    assert transition(JobStatus.QUEUED, JobStatus.RUNNING) == JobStatus.RUNNING
    assert transition(JobStatus.RUNNING, JobStatus.PAUSED) == JobStatus.PAUSED
    assert transition(JobStatus.PAUSED, JobStatus.RUNNING) == JobStatus.RUNNING
    assert transition(JobStatus.RUNNING, JobStatus.COMPLETED) == JobStatus.COMPLETED
    assert transition(JobStatus.FAILED, JobStatus.QUEUED) == JobStatus.QUEUED
    assert transition(JobStatus.RUNNING, JobStatus.CANCELLED) == JobStatus.CANCELLED


def test_job_transitions_invalid() -> None:
    with pytest.raises(InvalidTransitionError):
        transition(JobStatus.CREATED, JobStatus.RUNNING)
    with pytest.raises(InvalidTransitionError):
        transition(JobStatus.RUNNING, JobStatus.QUEUED)
    with pytest.raises(InvalidTransitionError):
        transition(JobStatus.COMPLETED, JobStatus.CANCELLED)
    with pytest.raises(InvalidTransitionError):
        transition(JobStatus.CANCELLED, JobStatus.QUEUED)
    assert issubclass(InvalidTransitionError, ValueError)


# --------------------------------------------------------------------------
# costing
# --------------------------------------------------------------------------


def test_summarize_usage() -> None:
    project_id = uuid4()
    other_project = uuid4()
    events = [
        UsageEvent(
            id=uuid4(),
            project_id=project_id,
            scope=UsageScope.TRAINING_JOB,
            scope_id=uuid4(),
            kind=UsageKind.TRAINING,
            quantity=2.0,
            unit="gpu_hours",
            cost_usd=10.0,
            recorded_at="2026-09-26T00:00:00+00:00",
        ),
        UsageEvent(
            id=uuid4(),
            project_id=project_id,
            scope=UsageScope.DEPLOYMENT,
            scope_id=uuid4(),
            kind=UsageKind.INFERENCE,
            quantity=1000.0,
            unit="requests",
            cost_usd=2.5,
            recorded_at="2026-09-26T00:00:00+00:00",
        ),
        UsageEvent(
            id=uuid4(),
            project_id=other_project,  # must be excluded
            scope=UsageScope.PROJECT,
            scope_id=other_project,
            kind=UsageKind.STORAGE,
            quantity=5.0,
            unit="gb_months",
            cost_usd=99.0,
            recorded_at="2026-09-26T00:00:00+00:00",
        ),
    ]
    summary = summarize_usage(project_id, events)
    assert summary.project_id == project_id
    assert summary.total_cost_usd == pytest.approx(12.5)
    assert summary.by_scope == {"training_job": 10.0, "deployment": 2.5}
    assert summary.by_kind == {"training": 10.0, "inference": 2.5}
    assert summary.event_count == 2


def test_summarize_usage_empty() -> None:
    summary = summarize_usage(uuid4(), [])
    assert summary.total_cost_usd == 0.0
    assert summary.event_count == 0


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def test_termination_fixture_shapes() -> None:
    fields = termination_spec_fields()
    assert fields["name"] == "Search termination intelligence"
    assert fields["intelligence_primitive"].value == "termination"
    assert fields["input_schema"] == {"search_state": {"type": "object"}}
    assert fields["output_schema"] == {
        "decision": {"enum": ["continue", "stop"]},
        "confidence": {"type": "number"},
    }
    assert fields["latency_requirements"] == {"latency_budget_ms": 50}
    # kwargs for IntelligenceSpec minus id/project_id — must validate.
    spec = IntelligenceSpec(id=uuid4(), project_id=uuid4(), **fields)
    assert spec.problem_statement

    rows = termination_dataset_rows()
    assert len(rows) == 12
    assert all(set(r) == {"state_summary", "depth", "progress_score", "label"} for r in rows)
    assert all(r["label"] in ("continue", "stop") for r in rows)


def test_termination_fixture_is_a_believable_bar() -> None:
    """Sanity: the fixture really yields majority≈0.67 / keyword≈0.83 / rule≈0.92."""
    from collections import Counter

    rows = termination_dataset_rows()
    labels = [r["label"] for r in rows]
    assert Counter(labels).most_common(1)[0][1] / len(rows) == pytest.approx(0.67, abs=0.01)
