# Rustenwer — Phase 2 completion record & Phase 3 handoff

> Completed 2026-09-27. Phase 2 = Training Infrastructure: real training
> that actually runs, with honest boundaries where it can't.

## What was built

**Backend** (`api/app/training/` — package, was a single `training.py`):
- `queue.py` — SQLite persistent queue, atomic `BEGIN IMMEDIATE` claim.
- `runner.py` — the training subprocess (`python -m app.training.runner`):
  JSONL `events.jsonl` (started/log/metric/heartbeat/checkpoint/artifact/
  final) + `logs.txt` for the SSE tail; SIGTERM → graceful cancel,
  SIGUSR1 → graceful pause.
- `worker.py` — `WorkerManager`: drain loop thread, launch/reap,
  submit/cancel/pause/resume/retry, cost accounting, live PID info.
- `adapters.py` — real PyTorch classifier + real LoRA (frozen base,
  trainable A/B, CPU-capable); QLoRA path is real code but guarded —
  refuses CPU / missing unsloth+bitsandbytes with explicit errors.
- `checkpoints.py` — atomic torch checkpoints (temp+fsync+`os.replace`).
- `artifacts.py` — immutable versioned artifact store, SHA-256 verified.
- `providers.py` — `ComputeProvider`: working `local` subprocess executor;
  `digitalocean` GPU-droplet provider, code-complete, credential-blocked.
- `rates.py` — per-second provider rate table (indicative DO GPU prices).
- `runs.py` — metrics/logs/checkpoints/artifacts/cost assembly.
- `router.py` — Phase 2 HTTP endpoints (see `shared/README.md` contract).

**Web** (`web/app/projects/[id]/jobs/[jobId]/`, `web/components/Run*`):
job-detail page with run controls, live SSE log viewer, SVG loss curve,
checkpoints / artifacts / cost panels, platinum theme. `tsc`, Biome,
`next build` green.

**Tests**: `api/tests/test_exec_*.py` — queue, checkpoints, artifacts,
adapters (real torch), manager (real subprocess lifecycle: complete,
cancel-checkpoint, pause/resume, retry-from-checkpoint, SIGKILL→FAILED),
endpoints (409 validation matrix, SSE unit test, full HTTP lifecycle).

## How to run real training locally

```bash
cd api && source .venv/bin/activate
pip install -r requirements-train.txt   # torch CPU + numpy (base reqs stay torch-free)
uvicorn app.main:app                    # lifespan starts the worker
```
Enqueue: `POST /api/v1/training-jobs/{id}/enqueue {"provider": "local"}`.
Data under `RUSTENWER_DATA_DIR` (default `api/data/`, git-ignored).

## Honestly blocked (not tested, not claimed)

- **DigitalOcean**: no `DO_TOKEN`, no GPU budget — the provider has never
  provisioned a droplet. Refuses at enqueue (409, names `DO_TOKEN`).
- **QLoRA**: needs CUDA + unsloth + bitsandbytes; refuses on this CPU box.
- Auth is still the Phase 0 stub; Supabase wiring still pending Roger.

## Contracts the next phase must respect

- Enqueue validation → **409** (not 422) for strategy/provider/state faults.
- `GET .../logs` → `text/plain` (`t line` per line); `?follow=true` → SSE
  `data:` JSON `{"t","line"}` chunks ending `{"done": true}`.
- Retry: `POST .../retry {"from_checkpoint": true}` → 201, new attempt row.
- `TrainingRun.provider` (default `"local"`), `TrainingRun.error`.
- Pause checkpoints label the **last completed epoch** (`epoch - 1`);
  resume re-runs the interrupted epoch. Don't "fix" this back.
- `_launch` failures mark the run FAILED — never leave it stuck RUNNING.

## Phase 3 (Evaluation & Registry) starting points

- Evaluation runner can reuse the runner/worker pattern: new adapter kind
  (`evaluator`), same queue + events + artifacts flow.
- Model registry: publish from the artifact store's `model` artifact;
  `Model`/`ModelVersion` rows already exist (Phase 1 migration 002).
- Cost accounting exists per-run (`RunCost`, `UsageEvent(TRAINING)`) —
  Phase 3 aggregates it per project/model.
- The DO provider + QLoRA light up the day Roger supplies credentials/GPU;
  no code changes needed, only env vars and a live test.
