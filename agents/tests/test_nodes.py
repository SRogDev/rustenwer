"""Unit tests for the Phase-1 node functions.

`shared.services.*` are the conftest test doubles here — these tests verify
orchestration (Rule 3), not the deterministic domain logic.
"""

from __future__ import annotations

from uuid import uuid4

from agents.nodes.dataset import dataset_node
from agents.nodes.evaluation import evaluation_node
from agents.nodes.routing import route_after_baselines
from agents.nodes.specification import specification_node
from agents.nodes.strategy import strategy_node


def _ml_spec_dict() -> dict:
    return {
        "id": str(uuid4()),
        "project_id": str(uuid4()),
        "name": "Ticket classifier",
        "problem_statement": "classify incoming support tickets into categories",
        "intelligence_primitive": "classification",
        "constraints": ["latency under 100ms"],
        "evaluation_definition": "accuracy on holdout",
    }


def _dataset_rows() -> list[dict]:
    return [
        {"text": f"ticket {i}", "length": 10 + i, "label": "a" if i % 2 else "b"} for i in range(12)
    ]


# --- specification -------------------------------------------------------


def test_specification_node_from_existing_spec_dict() -> None:
    state = {"spec": _ml_spec_dict(), "notes": [], "phase": "intake"}
    update = specification_node(state)
    assert isinstance(update["diagnosis"], dict)
    assert update["diagnosis"]["primitive"] == "classification"
    assert update["diagnosis"]["ml_necessary"] is True
    assert update["no_ml_path"] is False
    assert update["phase"] == "specification"
    assert update["spec"]["name"] == "Ticket classifier"


def test_specification_node_synthesizes_spec_from_problem_statement() -> None:
    state = {
        "problem_statement": "deduplicate rows in the uploaded csv by email",
        "notes": [],
        "phase": "intake",
    }
    update = specification_node(state)
    assert update["spec"]["problem_statement"] == "deduplicate rows in the uploaded csv by email"
    assert update["diagnosis"]["ml_necessary"] is False  # deterministic pattern, no learning signal
    assert update["no_ml_path"] is True


def test_specification_node_appends_note() -> None:
    update = specification_node({"spec": _ml_spec_dict(), "notes": ["a"], "phase": "intake"})
    assert update["notes"] == ["a", update["notes"][1]]
    assert "specification" in update["notes"][1].lower()


# --- dataset -------------------------------------------------------------


def test_dataset_node_stores_report() -> None:
    state = {
        "dataset_rows": _dataset_rows(),
        "label_column": "label",
        "dataset_id": str(uuid4()),
        "dataset_version": 1,
        "notes": [],
        "phase": "specification",
    }
    update = dataset_node(state)
    report = update["dataset_report"]
    assert report["row_count"] == 12
    assert report["ready_for_training"] is True
    assert report["column_schema"]["length"] == "int"
    assert update["phase"] == "dataset_check"


def test_dataset_node_defaults_label_column() -> None:
    update = dataset_node({"dataset_rows": _dataset_rows(), "notes": [], "phase": "specification"})
    assert update["dataset_report"]["class_balance"] is None


# --- strategy ------------------------------------------------------------


def test_strategy_node_ml_path_picks_training_method() -> None:
    state = {
        "spec": _ml_spec_dict(),
        "diagnosis": {
            "spec_id": str(uuid4()),
            "ml_necessary": True,
            "primitive": "classification",
            "rationale": "r",
            "candidate_approaches": ["lora"],
            "data_requirements": [],
            "success_metrics": [],
            "key_constraints": [],
            "diagnosed_at": "2026-09-26T00:00:00+00:00",
        },
        "baseline_report": {
            "spec_id": str(uuid4()),
            "dataset_version_id": str(uuid4()),
            "baselines": [],
            "best_baseline": "deterministic_rule",
            "bar_to_beat": {"accuracy": 0.92, "latency_ms_p50": 0.03, "cost_usd_per_1k": 0.0},
            "evaluated_at": "2026-09-26T00:00:00+00:00",
        },
        "notes": [],
        "phase": "baselines",
    }
    update = strategy_node(state)
    strategy = update["strategy"]
    assert strategy["training_method"] not in (None, "none-deterministic")
    assert strategy["baseline_bar"]["accuracy"] == 0.92
    assert update["phase"] == "strategy"


def test_strategy_node_no_ml_path_uses_none_deterministic() -> None:
    state = {
        "spec": {
            **_ml_spec_dict(),
            "problem_statement": "deduplicate rows in the uploaded csv by email",
            "intelligence_primitive": "filtering",
        },
        "diagnosis": {
            "spec_id": str(uuid4()),
            "ml_necessary": False,
            "primitive": "filtering",
            "rationale": "r",
            "candidate_approaches": ["deterministic_rule"],
            "data_requirements": [],
            "success_metrics": [],
            "key_constraints": [],
            "diagnosed_at": "2026-09-26T00:00:00+00:00",
        },
        "baseline_report": None,
        "notes": [],
        "phase": "baselines",
    }
    update = strategy_node(state)
    strategy = update["strategy"]
    assert strategy["training_method"] == "none-deterministic"
    assert strategy["model_family"] is None
    assert strategy["no_training_justification"]  # Rule 2/13 representable


# --- evaluation ----------------------------------------------------------


def test_evaluation_node_stores_baseline_report_and_recommendation() -> None:
    state = {
        "spec": _ml_spec_dict(),
        "diagnosis": {
            "spec_id": str(uuid4()),
            "ml_necessary": True,
            "primitive": "classification",
            "rationale": "r",
            "candidate_approaches": [],
            "data_requirements": [],
            "success_metrics": [],
            "key_constraints": [],
            "diagnosed_at": "2026-09-26T00:00:00+00:00",
        },
        "dataset_rows": _dataset_rows(),
        "label_column": "label",
        "notes": [],
        "phase": "dataset_check",
    }
    update = evaluation_node(state)
    report = update["baseline_report"]
    assert [b["name"] for b in report["baselines"]] == [
        "majority_class",
        "keyword_heuristic",
        "deterministic_rule",
    ]
    assert report["best_baseline"] == "deterministic_rule"
    assert isinstance(update["recommendation"], str) and update["recommendation"]
    assert "train" in update["recommendation"].lower()  # ML path → beat the bar
    assert update["phase"] == "baselines"


def test_evaluation_node_no_ml_path_promotes_best_baseline() -> None:
    state = {
        "spec": {
            **_ml_spec_dict(),
            "problem_statement": "deduplicate rows in the uploaded csv by email",
            "intelligence_primitive": "filtering",
        },
        "diagnosis": {
            "spec_id": str(uuid4()),
            "ml_necessary": False,
            "primitive": "filtering",
            "rationale": "r",
            "candidate_approaches": [],
            "data_requirements": [],
            "success_metrics": [],
            "key_constraints": [],
            "diagnosed_at": "2026-09-26T00:00:00+00:00",
        },
        "dataset_rows": _dataset_rows(),
        "label_column": "label",
        "notes": [],
        "phase": "dataset_check",
    }
    update = evaluation_node(state)
    assert "deterministic_rule" in update["recommendation"]
    assert "promote best baseline" in update["recommendation"].lower()
    assert "beat the bar" not in update["recommendation"].lower()


# --- routing -------------------------------------------------------------


def test_route_after_baselines_ml_goes_to_strategy() -> None:
    assert route_after_baselines({"diagnosis": {"ml_necessary": True}}) == "strategy"


def test_route_after_baselines_no_ml_goes_to_summarize() -> None:
    assert route_after_baselines({"diagnosis": {"ml_necessary": False}}) == "summarize"


def test_route_after_baselines_missing_diagnosis_summarizes() -> None:
    assert route_after_baselines({}) == "summarize"
