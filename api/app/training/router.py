"""Training jobs + runs endpoints (Phase 1: CRUD + lifecycle; Phase 2: execution).

Job transitions go through shared.services.jobs.transition (Rule 3).
Phase 2 adds real execution: enqueue -> WorkerManager -> ComputeProvider
-> runner subprocess, with logs/metrics/checkpoints/artifacts/cost reads.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from shared.domain import (
    ApiUser,
    ArtifactRecord,
    CheckpointInfo,
    JobStatus,
    RunCost,
    RunMetrics,
    TrainingJob,
    TrainingRun,
    TrainingStrategy,
)
from shared.services.jobs import InvalidTransitionError, transition

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository
from app.training.adapters import AdapterValidationError
from app.training.worker import WorkerManager, get_worker_manager


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class TrainingJobCreate(BaseModel):
    name: str = Field(min_length=1)
    spec_id: UUID | None = None
    dataset_version_id: UUID | None = None
    strategy: TrainingStrategy | None = None
    compute_budget: dict[str, float | None] | None = None


class JobTransitionRequest(BaseModel):
    to: JobStatus


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class TrainingJobRepository(Protocol):
    """Storage contract for training jobs and their runs."""

    def list_jobs(self, project_id: UUID) -> list[TrainingJob]:
        """All jobs belonging to the given project."""
        ...

    def get_job(self, job_id: UUID) -> TrainingJob | None:
        """A job by id, or None when it does not exist."""
        ...

    def create_job(self, job: TrainingJob) -> TrainingJob:
        """Persist a fully-formed job."""
        ...

    def update_job(self, job_id: UUID, fields: dict[str, Any]) -> TrainingJob | None:
        """Apply field updates; None when the job does not exist."""
        ...

    def list_runs(self, job_id: UUID) -> list[TrainingRun]:
        """All runs of a job (empty until Phase 2 executes)."""
        ...

    def get_run(self, run_id: UUID) -> TrainingRun | None:
        """A run by id, or None when it does not exist."""
        ...

    def create_run(self, run: TrainingRun) -> TrainingRun:
        """Persist a run (Phase 2 execution will use this)."""
        ...

    def update_run(self, run_id: UUID, fields: dict[str, Any]) -> TrainingRun | None:
        """Apply field updates to a run; None when it does not exist."""
        ...


class InMemoryTrainingJobRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[UUID, TrainingJob] = {}
        self._runs: dict[UUID, TrainingRun] = {}

    def list_jobs(self, project_id: UUID) -> list[TrainingJob]:
        with self._lock:
            return [j for j in self._jobs.values() if j.project_id == project_id]

    def get_job(self, job_id: UUID) -> TrainingJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create_job(self, job: TrainingJob) -> TrainingJob:
        with self._lock:
            self._jobs[job.id] = job
            return job

    def update_job(self, job_id: UUID, fields: dict[str, Any]) -> TrainingJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            updated = job.model_copy(update={**fields, "updated_at": _utc_now()})
            self._jobs[job_id] = updated
            return updated

    def list_runs(self, job_id: UUID) -> list[TrainingRun]:
        with self._lock:
            runs = [r for r in self._runs.values() if r.job_id == job_id]
            return sorted(runs, key=lambda r: r.attempt)

    def get_run(self, run_id: UUID) -> TrainingRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def create_run(self, run: TrainingRun) -> TrainingRun:
        with self._lock:
            self._runs[run.id] = run
            return run

    def update_run(self, run_id: UUID, fields: dict[str, Any]) -> TrainingRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            updated = run.model_copy(update=fields)
            self._runs[run_id] = updated
            return updated


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["training-jobs"])


def get_training_job_repository() -> TrainingJobRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryTrainingJobRepository per test.
    """
    return _default_repository


_default_repository = InMemoryTrainingJobRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_job_or_404(
    job_repository: TrainingJobRepository,
    project_repository: ProjectRepository,
    job_id: UUID,
    user: ApiUser,
) -> TrainingJob:
    """Fetch a job, 404 when missing or owned by another org (via its project)."""
    job = job_repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found")
    project = project_repository.get_project(job.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found")
    return job


@router.post("/projects/{project_id}/training-jobs", response_model=TrainingJob,
             status_code=status.HTTP_201_CREATED)
def create_job(
    project_id: UUID,
    payload: TrainingJobCreate,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> TrainingJob:
    """Create a training job in CREATED status. Execution lands in Phase 2."""
    _get_project_or_404(project_repository, project_id, user)
    now = _utc_now()
    job = TrainingJob(
        id=uuid4(),
        project_id=project_id,
        spec_id=payload.spec_id,
        dataset_version_id=payload.dataset_version_id,
        name=payload.name,
        status=JobStatus.CREATED,
        strategy=payload.strategy,
        compute_budget=payload.compute_budget,
        created_at=now,
        updated_at=now,
    )
    return job_repository.create_job(job)


@router.get("/projects/{project_id}/training-jobs", response_model=list[TrainingJob])
def list_jobs(
    project_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[TrainingJob]:
    """List all training jobs of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return job_repository.list_jobs(project_id)


@router.get("/training-jobs/{job_id}", response_model=TrainingJob)
def get_job(
    job_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> TrainingJob:
    """Job detail; 404 when missing or owned by another org."""
    return _get_job_or_404(job_repository, project_repository, job_id, user)


@router.post("/training-jobs/{job_id}/transition", response_model=TrainingJob)
def transition_job(
    job_id: UUID,
    payload: JobTransitionRequest,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> TrainingJob:
    """Transition a job; 409 on invalid transition (job lifecycle §42)."""
    job = _get_job_or_404(job_repository, project_repository, job_id, user)
    try:
        new_status = transition(job.status, payload.to)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    updated = job_repository.update_job(job_id, {"status": new_status})
    assert updated is not None  # guarded by _get_job_or_404 above
    return updated


@router.get("/training-jobs/{job_id}/runs", response_model=list[TrainingRun])
def list_runs(
    job_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[TrainingRun]:
    """List a job's runs — empty until Phase 2 executes jobs."""
    job = _get_job_or_404(job_repository, project_repository, job_id, user)
    return job_repository.list_runs(job.id)


# --------------------------------------------------------------------------
# Phase 2 — execution
# --------------------------------------------------------------------------

_TERMINAL_RUN_STATUSES = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
)


class EnqueueRunRequest(BaseModel):
    provider: str = Field(default="local", min_length=1)


class RetryRunRequest(BaseModel):
    from_checkpoint: bool = True


def _get_run_or_404(
    manager: WorkerManager, job_id: UUID, run_id: UUID
) -> TrainingRun:
    try:
        run = manager.get_run(run_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found"
        ) from None
    if run.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found"
        )
    return run


@router.post(
    "/training-jobs/{job_id}/enqueue",
    response_model=TrainingRun,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_run(
    job_id: UUID,
    payload: EnqueueRunRequest,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> TrainingRun:
    """Validate the job's strategy and enqueue a real execution (Phase 2).

    409 when the strategy is missing, unknown, or rejected (e.g. QLoRA on
    the local CPU provider, digitalocean without DO_TOKEN), or when the job
    already has an active run.
    """
    job = _get_job_or_404(job_repository, project_repository, job_id, user)
    try:
        return manager.submit(job, provider_name=payload.provider)
    except (AdapterValidationError, KeyError, InvalidTransitionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/training-jobs/{job_id}/runs/{run_id}", response_model=TrainingRun)
def get_run(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> TrainingRun:
    """Run detail (Phase 2)."""
    _get_job_or_404(job_repository, project_repository, job_id, user)
    return _get_run_or_404(manager, job_id, run_id)


def _control(
    job_id: UUID,
    run_id: UUID,
    action: str,
    job_repository: TrainingJobRepository,
    project_repository: ProjectRepository,
    manager: WorkerManager,
    user: ApiUser,
) -> TrainingRun:
    _get_job_or_404(job_repository, project_repository, job_id, user)
    _get_run_or_404(manager, job_id, run_id)
    try:
        func = {"cancel": manager.cancel, "pause": manager.pause,
                "resume": manager.resume}[action]
        return func(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post("/training-jobs/{job_id}/runs/{run_id}/cancel", response_model=TrainingRun)
def cancel_run(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> TrainingRun:
    """Cancel a run: SIGTERM for running, dequeue for queued (409 otherwise)."""
    return _control(job_id, run_id, "cancel", job_repository,
                    project_repository, manager, user)


@router.post("/training-jobs/{job_id}/runs/{run_id}/pause", response_model=TrainingRun)
def pause_run(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> TrainingRun:
    """Pause a run gracefully (checkpoint first); resume() continues it."""
    return _control(job_id, run_id, "pause", job_repository,
                    project_repository, manager, user)


@router.post("/training-jobs/{job_id}/runs/{run_id}/resume", response_model=TrainingRun)
def resume_run(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> TrainingRun:
    """Resume a PAUSED run from its latest checkpoint (409 otherwise)."""
    return _control(job_id, run_id, "resume", job_repository,
                    project_repository, manager, user)


@router.post(
    "/training-jobs/{job_id}/runs/{run_id}/retry", response_model=TrainingRun,
    status_code=status.HTTP_201_CREATED,
)
def retry_run(
    job_id: UUID,
    run_id: UUID,
    payload: RetryRunRequest,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> TrainingRun:
    """Retry a FAILED/CANCELLED run as a new attempt (409 otherwise).

    from_checkpoint (default true) resumes from the previous attempt's
    checkpoints instead of training from scratch.
    """
    _get_job_or_404(job_repository, project_repository, job_id, user)
    _get_run_or_404(manager, job_id, run_id)
    try:
        return manager.retry(run_id, from_checkpoint=payload.from_checkpoint)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


def _stream_log_events(
    manager: WorkerManager, run_id: UUID, tail: int = 300
):
    """SSE data chunks for a run's log lines, then a done event.

    Reads the attempt's logs.txt (each line a {"t", "line"} record).
    """
    from app.training import runs as runs_model

    attempt = manager.attempt_dir(run_id)
    for line in runs_model.read_log_lines(attempt, tail):
        yield f"data: {line}\n\n"
    yield 'data: {"done": true}\n\n'


@router.get("/training-jobs/{job_id}/runs/{run_id}/logs")
def get_run_logs(
    job_id: UUID,
    run_id: UUID,
    tail: int = Query(default=300, ge=0),
    follow: bool = Query(default=False),
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
):
    """Log lines as plain text (one "t line" per line); follow=true streams SSE."""
    _get_job_or_404(job_repository, project_repository, job_id, user)
    run = _get_run_or_404(manager, job_id, run_id)
    if not follow:
        entries = manager.get_logs(run.id, tail=tail)
        body = "\n".join(f"{e['t']} {e['line']}" for e in entries)
        return PlainTextResponse(body)

    from app.training import runs as runs_model

    def _follow():
        seen = 0
        for chunk in _stream_log_events(manager, run.id, tail):
            if '"done": true' in chunk:
                continue  # done is emitted only at terminal below
            seen += 1
            yield chunk
        while True:
            time.sleep(0.5)
            lines = runs_model.read_log_lines(manager.attempt_dir(run.id), None)
            for line in lines[seen:]:
                yield f"data: {line}\n\n"
                seen += 1
            if manager.get_run(run.id).status in _TERMINAL_RUN_STATUSES:
                break
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(_follow(), media_type="text/event-stream")


@router.get(
    "/training-jobs/{job_id}/runs/{run_id}/metrics", response_model=RunMetrics
)
def get_run_metrics(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> RunMetrics:
    """Metric curves for the run's latest attempt."""
    _get_job_or_404(job_repository, project_repository, job_id, user)
    run = _get_run_or_404(manager, job_id, run_id)
    return manager.get_metrics(run.id)


@router.get(
    "/training-jobs/{job_id}/runs/{run_id}/checkpoints",
    response_model=list[CheckpointInfo],
)
def get_run_checkpoints(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> list[CheckpointInfo]:
    """Checkpoints of the run's latest attempt, oldest first."""
    _get_job_or_404(job_repository, project_repository, job_id, user)
    run = _get_run_or_404(manager, job_id, run_id)
    return manager.get_checkpoints(run.id)


@router.get(
    "/training-jobs/{job_id}/runs/{run_id}/artifacts",
    response_model=list[ArtifactRecord],
)
def get_run_artifacts(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> list[ArtifactRecord]:
    """Immutable artifact versions published by this run."""
    _get_job_or_404(job_repository, project_repository, job_id, user)
    run = _get_run_or_404(manager, job_id, run_id)
    return manager.get_artifacts(run.id)


@router.get("/training-jobs/{job_id}/runs/{run_id}/cost", response_model=RunCost)
def get_run_cost(
    job_id: UUID,
    run_id: UUID,
    job_repository: TrainingJobRepository = Depends(get_training_job_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    manager: WorkerManager = Depends(get_worker_manager),
    user: ApiUser = Depends(get_current_user),
) -> RunCost:
    """Cost accounting: wall time x provider rate (Phase 1 usage ledger too)."""
    _get_job_or_404(job_repository, project_repository, job_id, user)
    run = _get_run_or_404(manager, job_id, run_id)
    return manager.get_cost(run.id)
