"""TrainingMethodAdapter tests (TDD: RED first, then implement).

Contract under test (plan §54):
  validate(strategy) -> [errors]; supports_provider(provider) -> err|None
  prepare(ctx) -> dataset_info (materializes dataset in workdir)
  estimate(strategy) -> CostEstimate
  train(ctx, dataset_info) -> result (real torch loop; emits metric/checkpoint events)
  save/load_checkpoint round-trip; evaluate -> metrics; export -> files
  ClassifierAdapter + LoRAAdapter genuinely train on CPU.
  QLoRAAdapter is real Unsloth code but requires CUDA -> honest error on CPU.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from shared.domain import TrainingStrategy

from app.training.adapters import (
    ADAPTERS,
    AdapterContext,
    AdapterEnvironmentError,
    ClassifierAdapter,
    CostEstimate,
    LoRAAdapter,
    QLoRAAdapter,
    TrainContext,
    get_adapter,
)


def _strategy(**overrides: Any) -> TrainingStrategy:
    base: dict[str, Any] = {
        "model_family": "tiny-mlp",
        "architecture": {"type": "mlp", "hidden": [32]},
        "training_method": "classifier",
        "objective": "separate synthetic blobs",
        "hyperparameters": {"epochs": 10, "lr": 0.1, "batch_size": 64, "seed": 7,
                             "n_train": 400, "n_val": 100},
        "evaluation_plan": "holdout accuracy",
        "compute_budget": {"max_gpu_hours": 0.1, "max_cost_usd": 1.0},
        "rationale": "test strategy",
    }
    base.update(overrides)
    return TrainingStrategy(**base)


def _ctx(strategy: TrainingStrategy, workdir: Path, **overrides: Any) -> TrainContext:
    events: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "strategy": strategy,
        "workdir": workdir,
        "hyperparameters": dict(strategy.hyperparameters),
        "seed": 7,
        "emit": events.append,
        "should_stop": lambda: None,
        "resume_from": None,
    }
    kwargs.update(overrides)
    ctx = TrainContext(**kwargs)
    ctx.events = events  # type: ignore[attr-defined]  # test introspection hook
    return ctx


def _metric_epochs(events: list[dict]) -> dict[int, float]:
    out: dict[int, float] = {}
    for e in events:
        if e.get("type") == "metric" and e.get("name") == "loss_epoch":
            out[e["epoch"]] = e["value"]
    return out


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


def test_registry_contains_expected_adapters() -> None:
    assert {"classifier", "lora", "qlora"} <= set(ADAPTERS)


def test_get_adapter_unknown_method_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("svm-from-1998")


def test_get_adapter_none_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter(None)


# --------------------------------------------------------------------------
# ClassifierAdapter
# --------------------------------------------------------------------------


def test_classifier_validate_ok() -> None:
    assert ClassifierAdapter().validate(_strategy()) == []


def test_classifier_validate_rejects_wrong_method() -> None:
    errors = ClassifierAdapter().validate(_strategy(training_method="lora"))
    assert errors, "expected a validation error for a lora strategy on the classifier adapter"


def test_classifier_validate_rejects_nonsense_hyperparams() -> None:
    errors = ClassifierAdapter().validate(_strategy(hyperparameters={"epochs": 0}))
    assert errors


def test_classifier_supports_local_and_digitalocean() -> None:
    # The math runs anywhere; credential checks happen at submit() time.
    assert ClassifierAdapter().supports_provider("local") is None
    assert ClassifierAdapter().supports_provider("digitalocean") is None


def test_classifier_estimate_is_sane() -> None:
    est = ClassifierAdapter().estimate(_strategy())
    assert isinstance(est, CostEstimate)
    assert est.est_params > 0
    assert est.est_seconds > 0
    assert est.est_cost_usd >= 0


def test_classifier_prepare_materializes_dataset(tmp_path: Path) -> None:
    strategy = _strategy()
    info = ClassifierAdapter().prepare(
        AdapterContext(strategy=strategy, workdir=tmp_path,
                       hyperparameters=dict(strategy.hyperparameters), seed=7)
    )
    assert info["n_train"] == 400
    assert info["n_val"] == 100
    assert info["n_features"] == 20
    assert info["n_classes"] == 2
    assert Path(info["path"]).exists()


def test_classifier_prepare_is_deterministic(tmp_path: Path) -> None:
    strategy = _strategy()
    a = ClassifierAdapter().prepare(
        AdapterContext(strategy=strategy, workdir=tmp_path / "a",
                       hyperparameters=dict(strategy.hyperparameters), seed=7)
    )
    b = ClassifierAdapter().prepare(
        AdapterContext(strategy=strategy, workdir=tmp_path / "b",
                       hyperparameters=dict(strategy.hyperparameters), seed=7)
    )
    import torch

    da, db = torch.load(a["path"], weights_only=True), torch.load(b["path"], weights_only=True)
    assert torch.equal(da["X_train"], db["X_train"])


def test_classifier_train_loss_decreases(tmp_path: Path) -> None:
    strategy = _strategy()
    adapter = ClassifierAdapter()
    ctx = _ctx(strategy, tmp_path)
    info = adapter.prepare(
        AdapterContext(strategy=strategy, workdir=tmp_path,
                       hyperparameters=ctx.hyperparameters, seed=7)
    )
    result = adapter.train(ctx, info)
    losses = _metric_epochs(ctx.events)
    assert len(losses) == 10
    first, last = losses[min(losses)], losses[max(losses)]
    assert last < first, f"loss did not decrease: {losses}"
    assert result["val_accuracy"] > 0.75
    assert result["epochs"] == 10
    ckpt_events = [e for e in ctx.events if e.get("type") == "checkpoint"]
    assert len(ckpt_events) == 10
    assert Path(ckpt_events[0]["path"]).exists()


def test_classifier_train_respects_stop_request(tmp_path: Path) -> None:
    strategy = _strategy(hyperparameters={"epochs": 10, "lr": 0.05, "batch_size": 64,
                                          "seed": 7, "n_train": 400, "n_val": 100})
    adapter = ClassifierAdapter()
    state = {"calls": 0}

    def stop_after_first_epoch() -> str | None:
        state["calls"] += 1
        return "cancel" if state["calls"] > 12 else None  # ~1 epoch of batches

    ctx = _ctx(strategy, tmp_path, should_stop=stop_after_first_epoch)
    info = adapter.prepare(
        AdapterContext(strategy=strategy, workdir=tmp_path,
                       hyperparameters=ctx.hyperparameters, seed=7)
    )
    result = adapter.train(ctx, info)
    assert result["stopped"] == "cancel"
    assert result["epochs"] < 10


def test_classifier_resume_continues_from_checkpoint(tmp_path: Path) -> None:
    strategy = _strategy()
    adapter = ClassifierAdapter()
    prep = AdapterContext(strategy=strategy, workdir=tmp_path,
                          hyperparameters=dict(strategy.hyperparameters), seed=7)
    info = adapter.prepare(prep)

    ctx1 = _ctx(strategy, tmp_path)
    adapter.train(ctx1, info)
    ckpts = sorted((tmp_path / "checkpoints").glob("ckpt-*.pt"))
    assert len(ckpts) == 10

    strategy2 = _strategy(hyperparameters={"epochs": 12, "lr": 0.1, "batch_size": 64,
                                           "seed": 7, "n_train": 400, "n_val": 100})
    ctx2 = _ctx(strategy2, tmp_path, resume_from=ckpts[-1])
    result = adapter.train(ctx2, info)
    assert result["resumed_from_epoch"] == 9
    assert result["epochs"] == 12
    # Epochs 10 and 11 ran after resume (0-indexed).
    assert set(_metric_epochs(ctx2.events)) == {10, 11}


def test_classifier_evaluate_and_export(tmp_path: Path) -> None:
    strategy = _strategy()
    adapter = ClassifierAdapter()
    prep = AdapterContext(strategy=strategy, workdir=tmp_path,
                          hyperparameters=dict(strategy.hyperparameters), seed=7)
    info = adapter.prepare(prep)
    ctx = _ctx(strategy, tmp_path)
    adapter.train(ctx, info)
    ckpt = sorted((tmp_path / "checkpoints").glob("ckpt-*.pt"))[-1]
    state = adapter.load_checkpoint(ckpt)
    metrics = adapter.evaluate(prep, state, info)
    assert metrics["val_accuracy"] > 0.75

    out = tmp_path / "export"
    exported = adapter.export(prep, state, info, out)
    assert Path(exported["files"]["model"]).exists()
    assert Path(exported["files"]["config"]).exists()


# --------------------------------------------------------------------------
# LoRAAdapter (real LoRA math, CPU-capable)
# --------------------------------------------------------------------------


def test_lora_validate_ok() -> None:
    assert LoRAAdapter().validate(_strategy(training_method="lora",
                                            hyperparameters={"epochs": 1, "rank": 4})) == []


def test_lora_trains_with_fewer_trainable_params(tmp_path: Path) -> None:
    strategy = _strategy(training_method="lora",
                         hyperparameters={"epochs": 12, "lr": 0.1, "batch_size": 64,
                                          "seed": 7, "n_train": 400, "n_val": 100, "rank": 4})
    adapter = LoRAAdapter()
    ctx = _ctx(strategy, tmp_path)
    info = adapter.prepare(
        AdapterContext(strategy=strategy, workdir=tmp_path,
                       hyperparameters=ctx.hyperparameters, seed=7)
    )
    result = adapter.train(ctx, info)
    assert result["trainable_params"] < result["total_params"]
    losses = _metric_epochs(ctx.events)
    assert losses[1] < losses[0]
    assert result["val_accuracy"] > 0.7


# --------------------------------------------------------------------------
# QLoRAAdapter (real Unsloth path; honest CPU refusal)
# --------------------------------------------------------------------------


def test_qlora_validate_fails_on_cpu_without_cuda() -> None:
    errors = QLoRAAdapter().validate(_strategy(training_method="qlora"))
    assert any("CUDA" in e for e in errors), f"expected CUDA complaint, got {errors}"


def test_qlora_provider_support() -> None:
    adapter = QLoRAAdapter()
    assert adapter.supports_provider("local") is not None  # CPU-only here
    assert adapter.supports_provider("digitalocean") is None


def test_qlora_train_raises_environment_error_on_cpu(tmp_path: Path) -> None:
    strategy = _strategy(training_method="qlora")
    adapter = QLoRAAdapter()
    ctx = _ctx(strategy, tmp_path)
    info = {"n_train": 10, "n_val": 4, "n_features": 20, "n_classes": 2, "path": "x"}
    with pytest.raises(AdapterEnvironmentError):
        adapter.train(ctx, info)
