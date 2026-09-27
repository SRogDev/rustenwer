"""Dataset Agent deterministic logic (product plan §14).

Schema inference, leakage detection, split recommendation, and dataset
version validation. Pure deterministic checks — the LLM only decides.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

from shared.domain import DatasetReport


def _column_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    return names


def _column_type(values: list[Any]) -> str:
    """Infer one column's type: int/float/bool/str/null/mixed (bool first!)."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "null"
    kinds = set()
    for v in non_null:
        if isinstance(v, bool):
            kinds.add("bool")
        elif isinstance(v, int):
            kinds.add("int")
        elif isinstance(v, float):
            kinds.add("float")
        elif isinstance(v, str):
            kinds.add("str")
        else:
            kinds.add("mixed")
    if kinds == {"int", "float"}:
        return "float"
    if len(kinds) == 1:
        return kinds.pop()
    return "mixed"


def infer_column_schema(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Infer per-column types over the row sample."""
    schema: dict[str, str] = {}
    for column in _column_names(rows):
        schema[column] = _column_type([row.get(column) for row in rows])
    return schema


def _hashable(value: Any) -> Any:
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


def detect_leakage(rows: list[dict[str, Any]], label_column: str | None) -> list[str]:
    """Flag feature columns that suspiciously determine the label.

    Deterministic check: a non-label column whose value uniquely determines
    the label on the sample is likely leaking the answer. All-unique columns
    (identifiers) are skipped — they determine everything trivially.
    """
    if not label_column or not rows:
        return []
    if not any(row.get(label_column) is not None for row in rows):
        return []

    n = len(rows)
    flags: list[str] = []
    for column in _column_names(rows):
        if column == label_column:
            continue
        values = [row.get(column) for row in rows]
        non_null = [v for v in values if v is not None]
        if len(non_null) < 2:
            continue
        distinct = {_hashable(v) for v in non_null}
        if len(distinct) < 2 or len(distinct) == n:
            continue  # constant or identifier-like
        label_by_value: dict[Any, set[Any]] = {}
        for value, row in zip(values, rows, strict=True):
            label = row.get(label_column)
            if value is None or label is None:
                continue
            label_by_value.setdefault(_hashable(value), set()).add(_hashable(label))
        if label_by_value and all(len(labels) == 1 for labels in label_by_value.values()):
            flags.append(
                f"column '{column}' uniquely determines '{label_column}' "
                f"on {n} rows — possible label leakage"
            )
    return flags


def recommend_split(n: int) -> dict[str, float]:
    """Train/validation/test split recommendation (fractions summing to 1)."""
    return {"train": 0.7, "validation": 0.15, "test": 0.15}


def validate_dataset_version(
    dataset_id: UUID,
    version: int,
    rows: list[dict[str, Any]],
    label_column: str | None,
) -> DatasetReport:
    """Validate a dataset version and compute its DatasetReport."""
    schema = infer_column_schema(rows)
    n = len(rows)

    class_balance: dict[str, int] | None = None
    if label_column and label_column in schema:
        counts = Counter(row.get(label_column) for row in rows if row.get(label_column) is not None)
        if counts:
            class_balance = {
                str(label): count
                for label, count in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
            }

    missing_values = {
        column: sum(1 for row in rows if row.get(column) is None) for column in schema
    }
    leakage_flags = detect_leakage(rows, label_column)

    imbalance_detected = False
    if class_balance and len(class_balance) >= 2:
        ordered = sorted(class_balance.values())
        imbalance_detected = ordered[0] < 0.2 * ordered[-1]

    label_present = class_balance is not None and sum(class_balance.values()) > 0
    ready_for_training = n >= 10 and not leakage_flags and label_present

    notes = [f"{n} rows validated"]
    if label_column and label_present:
        notes.append(f"label column '{label_column}' with {len(class_balance or {})} classes")
    elif label_column:
        notes.append(f"label column '{label_column}' missing or empty — labels required")
    if leakage_flags:
        notes.append(f"{len(leakage_flags)} leakage flag(s) — resolve before training")
    if imbalance_detected:
        notes.append("class imbalance detected (minority < 20% of majority)")
    if n < 10:
        notes.append("fewer than 10 rows — not enough for training")

    return DatasetReport(
        dataset_id=dataset_id,
        version=version,
        row_count=n,
        column_schema=schema,
        class_balance=class_balance,
        missing_values=missing_values,
        leakage_flags=leakage_flags,
        imbalance_detected=imbalance_detected,
        recommended_split=recommend_split(n),
        ready_for_training=ready_for_training,
        notes=notes,
    )
