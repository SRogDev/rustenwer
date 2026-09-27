"""Projects endpoints: CRUD over the project collection (Phase 0).

Storage is an in-memory repository behind a Protocol, seeded empty by
design (no fake demo data). Phase 1 swaps in the Supabase-backed
implementation against migration 001; the router code does not change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import ApiUser, Project, ProjectStatus

from app.auth import get_current_user


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProjectStatus | None = None


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class ProjectRepository(Protocol):
    """Storage contract for projects; Phase 1 adds a Supabase implementation."""

    def list_projects(self, organization_id: UUID) -> list[Project]:
        """All projects belonging to the given organization."""
        ...

    def get_project(self, project_id: UUID) -> Project | None:
        """A project by id, or None when it does not exist."""
        ...

    def create_project(self, project: Project) -> Project:
        """Persist a fully-formed project."""
        ...

    def update_project(self, project_id: UUID, fields: dict[str, Any]) -> Project | None:
        """Apply field updates; None when the project does not exist."""
        ...

    def archive_project(self, project_id: UUID) -> Project | None:
        """Soft-archive (status -> ARCHIVED); None when it does not exist."""
        ...


class InMemoryProjectRepository:
    """Dict-backed repository for Phase 0. Empty at construction.

    Thread-safe enough for a dev server (single process, one lock).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._projects: dict[UUID, Project] = {}

    def list_projects(self, organization_id: UUID) -> list[Project]:
        with self._lock:
            return [p for p in self._projects.values() if p.organization_id == organization_id]

    def get_project(self, project_id: UUID) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def create_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
            return project

    def update_project(self, project_id: UUID, fields: dict[str, Any]) -> Project | None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            updated = project.model_copy(update={**fields, "updated_at": _utc_now()})
            self._projects[project_id] = updated
            return updated

    def archive_project(self, project_id: UUID) -> Project | None:
        return self.update_project(project_id, {"status": ProjectStatus.ARCHIVED})


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def get_repository() -> ProjectRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryProjectRepository per test.
    """
    return _default_repository


_default_repository = InMemoryProjectRepository()


def _get_or_404(repository: ProjectRepository, project_id: UUID, user: ApiUser) -> Project:
    """Fetch a project, 404 when missing or owned by another org."""
    project = repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.get("", response_model=list[Project])
def list_projects(
    repository: ProjectRepository = Depends(get_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Project]:
    """List all projects of the caller's organization."""
    return repository.list_projects(user.organization_id)


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    repository: ProjectRepository = Depends(get_repository),
    user: ApiUser = Depends(get_current_user),
) -> Project:
    """Create a project in the caller's organization."""
    now = _utc_now()
    project = Project(
        id=uuid4(),
        organization_id=user.organization_id,
        name=payload.name,
        description=payload.description,
        status=ProjectStatus.ACTIVE,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    return repository.create_project(project)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: UUID,
    repository: ProjectRepository = Depends(get_repository),
    user: ApiUser = Depends(get_current_user),
) -> Project:
    """Project detail; 404 when missing or owned by another org."""
    return _get_or_404(repository, project_id, user)


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    repository: ProjectRepository = Depends(get_repository),
    user: ApiUser = Depends(get_current_user),
) -> Project:
    """Update name/description/status; 404 when missing or other org."""
    _get_or_404(repository, project_id, user)
    updated = repository.update_project(project_id, payload.model_dump(exclude_unset=True))
    assert updated is not None  # guarded by _get_or_404 above
    return updated


@router.delete("/{project_id}", response_model=Project)
def delete_project(
    project_id: UUID,
    repository: ProjectRepository = Depends(get_repository),
    user: ApiUser = Depends(get_current_user),
) -> Project:
    """Soft-archive a project (status -> ARCHIVED) and return it."""
    _get_or_404(repository, project_id, user)
    archived = repository.archive_project(project_id)
    assert archived is not None  # guarded by _get_or_404 above
    return archived
