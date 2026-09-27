"""Usage endpoints: record cost events + project summary (Phase 1, §45)."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.domain import (
    ApiUser,
    UsageEvent,
    UsageKind,
    UsageRollups,
    UsageScope,
    UsageSummary,
)
from shared.services.costing import rollup_usage, summarize_usage

from app.auth import get_current_user
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class UsageEventCreate(BaseModel):
    scope: UsageScope
    scope_id: UUID
    kind: UsageKind
    quantity: float = 0.0
    unit: str = ""
    cost_usd: float = Field(default=0.0, ge=0.0)


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class UsageRepository(Protocol):
    """Storage contract for usage events."""

    def list_events(self, project_id: UUID) -> list[UsageEvent]:
        """All usage events belonging to the given project."""
        ...

    def record_event(self, event: UsageEvent) -> UsageEvent:
        """Persist a fully-formed usage event."""
        ...


class InMemoryUsageRepository:
    """Dict-backed repository for Phase 1. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[UUID, UsageEvent] = {}

    def list_events(self, project_id: UUID) -> list[UsageEvent]:
        with self._lock:
            return [e for e in self._events.values() if e.project_id == project_id]

    def record_event(self, event: UsageEvent) -> UsageEvent:
        with self._lock:
            self._events[event.id] = event
            return event


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["usage"])


def get_usage_repository() -> UsageRepository:
    """Dependency hook: returns the process-wide repository.

    Tests override this with a fresh InMemoryUsageRepository per test.
    """
    return _default_repository


_default_repository = InMemoryUsageRepository()


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.post("/projects/{project_id}/usage-events", response_model=UsageEvent,
             status_code=status.HTTP_201_CREATED)
def record_usage_event(
    project_id: UUID,
    payload: UsageEventCreate,
    usage_repository: UsageRepository = Depends(get_usage_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> UsageEvent:
    """Record a cost/usage event for the caller's project."""
    _get_project_or_404(project_repository, project_id, user)
    event = UsageEvent(
        id=uuid4(),
        project_id=project_id,
        scope=payload.scope,
        scope_id=payload.scope_id,
        kind=payload.kind,
        quantity=payload.quantity,
        unit=payload.unit,
        cost_usd=payload.cost_usd,
        recorded_at=_utc_now(),
    )
    return usage_repository.record_event(event)


@router.get("/projects/{project_id}/usage/summary", response_model=UsageSummary)
def usage_summary(
    project_id: UUID,
    usage_repository: UsageRepository = Depends(get_usage_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> UsageSummary:
    """Aggregated cost view for a project (§45)."""
    _get_project_or_404(project_repository, project_id, user)
    events = usage_repository.list_events(project_id)
    return summarize_usage(project_id, events)


@router.get("/projects/{project_id}/usage/rollups", response_model=UsageRollups)
def usage_rollups(
    project_id: UUID,
    usage_repository: UsageRepository = Depends(get_usage_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> UsageRollups:
    """Per-scope cost rollups: how much each training job / model /
    deployment / evaluation / inference cost (Phase 3, §45)."""
    _get_project_or_404(project_repository, project_id, user)
    events = usage_repository.list_events(project_id)
    return rollup_usage(project_id, events)
