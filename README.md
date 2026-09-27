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

Phase 0 is intentionally honest about what's real: the API serves projects from
an in-memory store behind a repository interface (Supabase wiring lands in
Phase 1), and auth accepts any well-formed Bearer token with a stub identity
until a Supabase project exists. The web UI calls the real API and falls back
to mock data only when the API is unreachable.

## Phase roadmap

- [x] **Phase 0 — Repository Foundation**: Next.js app, FastAPI backend,
  Supabase schema (organizations/users/projects), LangGraph skeleton, shared
  types, auth stub, project model, logging, config.
- [ ] **Phase 1 — Core MVP**: projects, IntelligenceSpec, datasets, training
  jobs, models, evaluations, deployments + Specification/Dataset/Training/
  Evaluation/Supervisor agents.
- [ ] **Phase 2 — Training Infrastructure**: GPU provisioning, job queue,
  workers, LoRA/QLoRA, checkpointing, artifacts.
- [ ] **Phase 3 — Evaluation & Registry**: benchmarks, evaluation runner,
  model + intelligence registries, cost accounting.
- [ ] **Phase 4 — Intelligence Abstraction**: Intelligence as first-class
  artifact, deploy an Intelligence (not a Model).
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
