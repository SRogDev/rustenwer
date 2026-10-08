# STATUS — rustenwer

> Single source of truth for where this project stands. Last updated: 2026-10-08.
> Read this before starting work. Update it in the same PR when reality changes.

## Done
- 2026-09-26 — Fases 0–4 done: domain types + migration 001 + RLS + FastAPI CRUD + LangGraph skeleton + Next.js app; real agents + baselines + job state machine + spec wizard; CPU PyTorch + LoRA training infra with checkpoints + cost accounting; Benchmark Registry + QualityVector + model registries; immutable IntelligenceVersion + hosted inference + deploy UI; termination intelligence v1 end-to-end.
- 2026-09-27 — Fase 5 implementation done (`/methods` catalog + `/methods/[slug]` detail pages, methods service layer).

## In progress / blocked
- Fase 5: push VERIFIED on main 2026-10-08 (all Phase-5 blobs match: docs/PHASE5.md, shared/services/methods.py, api/app/methods/, migration 005, web /methods UI). Final E2E verification still pending.
- Blocked on Roger: Supabase project + migrations + `SUPABASE_URL`/`JWT_SECRET`.
- CI: `.github/workflows/` cannot be pushed with the current token (lacks `workflows` scope) — needs a full-scope token or a local git remote.

## Next
- Verify Fase 5 E2E, then continue per the 66-section plan (Fase 6: Candidate Experiment Engine — entry points in docs/PHASE5.md).
