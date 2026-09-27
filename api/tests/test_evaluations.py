"""Evaluations endpoints tests (TDD: RED first, then implement).

Contract under test (see shared/README.md):
  POST   /api/v1/projects/{id}/evaluations/run   -> 201 Evaluation (COMPLETED)
  GET    /api/v1/projects/{id}/evaluations       -> list
  GET    /api/v1/evaluations/{evaluation_id}      -> detail
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from shared.services.fixtures import termination_dataset_rows, termination_spec_fields


def _seed_spec_and_version(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> tuple[str, str]:
    """Create a spec + dataset version from the termination fixture; return ids."""
    spec_payload = {
        "name": termination_spec_fields()["name"],
        "problem_statement": termination_spec_fields()["problem_statement"],
        "intelligence_primitive": "termination",
        "input_schema": termination_spec_fields()["input_schema"],
        "output_schema": termination_spec_fields()["output_schema"],
    }
    spec = client.post(
        f"/api/v1/projects/{project_id}/specs", json=spec_payload, headers=auth_headers
    ).json()
    dataset = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        json={"name": "termination-states"},
        headers=auth_headers,
    ).json()
    version = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions",
        json={"rows": termination_dataset_rows(), "label_column": "label"},
        headers=auth_headers,
    ).json()
    return spec["id"], version["id"]


def test_run_evaluation_completes_synchronously(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    spec_id, version_id = _seed_spec_and_version(client, project_id, auth_headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/evaluations/run",
        json={"name": "termination-baseline", "spec_id": spec_id, "dataset_version_id": version_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["spec_id"] == spec_id
    assert body["dataset_version_id"] == version_id
    assert body["completed_at"] is not None

    results = body["results"]
    assert len(results["baselines"]) == 3
    by_name = {b["name"]: b for b in results["baselines"]}
    assert by_name["majority_class"]["accuracy"] == pytest.approx(8 / 12)
    assert by_name["keyword_heuristic"]["accuracy"] == pytest.approx(10 / 12)
    assert by_name["deterministic_rule"]["accuracy"] == pytest.approx(11 / 12)
    assert results["bar_to_beat"]["accuracy"] == pytest.approx(11 / 12)
    assert results["recommendation"]  # must explain the outcome


def test_run_evaluation_unknown_spec_404(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    _, version_id = _seed_spec_and_version(client, project_id, auth_headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/evaluations/run",
        json={"spec_id": str(uuid4()), "dataset_version_id": version_id},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_run_evaluation_unknown_version_404(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    spec_id, _ = _seed_spec_and_version(client, project_id, auth_headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/evaluations/run",
        json={"spec_id": spec_id, "dataset_version_id": str(uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_list_and_get_evaluations(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    spec_id, version_id = _seed_spec_and_version(client, project_id, auth_headers)
    created = client.post(
        f"/api/v1/projects/{project_id}/evaluations/run",
        json={"spec_id": spec_id, "dataset_version_id": version_id},
        headers=auth_headers,
    ).json()

    resp = client.get(f"/api/v1/projects/{project_id}/evaluations", headers=auth_headers)
    assert resp.status_code == 200
    assert [e["id"] for e in resp.json()] == [created["id"]]

    detail = client.get(f"/api/v1/evaluations/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert client.get(f"/api/v1/evaluations/{uuid4()}", headers=auth_headers).status_code == 404
