# Rustenwer — Intelligence Fabrication & Discovery Platform

> **Product thesis:** Rustenwer is a platform for *fabricating intelligence*.
> Describe a problem that requires intelligent behavior, and Rustenwer determines
> how that intelligence should be constructed, trained, evaluated, and deployed —
> optimizing for **the smallest, cheapest, fastest, and sufficiently capable
> intelligence that solves the required problem**.
>
> It is not "no-code ML". It is **Intelligence Engineering + Automated
> Intelligence Discovery**: it must be allowed to conclude *"you do not need a
> trained model"* — a deterministic algorithm, a tiny classifier, or an LLM
> judge are all first-class answers.

## Architecture

```
                    RUSTENWER
                        │
                ┌───────┴────────┐
                │                │
          CONTROL PLANE       DATA PLANE
                │                │
         Agents / Harness    Compute / GPUs
         Orchestration       Training workers
         Planning             Inference
         Evaluation           Storage
         Discovery            Artifacts
                │
                └───────┬────────┘
                        │
                  Intelligence
                     Registry
```

- **Control Plane** decides what should happen: specs, orchestration, training
  strategy, experiments, evaluation, discovery, RSI, deployment, observability,
  human approval.
- **Data Plane** does the expensive computation: datasets, training, GPU jobs,
  checkpoints, artifacts, inference, benchmarks.
- **Intelligence Registry** is the artifact of record. A *Model* is an
  implementation detail; an *Intelligence* is the product.

### The abstraction stack

```
PROBLEM → INTELLIGENCE DESIGN → INTELLIGENCE DISCOVERY →
INTELLIGENCE FABRICATION → INTELLIGENCE EVALUATION →
INTELLIGENCE DEPLOYMENT → INTELLIGENCE EVOLUTION
```

## Stack (Phase 0)

| Layer        | Tech                                    |
|--------------|-----------------------------------------|
| Frontend     | Next.js (App Router) + TypeScript + Tailwind + Biome |
| Orchestration| LangGraph (explicit graph state, durable execution) |
| Backend      | FastAPI (Python)                        |
| Database     | Supabase / PostgreSQL (canonical source of truth) |
| Training     | PyTorch + Unsloth, LoRA/QLoRA (Phase 2+) |
| Compute      | DigitalOcean GPUs, provider-agnostic control plane |

Brand primary: **platinum `#E5E4E2`**.

## Monorepo layout

```
rustenwer/
├── web/                    # Next.js app (projects, specs, console)
├── api/                    # FastAPI control-plane API
├── agents/                 # LangGraph runtime (supervisor + agents)
├── supabase/migrations/    # SQL migrations (001 = organizations/users/projects)
├── shared/                 # Domain types, hand-synced TS ↔ Python (see shared/README.md)
├── design-system/          # ui-ux-pro-max design system (MASTER.md)
└── docs/                   # Decisions log, plans
```

## Run it locally (Phase 0)

Prereqs: Node 20+, Python 3.12+.

```bash
# API — http://localhost:8000  (docs at /docs)
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit if needed
uvicorn app.main:app --reload

# Web — http://localhost:3000
cd web
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

### Real training locally (Phase 2)

The base API requirements stay torch-free; training needs the extras:

```bash
cd api
source .venv/bin/activate
pip install -r requirements-train.txt   # torch CPU + numpy
```

Then enqueue a job (`POST /api/v1/training-jobs/{id}/enqueue`,
`{"provider": "local"}`): a worker thread claims it from the SQLite queue
and trains in a real subprocess (`python -m app.training.runner`). Watch
it at `/projects/{id}/jobs/{jobId}` — live logs, loss curve, checkpoints,
artifacts, cost. Runtime data (queue DB, runs, artifacts) lives under
`RUSTENWER_DATA_DIR` (default `api/data/`, git-ignored).

DigitalOcean GPU training is code-complete but credential-blocked: without
`DO_TOKEN` (+ `DO_SSH_KEY_IDS` / `DO_SSH_PRIVATE_KEY`) enqueueing with
`"provider": "digitalocean"` is refused with 409 and nothing is billed.
QLoRA likewise refuses on CPU — it needs CUDA plus unsloth/bitsandbytes.

Phase 1 is intentionally honest about what's real: the API serves everything
from in-memory stores behind repository interfaces (Supabase wiring still
lands once a Supabase project exists — migrations 001+002 are the canonical
schema), auth accepts any well-formed Bearer token with a stub identity,
and real GPU training execution waits for Phase 2. The LangGraph agents run
on deterministic fixtures (no LLM keys exist). The web UI calls the real API
and falls back to mock data only when the API is unreachable.

## Phase roadmap

- [x] **Phase 0 — Repository Foundation**: Next.js app, FastAPI backend,
  Supabase schema (organizations/users/projects), LangGraph skeleton, shared
  types, auth stub, project model, logging, config.
- [x] **Phase 1 — Core MVP** (2026-09-26): IntelligenceSpec CRUD + diagnosis
  (incl. the "no ML needed" conclusion), datasets + versioning + validation
  (schema/leakage/imbalance/splits), training-job lifecycle
  (CREATED→…→COMPLETED, pausable/cancellable), baselines-first evaluation
  (majority/keyword/deterministic, bar_to_beat), model registry, deployments,
  usage/cost tracking, demo fixture endpoint — plus real LangGraph nodes
  (Specification, Dataset, Training Strategy, Evaluation, Supervisor) and
  the spec wizard / datasets / dashboard UI in platinum.
- [x] **Phase 2 — Training Infrastructure** (2026-09-27): real local-CPU
  training that actually runs — SQLite persistent queue, subprocess workers,
  real PyTorch classifier + LoRA adapters (QLoRA code-complete but honestly
  blocked: needs CUDA + unsloth/bitsandbytes), atomic checkpoints with
  pause/resume/retry-from-checkpoint, immutable versioned artifact store
  (SHA-256), JSONL event stream (logs/metrics/heartbeats) with SSE tail,
  graceful cancel (SIGTERM) vs brutal kill detection, per-second cost
  accounting, `ComputeProvider` abstraction (working `local` provider +
  code-complete `digitalocean` GPU-droplet provider, refused without
  `DO_TOKEN` — never live-tested), and the training-job detail UI
  (run controls, live log viewer, SVG loss curve, checkpoints/artifacts/cost
  panels). 84+23 Phase-1 tests still green; ~60 new execution tests.
- [x] **Phase 3 — Evaluation & Registry** (2026-09-27): independent
  evaluation runner (benchmarks incl. seeded `termination` + `ring`,
  subject-independent scoring per Rule 11, cancellable runs, quality
  vectors with hand-verified ECE, Pareto-strict `beats_bar`, no global
  weights — priority-lexicographic ranking), baseline/incumbent comparison
  reports, model registry with immutable versions + lineage diff, first-class
  Intelligence registry (versions, resolved component lineage, honest 501
  promote until Phase 6), per-scope cost rollups (`UsageScope.EVALUATION`
  added), registry/evaluation/comparison/cost-rollup UI in platinum theme.
  Live E2E 30/30: trained a real 2-feature MLP → registered with lineage →
  ring-benchmark quality vector (task 0.975, cal 0.894) → beat all baselines
  in comparison → intelligence v1 pinning the model → evaluation costs in
  rollups. 218+23 tests green.
- [x] **Phase 4 — Intelligence Abstraction** (2026-09-27): Intelligence as
  first-class executable artifact — validated immutable architecture
  snapshots (8 component kinds), version diff with reviewer notes,
  hosted inference pipeline (input-schema validation, deterministic +
  real-torch model components, primitive-shaped machine outputs),
  `InferenceProvider` abstraction (hosted functional; external/GPU honest
  501s), deployments serving an Intelligence version (back-compat
  auto-wraps bare model deployments), per-inference usage events, and
  the deployment UI (architecture diagram, diff viewer, deploy flow,
  endpoint + curl, live infer console). Live E2E 21/21: deterministic
  termination v1 (`progress_score <= 0.21 → stop`) deployed, activated,
  and invoked over HTTP. 242+23 tests green; web tsc/Biome/build green.
  Full record: docs/PHASE4.md (includes the Spanish deep-dive lesson).
- [ ] **Phase 5 — Training Method Knowledge**: method registry + adapters.
- [ ] **Phase 6 — Candidate Experiment Engine**: experiments, search
  strategies, promotion/rollback.
- [ ] **Phase 7 — Intelligence Discovery**: architecture agent, discovery
  agent, negative search, experiment memory.
- [ ] **Phase 8 — RSI Harness**: isolated self-improvement of prompts/config/
  strategy with safety boundaries.
- [ ] **Phase 9 — Advanced RSI**: editable control flow, tools, memory.
- [ ] **Phase 10 — Replay / Dream Discovery**: offline discovery from
  accumulated experiment histories.

## Critical architectural rules

1. Never couple Intelligence to one model architecture.
2. Never assume fine-tuning is the correct solution.
3. Never let the LLM do deterministic infrastructure work a service can do.
4. Every expensive operation is observable and cancellable.
5. Every candidate is reproducible. 6. Every discovery has lineage.
7. Failed experiments are data. 8. Negative search is part of discovery.
9. Baselines precede expensive training. 10. Optimize intelligence-per-dollar.
11. Evaluation is independent from training. 12. RSI cannot touch the immutable
    security/control boundary. 13. The platform may conclude no ML is needed.
14. The model is an implementation detail; the Intelligence is the product.

## License

**Elastic License 2.0** — see [LICENSE](./LICENSE). Source-available, not
OSI open source: you may view, use, copy, and modify the code (including
for internal commercial use), but you may **not** offer it to third parties
as a hosted or managed service that competes with Rustenwer.
