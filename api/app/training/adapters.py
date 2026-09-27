"""TrainingMethodAdapter implementations (plan §54).

The Training Strategy Agent DECIDES (produces a TrainingStrategy); these
adapters EXECUTE (Rule 3). Three adapters ship in Phase 2:

- ClassifierAdapter — real torch MLP classifier, CPU-capable. The default
  local-execution workhorse and the e2e proof that the whole lifecycle works.
- LoRAAdapter — real LoRA (frozen base + trainable low-rank A/B matrices)
  on a tiny torch base model. LoRA math needs no GPU, so this genuinely
  trains on CPU.
- QLoRAAdapter — real Unsloth 4-bit QLoRA code path (import-guarded).
  Requires CUDA + unsloth/bitsandbytes, so on a CPU-only machine validate()
  and train() fail with an explicit, actionable error instead of pretending.
  The digitalocean provider is its real home.

All adapters train on a deterministic synthetic dataset in Phase 2 (seeded
blobs / JSONL). Real user datasets plug into prepare() in Phase 3+.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from shared.domain import TrainingStrategy

from app.training.checkpoints import load_checkpoint as _load_checkpoint
from app.training.checkpoints import save_checkpoint as _save_checkpoint

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class AdapterEnvironmentError(RuntimeError):
    """The adapter's code is real but this machine can't run it.

    Raised instead of silently degrading (e.g. QLoRA without CUDA).
    """


class AdapterValidationError(ValueError):
    """A TrainingStrategy failed adapter validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("invalid training strategy: " + "; ".join(self.errors))


# --------------------------------------------------------------------------
# Contexts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CostEstimate:
    est_seconds: float
    est_cost_usd: float
    est_params: int
    notes: str = ""


@dataclass
class AdapterContext:
    strategy: TrainingStrategy
    workdir: Path
    hyperparameters: dict[str, Any]
    seed: int = 0


@dataclass
class TrainContext:
    strategy: TrainingStrategy
    workdir: Path
    hyperparameters: dict[str, Any]
    seed: int = 0
    emit: Callable[[dict[str, Any]], None] = field(default=lambda e: None)
    should_stop: Callable[[], str | None] = field(default=lambda: None)
    resume_from: Path | None = None


class TrainingMethodAdapter(Protocol):
    """Plan §54 adapter interface: validate/prepare/estimate/train/..."""

    name: str

    def validate(self, strategy: TrainingStrategy) -> list[str]:
        """Strategy errors for THIS adapter; empty means OK."""
        ...

    def supports_provider(self, provider: str) -> str | None:
        """None when runnable on provider, else a human-readable reason."""
        ...

    def prepare(self, ctx: AdapterContext) -> dict[str, Any]:
        """Materialize the training dataset in ctx.workdir; return dataset_info."""
        ...

    def estimate(
        self, strategy: TrainingStrategy, dataset_info: dict[str, Any] | None = None
    ) -> CostEstimate:
        ...

    def train(self, ctx: TrainContext, dataset_info: dict[str, Any]) -> dict[str, Any]:
        """Run the training loop; emit metric/checkpoint events via ctx.emit."""
        ...

    def save_checkpoint(self, state: dict[str, Any], path: Path) -> None:
        ...

    def load_checkpoint(self, path: Path) -> dict[str, Any]:
        ...

    def evaluate(
        self, ctx: AdapterContext, state: dict[str, Any], dataset_info: dict[str, Any]
    ) -> dict[str, float]:
        ...

    def export(
        self,
        ctx: AdapterContext,
        state: dict[str, Any],
        dataset_info: dict[str, Any],
        out_dir: Path,
    ) -> dict[str, Any]:
        ...


# --------------------------------------------------------------------------
# Torch helpers
# --------------------------------------------------------------------------


def _torch():
    try:
        import torch
    except ImportError as exc:
        raise AdapterEnvironmentError(
            "torch is not installed. Install the training extras: "
            "pip install -r api/requirements-train.txt"
        ) from exc
    return torch


def _synthetic_blobs(n_train: int, n_val: int, n_features: int, seed: int) -> dict[str, Any]:
    """Deterministic 2-class tabular data with a circular (nonlinear) boundary.

    The radius threshold is the Rayleigh median sqrt(2*ln2) ~= 1.1774, so
    classes are ~50/50 and the network must learn the ring — a majority
    classifier scores only ~0.5. Seeded, so prepare() is reproducible.
    """
    torch = _torch()
    gen = torch.Generator().manual_seed(seed)
    threshold = (2 * 0.6931471805599453) ** 0.5  # sqrt(2 ln 2)

    def _split(n: int) -> tuple:
        X = torch.randn(n, n_features, generator=gen)
        radius = X[:, :2].pow(2).sum(dim=1).sqrt()
        y = (radius > threshold).long()
        return X, y

    X_train, y_train = _split(n_train)
    X_val, y_val = _split(n_val)
    return {
        "X_train": X_train, "y_train": y_train,
        "X_val": X_val, "y_val": y_val,
        "n_features": n_features, "n_classes": 2,
    }


def _prepare_blobs(ctx: AdapterContext, n_features: int = 20) -> dict[str, Any]:
    """Shared prepare(): seeded blobs -> workdir/dataset.pt (idempotent)."""
    torch = _torch()
    hp = ctx.hyperparameters
    n_train = int(hp.get("n_train", 2000))
    n_val = int(hp.get("n_val", 400))
    path = ctx.workdir / "dataset.pt"
    if not path.exists():
        ctx.workdir.mkdir(parents=True, exist_ok=True)
        data = _synthetic_blobs(n_train, n_val, n_features, ctx.seed)
        torch.save(data, str(path))
    return {
        "n_train": n_train, "n_val": n_val,
        "n_features": n_features, "n_classes": 2,
        "path": str(path),
    }


def _count_params(model: Any) -> tuple[int, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total, trainable


# --------------------------------------------------------------------------
# Shared supervised torch loop (classifier + LoRA)
# --------------------------------------------------------------------------


class _TorchSupervisedAdapter:
    """Real SGD training loop shared by the CPU-capable adapters.

    Subclasses only define build_model(); everything else — batching,
    checkpointing, resume, metrics — is identical and genuinely executed.
    """

    name: str = "torch-supervised"

    # -- to override ---------------------------------------------------

    def build_model(self, dataset_info: dict[str, Any], hp: dict[str, Any], seed: int):
        raise NotImplementedError

    # -- checkpoint passthrough ----------------------------------------

    def save_checkpoint(self, state: dict[str, Any], path: Path) -> None:
        _save_checkpoint(state, path)

    def load_checkpoint(self, path: Path) -> dict[str, Any]:
        return _load_checkpoint(path)

    # -- training -------------------------------------------------------

    def train(self, ctx: TrainContext, dataset_info: dict[str, Any]) -> dict[str, Any]:
        torch = _torch()
        hp = ctx.hyperparameters
        epochs = int(hp.get("epochs", 5))
        lr = float(hp.get("lr", 0.05))
        batch_size = int(hp.get("batch_size", 128))

        data = torch.load(dataset_info["path"], map_location="cpu", weights_only=True)
        X_train, y_train = data["X_train"], data["y_train"]
        n = X_train.shape[0]

        torch.manual_seed(ctx.seed)
        model = self.build_model(dataset_info, hp, ctx.seed)
        # SGD with momentum: plain SGD stalls on the ring boundary (the
        # smoke task); momentum is the standard fix, exposed as hyperparameters.
        opt = torch.optim.SGD(
            [p for p in model.parameters() if p.requires_grad],
            lr=lr,
            momentum=float(hp.get("momentum", 0.9)),
        )
        loss_fn = torch.nn.CrossEntropyLoss()

        ckpt_dir = ctx.workdir / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        start_epoch, step = 0, 0
        resumed_from_epoch: int | None = None
        if ctx.resume_from is not None:
            state = self.load_checkpoint(Path(ctx.resume_from))
            model.load_state_dict(state["model"])
            opt.load_state_dict(state["optimizer"])
            start_epoch = int(state["epoch"]) + 1
            step = int(state["step"])
            resumed_from_epoch = int(state["epoch"])
            if "rng" in state:
                torch.set_rng_state(state["rng"])
            ctx.emit({"type": "log",
                      "line": f"resumed from checkpoint epoch {state['epoch']}"})

        gen = torch.Generator().manual_seed(ctx.seed + 999)
        final_loss, val_acc = float("nan"), 0.0
        for epoch in range(start_epoch, epochs):
            model.train()
            perm = torch.randperm(n, generator=gen)
            epoch_loss, batches, last_grad_norm = 0.0, 0, 0.0
            for i in range(0, n, batch_size):
                stop = ctx.should_stop()
                if stop is not None:  # graceful stop: checkpoint, then report
                    ckpt = ckpt_dir / f"ckpt-{epoch:04d}.pt"
                    # Label the checkpoint with the last COMPLETED epoch, so a
                    # resume re-runs the interrupted epoch instead of skipping
                    # it (weights/optimizer/rng are the live mid-epoch state).
                    last_done = epoch - 1
                    self.save_checkpoint(
                        {"epoch": last_done, "step": step,
                         "model": model.state_dict(),
                         "optimizer": opt.state_dict(),
                         "rng": torch.get_rng_state()}, ckpt)
                    ctx.emit({"type": "checkpoint", "id": ckpt.stem, "epoch": last_done,
                              "step": step, "path": str(ckpt)})
                    return {"stopped": stop, "epochs": epoch,
                            "resumed_from_epoch": resumed_from_epoch}
                idx = perm[i:i + batch_size]
                xb, yb = X_train[idx], y_train[idx]
                opt.zero_grad()
                loss = loss_fn(model(xb), yb)
                loss.backward()
                last_grad_norm = float(
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0))
                opt.step()
                epoch_loss += float(loss.item())
                batches += 1
                step += 1

            final_loss = epoch_loss / max(batches, 1)
            val_acc = self._accuracy(model, data)
            ctx.emit({"type": "metric", "name": "loss_epoch",
                      "epoch": epoch, "step": step, "value": final_loss})
            ctx.emit({"type": "metric", "name": "val_accuracy",
                      "epoch": epoch, "step": step, "value": val_acc})
            ctx.emit({"type": "metric", "name": "lr",
                      "epoch": epoch, "step": step, "value": lr})
            ctx.emit({"type": "metric", "name": "grad_norm",
                      "epoch": epoch, "step": step, "value": last_grad_norm})
            ctx.emit({"type": "log",
                      "line": f"epoch {epoch}: loss={final_loss:.4f} "
                              f"val_acc={val_acc:.4f}"})

            ckpt = ckpt_dir / f"ckpt-{epoch:04d}.pt"
            self.save_checkpoint(
                {"epoch": epoch, "step": step,
                 "model": model.state_dict(),
                 "optimizer": opt.state_dict(),
                 "rng": torch.get_rng_state()}, ckpt)
            ctx.emit({"type": "checkpoint", "id": ckpt.stem, "epoch": epoch,
                      "step": step, "path": str(ckpt)})

        total, trainable = _count_params(model)
        return {"epochs": epochs, "final_loss": final_loss,
                "val_accuracy": val_acc, "total_params": total,
                "trainable_params": trainable,
                "resumed_from_epoch": resumed_from_epoch}

    # -- evaluation / export --------------------------------------------

    def _accuracy(self, model: Any, data: dict[str, Any]) -> float:
        torch = _torch()
        model.eval()
        with torch.no_grad():
            pred = model(data["X_val"]).argmax(dim=1)
            return float((pred == data["y_val"]).float().mean().item())

    def evaluate(
        self, ctx: AdapterContext, state: dict[str, Any], dataset_info: dict[str, Any]
    ) -> dict[str, float]:
        torch = _torch()
        data = torch.load(dataset_info["path"], map_location="cpu", weights_only=True)
        torch.manual_seed(ctx.seed)
        model = self.build_model(dataset_info, ctx.hyperparameters, ctx.seed)
        model.load_state_dict(state["model"])
        model.eval()
        with torch.no_grad():
            logits = model(data["X_val"])
            loss = float(torch.nn.CrossEntropyLoss()(logits, data["y_val"]).item())
        return {"val_accuracy": self._accuracy(model, data), "val_loss": loss}

    def export(
        self,
        ctx: AdapterContext,
        state: dict[str, Any],
        dataset_info: dict[str, Any],
        out_dir: Path,
    ) -> dict[str, Any]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / "model.pt"
        _save_checkpoint(state, model_path)
        config = {
            "training_method": self.name,
            "architecture": ctx.strategy.architecture,
            "n_features": dataset_info["n_features"],
            "n_classes": dataset_info["n_classes"],
            "hyperparameters": ctx.hyperparameters,
            "seed": ctx.seed,
        }
        config_path = out_dir / "config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return {"files": {"model": str(model_path), "config": str(config_path)}}


# --------------------------------------------------------------------------
# ClassifierAdapter — tiny MLP, fully trained
# --------------------------------------------------------------------------


class ClassifierAdapter(_TorchSupervisedAdapter):
    """Small MLP classifier trained with full SGD (CPU-capable)."""

    name = "classifier"

    def validate(self, strategy: TrainingStrategy) -> list[str]:
        errors: list[str] = []
        if strategy.training_method != "classifier":
            errors.append(
                f"classifier adapter needs training_method='classifier', "
                f"got {strategy.training_method!r}"
            )
        hp = strategy.hyperparameters or {}
        try:
            if int(hp.get("epochs", 5)) < 1:
                errors.append("hyperparameters.epochs must be >= 1")
        except (TypeError, ValueError):
            errors.append("hyperparameters.epochs must be an integer >= 1")
        try:
            if float(hp.get("lr", 0.05)) <= 0:
                errors.append("hyperparameters.lr must be > 0")
        except (TypeError, ValueError):
            errors.append("hyperparameters.lr must be a positive number")
        return errors

    def supports_provider(self, provider: str) -> str | None:
        # CPU math runs anywhere torch runs; whether the provider can actually
        # provision (e.g. DO_TOKEN present) is checked at submit() time.
        return None

    def prepare(self, ctx: AdapterContext) -> dict[str, Any]:
        return _prepare_blobs(ctx)

    def estimate(
        self, strategy: TrainingStrategy, dataset_info: dict[str, Any] | None = None
    ) -> CostEstimate:
        torch = _torch()
        hp = strategy.hyperparameters or {}
        n_train = int(hp.get("n_train", 2000))
        epochs = int(hp.get("epochs", 5))
        info = dataset_info or {"n_features": 20, "n_classes": 2}
        torch.manual_seed(0)
        total, _ = _count_params(self.build_model(info, hp, 0))
        # Rough CPU model: ~2ms per sample per epoch on a small MLP.
        est_seconds = epochs * (n_train / 1000) * 2.0
        return CostEstimate(
            est_seconds=est_seconds,
            est_cost_usd=est_seconds / 3600 * 0.02,
            est_params=total,
            notes="rough CPU estimate for the tiny MLP smoke model",
        )

    def build_model(self, dataset_info: dict[str, Any], hp: dict[str, Any], seed: int):
        torch = _torch()
        hidden = (hp.get("hidden") or [64])
        if isinstance(hidden, int):
            hidden = [hidden]
        layers: list[Any] = []
        prev = int(dataset_info["n_features"])
        torch.manual_seed(seed)
        for h in hidden:
            layers += [torch.nn.Linear(prev, int(h)), torch.nn.ReLU()]
            prev = int(h)
        layers.append(torch.nn.Linear(prev, int(dataset_info["n_classes"])))
        return torch.nn.Sequential(*layers)


# --------------------------------------------------------------------------
# LoRAAdapter — real LoRA on a tiny frozen base (CPU-capable)
# --------------------------------------------------------------------------


class _LoRALinear:
    """Namespace for the LoRA linear module (built with torch lazily)."""

    @staticmethod
    def make(torch, in_features: int, out_features: int, rank: int, alpha: float):
        import torch.nn as nn

        class LoRALinear(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.base = nn.Linear(in_features, out_features)
                for p in self.base.parameters():
                    p.requires_grad_(False)  # frozen base — only A/B train
                self.A = nn.Parameter(torch.empty(rank, in_features))
                self.B = nn.Parameter(torch.zeros(out_features, rank))
                nn.init.kaiming_uniform_(self.A, a=5 ** 0.5)
                self.scaling = alpha / rank

            def forward(self, x):  # type: ignore[no-untyped-def]
                return self.base(x) + (x @ self.A.t() @ self.B.t()) * self.scaling

        return LoRALinear()


class LoRAAdapter(_TorchSupervisedAdapter):
    """Real LoRA: frozen base MLP + trainable rank-r adapters.

    The math is identical to LLM LoRA (W_eff = W0 + BA·α/r); only the base
    is tiny so it trains on CPU. Proves the LoRA path end-to-end.
    """

    name = "lora"

    def validate(self, strategy: TrainingStrategy) -> list[str]:
        errors: list[str] = []
        if strategy.training_method != "lora":
            errors.append(
                f"lora adapter needs training_method='lora', "
                f"got {strategy.training_method!r}"
            )
        hp = strategy.hyperparameters or {}
        try:
            if int(hp.get("rank", 4)) < 1:
                errors.append("hyperparameters.rank must be >= 1")
        except (TypeError, ValueError):
            errors.append("hyperparameters.rank must be an integer >= 1")
        return errors

    def supports_provider(self, provider: str) -> str | None:
        # LoRA math runs anywhere torch runs; provider provisioning
        # (credentials etc.) is checked at submit() time.
        return None

    def prepare(self, ctx: AdapterContext) -> dict[str, Any]:
        return _prepare_blobs(ctx)

    def estimate(
        self, strategy: TrainingStrategy, dataset_info: dict[str, Any] | None = None
    ) -> CostEstimate:
        torch = _torch()
        hp = strategy.hyperparameters or {}
        torch.manual_seed(0)
        total, trainable = _count_params(
            self.build_model(dataset_info or {"n_features": 20, "n_classes": 2}, hp, 0)
        )
        epochs = int(hp.get("epochs", 5))
        n_train = int(hp.get("n_train", 2000))
        est_seconds = epochs * (n_train / 1000) * 2.5
        return CostEstimate(
            est_seconds=est_seconds,
            est_cost_usd=est_seconds / 3600 * 0.02,
            est_params=trainable,
            notes=f"LoRA: {trainable} trainable of {total} total params (CPU estimate)",
        )

    def build_model(self, dataset_info: dict[str, Any], hp: dict[str, Any], seed: int):
        torch = _torch()
        import torch.nn as nn

        rank = int(hp.get("rank", 4))
        alpha = float(hp.get("lora_alpha", 8.0))
        torch.manual_seed(seed)
        n_features = int(dataset_info["n_features"])
        n_classes = int(dataset_info["n_classes"])

        class LoRAMLP(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.fc1 = _LoRALinear.make(torch, n_features, 64, rank, alpha)
                self.relu = nn.ReLU()
                self.fc2 = _LoRALinear.make(torch, 64, n_classes, rank, alpha)

            def forward(self, x):  # type: ignore[no-untyped-def]
                return self.fc2(self.relu(self.fc1(x)))

        return LoRAMLP()


# --------------------------------------------------------------------------
# QLoRAAdapter — real Unsloth path, CUDA-gated
# --------------------------------------------------------------------------


class QLoRAAdapter:
    """4-bit QLoRA via Unsloth (plan §10: PEFT taxonomy).

    The implementation below is the real Unsloth flow. It is import- and
    CUDA-guarded: on a CPU-only machine validate()/train() refuse with an
    explicit error instead of silently running something that is not QLoRA.
    Its real home is the digitalocean GPU provider.
    """

    name = "qlora"

    def validate(self, strategy: TrainingStrategy) -> list[str]:
        errors: list[str] = []
        if strategy.training_method != "qlora":
            errors.append(
                f"qlora adapter needs training_method='qlora', "
                f"got {strategy.training_method!r}"
            )
        env_error = self._env_error()
        if env_error:
            errors.append(env_error)
        return errors

    def supports_provider(self, provider: str) -> str | None:
        if provider == "digitalocean":
            return None
        return (
            "QLoRA requires a CUDA GPU with unsloth/bitsandbytes; the "
            f"{provider!r} provider cannot run it — use the digitalocean "
            "provider or the 'lora' method."
        )

    def prepare(self, ctx: AdapterContext) -> dict[str, Any]:
        """Materialize a tiny deterministic JSONL instruction dataset.

        Smoke-test data so the GPU path has something to load; real user
        datasets replace this in Phase 3+.
        """
        hp = ctx.hyperparameters
        n = int(hp.get("n_train", 200))
        path = ctx.workdir / "dataset.jsonl"
        if not path.exists():
            ctx.workdir.mkdir(parents=True, exist_ok=True)
            topics = ["sorting", "filtering", "routing", "ranking", "planning"]
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(n):
                    topic = topics[i % len(topics)]
                    fh.write(json.dumps({
                        "instruction": f"Explain {topic} as an intelligence primitive.",
                        "input": "",
                        "output": f"{topic} maps a program construct to a learned decision.",
                    }) + "\n")
        return {"n_train": n, "format": "jsonl-instruction", "path": str(path)}

    def estimate(
        self, strategy: TrainingStrategy, dataset_info: dict[str, Any] | None = None
    ) -> CostEstimate:
        hp = strategy.hyperparameters or {}
        steps = int(hp.get("max_steps", 60))
        # H100-class rough model; replaced by measured numbers on GPU runs.
        est_seconds = steps * 4.0
        return CostEstimate(
            est_seconds=est_seconds,
            est_cost_usd=est_seconds / 3600 * 4.41,
            est_params=int(hp.get("rank", 16)) * 4096 * 32,
            notes="rough H100 estimate; measure on the first GPU run",
        )

    def train(self, ctx: TrainContext, dataset_info: dict[str, Any]) -> dict[str, Any]:
        env_error = self._env_error()
        if env_error:
            raise AdapterEnvironmentError(env_error)
        from unsloth import FastLanguageModel  # noqa: F401  (real path, GPU-only)

        torch = _torch()
        hp = ctx.hyperparameters
        # --- real Unsloth QLoRA flow (executes on CUDA runners) ---
        from unsloth import FastLanguageModel as FLM

        model, tokenizer = FLM.from_pretrained(
            model_name=hp.get("base_model", "unsloth/Llama-3.2-1B"),
            max_seq_length=int(hp.get("max_seq_length", 2048)),
            dtype=None,
            load_in_4bit=True,
        )
        model = FLM.get_peft_model(
            model,
            r=int(hp.get("rank", 16)),
            target_modules=hp.get("target_modules", ["q_proj", "k_proj", "v_proj",
                                                     "o_proj", "gate_proj",
                                                     "up_proj", "down_proj"]),
            lora_alpha=int(hp.get("lora_alpha", 16)),
            lora_dropout=float(hp.get("lora_dropout", 0.0)),
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=ctx.seed,
        )
        from datasets import load_dataset  # noqa: F401
        from transformers import TrainingArguments
        from trl import SFTTrainer

        dataset = load_dataset("json", data_files=dataset_info["path"], split="train")

        def _format(ex):  # type: ignore[no-untyped-def]
            return (f"### Instruction:\n{ex['instruction']}\n\n"
                    f"### Response:\n{ex['output']}")

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            dataset_text_field="text",
            formatting_func=lambda ex: [_format(e) for e in ex],
            max_seq_length=int(hp.get("max_seq_length", 2048)),
            args=TrainingArguments(
                per_device_train_batch_size=int(hp.get("batch_size", 2)),
                gradient_accumulation_steps=int(hp.get("grad_accum", 4)),
                max_steps=int(hp.get("max_steps", 60)),
                learning_rate=float(hp.get("lr", 2e-4)),
                output_dir=str(ctx.workdir / "checkpoints"),
                save_steps=int(hp.get("save_steps", 30)),
                logging_steps=1,
                optim="adamw_8bit",
                seed=ctx.seed,
            ),
        )
        trainer.train(resume_from_checkpoint=(
            str(ctx.resume_from) if ctx.resume_from else None))
        out = ctx.workdir / "artifacts"
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(out / "lora"))
        tokenizer.save_pretrained(str(out / "lora"))
        return {"adapter": "qlora", "base_model": hp.get("base_model"),
                "device": str(torch.cuda.get_device_name(0))}

    # -- checkpoint/evaluate/export: delegate to the torch file format ----

    def save_checkpoint(self, state: dict[str, Any], path: Path) -> None:
        _save_checkpoint(state, path)

    def load_checkpoint(self, path: Path) -> dict[str, Any]:
        return _load_checkpoint(path)

    def evaluate(
        self, ctx: AdapterContext, state: dict[str, Any], dataset_info: dict[str, Any]
    ) -> dict[str, float]:
        raise AdapterEnvironmentError(self._env_error() or "QLoRA needs a CUDA runner")

    def export(
        self,
        ctx: AdapterContext,
        state: dict[str, Any],
        dataset_info: dict[str, Any],
        out_dir: Path,
    ) -> dict[str, Any]:
        raise AdapterEnvironmentError(self._env_error() or "QLoRA needs a CUDA runner")

    # -- internals ---------------------------------------------------------

    def _env_error(self) -> str | None:
        try:
            import unsloth  # noqa: F401
        except ImportError:
            return ("QLoRA requires the 'unsloth' package with a CUDA build of "
                    "torch (pip install unsloth bitsandbytes). Not installed here.")
        torch = _torch()
        if not torch.cuda.is_available():
            return ("QLoRA 4-bit training requires a CUDA GPU; none detected on "
                    "this machine. Run it on the digitalocean GPU provider.")
        return None


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

ADAPTERS: dict[str, TrainingMethodAdapter] = {
    "classifier": ClassifierAdapter(),
    "lora": LoRAAdapter(),
    "qlora": QLoRAAdapter(),
}


def get_adapter(training_method: str | None) -> TrainingMethodAdapter:
    """Fetch an adapter by training_method; KeyError on unknown/None."""
    try:
        return ADAPTERS[training_method]  # type: ignore[index]
    except KeyError:
        raise KeyError(
            f"unknown training_method: {training_method!r} "
            f"(known: {sorted(ADAPTERS)})"
        ) from None
