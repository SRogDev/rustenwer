"""Intelligences endpoints: first-class intelligence artifacts (Phase 3, §31).

An Intelligence is an executable system performing a cognitive function. It
is separate from Model: one model may power multiple intelligences, and one
intelligence may combine multiple model versions, baselines and a harness.

Intelligence versions are immutable (§43): the repository offers no update
or delete, and version numbers auto-increment on publish — clients cannot
publish an explicit version number.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import (
    ApiUser,
    Intelligence,
    IntelligencePrimitive,
    IntelligenceVersion,
)

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class IntelligenceCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    primitive: IntelligencePrimitive | None = None


class IntelligenceComponents(BaseModel):
    model_version_ids: list[UUID] = Field(default_factory=list)
    baseline_refs: list[str] = Field(default_factory=list)
    harness: dict[str, Any] = Field(default_factory=dict)


class IntelligenceVersionCreate(BaseModel):
    components: IntelligenceComponents = Field(default_factory=IntelligenceComponents)
    notes: str | None = None


class ResolvedComponent(BaseModel):
    model_version_id: UUID
    model_name: str
    version: int
    architecture_summary: str | None = None
    training_run_id: UUID | None = None
    seed: int | None = None
    code_version: str | None = None


class IntelligenceVersionDetail(IntelligenceVersion):
    resolved_components: list[ResolvedComponent] = Field(default_factory=list)
    baseline_refs: list[str] = Field(default_factory=list)
    harness: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class IntelligenceRepository(Protocol):
    """Storage contract for intelligences and their immutable versions."""

    def list_intelligences(self, project_id: UUID) -> list[Intelligence]:
        """All intelligences belonging to the given project."""
        ...

    def get_intelligence(self, intelligence_id: UUID) -> Intelligence | None:
        """An intelligence by id, or None when it does not exist."""
        ...

    def create_intelligence(self, intelligence: Intelligence) -> Intelligence:
        """Persist a fully-formed intelligence."""
        ...

    def list_versions(self, intelligence_id: UUID) -> list[IntelligenceVersion]:
        """All versions of an intelligence, ascending by version number."""
        ...

    def get_version_by_number(
        self, intelligence_id: UUID, version: int
    ) -> IntelligenceVersion | None:
        """An intelligence's version by its number, or None when missing."""
        ...

    def create_version(self, version: IntelligenceVersion) -> IntelligenceVersion:
        """Persist an immutable intelligence version."""
        ...


class InMemoryIntelligenceRepository:
    """Dict-backed repository for Phase 3. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._intelligences: dict[UUID, Intelligence] = {}
        self._versions: dict[UUID, IntelligenceVersion] = {}

    def list_intelligences(self, project_id: UUID) -> list[Intelligence]:
        with self._lock:
            return [
                i for i in self._intelligences.values() if i.project_id == project_id
            ]

    def get_intelligence(self, intelligence_id: UUID) -> Intelligence | None:
        with self._lock:
            return self._intelligences.get(intelligence_id)

    def create_intelligence(self, intelligence: Intelligence) -> Intelligence:
        with self._lock:
            self._intelligences[intelligence.id] = intelligence
            return intelligence

    def list_versions(self, intelligence_id: UUID) -> list[IntelligenceVersion]:
        with self._lock:
            versions = [
                v for v in self._versions.values() if v.intelligence_id == intelligence_id
            ]
            return sorted(versions, key=lambda v: v.version)

    def get_version_by_number(
        self, intelligence_id: UUID, version: int
    ) -> IntelligenceVersion | None:
        with self._lock:
            for v in self._versions.values():
                if v.intelligence_id == intelligence_id and v.version == version:
                    return v
            return None

    def create_version(self, version: IntelligenceVersion) -> IntelligenceVersion:
        with self._lock:
            self._versions[version.id] = version
            return version


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["intelligences"])


def get_intelligence_repository() -> IntelligenceRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryIntelligenceRepository per test.
    The evaluation package imports this hook lazily to resolve incumbents.
    """
    return _default_repository


_default_repository = InMemoryIntelligenceRepository()


def get_model_repository_hook() -> Any:
    """Resolve the model repository without importing app.models at module load.

    The import lives inside the function so this package can never create an
    import cycle with app.models (which may itself grow registry imports in
    later phases). Returns the app.models ModelRepository Protocol instance.
    """
    from app.models import get_model_repository

    return get_model_repository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_intelligence_or_404(
    intelligence_repository: IntelligenceRepository,
    project_repository: ProjectRepository,
    intelligence_id: UUID,
    user: ApiUser,
) -> Intelligence:
    """Fetch an intelligence, 404 when missing or owned by another org (via its project)."""
    intelligence = intelligence_repository.get_intelligence(intelligence_id)
    if intelligence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Intelligence not found"
        )
    project = project_repository.get_project(intelligence.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Intelligence not found"
        )
    return intelligence


def _architecture_summary(architecture: dict[str, Any] | None) -> str | None:
    """One short human-readable line describing an architecture dict."""
    if not architecture:
        return None
    name = architecture.get("name")
    if isinstance(name, str) and name:
        return name
    kind = architecture.get("kind")
    if isinstance(kind, str) and kind:
        return kind
    keys = sorted(str(key) for key in architecture)
    return ",".join(keys) if keys else None


def _resolve_version(
    version: IntelligenceVersion, model_repository: Any
) -> IntelligenceVersionDetail:
    """Build the version detail with component lineage resolved."""
    resolved: list[ResolvedComponent] = []
    raw_ids = version.components.get("model_version_ids", []) or []
    for raw in raw_ids:
        try:
            version_id = UUID(str(raw))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model version not found: {raw}",
            ) from exc
        model_version = model_repository.get_version(version_id)
        if model_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model version not found: {raw}",
            )
        model = model_repository.get_model(model_version.model_id)
        resolved.append(
            ResolvedComponent(
                model_version_id=model_version.id,
                model_name=model.name if model is not None else str(model_version.model_id),
                version=model_version.version,
                architecture_summary=_architecture_summary(model_version.architecture),
                training_run_id=model_version.training_run_id,
                seed=model_version.seed,
                code_version=model_version.code_version,
            )
        )
    return IntelligenceVersionDetail(
        **version.model_dump(),
        resolved_components=resolved,
        baseline_refs=list(version.components.get("baseline_refs", []) or []),
        harness=dict(version.components.get("harness", {}) or {}),
    )


@router.post(
    "/projects/{project_id}/intelligences",
    response_model=Intelligence,
    status_code=status.HTTP_201_CREATED,
)
def create_intelligence(
    project_id: UUID,
    payload: IntelligenceCreate,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Intelligence:
    """Create an intelligence for the caller's project."""
    _get_project_or_404(project_repository, project_id, user)
    intelligence = Intelligence(
        id=uuid4(),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        primitive=payload.primitive,
        created_at=_utc_now(),
    )
    return intelligence_repository.create_intelligence(intelligence)


@router.get("/projects/{project_id}/intelligences", response_model=list[Intelligence])
def list_intelligences(
    project_id: UUID,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Intelligence]:
    """List all intelligences of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return intelligence_repository.list_intelligences(project_id)


@router.get("/intelligences/{intelligence_id}", response_model=Intelligence)
def get_intelligence(
    intelligence_id: UUID,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Intelligence:
    """Intelligence detail; 404 when missing or owned by another org."""
    return _get_intelligence_or_404(
        intelligence_repository, project_repository, intelligence_id, user
    )


@router.post(
    "/intelligences/{intelligence_id}/versions",
    response_model=IntelligenceVersion,
    status_code=status.HTTP_201_CREATED,
)
def create_intelligence_version(
    intelligence_id: UUID,
    payload: IntelligenceVersionCreate,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    # Any: the app.models ModelRepository Protocol (TYPE_CHECKING-only import
    # keeps this package cycle-free; see get_model_repository_hook).
    model_repository: Any = Depends(get_model_repository_hook),
    user: ApiUser = Depends(get_current_user),
) -> IntelligenceVersion:
    """Publish an immutable intelligence version (number auto-increments)."""
    intelligence = _get_intelligence_or_404(
        intelligence_repository, project_repository, intelligence_id, user
    )
    for version_id in payload.components.model_version_ids:
        if model_repository.get_version(version_id) is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Model version not found: {version_id}",
            )
    next_number = (
        max(
            (v.version for v in intelligence_repository.list_versions(intelligence.id)),
            default=0,
        )
        + 1
    )
    version = IntelligenceVersion(
        id=uuid4(),
        intelligence_id=intelligence.id,
        version=next_number,
        components=payload.components.model_dump(mode="json"),
        notes=payload.notes,
        created_at=_utc_now(),
    )
    return intelligence_repository.create_version(version)


@router.get(
    "/intelligences/{intelligence_id}/versions",
    response_model=list[IntelligenceVersion],
)
def list_intelligence_versions(
    intelligence_id: UUID,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[IntelligenceVersion]:
    """Version chain of an intelligence, ascending."""
    intelligence = _get_intelligence_or_404(
        intelligence_repository, project_repository, intelligence_id, user
    )
    return intelligence_repository.list_versions(intelligence.id)


@router.get(
    "/intelligences/{intelligence_id}/versions/{version}",
    response_model=IntelligenceVersionDetail,
)
def get_intelligence_version(
    intelligence_id: UUID,
    version: int,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    # Any: the app.models ModelRepository Protocol (see get_model_repository_hook).
    model_repository: Any = Depends(get_model_repository_hook),
    user: ApiUser = Depends(get_current_user),
) -> IntelligenceVersionDetail:
    """One intelligence version with its component lineage resolved."""
    intelligence = _get_intelligence_or_404(
        intelligence_repository, project_repository, intelligence_id, user
    )
    intelligence_version = intelligence_repository.get_version_by_number(
        intelligence.id, version
    )
    if intelligence_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Intelligence version not found"
        )
    return _resolve_version(intelligence_version, model_repository)


@router.post(
    "/intelligences/{intelligence_id}/promote",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def promote_intelligence(
    intelligence_id: UUID,
    intelligence_repository: IntelligenceRepository = Depends(get_intelligence_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> None:
    """HONEST STUB: candidate promotion is implemented in Phase 6
    (Candidate Experiment Engine). This endpoint exists so the registry
    contract is complete; it always answers 501."""
    _get_intelligence_or_404(
        intelligence_repository, project_repository, intelligence_id, user
    )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Candidate promotion is implemented in Phase 6 (Candidate Experiment Engine).",
    )
