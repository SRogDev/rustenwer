"""Phase 3: per-scope cost rollups (TDD)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared.domain import UsageEvent, UsageKind, UsageScope
from shared.services.costing import rollup_usage


def _event(project_id, scope, kind, cost):
    return UsageEvent(
        id=uuid4(),
        project_id=project_id,
        scope=scope,
        scope_id=uuid4(),
        kind=kind,
        quantity=1.0,
        unit="run",
        cost_usd=cost,
        recorded_at=datetime.now(UTC).isoformat(),
    )


def test_rollup_groups_by_scope_and_kind():
    project_id = uuid4()
    other_project = uuid4()
    events = [
        _event(project_id, UsageScope.TRAINING_JOB, UsageKind.TRAINING, 1.50),
        _event(project_id, UsageScope.TRAINING_JOB, UsageKind.TRAINING, 0.50),
        _event(project_id, UsageScope.MODEL, UsageKind.INFERENCE, 0.10),
        _event(project_id, UsageScope.MODEL, UsageKind.EVALUATION, 0.05),
        _event(other_project, UsageScope.MODEL, UsageKind.INFERENCE, 99.0),  # excluded
    ]
    rollup = rollup_usage(project_id, events)
    assert rollup.project_id == project_id
    assert rollup.total_cost_usd == 2.15
    assert rollup.event_count == 4
    assert rollup.by_scope["training_job"].total_cost_usd == 2.0
    assert rollup.by_scope["training_job"].event_count == 2
    assert rollup.by_scope["training_job"].by_kind["training"] == 2.0
    assert rollup.by_scope["model"].total_cost_usd == pytest.approx(0.15)
    assert rollup.by_scope["model"].by_kind["evaluation"] == 0.05
    assert rollup.by_kind["training"] == 2.0
    assert rollup.by_kind["evaluation"] == 0.05


def test_rollup_empty():
    project_id = uuid4()
    rollup = rollup_usage(project_id, [])
    assert rollup.total_cost_usd == 0.0
    assert rollup.by_scope == {}
    assert rollup.event_count == 0
