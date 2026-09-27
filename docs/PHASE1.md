# Rustenwer — Phase 1 build brief (for implementation agents)

> **Scope: Phase 1 ONLY** — "Original Rustenwer MVP Core" (product plan §61).
> You are one of three parallel builders. Read this whole file first, then
> implement ONLY your assigned area. Do not invent scope beyond it.

## 0. Non-negotiable conventions

1. **Read `~/workspace/skills/gentle-ai/SKILL.md` first** (updated 2026-09-26).
   All coding goes through it: ODD routing, **TDD RED→GREEN** (write the
   failing test first for new behavior, then implement; report the evidence),
   RDD self-review before you finish.
2. **Web builder only:** read `design-system/rustenwer/MASTER.md`, but the
   owner override wins — **platinum `#E5E4E2` is the primary brand color**
   (`--color-platinum` in `web/app/globals.css`). Biome clean, `tsc` clean,
   `npm run build` green. No emojis as icons; a11y checklist in MASTER.md.
3. **Python:** ruff (`line-length = 100`, config in `api/pyproject.toml`),
   pytest. Venvs are per-component: `api/.venv`, `agents/.venv`. System
   python is PEP 668 externally-managed — **never `pip install --user`**;
   install into the component venv if you need a package.
4. **Do NOT `git commit` and do NOT push.** Leave your changes in the working
   tree. The coordinator reviews and commits. Report: files changed/added,
   exact commands run + results (RED→GREEN evidence), what's stubbed.
5. **Do NOT touch** `shared/types.ts`, `shared/domain.py`, `shared/README.md`
   — the contract is frozen by the coordinator. If something is missing or
   wrong, report it instead of editing.
6. **Mark stubs honestly.** No real LLM calls exist (no keys) — deterministic
   fixtures must be clearly labeled `DETERMINISTIC FIXTURE`.
7. **Do NOT implement:** Supabase client wiring (no credentials exist),
   real training/GPU execution (Phase 2), experiments/candidates/discovery/RSI
   entities (Phases 6–8), `.github/workflows/*`.

## 1. Product context (condensed from the plan)

Rustenwer fabricates intelligence: the user describes desired behavior; the
platform determines the smallest/cheapest/fastest sufficiently-capable
intelligence — which may be **no ML at all** (Rule 13). Key rules baked now:

- **Rule 2:** never assume fine-tuning is the answer; strategy must justify
  the method, and "no training" is a first-class outcome.
- **Rule 3:** agents decide, services execute. Deterministic logic lives in
  `shared/services/` (pure Python, no FastAPI/LangGraph imports); LangGraph
  nodes only orchestrate.
- **Rule 4:** every expensive op is observable + cancellable (job transitions).
- **Rule 9:** baselines run BEFORE any training is proposed; the best
  baseline sets the `bar_to_beat`.
- **Rule 11:** evaluation is independent of the training mechanism — the
  runner evaluates row data, never model internals.
- **Rule 13:** the platform may conclude "you do not need a trained model".

Diagnostic agent (§8) must answer: 1 problem? 2 desired behavior? 3 inputs?
4 outputs? 5 primitive? 6 is ML necessary? 7 candidate approaches? 8 data
required? 9 how is success measured? 10 constraints?

Training Strategy agent (§12) decides: model, architecture, training method,
objective, dataset, hyperparameters, evaluation, compute budget. It does NOT
execute.

Dataset agent (§14): inspect/validate schema, missing data, label problems,
train/val/test splits, leakage, imbalance, version datasets. Deterministic
transformations in services; the LLM only decides.

Evaluation agent (§15): quality, accuracy, calibration, robustness,
generalization, latency, memory, inference cost, training cost, model size,
failure rate. Task-specific metrics.

Baselines (§16) implemented in Phase 1: `majority_class`, `keyword_heuristic`,
`deterministic_rule`.

Job lifecycle (§42): CREATED → QUEUED → RUNNING → PAUSED → FAILED →
CANCELLED → COMPLETED.

## 2. Data model (migration 002 — backend builder writes it)

`supabase/migrations/002_phase1_core.sql`. Mirror the style of `001`
(RLS enabled, org-scoped policies via `public.current_organization_id()`).
All tables get `id uuid PK default gen_random_uuid()`, `created_at timestamptz
default now()`.

- `intelligence_specs`: project_id FK→projects (cascade), name text,
  description text, problem_statement text NOT NULL, input_schema jsonb
  default '{}', output_schema jsonb default '{}',
  intelligence_primitive text CHECK (20 values from shared types),
  quality_requirements/cost_requirements/memory_requirements/
  reliability_requirements/latency_requirements/deployment_requirements jsonb,
  constraints text[] default '{}', available_data text,
  evaluation_definition text, human_review_policy text,
  status text default 'DRAFT' CHECK ('DRAFT','DIAGNOSED','APPROVED','ARCHIVED'),
  version int default 1, updated_at.
- `datasets`: project_id FK, name text, description text,
  format text default 'inline' CHECK ('jsonl','csv','inline'),
  row_count int default 0, updated_at.
- `dataset_versions`: dataset_id FK (cascade), version int NOT NULL,
  column_schema jsonb default '{}', split_config jsonb,
  stats jsonb (the DatasetReport), created_at. UNIQUE(dataset_id, version).
  (Rows are stored inline in the API's in-memory repo for Phase 1; a future
  migration moves them to artifact storage — note in a comment.)
- `training_jobs`: project_id FK, spec_id FK nullable,
  dataset_version_id uuid nullable (FK added in a later phase; plain uuid
  for now — comment it), name text, status text default 'CREATED'
  CHECK (7 job states), strategy jsonb, compute_budget jsonb, error text,
  updated_at.
- `training_runs`: job_id FK (cascade), attempt int default 1, status text
  default 'CREATED' CHECK (7 states), metrics jsonb default '{}',
  artifacts jsonb default '{}', logs text, started_at/finished_at timestamptz.
- `models`: project_id FK, name text, description text.
- `model_versions`: model_id FK (cascade), version int default 1,
  training_run_id uuid nullable, architecture jsonb, size_bytes bigint,
  metrics jsonb default '{}', artifact_uri text.
  UNIQUE(model_id, version).
- `evaluations`: project_id FK, spec_id FK, dataset_version_id uuid,
  name text, status text default 'PENDING'
  CHECK ('PENDING','RUNNING','COMPLETED','FAILED'), results jsonb,
  completed_at timestamptz.
- `deployments`: project_id FK, spec_id FK, model_version_id uuid nullable,
  name text, status text default 'DRAFT'
  CHECK ('DRAFT','ACTIVE','PAUSED','ARCHIVED'), endpoint_url text,
  config jsonb default '{}', updated_at.
- `usage_events`: project_id FK, scope text
  CHECK ('project','experiment','candidate','training_job','model',
         'deployment','inference'), scope_id uuid, kind text
  CHECK ('training','inference','evaluation','storage'),
  quantity double precision default 0, unit text default '',
  cost_usd double precision default 0, recorded_at timestamptz default now().
- Indexes on all `*_id` FK columns. Comment at top listing later-phase
  entities (experiments, candidates, discovery, RSI) as DO NOT CREATE.

## 3. `shared/services/` — deterministic domain services (backend builder)

Pure-Python package, **no FastAPI/LangGraph imports**. Pydantic models from
`shared.domain`. This is where Rule 3 lives: agents (LangGraph) and the API
both call these. Exact public signatures — do not change them:

```python
# shared/services/diagnosis.py
def diagnose_spec(spec: IntelligenceSpec) -> DiagnosisResult

# shared/services/datasets.py
def infer_column_schema(rows: list[dict[str, Any]]) -> dict[str, str]
def detect_leakage(rows: list[dict[str, Any]], label_column: str | None) -> list[str]
def recommend_split(n: int) -> dict[str, float]
def validate_dataset_version(dataset_id: UUID, version: int,
                             rows: list[dict[str, Any]],
                             label_column: str | None) -> DatasetReport

# shared/services/baselines.py
def run_baselines(spec: IntelligenceSpec, dataset_version_id: UUID,
                  rows: list[dict[str, Any]], label_column: str = "label") -> BaselineReport

# shared/services/strategy.py
def propose_strategy(spec: IntelligenceSpec, diagnosis: DiagnosisResult,
                     baseline_report: BaselineReport | None) -> TrainingStrategy

# shared/services/jobs.py
class InvalidTransitionError(ValueError): ...
ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]]
def transition(current: JobStatus, to: JobStatus) -> JobStatus  # raises InvalidTransitionError

# shared/services/costing.py
def summarize_usage(project_id: UUID, events: list[UsageEvent]) -> UsageSummary

# shared/services/fixtures.py
def termination_spec_fields() -> dict[str, Any]  # kwargs for IntelligenceSpec minus id/project_id
def termination_dataset_rows() -> list[dict[str, Any]]
```

Behavior notes:

- `diagnose_spec`: keyword map over `problem_statement.lower()` →
  primitive (prefer `spec.intelligence_primitive` when it isn't the default
  guess; the spec carries the user's pick). `ml_necessary=False` when the
  problem matches deterministic patterns (`sort by`, `filter by`, `lookup`,
  `count`, `deduplicate`, `format`, `threshold`, `validate`) with no learning
  signal words (`learn`, `predict`, `classify`, `fuzzy`, `ambiguous`). The
  `rationale` must visibly answer the 10 diagnostic questions (§8) in
  condensed form. `candidate_approaches` always starts with cheap baselines
  (Rule 9) and adds ML options only when `ml_necessary`.
- `validate_dataset_version`: infer per-column types (`int`/`float`/`bool`/
  `str`/`null`/`mixed`); `class_balance` from `label_column` (None when not
  given or absent); `missing_values` per column; `leakage_flags` when a
  feature column is suspiciously predictive of the label (e.g. a column whose
  value uniquely determines the label on the sample — deterministic check);
  `imbalance_detected` when minority class < 20% of majority;
  `ready_for_training` = rows ≥ 10 and no leakage flags and label present.
- `run_baselines`: three baselines, each timed with `perf_counter` (p50
  latency per prediction):
  - `majority_class`: always predict the most frequent label.
  - `keyword_heuristic`: if a text column exists (first non-label `str`
    column), predict by label-token presence; else fall back to a median
    split on the first numeric column.
  - `deterministic_rule`: pick the numeric column + threshold with best
    accuracy by exhaustive scan (deterministic).
  `cost_usd_per_1k = 0.0`, `size_bytes` = small constant from the serialized
  rule. `bar_to_beat` = best baseline's (accuracy, latency, cost). When
  labels are missing/unusable, baselines report `accuracy=None` and the bar
  carries zeros with a note in `recommendation`.
- `propose_strategy`: if `not diagnosis.ml_necessary` → `training_method=
  "none-deterministic"`, `model_family=None`, `architecture=None`,
  `no_training_justification` set (Rule 2/13). Else pick by primitive:
  `classification`/`termination` → `embedding-ft` (small data) or `lora`;
  default `lora`. Hyperparameters: `{rank: 16, epochs: 3, lr: 2e-4}`-style
  defaults. `compute_budget` heuristic: `max_cost_usd` scaled from data size
  (e.g. `min(50, 5 + n_rows/100)`), `max_gpu_hours` similarly small.
  `baseline_bar` copied from the report (Rule 9). `evaluation_plan`
  references the spec's `evaluation_definition`.
- `transition`: CREATED→{QUEUED, CANCELLED}; QUEUED→{RUNNING, CANCELLED};
  RUNNING→{PAUSED, FAILED, CANCELLED, COMPLETED}; PAUSED→{RUNNING, CANCELLED};
  FAILED→{QUEUED}; CANCELLED/COMPLETED→{} (terminal).
- `termination_spec_fields()`: the plan §7 example — name
  "Search termination intelligence", primitive `termination`,
  input_schema `{"search_state": {"type": "object"}}`,
  output_schema `{"decision": {"enum": ["continue", "stop"]}, "confidence":
  {"type": "number"}}`, `latency_requirements={"latency_budget_ms": 50}`,
  objective "maximize useful discoveries".
- `termination_dataset_rows()`: 12 rows, each
  `{state_summary: str, depth: int, progress_score: float, label:
  "continue"|"stop"}` — craft so majority≈0.67, keyword heuristic≈0.83,
  deterministic rule≈0.92 (a believable bar).

## 4. FastAPI (backend builder)

New modules under `api/app/`, following the existing `projects.py` pattern
(router + `Protocol` repository + `InMemory*` implementation + dependency
hook `get_*_repository()`; tests override per-test). Register all routers in
`api/app/main.py`. Endpoints — exact contract in `shared/README.md`
(coordinator extends it; read it):

- specs: create/list/get/patch + `/diagnose` + `/approve`
- datasets: create/list/get + versions create/list/get + `/validate`
- training-jobs: create/list/get + `/transition` + `/runs`
- models: create/list + versions create/list
- evaluations: `/run` (synchronous baseline evaluation → COMPLETED) + list/get
- deployments: create/list/patch (DRAFT→ACTIVE→PAUSED→ARCHIVED + CANCEL→ARCHIVED)
- usage: record event + `/summary`
- `POST /api/v1/projects/{project_id}/demo/termination` — seeds the fixture
  (spec + dataset + version) and runs the baseline evaluation; returns
  `{spec, dataset, version, evaluation}`.

Rules: org-scoping on every query (like `_get_or_404` in projects.py);
`PATCH /specs` 409 when status isn't DRAFT; `/diagnose` allowed from
DRAFT/DIAGNOSED (re-diagnosis bumps nothing — diagnosis is not versioned in
Phase 1); `/approve` from DRAFT/DIAGNOSED → APPROVED else 409; job
`/transition` uses `shared.services.jobs.transition` (409 on invalid).
In-memory repos keep rows for dataset versions (dict version_id → rows);
mark clearly that artifact storage is a later migration.

Tests (`api/tests/`): keep the 13 phase-0 tests green; add
`test_specs.py`, `test_datasets.py`, `test_training_jobs.py`,
`test_evaluations.py`, `test_usage.py`, `test_services.py` (diagnosis incl.
the **no-ML conclusion**, baselines on the fixture, job transitions incl.
invalid, usage summary). TDD: write failing tests first.

## 5. LangGraph agents (agents builder)

Replace the phase-0 placeholders with real nodes. `agents/` venv needs
`pytest` (install into `agents/.venv`). Add `agents/__init__.py` mirroring
`api/app/__init__.py`'s sys.path trick so `from shared...` works.

- `agents/state.py`: extend `SupervisorState` with `spec: dict | None`,
  `diagnosis: dict | None`, `dataset_report: dict | None`,
  `strategy: dict | None`, `baseline_report: dict | None`,
  `recommendation: str | None`, `no_ml_path: bool`, keep `messages`,
  `project_id`, `problem_statement`, `phase`, `notes`.
- `agents/llm_stub.py`: `StubLLM` class, `diagnose(problem_statement,
  primitive_hint) -> dict` keyword mapping. Docstring: **DETERMINISTIC
  FIXTURE — replace with a real LLM adapter when keys exist.**
- `agents/nodes/specification.py`: `specification_node(state)` — build an
  `IntelligenceSpec` from `state["spec"]` (dict) or synthesize a minimal one
  from `problem_statement`; call `shared.services.diagnosis.diagnose_spec`;
  store `diagnosis` (as dict), set `no_ml_path = not ml_necessary`.
- `agents/nodes/dataset.py`: `dataset_node(state)` — call
  `validate_dataset_version` on `state["dataset_rows"]` (list of dicts) +
  `state["label_column"]`; store `dataset_report`.
- `agents/nodes/strategy.py`: `strategy_node(state)` — call
  `propose_strategy(spec, diagnosis, baseline_report)`; store `strategy`.
  (Rule 2: the no-training path must be representable.)
- `agents/nodes/evaluation.py`: `evaluation_node(state)` — call
  `run_baselines`; store `baseline_report`; write `recommendation`
  ("promote best baseline" vs "train candidate X to beat bar").
- `agents/nodes/routing.py`: `route_after_baselines(state)` → `"strategy"`
  if `diagnosis.ml_necessary` else `"summarize"`.
- `agents/supervisor.py`: rebuild graph —
  `intake → specification → dataset_check → baselines → route → (strategy → summarize | summarize)`.
  Keep node functions importable for unit tests.
- `agents/demo.py`: end-to-end run with the termination fixture
  (`shared.services.fixtures`): spec → baselines → strategy → recommendation;
  print the trajectory; exit non-zero on assertion failure.
- `agents/tests/`: `test_stub.py`, `test_nodes.py`, `test_graph.py`
  (full run passes; no-ML path short-circuits strategy).

## 6. Web (web builder)

Extend `web/lib/api.ts` with typed clients for every new endpoint (import
types from `../../shared/types`; keep the `ApiOfflineError` pattern; mock
fallbacks for the new entities, clearly marked MOCK, served only offline).

Pages (App Router), platinum theme, reuse existing components
(`StatusBadge`, `SiteHeader`, ...):

- `web/app/projects/[id]/specs/new/page.tsx` — 3-step wizard:
  1. Describe: name, problem_statement (textarea, plain-language helper per
     plan §6: "describe what should happen, not ML terms"), primitive select
     (20 primitives + "auto-detect").
  2. Inputs/outputs: JSON textareas with validation + quality/latency
     (latency_budget_ms)/cost fields.
  3. Review → create → redirect to spec detail.
- `web/app/projects/[id]/specs/[specId]/page.tsx` — spec detail: all fields,
  status badge, **Diagnose** button (POST diagnose; show result incl. the
  "no ML needed" callout when `ml_necessary` is false), **Approve** button,
  **Run baseline evaluation** button + results table (baseline, accuracy,
  p50 latency, cost/1k, bar_to_beat), evaluations history.
- `web/app/projects/[id]/datasets/page.tsx` — dataset list + create form;
  per dataset: version upload (textarea with JSON array + label column input),
  validation report view (schema, class balance, leakage flags, split).
- Extend `web/app/projects/[id]/page.tsx`: sections for Specs (list + "New
  spec" link), Training Jobs (table + transition buttons: queue/run/pause/
  resume/cancel), Evaluations (list), Usage (summary cards). Also a
  "Try the termination demo" button calling the demo endpoint.
- `npm run build` green, Biome clean, `tsc` clean.

## 7. What "done" looks like (per builder)

- Backend: migration 002 written; routers registered; `pytest` all green
  (13 old + new); `ruff check` clean; RED→GREEN evidence reported.
- Agents: `python demo.py` passes end-to-end; `pytest` green; graph has no
  placeholder nodes left.
- Web: `npm run build` green; `biome check` clean; all new pages reachable
  from the project page; wizard creates a real spec against the API.
