# Phase 2 — Training Infrastructure (plan)

**Goal:** real training execution. A `TrainingStrategy` (decided by the Strategy Agent in Phase 1) goes in; a trained artifact, metrics, logs, checkpoints, and cost come out. Plan §61 Phase 2 + Rule 3 (agents decide, services execute) + Rule 4 (every expensive op observable + cancellable).

## Architecture

```
POST /training-jobs/{id}/enqueue
        │  1. adapter = ADAPTERS[strategy.training_method]; errors = adapter.validate(strategy) → 409 if any
        │  2. create TrainingRun(attempt=n+1); job CREATED|FAILED → QUEUED
        ▼
FileJobQueue (SQLite, data/queue.db) ──persistent──▶ WorkerManager (monitor thread)
        │  claim → job QUEUED → RUNNING
        ▼
ComputeProvider.launch(run_ctx) → WorkerHandle
  • LocalExecutor: subprocess `sys.executable -m api.app.training.runner --run-dir …`
  • DigitalOceanProvider: provision GPU droplet + ssh-run (code-complete, DO_TOKEN-blocked)
        │
        ▼
Runner (subprocess): adapter.prepare() → adapter.train(ctx) emitting JSONL events
  events: log | metric{step,value} | heartbeat{cpu,mem} | checkpoint{epoch} | artifact{name,version} | status{state} | cost{seconds,usd}
  SIGTERM → graceful stop: final checkpoint + status{paused|cancelled}
        │
        ▼
Manager on exit: job → COMPLETED|FAILED|CANCELLED|PAUSED; usage event (wall-time × rate); artifacts registered
```

## Modules (`api/app/training/` package; `training.py` → `training/__init__.py` re-exporting router bits)

| File | Contents |
|---|---|
| `adapters.py` | `TrainingMethodAdapter` Protocol (`validate/prepare/estimate/train/save_checkpoint/load_checkpoint/evaluate/export`); `ADAPTERS` registry; `ClassifierAdapter` (real torch MLP, CPU); `LoRAAdapter` (real LoRA on tiny torch base, CPU); `QLoRAAdapter` (real Unsloth path import-guarded; raises `AdapterEnvironmentError` on CPU-only) |
| `queue.py` | `JobQueue` Protocol + `FileJobQueue` (SQLite; `enqueue/claim/remove/pending`; atomic claim) |
| `providers.py` | `ComputeProvider` Protocol; `LocalExecutor` (subprocess); `DigitalOceanProvider` (DO API v2 via urllib; provision/teardown/ssh-run; `DO_TOKEN`-blocked); `ProviderCredentialsError` |
| `worker.py` | `WorkerManager` (submit/cancel/pause/resume/retry; heartbeat timeout; cost → usage repo); `get_worker_manager()` dep hook |
| `runner.py` | `python -m api.app.training.runner` subprocess entrypoint; signal handling; synthetic seeded dataset; event emission |
| `checkpoints.py` | atomic `save_checkpoint` (tmp + os.replace), `load_checkpoint`, `latest_checkpoint(run_dir)`, registry listing |
| `artifacts.py` | `ArtifactStore` Protocol + `LocalArtifactStore` (immutable, versioned, sha256-verified) |
| `rates.py` | `PROVIDER_RATES_USD_PER_HOUR` (`local-cpu`, DO GPU slugs as indicative constants) |
| `router.py` | existing job CRUD + new execution endpoints (see contract) |

## API contract (new endpoints, all bearer-auth, org-scoped)

- `POST /api/v1/training-jobs/{job_id}/enqueue` `{provider?, hyperparameters?, resume_from_checkpoint_id?}` → `201 TrainingRun`; `409` (no/invalid strategy, bad state, qlora-on-local)
- `GET /api/v1/training-jobs/{job_id}/runs/{run_id}` → `TrainingRun`
- `POST /api/v1/training-jobs/{job_id}/runs/{run_id}/cancel|pause` → `TrainingRun`
- `POST /api/v1/training-jobs/{job_id}/runs/{run_id}/resume` → `TrainingRun`
- `POST /api/v1/training-jobs/{job_id}/runs/{run_id}/retry` `{from_checkpoint?}` → `201 TrainingRun`
- `GET .../logs?tail=300&follow=true` → SSE (`text/event-stream`); `follow=false` → `text/plain`
- `GET .../metrics` → `RunMetrics`; `GET .../checkpoints` → `CheckpointInfo[]`; `GET .../artifacts` → `ArtifactRecord[]`; `GET .../cost` → `RunCost`

## Data layout (`RUSTENWER_DATA_DIR`, default `api/data/`; gitignored)

`queue.db`, `runs/{run_id}/attempt-{n}/{config.json, events.jsonl, logs.txt, checkpoints/ckpt-*.pt, artifacts/}`, `artifacts/{name}/v{n}/payload` + `registry.jsonl`

## Tests (TDD RED→GREEN)

`test_exec_queue.py` (persistence across reopen, FIFO, atomic claim), `test_exec_checkpoints.py` (atomicity, resume), `test_exec_artifacts.py` (versioning, immutability, sha verify), `test_exec_adapters.py` (validate errors, estimate, classifier trains → loss decreases, resume continues, qlora CPU error), `test_exec_manager.py` (e2e: enqueue→COMPLETED with real artifacts/metrics/logs/cost; cancel→checkpoint; pause/resume; retry new attempt), `test_exec_endpoints.py` (HTTP surface, 409s, SSE). Keep 84+23 green.

## Web (delegated)

Job detail page `web/app/projects/[id]/jobs/[jobId]/page.tsx`: status, strategy summary, SSE log viewer, SVG loss chart, checkpoints, artifacts, cost, enqueue/pause/resume/cancel/retry buttons; platinum theme; build green.

## Explicitly NOT in Phase 2

Supabase swap (still in-memory), real LLM calls, multi-GPU, DO execution without token, Phase-3 registries.
