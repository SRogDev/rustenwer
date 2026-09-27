"""Phase 5 tests — training-method knowledge (registry, recommendation,
research, new adapters, strategy integration).

TDD: written BEFORE the implementation (RED), then made to pass (GREEN).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from shared.domain import (
    BaselineReport,
    DiagnosisResult,
    IntelligencePrimitive,
    IntelligenceSpec,
    MethodValidationStatus,
    ResearchFinding,
    TrainingStrategy,
)
from shared.services.baselines import run_baselines
from shared.services.diagnosis import diagnose_spec
from shared.services.fixtures import termination_dataset_rows, termination_spec_fields
from shared.services.methods import (
    TRAINING_METHODS,
    detect_environment,
    recommend_methods,
    veto_contrastive_unless_similarity,
    veto_distillation_requires_labeled,
    veto_qlora_without_cuda,
    veto_unregistered_local,
)
from shared.services.strategy import propose_strategy

# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _spec(**overrides) -> IntelligenceSpec:
    fields: dict = {"id": uuid4(), "project_id": uuid4(), **termination_spec_fields()}
    fields.update(overrides)
    return IntelligenceSpec(**fields)


def _diagnosis(spec: IntelligenceSpec) -> DiagnosisResult:
    return diagnose_spec(spec)


def _baseline_report(spec: IntelligenceSpec) -> BaselineReport:
    rows = termination_dataset_rows()
    return run_baselines(spec, uuid4(), rows, label_column="label")


def _methods_by_slug() -> dict[str, object]:
    return {m.slug: m for m in TRAINING_METHODS}  # type: ignore[attr-defined]


_CPU_ENV = {"has_cuda": False, "has_unsloth": False}
_CUDA_ENV = {"has_cuda": True, "has_unsloth": True}


# --------------------------------------------------------------------------
# vetoes
# --------------------------------------------------------------------------


def test_qlora_vetoed_without_cuda() -> None:
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    rec = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    vetoed = {v.slug for v in rec.vetoed}
    assert "qlora" in vetoed
    reason = next(v.reason for v in rec.vetoed if v.slug == "qlora")
    assert "CUDA" in reason
    recommended = {r.slug for r in rec.recommended}
    assert "qlora" not in recommended


def test_qlora_allowed_with_cuda() -> None:
    """With CUDA present the qlora veto predicate stays silent (it may still
    lose on cost/latency ranking — the predicate is the veto under test)."""
    qlora = _methods_by_slug()["qlora"]
    assert veto_qlora_without_cuda(qlora, _CUDA_ENV) is None  # type: ignore[arg-type]
    assert veto_qlora_without_cuda(qlora, _CPU_ENV) is not None  # type: ignore[arg-type]


def test_embedding_ft_vetoed_no_adapter() -> None:
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    rec = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    vetoed = {v.slug: v.reason for v in rec.vetoed}
    assert "embedding-ft" in vetoed
    assert "adapter" in vetoed["embedding-ft"].lower()


def test_unregistered_local_predicate_is_data_driven() -> None:
    """Any method without a local adapter is vetoed — the predicate checks
    the method's own fields, not a hardcoded slug list."""
    by_slug = _methods_by_slug()
    assert (
        veto_unregistered_local(by_slug["embedding-ft"]) is not None  # type: ignore[arg-type]
    )
    assert (
        veto_unregistered_local(by_slug["classifier"]) is None  # type: ignore[arg-type]
    )


def test_contrastive_vetoed_for_pure_classification() -> None:
    spec = _spec(intelligence_primitive=IntelligencePrimitive.CLASSIFICATION)
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    rec = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    vetoed = {v.slug: v.reason for v in rec.vetoed}
    assert "contrastive" in vetoed
    reason = vetoed["contrastive"].lower()
    assert "classification" in reason or "similarity" in reason


def test_contrastive_recommended_for_ranking() -> None:
    spec = _spec(intelligence_primitive=IntelligencePrimitive.RANKING)
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    rec = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    recommended = {r.slug for r in rec.recommended}
    assert "contrastive" in recommended
    vetoed = {v.slug for v in rec.vetoed}
    assert "contrastive" not in vetoed


def test_contrastive_allowed_with_allow_generic() -> None:
    spec = _spec(intelligence_primitive=IntelligencePrimitive.CLASSIFICATION)
    contrastive = _methods_by_slug()["contrastive"]
    assert (
        veto_contrastive_unless_similarity(contrastive, spec, False)  # type: ignore[arg-type]
        is not None
    )
    assert (
        veto_contrastive_unless_similarity(contrastive, spec, True)  # type: ignore[arg-type]
        is None
    )


def test_distillation_requires_labeled_data() -> None:
    by_slug = _methods_by_slug()
    distill = by_slug["distillation"]
    # No baseline report at all: synthetic path always has labels (§plan).
    assert veto_distillation_requires_labeled(distill, None) is None  # type: ignore[arg-type]
    # Report with real labels: allowed.
    spec = _spec()
    baseline = _baseline_report(spec)
    assert veto_distillation_requires_labeled(distill, baseline) is None  # type: ignore[arg-type]
    # Report where nothing was labeled: vetoed.
    unlabeled = baseline.model_copy(
        update={
            "baselines": [
                b.model_copy(update={"accuracy": None, "predictions_evaluated": 0})
                for b in baseline.baselines
            ]
        }
    )
    reason = veto_distillation_requires_labeled(distill, unlabeled)  # type: ignore[arg-type]
    assert reason is not None
    assert "label" in reason.lower()


def test_rule13_short_circuits_recommendation() -> None:
    """Rule 13: 'none-deterministic' is NOT a training method — the engine
    short-circuits with an empty recommendation and a note."""
    spec = _spec(
        problem_statement="Sort by timestamp, filter by language, and validate the output format."
    )
    diagnosis = _diagnosis(spec)
    assert diagnosis.ml_necessary is False
    rec = recommend_methods(spec, diagnosis, None, _CPU_ENV)
    assert rec.recommended == []
    assert rec.vetoed == []
    assert rec.citations == []
    assert "none-deterministic" in rec.note.lower() or "rule 13" in rec.note.lower()


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------


def test_ranking_deterministic() -> None:
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    first = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    second = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    assert [r.slug for r in first.recommended] == [r.slug for r in second.recommended]
    assert [r.score for r in first.recommended] == [r.score for r in second.recommended]
    assert first.citations == second.citations


def test_spec_latency_requirement_changes_order() -> None:
    """Spec-driven ordering (§30, no global weights): a strict latency
    budget demotes the slower LLM-class method below the cheap MLP."""
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    relaxed = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    order_relaxed = [r.slug for r in relaxed.recommended]

    strict = _spec(latency_requirements={"max_ms_p50": 1.0})
    diagnosis2 = _diagnosis(strict)
    baseline2 = _baseline_report(strict)
    constrained = recommend_methods(strict, diagnosis2, baseline2, _CPU_ENV)
    order_constrained = [r.slug for r in constrained.recommended]

    assert "lora" in order_relaxed and "lora" in order_constrained
    assert "classifier" in order_relaxed and "classifier" in order_constrained
    # In the relaxed case the LLM-class method outranks the tiny MLP on
    # primitive fit; under a 1ms budget it falls behind it.
    assert order_relaxed.index("lora") < order_relaxed.index("classifier")
    assert order_constrained.index("classifier") < order_constrained.index("lora")


def test_citations_reference_ranked_methods() -> None:
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    rec = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    assert rec.citations
    ranked = {f"{r.slug}@{r.version}" for r in rec.recommended}
    assert set(rec.citations) == ranked
    assert all("@" in c for c in rec.citations)


def test_every_recommended_rank_has_reasons() -> None:
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    rec = recommend_methods(spec, diagnosis, baseline, _CPU_ENV)
    for rank in rec.recommended:
        assert rank.reasons, f"{rank.slug} has no reasons"
    for veto in rec.vetoed:
        assert veto.reason, f"{veto.slug} veto has no reason"


# --------------------------------------------------------------------------
# registry consistency
# --------------------------------------------------------------------------


def test_registry_every_validated_local_method_has_adapter() -> None:
    from app.methods.registry import METHOD_ADAPTERS, assert_registered

    for method in TRAINING_METHODS:  # type: ignore[attr-defined]
        if (
            method.status == MethodValidationStatus.VALIDATED
            and method.locally_runnable
        ):
            assert method.slug in METHOD_ADAPTERS, (
                f"VALIDATED+local method {method.slug} has no adapter entry"
            )
    assert_registered()  # the canonical consistency check


def test_registry_every_adapter_maps_to_a_method_row() -> None:
    from app.methods.registry import METHOD_ADAPTERS

    slugs = {m.slug for m in TRAINING_METHODS}  # type: ignore[attr-defined]
    for slug in METHOD_ADAPTERS:
        assert slug in slugs, f"adapter mapping {slug} has no method row"


def test_registry_adapters_exist_in_adapter_registry() -> None:
    from app.methods.registry import METHOD_ADAPTERS
    from app.training.adapters import ADAPTERS

    for slug, adapter_key in METHOD_ADAPTERS.items():
        assert adapter_key in ADAPTERS, (
            f"method {slug} maps to unknown adapter {adapter_key!r}"
        )


def test_seed_taxonomy_complete() -> None:
    slugs = {m.slug for m in TRAINING_METHODS}  # type: ignore[attr-defined]
    for slug in (
        "classifier",
        "lora",
        "qlora",
        "distillation",
        "contrastive",
        "instruction-tuning",
        "dpo",
        "rl-verifiable",
        "self-supervised",
        "synthetic-data",
        "curriculum",
        "evolutionary-search",
        "embedding-ft",
    ):
        assert slug in slugs, f"seed missing taxonomy entry {slug}"
    by_slug = {m.slug: m for m in TRAINING_METHODS}  # type: ignore[attr-defined]
    assert by_slug["classifier"].status == MethodValidationStatus.VALIDATED  # type: ignore[union-attr]
    assert by_slug["embedding-ft"].status == MethodValidationStatus.KNOWN  # type: ignore[union-attr]
    assert by_slug["embedding-ft"].implementation_templates == []  # type: ignore[union-attr]


def test_detect_environment_shape() -> None:
    env = detect_environment()
    assert set(env) == {"has_cuda", "has_unsloth"}
    assert isinstance(env["has_cuda"], bool)


# --------------------------------------------------------------------------
# research
# --------------------------------------------------------------------------


def test_research_finding_schema_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchFinding(technique="LoRA init trick")  # type: ignore[call-arg]


def test_research_seed_findings() -> None:
    from app.methods.research import get_research_repository

    repo = get_research_repository()
    findings = repo.list_findings()
    techniques = {f.technique for f in findings}
    assert "LoRA init trick" in techniques
    assert "QLoRA 4-bit" in techniques
    assert "Distillation soft targets" in techniques
    assert "Contrastive embeddings" in techniques
    for f in findings:
        assert f.useful_for and f.requires and f.advantage and f.weakness
        assert f.source and f.version >= 1


def test_research_repository_protocol() -> None:
    """The store is behind a Protocol so Supabase can swap in later."""

    from app.methods.research import ResearchFindingRepository

    class CustomRepo:
        def list_findings(self) -> list[ResearchFinding]:
            return []

        def add_finding(self, finding: ResearchFinding) -> ResearchFinding:
            return finding

    repo: ResearchFindingRepository = CustomRepo()
    assert repo.list_findings() == []


# --------------------------------------------------------------------------
# adapters: distillation learns, contrastive learns
# --------------------------------------------------------------------------


def _train_ctx(adapter, tmp_path: Path, strategy: TrainingStrategy, hp: dict):
    from app.training.adapters import AdapterContext, TrainContext

    actx = AdapterContext(strategy=strategy, workdir=tmp_path, hyperparameters=hp, seed=7)
    dataset_info = adapter.prepare(actx)
    tctx = TrainContext(
        strategy=strategy, workdir=tmp_path, hyperparameters=hp, seed=7
    )
    return actx, tctx, dataset_info


def _strategy_for(method: str, hp: dict) -> TrainingStrategy:
    return TrainingStrategy(
        training_method=method,
        objective="phase-5 smoke test",
        hyperparameters=hp,
    )


def test_distillation_learns_and_beats_scratch() -> None:
    """The distillation thesis: a student trained with soft targets from a
    teacher beats (or matches) the same student trained from scratch on the
    same seeded task."""
    from app.training.adapters import (
        ClassifierAdapter,
        DistillationAdapter,
        get_adapter,
    )

    teacher_hp = {"n_train": 1200, "n_val": 300, "epochs": 10, "lr": 0.05,
                  "batch_size": 128, "hidden": [128, 64], "n_features": 20}
    student_hp = {"n_train": 1200, "n_val": 300, "epochs": 10, "lr": 0.05,
                  "batch_size": 128, "n_features": 20}

    adapter = get_adapter("distillation")
    assert isinstance(adapter, DistillationAdapter)

    import tempfile

    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        # Student via distillation.
        distill_strategy = _strategy_for("distillation", {
            **student_hp,
            "teacher_hp": teacher_hp,
            "student_hidden": [32],
            "temperature": 4.0,
            "alpha": 0.5,
        })
        actx, tctx, info = _train_ctx(adapter, Path(d1), distill_strategy,
                                     distill_strategy.hyperparameters)
        assert adapter.validate(distill_strategy) == []
        result = adapter.train(tctx, info)
        distill_acc = float(result["val_accuracy"])

        # Same student architecture trained from scratch.
        scratch = ClassifierAdapter()
        scratch_strategy = _strategy_for("classifier", {**student_hp, "hidden": [32]})
        actx2, tctx2, info2 = _train_ctx(scratch, Path(d2), scratch_strategy,
                                        scratch_strategy.hyperparameters)
        scratch_result = scratch.train(tctx2, info2)
        scratch_acc = float(scratch_result["val_accuracy"])

    assert distill_acc > 0.6, f"distilled student did not learn: {distill_acc}"
    assert distill_acc >= scratch_acc, (
        f"distillation thesis violated: distill={distill_acc:.3f} < scratch={scratch_acc:.3f}"
    )


def test_contrastive_learns() -> None:
    """Contrastive adapter: nearest-centroid retrieval accuracy on val > 0.6."""
    from app.training.adapters import ContrastiveAdapter, get_adapter

    adapter = get_adapter("contrastive")
    assert isinstance(adapter, ContrastiveAdapter)

    import tempfile

    with tempfile.TemporaryDirectory() as d:
        hp = {"n_train": 1200, "n_val": 300, "epochs": 12, "lr": 0.05,
              "batch_size": 128, "embedding_dim": 32, "n_features": 20}
        strategy = _strategy_for("contrastive", hp)
        actx, tctx, info = _train_ctx(adapter, Path(d), strategy, hp)
        assert adapter.validate(strategy) == []
        assert adapter.supports_provider("local") is None
        result = adapter.train(tctx, info)
        assert float(result["val_accuracy"]) > 0.6, result
        metrics = adapter.evaluate(actx, result["state"], info)
        assert metrics["val_accuracy"] > 0.6


def test_distillation_and_contrastive_validate_rejects_wrong_method() -> None:
    from app.training.adapters import ContrastiveAdapter, DistillationAdapter

    assert DistillationAdapter().validate(_strategy_for("lora", {}))
    assert ContrastiveAdapter().validate(_strategy_for("classifier", {}))


# --------------------------------------------------------------------------
# strategy integration
# --------------------------------------------------------------------------


def test_strategy_carries_method_citations() -> None:
    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    strategy = propose_strategy(spec, diagnosis, baseline)
    assert strategy.method_citations, "no method citations on the strategy"
    assert strategy.training_method in {
        c.split("@")[0] for c in strategy.method_citations
    }, "training_method must be the top recommendation"
    assert strategy.vetoed_methods, "vetoes must be recorded as data"
    veto_slugs = {v["slug"] for v in strategy.vetoed_methods}
    assert "qlora" in veto_slugs  # no CUDA in this environment
    assert all("reason" in v for v in strategy.vetoed_methods)


def test_strategy_no_training_path_has_empty_citations() -> None:
    spec = _spec(
        problem_statement="Sort by timestamp, filter by language, and validate the output format."
    )
    diagnosis = _diagnosis(spec)
    assert diagnosis.ml_necessary is False
    strategy = propose_strategy(spec, diagnosis, None)
    assert strategy.training_method == "none-deterministic"
    assert strategy.method_citations == []
    assert strategy.vetoed_methods == []
    assert strategy.no_training_justification


# --------------------------------------------------------------------------
# HTTP surface
# --------------------------------------------------------------------------


def test_methods_endpoints() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    headers = {"Authorization": "Bearer test-token"}

    resp = client.get("/api/v1/methods", headers=headers)
    assert resp.status_code == 200, resp.text
    methods = resp.json()
    assert isinstance(methods, list) and len(methods) >= 13

    resp = client.get("/api/v1/methods", params={"status": "VALIDATED"}, headers=headers)
    assert resp.status_code == 200
    assert all(m["status"] == "VALIDATED" for m in resp.json())

    resp = client.get("/api/v1/methods", params={"category": "peft"}, headers=headers)
    assert resp.status_code == 200
    assert {m["slug"] for m in resp.json()} == {"lora", "qlora"}

    resp = client.get("/api/v1/methods/lora", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current"]["slug"] == "lora"
    assert [v["version"] for v in body["versions"]] == sorted(
        v["version"] for v in body["versions"]
    )

    resp = client.get("/api/v1/methods/nope", headers=headers)
    assert resp.status_code == 404

    resp = client.get("/api/v1/methods")
    assert resp.status_code in (401, 403)


def test_recommend_endpoint() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    headers = {"Authorization": "Bearer test-token"}

    spec = _spec()
    diagnosis = _diagnosis(spec)
    baseline = _baseline_report(spec)
    resp = client.post(
        "/api/v1/methods/recommend",
        json={
            "spec": spec.model_dump(mode="json"),
            "diagnosis": diagnosis.model_dump(mode="json"),
            "baseline_report": baseline.model_dump(mode="json"),
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recommended"] and body["citations"]
    vetoed_slugs = {v["slug"] for v in body["vetoed"]}
    assert "qlora" in vetoed_slugs  # no CUDA on this machine
    top = body["recommended"][0]
    assert {"slug", "version", "score", "reasons"} <= set(top)


def test_research_endpoint() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    headers = {"Authorization": "Bearer test-token"}

    resp = client.get("/api/v1/research", headers=headers)
    assert resp.status_code == 200, resp.text
    findings = resp.json()
    assert len(findings) == 4
    assert all(
        {"technique", "useful_for", "requires", "advantage", "weakness", "source", "version"}
        <= set(f)
        for f in findings
    )


def test_recommend_without_diagnosis_is_generic() -> None:
    """Null diagnosis (spec not diagnosed yet) must not 422.

    Contract with the web client (MethodRecommendationPanel): diagnosis may
    be null. The engine ranks generically from the spec's own
    intelligence_primitive and says so in `note`.
    """
    spec = _spec()
    rec = recommend_methods(spec, None, None, detect_environment())
    assert rec.recommended, "expected a generic ranking without diagnosis"
    assert rec.citations
    assert "No diagnosis provided" in rec.note


def test_recommend_endpoint_without_diagnosis() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    headers = {"Authorization": "Bearer test-token"}

    spec = _spec()
    resp = client.post(
        "/api/v1/methods/recommend",
        json={"spec": spec.model_dump(mode="json"), "diagnosis": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recommended"] and body["citations"]
    assert "No diagnosis provided" in body["note"]
