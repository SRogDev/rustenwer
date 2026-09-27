"""Evaluation subjects (plan §56): baselines, model versions, references.

Rule 11: the evaluator scores row data, never model internals. Every
subject kind produces per-row ``(label, P(positive class))`` predictions
plus real per-sample latencies; the runner turns those into metrics.

Binary-probability convention: the *positive* class is the second label of
the sorted unique labels (``1`` for ``{0, 1}``, ``"stop"`` for
``{"continue", "stop"}``). ``y_proba`` is always P(positive). Hard
classifiers (the Phase-1 baselines) emit 1.0/0.0.

Feature mismatch (e.g. a ring-trained model scored on text rows, or a
20-feature model on 2-float rows) raises ``SubjectBenchmarkMismatch`` —
the run FAILS with a clear, honest error. That is negative evidence by
design, not a bug.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from time import perf_counter, sleep
from typing import Any
from uuid import UUID, uuid4

from shared.domain import (
    Benchmark,
    EvaluationSubject,
    IntelligencePrimitive,
    IntelligenceSpec,
    IntelligenceSpecStatus,
    ModelVersion,
    SubjectKind,
)
from shared.services.baselines import (
    _labels,
    _majority_label,
    _numeric_columns,
    _text_column,
    run_baselines,
)


class SubjectBenchmarkMismatch(Exception):
    """Subject features don't fit the benchmark rows: the run must FAIL.

    Raised at evaluation time (inside the worker), never at submit: a
    mismatch is evidence about the subject, not a malformed request.
    """


class SubjectArtifactError(Exception):
    """The subject's artifact bundle is missing or unreadable: run FAILS."""


class UnknownBaselineError(ValueError):
    """Unknown baseline name: 409 at submit."""


class UnknownModelVersionError(ValueError):
    """Unknown model_version ref: 409 at submit."""


class InvalidSubjectError(ValueError):
    """Malformed subject (bad kind, missing ref, ...): 409 at submit."""


KNOWN_BASELINES = ("majority_class", "keyword_heuristic", "deterministic_rule")


@dataclass
class RowPredictions:
    """Per-row predictions of one subject on one benchmark's rows."""

    y_true: list[Any] = field(default_factory=list)
    y_pred: list[Any] = field(default_factory=list)
    y_proba: list[float] = field(default_factory=list)  # P(positive class)
    latencies_ms: list[float] = field(default_factory=list)
    rows_evaluated: int = 0
    total_rows: int = 0
    positive_label: Any = None
    cancelled: bool = False


def positive_label_for(labels: list[Any]) -> Any | None:
    """Second sorted unique label (binary positive class), else the only one."""
    unique = sorted(set(labels), key=str)
    if not unique:
        return None
    return unique[1] if len(unique) > 1 else unique[0]


def validate_subject(
    subject: EvaluationSubject, model_repository: Any
) -> ModelVersion | None:
    """Validate a subject at submit time; 409-style ValueErrors on faults.

    Returns the resolved ModelVersion for ``model_version`` subjects, else
    None. Feature compatibility is checked later, at evaluation time.
    """
    if subject.kind == SubjectKind.BASELINE:
        if subject.ref not in KNOWN_BASELINES:
            raise UnknownBaselineError(
                f"unknown baseline {subject.ref!r}; "
                f"known: {', '.join(KNOWN_BASELINES)}"
            )
        return None
    if subject.kind == SubjectKind.MODEL_VERSION:
        try:
            version_id = UUID(str(subject.ref))
        except (ValueError, AttributeError, TypeError) as exc:
            raise UnknownModelVersionError(
                f"model_version ref is not a UUID: {subject.ref!r}"
            ) from exc
        version = model_repository.get_version(version_id)
        if version is None:
            raise UnknownModelVersionError(
                f"unknown model_version ref: {subject.ref}"
            )
        return version
    if subject.kind == SubjectKind.REFERENCE:
        if subject.quality_vector is None:
            raise InvalidSubjectError(
                "reference subjects must carry a quality_vector"
            )
        return None
    raise InvalidSubjectError(f"invalid subject kind: {subject.kind!r}")


# --------------------------------------------------------------------------
# Baseline subjects
# --------------------------------------------------------------------------


def _baseline_predictors(
    rows: list[dict[str, Any]], label_column: str, baseline_name: str
) -> Any:
    """Per-row predict closures mirroring shared/services/baselines.py.

    The fitting helpers are imported (not duplicated) so tie-breaking and
    rule selection cannot drift; the closures mirror the baselines'
    ``predict_one`` logic one-to-one. ``evaluate_baseline_rows`` pins the
    mirror: per-row accuracy must equal run_baselines' aggregate accuracy.
    """
    labels = _labels(rows, label_column)
    majority = _majority_label(labels)

    if baseline_name == "majority_class":

        def predict(row: dict[str, Any]) -> Any:
            return majority

    elif baseline_name == "keyword_heuristic":
        ordered_labels = sorted(set(labels), key=str)
        text_col = _text_column(rows, label_column)
        if text_col is not None:

            def predict(row: dict[str, Any]) -> Any:  # noqa: F811
                text = str(row.get(text_col) or "").lower()
                hits = [lab for lab in ordered_labels if str(lab).lower() in text]
                return hits[0] if len(hits) == 1 else majority

        else:
            numeric = _numeric_columns(rows, label_column)
            medians: dict[str, float] = {}
            if numeric:
                values = sorted(
                    row[numeric[0]] for row in rows if row.get(numeric[0]) is not None
                )
                medians[numeric[0]] = float(median(values)) if values else 0.0

            def predict(row: dict[str, Any]) -> Any:  # noqa: F811
                if not numeric:
                    return majority
                column = numeric[0]
                value = row.get(column)
                if value is None:
                    return majority
                side_labels = [
                    lab
                    for r, lab in ((r, r.get(label_column)) for r in rows)
                    if lab is not None
                    and r.get(column) is not None
                    and (r[column] <= medians[column]) == (value <= medians[column])
                ]
                return _majority_label(side_labels)

    elif baseline_name == "deterministic_rule":
        best_accuracy = -1.0
        best_rule: dict[str, Any] = {"fallback": "majority_class"}
        for column in _numeric_columns(rows, label_column):
            values = sorted({row[column] for row in rows if row.get(column) is not None})
            thresholds = [(a + b) / 2 for a, b in zip(values, values[1:], strict=False)]
            for threshold in thresholds:
                left = [
                    row.get(label_column)
                    for row in rows
                    if row.get(column) is not None
                    and row.get(label_column) is not None
                    and row[column] <= threshold
                ]
                right = [
                    row.get(label_column)
                    for row in rows
                    if row.get(column) is not None
                    and row.get(label_column) is not None
                    and row[column] > threshold
                ]
                left_label = _majority_label(left)
                right_label = _majority_label(right)
                correct = sum(1 for lab in left if lab == left_label) + sum(
                    1 for lab in right if lab == right_label
                )
                acc = correct / len(labels) if labels else 0.0
                if acc > best_accuracy:  # strictly greater: first best wins
                    best_accuracy = acc
                    best_rule = {
                        "column": column,
                        "threshold": threshold,
                        "left_label": left_label,
                        "right_label": right_label,
                    }
        rule = best_rule
        column = rule.get("column")
        threshold = rule.get("threshold")

        def predict(row: dict[str, Any]) -> Any:  # noqa: F811
            if column is None or row.get(column) is None:
                return majority
            return rule["left_label"] if row[column] <= threshold else rule["right_label"]

    else:
        raise UnknownBaselineError(f"unknown baseline {baseline_name!r}")
    return predict


def evaluate_baseline_rows(
    rows: list[dict[str, Any]],
    label_column: str,
    baseline_name: str,
    *,
    should_stop: Any = None,
    row_delay_s: float = 0.0,
) -> RowPredictions:
    """Score one named baseline per row, with real per-sample latencies."""
    if baseline_name not in KNOWN_BASELINES:
        raise UnknownBaselineError(f"unknown baseline {baseline_name!r}")
    predict = _baseline_predictors(rows, label_column, baseline_name)

    labeled = [row for row in rows if row.get(label_column) is not None]
    positive = positive_label_for([row[label_column] for row in labeled])
    result = RowPredictions(total_rows=len(rows), positive_label=positive)
    for row in labeled:
        if should_stop is not None and should_stop():
            result.cancelled = True
            break
        start = perf_counter()
        prediction = predict(row)
        result.latencies_ms.append((perf_counter() - start) * 1000.0)
        result.y_true.append(row[label_column])
        result.y_pred.append(prediction)
        result.y_proba.append(1.0 if prediction == positive else 0.0)
        result.rows_evaluated += 1
        if row_delay_s > 0:
            sleep(row_delay_s)
    return result


def evaluate_baseline_subject(
    benchmark: Benchmark,
    rows: list[dict[str, Any]],
    label_column: str,
    baseline_name: str,
    *,
    should_stop: Any = None,
    row_delay_s: float = 0.0,
) -> RowPredictions:
    """Evaluate a baseline subject, reusing run_baselines for name validation.

    A lightweight IntelligenceSpec is built from the benchmark (name and
    description map to name/problem_statement, primitive CLASSIFICATION);
    run_baselines runs the real baseline service and the named baseline is
    picked from its report — the per-row scoring above must agree with it.
    """
    spec = IntelligenceSpec(
        id=uuid4(),
        project_id=uuid4(),
        name=benchmark.name,
        problem_statement=benchmark.description or benchmark.name,
        intelligence_primitive=IntelligencePrimitive.CLASSIFICATION,
        status=IntelligenceSpecStatus.DRAFT,
    )
    report = run_baselines(spec, uuid4(), rows, label_column=label_column)
    if baseline_name not in {b.name for b in report.baselines}:
        raise UnknownBaselineError(f"unknown baseline {baseline_name!r}")
    return evaluate_baseline_rows(
        rows, label_column, baseline_name, should_stop=should_stop,
        row_delay_s=row_delay_s,
    )


# --------------------------------------------------------------------------
# Model-version subjects (torch bundles)
# --------------------------------------------------------------------------


def _torch():  # lazy: importing this module must not require torch
    try:
        import torch
    except ImportError as exc:
        raise SubjectArtifactError(
            "torch is not installed; cannot evaluate a model_version subject"
        ) from exc
    return torch


def _resolve_bundle_dir(artifact_uri: str | None, artifact_root: Path) -> Path:
    if not artifact_uri:
        raise SubjectArtifactError("model version has no artifact_uri")
    bundle = Path(artifact_uri)
    if not bundle.is_absolute():
        bundle = artifact_root / bundle
    missing = [
        name for name in ("model.pt", "config.json") if not (bundle / name).is_file()
    ]
    if missing:
        raise SubjectArtifactError(
            f"artifact bundle {bundle} is missing {', '.join(missing)}; "
            "expected an exported bundle (model.pt + config.json)"
        )
    return bundle


def _rebuild_mlp(n_features: int, n_classes: int, hp: dict[str, Any], seed: int):
    """Rebuild the MLP exactly as adapters.py::ClassifierAdapter.build_model."""
    torch = _torch()
    hidden = hp.get("hidden") or [64]
    if isinstance(hidden, int):
        hidden = [hidden]
    layers: list[Any] = []
    prev = int(n_features)
    torch.manual_seed(seed)
    for h in hidden:
        layers += [torch.nn.Linear(prev, int(h)), torch.nn.ReLU()]
        prev = int(h)
    layers.append(torch.nn.Linear(prev, int(n_classes)))
    return torch.nn.Sequential(*layers)


def evaluate_model_version_rows(
    version: ModelVersion,
    rows: list[dict[str, Any]],
    label_column: str,
    artifact_root: Path,
    *,
    should_stop: Any = None,
    row_delay_s: float = 0.0,
) -> RowPredictions:
    """Score a registered model version per row: predict_proba + latencies."""
    torch = _torch()
    bundle = _resolve_bundle_dir(version.artifact_uri, Path(artifact_root))
    config = json.loads((bundle / "config.json").read_text(encoding="utf-8"))
    n_features = int(config["n_features"])
    n_classes = int(config["n_classes"])
    hp = config.get("hyperparameters") or {}
    seed = int(config.get("seed", 0))

    labeled = [row for row in rows if row.get(label_column) is not None]
    unique_labels = sorted({row[label_column] for row in labeled}, key=str)
    if len(unique_labels) != n_classes:
        raise SubjectBenchmarkMismatch(
            f"model expects {n_classes} output classes but the benchmark rows "
            f"carry {len(unique_labels)} distinct labels {unique_labels}"
        )
    positive = positive_label_for([row[label_column] for row in labeled])
    positive_idx = unique_labels.index(positive)

    model = _rebuild_mlp(n_features, n_classes, hp, seed)
    state = torch.load(bundle / "model.pt", map_location="cpu", weights_only=True)
    model.load_state_dict(state["model"] if isinstance(state, dict) and "model" in state else state)
    model.eval()

    result = RowPredictions(total_rows=len(rows), positive_label=positive)
    with torch.no_grad():
        for row in labeled:
            if should_stop is not None and should_stop():
                result.cancelled = True
                break
            features = row.get("x")
            if not (
                isinstance(features, list)
                and len(features) == n_features
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in features)
            ):
                raise SubjectBenchmarkMismatch(
                    f"model expects a numeric feature vector 'x' of length "
                    f"{n_features} (from its exported config.json) but row "
                    f"carries {features!r}; a model trained on different "
                    f"features cannot be scored on this benchmark"
                )
            start = perf_counter()
            logits = model(torch.tensor([features], dtype=torch.float32))
            proba = float(torch.softmax(logits, dim=1)[0, positive_idx].item())
            result.latencies_ms.append((perf_counter() - start) * 1000.0)
            truth = row[label_column]
            result.y_true.append(truth)
            result.y_pred.append(
                unique_labels[int(torch.argmax(logits, dim=1).item())]
            )
            result.y_proba.append(proba)
            result.rows_evaluated += 1
            if row_delay_s > 0:
                sleep(row_delay_s)
    return result


def bundle_size_bytes(version: ModelVersion, artifact_root: Path) -> int | None:
    """Total bytes of the exported bundle, or None when unavailable."""
    try:
        bundle = _resolve_bundle_dir(version.artifact_uri, Path(artifact_root))
    except SubjectArtifactError:
        return None
    return sum(p.stat().st_size for p in bundle.iterdir() if p.is_file())


def evaluate_subject_rows(
    *,
    subject: EvaluationSubject,
    benchmark: Benchmark,
    rows: list[dict[str, Any]],
    label_column: str,
    model_repository: Any,
    artifact_root: Path,
    should_stop: Any = None,
    row_delay_s: float = 0.0,
) -> RowPredictions:
    """Dispatch to the subject-kind evaluator (baseline | model_version)."""
    if subject.kind == SubjectKind.BASELINE:
        return evaluate_baseline_subject(
            benchmark, rows, label_column, str(subject.ref),
            should_stop=should_stop, row_delay_s=row_delay_s,
        )
    if subject.kind == SubjectKind.MODEL_VERSION:
        version = validate_subject(subject, model_repository)
        assert version is not None  # validate_subject resolved it
        return evaluate_model_version_rows(
            version, rows, label_column, Path(artifact_root),
            should_stop=should_stop, row_delay_s=row_delay_s,
        )
    raise InvalidSubjectError(
        f"subject kind {subject.kind!r} has no row evaluator "
        "(reference subjects carry their quality vector directly)"
    )
