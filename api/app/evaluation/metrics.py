"""Evaluation metrics (plan §56).

Pure functions — no torch, no I/O — so the API routers, the evaluation
worker, and the comparison report all share one implementation.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any


def accuracy(y_true: list[Any], y_pred: list[Any]) -> float | None:
    """Fraction of predictions equal to the truth. None when empty."""
    if not y_true:
        return None
    return sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == p) / len(y_true)


def per_class_accuracy(y_true: list[Any], y_pred: list[Any]) -> dict[Any, float]:
    """Accuracy per distinct label, in first-appearance order."""
    totals: dict[Any, int] = {}
    correct: dict[Any, int] = {}
    for t, p in zip(y_true, y_pred, strict=True):
        totals[t] = totals.get(t, 0) + 1
        if t == p:
            correct[t] = correct.get(t, 0) + 1
    return {label: correct.get(label, 0) / n for label, n in totals.items()}


def expected_calibration_error(
    y_true: list[int], y_proba: list[float], n_bins: int = 10
) -> float | None:
    """Expected Calibration Error for binary probabilistic predictions.

    `y_true` holds 0/1, `y_proba` the predicted P(y=1). Bin `i` covers
    `(i/n_bins, (i+1)/n_bins]` (bin 0 also covers 0). ECE is the
    sample-weighted mean of |accuracy - confidence| over non-empty bins.
    None when there are no samples.
    """
    if not y_true:
        return None
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for proba, truth in zip(y_proba, y_true, strict=True):
        idx = min(int(proba * n_bins), n_bins - 1)
        bins[idx].append((proba, truth))
    n = len(y_true)
    ece = 0.0
    for members in bins:
        if not members:
            continue
        acc = sum(t for _, t in members) / len(members)
        conf = sum(p for p, _ in members) / len(members)
        ece += abs(acc - conf) * (len(members) / n)
    return ece


def brier_score(y_true: list[int], y_proba: list[float]) -> float | None:
    """Mean squared error between P(y=1) and the 0/1 truth. None when empty."""
    if not y_true:
        return None
    return sum((p - t) ** 2 for p, t in zip(y_proba, y_true, strict=True)) / len(y_true)


def latency_p50_ms(latencies: list[float]) -> float | None:
    """Median per-sample latency in milliseconds. None when empty."""
    if not latencies:
        return None
    return float(median(latencies))


def latency_p99_ms(latencies: list[float]) -> float | None:
    """Nearest-rank 99th percentile latency in milliseconds. None when empty."""
    if not latencies:
        return None
    ordered = sorted(latencies)
    rank = min(math.ceil(0.99 * len(ordered)), len(ordered))
    return float(ordered[rank - 1])


def cost_per_1k_usd(total_cost_usd: float, n: int) -> float:
    """Cost per 1,000 predictions. 0.0 when nothing was evaluated."""
    if n <= 0:
        return 0.0
    return total_cost_usd / n * 1000.0
