"""Evaluation run execution (plan §56): async, cancellable, observable.

``EvaluationManager`` follows the same lifecycle as training runs:
PENDING -> RUNNING -> COMPLETED / FAILED / CANCELLED. Each run executes
in its own worker thread; the cancel flag is checked between rows so a
slow subject can be stopped mid-flight with partial metrics recorded.

Evaluation cost is local CPU by rule: ``cost_usd`` is 0.0 and the
benchmark's ``cost_rules`` say so explicitly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Protocol
from uuid import UUID

from shared.domain import (
    EvaluationRun,
    EvaluationStatus,
    QualityVector,
    SubjectKind,
)

from app.evaluation import metrics as metrics_module
from app.evaluation import quality as quality_module
from app.evaluation.benchmarks import BenchmarkRegistry
from app.evaluation.subjects import (
    InvalidSubjectError,
    RowPredictions,
    SubjectArtifactError,
    SubjectBenchmarkMismatch,
    UnknownBaselineError,
    UnknownModelVersionError,
    bundle_size_bytes,
    evaluate_subject_rows,
    validate_subject,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class EvaluationRunRepository(Protocol):
    """Storage contract for evaluation runs."""

    def list_runs(self, project_id: UUID) -> list[EvaluationRun]:
        """All evaluation runs belonging to the given project."""
        ...

    def get_run(self, run_id: UUID) -> EvaluationRun | None:
        """An evaluation run by id, or None when it does not exist."""
        ...

    def create_run(self, run: EvaluationRun) -> EvaluationRun:
        """Persist a fully-formed evaluation run."""
        ...

    def update_run(self, run: EvaluationRun) -> EvaluationRun:
        """Persist mutations of a run (status, metrics, ...)."""
        ...


class InMemoryEvaluationRunRepository:
    """Dict-backed repository. Empty at construction."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[UUID, EvaluationRun] = {}

    def list_runs(self, project_id: UUID) -> list[EvaluationRun]:
        with self._lock:
            return [r for r in self._runs.values() if r.project_id == project_id]

    def get_run(self, run_id: UUID) -> EvaluationRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def create_run(self, run: EvaluationRun) -> EvaluationRun:
        with self._lock:
            self._runs[run.id] = run
            return run

    def update_run(self, run: EvaluationRun) -> EvaluationRun:
        with self._lock:
            self._runs[run.id] = run
            return run


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------


class EvaluationManager:
    """Thread-based evaluation runner.

    ``submit`` validates the subject (ValueError on subject faults — the
    router maps these to 409), persists the run as RUNNING, and evaluates
    it in a worker thread. ``cancel`` sets a flag the worker checks
    between rows; the run lands CANCELLED with whatever partial metrics
    were recorded. ``on_finish`` fires once per terminal run (the router
    uses it to record a UsageEvent).
    """

    def __init__(
        self,
        *,
        run_repository: EvaluationRunRepository,
        benchmark_registry: BenchmarkRegistry,
        model_repository: Any,
        artifact_root: Path | str | None = None,
        row_delay_s: float = 0.0,
        on_finish: Any = None,
    ) -> None:
        self._runs = run_repository
        self._registry = benchmark_registry
        self._models = model_repository
        self._artifact_root = Path(artifact_root) if artifact_root else Path("artifacts")
        self._row_delay_s = row_delay_s
        self._on_finish = on_finish
        self._lock = Lock()
        self._cancel_flags: dict[UUID, bool] = {}
        self._threads: dict[UUID, Thread] = {}

    # -- public API ------------------------------------------------------

    @property
    def run_repository(self) -> EvaluationRunRepository:
        return self._runs

    @property
    def benchmark_registry(self) -> BenchmarkRegistry:
        return self._registry

    @property
    def model_repository(self) -> Any:
        return self._models

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    def submit(self, run: EvaluationRun) -> EvaluationRun:
        """Validate the subject, persist the run, evaluate in a thread."""
        benchmark = self._registry.get(run.benchmark_id)
        if benchmark is None:
            raise ValueError(f"unknown benchmark: {run.benchmark_id}")
        validate_subject(run.subject, self._models)  # 409-style faults
        run.status = EvaluationStatus.PENDING
        stored = self._runs.create_run(run)
        with self._lock:
            self._cancel_flags[stored.id] = False
            thread = Thread(
                target=self._execute, args=(stored.id,), daemon=True,
                name=f"evaluation-{stored.id}",
            )
            self._threads[stored.id] = thread
            thread.start()
        return stored

    def get(self, run_id: UUID) -> EvaluationRun | None:
        return self._runs.get_run(run_id)

    def cancel(self, run_id: UUID) -> EvaluationRun | None:
        """Flag a running evaluation for cancellation. None when unknown."""
        run = self._runs.get_run(run_id)
        if run is None:
            return None
        if run.status in {
            EvaluationStatus.COMPLETED,
            EvaluationStatus.FAILED,
            EvaluationStatus.CANCELLED,
        }:
            return run  # already terminal; the router answers 409
        with self._lock:
            self._cancel_flags[run_id] = True
        return self._runs.get_run(run_id)

    def wait(self, run_id: UUID, timeout_s: float = 60.0) -> EvaluationRun:
        """Block until the run is terminal (test/sync helper)."""
        thread = self._threads.get(run_id)
        if thread is not None:
            thread.join(timeout=timeout_s)
        run = self._runs.get_run(run_id)
        if run is None:
            raise ValueError(f"unknown evaluation run: {run_id}")
        if run.status not in {
            EvaluationStatus.COMPLETED,
            EvaluationStatus.FAILED,
            EvaluationStatus.CANCELLED,
        }:
            raise TimeoutError(f"evaluation run {run_id} did not finish in time")
        return run

    # -- worker ----------------------------------------------------------

    def _should_stop(self, run_id: UUID) -> bool:
        with self._lock:
            return self._cancel_flags.get(run_id, False)

    def _execute(self, run_id: UUID) -> None:
        run = self._runs.get_run(run_id)
        if run is None:
            return
        run.status = EvaluationStatus.RUNNING
        self._runs.update_run(run)
        try:
            benchmark = self._registry.get(run.benchmark_id)
            if benchmark is None:
                raise ValueError(f"unknown benchmark: {run.benchmark_id}")
            rows = self._registry.get_rows(benchmark)
            label_column = self._registry.get_label_column(benchmark)

            if run.subject.kind == SubjectKind.REFERENCE:
                run.quality_vector = run.subject.quality_vector
                run.metrics = {"reference": True}
                run.cost_usd = 0.0
                self._finish(run, EvaluationStatus.COMPLETED)
                return

            predictions = evaluate_subject_rows(
                subject=run.subject,
                benchmark=benchmark,
                rows=rows,
                label_column=label_column,
                model_repository=self._models,
                artifact_root=self._artifact_root,
                should_stop=lambda: self._should_stop(run_id),
                row_delay_s=self._row_delay_s,
            )
            run.metrics = self._metrics_for(run, predictions)
            run.quality_vector = self._vector_for(run, predictions)
            run.cost_usd = 0.0  # local CPU by rule; see benchmark cost_rules
            status = (
                EvaluationStatus.CANCELLED
                if predictions.cancelled or self._should_stop(run_id)
                else EvaluationStatus.COMPLETED
            )
            self._finish(run, status)
        except (SubjectBenchmarkMismatch, SubjectArtifactError) as exc:
            # Negative evidence: the subject genuinely doesn't fit the
            # benchmark. The run FAILS with the honest reason attached.
            run.error = f"{type(exc).__name__}: {exc}"
            run.metrics = {"predictions_evaluated": 0}
            self._finish(run, EvaluationStatus.FAILED)
        except Exception as exc:  # noqa: BLE001 — a sick worker must report
            run.error = f"{type(exc).__name__}: {exc}"
            self._finish(run, EvaluationStatus.FAILED)

    def _finish(self, run: EvaluationRun, status: EvaluationStatus) -> None:
        run.status = status
        run.completed_at = _utc_now()
        self._runs.update_run(run)
        if self._on_finish is not None:
            try:
                self._on_finish(run)
            except Exception:  # noqa: BLE001 — usage recording must not fail the run
                pass

    # -- metrics ---------------------------------------------------------

    def _metrics_for(self, run: EvaluationRun, pred: RowPredictions) -> dict[str, Any]:
        return predictions_to_metrics(pred)

    def _vector_for(self, run: EvaluationRun, pred: RowPredictions) -> QualityVector:
        model_size = None
        if run.subject.kind == SubjectKind.MODEL_VERSION:
            version = self._models.get_version(UUID(str(run.subject.ref)))
            if version is not None:
                model_size = bundle_size_bytes(version, self._artifact_root)
        return predictions_to_quality_vector(pred, model_size_bytes=model_size)


def predictions_to_metrics(pred: RowPredictions) -> dict[str, Any]:
    """Run/compare-level metric dict from per-row predictions."""
    y_true_bin = [1 if t == pred.positive_label else 0 for t in pred.y_true]
    return {
        "accuracy": metrics_module.accuracy(pred.y_true, pred.y_pred),
        "per_class_accuracy": metrics_module.per_class_accuracy(
            pred.y_true, pred.y_pred
        ),
        "ece": metrics_module.expected_calibration_error(y_true_bin, pred.y_proba),
        "brier": metrics_module.brier_score(y_true_bin, pred.y_proba),
        "latency_ms_p50": metrics_module.latency_p50_ms(pred.latencies_ms),
        "latency_ms_p99": metrics_module.latency_p99_ms(pred.latencies_ms),
        "cost_usd_per_1k": 0.0,  # local CPU by rule; see benchmark cost_rules
        "predictions_evaluated": pred.rows_evaluated,
        "total_rows": pred.total_rows,
        "positive_label": None
        if pred.positive_label is None
        else str(pred.positive_label),
        "cancelled": pred.cancelled,
    }


def predictions_to_quality_vector(
    pred: RowPredictions, *, model_size_bytes: int | None = None
) -> QualityVector:
    """Assemble the plan §30 QualityVector from per-row predictions."""
    m = predictions_to_metrics(pred)
    reliability = pred.rows_evaluated / pred.total_rows if pred.total_rows else None
    return quality_module.assemble_quality_vector(
        {
            "accuracy": m["accuracy"],
            "ece": m["ece"],
            "latency_ms_p50": m["latency_ms_p50"],
            "latency_ms_p99": m["latency_ms_p99"],
            "cost_usd_per_1k": m["cost_usd_per_1k"],
            "model_size_bytes": model_size_bytes,
            "reliability": reliability,
        }
    )


__all__ = [
    "EvaluationManager",
    "EvaluationRunRepository",
    "InMemoryEvaluationRunRepository",
    "InvalidSubjectError",
    "UnknownBaselineError",
    "UnknownModelVersionError",
    "predictions_to_metrics",
    "predictions_to_quality_vector",
]
