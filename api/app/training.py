"""Training jobs + runs endpoints (Phase 1).

Job transitions go through shared.services.jobs.transition (Rule 3).
Real GPU execution lands in Phase 2 — runs stay empty until then.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import ApiUser, JobStatus, TrainingJob, TrainingRun, TrainingStrategy
from shared.services.jobs import InvalidTransitionError, transition

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


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

    def create_run(self, run: TrainingRun) -> TrainingRun:
        """Persist a run (Phase 2 execution will use this)."""
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

    def create_run(self, run: TrainingRun) -> TrainingRun:
        with self._lock:
            self._runs[run.id] = run
            return run


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
