# Rustenwer — Decisions Log

Durable decisions made during the build. New entries go on top.

## 2026-09-26 — Phase 1 integration (coordinator)

- **In-memory repos kept for Phase 1** (no Supabase credentials exist);
  migrations 001+002 are the canonical schema, swap is a later job.
- **Contract fix**: `TrainingStrategy.architecture` is a structured
  `dict`/`Record`, not a string (plan §9 treats architectures as composable
  structures).
- **Spec auto-detect**: `POST /specs` accepts omitting
  `intelligence_primitive` → keyword-based `detect_primitive()` in
  `shared/services/diagnosis.py` (falls back to `decision`); the Diagnostic
  Agent refines it at `/diagnose`.
- **Baseline notes**: `BaselineReport` has no `recommendation` field — the
  unusable-labels note lives in each baseline's `description` and in
  `EvaluationResults.recommendation`. `propose_strategy`'s `dataset_ref`
  carries the dataset *version UUID* (consistent with
  `Evaluation.dataset_version_id`).
- **Deployment cancel** = transition to `ARCHIVED` from any state
  (`DeploymentStatus` has no CANCELLED).
- Verified: API 84/84 pytest, ruff clean; agents 23/23 pytest + `demo.py`
  end-to-end green; `npm run build` + `tsc` + `biome` green; live-server
  e2e (spec→diagnose→approve→dataset→evaluate→job lifecycle→usage→demo)
  all 200s. Migration 002 never executed against a live DB (no credentials)
  — syntax sanity-checked only.

## 2026-09-26 — License: MIT → Elastic License 2.0

- **Roger's decision: Elastic License 2.0** (source-available, not OSI open
  source). The initial MIT license is replaced: anyone may view and use the
  code, including internal commercial use, but may NOT provide it to third
  parties as a hosted/managed service competing with Rustenwer. Rationale:
  Roger intends Rustenwer as a real product/business and wants to keep the
  SaaS lane exclusive while staying source-available. Root README license
  section updated; `LICENSE` now carries the full ELv2 text.

## 2026-09-26 — Phase 0 kickoff

- **Repo is public** (Roger's choice). `SRogDev/rustenwer`.
- **Brand primary: platinum `#E5E4E2`** (Roger's requirement). The ui-ux-pro-max
  design-system search suggested AI-purple `#7C3AED`; we override the primary
  token with platinum and keep dark charcoal foregrounds for 4.5:1 contrast.
- **Auth in Phase 0 is a clearly-marked stub**: the API accepts any well-formed
  `Bearer` token and injects a stub identity. No Supabase project exists yet,
  so real JWT verification cannot be wired; it lands in Phase 1 when Roger
  creates the project and supplies `SUPABASE_URL`/`SUPABASE_JWT_SECRET`.
- **Projects storage in Phase 0 is in-memory** behind a repository interface,
  seeded from the same `Project` domain shape as the migration. The Supabase
  schema (migration 001) is the canonical model; the API swaps to it in
  Phase 1. No fake persistence: the README says plainly what is and isn't wired.
- **Monorepo**: `web/` (Next.js), `api/` (FastAPI), `agents/` (LangGraph),
  `supabase/migrations/`, `shared/` (hand-synced TS/Python domain types).
- **UI stack**: Next.js App Router, TypeScript strict, Tailwind, Biome
  (Roger prefers Biome over ESLint/Prettier). React 19.
- **Python stack**: per-component venvs (`api/.venv`, `agents/.venv`); system
  python is PEP 668 externally-managed — never `pip install --user`.
- **LangGraph in Phase 0 is a skeleton only**: explicit `SupervisorState`,
  placeholder nodes, no real agents (plan rule: do not implement Phase 1
  agents in Phase 0).

## Phase 2 — Training Infrastructure (2026-09-27)

- **Real local training, honest cloud story.** The `local` compute provider
  trains for real (PyTorch CPU subprocess). The `digitalocean` provider is
  code-complete (API v2 droplet create → cloud-init → SSH/SCP → destroy) but
  has never run: no `DO_TOKEN`, no GPU budget. It refuses at enqueue with a
  409 naming `DO_TOKEN`, before any billing is possible. The API never
  pretends a cloud run happened.
- **QLoRA is a guarded path, not a stub.** `QLoRAAdapter` contains the real
  4-bit + LoRA training code, but `validate()` refuses CPU execution and
  missing unsloth/bitsandbytes with explicit errors. A guarded real path
  beats a fake "success".
- **Subprocess isolation.** Each attempt runs as `python -m
  app.training.runner` in its own process group; the API only tails
  `events.jsonl`. A crashed/OOM runner cannot take down the API, and a
  brutal SIGKILL is detected as FAILED (no final event) rather than
  misreported.
- **Launch failures must not orphan runs.** A `NameError` in `_launch`
  once left a run stuck RUNNING forever (the loop's blanket except
  swallowed it after the queue item was claimed). `_launch` now catches
  broad `Exception` and marks the run FAILED with the error.
- **Pause checkpoints label the last completed epoch.** A mid-epoch pause
  used to label the checkpoint with the in-progress epoch, so resume
  skipped a full epoch of the schedule. Now it stores `epoch - 1` and the
  resume re-runs the interrupted epoch from the saved weights/optimizer.
- **Checkpoints are atomic** (temp file + fsync + `os.replace`); **artifacts
  are immutable and content-verified** (SHA-256, versioned, `os.replace`
  publish). Resume trusts only checksummed state.
- **Enqueue validation is all 409.** Missing/unknown/rejected strategies,
  bad provider credentials, and illegal job transitions all return 409
  (the job/state is at fault, not the request syntax).
- **Logs: `text/plain` for fetch, SSE for follow.** `GET .../logs` returns
  one `t line` per line; `?follow=true` streams `data:` JSON chunks ending
  in `{"done": true}` (EventSource can't send Authorization headers, so the
  UI reads the stream with fetch + ReadableStream).
- **Cost = wall-time × provider rate, per second.** `RunCost` is computed
  from attempt wall time; a `UsageEvent(TRAINING)` is recorded per
  completed attempt. DigitalOcean indicative rates (2026-09-27, $/hr):
  RTX4000 0.76, L40s/RTX6000 1.57, MI300X 2.59, MI325X 3.80, H100 4.41,
  H200 4.47 — per-second billing with a minimum charge; powered-off GPU
  droplets still bill, so teardown destroys them.
- **Runtime data is git-ignored** under `RUSTENWER_DATA_DIR` (default
  `api/data/`): queue DB, run attempts, checkpoints, artifact store.
- **Synthetic data for the real adapters is a balanced ring task**
  (Rayleigh median threshold ≈ 1.1774) — the first imbalanced task let the
  model collapse to the majority class. SGD needs momentum 0.9 to learn it;
  plain SGD stalls. (A lesson about task design, not just code.)
