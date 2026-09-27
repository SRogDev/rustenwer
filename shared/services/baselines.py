"""Baselines (product plan §16): majority_class, keyword_heuristic, deterministic_rule.

Rule 9: baselines run BEFORE any training is proposed; the best baseline
sets the `bar_to_beat`. The evaluator is independent of the training
mechanism (Rule 11) — it scores row data, never model internals.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from datetime import UTC, datetime
from statistics import median
from time import perf_counter
from typing import Any
from uuid import UUID

from shared.domain import BaselineMetrics, BaselineReport, IntelligenceSpec, QualityBar


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _labels(rows: list[dict[str, Any]], label_column: str) -> list[Any]:
    return [row[label_column] for row in rows if row.get(label_column) is not None]


def _majority_label(labels: list[Any]) -> Any | None:
    """Most frequent label; ties broken alphabetically (deterministic)."""
    if not labels:
        return None
    counts = Counter(labels)
    return min(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[0]


def _accuracy(predictions: list[Any], truths: list[Any]) -> float | None:
    if not truths:
        return None
    return sum(1 for p, t in zip(predictions, truths, strict=True) if p == t) / len(truths)


def _timed_predict(
    predict_one: Any, rows: list[dict[str, Any]]
) -> tuple[list[Any], float]:
    """Run per-row predictions; return (predictions, p50 latency in ms)."""
    predictions: list[Any] = []
    latencies_ms: list[float] = []
    for row in rows:
        start = perf_counter()
        predictions.append(predict_one(row))
        latencies_ms.append((perf_counter() - start) * 1000.0)
    return predictions, median(latencies_ms) if latencies_ms else 0.0


def _text_column(rows: list[dict[str, Any]], label_column: str) -> str | None:
    """First non-label column whose non-null values are all strings."""
    if not rows:
        return None
    for key in rows[0]:
        if key == label_column:
            continue
        values = [row.get(key) for row in rows if row.get(key) is not None]
        if values and all(isinstance(v, str) for v in values):
            return key
    return None


def _numeric_columns(rows: list[dict[str, Any]], label_column: str) -> list[str]:
    """Non-label numeric (int/float, not bool) columns, sorted by name.

    Vector-valued columns (fixed-length lists/tuples of numbers, e.g. the
    ring benchmark's ``x: [float, float]``) expand to indexed pseudo-columns
    ``name[0]``, ``name[1]``, ... so threshold rules can see each dimension.
    Resolve values with :func:`_column_value`.
    """
    if not rows:
        return []
    columns = []
    for key in rows[0]:
        if key == label_column:
            continue
        values = [row.get(key) for row in rows if row.get(key) is not None]
        if not values:
            continue
        if all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
        ):
            columns.append(key)
        elif all(isinstance(v, (list, tuple)) for v in values):
            lengths = {len(v) for v in values}
            flat_ok = all(
                isinstance(x, (int, float)) and not isinstance(x, bool)
                for v in values
                for x in v
            )
            if len(lengths) == 1 and flat_ok:
                columns.extend(f"{key}[{i}]" for i in range(lengths.pop()))
    return sorted(columns)


def _column_value(row: dict[str, Any], column: str) -> Any:
    """Resolve a column against a row, honoring ``name[i]`` pseudo-columns."""
    name, sep, index = column.partition("[")
    if not sep:
        return row.get(column)
    try:
        i = int(index.rstrip("]"))
    except ValueError:
        return None
    values = row.get(name)
    if not isinstance(values, (list, tuple)) or i < 0 or i >= len(values):
        return None
    return values[i]


def _majority_baseline(
    rows: list[dict[str, Any]], label_column: str
) -> BaselineMetrics:
    labels = _labels(rows, label_column)
    majority = _majority_label(labels)

    def predict_one(_row: dict[str, Any]) -> Any:
        return majority

    predictions, p50 = _timed_predict(predict_one, rows)
    rule = {"majority_label": majority}
    return BaselineMetrics(
        name="majority_class",
        description="Always predict the most frequent label.",
        accuracy=_accuracy(predictions, labels),
        latency_ms_p50=p50,
        cost_usd_per_1k=0.0,
        size_bytes=len(json.dumps(rule, sort_keys=True).encode()),
        predictions_evaluated=len(labels),
    )


def _keyword_baseline(
    rows: list[dict[str, Any]], label_column: str
) -> BaselineMetrics:
    labels = _labels(rows, label_column)
    majority = _majority_label(labels)
    ordered_labels = sorted(set(labels), key=str)
    text_col = _text_column(rows, label_column)

    if text_col is not None:

        def predict_one(row: dict[str, Any]) -> Any:
            text = str(row.get(text_col) or "").lower()
            hits = [label for label in ordered_labels if str(label).lower() in text]
            return hits[0] if len(hits) == 1 else majority

        description = (
            f"Predict by label-token presence in text column '{text_col}'; "
            "fall back to the majority label on ambiguity."
        )
        rule: dict[str, Any] = {"text_column": text_col}
    else:
        numeric = _numeric_columns(rows, label_column)
        medians = {}
        if numeric:
            values = sorted(
                _column_value(row, numeric[0])
                for row in rows
                if _column_value(row, numeric[0]) is not None
            )
            medians[numeric[0]] = median(values) if values else 0.0

        def predict_one(row: dict[str, Any]) -> Any:
            if not numeric:
                return majority
            column = numeric[0]
            value = _column_value(row, column)
            if value is None:
                return majority
            side_labels = [
                lab
                for r, lab in ((r, r.get(label_column)) for r in rows)
                if lab is not None
                and _column_value(r, column) is not None
                and (_column_value(r, column) <= medians[column])
                == (value <= medians[column])
            ]
            return _majority_label(side_labels)

        description = (
            "No text column found; fall back to a median split on the first "
            "numeric column."
        )
        rule = {"numeric_column": numeric[0] if numeric else None, "medians": medians}

    predictions, p50 = _timed_predict(predict_one, rows)
    return BaselineMetrics(
        name="keyword_heuristic",
        description=description,
        accuracy=_accuracy(predictions, labels),
        latency_ms_p50=p50,
        cost_usd_per_1k=0.0,
        size_bytes=len(json.dumps(rule, sort_keys=True, default=str).encode()),
        predictions_evaluated=len(labels),
    )


def _deterministic_rule_baseline(
    rows: list[dict[str, Any]], label_column: str
) -> BaselineMetrics:
    labels = _labels(rows, label_column)
    majority = _majority_label(labels)

    best_accuracy = -1.0
    best_rule: dict[str, Any] = {"fallback": "majority_class"}

    for column in _numeric_columns(rows, label_column):
        values = sorted(
            {
                _column_value(row, column)
                for row in rows
                if _column_value(row, column) is not None
            }
        )
        thresholds = [(a + b) / 2 for a, b in itertools.pairwise(values)]
        for threshold in thresholds:
            left = [
                row.get(label_column)
                for row in rows
                if _column_value(row, column) is not None
                and row.get(label_column) is not None
                and _column_value(row, column) <= threshold
            ]
            right = [
                row.get(label_column)
                for row in rows
                if _column_value(row, column) is not None
                and row.get(label_column) is not None
                and _column_value(row, column) > threshold
            ]
            left_label = _majority_label(left)
            right_label = _majority_label(right)
            correct = sum(1 for lab in left if lab == left_label) + sum(
                1 for lab in right if lab == right_label
            )
            accuracy = correct / len(labels) if labels else 0.0
            if accuracy > best_accuracy:  # strictly greater: first best wins
                best_accuracy = accuracy
                best_rule = {
                    "column": column,
                    "threshold": threshold,
                    "left_label": left_label,
                    "right_label": right_label,
                }

    rule = best_rule
    column = rule.get("column")
    threshold = rule.get("threshold")

    def predict_one(row: dict[str, Any]) -> Any:
        value = _column_value(row, column) if column is not None else None
        if value is None:
            return majority
        return rule["left_label"] if value <= threshold else rule["right_label"]

    predictions, p50 = _timed_predict(predict_one, rows)
    return BaselineMetrics(
        name="deterministic_rule",
        description=(
            "Exhaustive scan over numeric columns and thresholds; "
            "each side predicts its majority label."
            if column is not None
            else "No numeric column found; fell back to majority_class."
        ),
        accuracy=_accuracy(predictions, labels),
        latency_ms_p50=p50,
        cost_usd_per_1k=0.0,
        size_bytes=len(json.dumps(rule, sort_keys=True, default=str).encode()),
        predictions_evaluated=len(labels),
    )


def run_baselines(
    spec: IntelligenceSpec,
    dataset_version_id: UUID,
    rows: list[dict[str, Any]],
    label_column: str = "label",
) -> BaselineReport:
    """Run the three cheap baselines and set the bar to beat (Rule 9).

    When labels are missing/unusable every baseline reports accuracy=None
    and the bar carries zeros — the caller should surface that in its
    recommendation (BaselineReport has no recommendation field).
    """
    if not rows:
        rows = []
    baselines = [
        _majority_baseline(rows, label_column),
        _keyword_baseline(rows, label_column),
        _deterministic_rule_baseline(rows, label_column),
    ]

    scored = [b for b in baselines if b.accuracy is not None]
    if scored:
        # Highest accuracy wins; ties broken by latency, then cost, then name.
        best = min(
            scored,
            key=lambda b: (-b.accuracy, b.latency_ms_p50, b.cost_usd_per_1k, b.name),  # type: ignore[operator]
        )
        best_name = best.name
        bar = QualityBar(
            accuracy=best.accuracy,  # type: ignore[arg-type]
            latency_ms_p50=best.latency_ms_p50,
            cost_usd_per_1k=best.cost_usd_per_1k,
        )
    else:
        best_name = ""
        bar = QualityBar(accuracy=0.0, latency_ms_p50=0.0, cost_usd_per_1k=0.0)

    return BaselineReport(
        spec_id=spec.id,
        dataset_version_id=dataset_version_id,
        baselines=baselines,
        best_baseline=best_name,
        bar_to_beat=bar,
        evaluated_at=_utc_now(),
    )
