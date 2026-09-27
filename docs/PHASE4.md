# Rustenwer — Phase 4 completion record & Phase 5 handoff

> Completed 2026-09-27. Phase 4 = Intelligence Abstraction: the
> Intelligence becomes the first-class, executable product artifact —
> immutable versions with validated architecture snapshots, a hosted
> inference pipeline serving deterministic + model components with
> machine-readable outputs, the `InferenceProvider` abstraction, and
> deployments that serve an Intelligence (never a bare Model).

## What was built

**Contracts** (`shared/domain.py`, `shared/types.ts`, `shared/README.md`):
- `ArchitectureComponentKind` (8 kinds: `model_version`, `baseline`,
  `prompt`, `deterministic_rule`, `threshold`, `tool`, `harness`,
  `post_processor`), `ARCHITECTURE_KINDS` (`single_model`,
  `model_with_rules`, `deterministic_rule`, `ensemble`, `router`,
  `tool_graph`, `llm_judge_threshold`), `ArchitectureComponent`
  (kind, optional immutable ref, label, config), `IntelligenceArchitecture`
  (kind, components, execution order), `IntelligenceVersion` deepened
  (architecture, input/output schemas, `locked`), `IntelligenceVersionDiff`
  (`components_added/removed/modified`, `changed_fields`,
  `architecture_kind_changed`, `schema_changed`, human-readable `notes`).
- `InferenceProvider` (`rustenwer_hosted | external_api | local_gpu`),
  `ProviderInfo`, `InferenceRequest`, `InferenceResponse` (output +
  intelligence/deployment lineage + latency).
- `PRIMITIVE_PROGRAMMING_MAP` — the 12 programming primitives ↔
  intelligence primitive mappings (if→decision, filter→filtering,
  compress→compression, …).
- `Deployment` deepened: `intelligence_version_id` (preferred target),
  `provider`, `endpoint_url`; `model_version_id` kept for back-compat.
- Migration `004_phase4_intelligence.sql`: `intelligence_architectures`
  table, immutable snapshot columns on `intelligence_versions`,
  `deployments.intelligence_version_id` + provider, `inference_endpoints`,
  indexes, RLS. Canonical but unexecuted (no Supabase project).

**Intelligence subsystem** (`api/app/intelligence/`):
- `architectures.py` — publish-time validation: architecture-kind must be
  known; every component kind must be a real `ArchitectureComponentKind`;
  `model_version` refs must resolve to a real model version (404
  otherwise); deterministic-rule configs must carry column/threshold/
  labels; threshold configs must carry input_key/threshold/above/below;
  prompt components must carry a template; execution order must cover
  exactly the component indexes; **non-executable kinds (`router`,
  `tool_graph`) are rejected until Phase 7** — fail fast where the user
  can fix it. Summaries + component diffs for the registry.
- `diff.py` — `diff_versions`: kind changes, added/removed components,
  modified components with changed config keys (e.g. threshold 0.21 →
  0.35), schema changes, and human-readable notes for reviewers.
- `inference.py` — the hosted pipeline: JSON-schema-lite input validation
  (required fields, type coercion checks → 422), then per-kind executors:
  `deterministic_rule`, `threshold`, `baseline`, `model_version` (real
  torch, shared bundle-loading path with the evaluation subjects),
  `post_processor`. Outputs are shaped machine-readable per primitive:
  termination/decision → `{decision, confidence}`; classification →
  `{label, probabilities}`; ranking → `{score}`. Prompt/tool components
  fail honestly (`ProviderNotConfigured` → 501, no fake LLM).
- `router.py` — `GET /inference/providers` (honest capability entries),
  `GET /deployments/{id}`, `POST /deployments/{id}/infer` (only ACTIVE
  deployments; records an `INFERENCE` usage event at cost 0.0 for local
  CPU). Error mapping: schema → 422, provider → 501, component → 502,
  unknown target → 404, inactive → 409.
- `service.py` — `resolve_deployment_target` (404 when the pinned version
  is gone) and `ensure_model_backcompat_intelligence`: a bare
  `model_version_id` deployment auto-creates a single-model intelligence
  ("<name> (auto)") pinning classes + feature key, so the Phase-1 contract
  keeps working while everything new targets intelligences.

**Deployments** (`api/app/deployments.py`): create requires exactly one
target (409 otherwise); repository injection via lazy hooks so tests stay
isolated; deployment detail endpoint.

**Web** (platinum theme, Biome + tsc + production build green):
- `ArchitectureDiagram` — each version's immutable snapshot rendered as
  an execution pipeline: kind pills, pinned refs, config summaries.
- `VersionDiffViewer` — pick two versions, see kind changes,
  added/removed/modified components, reviewer notes.
- Deploy flow (`/projects/[id]/deployments/new`): select an immutable
  intelligence version + spec + name; "Deploy this version" links from
  every version card preselect it.
- Deployment detail: lifecycle state + transition buttons, provider,
  pinned version, endpoint URL + copy-paste curl, live infer console
  (JSON inputs → machine-readable output), pinned architecture diagram.
- Project page gains a Deployments section.

## Live E2E proof (21/21 checks, real uvicorn server)

`/tmp/p4_e2e.py` drove the real HTTP API end to end:

1. Project + termination spec + intelligence created.
2. **Intelligence v1 published** with the deterministic rule
   `progress_score <= 0.21 → stop` (locked, immutable).
3. Deployment created targeting the intelligence version — pins it,
   exposes `/api/v1/deployments/{id}/infer`.
4. DRAFT inference correctly refused (409); after activation:
   `{"progress_score": 0.10}` → **`{"decision": "stop", "confidence": 1.0}`**;
   `{"progress_score": 0.90}` → `continue`.
5. Wrong-typed input → 422; providers list honest
   (hosted functional, external_api/local_gpu not); inference usage
   events recorded.

A torch model-component E2E also passes in the test suite: a real
2-feature MLP bundle served through a deployed intelligence returns
`{label, probabilities}` identical to the raw torch computation.

## Verification

- API: **242 passed** (218 Phase-1–3 + 24 new Phase-4), ruff clean.
- Agents: **23 passed** (untouched by Phase 4).
- Web: tsc 0 errors, Biome clean (57 files), `next build` green —
  two new routes (`/deployments/new`, `/deployments/[deploymentId]`).
- npm audit: environment-blocked (registry unreachable through the
  egress proxy); no new production dependencies added.
- TDD: both new test files written RED first (9 errors → green;
  12 inference tests → green including real torch).

## Decisions & bug fixes (also in `docs/DECISIONS.md`)

- Deployments require exactly one target (409 on zero/two); Phase-1
  tests now exercise the back-compat auto-intelligence path.
- Providers are capability entries; real integrations register an
  `InferenceProvider` implementation — the infer endpoint never changes.
- Input 422 / component 502 / provider 501: the status names the broken
  layer.
- Non-executable kinds rejected at publish (Phase 7 owns routers).
- `GET /api/v1/intelligence-versions/{version_id}` added: deployments
  pin version ids, so detail pages resolve versions directly.
- The web diff client was first written against a query-param diff
  route that never existed; fixed to the real
  `/versions/{a}/diff/{b}` route — a reminder to read the backend
  routes, not assume them.

## Honest stubs & blocks

- No Supabase project/credentials: migration 004 canonical, unexecuted;
  repositories in-memory.
- `external_api` / `local_gpu` providers: capability entries, 501 when
  invoked. `promote` still 501 (Phase 6).
- The old `components` map is still accepted at publish and auto-derived
  from the architecture snapshot when omitted.

## Phase 5 handoff — Training Method Knowledge

Phase 5 entry points, in suggested commit order:

1. **`TrainingMethod` entity** (`shared/domain.py` + migration 005):
   method identity (name, family: `gradient_boosting | neural | kernel |
   …`), validated hyperparameter schema, capability tags (task kinds,
   data regimes), and provenance (paper/blog URL, author).
2. **Adapter registry** (`api/app/training/`): turn the Phase-2
   `TrainingMethodAdapter` interface into a registered catalog —
   `validate/prepare/estimate/train/checkpoint/resume/evaluate/export`
   per method, with the existing classifier/LoRA/QLoRA adapters as the
   first three entries.
3. **Structured research knowledge**: store method knowledge as data
   (when to use, failure modes, cost/latency profile), not docs — the
   Training Strategy agent reads it to propose methods per spec.
4. **Seed with existing validated methods**: the three Phase-2 adapters
   plus the Phase-1 baselines (majority/keyword/deterministic), each
   with its measured bar from the benchmarks (e.g. deterministic_rule
   0.65 on ring) so the strategy agent starts from evidence, not lore.
5. Suggested first commit: `TrainingMethod` contract + migration 005,
   mirroring how Phase 4 started from contracts.

---

## Lección profunda — Fase 4: qué es realmente una "Inteligencia"

*Esta sección es material de estudio: los conceptos de IA detrás de lo
construido en esta fase, explicados desde cero.*

### 1. Modelo ≠ Inteligencia (la idea central de Rustenwer)

En ML tradicional, el "modelo" (los pesos entrenados) **es** el producto:
entrenas una red, la sirves, listo. Rustenwer dice que eso es
insuficiente. Un **modelo** es solo *conocimiento comprimido* (pesos):
una matriz de números que mapea entradas a salidas. Una
**Inteligencia** es el *sistema ejecutable completo*: qué componentes se
ejecutan, en qué orden, con qué reglas deterministas, qué esquemas de
entrada/salida acepta, qué prompts, qué umbrales.

Analogía: el modelo es el motor de un coche; la Inteligencia es el coche
completo (motor + frenos + volante + manual de instrucciones). Nadie
"despliega un motor" en producción: despliegas el coche. Por eso la Fase
4 cambió los deployments: antes apuntaban a un `model_version_id`
(el motor); ahora apuntan a un `intelligence_version_id` (el coche).

### 2. Inmutabilidad: por qué las versiones no se editan

Cada `IntelligenceVersion` es **inmutable**: una vez publicada, jamás
cambia (campo `locked`). Esto no es burocracia, es la base de la
reproducibilidad científica y de la ingeniería seria:

- Si la v1 en producción decide `stop` con `progress_score <= 0.21`,
  esa regla queda congelada para siempre. Si mañana publicas v2 con
  `<= 0.35`, el deployment vivo **sigue sirviendo v1**. Cero sorpresas.
- El diff entre v1 y v2 (`components_added/removed/modified`) es la
  evidencia que un humano revisa antes de aprobar el cambio — igual que
  un code review, pero sobre el artefacto de IA.

En la industria esto se llama *immutable artifacts* (Docker images,
Nix, etc.). Rustenwer lo aplica al nivel semántico: no solo los bytes
son inmutables, también la arquitectura.

### 3. Arquitectura como snapshot validado

El `IntelligenceArchitecture` es un **grafo de ejecución declarativo**:
componentes + orden. La validación en el momento de publicar (no en
inferencia) implementa el principio *fail fast*: si tu regla
determinista no tiene `threshold`, o tu `model_version` apunta a un id
que no existe, te enteras al publicar — cuando puedes arreglarlo — no
a las 3am cuando el deployment falla.

Observa la distinción de tipos de error en `/infer`: 422 = tu input
está mal, 502 = nuestra ejecución falló, 501 = esa capacidad no existe
todavía. Cada capa nombra su propia culpa. Esto es diseño de APIs
honesto.

### 4. Componentes deterministas vs. aprendidos

La Fase 4 ejecuta dos familias de componentes en el mismo pipeline:

- **Deterministas** (`deterministic_rule`, `threshold`): lógica exacta,
  cero incertidumbre. `progress_score <= 0.21 → stop` siempre da lo
  mismo. Son la línea base honesta: si una regla de una línea resuelve
  tu problema, entrenar una red es desperdicio (esta es la tesis
  "baselines first" de la Fase 1).
- **Aprendidos** (`model_version`): pesos de PyTorch reconstruidos
  bit-a-bit desde el bundle exportado (`model.pt` + `config.json`).
  El test E2E verifica que la inferencia servida coincide con el
  cómputo torch crudo — la garantía de que el "motor" dentro del
  "coche" es exactamente el que se entrenó.

La lección: un sistema de IA real es **híbrido**. La pureza ("todo
debe ser una red neuronal") es una trampa; lo que importa es el
comportamiento medible del sistema completo.

### 5. Outputs machine-readable por primitiva

Cada primitiva de inteligencia define su **contrato de salida**:
terminación → `{decision, confidence}`, clasificación →
`{label, probabilities}`, ranking → `{score}`. Esto convierte a la
Inteligencia en un *componente componible*: otro sistema puede llamar
al endpoint y parsear la salida sin NLP, sin adivinar. Es la diferencia
entre "la IA me respondió un párrafo" y "la IA me devolvió un valor
tipado". Los sistemas que escalan hablan en contratos, no en prosa.

### 6. Abstracción de proveedor (InferenceProvider)

El endpoint `/infer` no sabe si la inferencia corre en CPU local, en
una GPU remota o vía una API externa: solo conoce la interfaz
`InferenceProvider`. Hoy `rustenwer_hosted` funciona y los otros dos
responden 501 honesto. Este es el patrón *Strategy* aplicado a
infraestructura: cuando Roger conecte una GPU real, registrará una
implementación nueva sin tocar ni una línea del endpoint. Diseñar el
seam (la costura) antes de necesitarlo es lo que permite crecer sin
reescribir.

### 7. Qué NO hace esta fase (y por qué es correcto)

- No hay LLM real (los componentes `prompt` devuelven 501 honesto).
- No hay `router`/`tool_graph` ejecutables (Fase 7).
- No hay promoción automática (Fase 6).

Cada "no" es deliberado: Rustenwer crece por fases donde cada fase deja
un sistema *completo y verificable*, no un andamiaje de promesas. La
disciplina de no pretender capacidades es lo que hace que el E2E de 21
checks signifique algo.
