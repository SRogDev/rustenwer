"""Models, deployments, and the termination demo endpoint (TDD: RED first).

Contract under test (see shared/README.md):
  POST   /api/v1/projects/{id}/models                 -> 201
  GET    /api/v1/projects/{id}/models                 -> list
  POST   /api/v1/models/{model_id}/versions           -> 201
  GET    /api/v1/models/{model_id}/versions           -> list
  POST   /api/v1/projects/{id}/deployments           -> 201 (DRAFT)
  GET    /api/v1/projects/{id}/deployments           -> list
  PATCH  /api/v1/deployments/{deployment_id}          -> {status}; 409 on invalid
  POST   /api/v1/projects/{id}/demo/termination       -> {spec, dataset, version, evaluation}
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def _create_model(client: TestClient, project_id: UUID, auth_headers: dict, **overrides) -> dict:
    payload = {"name": "termination-encoder", "description": "Demo model"}
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/projects/{project_id}/models", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_spec(client: TestClient, project_id: UUID, auth_headers: dict) -> dict:
    resp = client.post(
        f"/api/v1/projects/{project_id}/specs",
        json={
            "name": "S",
            "problem_statement": "Predict churn.",
            "intelligence_primitive": "classification",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------


def test_create_and_list_models(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    _create_model(client, project_id, auth_headers, name="m-a")
    _create_model(client, project_id, auth_headers, name="m-b")
    resp = client.get(f"/api/v1/projects/{project_id}/models", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(m["name"] for m in resp.json()) == ["m-a", "m-b"]


def test_model_versions_increment(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    model = _create_model(client, project_id, auth_headers)
    v1 = client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={"metrics": {"accuracy": 0.9}},
        headers=auth_headers,
    )
    assert v1.status_code == 201, v1.text
    assert v1.json()["version"] == 1

    v2 = client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={"metrics": {"accuracy": 0.93}},
        headers=auth_headers,
    )
    assert v2.json()["version"] == 2

    listing = client.get(
        f"/api/v1/models/{model['id']}/versions", headers=auth_headers
    ).json()
    assert sorted(v["version"] for v in listing) == [1, 2]

    assert (
        client.post(
            f"/api/v1/models/{uuid4()}/versions", json={}, headers=auth_headers
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------
# deployments
# --------------------------------------------------------------------------


def _create_deployment(
    client: TestClient, project_id: UUID, auth_headers: dict, **overrides
) -> dict:
    spec = _create_spec(client, project_id, auth_headers)
    payload = {"name": "prod", "spec_id": spec["id"]}
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/projects/{project_id}/deployments", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_deployment_lifecycle(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    deployment = _create_deployment(client, project_id, auth_headers)
    assert deployment["status"] == "DRAFT"
    deployment_id = deployment["id"]

    for target in ["ACTIVE", "PAUSED", "ACTIVE", "ARCHIVED"]:
        resp = client.patch(
            f"/api/v1/deployments/{deployment_id}",
            json={"status": target},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target


def test_deployment_invalid_transition_409(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    deployment = _create_deployment(client, project_id, auth_headers)
    resp = client.patch(
        f"/api/v1/deployments/{deployment['id']}",
        json={"status": "PAUSED"},  # DRAFT -> PAUSED is illegal
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_deployment_cancel_from_anywhere(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    deployment = _create_deployment(client, project_id, auth_headers)
    client.patch(
        f"/api/v1/deployments/{deployment['id']}",
        json={"status": "ACTIVE"},
        headers=auth_headers,
    )
    resp = client.patch(
        f"/api/v1/deployments/{deployment['id']}",
        json={"status": "ARCHIVED"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ARCHIVED"
    resp = client.patch(
        f"/api/v1/deployments/{deployment['id']}",
        json={"status": "ACTIVE"},
        headers=auth_headers,
    )
    assert resp.status_code == 409  # ARCHIVED is terminal


def test_list_deployments(client: TestClient, project_id: UUID, auth_headers: dict) -> None:
    _create_deployment(client, project_id, auth_headers, name="d-a")
    _create_deployment(client, project_id, auth_headers, name="d-b")
    resp = client.get(f"/api/v1/projects/{project_id}/deployments", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(d["name"] for d in resp.json()) == ["d-a", "d-b"]


# --------------------------------------------------------------------------
# demo
# --------------------------------------------------------------------------


def test_demo_termination_seeds_and_evaluates(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    resp = client.post(
        f"/api/v1/projects/{project_id}/demo/termination", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    spec = body["spec"]
    assert spec["name"] == "Search termination intelligence"
    assert spec["intelligence_primitive"] == "termination"
    assert spec["status"] == "DIAGNOSED"  # demo diagnoses the seeded spec

    dataset = body["dataset"]
    assert dataset["project_id"] == str(project_id)

    version = body["version"]
    assert version["dataset_id"] == dataset["id"]
    assert version["stats"]["row_count"] == 12
    assert version["stats"]["ready_for_training"] is True

    evaluation = body["evaluation"]
    assert evaluation["status"] == "COMPLETED"
    assert evaluation["spec_id"] == spec["id"]
    assert evaluation["dataset_version_id"] == version["id"]
    bar = evaluation["results"]["bar_to_beat"]
    assert bar["accuracy"] == pytest.approx(11 / 12)


def test_demo_termination_unknown_project_404(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        f"/api/v1/projects/{uuid4()}/demo/termination", headers=auth_headers
    )
    assert resp.status_code == 404
