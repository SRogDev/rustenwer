"""Deployment orchestration for intelligences (Phase 4, plan §31, §33).

A deployment serves an immutable intelligence version. The legacy path —
deploying a bare model_version_id — auto-creates a single-model intelligence
wrapping it, so old clients keep working while the registry stays
intelligence-first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from shared.domain import (
    ArchitectureComponent,
    ArchitectureComponentKind,
    Intelligence,
    IntelligenceArchitecture,
    IntelligenceVersion,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class DeploymentTargetError(LookupError):
    """A deployment references something that does not resolve."""


def resolve_deployment_target(
    deployment: Any,
    intelligence_repository: Any,
) -> tuple[Intelligence, IntelligenceVersion]:
    """Resolve a deployment to its (intelligence, immutable version).

    Raises DeploymentTargetError when the deployment has no intelligence
    version or the version no longer resolves.
    """
    version_id = getattr(deployment, "intelligence_version_id", None)
    if version_id is None:
        raise DeploymentTargetError("deployment has no intelligence_version_id")
    version = intelligence_repository.get_version_by_id(version_id)
    if version is None:
        raise DeploymentTargetError(
            f"intelligence version not found: {version_id}"
        )
    intelligence = intelligence_repository.get_intelligence(version.intelligence_id)
    if intelligence is None:
        raise DeploymentTargetError(
            f"intelligence not found: {version.intelligence_id}"
        )
    return intelligence, version


def ensure_model_backcompat_intelligence(
    *,
    project_id: UUID,
    model: Any,
    model_version: Any,
    classes: list[str] | None,
    feature_key: str,
    intelligence_repository: Any,
) -> tuple[Intelligence, IntelligenceVersion]:
    """Auto-create a single-model intelligence wrapping a model version.

    This is the Phase-4 back-compat path for `model_version_id` deployments:
    the model becomes one component of a real intelligence (single_model
    architecture, pinned classes + feature key), so inference, diffing and
    lineage all work through the intelligence abstraction.
    """
    pinned = [str(c) for c in (classes or [])]
    intelligence = Intelligence(
        id=uuid4(),
        project_id=project_id,
        name=f"{model.name if model is not None else model_version.model_id} (auto)",
        description=(
            "Auto-created back-compat wrapper: deploys model "
            f"{model.name} v{model_version.version} as a single-model intelligence."
        ),
        primitive=None,
        created_at=_utc_now(),
    )
    intelligence_repository.create_intelligence(intelligence)
    architecture = IntelligenceArchitecture(
        kind="single_model",
        components=[
            ArchitectureComponent(
                kind=ArchitectureComponentKind.MODEL_VERSION,
                ref=str(model_version.id),
                label=model.name,
                config={"classes": pinned, "feature_key": feature_key},
            )
        ],
        execution_order=[0],
        notes="Auto-created by the model_version_id deployment path.",
    )
    version = IntelligenceVersion(
        id=uuid4(),
        intelligence_id=intelligence.id,
        version=1,
        components={
            "model_version_ids": [str(model_version.id)],
            "baseline_refs": [],
            "harness": {},
        },
        architecture=architecture,
        notes="Auto-created back-compat wrapper (model deploy path).",
        created_at=_utc_now(),
    )
    intelligence_repository.create_version(version)
    return intelligence, version
