"""Projects CRUD tests (TDD: RED first, then implement).

Contract under test (see shared/README.md):
  GET    /api/v1/projects      -> list of the caller's org
  POST   /api/v1/projects      -> 201
  GET    /api/v1/projects/{id} -> 404 if missing or other org
  PATCH  /api/v1/projects/{id} -> update name/description/status
  DELETE /api/v1/projects/{id} -> soft archive (status=ARCHIVED)
All endpoints require a well-formed Bearer token (Phase-0 stub auth).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from shared.domain import Project, ProjectStatus

from app.projects import InMemoryProjectRepository

OTHER_ORG_ID = UUID("11111111-1111-1111-1111-111111111111")


def _other_org_project() -> Project:
    now = datetime.now().isoformat()
    return Project(
        id=uuid4(),
        organization_id=OTHER_ORG_ID,
        name="foreign project",
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def test_list_starts_empty(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/projects", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_create_returns_201_and_project_appears_in_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = {"name": "escalation-intelligence", "description": "support ticket triage"}
    response = client.post("/api/v1/projects", json=payload, headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "escalation-intelligence"
    assert body["description"] == "support ticket triage"
    assert body["status"] == "ACTIVE"
    assert UUID(body["id"])
    assert UUID(body["organization_id"])
    # timestamps are ISO-8601
    datetime.fromisoformat(body["created_at"])
    datetime.fromisoformat(body["updated_at"])

    listed = client.get("/api/v1/projects", headers=auth_headers).json()
    assert [p["id"] for p in listed] == [body["id"]]


def test_create_rejects_empty_name_with_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/projects", json={"name": ""}, headers=auth_headers)
    assert response.status_code == 422


def test_get_unknown_project_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/projects/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_get_other_org_project_returns_404(
    client: TestClient,
    repository: InMemoryProjectRepository,
    auth_headers: dict[str, str],
) -> None:
    foreign = _other_org_project()
    repository.create_project(foreign)

    response = client.get(f"/api/v1/projects/{foreign.id}", headers=auth_headers)
    assert response.status_code == 404

    # ...and it must not leak into the list either
    listed = client.get("/api/v1/projects", headers=auth_headers).json()
    assert listed == []


def test_patch_updates_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "v1"}, headers=auth_headers).json()[
        "id"
    ]

    response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "v2", "description": "updated", "status": "PAUSED"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "v2"
    assert body["description"] == "updated"
    assert body["status"] == "PAUSED"

    detail = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()
    assert detail["name"] == "v2"


def test_patch_unknown_project_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.patch(f"/api/v1/projects/{uuid4()}", json={"name": "x"}, headers=auth_headers)
    assert response.status_code == 404


def test_patch_empty_name_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "v1"}, headers=auth_headers).json()[
        "id"
    ]

    response = client.patch(
        f"/api/v1/projects/{project_id}", json={"name": ""}, headers=auth_headers
    )
    assert response.status_code == 422


def test_delete_archives_project_and_it_stays_retrievable(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = client.post(
        "/api/v1/projects", json={"name": "doomed"}, headers=auth_headers
    ).json()["id"]

    response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"

    detail = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "ARCHIVED"


def test_delete_unknown_project_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.delete(f"/api/v1/projects/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Token abc"}])
def test_endpoints_reject_missing_or_malformed_token_with_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    for method, url in (
        ("get", "/api/v1/projects"),
        ("post", "/api/v1/projects"),
        ("get", f"/api/v1/projects/{uuid4()}"),
        ("patch", f"/api/v1/projects/{uuid4()}"),
        ("delete", f"/api/v1/projects/{uuid4()}"),
    ):
        response = client.request(method, url, headers=headers)
        assert response.status_code == 401, f"{method} {url}"
        assert "detail" in response.json()
