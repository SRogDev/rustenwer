# Rustenwer — Phase 3 completion record & Phase 4 handoff

> Completed 2026-09-27. Phase 3 = Evaluation & Registry: independent
> evaluation of any subject on reusable benchmarks, multi-objective quality
> vectors, baseline/incumbent comparison, immutable model lineage, the
> Intelligence registry (first-class, separate from Model), and per-scope
> cost rollups.

## What was built

**Contracts** (`shared/domain.py`, `shared/types.ts`, `shared/README.md`):
- `SubjectKind` (`baseline | model_version | reference`), `EvaluationSubject`,
  `QualityVector` (task_quality, calibration=1−ECE, robustness,
  latency_ms_p50/p99, inference_cost_usd_per_1k, training_cost_usd,
  model_size_bytes, reliability — no global weights, ever), `Benchmark`,
  `EvaluationRun` (+ `EvaluationStatus.CANCELLED`), `ComparisonSubjectResult`,
  `ComparisonReport`, preliminary `Intelligence` / `IntelligenceVersion`.
- ModelVersion lineage (§43): dataset_version_id, training_strategy,
  code_version, template_version, seed, base_model, immutable versions.
- `UsageScope.EVALUATION` added (Python + TS + migration 003 alters the
  `usage_events.scope` check constraint).
- Migration `003_phase3_registry.sql`: `benchmarks`, `evaluation_runs`,
  `intelligences`, `intelligence_versions`, lineage columns, RLS.

**Evaluation subsystem** (`api/app/evaluation/`):
- `metrics.py` — pure functions: accuracy, expected calibration error
  (hand-verified: ECE = 0.35 on a pinned case), latency p50/p99,
  cost_per_1k, Brier score, per-class accuracy. No torch.
- `benchmarks.py` — `BenchmarkRegistry` + in-memory repo seeded with two
  global benchmarks: `termination-benchmark` (Phase-1 rows) and
  `ring-benchmark` (200 deterministic held-out rows, seed 20260926 ≠
  training seed 0, same N(0,1)/Rayleigh-median≈1.1774 distribution as the
  Phase-2 training blobs). Project-scoped custom benchmarks with rows +
  label column.
- `subjects.py` — subject-independent evaluator (Rule 11): baseline
  subjects reuse `run_baselines` via per-row mirrors pinned equal by test;
  model_version subjects resolve via `ModelRepository`, rebuild the MLP
  exactly as `adapters.py::build_model`, load `model.pt`+`config.json`;
  feature mismatch → `SubjectBenchmarkMismatch` → the run FAILS (negative
  evidence by design, never a silent skip).
- `runner.py` — thread-based `EvaluationManager`: PENDING→RUNNING→
  COMPLETED/FAILED/CANCELLED, cancel flag checked between rows (partial
  metrics kept), `on_finish` records one `UsageEvent(kind=EVALUATION,
  scope=EVALUATION)` per terminal run. Local-CPU `cost_usd=0.0`, honestly.
- `quality.py` — `assemble_quality_vector`, `beats_bar` (Pareto-strict on
  all three axes — see decisions), spec-priority lexicographic ranking,
  **no global weights anywhere**.
- `compare.py` — `build_comparison_report`: per-subject `beats_bar` /
  `beats_incumbent`, winner per spec priorities, plain-language notes.
- `router.py` — full evaluation-runs table; 404 on missing, **409 on
  subject/state faults** (unknown baseline, bogus model ref, bad kind);
  incumbent resolved lazily (ImportError → explanatory note, never 500).

**Registry** (`api/app/registry/`, `api/app/models.py`):
- Intelligence CRUD + list/detail, immutable versions (auto-increment),
  component validation, resolved component lineage
  (`model_version_id → model_name, version, architecture_summary,
  training_run_id, seed, code_version`).
- Model version lookup + `/models/{id}/lineage` diff endpoint (consecutive
  versions, changed field names).
- `POST /intelligences/{id}/promote` → honest **501** until Phase 6.
- Org scoping on every route; 404 on missing/foreign-org.

**Cost** (`shared/services/costing.py`, `api/app/usage.py`):
- `GET /api/v1/projects/{id}/usage/rollups` → `UsageRollups`: total +
  per-scope (`ScopeRollup`: total, by_kind, event_count) + by_kind.

**Web** (`web/app/projects/[id]/registry/`, `web/components/`):
- Registry browser (Models / Intelligences / Benchmarks tabs), model
  version chain + client-side "what changed" diff explorer, intelligence
  version chain with resolved components, "Promote — Phase 6" button that
  surfaces the 501 honestly.
- Benchmark detail: run-evaluation form (baseline | model version |
  reference), run list, multi-subject `ComparePanel` (side-by-side quality
  vectors, beats-bar/incumbent badges, winner highlight).
- Run detail: status pill incl. CANCELLED, cancel button, 3s polling, SVG
  quality-vector radar, cost dimensions, metrics table, FAILED error.
- Project dashboard: cost-rollups section (total + per-scope bars) with
  offline-mock fallback. Platinum `#E5E4E2` theme, tsc + Biome + `next
  build` green.

**Tests**: 50 evaluation tests (TDD RED→GREEN), 19 registry tests,
cost-rollup tests. Full suite: **218 API + 23 agents, all green**; ruff
clean.

## Live E2E proof (30/30 checks, real server + real torch)

`train → register → evaluate → compare → registry → rollups`, all through
HTTP against `uvicorn` with the real Phase-2 training stack:

1. Trained a 2-feature MLP classifier (5 epochs, seed 7) via
   `POST /training-jobs → /enqueue` → COMPLETED (needed a small additive
   change: `_prepare_blobs` now honors a `n_features` hyperparameter,
   default 20 — the ring benchmark's rows are 2-float).
2. Registered the export bundle as model v1 with full lineage
   (`training_run_id`, `training_strategy`, `code_version`,
   `template_version`, `seed`); `/models/{id}/lineage` returns it.
3. Ran `ring-benchmark` with subject `model_version` → COMPLETED with a
   real quality vector: **task_quality=0.9750, calibration=0.8941**,
   latency p50 0.03ms, inference cost $0.00 (local CPU, honest).
4. Compared model vs the three Phase-1 baselines: **winner = the trained
   model**; deterministic_rule correctly reaches **0.6500** on ring rows
   (a real bug was found and fixed here — see decisions); the model beats
   the bar on task quality (0.975 vs 0.650) while `beats_bar` is honestly
   False under the Pareto-strict gate (slower than a constant-time
   lookup).
5. Created an intelligence, pinned the model version in intelligence v1,
   resolved components show the full lineage chain back to the training
   run.
6. `/usage/rollups` shows the evaluation scope with its events.

## Decisions & bug fixes (also in `docs/DECISIONS.md`)

- **Vector-valued benchmark rows blinded the baselines.** `_numeric_columns`
  only saw scalar columns, so on `x: [float, float]` rows every baseline
  silently fell back to majority (0.535) while a single threshold actually
  scores 0.65. Fixed: list/tuple columns expand to `name[i]`
  pseudo-columns, resolved via `_column_value`, in both `run_baselines`
  and the evaluation mirrors (which import the same helpers, so the
  mirror==aggregate pin still holds).
- **`beats_bar` is Pareto-strict** (task AND latency AND cost vs the bar),
  per the evaluation writer's tested contract. Consequence: trained models
  essentially never beat the bar on latency against microsecond-scale
  constant-time baselines, and the gate is jitter-sensitive at that scale
  (bar latency 0.0007ms vs a rerun at 0.0008ms flips the bit). The
  priority-ranked `winner` is the promotion-relevant signal; Phase 6
  should revisit the gate (epsilon tolerance or spec-budget-based).
- **`UsageScope.EVALUATION` added** (was missing; the runner recorded
  scope=PROJECT). Migration 003 alters the `usage_events.scope` check
  constraint; `scope_id` is now the evaluation run id.
- **No global quality weights.** `rank_by_spec_priority` is lexicographic
  over `spec.quality_requirements["priority"]`; unknown fields raise.
- **Subject mismatch fails the run, never 500s the comparison.** In
  `compare`, a mismatched subject is reported unscored with the honest
  error in its metrics.
- **Promotion is a 501, not a stub that pretends.** The web button calls
  it and renders the 501 detail.

## Honest stubs & blocks (unchanged from Phase 2)

- No Supabase project/credentials: migration 003 is canonical but
  unexecuted; repositories are in-memory.
- DigitalOcean provider still credential-blocked; QLoRA still needs CUDA.
- `agents/` LangGraph nodes untouched by Phase 3 (evaluation agents stay
  Phase-1; the runner is the deterministic service per Rule 11).

## Phase 4 handoff

- Deepen `Intelligence` / `IntelligenceVersion` / `IntelligenceArchitecture`
  (plan §31–§34): richer component kinds (prompt programs, tool graphs,
  harness configs), version-diff for intelligences, intelligence-level
  lineage.
- Refactor deployment to deploy an **Intelligence**, not a Model
  (the registry's 501 `promote` becomes the Phase-6 promotion engine's
  entry point; `ComparisonReport` is its input data).
- Revisit `beats_bar` gate semantics (above).
- Suggested first commit: intelligence version diff endpoint mirroring
  the model lineage diff.
