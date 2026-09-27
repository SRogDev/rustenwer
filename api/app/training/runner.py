"""Training-run worker subprocess (Phase 2).

Entry point: `python -m app.training.runner --attempt-dir <dir>`

The manager writes `strategy.json` into the attempt dir, then spawns this.
The runner:
  1. validates the strategy through the adapter (Rule 3: strategy is input)
  2. prepares the dataset (real, seeded)
  3. trains (real torch / real Unsloth on CUDA), emitting JSONL events:
       {"type":"started"|"log"|"metric"|"checkpoint"|"artifact"|
               "heartbeat"|"final", "t": iso, ...}
  4. exports + publishes the model artifact
  5. writes final.json (status COMPLETED/FAILED/CANCELLED/PAUSED)

Signals: SIGTERM = graceful cancel, SIGUSR1 = graceful pause. The adapter
loop calls should_stop() per batch; on stop it saves a checkpoint and the
runner reports CANCELLED/PAUSED instead of FAILED.

Exit codes: 0 finished (any terminal status), 1 unexpected crash.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import signal
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class EventSink:
    """Append-only JSONL emitter; every event carries an ISO timestamp.

    Log events are ALSO appended to logs.txt as {"t", "line"} records —
    the plain-text stream the SSE endpoint serves.
    """

    def __init__(self, attempt_dir: Path) -> None:
        self._path = attempt_dir / "events.jsonl"
        self._fh = open(self._path, "a", encoding="utf-8")  # noqa: PTH123
        self._logs = open(attempt_dir / "logs.txt", "a", encoding="utf-8")  # noqa: PTH123

    def emit(self, event: dict[str, Any]) -> None:
        event = {"t": _utc_now(), **event}
        self._fh.write(json.dumps(event) + "\n")
        self._fh.flush()
        if event.get("type") == "log":
            self._logs.write(json.dumps({"t": event["t"], "line": event.get("line", "")}) + "\n")
            self._logs.flush()

    def log(self, line: str) -> None:
        self.emit({"type": "log", "line": line})

    def close(self) -> None:
        self._fh.close()
        self._logs.close()


_stop_mode: dict[str, str | None] = {"mode": None}
_last_heartbeat = {"at": 0.0}


def _install_signal_handlers() -> None:
    def _handler(signum: int, _frame: Any) -> None:
        # SIGUSR1 (10) = pause, anything else terminating = cancel.
        _stop_mode["mode"] = "pause" if signum == signal.SIGUSR1 else "cancel"

    signal.signal(signal.SIGTERM, _handler)
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, _handler)


def _resource_snapshot() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 2),
        "rss_mb": round(usage.ru_maxrss / 1024, 1),  # ru_maxrss is KiB on Linux
        "gpu": None,  # local CPU execution: no GPU telemetry
    }


def run_attempt(attempt_dir: Path, sink: EventSink) -> dict[str, Any]:
    """Execute one training attempt. Returns the final payload."""
    from shared.domain import TrainingStrategy

    from app.training.adapters import (
        AdapterContext,
        AdapterEnvironmentError,
        TrainContext,
        get_adapter,
    )

    strategy = TrainingStrategy(**json.loads((attempt_dir / "strategy.json").read_text()))
    sink.emit({"type": "started", "run_id": os.environ["RUSTENWER_RUN_ID"]})

    try:
        adapter = get_adapter(strategy.training_method)
    except KeyError as exc:
        return {"status": "FAILED", "error": str(exc)}

    errors = adapter.validate(strategy)
    if errors:
        return {"status": "FAILED",
                "error": "strategy validation failed: " + "; ".join(errors)}

    hp = dict(strategy.hyperparameters or {})
    seed = int(hp.get("seed", 0))
    ctx = AdapterContext(strategy=strategy, workdir=attempt_dir,
                         hyperparameters=hp, seed=seed)
    sink.log(f"adapter={adapter.name} seed={seed}")

    try:
        dataset_info = adapter.prepare(ctx)
    except AdapterEnvironmentError as exc:
        return {"status": "FAILED", "error": str(exc)}
    sink.emit({"type": "dataset", "info": dataset_info})
    sink.log(f"dataset ready: {dataset_info.get('n_train')} train rows")

    resume_from = None
    ckpt_dir = attempt_dir / "checkpoints"
    if ckpt_dir.is_dir():
        from app.training.checkpoints import latest_checkpoint

        resume_from = latest_checkpoint(ckpt_dir)
        if resume_from is not None:
            sink.log(f"resuming from {resume_from.name}")

    def should_stop() -> str | None:
        now = time.time()
        if now - _last_heartbeat["at"] > 30:
            _last_heartbeat["at"] = now
            sink.emit({"type": "heartbeat", **_resource_snapshot()})
        return _stop_mode["mode"]

    tctx = TrainContext(strategy=strategy, workdir=attempt_dir, hyperparameters=hp,
                        seed=seed, emit=sink.emit, should_stop=should_stop,
                        resume_from=resume_from)
    try:
        summary = adapter.train(tctx, dataset_info)
    except AdapterEnvironmentError as exc:
        return {"status": "FAILED", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — report, don't crash silently
        return {"status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=20)}

    if summary.get("stopped"):
        mode = summary["stopped"]
        status = "CANCELLED" if mode == "cancel" else "PAUSED"
        sink.log(f"training {status.lower()} gracefully after checkpoint")
        return {"status": status, "result": summary}

    sink.log(f"training complete: val_acc={summary.get('val_accuracy', 0):.4f}")

    # Evaluate the final state and export a shippable bundle.
    final_ckpt = ckpt_dir / "ckpt-final.pt"
    state = adapter.load_checkpoint(final_ckpt) if final_ckpt.exists() else None
    if state is None:
        from app.training.checkpoints import latest_checkpoint

        latest = latest_checkpoint(ckpt_dir)
        state = adapter.load_checkpoint(latest) if latest else {}
    evaluation: dict[str, float] = {}
    if state:
        try:
            evaluation = adapter.evaluate(ctx, state, dataset_info)
        except AdapterEnvironmentError:
            evaluation = {}

    export_dir = attempt_dir / "export"
    export_info: dict[str, Any] = {}
    if state:
        try:
            export_info = adapter.export(ctx, state, dataset_info, export_dir)
        except AdapterEnvironmentError:
            export_info = {}

    artifact_refs = []
    model_file = export_dir / "model.pt"
    config_file = export_dir / "config.json"
    if model_file.exists() or config_file.exists():
        from app.training.artifacts import LocalArtifactStore

        data_dir = Path(os.environ.get("RUSTENWER_DATA_DIR", ""))
        if data_dir:
            store = LocalArtifactStore(data_dir / "artifacts")
            for name, path in (("model", model_file), ("config", config_file)):
                if not path.exists():
                    continue
                record = store.publish(name, path, run_id=os.environ["RUSTENWER_RUN_ID"])
                artifact_refs.append(record.model_dump())
                sink.emit({"type": "artifact", **record.model_dump()})

    sink.emit({"type": "heartbeat", **_resource_snapshot()})
    return {"status": "COMPLETED",
            "result": {**summary, "evaluation": evaluation,
                       "export": export_info, "artifacts": artifact_refs}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rustenwer training runner")
    parser.add_argument("--attempt-dir", required=True)
    args = parser.parse_args(argv)

    attempt_dir = Path(args.attempt_dir)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    _install_signal_handlers()
    sink = EventSink(attempt_dir)
    try:
        final = run_attempt(attempt_dir, sink)
    except Exception as exc:  # noqa: BLE001 — last-resort crash handler
        final = {"status": "FAILED", "error": f"runner crash: {exc}",
                 "traceback": traceback.format_exc(limit=20)}
    sink.emit({"type": "final", **final})
    sink.close()
    (attempt_dir / "final.json").write_text(json.dumps(final, indent=2))
    print(json.dumps({"status": final["status"]}), flush=True)
    return 0 if final["status"] in {"COMPLETED", "CANCELLED", "PAUSED"} else 1


if __name__ == "__main__":
    sys.exit(main())
