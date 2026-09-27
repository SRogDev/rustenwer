# Phase 5 — Training Method Knowledge (plan)

Product plan refs: §10 (method taxonomy), §11 (TrainingMethod structured
representation, versioned), §12 (strategy vs execution), §52–§53 (research
pipeline), §54 (adapter interface — exists from Phase 2).

## Goal
Make training-method choice a data-driven decision, not a hardcoded branch.
`shared/services/strategy.py::propose_strategy` currently hardcodes
`"embedding-ft" if n_rows < 1000 else "lora"`. Phase 5 replaces that with a
registry query: given (IntelligenceSpec, DiagnosisResult, baseline bar,
environment), return ranked compatible methods + explicit vetoes with
reasons. Vetoes are the negative-search seed for Phase 7 — stored as data.

## Design contracts

### 1. TrainingMethod (versioned, structured — §11)
New pydantic models in `shared/domain.py` (mirrored in `shared/types.ts`,
sync ledger in `shared/README.md` updated):

- `MethodCategory(StrEnum)`: values from the §10 taxonomy —
  `supervised`, `peft`, `self_supervised`, `preference_optimization`,
  `reinforcement_learning`, `distillation`, `contrastive`,
  `synthetic_data`, `curriculum`, `search_evolutionary`, `hybrid`.
- `MethodValidationStatus(StrEnum)`: `VALIDATED` (real local or GPU run
  exists), `KNOWN` (taxonomy entry, not yet validated on our stack).
- `TrainingMethod(BaseModel)`: `slug` (e.g. `"lora"`), `name`, `category`,
  `version` (int, immutable per version — a new version is a NEW row/record,
  never an edit), `status`, `supported_tasks` (list[str]),
  `data_requirements` (dict, e.g. `{min_rows, labeled: bool,
  pairwise: bool}`), `compute_requirements` (dict, e.g.
  `{gpu_required: bool, min_vram_gb, rough_cost_per_hour_usd}`),
  `strengths`/`weaknesses`/`failure_modes` (list[str]),
  `compatible_architectures` (list[str]), `compatible_objectives`
  (list[str]), `evaluation_requirements` (list[str]),
  `implementation_templates` (list[str] — adapter names, may be empty),
  `locally_runnable` (bool), `notes` (str).

Seeded methods (status VALIDATED): `classifier` (supervised),
`lora` (peft), `qlora` (peft, GPU-only), `distillation` (new Phase 5),
`contrastive` (new Phase 5). Seed KNOWN entries for the rest of the §10
taxonomy (instruction-tuning, dpo, rl-verifiable, self-supervised,
synthetic-data, curriculum, evolutionary-search, embedding-ft) so the
catalog is complete but honest: `implementation_templates: []` and
`locally_runnable: false` where no adapter exists.

### 2. Adapter linkage
Extend `ADAPTERS` in `api/app/training/adapters.py` (or a new module it
re-exports) with two REAL CPU-capable adapters implementing the §54
interface (validate/prepare/estimate/train/checkpoint/resume/evaluate/
export):

- `DistillationAdapter` (`training_method="distillation"`): trains a larger
  teacher MLP on the synthetic blobs, then distills into a small student
  with temperature-scaled soft targets. Reuse `_TorchSupervisedAdapter`
  where possible; the distill loop is new code. Must PROVE the thesis in
  tests: student trained with distillation ≥ student trained from scratch
  on the same toy task (or matches teacher closely).
- `ContrastiveAdapter` (`training_method="contrastive"`): small embedding
  tower + contrastive/infonce-style loss over synthetic similar/dissimilar
  pairs derived from the blobs (same-class = similar). Evaluation reports
  retrieval-style accuracy (nearest-centroid on val).

`api/app/methods/registry.py` holds the canonical seed list
`TRAINING_METHODS: list[TrainingMethod]` plus
`METHOD_ADAPTERS: dict[str, str]` (method slug → adapter key in ADAPTERS,
only for locally registered ones) and a consistency check
`assert_registered()` used in tests: every VALIDATED method with
`locally_runnable=True` must have an adapter entry.

### 3. Recommendation engine (`api/app/methods/recommend.py`)
Pure function, fully unit-testable:

```python
def recommend_methods(spec, diagnosis, baseline_report, environment) -> MethodRecommendation
```

- `environment`: `{has_cuda: bool, has_unsloth: bool}` (detected once at
  startup, passed in — keeps the function pure).
- `MethodRecommendation`: `recommended: list[MethodRank]` (slug, version,
  score, reasons[]), `vetoed: list[MethodVeto]` (slug, version, reason),
  `citations: list[str]` (`"lora@1"` style — the Strategy Agent embeds
  these).
- Veto rules (data, not prose — each rule is a small named predicate):
  - `qlora` vetoed when `not has_cuda` ("no CUDA here; use the
    digitalocean provider") — mirrors `QLoRAAdapter.supports_provider`.
  - `embedding-ft` vetoed: "no local adapter registered yet".
  - `distillation` requires labeled data (`data_requirements.labeled` vs
    spec/dataset signal; for our synthetic path always available).
  - `contrastive` only recommended when the primitive is
    ranking/retrieval/similarity-ish OR the caller passes
    `allow_generic=True`; vetoed otherwise with reason.
  - `none-deterministic` is NOT a training method — when
    `diagnosis.ml_necessary` is False the engine short-circuits with an
    empty recommendation and a note (Rule 13).
- Ranking: deterministic score from (primitive fit from
  `supported_tasks`/`compatible_objectives`, cost from
  `compute_requirements`, latency requirement from the spec). No global
  weights (§30) — the spec's requirements drive the ordering; document
  the formula in the docstring.

### 4. Research knowledge (`api/app/methods/research.py`)
`ResearchFinding` model (§52 shape): `technique`, `useful_for`,
`requires`, `advantage`, `weakness`, `source` (e.g.
`"validated: phase-5 e2e"`), `version`. Seeded findings:
- LoRA init trick (Kaiming-uniform A, zero B — matches our LoRAAdapter).
- QLoRA 4-bit (memory win, CUDA-only).
- Distillation soft-targets with temperature (what our adapter uses).
- Contrastive embeddings for ranking/similarity.
Store: in-memory repository behind a Protocol (same pattern as Phase 1+),
migration 005 is canonical for the later Supabase swap.

### 5. Strategy Agent integration (Rule 3: it DECIDES)
`shared/services/strategy.py::propose_strategy` calls the recommendation
engine (lazy import to avoid circulars) and:
- sets `training_method` from the top recommendation (instead of the
  hardcoded branch),
- fills new `TrainingStrategy` fields `method_citations: list[str]` and
  `vetoed_methods: list[dict]` (slug + reason) — add to `shared/domain.py`
  AND `shared/types.ts`,
- keeps the `none-deterministic` path (Rule 13) and the baseline-bar
  objective text.

### 6. API (`api/app/methods/router.py`)
- `GET /api/v1/methods` — list (filter `?category=`, `?status=`).
- `GET /api/v1/methods/{slug}` — all versions + current.
- `POST /api/v1/methods/recommend` — body `{spec, diagnosis,
  baseline_report?, allow_generic?}` → `MethodRecommendation`.
- `GET /api/v1/research` — findings list.
Wire the router in `api/app/main.py` behind the existing auth dependency
(check how other routers do it).

### 7. Migration `supabase/migrations/005_phase5_methods.sql`
Canonical tables: `training_methods` (all §11 columns, unique
`(slug, version)`), `adapter_registry` (method_slug, method_version,
adapter_name, template_ref, locally_runnable, notes), `research_findings`
(§52 columns + version). Comment header noting the API runs in-memory
until the Supabase swap (same convention as 001–004).

### 8. Web UI
- `/methods` — catalog browser: taxonomy tree grouped by category,
  VALIDATED vs KNOWN badges, method detail panel (strengths / weaknesses /
  failure modes / data & compute requirements / implementation templates).
- Spec detail page: "Method recommendation" section — calls
  `POST /methods/recommend` for the current spec, shows ranked methods
  with reasons and the vetoed list with reasons ("ruled out Y because…").
- Platinum theme (`#E5E4E2` primary, charcoal foregrounds — owner
  override), `npm run build` green, Biome clean. API client in
  `web/lib/` typed from `shared/types.ts`.

## Tests (TDD, RED→GREEN)
`api/tests/test_phase5_methods.py` (+ extend existing where natural):
- vetoes fire: qlora vetoed without CUDA; embedding-ft vetoed (no
  adapter); contrastive vetoed for pure classification without
  allow_generic.
- ranking deterministic: same input → same order; spec latency/cost
  requirements change the order (at least one assertion proving
  spec-driven ordering).
- registry consistency: every VALIDATED + locally_runnable method has an
  adapter in ADAPTERS; every adapter key maps to a method row.
- research finding schema validation (missing field → 422/validation
  error).
- distillation learns: student-with-distillation val_accuracy ≥
  student-from-scratch on seeded blobs (or ≥ 0.9 × teacher accuracy).
- contrastive learns: nearest-centroid val accuracy > 0.6 on seeded data.
- strategy integration: `propose_strategy` output carries
  `method_citations` non-empty when ML necessary, empty + note when not.
Keep ALL previous suites green (242+ pytest baseline).

## E2E (coordinator runs)
1. Boot API, create project + spec (termination primitive, ring task),
   `POST /methods/recommend` → expect classifier/lora/distillation
   ranked, qlora vetoed.
2. Submit a training job with `training_method="distillation"`, run the
   worker path to completion locally, assert artifacts + metrics.
3. Report exact evidence.

## Delivery
- Reviewable conventional commits via `git add -A` + local commits.
- Coordinator pushes with `~/workspace/scripts/push_repo.py`
  (SRogDev/rustenwer). NEVER `.github/workflows/*`.
- Update: root README roadmap, `docs/DECISIONS.md`, write
  `docs/PHASE5.md` handoff (key files, contracts, Phase 6 entry points).
- Deep-dive teaching section (Spanish) for Roger's report.
