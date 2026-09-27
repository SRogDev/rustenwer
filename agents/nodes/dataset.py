"""Dataset agent node.

Orchestrates `shared.services.datasets.validate_dataset_version` (Rule 3):
schema inference, missing values, class balance, leakage flags and the
train/val/test split recommendation are all computed deterministically in
the service; this node only wires state in and stores the report.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import structlog

from agents.nodes._common import append_note
from agents.state import SupervisorState

logger = structlog.get_logger(__name__)


def dataset_node(state: SupervisorState) -> dict:
    """Validate the dataset version carried in state and store the report."""
    from shared.services.datasets import (  # lazy: backend builder delivers it
        validate_dataset_version,
    )

    dataset_id = UUID(str(state.get("dataset_id") or uuid4()))
    version = int(state.get("dataset_version") or 1)
    rows = list(state.get("dataset_rows") or [])
    label_column = state.get("label_column")

    report = validate_dataset_version(
        dataset_id=dataset_id,
        version=version,
        rows=rows,
        label_column=label_column,
    )
    logger.info(
        "dataset.validated",
        rows=report.row_count,
        ready_for_training=report.ready_for_training,
        leakage=len(report.leakage_flags),
    )
    return {
        "dataset_report": report.model_dump(mode="json"),
        "phase": "dataset_check",
        **append_note(
            state,
            f"dataset_check: validated {report.row_count} rows "
            f"(ready_for_training={report.ready_for_training})",
        ),
    }
