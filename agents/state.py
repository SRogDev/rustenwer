"""Supervisor graph state (Phase-0 skeleton)."""

from __future__ import annotations

from typing import TypedDict


class SupervisorState(TypedDict, total=False):
    """Shared state flowing through the supervisor graph.

    Phase 0 carries just enough for the placeholder nodes to exercise the
    graph plumbing. Phase 1 agents (Specification, Dataset, Training
    Strategy, Evaluation, Supervisor) extend this with their own fields.
    """

    messages: list
    project_id: str | None
    problem_statement: str | None
    phase: str  # current pipeline phase; starts at "intake"
    notes: list[str]
