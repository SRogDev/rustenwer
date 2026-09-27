"""WorkerManager tests (TDD: RED first, then implement).

The manager is exercised for real: LocalExecutor spawns a genuine worker
subprocess that trains a tiny torch classifier. No mocks for the training
path — subprocess, checkpoints, metrics, logs, artifacts, and cost are all
real. Runs are kept tiny (few epochs, small synthetic data) so the suite
stays fast.
"""

from __future__ import annotations

import os
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from shared.domain import JobStatus, TrainingJob, TrainingStrategy, UsageKind
from shared.services.jobs import InvalidTransitionError

from app import training as training_module
from app.config import Settings
from app.training.worker import WorkerManager
from app.usage import InMemoryUsageRepository

TERMINAL = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


def _strategy(**overrides: Any) -> TrainingStrategy:
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
    return TrainingStrategy(**base)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def job_repo() -> training_module.InMemoryTrainingJobRepository:
    return training_module.InMemoryTrainingJobRepository()


@pytest.fixture
def usage_repo() -> InMemoryUsageRepository:
    return InMemoryUsageRepository()


@pytest.fixture
def manager(
    tmp_path: Path,
    job_repo: training_module.InMemoryTrainingJobRepository,
    usage_repo: InMemoryUsageRepository,
) -> WorkerManager:
    settings = Settings(data_dir=str(tmp_path / "data"))
    m = WorkerManager(settings=settings, job_repo=job_repo, usage_repo=usage_repo)
    m.start()
    yield m
    m.stop()


def _make_job(
    job_repo: training_module.InMemoryTrainingJobRepository,
    strategy: TrainingStrategy,
    name: str = "e2e-job",
) -> TrainingJob:
    job = TrainingJob(
        id=uuid4(), project_id=uuid4(), name=name, status=JobStatus.CREATED,
        strategy=strategy, created_at=_now(), updated_at=_now(),
    )
    return job_repo.create_job(job)


def _wait_for(
    manager: WorkerManager, run_id: UUID, states: set[JobStatus], timeout: float = 120.0
):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = manager.get_run(run_id)
        assert run is not None
        if run.status in states:
            return run
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} never reached {states}")


def _wait_for_log(manager: WorkerManager, run_id: UUID, needle: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if needle in manager.get_logs_text(run_id):
            return
        time.sleep(0.5)
    raise AssertionError(f"logs never contained {needle!r}")


# --------------------------------------------------------------------------
# Submit / validation
# --------------------------------------------------------------------------


def test_submit_requires_strategy(manager: WorkerManager, job_repo) -> None:
    job = _make_job(job_repo, None)  # type: ignore[arg-type]
    with pytest.raises(training_module.AdapterValidationError):
        manager.submit(job)


def test_submit_rejects_unknown_method(manager: WorkerManager, job_repo) -> None:
    job = _make_job(job_repo, _strategy(training_method="svm-from-1998"))
    with pytest.raises(KeyError):
        manager.submit(job)


def test_submit_rejects_no_training_strategy(manager: WorkerManager, job_repo) -> None:
    job = _make_job(job_repo, _strategy(training_method="none-deterministic"))
    with pytest.raises(training_module.AdapterValidationError):
        manager.submit(job)


def test_submit_rejects_qlora_on_local(manager: WorkerManager, job_repo) -> None:
    job = _make_job(job_repo, _strategy(training_method="qlora"))
    with pytest.raises(training_module.AdapterValidationError):
        manager.submit(job, provider_name="local")


def test_submit_twice_raises(manager: WorkerManager, job_repo) -> None:
    job = _make_job(job_repo, _strategy())
    run = manager.submit(job)
    assert run.status == JobStatus.QUEUED
    assert job_repo.get_job(job.id).status == JobStatus.QUEUED
    with pytest.raises(InvalidTransitionError):  # illegal QUEUED -> QUEUED
        manager.submit(job_repo.get_job(job.id))


# --------------------------------------------------------------------------
# End-to-end: real subprocess training
# --------------------------------------------------------------------------


def test_e2e_local_training_completes_with_artifacts(
    manager: WorkerManager, job_repo, usage_repo: InMemoryUsageRepository
) -> None:
    job = _make_job(job_repo, _strategy())
    run = manager.submit(job)

    run = _wait_for(manager, run.id, TERMINAL)
    assert run.status == JobStatus.COMPLETED, f"run failed: {run.error}"
    assert job_repo.get_job(job.id).status == JobStatus.COMPLETED

    # Metrics: real loss series, decreasing.
    metrics = manager.get_metrics(run.id)
    loss = next(s for s in metrics.series if s.name == "loss_epoch")
    assert len(loss.points) == 10
    assert loss.points[-1].value < loss.points[0].value
    assert metrics.latest["val_accuracy"] > 0.75

    # Logs: real lines persisted.
    logs = manager.get_logs_text(run.id)
    assert "epoch" in logs.lower()

    # Checkpoints: real files.
    ckpts = manager.get_checkpoints(run.id)
    assert len(ckpts) == 10
    assert all(c.bytes > 0 for c in ckpts)

    # Artifacts: immutable versioned records.
    arts = manager.get_artifacts(run.id)
    names = {a.name for a in arts}
    assert "model" in names and "config" in names

    # Cost: wall-time accounting + usage event.
    cost = manager.get_cost(run.id)
    assert cost.provider == "local"
    assert cost.seconds > 0
    assert cost.usd >= 0
    events = usage_repo.list_events(job.project_id)
    training_events = [e for e in events if e.kind == UsageKind.TRAINING]
    assert len(training_events) == 1
    assert training_events[0].cost_usd == pytest.approx(cost.usd)
    assert training_events[0].scope_id == job.id


def test_cancel_writes_graceful_checkpoint(manager: WorkerManager, job_repo) -> None:
    strategy = _strategy(hyperparameters={"epochs": 200, "lr": 0.05, "batch_size": 64,
                                           "seed": 7, "n_train": 400, "n_val": 100})
    job = _make_job(job_repo, strategy)
    run = manager.submit(job)
    _wait_for(manager, run.id, {JobStatus.RUNNING})
    _wait_for_log(manager, run.id, "epoch 0")  # training is genuinely underway

    cancelled = manager.cancel(run.id)
    assert cancelled.status in {JobStatus.CANCELLED, JobStatus.RUNNING}  # async handoff
    run = _wait_for(manager, run.id, TERMINAL)
    assert run.status == JobStatus.CANCELLED
    assert job_repo.get_job(job.id).status == JobStatus.CANCELLED
    # Graceful stop wrote a checkpoint before dying.
    assert len(manager.get_checkpoints(run.id)) >= 1


def test_pause_and_resume_continues_training(manager: WorkerManager, job_repo) -> None:
    strategy = _strategy(hyperparameters={"epochs": 4, "lr": 0.05, "batch_size": 64,
                                           "seed": 7, "n_train": 400, "n_val": 100})
    job = _make_job(job_repo, strategy)
    run = manager.submit(job)
    _wait_for(manager, run.id, {JobStatus.RUNNING})
    _wait_for_log(manager, run.id, "epoch 0")

    manager.pause(run.id)
    run = _wait_for(manager, run.id, {JobStatus.PAUSED, JobStatus.CANCELLED})
    assert run.status == JobStatus.PAUSED
    assert len(manager.get_checkpoints(run.id)) >= 1

    manager.resume(run.id)
    run = _wait_for(manager, run.id, TERMINAL, timeout=180)
    assert run.status == JobStatus.COMPLETED, f"run failed: {run.error}"
    metrics = manager.get_metrics(run.id)
    loss = next(s for s in metrics.series if s.name == "loss_epoch")
    assert len(loss.points) == 4  # all 4 epochs ran across pause/resume


def test_retry_from_checkpoint_creates_new_attempt(manager: WorkerManager, job_repo) -> None:
    strategy = _strategy(hyperparameters={"epochs": 200, "lr": 0.05, "batch_size": 64,
                                           "seed": 7, "n_train": 400, "n_val": 100})
    job = _make_job(job_repo, strategy)
    run1 = manager.submit(job)
    _wait_for(manager, run1.id, {JobStatus.RUNNING})
    _wait_for_log(manager, run1.id, "epoch 0")
    manager.cancel(run1.id)
    _wait_for(manager, run1.id, TERMINAL)

    run2 = manager.retry(run1.id, from_checkpoint=True)
    assert run2.attempt == 2
    assert run2.id != run1.id
    run2 = _wait_for(manager, run2.id, TERMINAL, timeout=180)
    assert run2.status == JobStatus.COMPLETED, f"run failed: {run2.error}"
    assert job_repo.get_job(job.id).status == JobStatus.COMPLETED


def test_brutal_kill_marks_run_failed(manager: WorkerManager, job_repo) -> None:
    strategy = _strategy(hyperparameters={"epochs": 200, "lr": 0.05, "batch_size": 64,
                                           "seed": 7, "n_train": 400, "n_val": 100})
    job = _make_job(job_repo, strategy)
    run = manager.submit(job)
    _wait_for(manager, run.id, {JobStatus.RUNNING})
    _wait_for_log(manager, run.id, "epoch 0")

    info = manager.live_info(run.id)
    assert info is not None and info["pid"]
    os.kill(info["pid"], signal.SIGKILL)  # simulate a crash — no graceful shutdown

    run = _wait_for(manager, run.id, TERMINAL)
    assert run.status == JobStatus.FAILED
    assert run.error, "expected an error message on the failed run"
    assert job_repo.get_job(job.id).status == JobStatus.FAILED
