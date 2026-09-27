"""Usage endpoints tests (TDD: RED first, then implement).

Contract under test (see shared/README.md):
  POST   /api/v1/projects/{id}/usage-events   -> 201
  GET    /api/v1/projects/{id}/usage/summary   -> UsageSummary (§45)
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient


def _record(
    client: TestClient, project_id: UUID, auth_headers: dict, **overrides
) -> dict:
    payload = {
        "scope": "training_job",
        "scope_id": str(uuid4()),
        "kind": "training",
        "quantity": 2.0,
        "unit": "gpu_hours",
        "cost_usd": 10.0,
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/projects/{project_id}/usage-events", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_record_usage_event(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _record(client, project_id, auth_headers)
    assert body["project_id"] == str(project_id)
    assert body["scope"] == "training_job"
    assert body["kind"] == "training"
    assert body["cost_usd"] == 10.0
    assert body["recorded_at"]


def test_usage_summary_aggregates(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    _record(client, project_id, auth_headers, cost_usd=10.0)
    _record(
        client,
        project_id,
        auth_headers,
        scope="deployment",
        kind="inference",
        quantity=1000.0,
        unit="requests",
        cost_usd=2.5,
    )
    resp = client.get(f"/api/v1/projects/{project_id}/usage/summary", headers=auth_headers)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["project_id"] == str(project_id)
    assert summary["total_cost_usd"] == 12.5
    assert summary["by_scope"] == {"training_job": 10.0, "deployment": 2.5}
    assert summary["by_kind"] == {"training": 10.0, "inference": 2.5}
    assert summary["event_count"] == 2


def test_usage_summary_empty(client: TestClient, project_id: UUID, auth_headers: dict) -> None:
    resp = client.get(f"/api/v1/projects/{project_id}/usage/summary", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total_cost_usd"] == 0.0
    assert resp.json()["event_count"] == 0


def test_record_event_unknown_project_404(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        f"/api/v1/projects/{uuid4()}/usage-events",
        json={"scope": "project", "scope_id": str(uuid4()), "kind": "storage"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
