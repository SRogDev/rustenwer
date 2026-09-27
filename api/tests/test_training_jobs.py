"""Training jobs + runs endpoints tests (TDD: RED first, then implement).

Contract under test (see shared/README.md):
  POST   /api/v1/projects/{id}/training-jobs          -> 201 (CREATED)
  GET    /api/v1/projects/{id}/training-jobs          -> list
  GET    /api/v1/training-jobs/{job_id}                -> detail
  POST   /api/v1/training-jobs/{job_id}/transition     -> 200; 409 on invalid (§42)
  GET    /api/v1/training-jobs/{job_id}/runs           -> list (empty until Phase 2)
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient


def _create_job(
    client: TestClient, project_id: UUID, auth_headers: dict, **overrides
) -> dict:
    payload = {"name": "termination-embedding-ft"}
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/projects/{project_id}/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_job_starts_created(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_job(client, project_id, auth_headers)
    assert body["status"] == "CREATED"
    assert body["project_id"] == str(project_id)
    assert body["spec_id"] is None


def test_create_job_with_spec_and_strategy(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    spec = client.post(
        f"/api/v1/projects/{project_id}/specs",
        json={
            "name": "S",
            "problem_statement": "Predict churn.",
            "intelligence_primitive": "classification",
        },
        headers=auth_headers,
    ).json()
    body = _create_job(
        client,
        project_id,
        auth_headers,
        spec_id=spec["id"],
        strategy={"training_method": "lora", "objective": "beat the bar"},
    )
    assert body["spec_id"] == spec["id"]
    assert body["strategy"]["training_method"] == "lora"


def test_list_and_get_jobs(client: TestClient, project_id: UUID, auth_headers: dict) -> None:
    _create_job(client, project_id, auth_headers, name="job-a")
    _create_job(client, project_id, auth_headers, name="job-b")
    resp = client.get(f"/api/v1/projects/{project_id}/training-jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(j["name"] for j in resp.json()) == ["job-a", "job-b"]

    job_id = resp.json()[0]["id"]
    detail = client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert client.get(f"/api/v1/training-jobs/{uuid4()}", headers=auth_headers).status_code == 404


def test_transition_happy_path(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(client, project_id, auth_headers)
    job_id = job["id"]
    for target in ["QUEUED", "RUNNING", "PAUSED", "RUNNING", "COMPLETED"]:
        resp = client.post(
            f"/api/v1/training-jobs/{job_id}/transition",
            json={"to": target},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target


def test_transition_invalid_409(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(client, project_id, auth_headers)
    resp = client.post(
        f"/api/v1/training-jobs/{job['id']}/transition",
        json={"to": "RUNNING"},  # CREATED -> RUNNING is illegal
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_transition_from_terminal_409(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(client, project_id, auth_headers)
    client.post(
        f"/api/v1/training-jobs/{job['id']}/transition",
        json={"to": "CANCELLED"},
        headers=auth_headers,
    )
    resp = client.post(
        f"/api/v1/training-jobs/{job['id']}/transition",
        json={"to": "QUEUED"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_transition_unknown_job_404(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        f"/api/v1/training-jobs/{uuid4()}/transition",
        json={"to": "QUEUED"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_list_runs_empty_until_phase2(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(client, project_id, auth_headers)
    resp = client.get(f"/api/v1/training-jobs/{job['id']}/runs", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []  # real GPU execution lands in Phase 2
