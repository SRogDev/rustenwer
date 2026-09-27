# Phase 5 — Training Method Knowledge (backend completion record)

Date: 2026-09-27. Scope: backend only (the `/methods` web UI was built in
parallel by the web builder against `shared/types.ts`).

## What changed

Method selection is now a registry query, not a hardcoded branch:

- **Seeded catalog**: 13 methods from the plan §10 taxonomy. `VALIDATED`
  (plan §57): classifier, lora, qlora, distillation, contrastive. `KNOWN`:
  instruction-tuning, dpo, rl-verifiable, self-supervised, synthetic-data,
  curriculum, evolutionary-search, embedding-ft (honestly vetoed — no local
  adapter registered).
- **Pure recommendation engine** (`shared/services/methods.py`, no
  FastAPI/torch imports at module level): `recommend_methods()` applies
  named veto predicates (qlora needs CUDA; unregistered methods;
  distillation needs labeled data; contrastive only for similarity-ish
  tasks or `allow_generic`) then ranks deterministically from the spec —
  no global weights (§30). `propose_strategy` now takes the engine's top
  rank instead of the hardcoded embedding-ft→lora heuristic; strategies
  carry `method_citations` + `vetoed_methods` — exactly the negative-search
  data Phase 7 will consume.
- **HTTP** (`api/app/methods/`, mounted at `/api/v1` behind bearer auth):
  `GET /methods` (+ `?category=`/`?status=`), `GET /methods/{slug}` →
  `{slug, versions, current}`, `POST /methods/recommend` → full
  `MethodRecommendation`, `GET /research` (4 seeded findings, §52).
- **New adapters** (real CPU, behind `assert_registered`): `DistillationAdapter`
  (teacher MLP → temperature-scaled soft-target student; thesis test:
  student beats 0.7 where a small net alone cannot) and `ContrastiveAdapter`
  (SupCon loss over same-class in-batch positives; nearest-centroid
  retrieval eval ≈ 0.95 on the ring task).
- **Migration** `005_phase5_methods.sql`: `training_methods`,
  `adapter_registry`, `research_findings` (canonical schema; in-memory repos
  remain the runtime until credentials exist).

## Test evidence

- TDD RED: `test_phase5_methods.py` written first — collection error (no
  Phase 5 types existed).
- GREEN: 29/29 Phase 5 tests pass. Two real bugs caught by learning tests:
  1. contrastive tower used `F.normalize(..., dim=1)` — for `(B,K,D)`
     negative tensors this normalizes over the K axis, and the model gamed
     the loss instead of learning (contradictory sim measurements);
     fixed to `dim=-1`;
  2. 1-positive InfoNCE collapsed to a constant embedding (loss → log(1+K));
     switched to supervised-contrastive (all same-class in-batch samples
     as positives) — retrieval accuracy 0.51 → 0.95.
- Full suite: **271 passed** (242 pre-existing + 29 new), `ruff check`
  clean from `api/`.

## Open items (coordinator)

- Apply migration 005 when a Supabase project exists.
- `qlora` adapter is code-complete but `locally_runnable=False` (needs
  CUDA/unsloth/bitsandbytes) — honest 501-style behavior retained.

## Phase 6 entry points (Candidate Experiment Engine)

Phase 6 builds on exactly these Phase-5 seams — do not redesign them:

- **Method citations are the candidate's training contract.** A Phase-6
  `Candidate` should reference `{method_slug, method_version}` (e.g.
  `"distillation@1"`) plus the full `TrainingStrategy` the engine's
  `STRATEGY_DEFAULTS` produced. `strategy_defaults_for(slug)` in
  `shared/services/methods.py` is the canonical "method → model family /
  architecture / hyperparameters" mapping — the Candidate Generator
  should call it, not invent its own.
- **Vetoes are negative-search data.** `MethodRecommendation.vetoed`
  (slug, version, reason) is already structured — Phase 7's Experiment
  Memory can persist these rows verbatim as "ruled out" evidence.
- **New search dimensions for the Experiment Engine:** `TRAINING_METHODS`
  is a finite, versioned set — Random/Grid/LLM-proposal search over
  `method × hyperparameters × dataset config` is now well-defined. The
  deterministic `_score_method` ranking gives the LLM-proposal strategy a
  prior to beat.
- **Promotion policy hook (§58):** `baseline_bar` on `TrainingStrategy`
  + `MethodRank.score` give the promotion gate a cost/quality prior before
  any GPU is spent.
- **Files to extend:** `shared/services/methods.py` (pure engine —
  keep it framework-free), `api/app/methods/registry.py` (seed list),
  `supabase/migrations/005_phase5_methods.sql` (new method versions are
  NEW rows, never edits).

---

## Deep-dive: destilación y aprendizaje contrastivo (lección en español)

Esta fase implementa dos técnicas reales de machine learning. Aquí va la
explicación a fondo.

### 1. Knowledge distillation (destilación de conocimiento)

**La idea.** Entrenas primero una red "maestra" (*teacher*) grande y
precisa. Luego entrenas una red "estudiante" (*student*) pequeña — no con
las etiquetas duras (0/1), sino con las *probabilidades suavizadas* del
maestro. La intuición: las etiquetas duras dicen "esto es un gato" y nada
más; el maestro dice "90% gato, 8% perro, 2% zorro" — esa distribución
contiene el *conocimiento oscuro* (*dark knowledge*): qué clases se parecen
entre sí. El estudiante aprende mucho más de esa "segunda opinión" que de
un sí/no binario.

**El truco matemático: temperatura.** Los logits del maestro `z` se pasan
por softmax con temperatura `T`:

`softmax(z/T)` — con `T > 1` la distribución se "aplana" (suaviza): las
probabilidades pequeñas crecen y las grandes bajan, revelando más
estructura de similitud entre clases. Con `T = 1` es el softmax normal.

**La pérdida** combina dos términos:
`L = α · KL(student || teacher_suavizado) + (1-α) · CE(student, etiquetas)`.
El primer término (divergencia KL) copia al maestro; el segundo ancla al
estudiante a la realidad. En nuestro adapter: maestro MLP de 2 capas
ocultas → estudiante de 1 capa oculta, `T=2.0`, `α=0.7`.

**El test que lo "prueba".** El test no verifica que la destilación exista
— verifica la *tesis* de la destilación: el estudiante destilado supera
0.7 de accuracy en validación. Si la implementación no transmitiera
conocimiento real (p. ej., si el término KL estuviera roto), el estudiante
pequeño no llegaría y el test fallaría. Eso es un *learning test*: no
prueba código, prueba una afirmación científica.

### 2. Aprendizaje contrastivo (contrastive learning)

**La idea.** En vez de predecir etiquetas, aprendes *representaciones*:
un espacio de embeddings donde los ejemplos similares quedan cerca y los
distintos lejos. Después, clasificar es trivial: calculas el centroide
(promedio) de los embeddings de cada clase en validación y asignas cada
punto a la clase de su centroide más cercano (*nearest-centroid*).

**InfoNCE.** Para cada ejemplo "ancla", tienes 1 positivo (similar) y K
negativos (distintos). La pérdida es una clasificación de K+1 opciones:

`L = -log( exp(s(a,p)/τ) / (exp(s(a,p)/τ) + Σ exp(s(a,nᵢ)/τ)) )`

donde `s` es similitud coseno y `τ` la temperatura. Minimizarla = acercar
el positivo y alejar los negativos.

**El bug real que encontramos (lección importante).** La torre de
embeddings normalizaba con `F.normalize(x, dim=1)`. Para tensores de
forma `(B, K, D)` (batch × K negativos × dimensión), `dim=1` normaliza
sobre el eje K — mezcla los K negativos entre sí en vez de normalizar
cada vector de embedding. El modelo "aprendía" a explotar esa
normalización errónea: la pérdida bajaba pero los embeddings no separaban
nada (las mediciones de similitud se contradecían entre sí). Con `dim=-1`
se normaliza cada vector individualmente, que es lo correcto.

**El colapso (segunda lección).** Con 1 solo positivo por ancla, el modelo
colapsaba a un embedding *constante*: todos los vectores idénticos. ¿Por
qué? Es un mínimo local estable: si todo es igual, la pérdida vale
exactamente `log(1+K)` y el gradiente no tiene de dónde agarrarse para
salir — la señal de "1 positivo aleatorio de la misma clase" es demasiado
débil al inicio, cuando los embeddings son aleatorios.

**La solución: supervised contrastive (SupCon).** En vez de 1 positivo,
* todos los ejemplos de la misma clase dentro del batch son positivos*:

`L = logsumexp(sims de todos) − logsumexp(sims de positivos)`

La señal de agrupamiento es ~64× más fuerte por ancla (batch 128, 2
clases balanceadas) y el modelo sí encuentra la estructura del anillo:
accuracy de recuperación 0.51 → 0.95. Lección general: en aprendizaje
contrastivo, la *construcción del batch* (cuántos positivos/negativos ve
cada ancla) importa tanto como la arquitectura.

### 3. Por qué el motor de recomendación es "puro"

`shared/services/methods.py` no importa FastAPI ni torch. Esto es
deliberado: los agentes LangGraph (que viven en `agents/`) y la API
comparten el *mismo* motor de decisión sin duplicar lógica ni arrastrar
dependencias del servidor al grafo de agentes. Es el patrón
"núcleo puro, adaptadores finos": la inteligencia en funciones puras,
los frameworks en los bordes.
