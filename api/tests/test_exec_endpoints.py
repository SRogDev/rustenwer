"""Execution endpoints tests (TDD: RED first, then implement).

Contract under test (see shared/README.md Phase 2):
  POST   /api/v1/training-jobs/{job_id}/enqueue -> 201 TrainingRun; 409 cases
  GET    /api/v1/training-jobs/{job_id}/runs/{run_id} -> detail / 404
  POST   .../cancel | pause | resume -> TrainingRun
  POST   .../retry -> 201 TrainingRun (new attempt)
  GET    .../logs?follow=false -> text/plain; follow=true -> text/event-stream
  GET    .../metrics | checkpoints | artifacts | cost
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from shared.domain import JobStatus

from app import training as training_module
from app.config import Settings
from app.training.worker import WorkerManager


def _strategy_json(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model_family": "tiny-mlp",
        "architecture": {"type": "mlp", "hidden": [32]},
        "training_method": "classifier",
        "objective": "test",
        "hyperparameters": {"epochs": 10, "lr": 0.1, "batch_size": 64, "seed": 7,
                             "n_train": 400, "n_val": 100},
        "evaluation_plan": "holdout accuracy",
        "compute_budget": {"max_gpu_hours": 0.1, "max_cost_usd": 1.0},
        "rationale": "test",
    }
    base.update(overrides)
    return base


@pytest.fixture
def worker_manager(
    tmp_path: Path,
    training_job_repository: training_module.InMemoryTrainingJobRepository,
    usage_repository,
) -> WorkerManager:
    settings = Settings(data_dir=str(tmp_path / "data"))
    m = WorkerManager(
        settings=settings, job_repo=training_job_repository, usage_repo=usage_repository
    )
    m.start()
    yield m
    m.stop()


@pytest.fixture
def exec_client(client: TestClient, worker_manager: WorkerManager) -> TestClient:
    client.app.dependency_overrides[training_module.get_worker_manager] = (
        lambda: worker_manager
    )
    return client


def _create_job(
    exec_client: TestClient, project_id: UUID, auth_headers: dict, strategy: dict | None = None
) -> dict:
    payload: dict[str, Any] = {"name": "exec-test-job"}
    if strategy is not None:
        payload["strategy"] = strategy
    resp = exec_client.post(
        f"/api/v1/projects/{project_id}/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait_run(
    exec_client: TestClient, job_id: str, run_id: str, auth_headers: dict,
    states: set[str], timeout: float = 120.0,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = exec_client.get(
            f"/api/v1/training-jobs/{job_id}/runs/{run_id}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in states:
            return body
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} never reached {states}")


# --------------------------------------------------------------------------
# Enqueue validation -> 409
# --------------------------------------------------------------------------


def test_enqueue_409_without_strategy(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(exec_client, project_id, auth_headers)
    resp = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    )
    assert resp.status_code == 409
    assert "strategy" in resp.json()["detail"].lower()


def test_enqueue_409_unknown_method(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(exec_client, project_id, auth_headers, _strategy_json(training_method="svm"))
    resp = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_enqueue_409_no_training_needed(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(
        exec_client, project_id, auth_headers, _strategy_json(training_method="none-deterministic")
    )
    resp = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_enqueue_409_qlora_on_local(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(
        exec_client, project_id, auth_headers, _strategy_json(training_method="qlora")
    )
    resp = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue",
        json={"provider": "local"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "cuda" in resp.json()["detail"].lower()


def test_enqueue_409_digitalocean_without_token(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(exec_client, project_id, auth_headers, _strategy_json())
    resp = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue",
        json={"provider": "digitalocean"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "DO_TOKEN" in resp.json()["detail"]


def test_enqueue_409_when_already_queued(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(exec_client, project_id, auth_headers, _strategy_json())
    first = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    )
    assert first.status_code == 201
    second = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    )
    assert second.status_code == 409


# --------------------------------------------------------------------------
# Full lifecycle over HTTP
# --------------------------------------------------------------------------


def test_enqueue_runs_to_completion_over_http(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(exec_client, project_id, auth_headers, _strategy_json())
    run = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    ).json()
    assert run["status"] == "QUEUED"
    assert run["attempt"] == 1
    assert run["provider"] == "local"

    run = _wait_run(exec_client, job["id"], run["id"], auth_headers, {"COMPLETED"})
    assert run["status"] == "COMPLETED"

    metrics = exec_client.get(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/metrics", headers=auth_headers
    )
    assert metrics.status_code == 200, metrics.text
    loss = next(s for s in metrics.json()["series"] if s["name"] == "loss_epoch")
    assert len(loss["points"]) == 10
    assert metrics.json()["latest"]["val_accuracy"] > 0.75

    logs = exec_client.get(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/logs?follow=false",
        headers=auth_headers,
    )
    assert logs.status_code == 200
    assert "epoch" in logs.text.lower()

    ckpts = exec_client.get(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/checkpoints", headers=auth_headers
    )
    assert ckpts.status_code == 200 and len(ckpts.json()) == 10

    arts = exec_client.get(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/artifacts", headers=auth_headers
    )
    assert arts.status_code == 200
    assert {"model", "config"} <= {a["name"] for a in arts.json()}

    cost = exec_client.get(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/cost", headers=auth_headers
    )
    assert cost.status_code == 200
    assert cost.json()["seconds"] > 0


def test_run_detail_404_for_unknown_run(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    job = _create_job(exec_client, project_id, auth_headers, _strategy_json())
    resp = exec_client.get(
        f"/api/v1/training-jobs/{job['id']}/runs/{uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_run_of_other_job_is_404(
    exec_client: TestClient, project_id: UUID, auth_headers: dict,
    worker_manager: WorkerManager,
) -> None:
    job_a = _create_job(exec_client, project_id, auth_headers, _strategy_json())
    job_b = _create_job(exec_client, project_id, auth_headers, _strategy_json())
    run = exec_client.post(
        f"/api/v1/training-jobs/{job_a['id']}/enqueue", json={}, headers=auth_headers
    ).json()
    resp = exec_client.get(
        f"/api/v1/training-jobs/{job_b['id']}/runs/{run['id']}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_pause_resume_cancel_over_http(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    strategy = _strategy_json()
    strategy["hyperparameters"] = {"epochs": 60, "lr": 0.05, "batch_size": 64, "seed": 7,
                                   "n_train": 400, "n_val": 100}
    job = _create_job(exec_client, project_id, auth_headers, strategy)
    run = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    ).json()
    run = _wait_run(exec_client, job["id"], run["id"], auth_headers, {"RUNNING"})

    paused = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/pause", headers=auth_headers
    )
    assert paused.status_code == 200, paused.text
    run = _wait_run(exec_client, job["id"], run["id"], auth_headers, {"PAUSED", "CANCELLED"})
    assert run["status"] == "PAUSED"

    resumed = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/resume", headers=auth_headers
    )
    assert resumed.status_code == 200, resumed.text

    cancelled = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/runs/{run['id']}/cancel", headers=auth_headers
    )
    assert cancelled.status_code == 200, cancelled.text
    run = _wait_run(exec_client, job["id"], run["id"], auth_headers,
                    {"CANCELLED", "COMPLETED", "RUNNING", "PAUSED"})
    assert run["status"] in {"CANCELLED", "COMPLETED"}  # cancel may race a fast finish


def test_retry_creates_second_attempt_over_http(
    exec_client: TestClient, project_id: UUID, auth_headers: dict
) -> None:
    strategy = _strategy_json()
    strategy["hyperparameters"] = {"epochs": 60, "lr": 0.05, "batch_size": 64, "seed": 7,
                                   "n_train": 400, "n_val": 100}
    job = _create_job(exec_client, project_id, auth_headers, strategy)
    run1 = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/enqueue", json={}, headers=auth_headers
    ).json()
    run1 = _wait_run(exec_client, job["id"], run1["id"], auth_headers, {"RUNNING"})
    exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/runs/{run1['id']}/cancel", headers=auth_headers
    )
    run1 = _wait_run(exec_client, job["id"], run1["id"], auth_headers,
                     {"CANCELLED", "COMPLETED", "RUNNING", "PAUSED"})
    if run1["status"] != "CANCELLED":
        pytest.skip("run finished before cancel landed; retry-from-cancel not exercised")

    run2 = exec_client.post(
        f"/api/v1/training-jobs/{job['id']}/runs/{run1['id']}/retry",
        json={"from_checkpoint": True},
        headers=auth_headers,
    )
    assert run2.status_code == 201, run2.text
    assert run2.json()["attempt"] == 2


# --------------------------------------------------------------------------
# SSE stream unit test (no TestClient streaming needed)
# --------------------------------------------------------------------------


def test_sse_stream_emits_data_lines_and_done(
    tmp_path: Path,
    training_job_repository: training_module.InMemoryTrainingJobRepository,
    usage_repository,
) -> None:
    from datetime import UTC, datetime

    from shared.domain import TrainingRun

    settings = Settings(data_dir=str(tmp_path / "data"))
    mgr = WorkerManager(
        settings=settings, job_repo=training_job_repository, usage_repo=usage_repository
    )
    run_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC).isoformat()
    training_job_repository.create_run(
        TrainingRun(id=run_id, job_id=job_id, attempt=1, status=JobStatus.COMPLETED,
                    started_at=now, finished_at=now)
    )
    attempt = mgr.attempt_dir(run_id)
    attempt.mkdir(parents=True)
    (attempt / "logs.txt").write_text('{"t":"x","line":"hello"}\n{"t":"y","line":"world"}\n')

    from app.training.router import _stream_log_events

    chunks = list(_stream_log_events(mgr, run_id, tail=10))
    data_lines = [c for c in chunks if c.startswith("data:")]
    assert len(data_lines) == 3  # 2 log lines + final done
    assert json.loads(data_lines[0][5:])["line"] == "hello"
    assert json.loads(data_lines[-1][5:])["done"] is True
