"""Evaluations endpoints (Phase 1).

POST /evaluations/run executes the baseline evaluation synchronously
(Rule 11: the runner evaluates row data, never model internals) and stores
the result as a COMPLETED evaluation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from shared.domain import (
    ApiUser,
    Evaluation,
    EvaluationResults,
    EvaluationStatus,
)
from shared.services.baselines import run_baselines

from app.auth import get_current_user
from app.datasets import DatasetRepository, get_dataset_repository
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository
from app.specs import SpecRepository, get_spec_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class EvaluationRunRequest(BaseModel):
    name: str | None = None
    spec_id: UUID
    dataset_version_id: UUID


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class EvaluationRepository(Protocol):
    """Storage contract for evaluations."""

    def list_evaluations(self, project_id: UUID) -> list[Evaluation]:
        """All evaluations belonging to the given project."""
        ...

    def get_evaluation(self, evaluation_id: UUID) -> Evaluation | None:
        """An evaluation by id, or None when it does not exist."""
        ...

    def create_evaluation(self, evaluation: Evaluation) -> Evaluation:
        """Persist a fully-formed evaluation."""
        ...


class InMemoryEvaluationRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._evaluations: dict[UUID, Evaluation] = {}

    def list_evaluations(self, project_id: UUID) -> list[Evaluation]:
        with self._lock:
            return [e for e in self._evaluations.values() if e.project_id == project_id]

    def get_evaluation(self, evaluation_id: UUID) -> Evaluation | None:
        with self._lock:
            return self._evaluations.get(evaluation_id)

    def create_evaluation(self, evaluation: Evaluation) -> Evaluation:
        with self._lock:
            self._evaluations[evaluation.id] = evaluation
            return evaluation


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


def get_evaluation_repository() -> EvaluationRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryEvaluationRepository per test.
    """
    return _default_repository


_default_repository = InMemoryEvaluationRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_evaluation_or_404(
    evaluation_repository: EvaluationRepository,
    project_repository: ProjectRepository,
    evaluation_id: UUID,
    user: ApiUser,
) -> Evaluation:
    """Fetch an evaluation, 404 when missing or owned by another org (via its project)."""
    evaluation = evaluation_repository.get_evaluation(evaluation_id)
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found"
        )
    project = project_repository.get_project(evaluation.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found"
        )
    return evaluation


def _recommendation(report_bar_accuracy: float, best_baseline: str) -> str:
    if best_baseline:
        return (
            f"Best baseline '{best_baseline}' reaches accuracy {report_bar_accuracy:.3f}. "
            "Train a candidate only if it can beat this bar on accuracy, p50 latency, "
            "and cost per 1k predictions (Rule 9)."
        )
    return (
        "Labels missing or unusable — baselines could not be scored and the bar "
        "carries zeros. Supply a label column to establish the bar to beat."
    )


@router.post("/projects/{project_id}/evaluations/run", response_model=Evaluation,
             status_code=status.HTTP_201_CREATED)
def run_evaluation(
    project_id: UUID,
    payload: EvaluationRunRequest,
    evaluation_repository: EvaluationRepository = Depends(get_evaluation_repository),
    spec_repository: SpecRepository = Depends(get_spec_repository),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Evaluation:
    """Run the baseline evaluation synchronously -> 201 Evaluation (COMPLETED)."""
    _get_project_or_404(project_repository, project_id, user)

    spec = spec_repository.get_spec(payload.spec_id)
    if spec is None or spec.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found")
    project = project_repository.get_project(spec.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found")

    version = dataset_repository.get_version(payload.dataset_version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found"
        )
    dataset = dataset_repository.get_dataset(version.dataset_id)
    if dataset is None or dataset.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found"
        )
    rows = dataset_repository.get_rows(version.id) or []
    label_column = dataset_repository.get_label_column(version.id) or "label"

    report = run_baselines(spec, version.id, rows, label_column=label_column)

    now = _utc_now()
    evaluation = Evaluation(
        id=uuid4(),
        project_id=project_id,
        spec_id=spec.id,
        dataset_version_id=version.id,
        name=payload.name or f"baseline-evaluation-{now}",
        status=EvaluationStatus.COMPLETED,
        results=EvaluationResults(
            baselines=report.baselines,
            bar_to_beat=report.bar_to_beat,
            recommendation=_recommendation(
                report.bar_to_beat.accuracy, report.best_baseline
            ),
            evaluated_at=report.evaluated_at,
        ),
        created_at=now,
        completed_at=now,
    )
    return evaluation_repository.create_evaluation(evaluation)


@router.get("/projects/{project_id}/evaluations", response_model=list[Evaluation])
def list_evaluations(
    project_id: UUID,
    evaluation_repository: EvaluationRepository = Depends(get_evaluation_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Evaluation]:
    """List all evaluations of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return evaluation_repository.list_evaluations(project_id)


@router.get("/evaluations/{evaluation_id}", response_model=Evaluation)
def get_evaluation(
    evaluation_id: UUID,
    evaluation_repository: EvaluationRepository = Depends(get_evaluation_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Evaluation:
    """Evaluation detail; 404 when missing or owned by another org."""
    return _get_evaluation_or_404(evaluation_repository, project_repository, evaluation_id, user)
