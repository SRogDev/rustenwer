"""Inference pipeline + provider abstraction (Phase 4, plan §33, §34).

The hosted provider executes a deployed intelligence version end to end:

  validate inputs against the version's input_schema
      -> execute architecture components in order
      -> shape the machine-readable output for the intelligence's primitive

Only RUSTENWER_HOSTED executes in Phase 4. EXTERNAL_API and LOCAL_GPU are
honest capability entries: listed by GET /inference/providers, but inferring
through them raises ProviderNotConfigured instead of pretending to work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from shared.domain import (
    ArchitectureComponent,
    ArchitectureComponentKind,
    InferenceProvider,
    Intelligence,
    IntelligencePrimitive,
    IntelligenceVersion,
    ProviderInfo,
    output_shape_for_primitive,
)


class SchemaValidationError(ValueError):
    """Inputs fail the intelligence version's input_schema (mapped to 422)."""


class ComponentExecutionError(RuntimeError):
    """A component failed at inference time (mapped to 502)."""


class ProviderNotConfigured(RuntimeError):
    """The provider exists but cannot serve (mapped to 501)."""


@dataclass
class InferenceContext:
    """Everything the hosted pipeline needs beyond the version itself."""

    model_repository: Any
    artifact_root: Path


# --------------------------------------------------------------------------
# Input validation (JSON-schema-lite)
# --------------------------------------------------------------------------

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def _field_spec(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize an input_schema to {field: spec}.

    Accepts both {"field": {"type": ..., "required": ...}} and the
    {"properties": {...}, "required": [...]} shape.
    """
    if "properties" in schema and isinstance(schema["properties"], dict):
        required = set(schema.get("required") or [])
        return {
            name: {"type": spec.get("type"), "required": name in required}
            for name, spec in schema["properties"].items()
            if isinstance(spec, dict)
        }
    return {k: v for k, v in schema.items() if isinstance(v, dict)}


def validate_inputs(inputs: dict[str, Any], input_schema: dict[str, Any]) -> None:
    """Validate inputs against a version's input_schema.

    Raises SchemaValidationError listing every violation (never a bare 500).
    """
    if not isinstance(inputs, dict):
        raise SchemaValidationError("inputs must be an object")
    violations: list[str] = []
    for field, spec in _field_spec(input_schema or {}).items():
        if field not in inputs:
            if spec.get("required"):
                violations.append(f"missing required input: {field!r}")
            continue
        expected = spec.get("type")
        if expected and expected in _JSON_TYPES:
            value = inputs[field]
            if isinstance(value, bool) and expected == "number":
                violations.append(f"{field!r} must be a number, got bool")
            elif not isinstance(value, _JSON_TYPES[expected]):
                violations.append(
                    f"{field!r} must be {expected}, got {type(value).__name__}"
                )
    if violations:
        raise SchemaValidationError("; ".join(violations))


# --------------------------------------------------------------------------
# Component executors
# --------------------------------------------------------------------------


def _column_value(row: dict[str, Any], column: str | None) -> Any:
    """Resolve a column, supporting 'name[i]' pseudo-columns for vectors."""
    if not column:
        return None
    if "[" in column and column.endswith("]"):
        name, _, rest = column.partition("[")
        try:
            index = int(rest[:-1])
        except ValueError:
            return None
        values = row.get(name)
        if isinstance(values, (list, tuple)) and 0 <= index < len(values):
            return values[index]
        return None
    return row.get(column)


def _exec_deterministic_rule(
    component: ArchitectureComponent, inputs: dict[str, Any]
) -> dict[str, Any]:
    config = component.config
    value = _column_value(inputs, config.get("column"))
    if value is None:
        label = config.get("fallback_label")
    else:
        threshold = config["threshold"]
        label = config["left_label"] if value <= threshold else config["right_label"]
    return {
        "label": label,
        "confidence": 1.0,  # deterministic by construction
        "rule": {
            "column": config.get("column"),
            "threshold": config.get("threshold"),
            "observed": value,
        },
    }


def _exec_threshold(
    component: ArchitectureComponent, inputs: dict[str, Any]
) -> dict[str, Any]:
    config = component.config
    value = inputs.get(config.get("input_key"))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ComponentExecutionError(
            f"threshold component {component.label!r}: input "
            f"{config.get('input_key')!r} is not numeric"
        )
    label = config["above"] if value > config["threshold"] else config["below"]
    return {"label": label, "confidence": 1.0, "observed": value}


def _exec_baseline(
    component: ArchitectureComponent, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Single-row prediction for a fitted baseline.

    Baselines are cheap by design, but they still need their fitted artifact:
    config["fitted"] carries it, e.g. {"label": "stop"} for majority_class or
    the rule dict for deterministic_rule. Unfitted or unknown baselines fail
    honestly instead of silently falling back.
    """
    name = component.ref
    fitted = component.config.get("fitted")
    if name == "majority_class":
        if not isinstance(fitted, dict) or "label" not in fitted:
            raise ComponentExecutionError(
                f"baseline component {component.label!r}: majority_class needs "
                "config.fitted.label"
            )
        return {"label": fitted["label"], "confidence": 1.0}
    if name == "deterministic_rule":
        if not isinstance(fitted, dict):
            raise ComponentExecutionError(
                f"baseline component {component.label!r}: deterministic_rule "
                "needs config.fitted with the fitted rule"
            )
        return _exec_deterministic_rule(
            ArchitectureComponent(
                kind=ArchitectureComponentKind.DETERMINISTIC_RULE,
                label=component.label,
                config=fitted,
            ),
            inputs,
        )
    raise ComponentExecutionError(
        f"baseline component {component.label!r}: baseline {name!r} is not "
        "executable as a single-row component in Phase 4"
    )


def _exec_model_version(
    component: ArchitectureComponent, inputs: dict[str, Any], ctx: InferenceContext
) -> dict[str, Any]:
    from app.evaluation.subjects import load_classifier_bundle

    if not component.ref:
        raise ComponentExecutionError("model_version component needs a ref")
    version = ctx.model_repository.get_version(UUID(str(component.ref)))
    if version is None:
        raise ComponentExecutionError(f"model version not found: {component.ref}")
    torch, model, config = load_classifier_bundle(version, ctx.artifact_root)
    feature_key = component.config.get("feature_key", "x")
    n_features = int(config["n_features"])
    features = inputs.get(feature_key)
    if not (
        isinstance(features, list)
        and len(features) == n_features
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in features)
    ):
        raise ComponentExecutionError(
            f"model component {component.label!r}: input {feature_key!r} must be "
            f"a numeric vector of length {n_features}"
        )
    classes: list[str] = [str(c) for c in component.config.get("classes", [])]
    if len(classes) != int(config["n_classes"]):
        raise ComponentExecutionError(
            f"model component {component.label!r}: config.classes "
            f"({len(classes)}) must list all {config['n_classes']} classes "
            "pinned at publish time"
        )
    with torch.no_grad():
        logits = model(torch.tensor([features], dtype=torch.float32))
        proba = torch.softmax(logits, dim=1)[0]
        probabilities = {c: float(proba[i].item()) for i, c in enumerate(classes)}
    best = max(probabilities, key=lambda c: probabilities[c])
    return {"label": best, "probabilities": probabilities, "confidence": probabilities[best]}


def _resolve_path(state: dict[str, Any], path: str) -> Any:
    current: Any = state
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ComponentExecutionError(
                f"post_processor: cannot resolve path {path!r}"
            )
    return current


def _exec_post_processor(
    component: ArchitectureComponent, state: dict[str, Any]
) -> dict[str, Any]:
    mappings = component.config.get("mappings")
    if not isinstance(mappings, dict):
        raise ComponentExecutionError(
            f"post_processor {component.label!r}: config.mappings must be an object"
        )
    return {key: _resolve_path(state, path) for key, path in mappings.items()}


def _execute_component(
    component: ArchitectureComponent,
    inputs: dict[str, Any],
    state: dict[str, Any],
    ctx: InferenceContext,
) -> dict[str, Any]:
    kind = component.kind
    if kind is ArchitectureComponentKind.DETERMINISTIC_RULE:
        return _exec_deterministic_rule(component, inputs)
    if kind is ArchitectureComponentKind.THRESHOLD:
        return _exec_threshold(component, inputs)
    if kind is ArchitectureComponentKind.BASELINE:
        return _exec_baseline(component, inputs)
    if kind is ArchitectureComponentKind.MODEL_VERSION:
        return _exec_model_version(component, inputs, ctx)
    if kind is ArchitectureComponentKind.POST_PROCESSOR:
        return _exec_post_processor(component, state)
    if kind is ArchitectureComponentKind.PROMPT:
        raise ProviderNotConfigured(
            f"prompt component {component.label!r}: no LLM provider is configured "
            "in Phase 4 — prompt components are metadata until an inference "
            "provider supports them"
        )
    raise ComponentExecutionError(
        f"component kind {kind.value!r} is not executable in Phase 4"
    )


# --------------------------------------------------------------------------
# Output shaping (plan §33)
# --------------------------------------------------------------------------


def _shape_output(
    primitive: IntelligencePrimitive | None,
    raw: dict[str, Any],
    component_kind: ArchitectureComponentKind | None,
) -> dict[str, Any]:
    """Shape a component's raw output into the primitive's machine-readable
    contract. Never emits free text where a contract key is expected."""
    key = primitive.value if isinstance(primitive, IntelligencePrimitive) else None
    shape = output_shape_for_primitive(primitive)

    if key in ("decision", "termination"):
        decision = raw.get("decision", raw.get("label"))
        confidence = raw.get("confidence")
        if confidence is None:
            probabilities = raw.get("probabilities") or {}
            confidence = probabilities.get(decision, 1.0 if decision is not None else 0.0)
        return {"decision": decision, "confidence": float(confidence)}
    if key == "classification":
        label = raw.get("label")
        probabilities = raw.get("probabilities") or {}
        if not probabilities and raw.get("confidence") is not None and label is not None:
            probabilities = {label: float(raw["confidence"])}
        return {"label": label, "probabilities": probabilities}
    if key == "ranking":
        return {"score": float(raw.get("score", 0.0))}
    # Generic: keep the raw output under its contract key.
    if shape == ["output"]:
        return {"output": raw}
    return {k: raw.get(k) for k in shape}


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


def execute_pipeline(
    intelligence: Intelligence,
    version: IntelligenceVersion,
    inputs: dict[str, Any],
    ctx: InferenceContext,
) -> dict[str, Any]:
    """Run a full intelligence version: validate -> execute -> shape."""
    validate_inputs(inputs, version.input_schema or {})
    architecture = version.architecture
    components = (
        architecture.ordered_components() if architecture is not None else []
    )
    if not components:
        raise ComponentExecutionError("intelligence version has no components to execute")
    state: dict[str, Any] = {"inputs": dict(inputs)}
    last_kind: ArchitectureComponentKind | None = None
    last_output: dict[str, Any] = {}
    for component in components:
        output = _execute_component(component, inputs, state, ctx)
        state[component.label or component.kind.value] = output
        last_kind, last_output = component.kind, output
    return _shape_output(intelligence.primitive, last_output, last_kind)


# --------------------------------------------------------------------------
# Providers (plan §34)
# --------------------------------------------------------------------------


class InferenceProviderBase(Protocol):
    """One inference backend behind the unified abstraction."""

    name: InferenceProvider

    def capabilities(self) -> ProviderInfo:
        """What this provider can do (honest, no pretending)."""
        ...

    def infer(
        self,
        *,
        intelligence: Intelligence,
        version: IntelligenceVersion,
        inputs: dict[str, Any],
        ctx: InferenceContext,
    ) -> dict[str, Any]:
        """Execute one inference; raises ProviderNotConfigured when the
        provider cannot serve."""
        ...


class HostedInferenceProvider:
    """Rustenwer-hosted inference: the real local pipeline executor."""

    name = InferenceProvider.RUSTENWER_HOSTED

    def capabilities(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            functional=True,
            capabilities=[
                "deterministic_rule",
                "threshold",
                "baseline (fitted)",
                "model_version (local CPU torch)",
                "post_processor",
                "input schema validation",
                "primitive output shaping",
            ],
            note="Executes the intelligence pipeline in-process on local CPU.",
        )

    def infer(
        self,
        *,
        intelligence: Intelligence,
        version: IntelligenceVersion,
        inputs: dict[str, Any],
        ctx: InferenceContext,
    ) -> dict[str, Any]:
        return execute_pipeline(intelligence, version, inputs, ctx)


class ExternalAPIProvider:
    """External API inference — capability entry only in Phase 4."""

    name = InferenceProvider.EXTERNAL_API

    def capabilities(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            functional=False,
            capabilities=[],
            note="Not configured in Phase 4: no external inference endpoint is wired.",
        )

    def infer(self, **kwargs: Any) -> dict[str, Any]:
        raise ProviderNotConfigured(
            "external_api provider is not configured in Phase 4"
        )


class LocalGPUProvider:
    """Local GPU inference — capability entry only in Phase 4."""

    name = InferenceProvider.LOCAL_GPU

    def capabilities(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            functional=False,
            capabilities=[],
            note="Not configured in Phase 4: no GPU worker pool exists yet.",
        )

    def infer(self, **kwargs: Any) -> dict[str, Any]:
        raise ProviderNotConfigured("local_gpu provider is not configured in Phase 4")


PROVIDERS: dict[str, InferenceProviderBase] = {
    InferenceProvider.RUSTENWER_HOSTED.value: HostedInferenceProvider(),
    InferenceProvider.EXTERNAL_API.value: ExternalAPIProvider(),
    InferenceProvider.LOCAL_GPU.value: LocalGPUProvider(),
}


def get_provider(name: str | InferenceProvider) -> InferenceProviderBase:
    """Resolve a provider by name; ValueError (→404) on unknown names."""
    key = name.value if isinstance(name, InferenceProvider) else str(name)
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown inference provider: {name!r}") from exc
