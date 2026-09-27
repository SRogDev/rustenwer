"""Phase 4: inference pipeline + providers + intelligence deployments.

TDD: written RED before the implementation. Covers plan §33 (deploy an
Intelligence; machine-readable outputs) and §34 (InferenceProvider).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from shared.domain import IntelligencePrimitive


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer <redacted>"}


def _repos(client: TestClient) -> dict[str, Any]:
    return client.app.state.test_repos  # type: ignore[attr-defined]


def _project(client: TestClient, auth: dict[str, str]) -> UUID:
    resp = client.post("/api/v1/projects", json={"name": "p4-infer"}, headers=auth)
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


def _spec(client: TestClient, auth: dict[str, str], project_id: UUID) -> UUID:
    resp = client.post(
        f"/api/v1/projects/{project_id}/specs",
        json={
            "name": "termination spec",
            "problem_statement": "Decide when a search should stop.",
            "intelligence_primitive": "termination",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


def _termination_version(
    client: TestClient, auth: dict[str, str], project_id: UUID
) -> tuple[UUID, UUID]:
    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={"name": "term-intel", "primitive": "termination"},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    intel_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/intelligences/{intel_id}/versions",
        json={
            "components": {},
            "architecture": {
                "kind": "deterministic_rule",
                "components": [
                    {
                        "kind": "deterministic_rule",
                        "label": "progress rule",
                        "config": {
                            "column": "progress_score",
                            "threshold": 0.21,
                            "left_label": "stop",
                            "right_label": "continue",
                            "fallback_label": "continue",
                        },
                    }
                ],
                "execution_order": [0],
            },
            "input_schema": {
                "progress_score": {"type": "number", "required": True},
                "depth": {"type": "number"},
            },
            "notes": "v1",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return intel_id, UUID(resp.json()["id"])


def _deploy(
    client: TestClient,
    auth: dict[str, str],
    project_id: UUID,
    spec_id: UUID,
    intelligence_version_id: UUID,
    activate: bool = True,
) -> UUID:
    resp = client.post(
        f"/api/v1/projects/{project_id}/deployments",
        json={
            "name": "term-deploy",
            "spec_id": str(spec_id),
            "intelligence_version_id": str(intelligence_version_id),
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["intelligence_version_id"] == str(intelligence_version_id)
    assert body["endpoint_url"] == f"/api/v1/deployments/{body['id']}/infer"
    deployment_id = UUID(body["id"])
    if activate:
        resp = client.patch(
            f"/api/v1/deployments/{deployment_id}",
            json={"status": "ACTIVE"},
            headers=auth,
        )
        assert resp.status_code == 200, resp.text
    return deployment_id


# --------------------------------------------------------------------------
# Inference pipeline
# --------------------------------------------------------------------------


def test_infer_termination_stop(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"progress_score": 0.10, "depth": 2}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["output"] == {"decision": "stop", "confidence": 1.0}
    assert body["primitive"] == IntelligencePrimitive.TERMINATION.value
    assert body["intelligence_version_id"] == str(version_id)
    assert body["provider"] == "rustenwer_hosted"
    assert body["latency_ms"] >= 0


def test_infer_termination_continue(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"progress_score": 0.90}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["output"]["decision"] == "continue"


def test_infer_rejects_missing_required_input(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"depth": 3}},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "progress_score" in resp.json()["detail"]


def test_infer_rejects_wrong_input_type(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"progress_score": "high"}},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text


def test_infer_inactive_deployment_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)
    deployment_id = _deploy(
        client, auth_headers, project_id, spec_id, version_id, activate=False
    )

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"progress_score": 0.5}},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


def test_infer_records_usage_event(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"progress_score": 0.5}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    repos = client.app.state.test_repos  # type: ignore[attr-defined]
    events = repos["usage"].list_events(project_id)
    inference_events = [e for e in events if e.scope.value == "inference"]
    assert len(inference_events) == 1
    assert inference_events[0].scope_id == deployment_id
    assert inference_events[0].cost_usd == 0.0


def test_deploy_requires_exactly_one_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    _, version_id = _termination_version(client, auth_headers, project_id)

    resp = client.post(
        f"/api/v1/projects/{project_id}/deployments",
        json={"name": "bad", "spec_id": str(spec_id)},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text

    resp = client.post(
        f"/api/v1/projects/{project_id}/deployments",
        json={
            "name": "bad",
            "spec_id": str(spec_id),
            "intelligence_version_id": str(version_id),
            "model_version_id": str(version_id),  # both -> 409
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


def test_deploy_unknown_intelligence_version_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from uuid import uuid4

    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    resp = client.post(
        f"/api/v1/projects/{project_id}/deployments",
        json={
            "name": "ghost",
            "spec_id": str(spec_id),
            "intelligence_version_id": str(uuid4()),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------
# Back-compat: deploying a bare model_version_id
# --------------------------------------------------------------------------


def test_deploy_model_version_auto_creates_intelligence(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)

    resp = client.post(
        f"/api/v1/projects/{project_id}/models",
        json={"name": "legacy-model"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    model_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/models/{model_id}/versions",
        json={"architecture": {"kind": "mlp"}},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    model_version_id = UUID(resp.json()["id"])

    resp = client.post(
        f"/api/v1/projects/{project_id}/deployments",
        json={
            "name": "legacy-deploy",
            "spec_id": str(spec_id),
            "model_version_id": str(model_version_id),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # The old contract still works: the deployment now points at an
    # auto-created intelligence version wrapping the model.
    assert body["model_version_id"] == str(model_version_id)
    assert body["intelligence_version_id"] is not None

    repos = client.app.state.test_repos  # type: ignore[attr-defined]
    intel_version = repos["intelligence"].get_version_by_id(
        UUID(body["intelligence_version_id"])
    )
    assert intel_version is not None
    assert intel_version.architecture is not None
    assert intel_version.architecture.kind == "single_model"
    assert (
        intel_version.architecture.components[0].kind.value == "model_version"
    )
    assert intel_version.architecture.components[0].ref == str(model_version_id)

    intel = repos["intelligence"].get_intelligence(intel_version.intelligence_id)
    assert intel is not None and intel.project_id == project_id
    assert "(auto)" in intel.name


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------


def test_providers_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/v1/inference/providers", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    providers = {p["name"]: p for p in resp.json()}
    assert providers["rustenwer_hosted"]["functional"] is True
    assert providers["external_api"]["functional"] is False
    assert providers["local_gpu"]["functional"] is False


def test_prompt_component_fails_honestly(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={"name": "prompt-intel", "primitive": "decision"},
        headers=auth_headers,
    )
    intel_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/intelligences/{intel_id}/versions",
        json={
            "components": {},
            "architecture": {
                "kind": "llm_judge_threshold",
                "components": [
                    {
                        "kind": "prompt",
                        "label": "judge",
                        "config": {"template": "Decide: {x}"},
                    }
                ],
            },
            "input_schema": {"x": {"type": "string", "required": True}},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    version_id = UUID(resp.json()["id"])
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"x": "hello"}},
        headers=auth_headers,
    )
    assert resp.status_code == 501, resp.text
    assert "no LLM provider" in resp.json()["detail"]


# --------------------------------------------------------------------------
# Model component with real torch weights
# --------------------------------------------------------------------------


def _write_classifier_bundle(bundle_dir: Path) -> None:
    """A real exported bundle: tiny 2-feature MLP + config.json."""
    torch = pytest.importorskip("torch")
    from app.evaluation.subjects import _rebuild_mlp

    model = _rebuild_mlp(n_features=2, n_classes=2, hp={"hidden": [4]}, seed=0)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict()}, bundle_dir / "model.pt")
    (bundle_dir / "config.json").write_text(
        json.dumps(
            {
                "training_method": "classifier",
                "n_features": 2,
                "n_classes": 2,
                "hyperparameters": {"hidden": [4]},
                "seed": 0,
            }
        ),
        encoding="utf-8",
    )


def test_model_component_real_prediction(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    torch = pytest.importorskip("torch")
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)

    bundle = tmp_path / "bundle"
    _write_classifier_bundle(bundle)

    resp = client.post(
        f"/api/v1/projects/{project_id}/models",
        json={"name": "tiny-clf"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    model_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/models/{model_id}/versions",
        json={
            "artifact_uri": str(bundle),
            "architecture": {"n_classes": 2, "kind": "mlp"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    model_version_id = UUID(resp.json()["id"])

    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={"name": "clf-intel", "primitive": "classification"},
        headers=auth_headers,
    )
    intel_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/intelligences/{intel_id}/versions",
        json={
            "components": {},
            "architecture": {
                "kind": "single_model",
                "components": [
                    {
                        "kind": "model_version",
                        "ref": str(model_version_id),
                        "label": "tiny classifier",
                        "config": {"classes": ["no", "yes"], "feature_key": "x"},
                    }
                ],
            },
            "input_schema": {"x": {"type": "array", "required": True}},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    version_id = UUID(resp.json()["id"])
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"x": [0.5, -0.3]}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    output = resp.json()["output"]
    assert set(output.keys()) == {"label", "probabilities"}
    assert output["label"] in ("no", "yes")
    assert abs(sum(output["probabilities"].values()) - 1.0) < 1e-6

    # Cross-check against the raw torch computation: same weights, same math.
    from app.evaluation.subjects import load_classifier_bundle

    repos = client.app.state.test_repos  # type: ignore[attr-defined]
    version = repos["model"].get_version(model_version_id)
    _, model, _ = load_classifier_bundle(version, Path("/tmp"))
    with torch.no_grad():
        logits = model(torch.tensor([[0.5, -0.3]], dtype=torch.float32))
        expected = ["no", "yes"][int(torch.argmax(logits, dim=1).item())]
    assert output["label"] == expected


def test_model_component_rejects_unpinned_classes(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    pytest.importorskip("torch")
    project_id = _project(client, auth_headers)
    spec_id = _spec(client, auth_headers, project_id)
    bundle = tmp_path / "bundle"
    _write_classifier_bundle(bundle)

    resp = client.post(
        f"/api/v1/projects/{project_id}/models",
        json={"name": "tiny-clf-2"},
        headers=auth_headers,
    )
    model_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/models/{model_id}/versions",
        json={"artifact_uri": str(bundle), "architecture": {"n_classes": 2}},
        headers=auth_headers,
    )
    model_version_id = UUID(resp.json()["id"])

    resp = client.post(
        f"/api/v1/projects/{project_id}/intelligences",
        json={"name": "clf-intel-2", "primitive": "classification"},
        headers=auth_headers,
    )
    intel_id = UUID(resp.json()["id"])
    resp = client.post(
        f"/api/v1/intelligences/{intel_id}/versions",
        json={
            "components": {},
            "architecture": {
                "kind": "single_model",
                "components": [
                    {
                        "kind": "model_version",
                        "ref": str(model_version_id),
                        "label": "unpinned",
                        "config": {"classes": ["only-one"]},
                    }
                ],
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    version_id = UUID(resp.json()["id"])
    deployment_id = _deploy(client, auth_headers, project_id, spec_id, version_id)

    resp = client.post(
        f"/api/v1/deployments/{deployment_id}/infer",
        json={"inputs": {"x": [0.5, -0.3]}},
        headers=auth_headers,
    )
    assert resp.status_code == 502, resp.text
    assert "classes" in resp.json()["detail"]
