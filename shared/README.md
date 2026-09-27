# Shared domain types

`types.ts` (web) and `domain.py` (api/agents) are the **single source of truth**
for Rustenwer's domain shapes. They are **hand-synced** by design:

- Change both files together, never one alone.
- Enum values must be identical strings across both files.
- Update this README's changelog entry when the contract changes.

Future: code-generate one from the other (e.g. JSON Schema as the canonical
form). Until then, this README is the sync ledger.

## API contract (Phase 0)

Base URL: `http://localhost:8000` (env `API_URL`; web uses `NEXT_PUBLIC_API_URL`).

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | liveness: `{status, version, service}` |
| GET | `/api/v1/projects` | bearer | list projects of the caller's org |
| POST | `/api/v1/projects` | bearer | create project `{name, description?}` → `201 Project` |
| GET | `/api/v1/projects/{id}` | bearer | project detail or `404` |
| PATCH | `/api/v1/projects/{id}` | bearer | update `name/description/status` |
| DELETE | `/api/v1/projects/{id}` | bearer | archive (soft → `ARCHIVED`) |

Auth: `Authorization: Bearer <supabase-jwt>`. Phase 0 accepts any well-formed
token and injects a stub identity — the real Supabase JWT verification lands
with Phase 1 once a Supabase project exists (see `docs/DECISIONS.md`).

Errors: `{detail: string}` with standard HTTP codes.

## Changelog

- 2026-09-26 — Initial contract: `IntelligencePrimitive` (20 values, plan §2.3),
  `CandidateLifecycle` (9, plan §17), `JobStatus` (7, plan §42),
  `ProjectStatus`, `IntelligenceSpecStatus`, `Organization`, `ApiUser`,
  `Project`, `IntelligenceSpec` (plan §7).
