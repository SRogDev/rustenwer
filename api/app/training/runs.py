"""Read model over a run's attempt directories (Phase 2).

The runner subprocess appends JSONL events to
`<data_dir>/runs/<run_id>/attempt-<n>/events.jsonl`. These helpers turn
those events into the API's logs / metrics / cost views. Torn trailing
lines (crashed writer) are tolerated — partial data is still served.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import UUID

from shared.domain import MetricPoint, MetricSeries, RunCost, RunMetrics

from app.training.checkpoints import list_checkpoints


def runs_root(data_dir: Path | str) -> Path:
    return Path(data_dir) / "runs"


def attempt_dirs(data_dir: Path | str, run_id: UUID) -> list[Path]:
    root = runs_root(data_dir) / str(run_id)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir() and p.name.startswith("attempt-")),
        key=lambda p: p.name,
    )


def latest_attempt_dir(data_dir: Path | str, run_id: UUID) -> Path | None:
    dirs = attempt_dirs(data_dir, run_id)
    return dirs[-1] if dirs else None


def new_attempt_dir(data_dir: Path | str, run_id: UUID) -> Path:
    """Create the next attempt-N directory for a run."""
    root = runs_root(data_dir) / str(run_id)
    root.mkdir(parents=True, exist_ok=True)
    existing = [p.name for p in attempt_dirs(data_dir, run_id)]
    n = 1
    while f"attempt-{n}" in existing:
        n += 1
    attempt = root / f"attempt-{n}"
    attempt.mkdir(parents=True, exist_ok=False)
    return attempt


def iter_events(attempt_dir: Path) -> Iterator[dict]:
    """Yield parsed events; skip blank/corrupt lines (crashed writer)."""
    path = Path(attempt_dir) / "events.jsonl"
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                yield event


def read_logs(attempt_dir: Path, tail: int = 300) -> list[dict[str, str]]:
    """Log lines as {"t", "line"} — the SSE payload shape.

    Primary source is logs.txt (written by the runner's EventSink);
    falls back to filtering events.jsonl when logs.txt is absent.
    """
    lines = read_log_lines(Path(attempt_dir), tail=None)
    parsed = []
    for raw in lines:
        try:
            entry = json.loads(raw)
            parsed.append({"t": str(entry.get("t", "")), "line": str(entry.get("line", ""))})
        except (json.JSONDecodeError, AttributeError):
            continue
    return parsed[-tail:] if tail >= 0 else parsed


def read_log_lines(attempt_dir: Path, tail: int | None) -> list[str]:
    """Raw log lines (JSON strings); logs.txt preferred, events.jsonl fallback."""
    logs_txt = Path(attempt_dir) / "logs.txt"
    if logs_txt.exists():
        lines = [ln for ln in logs_txt.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
    else:
        lines = [
            json.dumps({"t": e.get("t", ""), "line": e.get("line", "")})
            for e in iter_events(attempt_dir)
            if e.get("type") == "log"
        ]
    if tail is not None and tail >= 0:
        lines = lines[-tail:]
    return lines


def read_metrics(attempt_dir: Path, run_id: UUID) -> RunMetrics:
    """Build the shared RunMetrics contract from metric events."""
    by_name: dict[str, list[MetricPoint]] = {}
    for e in iter_events(attempt_dir):
        if e.get("type") != "metric":
            continue
        name = str(e.get("name", "unnamed"))
        try:
            value = float(e["value"])
        except (KeyError, TypeError, ValueError):
            continue
        by_name.setdefault(name, []).append(
            MetricPoint(
                step=int(e.get("step", 0)),
                value=value,
                ts=str(e.get("t", "")),
            )
        )
    return RunMetrics(
        run_id=run_id,
        series=[MetricSeries(name=name, points=points)
                for name, points in by_name.items()],
        latest={name: points[-1].value for name, points in by_name.items()
                if points},
    )


def _parse_ts(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _wall_segments(attempt_dir: Path) -> list[float]:
    """One wall-time per started→final execution segment.

    Pause/resume appends a second started/final pair to the same attempt
    dir; each pair is billed separately so nothing is double-counted.
    """
    segments: list[float] = []
    started = None
    for e in iter_events(attempt_dir):
        t = e.get("type")
        if t == "started":
            started = _parse_ts(str(e.get("t", "")))
        elif t == "final" and started is not None:
            final = _parse_ts(str(e.get("t", "")))
            if final is not None:
                segments.append(max((final - started).total_seconds(), 0.0))
            started = None
    return segments


def attempt_wall_seconds(attempt_dir: Path) -> float | None:
    """Wall time of the LAST execution segment; None if none completed.

    Used for per-reap usage events: each reap bills exactly the segment
    whose process just exited.
    """
    segments = _wall_segments(Path(attempt_dir))
    return segments[-1] if segments else None


def attempt_total_wall_seconds(attempt_dir: Path) -> float | None:
    """Total wall time across all execution segments (pause/resume-safe)."""
    segments = _wall_segments(Path(attempt_dir))
    return sum(segments) if segments else None


def read_cost(
    attempt_dir: Path, run_id: UUID, provider: str, rate_usd_per_hour: float
) -> RunCost:
    """Wall-time x rate, in the shared RunCost contract.

    Totals all execution segments, so a paused-then-resumed run reports
    its true cost instead of only the last segment.
    """
    wall = attempt_total_wall_seconds(attempt_dir) or 0.0
    return RunCost(
        run_id=run_id,
        provider=provider,
        seconds=wall,
        usd=wall / 3600 * rate_usd_per_hour,
        rate_usd_per_hour=rate_usd_per_hour,
    )


def read_checkpoints(attempt_dir: Path) -> list:
    """CheckpointInfo list for one attempt dir (empty when none)."""
    return list_checkpoints(Path(attempt_dir) / "checkpoints")


def read_final(attempt_dir: Path) -> dict | None:
    """The final event dict, or None when the attempt never finished."""
    final = None
    for e in iter_events(attempt_dir):
        if e.get("type") == "final":
            final = e
    return final
