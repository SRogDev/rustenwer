"""End-to-end graph tests (with the conftest `shared.services` doubles)."""

from __future__ import annotations

from uuid import uuid4

from agents.supervisor import build_supervisor_graph

_EXPECTED_NODES = {"intake", "specification", "dataset_check", "baselines", "strategy", "summarize"}


def _ml_state() -> dict:
    return {
        "messages": [],
        "project_id": str(uuid4()),
        "problem_statement": "predict whether a customer will churn next month",
        "phase": "intake",
        "notes": [],
        "spec": {
            "id": str(uuid4()),
            "project_id": str(uuid4()),
            "name": "Churn predictor",
            "problem_statement": "predict whether a customer will churn next month",
            "intelligence_primitive": "prediction",
            "evaluation_definition": "accuracy on holdout",
        },
        "dataset_rows": [
            {"tenure": i, "tickets": i % 3, "label": "churn" if i % 4 == 0 else "stay"}
            for i in range(12)
        ],
        "label_column": "label",
        "dataset_id": str(uuid4()),
        "dataset_version": 1,
    }


def _no_ml_state() -> dict:
    return {
        "messages": [],
        "project_id": str(uuid4()),
        "problem_statement": "validate and deduplicate uploaded customer emails",
        "phase": "intake",
        "notes": [],
        "dataset_rows": [
            {"email": f"user{i}@x.com", "label": "ok" if i % 2 else "dup"} for i in range(12)
        ],
        "label_column": "label",
    }


def test_graph_has_no_placeholder_nodes() -> None:
    graph = build_supervisor_graph()
    nodes = {n for n in graph.get_graph().nodes.keys() if not n.startswith("__")}
    assert nodes == _EXPECTED_NODES


def test_full_run_ml_path_reaches_strategy() -> None:
    final = build_supervisor_graph().invoke(_ml_state())
    assert final["diagnosis"]["ml_necessary"] is True
    assert final["no_ml_path"] is False
    assert final["dataset_report"]["row_count"] == 12
    assert final["baseline_report"]["best_baseline"] == "deterministic_rule"
    assert final["strategy"]["training_method"] != "none-deterministic"
    assert final["recommendation"]
    assert final["phase"] == "done"
    assert any("summarize" in n.lower() for n in final["notes"])


def test_full_run_no_ml_path_skips_strategy() -> None:
    final = build_supervisor_graph().invoke(_no_ml_state())
    assert final["diagnosis"]["ml_necessary"] is False
    assert final["no_ml_path"] is True
    assert final.get("strategy") is None  # short-circuited by routing
    assert final["baseline_report"]["best_baseline"] == "deterministic_rule"
    assert "deterministic_rule" in final["recommendation"]
    assert final["phase"] == "done"


def test_run_appends_trajectory_notes() -> None:
    final = build_supervisor_graph().invoke(_ml_state())
    joined = " ".join(final["notes"]).lower()
    for stage in ("intake", "specification", "dataset", "baseline", "strategy", "summarize"):
        assert stage in joined
