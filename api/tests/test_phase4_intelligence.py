"""Phase 4: intelligence abstraction — architectures, version diff, inference.

Covers plan §2 (Intelligence != Model), §31 (intelligence as first-class
artifact, immutable versions), §32 (registry contents incl. diffs),
§33 (deployment serves an intelligence; machine-readable outputs),
§34 (InferenceProvider abstraction), §43 (immutable versioning).

TDD: these tests were written RED before the implementation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from shared.domain import ArchitectureComponentKind, IntelligenceVersion


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer <redacted>"}


@pytest.fixture
def intelligence_repository(client: TestClient):
    return client.app.state.test_repos["intelligence"]  # type: ignore[attr-defined]


@pytest.fixture
def project_id(client: TestClient, auth_headers: dict[str, str]) -> UUID:
    resp = client.post(
        "/api/v1/projects", json={"name": "phase4"}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


@pytest.fixture
def intelligence_id(
    client: TestClient, auth_headers: dict[str, str], project_id: UUID
) -> UUID:
    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={
            "name": "termination-intelligence",
            "description": "Decide when a search should stop.",
            "primitive": "termination",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


def _termination_architecture(threshold: float = 0.21) -> dict[str, Any]:
    return {
        "kind": "deterministic_rule",
        "components": [
            {
                "kind": "deterministic_rule",
                "label": "progress rule",
                "config": {
                    "column": "progress_score",
                    "threshold": threshold,
                    "left_label": "stop",
                    "right_label": "continue",
                    "fallback_label": "continue",
                },
            }
        ],
        "execution_order": [0],
    }


def _publish(
    client: TestClient,
    auth_headers: dict[str, str],
    intelligence_id: UUID,
    architecture: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "components": {"model_version_ids": [], "baseline_refs": [], "harness": {}},
        "notes": "v",
    }
    if architecture is not None:
        payload["architecture"] = architecture
    if extra:
        payload.update(extra)
    resp = client.post(
        f"/api/v1/intelligences/{intelligence_id}/versions",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# Architecture validation
# --------------------------------------------------------------------------


def test_publish_version_with_architecture_snapshot(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    body = _publish(client, auth_headers, intelligence_id, _termination_architecture())
    assert body["version"] == 1
    assert body["architecture"]["kind"] == "deterministic_rule"
    assert body["architecture"]["components"][0]["config"]["threshold"] == 0.21
    assert body["locked"] is True


def test_publish_rejects_unknown_baseline_ref(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    arch = {
        "kind": "heuristic_pipeline",
        "components": [{"kind": "baseline", "ref": "no_such_baseline", "label": "x"}],
    }
    resp = client.post(
        f"/api/v1/intelligences/{intelligence_id}/versions",
        json={"components": {}, "architecture": arch},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


def test_publish_rejects_unknown_model_version_ref(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    arch = {
        "kind": "single_model",
        "components": [
            {"kind": "model_version", "ref": str(uuid4()), "label": "ghost"}
        ],
    }
    resp = client.post(
        f"/api/v1/intelligences/{intelligence_id}/versions",
        json={"components": {}, "architecture": arch},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


def test_publish_rejects_malformed_rule_config(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    arch = {
        "kind": "deterministic_rule",
        "components": [
            {
                "kind": "deterministic_rule",
                "label": "broken",
                "config": {"column": "progress_score"},  # missing threshold/labels
            }
        ],
    }
    resp = client.post(
        f"/api/v1/intelligences/{intelligence_id}/versions",
        json={"components": {}, "architecture": arch},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


def test_publish_rejects_unknown_architecture_kind(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    resp = client.post(
        f"/api/v1/intelligences/{intelligence_id}/versions",
        json={"components": {}, "architecture": {"kind": "telepathy"}},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


def test_duplicate_version_number_rejected_at_repository(
    intelligence_repository,  # InMemoryIntelligenceRepository via conftest client
    intelligence_id: UUID,
) -> None:
    version = IntelligenceVersion(
        id=uuid4(),
        intelligence_id=intelligence_id,
        version=1,
        created_at="2026-09-27T00:00:00+00:00",
    )
    intelligence_repository.create_version(version)
    with pytest.raises(ValueError, match="already exists"):
        intelligence_repository.create_version(
            IntelligenceVersion(
                id=uuid4(),
                intelligence_id=intelligence_id,
                version=1,
                created_at="2026-09-27T00:00:00+00:00",
            )
        )


# --------------------------------------------------------------------------
# Version lookup by immutable id
# --------------------------------------------------------------------------


def test_get_version_by_id(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    version = _publish(
        client, auth_headers, intelligence_id, _termination_architecture()
    )
    resp = client.get(
        f"/api/v1/intelligence-versions/{version['id']}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == version["id"]
    assert body["version"] == 1

    resp = client.get(
        f"/api/v1/intelligence-versions/{uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------
# Version diff
# --------------------------------------------------------------------------


def test_diff_reports_threshold_change_and_added_component(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    _publish(client, auth_headers, intelligence_id, _termination_architecture(0.21))
    v2_arch = _termination_architecture(0.35)
    v2_arch["components"].append(
        {
            "kind": "threshold",
            "label": "depth guard",
            "config": {
                "input_key": "depth",
                "threshold": 10,
                "above": "stop",
                "below": "continue",
            },
        }
    )
    v2_arch["execution_order"] = [0, 1]
    _publish(client, auth_headers, intelligence_id, v2_arch)

    resp = client.get(
        f"/api/v1/intelligences/{intelligence_id}/versions/1/diff/2",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    diff = resp.json()
    assert diff["from_version"] == 1 and diff["to_version"] == 2
    assert diff["architecture_kind_changed"] is False
    assert len(diff["components_added"]) == 1
    assert diff["components_added"][0]["label"] == "depth guard"
    modified = diff["components_modified"]
    assert len(modified) == 1
    assert modified[0]["label"] == "progress rule"
    assert "threshold" in modified[0]["changed_config_keys"]
    assert diff["notes"], "diff should carry human-readable notes"


def test_diff_identical_versions_is_empty(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    _publish(client, auth_headers, intelligence_id, _termination_architecture())
    _publish(client, auth_headers, intelligence_id, _termination_architecture())
    resp = client.get(
        f"/api/v1/intelligences/{intelligence_id}/versions/1/diff/2",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    diff = resp.json()
    assert diff["changed_fields"] == []
    assert diff["components_added"] == []
    assert diff["components_removed"] == []
    assert diff["components_modified"] == []


def test_diff_missing_version_404(
    client: TestClient, auth_headers: dict[str, str], intelligence_id: UUID
) -> None:
    _publish(client, auth_headers, intelligence_id, _termination_architecture())
    resp = client.get(
        f"/api/v1/intelligences/{intelligence_id}/versions/1/diff/9",
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


def test_architecture_component_kind_values() -> None:
    assert ArchitectureComponentKind.DETERMINISTIC_RULE.value == "deterministic_rule"
    assert ArchitectureComponentKind.MODEL_VERSION.value == "model_version"
