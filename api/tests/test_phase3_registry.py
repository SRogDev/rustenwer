"""Phase 3: intelligence registry + model lineage (TDD RED -> GREEN).

Covers plan §31 (Intelligence as first-class artifact, separate from Model),
§32 (registry contents) and §43 (immutable versioning).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from shared.domain import Intelligence, Model, ModelVersion, Project

from app import models as models_module
from app.main import create_app
from app.projects import InMemoryProjectRepository
from app.projects import get_repository as get_project_repository
from app.registry import intelligences as intelligences_module
from app.registry import router as registry_router


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Fixtures (defined in-module; the registry router is wired here because
# api/app/main.py is owned by another writer and does not include it yet)
# --------------------------------------------------------------------------


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer <redacted>"}


@pytest.fixture
def project_repository() -> InMemoryProjectRepository:
    return InMemoryProjectRepository()


@pytest.fixture
def model_repository() -> models_module.InMemoryModelRepository:
    return models_module.InMemoryModelRepository()


@pytest.fixture
def intelligence_repository() -> intelligences_module.InMemoryIntelligenceRepository:
    return intelligences_module.InMemoryIntelligenceRepository()


@pytest.fixture
def client(
    project_repository: InMemoryProjectRepository,
    model_repository: models_module.InMemoryModelRepository,
    intelligence_repository: intelligences_module.InMemoryIntelligenceRepository,
) -> TestClient:
    application = create_app()
    if not any(
        getattr(route, "path", "").startswith("/api/v1/intelligences")
        for route in application.routes
    ):
        application.include_router(registry_router)
    application.dependency_overrides[get_project_repository] = lambda: project_repository
    application.dependency_overrides[models_module.get_model_repository] = (
        lambda: model_repository
    )
    application.dependency_overrides[intelligences_module.get_intelligence_repository] = (
        lambda: intelligence_repository
    )
    # The registry resolves model versions through this hook (which lazily
    # calls app.models.get_model_repository); override it with the per-test repo.
    application.dependency_overrides[intelligences_module.get_model_repository_hook] = (
        lambda: model_repository
    )
    return TestClient(application)


@pytest.fixture
def project_id(client: TestClient, auth_headers: dict[str, str]) -> UUID:
    resp = client.post(
        "/api/v1/projects", json={"name": "registry-test"}, headers=auth_headers
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


def _foreign_project_id(project_repository: InMemoryProjectRepository) -> UUID:
    """A project owned by a different organization (stub auth can't make one)."""
    pid = uuid4()
    project_repository.create_project(
        Project(
            id=pid,
            organization_id=uuid4(),
            name="foreign",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )
    return pid


def _create_model(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID, name: str = "m"
) -> UUID:
    resp = client.post(
        f"/api/v1/projects/{project_id}/models",
        json={"name": name},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


def _create_model_version(
    client: TestClient, auth_headers: dict[str, str], model_id: UUID, **fields: Any
) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/models/{model_id}/versions",
        json={"metrics": {}, **fields},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_intelligence(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID, **fields: Any
) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={"name": "intel", **fields},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_intelligence_version(
    client: TestClient,
    auth_headers: dict[str, str],
    intelligence_id: str,
    components: dict[str, Any],
    notes: str | None = None,
):
    payload: dict[str, Any] = {"components": components}
    if notes is not None:
        payload["notes"] = notes
    return client.post(
        f"/api/v1/intelligences/{intelligence_id}/versions",
        json=payload,
        headers=auth_headers,
    )


# --------------------------------------------------------------------------
# Immutability (§43)
# --------------------------------------------------------------------------


def test_model_repository_protocol_has_no_update_or_delete() -> None:
    for repo in (
        models_module.ModelRepository,
        models_module.InMemoryModelRepository,
    ):
        assert not hasattr(repo, "update_version")
        assert not hasattr(repo, "delete_version")


def test_intelligence_repository_protocol_has_no_update_or_delete() -> None:
    for repo in (
        intelligences_module.IntelligenceRepository,
        intelligences_module.InMemoryIntelligenceRepository,
    ):
        assert not hasattr(repo, "update_version")
        assert not hasattr(repo, "delete_version")


def test_model_version_numbers_auto_increment_and_first_is_immutable(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    model_id = _create_model(client, auth_headers, project_id)
    v1 = _create_model_version(
        client, auth_headers, model_id, seed=1, metrics={"accuracy": 0.8}
    )
    v1_snapshot = deepcopy(v1)
    v2 = _create_model_version(
        client, auth_headers, model_id, seed=2, metrics={"accuracy": 0.9}
    )
    assert v1["version"] == 1
    assert v2["version"] == 2
    reread = client.get(
        f"/api/v1/models/{model_id}/versions/1", headers=auth_headers
    )
    assert reread.status_code == 200
    assert reread.json() == v1_snapshot


# --------------------------------------------------------------------------
# get_version_by_number
# --------------------------------------------------------------------------


def test_get_version_by_number_hit_and_miss(
    client: TestClient,
    auth_headers: dict[str, str],
    project_id: UUID,
    model_repository: models_module.InMemoryModelRepository,
) -> None:
    model_id = _create_model(client, auth_headers, project_id)
    _create_model_version(client, auth_headers, model_id, seed=5)

    hit = client.get(f"/api/v1/models/{model_id}/versions/1", headers=auth_headers)
    assert hit.status_code == 200
    assert hit.json()["version"] == 1
    assert hit.json()["seed"] == 5

    miss = client.get(f"/api/v1/models/{model_id}/versions/99", headers=auth_headers)
    assert miss.status_code == 404

    assert model_repository.get_version_by_number(model_id, 1) is not None
    assert model_repository.get_version_by_number(model_id, 99) is None
    assert model_repository.get_version_by_number(uuid4(), 1) is None


def test_model_version_endpoints_404_on_foreign_org(
    client: TestClient,
    auth_headers: dict[str, str],
    project_repository: InMemoryProjectRepository,
    model_repository: models_module.InMemoryModelRepository,
) -> None:
    foreign_pid = _foreign_project_id(project_repository)
    mid = uuid4()
    model_repository.create_model(
        Model(id=mid, project_id=foreign_pid, name="foreign-model", created_at=_utc_now())
    )
    model_repository.create_version(
        ModelVersion(id=uuid4(), model_id=mid, version=1, created_at=_utc_now())
    )
    assert (
        client.get(f"/api/v1/models/{mid}/versions/1", headers=auth_headers).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/models/{mid}/lineage", headers=auth_headers).status_code
        == 404
    )


# --------------------------------------------------------------------------
# Lineage (§43)
# --------------------------------------------------------------------------


def test_model_version_carries_full_lineage(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    model_id = _create_model(client, auth_headers, project_id)
    dataset_version_id = str(uuid4())
    training_run_id = str(uuid4())
    _create_model_version(
        client,
        auth_headers,
        model_id,
        training_run_id=training_run_id,
        dataset_version_id=dataset_version_id,
        training_strategy={"name": "qlora", "rank": 8},
        code_version="abc123",
        template_version="tpl-7",
        seed=42,
        base_model="hf-org/bert-base",
        architecture={"name": "transformer"},
        size_bytes=1024,
        artifact_uri="s3://bucket/artifact",
        metrics={"accuracy": 0.91},
    )
    detail = client.get(
        f"/api/v1/models/{model_id}/versions/1", headers=auth_headers
    ).json()
    assert detail["training_run_id"] == training_run_id
    assert detail["dataset_version_id"] == dataset_version_id
    assert detail["training_strategy"] == {"name": "qlora", "rank": 8}
    assert detail["code_version"] == "abc123"
    assert detail["template_version"] == "tpl-7"
    assert detail["seed"] == 42
    assert detail["base_model"] == "hf-org/bert-base"
    assert detail["architecture"] == {"name": "transformer"}
    assert detail["size_bytes"] == 1024
    assert detail["artifact_uri"] == "s3://bucket/artifact"
    assert detail["metrics"] == {"accuracy": 0.91}


def test_lineage_diff_reports_changed_fields(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    model_id = _create_model(client, auth_headers, project_id)
    arch = {"name": "mlp", "layers": [64, 32]}
    _create_model_version(
        client, auth_headers, model_id, seed=1, metrics={"accuracy": 0.8}, architecture=arch
    )
    _create_model_version(
        client, auth_headers, model_id, seed=2, metrics={"accuracy": 0.9}, architecture=arch
    )
    resp = client.get(f"/api/v1/models/{model_id}/lineage", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert [v["version"] for v in body["versions"]] == [1, 2]
    assert len(body["changes"]) == 1
    change = body["changes"][0]
    assert change["from_version"] == 1
    assert change["to_version"] == 2
    assert set(change["changed_fields"]) == {"seed", "metrics"}


def test_lineage_single_version_has_no_changes(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    model_id = _create_model(client, auth_headers, project_id)
    _create_model_version(client, auth_headers, model_id)
    body = client.get(f"/api/v1/models/{model_id}/lineage", headers=auth_headers).json()
    assert len(body["versions"]) == 1
    assert body["changes"] == []


# --------------------------------------------------------------------------
# Intelligences (§31, §32)
# --------------------------------------------------------------------------


def test_create_intelligence(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    body = _create_intelligence(
        client,
        auth_headers,
        project_id,
        name="summarizer",
        description="summarizes docs",
        primitive="classification",
    )
    assert body["name"] == "summarizer"
    assert body["project_id"] == str(project_id)
    assert body["description"] == "summarizes docs"
    assert body["primitive"] == "classification"


def test_create_intelligence_minimal_defaults(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    body = _create_intelligence(client, auth_headers, project_id, name="bare")
    assert body["primitive"] is None
    assert body["description"] is None


def test_create_intelligence_rejects_unknown_primitive(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={"name": "x", "primitive": "telepathy"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_intelligence_unknown_project_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        f"/api/v1/projects/{uuid4()}/intelligences",
        json={"name": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_list_and_get_intelligence(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    a = _create_intelligence(client, auth_headers, project_id, name="a")
    b = _create_intelligence(client, auth_headers, project_id, name="b")
    listed = client.get(
        f"/api/v1/projects/{project_id}/intelligences", headers=auth_headers
    )
    assert listed.status_code == 200
    assert {i["id"] for i in listed.json()} == {a["id"], b["id"]}
    detail = client.get(f"/api/v1/intelligences/{a['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == a["id"]
    assert detail.json()["name"] == "a"


def test_intelligence_org_scoping_404(
    client: TestClient,
    auth_headers: dict[str, str],
    project_repository: InMemoryProjectRepository,
    intelligence_repository: intelligences_module.InMemoryIntelligenceRepository,
) -> None:
    foreign_pid = _foreign_project_id(project_repository)
    iid = uuid4()
    intelligence_repository.create_intelligence(
        Intelligence(id=iid, project_id=foreign_pid, name="foreign", created_at=_utc_now())
    )
    assert client.get(f"/api/v1/intelligences/{iid}", headers=auth_headers).status_code == 404
    assert (
        client.get(f"/api/v1/intelligences/{iid}/versions", headers=auth_headers).status_code
        == 404
    )
    resp = _post_intelligence_version(client, auth_headers, str(iid), {})
    assert resp.status_code == 404


def test_intelligence_404s(client: TestClient, auth_headers: dict[str, str]) -> None:
    missing = str(uuid4())
    assert client.get(f"/api/v1/intelligences/{missing}", headers=auth_headers).status_code == 404
    assert (
        client.get(f"/api/v1/intelligences/{missing}/versions", headers=auth_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/intelligences/{missing}/versions/1", headers=auth_headers
        ).status_code
        == 404
    )
    resp = _post_intelligence_version(client, auth_headers, missing, {})
    assert resp.status_code == 404
    assert (
        client.post(f"/api/v1/intelligences/{missing}/promote", headers=auth_headers).status_code
        == 404
    )


def test_intelligence_version_chain_and_resolved_lineage(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    model_id = _create_model(client, auth_headers, project_id, name="ranker")
    mv1 = _create_model_version(
        client, auth_headers, model_id, seed=11, code_version="c1", architecture={"name": "mlp"}
    )
    mv2 = _create_model_version(
        client, auth_headers, model_id, seed=22, code_version="c2", architecture={"name": "mlp"}
    )
    intel = _create_intelligence(client, auth_headers, project_id, name="ranker-intel")

    v1_resp = _post_intelligence_version(
        client,
        auth_headers,
        intel["id"],
        {
            "model_version_ids": [mv1["id"]],
            "baseline_refs": ["keyword"],
            "harness": {"kind": "local"},
        },
        notes="first",
    )
    assert v1_resp.status_code == 201
    v1 = v1_resp.json()
    assert v1["version"] == 1
    v1_snapshot = deepcopy(v1)

    v2_resp = _post_intelligence_version(
        client,
        auth_headers,
        intel["id"],
        {
            "model_version_ids": [mv1["id"], mv2["id"]],
            "baseline_refs": ["keyword", "majority"],
            "harness": {"kind": "local", "timeout_s": 30},
        },
        notes="second",
    )
    assert v2_resp.status_code == 201
    assert v2_resp.json()["version"] == 2

    # v1 is unchanged by the second publish (immutability)
    reread_v1 = client.get(
        f"/api/v1/intelligences/{intel['id']}/versions/1", headers=auth_headers
    )
    assert reread_v1.status_code == 200
    assert reread_v1.json()["components"] == v1_snapshot["components"]
    assert reread_v1.json()["notes"] == v1_snapshot["notes"]

    chain = client.get(
        f"/api/v1/intelligences/{intel['id']}/versions", headers=auth_headers
    )
    assert chain.status_code == 200
    assert [v["version"] for v in chain.json()] == [1, 2]

    detail = client.get(
        f"/api/v1/intelligences/{intel['id']}/versions/2", headers=auth_headers
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["version"] == 2
    assert body["baseline_refs"] == ["keyword", "majority"]
    assert body["harness"] == {"kind": "local", "timeout_s": 30}
    resolved = {c["model_version_id"]: c for c in body["resolved_components"]}
    assert set(resolved) == {mv1["id"], mv2["id"]}
    assert resolved[mv1["id"]]["model_name"] == "ranker"
    assert resolved[mv1["id"]]["version"] == 1
    assert resolved[mv1["id"]]["architecture_summary"] == "mlp"
    assert resolved[mv1["id"]]["seed"] == 11
    assert resolved[mv1["id"]]["code_version"] == "c1"
    assert resolved[mv2["id"]]["version"] == 2
    assert resolved[mv2["id"]]["seed"] == 22


def test_intelligence_version_number_miss_404(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    intel = _create_intelligence(client, auth_headers, project_id)
    resp = client.get(
        f"/api/v1/intelligences/{intel['id']}/versions/7", headers=auth_headers
    )
    assert resp.status_code == 404


def test_intelligence_version_rejects_unknown_model_version(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    intel = _create_intelligence(client, auth_headers, project_id)
    resp = _post_intelligence_version(
        client, auth_headers, intel["id"], {"model_version_ids": [str(uuid4())]}
    )
    assert resp.status_code == 409


def test_promote_is_phase6_stub(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> None:
    intel = _create_intelligence(client, auth_headers, project_id)
    resp = client.post(
        f"/api/v1/intelligences/{intel['id']}/promote", headers=auth_headers
    )
    assert resp.status_code == 501
    assert resp.json()["detail"] == (
        "Candidate promotion is implemented in Phase 6 (Candidate Experiment Engine)."
    )
