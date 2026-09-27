"""Deployments endpoints (Phase 1).

Deployment lifecycle: DRAFT -> ACTIVE -> PAUSED -> ARCHIVED, with ARCHIVED
reachable from any non-terminal state (cancel-from-anywhere).
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import ApiUser, Deployment, DeploymentStatus

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


_ALLOWED_DEPLOYMENT_TRANSITIONS: dict[DeploymentStatus, frozenset[DeploymentStatus]] = {
    DeploymentStatus.DRAFT: frozenset({DeploymentStatus.ACTIVE, DeploymentStatus.ARCHIVED}),
    DeploymentStatus.ACTIVE: frozenset({DeploymentStatus.PAUSED, DeploymentStatus.ARCHIVED}),
    DeploymentStatus.PAUSED: frozenset({DeploymentStatus.ACTIVE, DeploymentStatus.ARCHIVED}),
    DeploymentStatus.ARCHIVED: frozenset(),  # terminal
}


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class DeploymentCreate(BaseModel):
    name: str = Field(min_length=1)
    spec_id: UUID
    model_version_id: UUID | None = None
    endpoint_url: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class DeploymentUpdate(BaseModel):
    status: DeploymentStatus


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class DeploymentRepository(Protocol):
    """Storage contract for deployments."""

    def list_deployments(self, project_id: UUID) -> list[Deployment]:
        """All deployments belonging to the given project."""
        ...

    def get_deployment(self, deployment_id: UUID) -> Deployment | None:
        """A deployment by id, or None when it does not exist."""
        ...

    def create_deployment(self, deployment: Deployment) -> Deployment:
        """Persist a fully-formed deployment."""
        ...

    def update_deployment(
        self, deployment_id: UUID, fields: dict[str, Any]
    ) -> Deployment | None:
        """Apply field updates; None when the deployment does not exist."""
        ...


class InMemoryDeploymentRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._deployments: dict[UUID, Deployment] = {}

    def list_deployments(self, project_id: UUID) -> list[Deployment]:
        with self._lock:
            return [d for d in self._deployments.values() if d.project_id == project_id]

    def get_deployment(self, deployment_id: UUID) -> Deployment | None:
        with self._lock:
            return self._deployments.get(deployment_id)

    def create_deployment(self, deployment: Deployment) -> Deployment:
        with self._lock:
            self._deployments[deployment.id] = deployment
            return deployment

    def update_deployment(
        self, deployment_id: UUID, fields: dict[str, Any]
    ) -> Deployment | None:
        with self._lock:
            deployment = self._deployments.get(deployment_id)
            if deployment is None:
                return None
            updated = deployment.model_copy(update={**fields, "updated_at": _utc_now()})
            self._deployments[deployment_id] = updated
            return updated


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["deployments"])


def get_deployment_repository() -> DeploymentRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryDeploymentRepository per test.
    """
    return _default_repository


_default_repository = InMemoryDeploymentRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_deployment_or_404(
    deployment_repository: DeploymentRepository,
    project_repository: ProjectRepository,
    deployment_id: UUID,
    user: ApiUser,
) -> Deployment:
    """Fetch a deployment, 404 when missing or owned by another org (via its project)."""
    deployment = deployment_repository.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
        )
    project = project_repository.get_project(deployment.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
        )
    return deployment


@router.post("/projects/{project_id}/deployments", response_model=Deployment,
             status_code=status.HTTP_201_CREATED)
def create_deployment(
    project_id: UUID,
    payload: DeploymentCreate,
    deployment_repository: DeploymentRepository = Depends(get_deployment_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Deployment:
    """Create a deployment in DRAFT status."""
    _get_project_or_404(project_repository, project_id, user)
    now = _utc_now()
    deployment = Deployment(
        id=uuid4(),
        project_id=project_id,
        spec_id=payload.spec_id,
        model_version_id=payload.model_version_id,
        name=payload.name,
        status=DeploymentStatus.DRAFT,
        endpoint_url=payload.endpoint_url,
        config=payload.config,
        created_at=now,
        updated_at=now,
    )
    return deployment_repository.create_deployment(deployment)


@router.get("/projects/{project_id}/deployments", response_model=list[Deployment])
def list_deployments(
    project_id: UUID,
    deployment_repository: DeploymentRepository = Depends(get_deployment_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Deployment]:
    """List all deployments of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return deployment_repository.list_deployments(project_id)


@router.patch("/deployments/{deployment_id}", response_model=Deployment)
def update_deployment(
    deployment_id: UUID,
    payload: DeploymentUpdate,
    deployment_repository: DeploymentRepository = Depends(get_deployment_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Deployment:
    """Transition a deployment's status; 409 on invalid transition."""
    deployment = _get_deployment_or_404(
        deployment_repository, project_repository, deployment_id, user
    )
    allowed = _ALLOWED_DEPLOYMENT_TRANSITIONS[deployment.status]
    if payload.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid deployment transition: {deployment.status.value} -> "
                f"{payload.status.value}"
            ),
        )
    updated = deployment_repository.update_deployment(
        deployment_id, {"status": payload.status}
    )
    assert updated is not None  # guarded by _get_deployment_or_404 above
    return updated
