"""Supervisor graph state (Phase 1 — Original Rustenwer MVP Core)."""

from __future__ import annotations

from typing import Any, TypedDict


class SupervisorState(TypedDict, total=False):
    """Shared state flowing through the supervisor graph.

    Phase 1 carries the artifacts of each agent node as plain dicts (JSON-safe,
    so the graph stays serializable). Node functions reconstruct the pydantic
    models from `shared.domain` when calling the deterministic services.
    """

    messages: list
    project_id: str | None
    problem_statement: str | None
    phase: str  # current pipeline phase; starts at "intake", ends at "done"
    notes: list[str]

    # --- Phase 1 agent artifacts (dicts serialized from shared.domain models)
    spec: dict | None  # IntelligenceSpec
    diagnosis: dict | None  # DiagnosisResult
    dataset_report: dict | None  # DatasetReport
    strategy: dict | None  # TrainingStrategy
    baseline_report: dict | None  # BaselineReport
    recommendation: str | None
    no_ml_path: bool  # True when diagnosis concludes no training is needed (Rule 13)

    # --- Dataset plumbing (inputs for the dataset/baseline nodes)
    dataset_rows: list[dict[str, Any]]
    label_column: str | None
    dataset_id: str | None
    dataset_version: int | None
