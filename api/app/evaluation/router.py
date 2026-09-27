"""Evaluation endpoints (Phase 3).

Implements the evaluation-runs table from shared/README.md:
benchmarks (seeded global + project-scoped), async cancellable
evaluation runs, and the synchronous candidate comparison report.

Conventions follow api/app/evaluations.py: `_utc_now()`, in-memory
repositories behind Protocols, `get_*_repository` dependency hooks,
org scoping via `_get_project_or_404`, 404 for missing, 409 for
subject/state faults.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from shared.domain import (
    ApiUser,
    Benchmark,
    ComparisonReport,
    ComparisonSubjectResult,
    EvaluationRun,
    EvaluationStatus,
    EvaluationSubject,
    IntelligencePrimitive,
    IntelligenceSpec,
    IntelligenceSpecStatus,
    QualityVector,
    SubjectKind,
    UsageEvent,
    UsageKind,
    UsageScope,
)
from shared.services.baselines import run_baselines

from app.auth import get_current_user
from app.config import get_settings
from app.evaluation.benchmarks import (
    BenchmarkRegistry,
    BenchmarkRepository,
    InMemoryBenchmarkRepository,
)
from app.evaluation.compare import build_comparison_report
from app.evaluation.runner import (
    EvaluationManager,
    EvaluationRunRepository,
    InMemoryEvaluationRunRepository,
    InvalidSubjectError,
    UnknownBaselineError,
    UnknownModelVersionError,
    predictions_to_metrics,
    predictions_to_quality_vector,
)
from app.evaluation.subjects import (
    SubjectArtifactError,
    SubjectBenchmarkMismatch,
    bundle_size_bytes,
    evaluate_subject_rows,
    validate_subject,
)
from app.models import ModelRepository, get_model_repository
from app.projects import ProjectRepository
from app.projects import get_repository as get_project_repository
from app.specs import SpecRepository, get_spec_repository
from app.usage import UsageRepository, get_usage_repository


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Request schemas
# --------------------------------------------------------------------------


class SubjectInput(BaseModel):
    kind: str  # validated manually -> 409 (not 422) on unknown kinds
    ref: str | None = None
    quality_vector: QualityVector | None = None


class EvaluationRunCreate(BaseModel):
    spec_id: UUID | None = None
    project_id: UUID | None = None
    name: str | None = None
    subject: SubjectInput


class BenchmarkCreate(BaseModel):
    name: str
    description: str = ""
    input_spec: dict[str, Any] = {}
    expected_output: dict[str, Any] = {}
    metrics: list[str] | None = None
    cost_rules: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    label_column: str = "label"


class CompareRequest(BaseModel):
    spec_id: UUID | None = None
    subjects: list[SubjectInput] = []
    include_baselines: bool = True
    incumbent_intelligence_version_id: UUID | None = None


# --------------------------------------------------------------------------
# Dependency hooks
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


def get_evaluation_run_repository() -> EvaluationRunRepository:
    """Dependency hook: returns the process-wide run repository."""
    return _default_run_repository


def get_benchmark_repository() -> BenchmarkRepository:
    """Dependency hook: returns the seeded process-wide benchmark repository."""
    return _default_benchmark_repository


def get_evaluation_manager() -> EvaluationManager:
    """Dependency hook: returns the process-wide evaluation manager.

    Tests override this with a fresh manager per test.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = EvaluationManager(
            run_repository=get_evaluation_run_repository(),
            benchmark_registry=BenchmarkRegistry(get_benchmark_repository()),
            model_repository=get_model_repository(),
            artifact_root=get_settings().data_dir / "artifacts",
            on_finish=_usage_recorder(get_usage_repository()),
        )
    return _default_manager


_default_run_repository = InMemoryEvaluationRunRepository()
_default_benchmark_repository = InMemoryBenchmarkRepository()
_default_manager: EvaluationManager | None = None


def _usage_recorder(usage_repository: UsageRepository):  # type: ignore[no-untyped-def]
    """on_finish callback: record one EVALUATION UsageEvent per terminal run."""

    def _on_finish(run: EvaluationRun) -> None:
        usage_repository.record_event(
            UsageEvent(
                id=uuid4(),
                project_id=run.project_id,
                scope=UsageScope.EVALUATION,
                scope_id=run.id,
                kind=UsageKind.EVALUATION,
                quantity=float(run.metrics.get("predictions_evaluated", 0) or 0),
                unit="predictions",
                cost_usd=run.cost_usd,
                recorded_at=_utc_now(),
            )
        )

    return _on_finish


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _get_project_or_404(
    project_repository: ProjectRepository, project_id: UUID, user: ApiUser
) -> None:
    project = project_repository.get_project(project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _get_benchmark_or_404(
    benchmark_repository: BenchmarkRepository,
    project_repository: ProjectRepository,
    benchmark_id: UUID,
    user: ApiUser,
) -> Benchmark:
    """Fetch a benchmark; 404 when missing or owned by another org.

    Global benchmarks (project_id None) are visible to every org.
    """
    benchmark = benchmark_repository.get_benchmark(benchmark_id)
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found"
        )
    if benchmark.project_id is not None:
        project = project_repository.get_project(benchmark.project_id)
        if project is None or project.organization_id != user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found"
            )
    return benchmark


def _get_run_or_404(
    manager: EvaluationManager,
    project_repository: ProjectRepository,
    run_id: UUID,
    user: ApiUser,
) -> EvaluationRun:
    """Fetch a run; 404 when missing or owned by another org (via its project)."""
    run = manager.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found"
        )
    project = project_repository.get_project(run.project_id)
    if project is None or project.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found"
        )
    return run


def _to_subject(payload: SubjectInput) -> EvaluationSubject:
    try:
        kind = SubjectKind(payload.kind)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"invalid subject kind: {payload.kind!r}; "
            "expected 'baseline' | 'model_version' | 'reference'",
        ) from None
    return EvaluationSubject(
        kind=kind, ref=payload.ref, quality_vector=payload.quality_vector
    )


def _lightweight_spec(benchmark: Benchmark) -> IntelligenceSpec:
    """A spec built from the benchmark, for ranking when no spec_id is given."""
    return IntelligenceSpec(
        id=uuid4(),
        project_id=uuid4(),
        name=benchmark.name,
        problem_statement=benchmark.description or benchmark.name,
        intelligence_primitive=IntelligencePrimitive.CLASSIFICATION,
        status=IntelligenceSpecStatus.DRAFT,
    )


def _resolve_incumbent(
    incumbent_version_id: UUID | None,
    manager: EvaluationManager,
) -> tuple[ComparisonSubjectResult | None, str | None]:
    """Resolve the incumbent's quality vector via the registry (lazy import).

    Returns (result, note). The registry package is built in parallel, so
    the import is lazy and every failure mode degrades to an explanatory
    note instead of a 500.
    """
    if incumbent_version_id is None:
        return None, None
    try:
        from app.registry.intelligences import get_intelligence_repository
    except ImportError:
        return None, "incumbent unavailable: registry package not installed"
    try:
        repository = get_intelligence_repository()
        lookup = getattr(repository, "get_intelligence_version", None) or getattr(
            repository, "get_version", None
        )
        if lookup is None:
            return None, "incumbent unavailable: registry has no version lookup"
        version = lookup(incumbent_version_id)
        if version is None:
            return None, f"incumbent unavailable: unknown version {incumbent_version_id}"
        best_run_id = getattr(version, "best_evaluation_run_id", None)
        if best_run_id is None:
            return (
                None,
                f"incumbent unavailable: version {incumbent_version_id} "
                "has no best evaluation run",
            )
        run = manager.get(best_run_id)
        if run is None or run.quality_vector is None:
            return (
                None,
                "incumbent unavailable: its best evaluation run has no quality vector",
            )
        subject = EvaluationSubject(
            kind=SubjectKind.REFERENCE,
            ref=f"incumbent:{incumbent_version_id}",
            quality_vector=run.quality_vector,
        )
        return (
            ComparisonSubjectResult(
                subject=subject,
                quality_vector=run.quality_vector,
                metrics=run.metrics or {},
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001 — degrade to a note, never 500
        return None, f"incumbent unavailable: {exc}"


# --------------------------------------------------------------------------
# Benchmark endpoints
# --------------------------------------------------------------------------


@router.get("/projects/{project_id}/benchmarks", response_model=list[Benchmark])
def list_benchmarks(
    project_id: UUID,
    benchmark_repository: BenchmarkRepository = Depends(get_benchmark_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[Benchmark]:
    """Seeded global benchmarks plus the project's own."""
    _get_project_or_404(project_repository, project_id, user)
    return BenchmarkRegistry(benchmark_repository).list(project_id)


@router.post(
    "/projects/{project_id}/benchmarks",
    response_model=Benchmark,
    status_code=status.HTTP_201_CREATED,
)
def create_benchmark(
    project_id: UUID,
    payload: BenchmarkCreate,
    benchmark_repository: BenchmarkRepository = Depends(get_benchmark_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Benchmark:
    """Create a project-scoped custom benchmark with its rows."""
    _get_project_or_404(project_repository, project_id, user)
    return BenchmarkRegistry(benchmark_repository).create_custom(
        project_id,
        name=payload.name,
        description=payload.description,
        rows=payload.rows,
        label_column=payload.label_column,
        input_spec=payload.input_spec,
        expected_output=payload.expected_output,
        metrics=payload.metrics,
        cost_rules=payload.cost_rules,
    )


@router.get("/benchmarks/{benchmark_id}", response_model=Benchmark)
def get_benchmark(
    benchmark_id: UUID,
    benchmark_repository: BenchmarkRepository = Depends(get_benchmark_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> Benchmark:
    """Benchmark detail; 404 when missing or owned by another org."""
    return _get_benchmark_or_404(
        benchmark_repository, project_repository, benchmark_id, user
    )


# --------------------------------------------------------------------------
# Evaluation-run endpoints
# --------------------------------------------------------------------------


@router.post(
    "/benchmarks/{benchmark_id}/runs",
    response_model=EvaluationRun,
    status_code=status.HTTP_201_CREATED,
)
def submit_evaluation_run(
    benchmark_id: UUID,
    payload: EvaluationRunCreate,
    benchmark_repository: BenchmarkRepository = Depends(get_benchmark_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    spec_repository: SpecRepository = Depends(get_spec_repository),
    manager: EvaluationManager = Depends(get_evaluation_manager),
    user: ApiUser = Depends(get_current_user),
) -> EvaluationRun:
    """Submit an async evaluation run -> 201; 409 on subject faults."""
    benchmark = _get_benchmark_or_404(
        benchmark_repository, project_repository, benchmark_id, user
    )
    subject = _to_subject(payload.subject)

    spec = None
    if payload.spec_id is not None:
        spec = spec_repository.get_spec(payload.spec_id)
        if spec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found"
            )
    project_id = payload.project_id or (spec.project_id if spec else None)
    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_id is required (or pass spec_id to derive it)",
        )
    _get_project_or_404(project_repository, project_id, user)
    if spec is not None and spec.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found"
        )

    now = _utc_now()
    run = EvaluationRun(
        id=uuid4(),
        project_id=project_id,
        benchmark_id=benchmark.id,
        spec_id=spec.id if spec else None,
        name=payload.name or f"evaluation-{now}",
        subject=subject,
        created_at=now,
    )
    try:
        return manager.submit(run)
    except (UnknownBaselineError, UnknownModelVersionError, InvalidSubjectError,
            ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/projects/{project_id}/evaluation-runs", response_model=list[EvaluationRun])
def list_evaluation_runs(
    project_id: UUID,
    manager: EvaluationManager = Depends(get_evaluation_manager),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> list[EvaluationRun]:
    """List all evaluation runs of a project."""
    _get_project_or_404(project_repository, project_id, user)
    return manager.run_repository.list_runs(project_id)


@router.get("/evaluation-runs/{run_id}", response_model=EvaluationRun)
def get_evaluation_run(
    run_id: UUID,
    manager: EvaluationManager = Depends(get_evaluation_manager),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> EvaluationRun:
    """Run detail incl. quality_vector; 404 when missing or foreign."""
    return _get_run_or_404(manager, project_repository, run_id, user)


@router.post("/evaluation-runs/{run_id}/cancel", response_model=EvaluationRun)
def cancel_evaluation_run(
    run_id: UUID,
    manager: EvaluationManager = Depends(get_evaluation_manager),
    project_repository: ProjectRepository = Depends(get_project_repository),
    user: ApiUser = Depends(get_current_user),
) -> EvaluationRun:
    """Cancel a running evaluation; 409 when already terminal."""
    run = _get_run_or_404(manager, project_repository, run_id, user)
    if run.status in {
        EvaluationStatus.COMPLETED,
        EvaluationStatus.FAILED,
        EvaluationStatus.CANCELLED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run is already {run.status.value}",
        )
    cancelled = manager.cancel(run_id)
    assert cancelled is not None  # _get_run_or_404 proved it exists
    return cancelled


# --------------------------------------------------------------------------
# Comparison endpoint
# --------------------------------------------------------------------------


@router.post("/benchmarks/{benchmark_id}/compare", response_model=ComparisonReport)
def compare_subjects(
    benchmark_id: UUID,
    payload: CompareRequest,
    benchmark_repository: BenchmarkRepository = Depends(get_benchmark_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
    spec_repository: SpecRepository = Depends(get_spec_repository),
    model_repository: ModelRepository = Depends(get_model_repository),
    manager: EvaluationManager = Depends(get_evaluation_manager),
    user: ApiUser = Depends(get_current_user),
) -> ComparisonReport:
    """Synchronous candidate comparison -> 200 ComparisonReport.

    Auto-includes the three Phase-1 baselines unless
    ``include_baselines=false``. A subject whose features mismatch the
    benchmark is reported as unscored (with the honest error in its
    metrics) rather than failing the whole comparison.
    """
    benchmark = _get_benchmark_or_404(
        benchmark_repository, project_repository, benchmark_id, user
    )
    registry = BenchmarkRegistry(benchmark_repository)
    rows = registry.get_rows(benchmark)
    label_column = registry.get_label_column(benchmark)

    spec: IntelligenceSpec | None = None
    if payload.spec_id is not None:
        spec = spec_repository.get_spec(payload.spec_id)
        if spec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found"
            )
        _get_project_or_404(project_repository, spec.project_id, user)
        if benchmark.project_id is not None and spec.project_id != benchmark.project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found"
            )
    ranking_spec = spec or _lightweight_spec(benchmark)

    subject_inputs = list(payload.subjects)
    if payload.include_baselines:
        auto = [
            SubjectInput(kind="baseline", ref=name)
            for name in ("majority_class", "keyword_heuristic", "deterministic_rule")
        ]
        seen = {(s.kind, s.ref) for s in subject_inputs}
        subject_inputs = [s for s in auto if (s.kind, s.ref) not in seen] + subject_inputs

    bar_spec = spec or _lightweight_spec(benchmark)
    bar_report = run_baselines(bar_spec, uuid4(), rows, label_column=label_column)
    bar = bar_report.bar_to_beat

    artifact_root = manager.artifact_root
    results: list[ComparisonSubjectResult] = []
    for subject_input in subject_inputs:
        subject = _to_subject(subject_input)
        try:
            validate_subject(subject, model_repository)
        except (UnknownBaselineError, UnknownModelVersionError,
                InvalidSubjectError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
        if subject.kind == SubjectKind.REFERENCE:
            results.append(
                ComparisonSubjectResult(
                    subject=subject,
                    quality_vector=subject.quality_vector,
                    metrics={"reference": True},
                )
            )
            continue
        try:
            predictions = evaluate_subject_rows(
                subject=subject,
                benchmark=benchmark,
                rows=rows,
                label_column=label_column,
                model_repository=model_repository,
                artifact_root=artifact_root,
            )
        except (SubjectBenchmarkMismatch, SubjectArtifactError) as exc:
            results.append(
                ComparisonSubjectResult(
                    subject=subject,
                    quality_vector=None,
                    metrics={"error": f"{type(exc).__name__}: {exc}"},
                )
            )
            continue
        model_size = None
        if subject.kind == SubjectKind.MODEL_VERSION:
            version = model_repository.get_version(UUID(str(subject.ref)))
            if version is not None:
                model_size = bundle_size_bytes(version, artifact_root)
        results.append(
            ComparisonSubjectResult(
                subject=subject,
                quality_vector=predictions_to_quality_vector(
                    predictions, model_size_bytes=model_size
                ),
                metrics=predictions_to_metrics(predictions),
            )
        )

    incumbent, incumbent_note = _resolve_incumbent(
        payload.incumbent_intelligence_version_id, manager
    )
    report = build_comparison_report(benchmark, results, bar, incumbent, ranking_spec)
    if incumbent_note:
        report.notes.append(incumbent_note)
    return report
