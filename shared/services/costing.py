"""Usage/cost aggregation (product plan §45)."""

from __future__ import annotations

from uuid import UUID

from shared.domain import ScopeRollup, UsageEvent, UsageRollups, UsageSummary


def summarize_usage(project_id: UUID, events: list[UsageEvent]) -> UsageSummary:
    """Aggregate a project's usage events into a UsageSummary.

    Events for other projects are excluded defensively (callers should
    already scope them, but the summary must never mix tenants).
    """
    scoped = [e for e in events if e.project_id == project_id]

    by_scope: dict[str, float] = {}
    by_kind: dict[str, float] = {}
    total = 0.0
    for event in scoped:
        total += event.cost_usd
        by_scope[event.scope.value] = by_scope.get(event.scope.value, 0.0) + event.cost_usd
        by_kind[event.kind.value] = by_kind.get(event.kind.value, 0.0) + event.cost_usd

    return UsageSummary(
        project_id=project_id,
        total_cost_usd=total,
        by_scope=by_scope,
        by_kind=by_kind,
        event_count=len(scoped),
    )


def rollup_usage(project_id: UUID, events: list[UsageEvent]) -> UsageRollups:
    """Per-scope cost rollups (Phase 3): how much each scope (training_job,
    model, deployment, evaluation, inference, ...) cost, broken down by kind.

    Same defensive tenant scoping as summarize_usage.
    """
    scoped = [e for e in events if e.project_id == project_id]

    by_scope: dict[str, ScopeRollup] = {}
    by_kind: dict[str, float] = {}
    total = 0.0
    for event in scoped:
        total += event.cost_usd
        rollup = by_scope.get(event.scope.value)
        if rollup is None:
            rollup = ScopeRollup(scope=event.scope.value)
            by_scope[event.scope.value] = rollup
        rollup.total_cost_usd += event.cost_usd
        rollup.by_kind[event.kind.value] = (
            rollup.by_kind.get(event.kind.value, 0.0) + event.cost_usd
        )
        rollup.event_count += 1
        by_kind[event.kind.value] = by_kind.get(event.kind.value, 0.0) + event.cost_usd

    return UsageRollups(
        project_id=project_id,
        total_cost_usd=total,
        by_scope=by_scope,
        by_kind=by_kind,
        event_count=len(scoped),
    )
