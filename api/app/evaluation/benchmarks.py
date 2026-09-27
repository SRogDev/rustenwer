"""Benchmarks (plan §57): reusable, seeded, comparable across candidates.

Two global benchmarks (``project_id=None``) are seeded into every fresh
repository:

- ``termination-benchmark`` — the Phase-1 §7 termination fixture
  (``shared/services/fixtures.py::termination_dataset_rows``).
- ``ring-benchmark`` — a deterministic held-out test set for the Phase-2
  ring task (``api/app/training/adapters.py::_synthetic_blobs``).

The ring test set reuses the *same distribution* as training: each feature
is drawn i.i.d. from N(0, 1) and the label is 1 iff the radius of the first
two dims exceeds sqrt(2·ln 2) ≈ 1.1774 (the Rayleigh median, so classes are
~50/50). The draws are produced by ``random.Random(RING_TEST_SEED).gauss``,
not ``torch.randn`` — bit-for-bit different, distributionally identical —
and the seed is fixed, so the set is a deterministic held-out set that
never overlaps the training draws.

Note on width: rows carry only the 2 signal dims (``input_spec`` is
``{x: [float, float]}``). The Phase-2 smoke task trains on 20-dim rows, so
a model exported from that task *mismatches* this benchmark on feature
width — ``subjects.SubjectBenchmarkMismatch`` fails the run with a clear
error instead of silently mis-scoring (negative evidence by design).

Project-scoped custom benchmarks store their rows (and label column) in
the repository side-table; the ``Benchmark`` contract shape itself is
never extended.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from shared.domain import Benchmark
from shared.services.fixtures import termination_dataset_rows

RING_TEST_SEED = 20260926
RING_TEST_N = 200
RING_THRESHOLD = math.sqrt(2 * math.log(2))  # Rayleigh median ≈ 1.1774

TERMINATION_BENCHMARK_ID = uuid5(NAMESPACE_URL, "rustenwer:benchmark:termination")
RING_BENCHMARK_ID = uuid5(NAMESPACE_URL, "rustenwer:benchmark:ring")

_ZERO_COST_RULES = {
    "compute": "local-cpu",
    "cost_usd_per_1k": 0.0,
    "note": "Evaluation runs on local CPU; no billed compute, cost_usd is 0.0 by rule.",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _ring_test_rows(n: int = RING_TEST_N, seed: int = RING_TEST_SEED) -> list[dict[str, Any]]:
    """Deterministic held-out ring test set (same distribution as training)."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for _ in range(n):
        x = [rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)]
        label = 1 if math.hypot(*x) > RING_THRESHOLD else 0
        rows.append({"x": x, "label": label})
    return rows


def termination_benchmark() -> Benchmark:
    """The global termination benchmark (Phase-1 §7 fixture)."""
    return Benchmark(
        id=TERMINATION_BENCHMARK_ID,
        project_id=None,
        name="termination-benchmark",
        description=(
            "Decide whether an agentic search should stop or continue, "
            "over the 12 labeled §7 termination states."
        ),
        input_spec={
            "state_summary": "string",
            "depth": "int",
            "progress_score": "float",
        },
        expected_output={"label": "stop | continue"},
        evaluation_function="classification_on_rows",
        metrics=["accuracy", "latency_ms_p50", "cost_usd_per_1k"],
        cost_rules=dict(_ZERO_COST_RULES),
        created_at=_utc_now(),
    )


def ring_benchmark() -> Benchmark:
    """The global ring benchmark (deterministic held-out ring test set)."""
    return Benchmark(
        id=RING_BENCHMARK_ID,
        project_id=None,
        name="ring-benchmark",
        description=(
            "Binary classification on a deterministic 200-sample held-out set "
            "drawn from the Phase-2 ring distribution (Rayleigh median "
            "boundary ≈ 1.1774 on the first two dims)."
        ),
        input_spec={"x": "[float, float]"},
        expected_output={"label": "0 | 1"},
        evaluation_function="classification_on_rows",
        metrics=["accuracy", "latency_ms_p50", "cost_usd_per_1k"],
        cost_rules=dict(_ZERO_COST_RULES),
        created_at=_utc_now(),
    )


# --------------------------------------------------------------------------
# Repository interface + in-memory implementation
# --------------------------------------------------------------------------


class BenchmarkRepository(Protocol):
    """Storage contract for benchmarks (rows live in a side-table)."""

    def list_benchmarks(self, project_id: UUID) -> list[Benchmark]:
        """Seeded global benchmarks + the project's own benchmarks."""
        ...

    def get_benchmark(self, benchmark_id: UUID) -> Benchmark | None:
        """A benchmark by id, or None when it does not exist."""
        ...

    def create_benchmark(self, benchmark: Benchmark) -> Benchmark:
        """Persist a fully-formed benchmark."""
        ...

    def store_rows(
        self, benchmark_id: UUID, rows: list[dict[str, Any]], label_column: str = "label"
    ) -> None:
        """Attach evaluation rows (and their label column) to a benchmark."""
        ...

    def get_rows(self, benchmark_id: UUID) -> list[dict[str, Any]] | None:
        """The benchmark's rows, or None when none were stored."""
        ...

    def get_label_column(self, benchmark_id: UUID) -> str:
        """Label column for the benchmark's rows ('label' default)."""
        ...


class InMemoryBenchmarkRepository:
    """Dict-backed repository, seeded with the two global benchmarks."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._benchmarks: dict[UUID, Benchmark] = {}
        self._rows: dict[UUID, list[dict[str, Any]]] = {}
        self._label_columns: dict[UUID, str] = {}
        for benchmark, rows in (
            (termination_benchmark(), termination_dataset_rows()),
            (ring_benchmark(), _ring_test_rows()),
        ):
            self._benchmarks[benchmark.id] = benchmark
            self._rows[benchmark.id] = rows
            self._label_columns[benchmark.id] = "label"

    def list_benchmarks(self, project_id: UUID) -> list[Benchmark]:
        with self._lock:
            return [
                b
                for b in self._benchmarks.values()
                if b.project_id is None or b.project_id == project_id
            ]

    def get_benchmark(self, benchmark_id: UUID) -> Benchmark | None:
        with self._lock:
            return self._benchmarks.get(benchmark_id)

    def create_benchmark(self, benchmark: Benchmark) -> Benchmark:
        with self._lock:
            self._benchmarks[benchmark.id] = benchmark
            return benchmark

    def store_rows(
        self, benchmark_id: UUID, rows: list[dict[str, Any]], label_column: str = "label"
    ) -> None:
        with self._lock:
            self._rows[benchmark_id] = rows
            self._label_columns[benchmark_id] = label_column

    def get_rows(self, benchmark_id: UUID) -> list[dict[str, Any]] | None:
        with self._lock:
            rows = self._rows.get(benchmark_id)
            return list(rows) if rows is not None else None

    def get_label_column(self, benchmark_id: UUID) -> str:
        with self._lock:
            return self._label_columns.get(benchmark_id, "label")


# --------------------------------------------------------------------------
# Registry service
# --------------------------------------------------------------------------


class BenchmarkRegistry:
    """Seeded global benchmarks + project-scoped custom benchmarks."""

    def __init__(self, repository: BenchmarkRepository) -> None:
        self._repository = repository

    def list(self, project_id: UUID) -> list[Benchmark]:
        """Global benchmarks plus the project's own."""
        return self._repository.list_benchmarks(project_id)

    def get(self, benchmark_id: UUID) -> Benchmark | None:
        return self._repository.get_benchmark(benchmark_id)

    def get_rows(self, benchmark: Benchmark) -> list[dict[str, Any]]:
        rows = self._repository.get_rows(benchmark.id)
        if rows is None:
            raise ValueError(f"benchmark {benchmark.id} has no rows stored")
        return rows

    def get_label_column(self, benchmark: Benchmark) -> str:
        return self._repository.get_label_column(benchmark.id)

    def create_custom(
        self,
        project_id: UUID,
        *,
        name: str,
        rows: list[dict[str, Any]],
        label_column: str = "label",
        description: str = "",
        input_spec: dict[str, Any] | None = None,
        expected_output: dict[str, Any] | None = None,
        metrics: list[str] | None = None,
        cost_rules: dict[str, Any] | None = None,
    ) -> Benchmark:
        """Register a project-scoped benchmark with its rows."""
        benchmark = Benchmark(
            id=uuid4(),
            project_id=project_id,
            name=name,
            description=description,
            input_spec=input_spec or {},
            expected_output=expected_output or {},
            evaluation_function="classification_on_rows",
            metrics=metrics or ["accuracy", "latency_ms_p50", "cost_usd_per_1k"],
            cost_rules=cost_rules or dict(_ZERO_COST_RULES),
            created_at=_utc_now(),
        )
        self._repository.create_benchmark(benchmark)
        self._repository.store_rows(benchmark.id, rows, label_column)
        return benchmark
