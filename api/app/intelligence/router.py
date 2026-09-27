"""Intelligence serving endpoints (Phase 4, plan §33, §34).

GET  /api/v1/inference/providers   — capability entries for every provider
POST /api/v1/deployments/{id}/infer — run a deployed intelligence version

The infer endpoint executes the deployment's provider against the pinned,
immutable intelligence version: input validation -> component execution ->
primitive-shaped machine-readable output. Every call records an INFERENCE
usage event (local CPU cost is honestly 0.0).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from shared.domain import (
    ApiUser,
    Deployment,
    DeploymentStatus,
    InferenceRequest,
    InferenceResponse,
    ProviderInfo,
    UsageEvent,
    UsageKind,
    UsageScope,
)

from app.auth import get_current_user
from app.deployments import DeploymentRepository, get_deployment_repository
from app.intelligence.inference import (
    PROVIDERS,
    ComponentExecutionError,
    InferenceContext,
    ProviderNotConfigured,
    SchemaValidationError,
    get_provider,
)
from app.intelligence.service import DeploymentTargetError, resolve_deployment_target
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


router = APIRouter(prefix="/api/v1", tags=["inference"])


def get_intelligence_repository_hook() -> Any:
    """Lazy hook (cycle-free) for the intelligence repository."""
    from app.registry.intelligences import get_intelligence_repository

    return get_intelligence_repository()


def get_model_repository_hook() -> Any:
    """Lazy hook (cycle-free) for the model repository."""
    from app.models import get_model_repository

    return get_model_repository()


def get_usage_repository_hook() -> Any:
    """Lazy hook (cycle-free) for the usage repository."""
    from app.usage import get_usage_repository

    return get_usage_repository()


def _get_deployment_or_404(
    deployment_repository: DeploymentRepository,
    project_repository: ProjectRepository,
    deployment_id: UUID,
    user: ApiUser,
) -> Deployment:
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


@router.get("/inference/providers", response_model=list[ProviderInfo])
def list_providers(user: ApiUser = Depends(get_current_user)) -> list[ProviderInfo]:
    """Capability entries for every known inference provider (§34)."""
    return [provider.capabilities() for provider in PROVIDERS.values()]


@router.post(
    "/deployments/{deployment_id}/infer",
    response_model=InferenceResponse,
    status_code=status.HTTP_200_OK,
)
def infer_deployment(
    deployment_id: UUID,
    payload: InferenceRequest,
    deployment_repository: DeploymentRepository = Depends(get_deployment_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    # Any: repository Protocols resolved lazily (see hooks above).
    intelligence_repository: Any = Depends(get_intelligence_repository_hook),
    model_repository: Any = Depends(get_model_repository_hook),
    usage_repository: Any = Depends(get_usage_repository_hook),
    user: ApiUser = Depends(get_current_user),
) -> InferenceResponse:
    """Run one inference against a deployed intelligence version."""
    from app.config import get_settings

    deployment = _get_deployment_or_404(
        deployment_repository, project_repository, deployment_id, user
    )
    if deployment.status is not DeploymentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Deployment is {deployment.status.value}; "
                "only ACTIVE deployments serve inference."
            ),
        )
    try:
        intelligence, version = resolve_deployment_target(
            deployment, intelligence_repository
        )
    except DeploymentTargetError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    try:
        provider = get_provider(deployment.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    ctx = InferenceContext(
        model_repository=model_repository,
        artifact_root=Path(get_settings().data_dir) / "artifacts",
    )
    start = perf_counter()
    try:
        output = provider.infer(
            intelligence=intelligence,
            version=version,
            inputs=payload.inputs,
            ctx=ctx,
        )
    except SchemaValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ProviderNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    except ComponentExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    latency_ms = (perf_counter() - start) * 1000.0

    usage_repository.record_event(
        UsageEvent(
            id=uuid4(),
            project_id=deployment.project_id,
            scope=UsageScope.INFERENCE,
            scope_id=deployment.id,
            kind=UsageKind.INFERENCE,
            quantity=1.0,
            unit="request",
            cost_usd=0.0,  # local CPU: honestly zero
            recorded_at=_utc_now(),
        )
    )
    return InferenceResponse(
        output=output,
        intelligence_id=intelligence.id,
        intelligence_version_id=version.id,
        deployment_id=deployment.id,
        primitive=intelligence.primitive,
        latency_ms=latency_ms,
        provider=deployment.provider,
    )
