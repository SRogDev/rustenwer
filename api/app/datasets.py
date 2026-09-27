"""Datasets endpoints: datasets + versions + validation (Phase 1).

Version rows are stored inline in the in-memory repository (dict
version_id -> (rows, label_column)). A future migration moves them to
artifact storage — rows never leave the server (version payloads exclude
them by construction: DatasetVersion has no rows field).
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import ApiUser, Dataset, DatasetFormat, DatasetReport, DatasetVersion
from shared.services.datasets import validate_dataset_version

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    format: DatasetFormat = DatasetFormat.INLINE


class VersionCreate(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1)
    label_column: str | None = None


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class DatasetRepository(Protocol):
    """Storage contract for datasets and their versions."""

    def list_datasets(self, project_id: UUID) -> list[Dataset]:
        """All datasets belonging to the given project."""
        ...

    def get_dataset(self, dataset_id: UUID) -> Dataset | None:
        """A dataset by id, or None when it does not exist."""
        ...

    def create_dataset(self, dataset: Dataset) -> Dataset:
        """Persist a fully-formed dataset."""
        ...

    def update_dataset(self, dataset_id: UUID, fields: dict[str, Any]) -> Dataset | None:
        """Apply field updates; None when the dataset does not exist."""
        ...

    def list_versions(self, dataset_id: UUID) -> list[DatasetVersion]:
        """All versions of a dataset, ascending by version number."""
        ...

    def get_version(self, version_id: UUID) -> DatasetVersion | None:
        """A version by its id, or None when it does not exist."""
        ...

    def get_version_by_number(self, dataset_id: UUID, version: int) -> DatasetVersion | None:
        """A version by (dataset_id, version number)."""
        ...

    def create_version(
        self,
        version: DatasetVersion,
        rows: list[dict[str, Any]],
        label_column: str | None,
    ) -> DatasetVersion:
        """Persist a version plus its rows (in-memory until artifact storage lands)."""
        ...

    def get_rows(self, version_id: UUID) -> list[dict[str, Any]] | None:
        """Row data for a version id (server-side only)."""
        ...

    def get_label_column(self, version_id: UUID) -> str | None:
        """The label column recorded with a version's rows."""
        ...


class InMemoryDatasetRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._datasets: dict[UUID, Dataset] = {}
        self._versions: dict[UUID, DatasetVersion] = {}
        self._rows: dict[UUID, tuple[list[dict[str, Any]], str | None]] = {}

    def list_datasets(self, project_id: UUID) -> list[Dataset]:
        with self._lock:
            return [d for d in self._datasets.values() if d.project_id == project_id]

    def get_dataset(self, dataset_id: UUID) -> Dataset | None:
        with self._lock:
            return self._datasets.get(dataset_id)

    def create_dataset(self, dataset: Dataset) -> Dataset:
        with self._lock:
            self._datasets[dataset.id] = dataset
            return dataset

    def update_dataset(self, dataset_id: UUID, fields: dict[str, Any]) -> Dataset | None:
        with self._lock:
            dataset = self._datasets.get(dataset_id)
            if dataset is None:
                return None
            updated = dataset.model_copy(update={**fields, "updated_at": _utc_now()})
            self._datasets[dataset_id] = updated
            return updated

    def list_versions(self, dataset_id: UUID) -> list[DatasetVersion]:
        with self._lock:
            versions = [v for v in self._versions.values() if v.dataset_id == dataset_id]
            return sorted(versions, key=lambda v: v.version)

    def get_version(self, version_id: UUID) -> DatasetVersion | None:
        with self._lock:
            return self._versions.get(version_id)

    def get_version_by_number(self, dataset_id: UUID, version: int) -> DatasetVersion | None:
        with self._lock:
            for v in self._versions.values():
                if v.dataset_id == dataset_id and v.version == version:
                    return v
            return None

    def create_version(
        self,
        version: DatasetVersion,
        rows: list[dict[str, Any]],
        label_column: str | None,
    ) -> DatasetVersion:
        with self._lock:
            self._versions[version.id] = version
            self._rows[version.id] = (rows, label_column)
            return version

    def get_rows(self, version_id: UUID) -> list[dict[str, Any]] | None:
        with self._lock:
            entry = self._rows.get(version_id)
            return entry[0] if entry else None

    def get_label_column(self, version_id: UUID) -> str | None:
        with self._lock:
            entry = self._rows.get(version_id)
            return entry[1] if entry else None


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["datasets"])


def get_dataset_repository() -> DatasetRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryDatasetRepository per test.
    """
    return _default_repository


_default_repository = InMemoryDatasetRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_dataset_or_404(
    dataset_repository: DatasetRepository,
    project_repository: ProjectRepository,
    dataset_id: UUID,
    user: ApiUser,
) -> Dataset:
    """Fetch a dataset, 404 when missing or owned by another org (via its project)."""
    dataset = dataset_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    project = project_repository.get_project(dataset.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


def _get_version_or_404(
    dataset_repository: DatasetRepository,
    project_repository: ProjectRepository,
    dataset_id: UUID,
    version_number: int,
    user: ApiUser,
) -> DatasetVersion:
    dataset = _get_dataset_or_404(dataset_repository, project_repository, dataset_id, user)
    version = dataset_repository.get_version_by_number(dataset.id, version_number)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found"
        )
    return version


@router.post("/projects/{project_id}/datasets", response_model=Dataset,
             status_code=status.HTTP_201_CREATED)
def create_dataset(
    project_id: UUID,
    payload: DatasetCreate,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Dataset:
    """Create a dataset for the caller's project."""
    _get_project_or_404(project_repository, project_id, user)
    now = _utc_now()
    dataset = Dataset(
        id=uuid4(),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        format=payload.format,
        row_count=0,
        created_at=now,
        updated_at=now,
    )
    return dataset_repository.create_dataset(dataset)


@router.get("/projects/{project_id}/datasets", response_model=list[Dataset])
def list_datasets(
    project_id: UUID,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Dataset]:
    """List all datasets of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return dataset_repository.list_datasets(project_id)


@router.get("/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(
    dataset_id: UUID,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Dataset:
    """Dataset detail; 404 when missing or owned by another org."""
    return _get_dataset_or_404(dataset_repository, project_repository, dataset_id, user)


@router.post("/datasets/{dataset_id}/versions", response_model=DatasetVersion,
             status_code=status.HTTP_201_CREATED)
def create_version(
    dataset_id: UUID,
    payload: VersionCreate,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> DatasetVersion:
    """Upload rows as a new immutable version; validates and computes the DatasetReport."""
    dataset = _get_dataset_or_404(dataset_repository, project_repository, dataset_id, user)
    next_number = max(
        (v.version for v in dataset_repository.list_versions(dataset.id)), default=0
    ) + 1
    report = validate_dataset_version(dataset.id, next_number, payload.rows, payload.label_column)
    version = DatasetVersion(
        id=uuid4(),
        dataset_id=dataset.id,
        version=next_number,
        column_schema=report.column_schema,
        split_config=report.recommended_split,
        stats=report,
        created_at=_utc_now(),
    )
    dataset_repository.create_version(version, payload.rows, payload.label_column)
    dataset_repository.update_dataset(dataset.id, {"row_count": report.row_count})
    return version


@router.get("/datasets/{dataset_id}/versions", response_model=list[DatasetVersion])
def list_versions(
    dataset_id: UUID,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[DatasetVersion]:
    """List versions (no rows — rows never leave the server in Phase 1)."""
    dataset = _get_dataset_or_404(dataset_repository, project_repository, dataset_id, user)
    return dataset_repository.list_versions(dataset.id)


@router.get("/datasets/{dataset_id}/versions/{version_number}", response_model=DatasetVersion)
def get_version(
    dataset_id: UUID,
    version_number: int,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> DatasetVersion:
    """Version detail (no rows)."""
    return _get_version_or_404(
        dataset_repository, project_repository, dataset_id, version_number, user
    )


@router.post(
    "/datasets/{dataset_id}/versions/{version_number}/validate",
    response_model=DatasetReport,
)
def validate_version(
    dataset_id: UUID,
    version_number: int,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> DatasetReport:
    """Recompute the DatasetReport from the stored rows."""
    version = _get_version_or_404(
        dataset_repository, project_repository, dataset_id, version_number, user
    )
    rows = dataset_repository.get_rows(version.id)
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Version rows not found"
        )
    label_column = dataset_repository.get_label_column(version.id)
    return validate_dataset_version(version.dataset_id, version.version, rows, label_column)
