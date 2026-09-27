"""Specs endpoints tests (TDD: RED first, then implement).

Contract under test (see shared/README.md):
  POST   /api/v1/projects/{id}/specs       -> 201 (DRAFT)
  GET    /api/v1/projects/{id}/specs       -> list specs of a project
  GET    /api/v1/specs/{spec_id}            -> detail or 404
  PATCH  /api/v1/specs/{spec_id}            -> update DRAFT fields; 409 when not DRAFT
  POST   /api/v1/specs/{spec_id}/diagnose   -> DiagnosisResult; status -> DIAGNOSED
  POST   /api/v1/specs/{spec_id}/approve    -> DRAFT/DIAGNOSED -> APPROVED; 409 otherwise
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from shared.domain import IntelligencePrimitive, IntelligenceSpec, IntelligenceSpecStatus, Project

from app import specs as specs_module

OTHER_ORG_ID = UUID("22222222-2222-2222-2222-222222222222")


def _spec_payload(**overrides) -> dict:
    payload = {
        "name": "Churn classifier",
        "problem_statement": "Predict which customers will churn next month.",
        "intelligence_primitive": "classification",
    }
    payload.update(overrides)
    return payload


def _create_spec(client: TestClient, project_id: UUID, auth_headers: dict, **overrides) -> dict:
    resp = client.post(
        f"/api/v1/projects/{project_id}/specs",
        json=_spec_payload(**overrides),
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_spec_returns_draft(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_spec(client, project_id, auth_headers)
    assert body["status"] == "DRAFT"
    assert body["version"] == 1
    assert body["project_id"] == str(project_id)
    assert body["intelligence_primitive"] == "classification"


def test_create_spec_unknown_project_404(
    client: TestClient, auth_headers: dict
) -> None:
    resp = client.post(
        f"/api/v1/projects/{uuid4()}/specs",
        json=_spec_payload(),
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_list_specs(client: TestClient, project_id: UUID, auth_headers: dict) -> None:
    _create_spec(client, project_id, auth_headers, name="Spec A")
    _create_spec(client, project_id, auth_headers, name="Spec B")
    resp = client.get(f"/api/v1/projects/{project_id}/specs", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(s["name"] for s in resp.json()) == ["Spec A", "Spec B"]


def test_get_spec_detail(client: TestClient, project_id: UUID, auth_headers: dict) -> None:
    body = _create_spec(client, project_id, auth_headers)
    resp = client.get(f"/api/v1/specs/{body['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == body["id"]


def test_get_spec_unknown_404(client: TestClient, auth_headers: dict) -> None:
    resp = client.get(f"/api/v1/specs/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_spec_detail_other_org_404(
    client: TestClient,
    auth_headers: dict,
    repository,
    spec_repository: specs_module.InMemorySpecRepository,
) -> None:
    now = datetime.now(UTC).isoformat()
    other_project = Project(
        id=uuid4(),
        organization_id=OTHER_ORG_ID,
        name="Other org project",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    repository.create_project(other_project)
    spec = IntelligenceSpec(
        id=uuid4(),
        project_id=other_project.id,
        name="Foreign spec",
        problem_statement="Classify things.",
        intelligence_primitive=IntelligencePrimitive.CLASSIFICATION,
    )
    spec_repository.create_spec(spec)
    resp = client.get(f"/api/v1/specs/{spec.id}", headers=auth_headers)
    assert resp.status_code == 404


def test_patch_spec_draft_fields(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_spec(client, project_id, auth_headers)
    resp = client.patch(
        f"/api/v1/specs/{body['id']}",
        json={"name": "Renamed", "problem_statement": "Predict churn weekly."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["problem_statement"] == "Predict churn weekly."


def test_patch_spec_rejected_when_not_draft(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_spec(client, project_id, auth_headers)
    client.post(f"/api/v1/specs/{body['id']}/approve", headers=auth_headers)
    resp = client.patch(
        f"/api/v1/specs/{body['id']}", json={"name": "Nope"}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_diagnose_moves_to_diagnosed(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_spec(client, project_id, auth_headers)
    resp = client.post(f"/api/v1/specs/{body['id']}/diagnose", headers=auth_headers)
    assert resp.status_code == 200
    diagnosis = resp.json()
    assert diagnosis["spec_id"] == body["id"]
    assert diagnosis["ml_necessary"] is True
    assert diagnosis["primitive"] == "classification"
    assert diagnosis["candidate_approaches"][0] == "majority_class baseline"

    detail = client.get(f"/api/v1/specs/{body['id']}", headers=auth_headers).json()
    assert detail["status"] == "DIAGNOSED"


def test_diagnose_no_ml_conclusion(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_spec(
        client,
        project_id,
        auth_headers,
        problem_statement="Sort by timestamp, filter by language, and validate the output format.",
    )
    resp = client.post(f"/api/v1/specs/{body['id']}/diagnose", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ml_necessary"] is False


def test_diagnose_rejected_when_approved(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_spec(client, project_id, auth_headers)
    client.post(f"/api/v1/specs/{body['id']}/approve", headers=auth_headers)
    resp = client.post(f"/api/v1/specs/{body['id']}/diagnose", headers=auth_headers)
    assert resp.status_code == 409


def test_approve_from_draft_and_diagnosed(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    draft = _create_spec(client, project_id, auth_headers, name="Direct")
    resp = client.post(f"/api/v1/specs/{draft['id']}/approve", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    diagnosed = _create_spec(client, project_id, auth_headers, name="Via diagnose")
    client.post(f"/api/v1/specs/{diagnosed['id']}/diagnose", headers=auth_headers)
    resp = client.post(f"/api/v1/specs/{diagnosed['id']}/approve", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"


def test_approve_twice_409(client: TestClient, project_id: UUID, auth_headers: dict) -> None:
    body = _create_spec(client, project_id, auth_headers)
    client.post(f"/api/v1/specs/{body['id']}/approve", headers=auth_headers)
    resp = client.post(f"/api/v1/specs/{body['id']}/approve", headers=auth_headers)
    assert resp.status_code == 409


def test_endpoints_require_auth(client: TestClient, project_id: UUID) -> None:
    resp = client.get(f"/api/v1/projects/{project_id}/specs")
    assert resp.status_code == 401
    resp = client.post(f"/api/v1/projects/{project_id}/specs", json=_spec_payload())
    assert resp.status_code == 401
    assert IntelligenceSpecStatus.DRAFT == "DRAFT"  # contract sanity


def test_create_spec_without_primitive_auto_detects(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    """Omitting intelligence_primitive triggers keyword-based auto-detect."""
    payload = _spec_payload()
    del payload["intelligence_primitive"]
    payload["problem_statement"] = "Decide when the search should stop."
    resp = client.post(
        f"/api/v1/projects/{project_id}/specs",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["intelligence_primitive"] == "termination"


def test_create_spec_auto_detect_falls_back_to_decision(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    payload = _spec_payload()
    del payload["intelligence_primitive"]
    payload["problem_statement"] = "Do something vaguely intelligent with the data."
    resp = client.post(
        f"/api/v1/projects/{project_id}/specs",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["intelligence_primitive"] == "decision"
