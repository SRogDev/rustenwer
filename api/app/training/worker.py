"""WorkerManager — queue draining, run lifecycle, cost accounting (Phase 2).

Owns the execution side of training:
  submit(job)  validate strategy -> persist run (QUEUED) -> enqueue
  _loop        claim queue items -> launch runner subprocess via ComputeProvider
  cancel()     SIGTERM (graceful) / drop from queue
  pause()      SIGUSR1 (graceful) / drop from queue; resume() re-queues same run
  retry()      new run row (attempt+1), optionally seeded with old checkpoints
  _reap        finished procs -> final status, job mirror, UsageEvent

Job submission is gated by the shared transition service (Rule 3): only a
job that may legally move to QUEUED can be submitted.

Threading: one daemon loop thread; all state mutations under a lock.
The repository stays the source of truth for run/job status.
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from shared.domain import (
    JobStatus,
    RunCost,
    RunMetrics,
    TrainingJob,
    TrainingRun,
    TrainingStrategy,
    UsageEvent,
    UsageKind,
    UsageScope,
)
from shared.services.jobs import transition

from app.training import runs as runs_model
from app.training.adapters import AdapterValidationError, get_adapter
from app.training.artifacts import LocalArtifactStore
from app.training.providers import (
    ComputeProvider,
    DigitalOceanComputeProvider,
    LocalComputeProvider,
)
from app.training.queue import FileJobQueue, JobQueue
from app.training.rates import DEFAULT_LOCAL_PROVIDER, rate_for


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class _LiveAttempt:
    run_id: UUID
    job_id: UUID
    attempt_dir: Path
    handle: Any
    provider_name: str
    stop_intent: str | None = None  # 'cancel' | 'pause' once requested


# provider name -> rate-table key (DO flavor is configurable per deployment)
DEFAULT_RATE_KEYS: dict[str, str] = {
    "local": DEFAULT_LOCAL_PROVIDER,
    "digitalocean": "digitalocean/gpu-rtx4000x1",
}


class WorkerManager:
    """Executes queued training runs. See module docstring."""

    def __init__(
        self,
        *,
        settings: Any = None,  # app.config.Settings (data_dir, training_max_workers)
        repo: Any = None,  # TrainingJobRepository (duck-typed)
        job_repo: Any = None,  # alias for repo
        usage_repo: Any = None,  # UsageRepository for cost accounting
        queue: JobQueue | None = None,
        data_dir: Path | str | None = None,
        providers: dict[str, ComputeProvider] | None = None,
        max_workers: int | None = None,
        poll_interval: float = 0.2,
        rate_keys: dict[str, str] | None = None,
        usage_sink: Callable[[UUID, UUID, float], None] | None = None,
    ) -> None:
        self._repo = job_repo if job_repo is not None else repo
        if self._repo is None:
            raise ValueError("WorkerManager needs job_repo (or repo)")
        if settings is not None:
            data_dir = data_dir if data_dir is not None else settings.data_dir
            if max_workers is None:
                max_workers = settings.training_max_workers
        if data_dir is None:
            raise ValueError("WorkerManager needs data_dir (or settings)")
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._queue = queue or FileJobQueue(self._data_dir / "queue.db")
        api_root = Path(__file__).resolve().parents[2]  # api/
        self._providers: dict[str, ComputeProvider] = providers or {
            "local": LocalComputeProvider(api_root=api_root),
            "digitalocean": DigitalOceanComputeProvider.from_env(),
        }
        self._artifact_store = LocalArtifactStore(self._data_dir / "artifacts")
        self._max_workers = max_workers if max_workers is not None else 2
        self._poll_interval = poll_interval
        self._rate_keys = {**DEFAULT_RATE_KEYS, **(rate_keys or {})}
        self._usage_repo = usage_repo
        self._usage_sink = usage_sink
        self._lock = threading.Lock()
        self._live: dict[UUID, _LiveAttempt] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._loop, name="training-worker", daemon=True
            )
            self._thread.start()

    def stop(self, *, grace: float = 5.0) -> None:
        with self._lock:
            self._running = False
            live = list(self._live.values())
            thread = self._thread
        for attempt in live:  # graceful shutdown of running attempts
            try:
                self._providers[attempt.provider_name].stop(
                    attempt.handle, graceful=True
                )
            except Exception:  # noqa: BLE001 — shutdown must not hang
                pass
        if thread is not None:
            thread.join(timeout=grace + 5)

    # -- submission ------------------------------------------------------

    def submit(
        self, job: TrainingJob, provider_name: str = "local"
    ) -> TrainingRun:
        """Validate a job's strategy and enqueue a real execution.

        Raises AdapterValidationError (bad strategy/provider), KeyError
        (unknown training_method), InvalidTransitionError (job not
        submittable, e.g. already QUEUED).
        """
        if job.strategy is None:
            raise AdapterValidationError(["job has no training strategy to execute"])
        strategy: TrainingStrategy = job.strategy
        try:
            adapter = get_adapter(strategy.training_method)
        except KeyError:
            # The "none" family means the strategy needs no model training;
            # that is a validation rejection, not an unknown-method crash.
            if (strategy.training_method or "").startswith("none"):
                raise AdapterValidationError(
                    [f"training_method {strategy.training_method!r} means no model "
                     "training is required; nothing to execute"]
                ) from None
            raise
        errors = adapter.validate(strategy)
        provider_msg = adapter.supports_provider(provider_name)
        if provider_msg:
            errors.append(provider_msg)
        provider = self._providers.get(provider_name)
        if provider is None:
            errors.append(f"unknown provider: {provider_name!r}")
        else:
            preflight = getattr(provider, "preflight", None)
            if callable(preflight):
                blocked = preflight()
                if blocked:
                    errors.append(blocked)
        if errors:
            raise AdapterValidationError(errors)

        # Lifecycle gate (Rule 3): a job with an active run cannot be submitted.
        transition(job.status, JobStatus.QUEUED)

        attempt = len(self._repo.list_runs(job.id)) + 1
        run = TrainingRun(
            id=uuid4(), job_id=job.id, attempt=attempt,
            status=JobStatus.QUEUED, provider=provider_name,
        )
        self._repo.create_run(run)
        attempt_dir = runs_model.new_attempt_dir(self._data_dir, run.id)
        (attempt_dir / "strategy.json").write_text(
            json.dumps(strategy.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        self._queue.enqueue(run.id, job.id)
        self._set_job_status(job, JobStatus.QUEUED)
        return run

    # -- control ----------------------------------------------------------

    def cancel(self, run_id: UUID) -> TrainingRun:
        run = self._require_run(run_id)
        with self._lock:
            live = self._live.get(run_id)
        if run.status == JobStatus.QUEUED and live is None:
            self._queue.remove(run_id)
            return self._finish_run(run, JobStatus.CANCELLED,
                                    error="cancelled while queued")
        if live is not None:
            live.stop_intent = "cancel"
            self._providers[live.provider_name].stop(live.handle, graceful=True)
            return self._repo.get_run(run_id)
        raise ValueError(f"run {run_id} is {run.status.value}; nothing to cancel")

    def pause(self, run_id: UUID) -> TrainingRun:
        run = self._require_run(run_id)
        with self._lock:
            live = self._live.get(run_id)
        if run.status == JobStatus.QUEUED and live is None:
            self._queue.remove(run_id)
            return self._finish_run(run, JobStatus.PAUSED,
                                    error="paused while queued")
        if live is not None:
            live.stop_intent = "pause"
            provider = self._providers[live.provider_name]
            pause_fn = getattr(provider, "pause", None)
            if callable(pause_fn):
                pause_fn(live.handle)
            else:
                provider.stop(live.handle, graceful=True)
            return self._repo.get_run(run_id)
        raise ValueError(f"run {run_id} is {run.status.value}; nothing to pause")

    def resume(self, run_id: UUID) -> TrainingRun:
        """Re-queue a PAUSED run; the runner resumes from its checkpoint."""
        run = self._require_run(run_id)
        if run.status != JobStatus.PAUSED:
            raise ValueError(
                f"run {run_id} is {run.status.value}; only PAUSED runs resume")
        attempt_dir = runs_model.latest_attempt_dir(self._data_dir, run.id)
        if attempt_dir is None or not (attempt_dir / "strategy.json").exists():
            raise ValueError(f"run {run_id} has no attempt directory to resume")
        updated = self._repo.update_run(
            run.id, {"status": JobStatus.QUEUED, "error": None})
        self._queue.enqueue(run.id, run.job_id)
        job = self._repo.get_job(run.job_id)
        if job is not None:
            self._set_job_status(job, JobStatus.QUEUED)
        assert updated is not None
        return updated

    def retry(self, run_id: UUID, from_checkpoint: bool = True) -> TrainingRun:
        """New attempt of a FAILED/CANCELLED run.

        With from_checkpoint (default), the previous attempt's checkpoints
        are copied over so training resumes instead of restarting.
        """
        run = self._require_run(run_id)
        if run.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
            raise ValueError(
                f"run {run_id} is {run.status.value}; only FAILED/CANCELLED retry")
        job = self._repo.get_job(run.job_id)
        if job is None:
            raise KeyError(f"unknown job: {run.job_id}")
        old_attempt = runs_model.latest_attempt_dir(self._data_dir, run.id)
        new_run = TrainingRun(
            id=uuid4(), job_id=run.job_id, attempt=run.attempt + 1,
            status=JobStatus.QUEUED, provider=run.provider,
        )
        self._repo.create_run(new_run)
        new_dir = runs_model.new_attempt_dir(self._data_dir, new_run.id)
        if old_attempt is not None:
            src_strategy = old_attempt / "strategy.json"
            if src_strategy.exists():
                shutil.copy2(src_strategy, new_dir / "strategy.json")
            src_ckpt = old_attempt / "checkpoints"
            if from_checkpoint and src_ckpt.is_dir():
                shutil.copytree(src_ckpt, new_dir / "checkpoints")
        self._queue.enqueue(new_run.id, new_run.job_id)
        self._set_job_status(job, JobStatus.QUEUED)
        return new_run

    # -- reads ------------------------------------------------------------

    def get_run(self, run_id: UUID) -> TrainingRun:
        return self._require_run(run_id)

    def attempt_dir(self, run_id: UUID) -> Path:
        """Latest attempt dir for a run, or the would-be first one.

        Never creates anything — callers decide (the SSE test writes
        logs.txt into it directly).
        """
        latest = runs_model.latest_attempt_dir(self._data_dir, run_id)
        if latest is not None:
            return latest
        return runs_model.runs_root(self._data_dir) / str(run_id) / "attempt-1"

    def live_info(self, run_id: UUID) -> dict[str, Any] | None:
        """Live execution info (pid etc.), or None when not running."""
        with self._lock:
            attempt = self._live.get(run_id)
        if attempt is None:
            return None
        return {
            "pid": attempt.handle.pid,
            "provider": attempt.provider_name,
            "attempt_dir": str(attempt.attempt_dir),
        }

    def get_logs(self, run_id: UUID, tail: int = 300) -> list[dict[str, str]]:
        self._require_run(run_id)
        attempt = runs_model.latest_attempt_dir(self._data_dir, run_id)
        if attempt is None:
            return []
        return runs_model.read_logs(attempt, tail=tail)

    def get_logs_text(self, run_id: UUID, tail: int = 100_000) -> str:
        """Log lines joined as text (handy for assertions and debugging)."""
        return "\n".join(e["line"] for e in self.get_logs(run_id, tail=tail))

    def get_metrics(self, run_id: UUID) -> RunMetrics:
        run = self._require_run(run_id)
        attempt = runs_model.latest_attempt_dir(self._data_dir, run_id)
        if attempt is None:
            return RunMetrics(run_id=run.id, series=[], latest={})
        return runs_model.read_metrics(attempt, run.id)

    def get_checkpoints(self, run_id: UUID) -> list:
        self._require_run(run_id)
        attempt = runs_model.latest_attempt_dir(self._data_dir, run_id)
        if attempt is None:
            return []
        return runs_model.read_checkpoints(attempt)

    def get_artifacts(self, run_id: UUID) -> list:
        """Artifact records emitted by this run (from its events)."""
        self._require_run(run_id)
        attempt = runs_model.latest_attempt_dir(self._data_dir, run_id)
        if attempt is None:
            return []
        from shared.domain import ArtifactRecord

        records = []
        for e in runs_model.iter_events(attempt):
            if e.get("type") == "artifact":
                try:
                    records.append(ArtifactRecord(
                        name=str(e["name"]), version=int(e["version"]),
                        sha256=str(e["sha256"]), bytes=int(e["bytes"]),
                        created_at=str(e.get("t", ""))))
                except (KeyError, ValueError, TypeError):
                    continue
        return records

    def get_cost(self, run_id: UUID) -> RunCost:
        run = self._require_run(run_id)
        attempt = runs_model.latest_attempt_dir(self._data_dir, run_id)
        rate = rate_for(self._rate_keys.get(run.provider, ""))
        if attempt is None:
            return RunCost(run_id=run.id, provider=run.provider, seconds=0.0,
                           usd=0.0, rate_usd_per_hour=rate)
        return runs_model.read_cost(attempt, run.id, run.provider, rate)

    # -- internals ----------------------------------------------------------

    def _require_run(self, run_id: UUID) -> TrainingRun:
        run = self._repo.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown run: {run_id}")
        return run

    def _set_job_status(self, job: TrainingJob, status: JobStatus) -> None:
        # Execution ground truth: the manager reports what actually happened.
        # User-initiated transitions still go through the transition service
        # on the /transition endpoint; submit() is gated by it above.
        self._repo.update_job(job.id, {"status": status})

    def _finish_run(
        self, run: TrainingRun, status: JobStatus, error: str | None = None
    ) -> TrainingRun:
        updated = self._repo.update_run(
            run.id, {"status": status, "error": error, "finished_at": _utc_now()}
        )
        job = self._repo.get_job(run.job_id)
        if job is not None:
            self._set_job_status(job, status)
        assert updated is not None
        return updated

    def _loop(self) -> None:
        while True:
            with self._lock:
                running = self._running
            if not running:
                return
            try:
                self._reap()
                with self._lock:
                    free = self._max_workers - len(self._live)
                while free > 0:
                    item = self._queue.claim()
                    if item is None:
                        break
                    self._launch(item)
                    free -= 1
            except Exception:  # noqa: BLE001 — the loop must never die
                time.sleep(1.0)
            time.sleep(self._poll_interval)

    def _launch(self, item: Any) -> None:
        run = self._repo.get_run(item.run_id)
        if run is None or run.status != JobStatus.QUEUED:
            return
        attempt_dir = runs_model.latest_attempt_dir(self._data_dir, run.id)
        if attempt_dir is None:
            self._finish_run(run, JobStatus.FAILED, error="attempt dir missing")
            return
        provider = self._providers.get(run.provider)
        if provider is None:
            self._finish_run(run, JobStatus.FAILED,
                             error=f"unknown provider {run.provider!r}")
            return
        self._repo.update_run(run.id, {"status": JobStatus.RUNNING,
                                       "started_at": _utc_now()})
        job = self._repo.get_job(run.job_id)
        if job is not None:
            self._set_job_status(job, JobStatus.RUNNING)
        command = [sys.executable, "-m", "app.training.runner",
                   "--attempt-dir", str(attempt_dir)]
        try:
            handle = provider.start(
                run_id=run.id, workdir=attempt_dir, command=command,
                env={
                    "RUSTENWER_DATA_DIR": str(self._data_dir),
                    "RUSTENWER_RUN_ID": str(run.id),
                    "RUSTENWER_ATTEMPT": str(run.attempt),
                },
            )
        except Exception as exc:  # noqa: BLE001 — a failed launch must not orphan the run
            self._finish_run(run, JobStatus.FAILED, error=f"launch failed: {exc}")
            return
        with self._lock:
            self._live[run.id] = _LiveAttempt(
                run_id=run.id, job_id=run.job_id, attempt_dir=attempt_dir,
                handle=handle, provider_name=run.provider)

    def _reap(self) -> None:
        with self._lock:
            live = list(self._live.values())
        for attempt in live:
            provider = self._providers[attempt.provider_name]
            try:
                provider.fetch_events(attempt.handle,
                                      attempt.attempt_dir / "events.jsonl")
                code = provider.poll(attempt.handle)
            except Exception as exc:  # noqa: BLE001 — a sick proc must not jam the loop
                code = 1
                self._note_poll_error(attempt, exc)
            if code is None:
                continue
            with self._lock:
                self._live.pop(attempt.run_id, None)
            run = self._repo.get_run(attempt.run_id)
            if run is None:
                continue
            final = runs_model.read_final(attempt.attempt_dir) or {
                "status": "FAILED",
                "error": f"runner exited (code {code}) without a final event",
            }
            status = self._as_job_status(str(final.get("status", "FAILED")))
            if attempt.stop_intent == "cancel" and status not in (
                    JobStatus.CANCELLED, JobStatus.PAUSED):
                status, final = JobStatus.CANCELLED, {**final, "status": "CANCELLED"}
            elif attempt.stop_intent == "pause" and status not in (
                    JobStatus.CANCELLED, JobStatus.PAUSED):
                status, final = JobStatus.PAUSED, {**final, "status": "PAUSED"}
            finished = self._finish_run(run, status, error=final.get("error"))
            self._account_cost(finished, attempt)

    def _note_poll_error(self, attempt: _LiveAttempt, exc: Exception) -> None:
        try:
            with open(attempt.attempt_dir / "events.jsonl", "a",
                      encoding="utf-8") as fh:
                fh.write(json.dumps({"t": _utc_now(), "type": "log",
                                     "line": f"poll error: {exc}"}) + "\n")
        except OSError:
            pass

    @staticmethod
    def _as_job_status(raw: str) -> JobStatus:
        try:
            return JobStatus(raw)
        except ValueError:
            return JobStatus.FAILED

    def _account_cost(self, run: TrainingRun, attempt: _LiveAttempt) -> None:
        """Record wall-time cost as a Phase-1 usage event (plan §45)."""
        wall = runs_model.attempt_wall_seconds(attempt.attempt_dir)
        if wall is None:
            return
        job = self._repo.get_job(run.job_id)
        if job is None:
            return
        rate = rate_for(self._rate_keys.get(run.provider, ""))
        usd = wall / 3600 * rate
        if self._usage_sink is not None:
            try:
                self._usage_sink(run.job_id, run.id, usd)
            except Exception:  # noqa: BLE001 — billing must not break reaping
                pass
        if self._usage_repo is not None:
            event = UsageEvent(
                id=uuid4(),
                project_id=job.project_id,
                scope=UsageScope.TRAINING_JOB,
                scope_id=job.id,
                kind=UsageKind.TRAINING,
                quantity=wall,
                unit="seconds",
                cost_usd=usd,
                recorded_at=_utc_now(),
            )
            try:
                self._usage_repo.record_event(event)
            except Exception:  # noqa: BLE001 — billing must not break reaping
                pass


# --------------------------------------------------------------------------
# Process-wide manager (FastAPI dependency)
# --------------------------------------------------------------------------

_default_manager: WorkerManager | None = None
_manager_lock = threading.Lock()


def get_worker_manager() -> WorkerManager:
    """Dependency hook: the process-wide manager (tests build their own)."""
    global _default_manager
    with _manager_lock:
        if _default_manager is None:
            from app.config import get_settings

            settings = get_settings()
            # Imported lazily to avoid a hard dependency cycle at module load.
            from app.training.router import get_training_job_repository

            _default_manager = WorkerManager(
                settings=settings,
                job_repo=get_training_job_repository(),
                max_workers=settings.training_max_workers,
            )
        return _default_manager
