"""Method catalog + recommendation + research endpoints (Phase 5).

Conventions follow api/app/evaluation/router.py: in-memory repositories
behind Protocols, `get_*_repository` dependency hooks, auth via
`get_current_user`, 404 for missing, 409 for state faults.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from shared.domain import (
    ApiUser,
    BaselineReport,
    DiagnosisResult,
    IntelligenceSpec,
    MethodCategory,
    MethodRecommendation,
    MethodValidationStatus,
    ResearchFinding,
    TrainingMethod,
)
from shared.services.methods import TRAINING_METHODS

from app.auth import get_current_user
from app.methods.recommend import detect_environment, recommend_methods
from app.methods.research import (
    ResearchFindingRepository,
    get_research_repository,
)

router = APIRouter(prefix="/api/v1", tags=["methods"])


def get_method_catalog() -> list[TrainingMethod]:
    """Dependency hook: the seeded method catalog (tests may override)."""
    return TRAINING_METHODS


# --------------------------------------------------------------------------
# Methods
# --------------------------------------------------------------------------


@router.get("/methods", response_model=list[TrainingMethod])
def list_methods(
    category: MethodCategory | None = Query(default=None),
    method_status: MethodValidationStatus | None = Query(default=None, alias="status"),
    catalog: list[TrainingMethod] = Depends(get_method_catalog),
    user: ApiUser = Depends(get_current_user),
) -> list[TrainingMethod]:
    """List the training-method catalog; filter by ?category= / ?status=."""
    methods = catalog
    if category is not None:
        methods = [m for m in methods if m.category == category]
    if method_status is not None:
        methods = [m for m in methods if m.status == method_status]
    return methods


@router.get("/methods/{slug}")
def get_method(
    slug: str,
    catalog: list[TrainingMethod] = Depends(get_method_catalog),
    user: ApiUser = Depends(get_current_user),
) -> dict:
    """All versions of one method plus the current (highest) version."""
    versions = sorted(
        (m for m in catalog if m.slug == slug), key=lambda m: m.version
    )
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown training method: {slug!r}",
        )
    return {
        "slug": slug,
        "versions": [m.model_dump(mode="json") for m in versions],
        "current": versions[-1].model_dump(mode="json"),
    }


class RecommendRequest(BaseModel):
    spec: IntelligenceSpec
    diagnosis: DiagnosisResult | None = None
    baseline_report: BaselineReport | None = None
    allow_generic: bool = False


@router.post("/methods/recommend", response_model=MethodRecommendation)
def recommend(
    body: RecommendRequest,
    user: ApiUser = Depends(get_current_user),
) -> MethodRecommendation:
    """Rank compatible training methods for (spec, diagnosis); veto the rest.

    The environment (CUDA/unsloth) is detected once per request and passed
    into the pure engine — the engine itself stays side-effect free.
    """
    environment = detect_environment()
    return recommend_methods(
        body.spec,
        body.diagnosis,
        body.baseline_report,
        environment,
        allow_generic=body.allow_generic,
    )


# --------------------------------------------------------------------------
# Research
# --------------------------------------------------------------------------


@router.get("/research", response_model=list[ResearchFinding])
def list_research(
    repository: ResearchFindingRepository = Depends(get_research_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[ResearchFinding]:
    """List the seeded research findings (plan §52)."""
    return repository.list_findings()
