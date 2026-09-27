"""Phase 3 — evaluation subsystem tests (plan §56, §57, §30, §15).

TDD: written RED before `app/evaluation/` existed. Covers:
- metrics.py: hand-computed accuracy / ECE / percentiles / brier /
  per-class accuracy / cost-per-1k
- quality.py: QualityVector assembly, beats_bar, spec-priority ranking
  (no global weights anywhere)
- benchmarks.py: seeded global benchmarks + project-scoped custom CRUD
- subjects.py + runner.py: baseline / model_version / reference subjects,
  cancel semantics, feature-mismatch failure (negative evidence)
- compare.py: winner per spec priorities, plain-language notes
- router.py: the evaluation-runs HTTP contract from shared/README.md
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from shared.domain import (
    ApiUser,
    Benchmark,
    ComparisonSubjectResult,
    EvaluationRun,
    EvaluationStatus,
    EvaluationSubject,
    IntelligencePrimitive,
    IntelligenceSpec,
    IntelligenceSpecStatus,
    Model,
    ModelVersion,
    QualityBar,
    QualityVector,
    SubjectKind,
    UserRole,
)
from shared.services.fixtures import termination_dataset_rows

from app.evaluation import benchmarks as benchmarks_module
from app.evaluation import compare as compare_module
from app.evaluation import metrics as metrics_module
from app.evaluation import quality as quality_module
from app.evaluation import runner as runner_module
from app.evaluation import subjects as subjects_module
from app.evaluation.benchmarks import BenchmarkRegistry, InMemoryBenchmarkRepository
from app.evaluation.runner import EvaluationManager
from app.main import create_app
from app.projects import InMemoryProjectRepository
from app.projects import get_repository as get_project_repository


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


STUB_ORG_ID = UUID("00000000-0000-0000-0000-000000000002")


def _stub_user() -> ApiUser:
    return ApiUser(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        organization_id=STUB_ORG_ID,
        email="dev@rustenwer.local",
        display_name="Phase-3 test user",
        role=UserRole.OWNER,
        created_at=_utc_now(),
    )


def _make_project(project_repository: InMemoryProjectRepository) -> UUID:
    from shared.domain import Project, ProjectStatus

    project_id = uuid4()
    now = _utc_now()
    project_repository.create_project(
        Project(
            id=project_id,
            organization_id=STUB_ORG_ID,
            name="eval-test-project",
            description=None,
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    return project_id


def _make_mlp_bundle(
    path: Path, n_features: int, n_classes: int = 2, hidden: tuple[int, ...] = (8,)
) -> Path:
    """A minimal exported bundle (model.pt + config.json) in export format."""
    import torch

    torch.manual_seed(0)
    layers: list = []
    prev = n_features
    for h in hidden:
        layers += [torch.nn.Linear(prev, h), torch.nn.ReLU()]
        prev = h
    layers.append(torch.nn.Linear(prev, n_classes))
    model = torch.nn.Sequential(*layers)
    bundle = path / f"bundle-{n_features}f"
    bundle.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict(), "epoch": 0, "step": 0}, bundle / "model.pt")
    (bundle / "config.json").write_text(
        json.dumps(
            {
                "training_method": "classifier",
                "n_features": n_features,
                "n_classes": n_classes,
                "hyperparameters": {"hidden": list(hidden)},
                "seed": 0,
            }
        ),
        encoding="utf-8",
    )
    return bundle


def _register_model_version(
    model_repository, project_id: UUID, bundle: Path
) -> ModelVersion:
    model_id = uuid4()
    model_repository.create_model(
        Model(
            id=model_id,
            project_id=project_id,
            name="ring-smoke",
            description=None,
            created_at=_utc_now(),
        )
    )
    version = ModelVersion(
        id=uuid4(),
        model_id=model_id,
        version=1,
        artifact_uri=str(bundle),
        created_at=_utc_now(),
    )
    return model_repository.create_version(version)


def _manager(
    tmp_path: Path, row_delay_s: float = 0.0
) -> tuple[EvaluationManager, InMemoryBenchmarkRepository]:
    from app.models import InMemoryModelRepository

    run_repository = runner_module.InMemoryEvaluationRunRepository()
    benchmark_repository = InMemoryBenchmarkRepository()
    registry = BenchmarkRegistry(benchmark_repository)
    manager = EvaluationManager(
        run_repository=run_repository,
        benchmark_registry=registry,
        model_repository=InMemoryModelRepository(),
        artifact_root=tmp_path / "artifacts",
        row_delay_s=row_delay_s,
    )
    return manager, benchmark_repository


def _submit_baseline_run(
    manager: EvaluationManager,
    benchmark_id: UUID,
    project_id: UUID,
    baseline_name: str = "deterministic_rule",
) -> EvaluationRun:
    run = EvaluationRun(
        id=uuid4(),
        project_id=project_id,
        benchmark_id=benchmark_id,
        name="test-run",
        subject=EvaluationSubject(kind=SubjectKind.BASELINE, ref=baseline_name),
        created_at=_utc_now(),
    )
    return manager.submit(run)


# ---------------------------------------------------------------------------
# metrics.py
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_accuracy(self) -> None:
        assert metrics_module.accuracy([1, 0, 1, 1], [1, 0, 0, 1]) == pytest.approx(0.75)
        assert metrics_module.accuracy([], []) is None

    def test_expected_calibration_error_hand_computed(self) -> None:
        # bin1 (0.5-1.0]: (0.9,1),(0.8,0) -> acc 0.5, conf 0.85, |d|=0.35, w=0.5
        # bin2 [0-0.5]:   (0.2,0),(0.1,1) -> acc 0.5, conf 0.15, |d|=0.35, w=0.5
        ece = metrics_module.expected_calibration_error(
            [1, 0, 0, 1], [0.9, 0.8, 0.2, 0.1], n_bins=2
        )
        assert ece == pytest.approx(0.35)

    def test_expected_calibration_error_perfect(self) -> None:
        ece = metrics_module.expected_calibration_error([1, 0, 1, 0], [1.0, 0.0, 1.0, 0.0])
        assert ece == pytest.approx(0.0)

    def test_expected_calibration_error_empty(self) -> None:
        assert metrics_module.expected_calibration_error([], []) is None

    def test_latency_percentiles(self) -> None:
        assert metrics_module.latency_p50_ms([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)
        assert metrics_module.latency_p99_ms([1.0, 2.0, 3.0, 4.0]) == pytest.approx(4.0)
        assert metrics_module.latency_p99_ms([5.0]) == pytest.approx(5.0)
        assert metrics_module.latency_p50_ms([]) is None
        assert metrics_module.latency_p99_ms([]) is None

    def test_cost_per_1k(self) -> None:
        assert metrics_module.cost_per_1k_usd(0.05, 100) == pytest.approx(0.5)
        assert metrics_module.cost_per_1k_usd(0.0, 0) == 0.0

    def test_brier_score(self) -> None:
        assert metrics_module.brier_score([1, 0], [1.0, 0.0]) == pytest.approx(0.0)
        assert metrics_module.brier_score([1, 0], [0.5, 0.5]) == pytest.approx(0.25)
        assert metrics_module.brier_score([], []) is None

    def test_per_class_accuracy(self) -> None:
        result = metrics_module.per_class_accuracy(
            ["a", "a", "b"], ["a", "b", "b"]
        )
        assert result == {"a": pytest.approx(0.5), "b": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# quality.py
# ---------------------------------------------------------------------------


class TestQuality:
    def test_assemble_quality_vector(self) -> None:
        vector = quality_module.assemble_quality_vector(
            {
                "accuracy": 0.9,
                "ece": 0.1,
                "robustness": 0.8,
                "latency_ms_p50": 5.0,
                "latency_ms_p99": 9.0,
                "cost_usd_per_1k": 0.02,
                "training_cost_usd": 1.5,
                "model_size_bytes": 1024,
                "reliability": 0.99,
            }
        )
        assert isinstance(vector, QualityVector)
        assert vector.task_quality == pytest.approx(0.9)
        assert vector.calibration == pytest.approx(0.9)  # 1 - ECE
        assert vector.robustness == pytest.approx(0.8)
        assert vector.latency_ms_p50 == pytest.approx(5.0)
        assert vector.latency_ms_p99 == pytest.approx(9.0)
        assert vector.inference_cost_usd_per_1k == pytest.approx(0.02)
        assert vector.training_cost_usd == pytest.approx(1.5)
        assert vector.model_size_bytes == 1024
        assert vector.reliability == pytest.approx(0.99)

    def test_assemble_missing_keys_become_none(self) -> None:
        vector = quality_module.assemble_quality_vector({})
        assert vector.task_quality is None
        assert vector.calibration is None

    def test_beats_bar_true(self) -> None:
        vector = QualityVector(task_quality=0.9, latency_ms_p50=5.0,
                              inference_cost_usd_per_1k=0.02)
        bar = QualityBar(accuracy=0.8, latency_ms_p50=10.0, cost_usd_per_1k=0.05)
        assert quality_module.beats_bar(vector, bar) is True

    def test_beats_bar_false_cases(self) -> None:
        bar = QualityBar(accuracy=0.8, latency_ms_p50=10.0, cost_usd_per_1k=0.05)
        assert quality_module.beats_bar(
            QualityVector(task_quality=0.7, latency_ms_p50=5.0,
                          inference_cost_usd_per_1k=0.02), bar
        ) is False  # accuracy below bar
        assert quality_module.beats_bar(
            QualityVector(task_quality=0.9, latency_ms_p50=50.0,
                          inference_cost_usd_per_1k=0.02), bar
        ) is False  # latency above bar
        assert quality_module.beats_bar(
            QualityVector(task_quality=0.9, latency_ms_p50=5.0,
                          inference_cost_usd_per_1k=0.5), bar
        ) is False  # cost above bar
        assert quality_module.beats_bar(
            QualityVector(latency_ms_p50=5.0, inference_cost_usd_per_1k=0.02), bar
        ) is False  # unmeasured quality cannot beat the bar

    def _spec_with_priority(self, priority: list[str] | None) -> IntelligenceSpec:
        return IntelligenceSpec(
            id=uuid4(),
            project_id=uuid4(),
            name="spec",
            problem_statement="rank me",
            intelligence_primitive=IntelligencePrimitive.CLASSIFICATION,
            quality_requirements={"priority": priority} if priority is not None else None,
            status=IntelligenceSpecStatus.DRAFT,
        )

    def test_rank_by_spec_priority_latency_first(self) -> None:
        spec = self._spec_with_priority(["latency_ms_p50", "task_quality"])
        ordered = quality_module.rank_by_spec_priority(
            [
                ("slow-accurate", QualityVector(task_quality=0.95, latency_ms_p50=50.0)),
                ("fast-rough", QualityVector(task_quality=0.70, latency_ms_p50=2.0)),
            ],
            spec,
        )
        assert ordered == ["fast-rough", "slow-accurate"]

    def test_rank_by_spec_priority_accuracy_first(self) -> None:
        spec = self._spec_with_priority(["task_quality", "latency_ms_p50"])
        ordered = quality_module.rank_by_spec_priority(
            [
                ("slow-accurate", QualityVector(task_quality=0.95, latency_ms_p50=50.0)),
                ("fast-rough", QualityVector(task_quality=0.70, latency_ms_p50=2.0)),
            ],
            spec,
        )
        assert ordered == ["slow-accurate", "fast-rough"]

    def test_rank_defaults_to_task_quality(self) -> None:
        spec = self._spec_with_priority(None)
        ordered = quality_module.rank_by_spec_priority(
            [
                ("b", QualityVector(task_quality=0.6)),
                ("a", QualityVector(task_quality=0.9)),
            ],
            spec,
        )
        assert ordered == ["a", "b"]

    def test_rank_unknown_field_raises(self) -> None:
        spec = self._spec_with_priority(["not_a_field"])
        with pytest.raises(ValueError, match="not_a_field"):
            quality_module.rank_by_spec_priority([("a", QualityVector())], spec)

    def test_rank_none_sorts_last(self) -> None:
        spec = self._spec_with_priority(["task_quality"])
        ordered = quality_module.rank_by_spec_priority(
            [("unmeasured", QualityVector()), ("measured", QualityVector(task_quality=0.1))],
            spec,
        )
        assert ordered == ["measured", "unmeasured"]


# ---------------------------------------------------------------------------
# benchmarks.py
# ---------------------------------------------------------------------------


class TestBenchmarks:
    def test_seeded_global_benchmarks(self) -> None:
        repo = InMemoryBenchmarkRepository()
        registry = BenchmarkRegistry(repo)
        project_id = uuid4()
        listed = registry.list(project_id)
        names = {b.name for b in listed}
        assert {"termination-benchmark", "ring-benchmark"} <= names
        for b in listed:
            if b.name in {"termination-benchmark", "ring-benchmark"}:
                assert b.project_id is None

    def test_termination_benchmark_rows_match_fixture(self) -> None:
        registry = BenchmarkRegistry(InMemoryBenchmarkRepository())
        benchmark = next(
            b for b in registry.list(uuid4()) if b.name == "termination-benchmark"
        )
        rows = registry.get_rows(benchmark)
        assert rows == termination_dataset_rows()
        assert benchmark.evaluation_function == "classification_on_rows"
        assert benchmark.metrics == ["accuracy", "latency_ms_p50", "cost_usd_per_1k"]
        assert benchmark.input_spec and benchmark.expected_output

    def test_ring_benchmark_is_deterministic(self) -> None:
        registry = BenchmarkRegistry(InMemoryBenchmarkRepository())
        benchmark = next(
            b for b in registry.list(uuid4()) if b.name == "ring-benchmark"
        )
        rows_a = registry.get_rows(benchmark)
        rows_b = registry.get_rows(benchmark)
        assert rows_a == rows_b
        assert len(rows_a) == 200
        for row in rows_a:
            assert set(row.keys()) == {"x", "label"}
            assert len(row["x"]) == 2
            assert row["label"] in (0, 1)
        # Labels follow the ring rule: radius > sqrt(2 ln 2) -> 1.
        import math

        threshold = math.sqrt(2 * math.log(2))
        for row in rows_a:
            radius = math.hypot(*row["x"])
            assert row["label"] == (1 if radius > threshold else 0)
        # Roughly balanced classes (Rayleigh median splits ~50/50).
        positives = sum(r["label"] for r in rows_a)
        assert 70 <= positives <= 130

    def test_ring_benchmark_held_out_from_training_seed(self) -> None:
        # The seeded test set must not reuse the training seed (0 is the
        # smoke-task default); document the fixed test seed.
        assert benchmarks_module.RING_TEST_SEED != 0

    def test_custom_benchmark_crud_project_scoped(self) -> None:
        repo = InMemoryBenchmarkRepository()
        registry = BenchmarkRegistry(repo)
        project_a, project_b = uuid4(), uuid4()
        created = registry.create_custom(
            project_a,
            name="my-bench",
            rows=[{"x": [0.1], "label": 0}],
            label_column="label",
        )
        assert isinstance(created, Benchmark)
        assert created.project_id == project_a
        assert {b.name for b in registry.list(project_a)} >= {
            "termination-benchmark",
            "ring-benchmark",
            "my-bench",
        }
        assert "my-bench" not in {b.name for b in registry.list(project_b)}
        assert registry.get_rows(created) == [{"x": [0.1], "label": 0}]

    def test_cost_rules_record_zero_local_cost(self) -> None:
        registry = BenchmarkRegistry(InMemoryBenchmarkRepository())
        for b in registry.list(uuid4()):
            if b.name in {"termination-benchmark", "ring-benchmark"}:
                assert b.cost_rules.get("cost_usd_per_1k") == 0.0


# ---------------------------------------------------------------------------
# runner.py — EvaluationManager
# ---------------------------------------------------------------------------


class TestEvaluationManager:
    def test_baseline_subject_completes(self, tmp_path: Path) -> None:
        manager, _ = _manager(tmp_path)
        project_id = uuid4()
        registry = manager.benchmark_registry
        benchmark = next(
            b for b in registry.list(project_id) if b.name == "termination-benchmark"
        )
        run = _submit_baseline_run(manager, benchmark.id, project_id)
        assert run.status in {EvaluationStatus.PENDING, EvaluationStatus.RUNNING}
        finished = manager.wait(run.id, timeout_s=30.0)
        assert finished.status == EvaluationStatus.COMPLETED
        assert finished.completed_at is not None
        assert finished.error is None
        assert finished.quality_vector is not None
        assert finished.quality_vector.task_quality == pytest.approx(11 / 12)
        assert finished.cost_usd == 0.0
        assert finished.metrics["predictions_evaluated"] == 12

    def test_unknown_baseline_name_rejected_at_submit(self, tmp_path: Path) -> None:
        manager, _ = _manager(tmp_path)
        project_id = uuid4()
        benchmark = next(
            b
            for b in manager.benchmark_registry.list(project_id)
            if b.name == "termination-benchmark"
        )
        run = EvaluationRun(
            id=uuid4(),
            project_id=project_id,
            benchmark_id=benchmark.id,
            name="bad",
            subject=EvaluationSubject(kind=SubjectKind.BASELINE, ref="nope"),
            created_at=_utc_now(),
        )
        with pytest.raises(subjects_module.UnknownBaselineError):
            manager.submit(run)

    def test_unknown_model_version_ref_rejected_at_submit(self, tmp_path: Path) -> None:
        manager, _ = _manager(tmp_path)
        project_id = uuid4()
        benchmark = next(
            b
            for b in manager.benchmark_registry.list(project_id)
            if b.name == "termination-benchmark"
        )
        run = EvaluationRun(
            id=uuid4(),
            project_id=project_id,
            benchmark_id=benchmark.id,
            name="bad",
            subject=EvaluationSubject(kind=SubjectKind.MODEL_VERSION, ref=str(uuid4())),
            created_at=_utc_now(),
        )
        with pytest.raises(subjects_module.UnknownModelVersionError):
            manager.submit(run)

    def test_reference_subject_completes_with_given_vector(self, tmp_path: Path) -> None:
        manager, _ = _manager(tmp_path)
        project_id = uuid4()
        benchmark = next(
            b
            for b in manager.benchmark_registry.list(project_id)
            if b.name == "termination-benchmark"
        )
        vector = QualityVector(task_quality=0.99, latency_ms_p50=1.0)
        run = manager.submit(
            EvaluationRun(
                id=uuid4(),
                project_id=project_id,
                benchmark_id=benchmark.id,
                name="ref",
                subject=EvaluationSubject(
                    kind=SubjectKind.REFERENCE, ref="incumbent", quality_vector=vector
                ),
                created_at=_utc_now(),
            )
        )
        finished = manager.wait(run.id, timeout_s=30.0)
        assert finished.status == EvaluationStatus.COMPLETED
        assert finished.quality_vector == vector

    def test_cancel_slow_subject_records_partial(self, tmp_path: Path) -> None:
        manager, _ = _manager(tmp_path, row_delay_s=0.25)
        project_id = uuid4()
        benchmark = next(
            b
            for b in manager.benchmark_registry.list(project_id)
            if b.name == "termination-benchmark"
        )
        run = _submit_baseline_run(manager, benchmark.id, project_id)
        # Wait until the worker is actually running, then cancel mid-flight.
        deadline = time.time() + 5.0
        while manager.get(run.id).status != EvaluationStatus.RUNNING:
            assert time.time() < deadline, "run never reached RUNNING"
            time.sleep(0.02)
        time.sleep(0.6)  # ~2 rows at 0.25s/row; 12 rows would take ~3s
        cancelled = manager.cancel(run.id)
        assert cancelled is not None
        finished = manager.wait(run.id, timeout_s=30.0)
        assert finished.status == EvaluationStatus.CANCELLED
        assert finished.completed_at is not None
        evaluated = finished.metrics.get("predictions_evaluated", 0)
        assert 0 < evaluated < 12  # partial, honest

    def test_cancel_unknown_run_returns_none(self, tmp_path: Path) -> None:
        manager, _ = _manager(tmp_path)
        assert manager.cancel(uuid4()) is None

    def test_model_version_subject_completes(self, tmp_path: Path) -> None:
        manager, benchmark_repo = _manager(tmp_path)
        model_repository = manager.model_repository
        project_id = uuid4()
        bundle = _make_mlp_bundle(tmp_path, n_features=2)
        version = _register_model_version(model_repository, project_id, bundle)
        benchmark = next(
            b for b in manager.benchmark_registry.list(project_id)
            if b.name == "ring-benchmark"
        )
        run = manager.submit(
            EvaluationRun(
                id=uuid4(),
                project_id=project_id,
                benchmark_id=benchmark.id,
                name="model-run",
                subject=EvaluationSubject(
                    kind=SubjectKind.MODEL_VERSION, ref=str(version.id)
                ),
                created_at=_utc_now(),
            )
        )
        finished = manager.wait(run.id, timeout_s=120.0)
        assert finished.status == EvaluationStatus.COMPLETED, finished.error
        assert finished.quality_vector is not None
        assert finished.quality_vector.task_quality is not None
        assert 0.0 <= finished.quality_vector.task_quality <= 1.0
        assert finished.metrics["predictions_evaluated"] == 200
        assert finished.quality_vector.latency_ms_p50 is not None
        assert finished.quality_vector.latency_ms_p99 is not None

    def test_feature_mismatch_fails_honestly(self, tmp_path: Path) -> None:
        # A 20-feature ring-trained model evaluated on 2-float ring rows, or on
        # text rows: the run FAILS with a clear error (negative evidence).
        manager, _ = _manager(tmp_path)
        project_id = uuid4()
        bundle = _make_mlp_bundle(tmp_path, n_features=20)
        version = _register_model_version(
            manager.model_repository, project_id, bundle
        )
        benchmark = next(
            b
            for b in manager.benchmark_registry.list(project_id)
            if b.name == "termination-benchmark"  # text rows vs numeric model
        )
        run = manager.submit(
            EvaluationRun(
                id=uuid4(),
                project_id=project_id,
                benchmark_id=benchmark.id,
                name="mismatch",
                subject=EvaluationSubject(
                    kind=SubjectKind.MODEL_VERSION, ref=str(version.id)
                ),
                created_at=_utc_now(),
            )
        )
        finished = manager.wait(run.id, timeout_s=120.0)
        assert finished.status == EvaluationStatus.FAILED
        assert finished.error is not None
        assert "mismatch" in finished.error.lower()

    def test_on_finish_callback_fires(self, tmp_path: Path) -> None:
        from app.models import InMemoryModelRepository

        seen: list[EvaluationRun] = []
        manager = EvaluationManager(
            run_repository=runner_module.InMemoryEvaluationRunRepository(),
            benchmark_registry=BenchmarkRegistry(InMemoryBenchmarkRepository()),
            model_repository=InMemoryModelRepository(),
            artifact_root=tmp_path / "artifacts",
            on_finish=seen.append,
        )
        project_id = uuid4()
        benchmark = next(
            b
            for b in manager.benchmark_registry.list(project_id)
            if b.name == "termination-benchmark"
        )
        run = _submit_baseline_run(manager, benchmark.id, project_id)
        manager.wait(run.id, timeout_s=30.0)
        assert [r.id for r in seen] == [run.id]
        assert seen[0].status == EvaluationStatus.COMPLETED

    def test_subject_predictions_match_run_baselines(self, tmp_path: Path) -> None:
        # The per-row baseline mirror in subjects.py must agree with the
        # aggregate accuracy reported by run_baselines (pins the mirror).
        from shared.services.baselines import run_baselines

        project_id = uuid4()
        spec = IntelligenceSpec(
            id=uuid4(),
            project_id=project_id,
            name="termination",
            problem_statement="decide when to stop searching",
            intelligence_primitive=IntelligencePrimitive.CLASSIFICATION,
            status=IntelligenceSpecStatus.DRAFT,
        )
        rows = termination_dataset_rows()
        report = run_baselines(spec, uuid4(), rows, label_column="label")
        for baseline in report.baselines:
            result = subjects_module.evaluate_baseline_rows(
                rows, "label", baseline.name
            )
            assert metrics_module.accuracy(
                result.y_true, result.y_pred
            ) == pytest.approx(baseline.accuracy)


# ---------------------------------------------------------------------------
# compare.py
# ---------------------------------------------------------------------------


def _comparison_subject(
    label: str, task_quality: float | None, latency_ms_p50: float | None
) -> ComparisonSubjectResult:
    return ComparisonSubjectResult(
        subject=EvaluationSubject(kind=SubjectKind.BASELINE, ref=label),
        quality_vector=QualityVector(
            task_quality=task_quality, latency_ms_p50=latency_ms_p50,
            inference_cost_usd_per_1k=0.0,
        ),
        metrics={"predictions_evaluated": 12},
    )


class TestCompare:
    def _spec(self, priority: list[str]) -> IntelligenceSpec:
        return IntelligenceSpec(
            id=uuid4(),
            project_id=uuid4(),
            name="spec",
            problem_statement="p",
            intelligence_primitive=IntelligencePrimitive.CLASSIFICATION,
            quality_requirements={"priority": priority},
            status=IntelligenceSpecStatus.DRAFT,
        )

    def test_winner_follows_spec_priorities(self) -> None:
        benchmark = Benchmark(
            id=uuid4(), name="b", created_at=_utc_now(),
        )
        bar = QualityBar(accuracy=0.5, latency_ms_p50=100.0, cost_usd_per_1k=1.0)
        subjects = [
            _comparison_subject("slow-accurate", 0.95, 50.0),
            _comparison_subject("fast-rough", 0.70, 2.0),
        ]
        report = compare_module.build_comparison_report(
            benchmark, subjects, bar, None, self._spec(["latency_ms_p50"])
        )
        assert report.winner == "baseline:fast-rough"
        report2 = compare_module.build_comparison_report(
            benchmark, subjects, bar, None, self._spec(["task_quality"])
        )
        assert report2.winner == "baseline:slow-accurate"

    def test_beats_bar_and_incumbent_flags(self) -> None:
        benchmark = Benchmark(id=uuid4(), name="b", created_at=_utc_now())
        bar = QualityBar(accuracy=0.8, latency_ms_p50=10.0, cost_usd_per_1k=0.05)
        incumbent = _comparison_subject("incumbent", 0.85, 5.0)
        subjects = [
            _comparison_subject("champion", 0.95, 4.0),
            _comparison_subject("weakling", 0.60, 4.0),
        ]
        report = compare_module.build_comparison_report(
            benchmark, subjects, bar, incumbent, self._spec(["task_quality"])
        )
        by_label = {r.subject.ref: r for r in report.results}
        assert by_label["champion"].beats_bar is True
        assert by_label["weakling"].beats_bar is False
        assert by_label["champion"].beats_incumbent is True
        assert by_label["weakling"].beats_incumbent is False
        assert report.incumbent is not None
        assert report.incumbent.subject.ref == "incumbent"

    def test_notes_are_plain_language_and_non_empty(self) -> None:
        benchmark = Benchmark(id=uuid4(), name="b", created_at=_utc_now())
        bar = QualityBar(accuracy=0.8, latency_ms_p50=10.0, cost_usd_per_1k=0.05)
        report = compare_module.build_comparison_report(
            benchmark,
            [_comparison_subject("solo", 0.9, 3.0)],
            bar,
            None,
            self._spec(["task_quality"]),
        )
        assert report.notes, "notes must be non-empty"
        assert all(isinstance(n, str) and n for n in report.notes)
        joined = " ".join(report.notes)
        assert "solo" in joined
        assert "winner" in joined.lower()

    def test_failed_subject_gets_note_not_crash(self) -> None:
        benchmark = Benchmark(id=uuid4(), name="b", created_at=_utc_now())
        failed = ComparisonSubjectResult(
            subject=EvaluationSubject(kind=SubjectKind.MODEL_VERSION, ref="deadbeef"),
            quality_vector=None,
            metrics={"error": "feature mismatch"},
        )
        report = compare_module.build_comparison_report(
            benchmark, [failed], None, None, self._spec(["task_quality"])
        )
        assert report.winner is None
        assert any("deadbeef" in n for n in report.notes)


# ---------------------------------------------------------------------------
# router.py — HTTP contract
# ---------------------------------------------------------------------------


@pytest.fixture
def _eval_app(tmp_path: Path):
    """TestClient with the evaluation router mounted (main.py untouched)."""
    from app import usage as usage_module
    from app.evaluation.router import (
        get_benchmark_repository,
        get_evaluation_manager,
        get_evaluation_run_repository,
    )
    from app.evaluation.router import router as evaluation_router
    from app.models import InMemoryModelRepository, get_model_repository
    from app.specs import InMemorySpecRepository, get_spec_repository
    from app.usage import InMemoryUsageRepository

    project_repository = InMemoryProjectRepository()
    run_repository = runner_module.InMemoryEvaluationRunRepository()
    benchmark_repository = InMemoryBenchmarkRepository()
    model_repository = InMemoryModelRepository()
    spec_repository = InMemorySpecRepository()
    usage_repository = InMemoryUsageRepository()

    manager = EvaluationManager(
        run_repository=run_repository,
        benchmark_registry=BenchmarkRegistry(benchmark_repository),
        model_repository=model_repository,
        artifact_root=tmp_path / "artifacts",
        on_finish=_record_usage(usage_repository),
    )

    application = create_app()
    application.include_router(evaluation_router)
    application.dependency_overrides[get_project_repository] = lambda: project_repository
    application.dependency_overrides[get_evaluation_run_repository] = (
        lambda: run_repository
    )
    application.dependency_overrides[get_benchmark_repository] = (
        lambda: benchmark_repository
    )
    application.dependency_overrides[get_model_repository] = lambda: model_repository
    application.dependency_overrides[get_spec_repository] = lambda: spec_repository
    application.dependency_overrides[
        usage_module.get_usage_repository
    ] = lambda: usage_repository
    application.dependency_overrides[get_evaluation_manager] = lambda: manager
    client = TestClient(application)
    project_id = _make_project(project_repository)
    return client, project_id, manager, model_repository, spec_repository


def _record_usage(usage_repository):
    from shared.domain import UsageEvent, UsageKind, UsageScope

    def _on_finish(run: EvaluationRun) -> None:
        usage_repository.record_event(
            UsageEvent(
                id=uuid4(),
                project_id=run.project_id,
                scope=UsageScope.PROJECT,
                scope_id=run.project_id,
                kind=UsageKind.EVALUATION,
                quantity=float(run.metrics.get("predictions_evaluated", 0) or 0),
                unit="predictions",
                cost_usd=run.cost_usd,
                recorded_at=_utc_now(),
            )
        )

    return _on_finish


_AUTH = {"Authorization": "Bearer <redacted>"}


def _wait_for_run(client: TestClient, run_id: str, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/v1/evaluation-runs/{run_id}", headers=_AUTH)
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")


class TestRouter:
    def test_list_benchmarks_includes_seeded(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        resp = client.get(f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH)
        assert resp.status_code == 200
        names = {b["name"] for b in resp.json()}
        assert {"termination-benchmark", "ring-benchmark"} <= names

    def test_create_custom_benchmark(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        resp = client.post(
            f"/api/v1/projects/{project_id}/benchmarks",
            json={
                "name": "custom-1",
                "description": "mine",
                "rows": [{"x": [0.5], "label": 1}],
            },
            headers=_AUTH,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "custom-1"
        assert body["project_id"] == str(project_id)

    def test_get_benchmark_detail_and_404(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.get(f"/api/v1/benchmarks/{benchmark_id}", headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["name"] == "termination-benchmark"
        resp = client.get(f"/api/v1/benchmarks/{uuid4()}", headers=_AUTH)
        assert resp.status_code == 404

    def test_submit_run_and_poll_to_completed(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "baseline", "ref": "deterministic_rule"},
            },
            headers=_AUTH,
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]
        body = _wait_for_run(client, run_id)
        assert body["status"] == "COMPLETED"
        assert body["quality_vector"]["task_quality"] == pytest.approx(11 / 12)

    def test_submit_unknown_baseline_is_409(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "baseline", "ref": "not_a_baseline"},
            },
            headers=_AUTH,
        )
        assert resp.status_code == 409

    def test_submit_bogus_model_ref_is_409(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "model_version", "ref": str(uuid4())},
            },
            headers=_AUTH,
        )
        assert resp.status_code == 409

    def test_submit_invalid_subject_kind_is_409(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "telepathy"},
            },
            headers=_AUTH,
        )
        assert resp.status_code == 409

    def test_submit_run_on_missing_benchmark_is_404(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        resp = client.post(
            f"/api/v1/benchmarks/{uuid4()}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "baseline", "ref": "majority_class"},
            },
            headers=_AUTH,
        )
        assert resp.status_code == 404

    def test_list_evaluation_runs(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        client.post(
            f"/api/v1/benchmarks/{benchmark_id}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "baseline", "ref": "majority_class"},
            },
            headers=_AUTH,
        )
        resp = client.get(
            f"/api/v1/projects/{project_id}/evaluation-runs", headers=_AUTH
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_compare_includes_baselines_and_picks_winner(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/compare",
            json={"subjects": []},
            headers=_AUTH,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["benchmark_id"] == benchmark_id
        refs = {r["subject"]["ref"] for r in body["results"]}
        assert {"majority_class", "keyword_heuristic", "deterministic_rule"} <= refs
        assert body["winner"] is not None
        assert body["notes"], "compare must explain its verdicts"

    def test_compare_without_baselines(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/compare",
            json={
                "subjects": [{"kind": "baseline", "ref": "majority_class"}],
                "include_baselines": False,
            },
            headers=_AUTH,
        )
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1

    def test_compare_incumbent_unavailable_noted(self, _eval_app) -> None:
        # app.registry does not exist in this tree: the lazy import must fail
        # soft and the report must say so instead of 500ing.
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        resp = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/compare",
            json={
                "subjects": [],
                "incumbent_intelligence_version_id": str(uuid4()),
            },
            headers=_AUTH,
        )
        assert resp.status_code == 200
        assert any("incumbent unavailable" in n for n in resp.json()["notes"])


class TestCancelEndpoint:
    def test_cancel_terminal_run_is_409(self, _eval_app) -> None:
        client, project_id, *_ = _eval_app
        listed = client.get(
            f"/api/v1/projects/{project_id}/benchmarks", headers=_AUTH
        ).json()
        benchmark_id = next(
            b["id"] for b in listed if b["name"] == "termination-benchmark"
        )
        run_id = client.post(
            f"/api/v1/benchmarks/{benchmark_id}/runs",
            json={
                "project_id": str(project_id),
                "subject": {"kind": "baseline", "ref": "majority_class"},
            },
            headers=_AUTH,
        ).json()["id"]
        _wait_for_run(client, run_id)
        resp = client.post(f"/api/v1/evaluation-runs/{run_id}/cancel", headers=_AUTH)
        assert resp.status_code == 409
