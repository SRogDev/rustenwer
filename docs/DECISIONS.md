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
