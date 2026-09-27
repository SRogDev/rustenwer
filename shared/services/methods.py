"""Phase 5 — training-method knowledge: pure, framework-free recommendation.

The registry query that replaces the hardcoded "embedding-ft if small else
lora" branch in `shared/services/strategy.py` (plan §3): given
(IntelligenceSpec, DiagnosisResult, BaselineReport, environment), return
ranked compatible methods plus explicit vetoes with reasons.

Vetoes are DATA, not prose — each is a small named predicate. The vetoed
list is the negative-search seed for Phase 7.

No FastAPI / torch imports: both `shared/services/strategy.py` (used by the
LangGraph agents) and `api/app/methods/` (HTTP) call this module.

Ranking (deterministic, §30 — no global weights):
    score = fit * 10 + spec_text_bonus - cost_penalty - latency_penalty

- `fit`: 10 when the spec's primitive is in the method's supported_tasks,
  4 when it is in compatible_objectives, 1 otherwise. Capability dominates.
- `spec_text_bonus`: +3 per method strength matching the spec's own wording
  (stem-tolerant, capped at +9) — the spec's words break ties between
  equally fitting methods.
- `cost_penalty`: 0.5 * rough_cost_per_hour_usd, tripled under a strict spec
  cost budget (max_usd_per_1k < 0.01). Cost is a tiebreaker, not a veto.
- `latency_penalty`: 20 when the method's typical p50 latency exceeds the
  spec's latency budget. A hard requirement demotes, honestly.

Ties break on slug ascending, so the same input always yields the same
order.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.domain import (
    BaselineReport,
    DiagnosisResult,
    IntelligenceSpec,
    MethodCategory,
    MethodRank,
    MethodRecommendation,
    MethodValidationStatus,
    MethodVeto,
    TrainingMethod,
)

# --------------------------------------------------------------------------
# Environment detection (done once, passed in — keeps recommend pure)
# --------------------------------------------------------------------------


def detect_environment() -> dict[str, bool]:
    """Detect the execution environment: CUDA + unsloth availability."""
    has_cuda = False
    try:
        import torch

        has_cuda = bool(torch.cuda.is_available())
    except ImportError:
        has_cuda = False
    try:
        import unsloth  # noqa: F401

        has_unsloth = True
    except ImportError:
        has_unsloth = False
    return {"has_cuda": has_cuda, "has_unsloth": has_unsloth}


# --------------------------------------------------------------------------
# Seed catalog (plan §10 taxonomy, §11 structured representation)
# --------------------------------------------------------------------------


def _method(**kwargs: Any) -> TrainingMethod:
    return TrainingMethod(**kwargs)


TRAINING_METHODS: list[TrainingMethod] = [
    _method(
        slug="classifier",
        name="Supervised MLP classifier",
        category=MethodCategory.SUPERVISED,
        version=1,
        status=MethodValidationStatus.VALIDATED,
        supported_tasks=["classification", "termination", "decision", "prediction"],
        data_requirements={"min_rows": 100, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": False,
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 0.02,
            "typical_latency_ms_p50": 0.5,
        },
        strengths=[
            "cheap and fast to train on CPU",
            "strong on tabular low-dimensional tasks",
            "simple to debug and export",
        ],
        weaknesses=[
            "no transfer from pretraining",
            "needs enough labeled rows to generalize",
        ],
        failure_modes=[
            "collapses to the majority class on imbalanced data",
            "overfits tiny datasets without regularization",
        ],
        compatible_architectures=["mlp", "single_model"],
        compatible_objectives=["accuracy", "low_latency", "low_cost"],
        evaluation_requirements=["held-out accuracy", "calibration"],
        implementation_templates=["classifier"],
        locally_runnable=True,
        notes="Validated in Phase 2: trains a real torch MLP on CPU (ring task).",
    ),
    _method(
        slug="lora",
        name="LoRA fine-tune (frozen base + low-rank adapters)",
        category=MethodCategory.PEFT,
        version=1,
        status=MethodValidationStatus.VALIDATED,
        supported_tasks=[
            "classification",
            "termination",
            "decision",
            "ranking",
            "routing",
            "critique",
        ],
        data_requirements={"min_rows": 200, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": False,  # LoRA math runs on CPU on our tiny base
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 4.41,
            "typical_latency_ms_p50": 25.0,
        },
        strengths=[
            "generalizes beyond exact matches",
            "reuses a pretrained base",
            "only a small fraction of parameters trains",
        ],
        weaknesses=[
            "needs a suitable pretrained base model",
            "heavier inference than a tiny MLP",
        ],
        failure_modes=[
            "rank too low underfits; rank too high overfits small data",
            "wrong base model for the domain",
        ],
        compatible_architectures=["lora-adapted-transformer", "single_model"],
        compatible_objectives=["accuracy", "generalization"],
        evaluation_requirements=["held-out accuracy", "calibration", "robustness"],
        implementation_templates=["lora"],
        locally_runnable=True,
        notes="Validated in Phase 2: real LoRA (W0 + BA·α/r) on a tiny frozen "
        "base, CPU-capable. Production use targets LLM-class bases on GPU.",
    ),
    _method(
        slug="qlora",
        name="QLoRA (4-bit quantized base + LoRA)",
        category=MethodCategory.PEFT,
        version=1,
        status=MethodValidationStatus.VALIDATED,
        supported_tasks=[
            "classification",
            "termination",
            "decision",
            "ranking",
            "routing",
            "critique",
        ],
        data_requirements={"min_rows": 200, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": True,
            "min_vram_gb": 8,
            "rough_cost_per_hour_usd": 4.41,
            "typical_latency_ms_p50": 25.0,
        },
        strengths=[
            "fine-tunes multi-billion-parameter models on one GPU",
            "memory win: 4-bit base + small adapters",
            "generalizes beyond exact matches",
        ],
        weaknesses=["requires CUDA + unsloth/bitsandbytes", "quantization noise"],
        failure_modes=[
            "4-bit quantization degrades sensitive tasks",
            "import/CUDA mismatch fails loudly, never silently",
        ],
        compatible_architectures=["qlora-adapted-transformer", "single_model"],
        compatible_objectives=["accuracy", "generalization", "memory_efficiency"],
        evaluation_requirements=["held-out accuracy", "calibration", "robustness"],
        implementation_templates=["qlora"],
        locally_runnable=False,  # needs CUDA; the digitalocean provider is its home
        notes="Guarded real path (Phase 2): validate()/train() refuse without "
        "CUDA + unsloth instead of pretending.",
    ),
    _method(
        slug="distillation",
        name="Knowledge distillation (teacher → student)",
        category=MethodCategory.DISTILLATION,
        version=1,
        status=MethodValidationStatus.VALIDATED,
        supported_tasks=[
            "classification",
            "termination",
            "decision",
            "prediction",
            "ranking",
        ],
        data_requirements={"min_rows": 100, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": False,
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 0.05,
            "typical_latency_ms_p50": 1.5,
        },
        strengths=[
            "student inherits the teacher's generalization at a fraction of the cost",
            "soft targets regularize small students",
            "deployable tiny model",
        ],
        weaknesses=[
            "pays teacher training cost up front",
            "needs labeled data for the teacher",
        ],
        failure_modes=[
            "a weak teacher teaches bad habits (student ≤ teacher)",
            "temperature too high washes out the signal",
        ],
        compatible_architectures=["teacher-student", "single_model"],
        compatible_objectives=["accuracy", "low_latency", "low_cost", "small_model"],
        evaluation_requirements=["held-out accuracy vs teacher and vs scratch"],
        implementation_templates=["distillation"],
        locally_runnable=True,
        notes="Validated in Phase 5: teacher MLP trained on blobs, student "
        "distilled with temperature-scaled soft targets; the thesis "
        "(distilled ≥ from-scratch) is pinned by test.",
    ),
    _method(
        slug="contrastive",
        name="Contrastive representation learning",
        category=MethodCategory.CONTRASTIVE,
        version=1,
        status=MethodValidationStatus.VALIDATED,
        supported_tasks=[
            "ranking",
            "retrieval",
            "search",
            "selection",
            "filtering",
            "memory_selection",
        ],
        data_requirements={"min_rows": 200, "labeled": True, "pairwise": True},
        compute_requirements={
            "gpu_required": False,
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 0.03,
            "typical_latency_ms_p50": 2.0,
        },
        strengths=[
            "embeddings capture similarity structure",
            "nearest-centroid retrieval is cheap at inference",
            "works when labels are relative, not absolute",
        ],
        weaknesses=[
            "needs pair/batch construction",
            "not a classifier — needs a retrieval head",
        ],
        failure_modes=[
            "representation collapse without enough negatives",
            "temperature too low makes training unstable",
        ],
        compatible_architectures=["embedding_tower", "embedding_knn_threshold"],
        compatible_objectives=["retrieval_quality", "low_latency"],
        evaluation_requirements=["nearest-centroid retrieval accuracy"],
        implementation_templates=["contrastive"],
        locally_runnable=True,
        notes="Validated in Phase 5: InfoNCE-style loss over same-class pairs; "
        "evaluated as nearest-centroid retrieval on val.",
    ),
    _method(
        slug="instruction-tuning",
        name="Instruction tuning",
        category=MethodCategory.SUPERVISED,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["routing", "critique", "planning", "decision"],
        data_requirements={"min_rows": 1000, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": True,
            "min_vram_gb": 16,
            "rough_cost_per_hour_usd": 4.41,
            "typical_latency_ms_p50": 30.0,
        },
        strengths=["aligns a base model to follow task instructions"],
        weaknesses=["needs curated instruction data"],
        failure_modes=["instruction data leakage into eval"],
        compatible_architectures=["instruction-tuned-transformer"],
        compatible_objectives=["instruction_following"],
        evaluation_requirements=["instruction-following evals"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet.",
    ),
    _method(
        slug="dpo",
        name="Direct Preference Optimization",
        category=MethodCategory.PREFERENCE_OPTIMIZATION,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["critique", "routing", "decision"],
        data_requirements={"min_rows": 500, "labeled": True, "pairwise": True},
        compute_requirements={
            "gpu_required": True,
            "min_vram_gb": 16,
            "rough_cost_per_hour_usd": 4.41,
            "typical_latency_ms_p50": 30.0,
        },
        strengths=["aligns to pairwise preferences without a reward model"],
        weaknesses=["needs high-quality preference pairs"],
        failure_modes=["preference data bias becomes model bias"],
        compatible_architectures=["dpo-aligned-transformer"],
        compatible_objectives=["preference_alignment"],
        evaluation_requirements=["win-rate vs reference on preference evals"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet.",
    ),
    _method(
        slug="rl-verifiable",
        name="RL with verifiable rewards (RLVR)",
        category=MethodCategory.REINFORCEMENT_LEARNING,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["planning", "optimization", "verification"],
        data_requirements={"min_rows": 500, "labeled": False, "pairwise": False},
        compute_requirements={
            "gpu_required": True,
            "min_vram_gb": 24,
            "rough_cost_per_hour_usd": 4.47,
            "typical_latency_ms_p50": 30.0,
        },
        strengths=["optimizes directly against a verifiable reward"],
        weaknesses=["needs a trustworthy verifier", "sample-inefficient"],
        failure_modes=["reward hacking against an imperfect verifier"],
        compatible_architectures=["rl-policy"],
        compatible_objectives=["verifiable_reward"],
        evaluation_requirements=["verifier pass rate on held-out tasks"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet.",
    ),
    _method(
        slug="self-supervised",
        name="Self-supervised pretraining",
        category=MethodCategory.SELF_SUPERVISED,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["retrieval", "classification", "memory_selection"],
        data_requirements={"min_rows": 10000, "labeled": False, "pairwise": False},
        compute_requirements={
            "gpu_required": True,
            "min_vram_gb": 24,
            "rough_cost_per_hour_usd": 4.47,
            "typical_latency_ms_p50": 2.0,
        },
        strengths=["learns from unlabeled data at scale"],
        weaknesses=["needs large unlabeled corpora", "long training"],
        failure_modes=["objective mismatch with the downstream task"],
        compatible_architectures=["pretrained-encoder"],
        compatible_objectives=["representation_quality"],
        evaluation_requirements=["linear probe / downstream evals"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet.",
    ),
    _method(
        slug="synthetic-data",
        name="Synthetic data generation",
        category=MethodCategory.SYNTHETIC_DATA,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["classification", "decision", "planning"],
        data_requirements={"min_rows": 0, "labeled": False, "pairwise": False},
        compute_requirements={
            "gpu_required": False,
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 0.10,
            "typical_latency_ms_p50": 0.5,
        },
        strengths=["creates labeled data where none exists"],
        weaknesses=["distribution shift vs real data"],
        failure_modes=["model collapse on self-generated loops"],
        compatible_architectures=["generator-plus-learner"],
        compatible_objectives=["data_coverage"],
        evaluation_requirements=["real-data validation of synthetic-trained models"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet. Our "
        "synthetic blobs are smoke data, not this method.",
    ),
    _method(
        slug="curriculum",
        name="Curriculum learning",
        category=MethodCategory.CURRICULUM,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["classification", "planning", "optimization"],
        data_requirements={"min_rows": 1000, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": False,
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 0.05,
            "typical_latency_ms_p50": 1.0,
        },
        strengths=["orders examples easy→hard for faster convergence"],
        weaknesses=["needs a difficulty measure"],
        failure_modes=["wrong curriculum is worse than random order"],
        compatible_architectures=["curriculum-scheduler"],
        compatible_objectives=["sample_efficiency"],
        evaluation_requirements=["convergence speed vs shuffled baseline"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet.",
    ),
    _method(
        slug="evolutionary-search",
        name="Evolutionary architecture search",
        category=MethodCategory.SEARCH_EVOLUTIONARY,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["optimization", "selection"],
        data_requirements={"min_rows": 500, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": True,
            "min_vram_gb": 16,
            "rough_cost_per_hour_usd": 4.47,
            "typical_latency_ms_p50": 5.0,
        },
        strengths=["discovers non-obvious architectures"],
        weaknesses=["very expensive", "hard to reproduce"],
        failure_modes=["search overfits the validation set"],
        compatible_architectures=["evolved-architecture"],
        compatible_objectives=["architecture_discovery"],
        evaluation_requirements=["held-out eval of the discovered architecture"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry (plan §10): no local adapter yet.",
    ),
    _method(
        slug="embedding-ft",
        name="Embedding fine-tune (small encoder + head)",
        category=MethodCategory.SUPERVISED,
        version=1,
        status=MethodValidationStatus.KNOWN,
        supported_tasks=["classification", "termination", "decision", "filtering"],
        data_requirements={"min_rows": 50, "labeled": True, "pairwise": False},
        compute_requirements={
            "gpu_required": False,
            "min_vram_gb": 0,
            "rough_cost_per_hour_usd": 0.05,
            "typical_latency_ms_p50": 2.0,
        },
        strengths=["cheap on small labeled sets", "reuses a sentence encoder"],
        weaknesses=["encoder choice dominates the outcome"],
        failure_modes=["encoder/domain mismatch"],
        compatible_architectures=["encoder-plus-head"],
        compatible_objectives=["accuracy", "low_cost"],
        evaluation_requirements=["held-out accuracy"],
        implementation_templates=[],
        locally_runnable=False,
        notes="KNOWN taxonomy entry: the old hardcoded strategy branch "
        "referenced it, but no adapter is registered yet — vetoed until one "
        "exists.",
    ),
]


# --------------------------------------------------------------------------
# Veto predicates — named, data-driven, each returns a reason or None
# --------------------------------------------------------------------------


def veto_qlora_without_cuda(
    method: TrainingMethod, environment: Mapping[str, bool]
) -> str | None:
    """QLoRA needs a CUDA GPU; without one it is not a real option.

    Mirrors QLoRAAdapter.supports_provider (plan §3).
    """
    if method.slug != "qlora":
        return None
    if not environment.get("has_cuda", False):
        return (
            "no CUDA here; use the digitalocean provider — "
            "QLoRA requires a CUDA GPU with unsloth/bitsandbytes"
        )
    return None


def veto_unregistered_local(method: TrainingMethod) -> str | None:
    """A method with no local adapter registered cannot be proposed for
    local execution — the catalog stays honest about the gap."""
    if method.slug in ("qlora",):  # handled by its own predicate
        return None
    if method.status == MethodValidationStatus.KNOWN or not method.locally_runnable:
        return (
            f"no local adapter registered yet for '{method.slug}' "
            f"({method.status.value.lower()}; implementation_templates is empty)"
        )
    return None


def veto_distillation_requires_labeled(
    method: TrainingMethod, baseline_report: BaselineReport | None
) -> str | None:
    """Distillation trains a teacher on labels; without labeled data the
    teacher cannot exist. The synthetic path always has labels (§plan)."""
    if method.slug != "distillation":
        return None
    labeled = _has_labeled_signal(baseline_report)
    if not labeled:
        return "distillation requires labeled data and the dataset shows no labels"
    return None


def _has_labeled_signal(baseline_report: BaselineReport | None) -> bool:
    if baseline_report is None:
        return True  # synthetic path: labels always available
    return any(
        (b.accuracy is not None) or (b.predictions_evaluated > 0)
        for b in baseline_report.baselines
    )


# Primitives where similarity/ranking structure is the point of the task.
_SIMILARITY_PRIMITIVES = frozenset(
    {"ranking", "retrieval", "search", "selection", "filtering", "memory_selection"}
)


def veto_contrastive_unless_similarity(
    method: TrainingMethod, spec: IntelligenceSpec, allow_generic: bool
) -> str | None:
    """Contrastive learning is a similarity tool; for a pure classification
    task it adds machinery without a job — unless the caller explicitly
    allows generic candidates."""
    if method.slug != "contrastive":
        return None
    if allow_generic:
        return None
    primitive = spec.intelligence_primitive.value
    if primitive in _SIMILARITY_PRIMITIVES:
        return None
    return (
        f"contrastive embeddings target similarity/ranking structure; "
        f"primitive '{primitive}' is not similarity-ish — pass "
        "allow_generic=true to consider it anyway"
    )


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------


def _spec_latency_budget_ms(spec: IntelligenceSpec) -> float | None:
    reqs = spec.latency_requirements or {}
    for key in ("max_ms_p50", "latency_budget_ms", "p50_ms"):
        value = reqs.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _spec_text(spec: IntelligenceSpec) -> str:
    parts = [
        spec.problem_statement or "",
        spec.description or "",
        spec.evaluation_definition or "",
    ]
    return " ".join(parts).lower()


def _word_variants(word: str) -> list[str]:
    """Naive stem variants so 'generalizes' matches 'generalize' in spec text."""
    variants = [word]
    if word.endswith("sses"):
        variants.append(word[:-2])
    elif word.endswith("ies"):
        variants.append(word[:-3] + "y")
    elif word.endswith("s") and not word.endswith("ss"):
        variants.append(word[:-1])
    return variants


def _strength_matches(strength: str, text: str) -> bool:
    """A strength matches when at least 2 of its first 3 content words
    appear in the spec text (stem-tolerant)."""
    words = [w.strip(".,;:()") for w in strength.lower().split() if len(w.strip(".,;:()")) > 4]
    candidates = words[:3]
    if not candidates:
        return False
    hits = sum(
        1 for w in candidates if any(v in text for v in _word_variants(w))
    )
    return hits >= min(2, len(candidates))


def _score_method(method: TrainingMethod, spec: IntelligenceSpec) -> tuple[float, list[str]]:
    """Deterministic spec-driven score + human-readable reasons.

    score = fit * 10 + text_bonus - cost_penalty - latency_penalty

    - fit: 10 for a supported_tasks hit, 4 for compatible_objectives, 1
      otherwise. Capability dominates: the right tool for the primitive wins.
    - text_bonus: +3 per method strength matching the spec's own wording
      (capped at +9). The spec's words — not a global weight — break ties
      between equally fitting methods.
    - cost_penalty: 0.5 * rough_cost_per_hour_usd, tripled when the spec
      declares a strict cost budget (max_usd_per_1k < 0.01). Cost is a
      tiebreaker, not a veto — the fit tier decides first.
    - latency_penalty: 20 when the method's typical p50 latency exceeds the
      spec's latency budget. A hard requirement demotes, honestly.
    """
    reasons: list[str] = []
    primitive = spec.intelligence_primitive.value

    if primitive in method.supported_tasks:
        fit = 10
        reasons.append(f"fits primitive '{primitive}' (supported_tasks)")
    elif primitive in method.compatible_objectives:
        fit = 4
        reasons.append(f"compatible with primitive '{primitive}' (compatible_objectives)")
    else:
        fit = 1
        reasons.append(f"generic fallback for primitive '{primitive}'")

    text = _spec_text(spec)
    matched = [s for s in method.strengths if _strength_matches(s, text)]
    text_bonus = min(len(matched) * 3, 9)
    if matched:
        reasons.append(f"spec text matches strengths: {', '.join(matched)}")

    cost_per_hour = float(method.compute_requirements.get("rough_cost_per_hour_usd", 0.0))
    cost_reqs = spec.cost_requirements or {}
    max_per_1k = cost_reqs.get("max_usd_per_1k")
    cost_weight = 3.0 if isinstance(max_per_1k, (int, float)) and max_per_1k < 0.01 else 1.0
    cost_penalty = 0.5 * cost_weight * cost_per_hour
    if cost_penalty:
        reasons.append(f"compute cost ${cost_per_hour:.2f}/h (weight {cost_weight})")

    latency_penalty = 0.0
    budget = _spec_latency_budget_ms(spec)
    typical = method.compute_requirements.get("typical_latency_ms_p50")
    if budget is not None and isinstance(typical, (int, float)) and typical > budget:
        latency_penalty = 20.0
        reasons.append(
            f"typical p50 latency {typical}ms exceeds the spec budget of {budget}ms"
        )

    score = fit * 10 + text_bonus - cost_penalty - latency_penalty
    return score, reasons


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def recommend_methods(
    spec: IntelligenceSpec,
    diagnosis: DiagnosisResult | None,
    baseline_report: BaselineReport | None,
    environment: Mapping[str, bool],
    allow_generic: bool = False,
) -> MethodRecommendation:
    """Rank compatible training methods for (spec, diagnosis); veto the rest.

    Rule 13: when the diagnosis concludes ML is not necessary, the engine
    short-circuits — 'none-deterministic' is not a training method, so the
    recommendation is empty with a note.

    diagnosis may be None (spec not diagnosed yet): the engine then assumes
    ML is necessary and ranks generically from the spec's own
    intelligence_primitive, with a note saying the recommendation sharpens
    once a diagnosis exists.
    """
    if diagnosis is not None and not diagnosis.ml_necessary:
        return MethodRecommendation(
            recommended=[],
            vetoed=[],
            citations=[],
            note=(
                "Rule 13: diagnosis concluded ML is not necessary — "
                "'none-deterministic' is not a training method, so no method "
                "is recommended. Ship a deterministic implementation instead."
            ),
        )

    recommended: list[MethodRank] = []
    vetoed: list[MethodVeto] = []
    for method in TRAINING_METHODS:
        reason = (
            veto_qlora_without_cuda(method, environment)
            or veto_contrastive_unless_similarity(method, spec, allow_generic)
            or veto_distillation_requires_labeled(method, baseline_report)
            or veto_unregistered_local(method)
        )
        if reason is not None:
            vetoed.append(MethodVeto(slug=method.slug, version=method.version, reason=reason))
            continue
        score, reasons = _score_method(method, spec)
        recommended.append(
            MethodRank(slug=method.slug, version=method.version, score=score, reasons=reasons)
        )

    # Deterministic order: score desc, slug asc (stable across runs).
    recommended.sort(key=lambda r: (-r.score, r.slug))
    citations = [f"{r.slug}@{r.version}" for r in recommended]
    note = ""
    if diagnosis is None:
        note = (
            "No diagnosis provided — ranked generically from the spec's "
            "intelligence_primitive. Diagnose the spec for a sharper "
            "recommendation."
        )
    return MethodRecommendation(
        recommended=recommended, vetoed=vetoed, citations=citations, note=note
    )


# --------------------------------------------------------------------------
# Strategy defaults per method — what propose_strategy fills in once the
# engine has picked a winner (plan §3: the strategy agent DECIDES).
# --------------------------------------------------------------------------

STRATEGY_DEFAULTS: dict[str, dict[str, Any]] = {
    "classifier": {
        "model_family": "mlp-small",
        "architecture": {"type": "classifier", "hidden": [64], "activation": "relu"},
        "hyperparameters": {"epochs": 5, "lr": 0.05, "batch_size": 128},
    },
    "distillation": {
        "model_family": "mlp-student-distilled",
        "architecture": {
            "type": "distillation",
            "teacher_hidden": [128, 64],
            "student_hidden": [32],
        },
        "hyperparameters": {
            "epochs": 10,
            "lr": 0.05,
            "batch_size": 128,
            "temperature": 4.0,
            "alpha": 0.5,
        },
    },
    "lora": {
        "model_family": "llama-3-8b-class",
        "architecture": {"type": "lora", "base": "Llama-3-8B-class instruct model"},
        "hyperparameters": {"rank": 16, "epochs": 3, "lr": 2e-4},
    },
    "qlora": {
        "model_family": "llama-3-8b-class-4bit",
        "architecture": {"type": "qlora", "base": "Llama-3-8B-class instruct model"},
        "hyperparameters": {"rank": 16, "max_steps": 60, "lr": 2e-4},
    },
    "contrastive": {
        "model_family": "embedding-tower",
        "architecture": {"type": "contrastive", "tower": [64], "embedding_dim": 32},
        "hyperparameters": {"epochs": 10, "lr": 0.05, "batch_size": 128},
    },
}


def strategy_defaults_for(slug: str) -> dict[str, Any]:
    """Model family / architecture / hyperparameters for a recommended method."""
    defaults = STRATEGY_DEFAULTS.get(slug)
    if defaults is not None:
        return defaults
    return {
        "model_family": f"{slug}-model",
        "architecture": {"type": slug},
        "hyperparameters": {"epochs": 5, "lr": 0.05},
    }
