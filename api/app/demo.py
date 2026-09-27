"""Termination demo endpoint (Phase 1, plan §7).

POST /api/v1/projects/{project_id}/demo/termination seeds the deterministic
termination fixture (spec + dataset + version), diagnoses the spec, runs the
baseline evaluation, and returns everything. All data is labeled
DETERMINISTIC FIXTURE — no real training happens here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from shared.domain import (
    ApiUser,
    Dataset,
    DatasetVersion,
    Evaluation,
    EvaluationResults,
    EvaluationStatus,
    IntelligenceSpec,
    IntelligenceSpecStatus,
)
from shared.services.baselines import run_baselines
from shared.services.datasets import validate_dataset_version
from shared.services.diagnosis import diagnose_spec
from shared.services.fixtures import termination_dataset_rows, termination_spec_fields

from app.auth import get_current_user
from app.datasets import DatasetRepository, get_dataset_repository
from app.evaluations import EvaluationRepository, get_evaluation_repository
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository
from app.specs import SpecRepository, get_spec_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


class TerminationDemoResult(BaseModel):
    """Demo response: the seeded spec, dataset, version, and baseline evaluation."""

    spec: IntelligenceSpec
    dataset: Dataset
    version: DatasetVersion
    evaluation: Evaluation


router = APIRouter(prefix="/api/v1", tags=["demo"])


@router.post("/projects/{project_id}/demo/termination", response_model=TerminationDemoResult)
def demo_termination(
    project_id: UUID,
    spec_repository: SpecRepository = Depends(get_spec_repository),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    evaluation_repository: EvaluationRepository = Depends(get_evaluation_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> TerminationDemoResult:
    """Seed the §7 termination fixture and run its baseline evaluation."""
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    now = _utc_now()

    # 1. Spec from the fixture, diagnosed immediately.
    spec_fields = termination_spec_fields()
    spec = IntelligenceSpec(
        id=uuid4(),
        project_id=project_id,
        status=IntelligenceSpecStatus.DRAFT,
        version=1,
        **spec_fields,
    )
    spec = spec_repository.create_spec(spec)
    diagnose_spec(spec)  # deterministic; result surfaced via GET /specs/{id}/diagnose
    spec = spec_repository.update_spec(spec.id, {"status": IntelligenceSpecStatus.DIAGNOSED})
    assert spec is not None

    # 2. Dataset + version 1 from the fixture rows.
    dataset = dataset_repository.create_dataset(
        Dataset(
            id=uuid4(),
            project_id=project_id,
            name="termination-demo-dataset",
            description="DETERMINISTIC FIXTURE — 12 labeled search states (plan §7).",
            row_count=0,
            created_at=now,
            updated_at=now,
        )
    )
    rows = termination_dataset_rows()
    report = validate_dataset_version(dataset.id, 1, rows, "label")
    version = dataset_repository.create_version(
        DatasetVersion(
            id=uuid4(),
            dataset_id=dataset.id,
            version=1,
            column_schema=report.column_schema,
            split_config=report.recommended_split,
            stats=report,
            created_at=now,
        ),
        rows,
        "label",
    )
    dataset_repository.update_dataset(dataset.id, {"row_count": report.row_count})
    dataset = dataset_repository.get_dataset(dataset.id)
    assert dataset is not None

    # 3. Synchronous baseline evaluation.
    baseline_report = run_baselines(spec, version.id, rows, label_column="label")
    best = baseline_report.best_baseline
    evaluation = evaluation_repository.create_evaluation(
        Evaluation(
            id=uuid4(),
            project_id=project_id,
            spec_id=spec.id,
            dataset_version_id=version.id,
            name="termination-demo-baseline",
            status=EvaluationStatus.COMPLETED,
            results=EvaluationResults(
                baselines=baseline_report.baselines,
                bar_to_beat=baseline_report.bar_to_beat,
                recommendation=(
                    f"Best baseline '{best}' reaches accuracy "
                    f"{baseline_report.bar_to_beat.accuracy:.3f}. Train a candidate "
                    "only if it can beat this bar (Rule 9)."
                ),
                evaluated_at=baseline_report.evaluated_at,
            ),
            created_at=now,
            completed_at=now,
        )
    )

    return TerminationDemoResult(
        spec=spec, dataset=dataset, version=version, evaluation=evaluation
    )
