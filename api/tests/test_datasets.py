"""Datasets endpoints tests (TDD: RED first, then implement).

Contract under test (see shared/README.md):
  POST   /api/v1/projects/{id}/datasets                          -> 201
  GET    /api/v1/projects/{id}/datasets                          -> list
  GET    /api/v1/datasets/{dataset_id}                            -> detail
  POST   /api/v1/datasets/{dataset_id}/versions                  -> 201 DatasetVersion
  GET    /api/v1/datasets/{dataset_id}/versions                   -> list (no rows)
  GET    /api/v1/datasets/{dataset_id}/versions/{version}         -> detail (no rows)
  POST   /api/v1/datasets/{dataset_id}/versions/{version}/validate -> DatasetReport
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from shared.services.fixtures import termination_dataset_rows


def _rows_payload(**overrides) -> dict:
    payload = {"rows": termination_dataset_rows(), "label_column": "label"}
    payload.update(overrides)
    return payload


def _create_dataset(client: TestClient, project_id: UUID, auth_headers: dict, **overrides) -> dict:
    payload = {"name": "termination-states", "description": "Search states"}
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/projects/{project_id}/datasets", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_version(
    client: TestClient, dataset_id: str, auth_headers: dict, **overrides
) -> dict:
    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        json=_rows_payload(**overrides),
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_list_datasets(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    _create_dataset(client, project_id, auth_headers, name="ds-a")
    _create_dataset(client, project_id, auth_headers, name="ds-b")
    resp = client.get(f"/api/v1/projects/{project_id}/datasets", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(d["name"] for d in resp.json()) == ["ds-a", "ds-b"]


def test_get_dataset_detail(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    body = _create_dataset(client, project_id, auth_headers)
    resp = client.get(f"/api/v1/datasets/{body['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == body["id"]
    assert client.get(f"/api/v1/datasets/{uuid4()}", headers=auth_headers).status_code == 404


def test_create_version_computes_report(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    dataset = _create_dataset(client, project_id, auth_headers)
    version = _create_version(client, dataset["id"], auth_headers)

    assert version["version"] == 1
    assert version["dataset_id"] == dataset["id"]
    assert "rows" not in version  # rows never leave the server
    stats = version["stats"]
    assert stats["row_count"] == 12
    assert stats["class_balance"] == {"continue": 8, "stop": 4}
    assert stats["ready_for_training"] is True
    assert version["column_schema"]["progress_score"] == "float"

    # Dataset row_count tracks the latest version.
    detail = client.get(f"/api/v1/datasets/{dataset['id']}", headers=auth_headers).json()
    assert detail["row_count"] == 12


def test_version_numbers_increment(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    dataset = _create_dataset(client, project_id, auth_headers)
    v1 = _create_version(client, dataset["id"], auth_headers)
    v2 = _create_version(client, dataset["id"], auth_headers)
    assert (v1["version"], v2["version"]) == (1, 2)

    resp = client.get(f"/api/v1/datasets/{dataset['id']}/versions", headers=auth_headers)
    assert resp.status_code == 200
    assert sorted(v["version"] for v in resp.json()) == [1, 2]

    resp = client.get(
        f"/api/v1/datasets/{dataset['id']}/versions/2", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == v2["id"]
    assert "rows" not in resp.json()

    resp = client.get(
        f"/api/v1/datasets/{dataset['id']}/versions/99", headers=auth_headers
    )
    assert resp.status_code == 404


def test_validate_version_recomputes_report(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    dataset = _create_dataset(client, project_id, auth_headers)
    _create_version(client, dataset["id"], auth_headers)
    resp = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/1/validate", headers=auth_headers
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["row_count"] == 12
    assert report["leakage_flags"] == []
    assert report["recommended_split"] == {"train": 0.7, "validation": 0.15, "test": 0.15}


def test_create_version_unknown_dataset_404(
    client: TestClient, auth_headers: dict
) -> None:
    resp = client.post(
        f"/api/v1/datasets/{uuid4()}/versions",
        json=_rows_payload(),
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_create_version_empty_rows_422(
    client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    dataset = _create_dataset(client, project_id, auth_headers)
    resp = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions",
        json={"rows": []},
        headers=auth_headers,
    )
    assert resp.status_code == 422
