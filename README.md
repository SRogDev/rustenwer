# Rustenwer — Intelligence Fabrication & Discovery Platform

> **Product thesis:** describe a problem that requires intelligent behavior, and Rustenwer determines how that intelligence should be constructed, trained, evaluated, and deployed — optimizing for the **smallest, cheapest, fastest, sufficiently capable** intelligence that solves it.
>
> It is not "no-code ML". It is **Intelligence Engineering + Automated Intelligence Discovery**: it must be allowed to conclude *"you do not need a trained model"* — a deterministic algorithm, a tiny classifier, or an LLM judge are all first-class answers.

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

- **Control Plane** decides: specs, orchestration, training strategy, experiments, evaluation, discovery, deployment, observability, human approval.
- **Data Plane** computes: datasets, training, GPU jobs, checkpoints, artifacts, inference, benchmarks.
- **Intelligence Registry** is the artifact of record — an *Intelligence* is the product; a *Model* is an implementation detail.

```
rustenwer/
├── web/                    # Next.js app (projects, specs, console)
├── api/                    # FastAPI control-plane API
├── agents/                 # LangGraph runtime (supervisor + agents)
├── supabase/migrations/    # SQL migrations
├── shared/                 # Domain types, hand-synced TS ↔ Python
├── design-system/          # UI/UX design system
└── docs/                   # Decisions log, plans
```

## Status

- **Fases 0–4 done (2026-09-26/27):** domain types + RLS + FastAPI CRUD + LangGraph agents (Specification, Dataset, Training Strategy, Evaluation, Supervisor); job state machine + spec wizard; CPU PyTorch + LoRA training infra (checkpoints, per-second cost accounting); Benchmark Registry + QualityVector + model registries; immutable IntelligenceVersion + hosted inference + deploy UI; termination intelligence v1 end-to-end.
- **Fase 5:** implementation done (`/methods` catalog + detail pages, methods service layer) — final E2E verification + push pending.
- **Blocked on setup:** Supabase project + migrations + `SUPABASE_URL`/`JWT_SECRET`. CI needs a full-scope token (current token lacks the `workflows` scope).

## Stack

Next.js (App Router) + TypeScript + Tailwind + Biome · LangGraph (explicit graph state, durable execution) · FastAPI (Python) · Supabase/Postgres · PyTorch + Unsloth (LoRA/QLoRA) · DigitalOcean GPUs (provider-agnostic control plane)

## Run it locally

```bash
# API — http://localhost:8000 (docs at /docs)
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

Real local-CPU training: `pip install -r requirements-train.txt`, then enqueue a job (`POST /api/v1/training-jobs/{id}/enqueue`, `{"provider": "local"}`) and watch it at `/projects/{id}/jobs/{jobId}` — live logs, loss curve, checkpoints, artifacts, cost.

## License

Elastic License 2.0 — see [LICENSE](LICENSE).
