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

### Phase 1 — MVP core

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/projects/{id}/specs` | bearer | create spec → `201` (DRAFT) |
| GET | `/api/v1/projects/{id}/specs` | bearer | list specs of a project |
| GET | `/api/v1/specs/{spec_id}` | bearer | spec detail or `404` |
| PATCH | `/api/v1/specs/{spec_id}` | bearer | update DRAFT fields; `409` when not DRAFT |
| POST | `/api/v1/specs/{spec_id}/diagnose` | bearer | run Specification/Diagnostic Agent → `DiagnosisResult`; status → `DIAGNOSED` |
| POST | `/api/v1/specs/{spec_id}/approve` | bearer | DRAFT/DIAGNOSED → `APPROVED`; `409` otherwise |
| POST | `/api/v1/projects/{id}/datasets` | bearer | create dataset → `201` |
| GET | `/api/v1/projects/{id}/datasets` | bearer | list datasets |
| GET | `/api/v1/datasets/{dataset_id}` | bearer | dataset detail |
| POST | `/api/v1/datasets/{dataset_id}/versions` | bearer | `{rows: [...], label_column?}` → `201 DatasetVersion` (validates + computes `DatasetReport`) |
| GET | `/api/v1/datasets/{dataset_id}/versions` | bearer | list versions (no rows) |
| GET | `/api/v1/datasets/{dataset_id}/versions/{version}` | bearer | version detail (no rows) |
| POST | `/api/v1/datasets/{dataset_id}/versions/{version}/validate` | bearer | recompute → `DatasetReport` |
| POST | `/api/v1/projects/{id}/training-jobs` | bearer | `{name, spec_id?, dataset_version_id?, strategy?}` → `201` (CREATED) |
| GET | `/api/v1/projects/{id}/training-jobs` | bearer | list jobs |
| GET | `/api/v1/training-jobs/{job_id}` | bearer | job detail |
| POST | `/api/v1/training-jobs/{job_id}/transition` | bearer | `{to: JobStatus}` → `200`; `409` on invalid transition (§42) |
| GET | `/api/v1/training-jobs/{job_id}/runs` | bearer | list runs (empty until Phase 2 executes) |
| POST | `/api/v1/projects/{id}/models` | bearer | create model → `201` |
| GET | `/api/v1/projects/{id}/models` | bearer | list models |
| POST | `/api/v1/models/{model_id}/versions` | bearer | add immutable version → `201` |
| GET | `/api/v1/models/{model_id}/versions` | bearer | list versions |
| POST | `/api/v1/projects/{id}/evaluations/run` | bearer | `{name?, spec_id, dataset_version_id}` → runs baselines → `201 Evaluation` (COMPLETED) |
| GET | `/api/v1/projects/{id}/evaluations` | bearer | list evaluations |
| GET | `/api/v1/evaluations/{evaluation_id}` | bearer | evaluation detail |
| POST | `/api/v1/projects/{id}/deployments` | bearer | create deployment → `201` (DRAFT) |
| GET | `/api/v1/projects/{id}/deployments` | bearer | list deployments |
| PATCH | `/api/v1/deployments/{deployment_id}` | bearer | `{status}` transitions; `409` on invalid |
| POST | `/api/v1/projects/{id}/usage-events` | bearer | record cost event → `201` |
| GET | `/api/v1/projects/{id}/usage/summary` | bearer | `UsageSummary` (§45) |
| POST | `/api/v1/projects/{id}/demo/termination` | bearer | seed §7 termination fixture (spec + dataset + version) and run baseline evaluation |

Deterministic domain logic (diagnosis, dataset validation, baselines,
strategy proposal, job transitions, usage summary) lives in
`shared/services/` (pure Python, no FastAPI/LangGraph imports) so the API
routers and the LangGraph agents both call the same code (plan Rule 3:
agents decide, services execute).

Auth: `Authorization: Bearer <supabase-jwt>`. Phase 0/1 accept any well-formed
token and inject a stub identity — real Supabase JWT verification and the
Supabase-backed repositories land once a Supabase project exists (see
`docs/DECISIONS.md`). Until then the API runs on in-memory repositories
behind `Protocol` interfaces; the migrations in `supabase/migrations/` are
the canonical schema.

Errors: `{detail: string}` with standard HTTP codes.

## Changelog

- 2026-09-26 — Phase 1 contract: `Dataset`, `DatasetVersion`, `DatasetReport`,
  `DiagnosisResult` (incl. `ml_necessary`, plan Rule 13), `BaselineMetrics`,
  `QualityBar`, `BaselineReport`, `TrainingStrategy`, `TrainingJob`,
  `TrainingRun`, `Model`, `ModelVersion`, `Evaluation`, `EvaluationResults`,
  `EvaluationStatus`, `Deployment`, `DeploymentStatus`, `UsageEvent`,
  `UsageSummary`, `DatasetFormat`, `UsageScope`, `UsageKind`. Full endpoint
  table above; deterministic logic in `shared/services/` (Rule 3).
- 2026-09-26 — Initial contract: `IntelligencePrimitive` (20 values, plan §2.3),
  `CandidateLifecycle` (9, plan §17), `JobStatus` (7, plan §42),
  `ProjectStatus`, `IntelligenceSpecStatus`, `Organization`, `ApiUser`,
  `Project`, `IntelligenceSpec` (plan §7).
