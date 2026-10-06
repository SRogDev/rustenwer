# rustenwer — Project Brief

> Full project context in one file. Hand this to ANOTHER AI (GPT, etc.) for planning
> and ideation, then bring the refined specs back. Keep this file accurate — it is the handoff doc.
> For the current timeline see `STATUS.md`. For how to work in this repo see `AGENTS.md`.

## One-liner
Rustenwer is Roger's Intelligence Fabrication & Discovery Platform: the smallest/cheapest/fastest sufficiently-capable intelligence for a problem needing intelligent behavior.

## Problem & audience
Companies overpay for oversized AI. Nobody sells 'exactly enough intelligence per dollar' as a productized service.

## Product (what it is / is not)
A platform + service that designs, trains, and hosts minimal sufficient AI for client problems. Human+AI hybrid fulfillment at first (Roger or engineers review/build) — the system must support that, not 100%-AI-only. It is ALSO Roger's extreme-depth AI learning path (each phase report includes a Spanish deep-dive).

## Key decisions (locked)
- License: Elastic License 2.0 (Roger's choice). Brand: platinum #E5E4E2.
- Multi-provider day one: Vast.ai spot for experiments, RunPod for final training + serverless GPU bursts, DO for CPU inference + control plane. CPU-first serving for tiny models.
- Moat = intelligence-per-dollar (tiny models + cascades).
- Supervisor-led quoting/contract agent generates both contracts from plain-language requests.
- Code against the working-tree contract, not the brief's snapshot (domain types evolved mid-build); never rename/reshape `shared/services/` signatures — the agents builder codes against them in parallel.

## Stack
Next.js web, FastAPI api, shared domain types (Python + TS), Supabase, LangGraph agents, CPU PyTorch + LoRA training infra.

## Business model
Two revenue lines: (1) one-time fee for BUILDING the client's AI product; (2) recurring SUPPORT tariff (retraining + inference + support). Client may buy training-only or both. Payments via Polar.

## Open questions
- Fase 5 E2E verification is the immediate open item.
- Pricing/costing calibration once real training runs accumulate cost data.
