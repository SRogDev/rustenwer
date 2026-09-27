"""Models endpoints: models + immutable versions (Phase 1; lineage in Phase 3).

Versioning rules (§43): versions are immutable — the repository offers no
update or delete for them. Version numbers are assigned by the server
(auto-increment); publishing with an explicit version number is not
supported.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import ApiUser, Model, ModelVersion

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class ModelCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class ModelVersionCreate(BaseModel):
    training_run_id: UUID | None = None
    architecture: dict[str, Any] | None = None
    size_bytes: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_uri: str | None = None
    # -- Phase 3 lineage (§43) -------------------------------------------
    dataset_version_id: UUID | None = None
    training_strategy: dict[str, Any] | None = None
    code_version: str | None = None
    template_version: str | None = None
    seed: int | None = None
    base_model: str | None = None


class VersionChange(BaseModel):
    from_version: int
    to_version: int
    changed_fields: list[str]


class ModelLineage(BaseModel):
    versions: list[ModelVersion]
    changes: list[VersionChange]


# Fields compared key-by-key when diffing consecutive versions for the
# lineage endpoint: the architecture, the metrics, and the Phase-3 lineage
# fields.
_LINEAGE_DIFF_FIELDS = (
    "architecture",
    "metrics",
    "dataset_version_id",
    "training_strategy",
    "code_version",
    "template_version",
    "seed",
    "base_model",
    "size_bytes",
    "artifact_uri",
    "training_run_id",
)


def _changed_fields(previous: ModelVersion, current: ModelVersion) -> list[str]:
    """Names of the lineage-diffed fields that differ between two versions."""
    return [
        field
        for field in _LINEAGE_DIFF_FIELDS
        if getattr(previous, field) != getattr(current, field)
    ]


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class ModelRepository(Protocol):
    """Storage contract for models and their versions."""

    def list_models(self, project_id: UUID) -> list[Model]:
        """All models belonging to the given project."""
        ...

    def get_model(self, model_id: UUID) -> Model | None:
        """A model by id, or None when it does not exist."""
        ...

    def create_model(self, model: Model) -> Model:
        """Persist a fully-formed model."""
        ...

    def list_versions(self, model_id: UUID) -> list[ModelVersion]:
        """All versions of a model, ascending by version number."""
        ...

    def get_version(self, version_id: UUID) -> ModelVersion | None:
        """A version by its id, or None when it does not exist."""
        ...

    def get_version_by_number(self, model_id: UUID, version: int) -> ModelVersion | None:
        """A model's version by its number, or None when missing."""
        ...

    def create_version(self, version: ModelVersion) -> ModelVersion:
        """Persist an immutable model version."""
        ...


class InMemoryModelRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._models: dict[UUID, Model] = {}
        self._versions: dict[UUID, ModelVersion] = {}

    def list_models(self, project_id: UUID) -> list[Model]:
        with self._lock:
            return [m for m in self._models.values() if m.project_id == project_id]

    def get_model(self, model_id: UUID) -> Model | None:
        with self._lock:
            return self._models.get(model_id)

    def create_model(self, model: Model) -> Model:
        with self._lock:
            self._models[model.id] = model
            return model

    def list_versions(self, model_id: UUID) -> list[ModelVersion]:
        with self._lock:
            versions = [v for v in self._versions.values() if v.model_id == model_id]
            return sorted(versions, key=lambda v: v.version)

    def get_version(self, version_id: UUID) -> ModelVersion | None:
        with self._lock:
            return self._versions.get(version_id)

    def get_version_by_number(self, model_id: UUID, version: int) -> ModelVersion | None:
        with self._lock:
            for v in self._versions.values():
                if v.model_id == model_id and v.version == version:
                    return v
            return None

    def create_version(self, version: ModelVersion) -> ModelVersion:
        with self._lock:
            self._versions[version.id] = version
            return version


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["models"])


def get_model_repository() -> ModelRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryModelRepository per test.
    """
    return _default_repository


_default_repository = InMemoryModelRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_model_or_404(
    model_repository: ModelRepository,
    project_repository: ProjectRepository,
    model_id: UUID,
    user: ApiUser,
) -> Model:
    """Fetch a model, 404 when missing or owned by another org (via its project)."""
    model = model_repository.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    project = project_repository.get_project(model.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.post("/projects/{project_id}/models", response_model=Model,
             status_code=status.HTTP_201_CREATED)
def create_model(
    project_id: UUID,
    payload: ModelCreate,
    model_repository: ModelRepository = Depends(get_model_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Model:
    """Create a model for the caller's project."""
    _get_project_or_404(project_repository, project_id, user)
    model = Model(
        id=uuid4(),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        created_at=_utc_now(),
    )
    return model_repository.create_model(model)


@router.get("/projects/{project_id}/models", response_model=list[Model])
def list_models(
    project_id: UUID,
    model_repository: ModelRepository = Depends(get_model_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Model]:
    """List all models of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return model_repository.list_models(project_id)


@router.post("/models/{model_id}/versions", response_model=ModelVersion,
             status_code=status.HTTP_201_CREATED)
def create_model_version(
    model_id: UUID,
    payload: ModelVersionCreate,
    model_repository: ModelRepository = Depends(get_model_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> ModelVersion:
    """Add an immutable version to a model (version numbers increment)."""
    model = _get_model_or_404(model_repository, project_repository, model_id, user)
    next_number = max(
        (v.version for v in model_repository.list_versions(model.id)), default=0
    ) + 1
    version = ModelVersion(
        id=uuid4(),
        model_id=model.id,
        version=next_number,
        training_run_id=payload.training_run_id,
        architecture=payload.architecture,
        size_bytes=payload.size_bytes,
        metrics=payload.metrics,
        artifact_uri=payload.artifact_uri,
        dataset_version_id=payload.dataset_version_id,
        training_strategy=payload.training_strategy,
        code_version=payload.code_version,
        template_version=payload.template_version,
        seed=payload.seed,
        base_model=payload.base_model,
        created_at=_utc_now(),
    )
    return model_repository.create_version(version)


@router.get("/models/{model_id}/versions", response_model=list[ModelVersion])
def list_model_versions(
    model_id: UUID,
    model_repository: ModelRepository = Depends(get_model_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[ModelVersion]:
    """List a model's versions."""
    model = _get_model_or_404(model_repository, project_repository, model_id, user)
    return model_repository.list_versions(model.id)


@router.get("/models/{model_id}/versions/{version}", response_model=ModelVersion)
def get_model_version(
    model_id: UUID,
    version: int,
    model_repository: ModelRepository = Depends(get_model_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> ModelVersion:
    """One model version with its full lineage; 404 when missing or foreign-org."""
    model = _get_model_or_404(model_repository, project_repository, model_id, user)
    model_version = model_repository.get_version_by_number(model.id, version)
    if model_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found"
        )
    return model_version


@router.get("/models/{model_id}/lineage", response_model=ModelLineage)
def get_model_lineage(
    model_id: UUID,
    model_repository: ModelRepository = Depends(get_model_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> ModelLineage:
    """Version chain of a model plus what changed between consecutive versions."""
    model = _get_model_or_404(model_repository, project_repository, model_id, user)
    versions = model_repository.list_versions(model.id)
    changes = [
        VersionChange(
            from_version=previous.version,
            to_version=current.version,
            changed_fields=_changed_fields(previous, current),
        )
        for previous, current in zip(versions, versions[1:], strict=False)
    ]
    return ModelLineage(versions=versions, changes=changes)
