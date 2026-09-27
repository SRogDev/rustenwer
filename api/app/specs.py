"""Specs endpoints: IntelligenceSpec CRUD + diagnose/approve (Phase 1).

Storage is an in-memory repository behind a Protocol, seeded empty by
design (no fake demo data). A later phase swaps in the Supabase-backed
implementation against migration 002; the router code does not change.
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
    DiagnosisResult,
    IntelligencePrimitive,
    IntelligenceSpec,
    IntelligenceSpecStatus,
)
from shared.services.diagnosis import detect_primitive, diagnose_spec

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class SpecCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    problem_statement: str = Field(min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    # Optional: omit for auto-detect (keyword-based; refined at /diagnose).
    intelligence_primitive: IntelligencePrimitive | None = None
    quality_requirements: dict[str, Any] | None = None
    latency_requirements: dict[str, Any] | None = None
    cost_requirements: dict[str, Any] | None = None
    memory_requirements: dict[str, Any] | None = None
    reliability_requirements: dict[str, Any] | None = None
    constraints: list[str] = Field(default_factory=list)
    available_data: str | None = None
    evaluation_definition: str | None = None
    deployment_requirements: dict[str, Any] | None = None
    human_review_policy: str | None = None


class SpecUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    problem_statement: str | None = Field(default=None, min_length=1)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    intelligence_primitive: IntelligencePrimitive | None = None
    quality_requirements: dict[str, Any] | None = None
    latency_requirements: dict[str, Any] | None = None
    cost_requirements: dict[str, Any] | None = None
    memory_requirements: dict[str, Any] | None = None
    reliability_requirements: dict[str, Any] | None = None
    constraints: list[str] | None = None
    available_data: str | None = None
    evaluation_definition: str | None = None
    deployment_requirements: dict[str, Any] | None = None
    human_review_policy: str | None = None


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class SpecRepository(Protocol):
    """Storage contract for intelligence specs."""

    def list_specs(self, project_id: UUID) -> list[IntelligenceSpec]:
        """All specs belonging to the given project."""
        ...

    def get_spec(self, spec_id: UUID) -> IntelligenceSpec | None:
        """A spec by id, or None when it does not exist."""
        ...

    def create_spec(self, spec: IntelligenceSpec) -> IntelligenceSpec:
        """Persist a fully-formed spec."""
        ...

    def update_spec(self, spec_id: UUID, fields: dict[str, Any]) -> IntelligenceSpec | None:
        """Apply field updates; None when the spec does not exist."""
        ...


class InMemorySpecRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._specs: dict[UUID, IntelligenceSpec] = {}

    def list_specs(self, project_id: UUID) -> list[IntelligenceSpec]:
        with self._lock:
            return [s for s in self._specs.values() if s.project_id == project_id]

    def get_spec(self, spec_id: UUID) -> IntelligenceSpec | None:
        with self._lock:
            return self._specs.get(spec_id)

    def create_spec(self, spec: IntelligenceSpec) -> IntelligenceSpec:
        with self._lock:
            self._specs[spec.id] = spec
            return spec

    def update_spec(self, spec_id: UUID, fields: dict[str, Any]) -> IntelligenceSpec | None:
        with self._lock:
            spec = self._specs.get(spec_id)
            if spec is None:
                return None
            updated = spec.model_copy(update=fields)
            self._specs[spec_id] = updated
            return updated


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["specs"])


def get_spec_repository() -> SpecRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemorySpecRepository per test.
    """
    return _default_repository


_default_repository = InMemorySpecRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_spec_or_404(
    spec_repository: SpecRepository,
    project_repository: ProjectRepository,
    spec_id: UUID,
    user: ApiUser,
) -> IntelligenceSpec:
    """Fetch a spec, 404 when missing or owned by another org (via its project)."""
    spec = spec_repository.get_spec(spec_id)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found")
    project = project_repository.get_project(spec.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found")
    return spec


@router.post("/projects/{project_id}/specs", response_model=IntelligenceSpec,
             status_code=status.HTTP_201_CREATED)
def create_spec(
    project_id: UUID,
    payload: SpecCreate,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> IntelligenceSpec:
    """Create a spec in DRAFT status for the caller's project.

    `intelligence_primitive` is optional: when omitted it is auto-detected
    from the problem statement (keyword-based; the Diagnostic Agent refines
    it at `/diagnose` time).
    """
    _get_project_or_404(project_repository, project_id, user)
    fields = payload.model_dump()
    if fields.get("intelligence_primitive") is None:
        fields["intelligence_primitive"] = detect_primitive(payload.problem_statement)
    spec = IntelligenceSpec(
        id=uuid4(),
        project_id=project_id,
        status=IntelligenceSpecStatus.DRAFT,
        version=1,
        **fields,
    )
    return spec_repository.create_spec(spec)


@router.get("/projects/{project_id}/specs", response_model=list[IntelligenceSpec])
def list_specs(
    project_id: UUID,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[IntelligenceSpec]:
    """List all specs of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return spec_repository.list_specs(project_id)


@router.get("/specs/{spec_id}", response_model=IntelligenceSpec)
def get_spec(
    spec_id: UUID,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> IntelligenceSpec:
    """Spec detail; 404 when missing or owned by another org."""
    return _get_spec_or_404(spec_repository, project_repository, spec_id, user)


@router.patch("/specs/{spec_id}", response_model=IntelligenceSpec)
def update_spec(
    spec_id: UUID,
    payload: SpecUpdate,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> IntelligenceSpec:
    """Update DRAFT fields; 409 when the spec is not in DRAFT."""
    spec = _get_spec_or_404(spec_repository, project_repository, spec_id, user)
    if spec.status != IntelligenceSpecStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit spec in status {spec.status.value}; only DRAFT specs are editable",
        )
    updated = spec_repository.update_spec(spec_id, payload.model_dump(exclude_unset=True))
    assert updated is not None  # guarded by _get_spec_or_404 above
    return updated


@router.post("/specs/{spec_id}/diagnose", response_model=DiagnosisResult)
def diagnose(
    spec_id: UUID,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> DiagnosisResult:
    """Run the Specification/Diagnostic agent; status -> DIAGNOSED.

    Allowed from DRAFT/DIAGNOSED. Re-diagnosis bumps nothing — diagnosis is
    not versioned in Phase 1.
    """
    spec = _get_spec_or_404(spec_repository, project_repository, spec_id, user)
    if spec.status not in (IntelligenceSpecStatus.DRAFT, IntelligenceSpecStatus.DIAGNOSED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot diagnose spec in status {spec.status.value}",
        )
    result = diagnose_spec(spec)
    spec_repository.update_spec(spec_id, {"status": IntelligenceSpecStatus.DIAGNOSED})
    return result


@router.post("/specs/{spec_id}/approve", response_model=IntelligenceSpec)
def approve_spec(
    spec_id: UUID,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> IntelligenceSpec:
    """Approve a spec: DRAFT/DIAGNOSED -> APPROVED; 409 otherwise."""
    spec = _get_spec_or_404(spec_repository, project_repository, spec_id, user)
    if spec.status not in (IntelligenceSpecStatus.DRAFT, IntelligenceSpecStatus.DIAGNOSED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve spec in status {spec.status.value}",
        )
    updated = spec_repository.update_spec(spec_id, {"status": IntelligenceSpecStatus.APPROVED})
    assert updated is not None  # guarded by _get_spec_or_404 above
    return updated
