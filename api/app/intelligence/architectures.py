"""Intelligence architecture validation and diffing (Phase 4, plan §2.2, §31).

An IntelligenceArchitecture describes how components compose into an
executable system. Publishing a version validates every component reference
(model versions must resolve; baselines must be known; rule/threshold/prompt
configs must be complete) — Rule 5: every candidate must be reproducible,
and a version that references a ghost component is not.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared.domain import (
    ARCHITECTURE_KINDS,
    ArchitectureComponent,
    ArchitectureComponentKind,
    IntelligenceArchitecture,
)

# Cheap baselines the hosted provider can execute (Phase 1 names).
KNOWN_BASELINES: frozenset[str] = frozenset(
    {"majority_class", "keyword_heuristic", "deterministic_rule"}
)

_REQUIRED_RULE_KEYS: tuple[str, ...] = (
    "column",
    "threshold",
    "left_label",
    "right_label",
)
_REQUIRED_THRESHOLD_KEYS: tuple[str, ...] = ("input_key", "threshold", "above", "below")


class ArchitectureValidationError(ValueError):
    """A published architecture references something unresolvable."""


def _model_repository_get_version(model_repository: Any, version_id: UUID) -> Any | None:
    get_version = getattr(model_repository, "get_version", None)
    if get_version is None:
        return None
    return get_version(version_id)


def validate_architecture(
    architecture: IntelligenceArchitecture, model_repository: Any
) -> None:
    """Validate every component of an architecture.

    Raises ArchitectureValidationError (mapped to 409 by the router) when a
    component cannot be resolved or is malformed.
    """
    if architecture.kind not in ARCHITECTURE_KINDS:
        raise ArchitectureValidationError(
            f"Unknown architecture kind: {architecture.kind!r}. "
            f"Known kinds: {', '.join(ARCHITECTURE_KINDS)}"
        )
    n = len(architecture.components)
    if architecture.execution_order:
        if sorted(architecture.execution_order) != list(range(n)):
            raise ArchitectureValidationError(
                "execution_order must be a permutation of component indexes "
                f"0..{n - 1}; got {architecture.execution_order}"
            )
    for index, component in enumerate(architecture.components):
        _validate_component(component, index, model_repository)


def _validate_component(
    component: ArchitectureComponent, index: int, model_repository: Any
) -> None:
    label = component.label or f"component[{index}]"
    kind = component.kind
    if kind is ArchitectureComponentKind.MODEL_VERSION:
        if not component.ref:
            raise ArchitectureValidationError(
                f"{label}: model_version component needs a ref (model version id)"
            )
        try:
            version_id = UUID(str(component.ref))
        except ValueError as exc:
            raise ArchitectureValidationError(
                f"{label}: model version ref is not a UUID: {component.ref!r}"
            ) from exc
        if _model_repository_get_version(model_repository, version_id) is None:
            raise ArchitectureValidationError(
                f"{label}: model version not found: {component.ref}"
            )
    elif kind is ArchitectureComponentKind.BASELINE:
        if component.ref not in KNOWN_BASELINES:
            raise ArchitectureValidationError(
                f"{label}: unknown baseline {component.ref!r}. "
                f"Known baselines: {', '.join(sorted(KNOWN_BASELINES))}"
            )
    elif kind is ArchitectureComponentKind.DETERMINISTIC_RULE:
        missing = [k for k in _REQUIRED_RULE_KEYS if k not in component.config]
        if missing:
            raise ArchitectureValidationError(
                f"{label}: deterministic_rule config missing keys: "
                f"{', '.join(missing)}"
            )
        if not isinstance(component.config.get("threshold"), (int, float)):
            raise ArchitectureValidationError(
                f"{label}: deterministic_rule config 'threshold' must be numeric"
            )
    elif kind is ArchitectureComponentKind.THRESHOLD:
        missing = [k for k in _REQUIRED_THRESHOLD_KEYS if k not in component.config]
        if missing:
            raise ArchitectureValidationError(
                f"{label}: threshold config missing keys: {', '.join(missing)}"
            )
    elif kind is ArchitectureComponentKind.PROMPT:
        template = component.config.get("template")
        if not isinstance(template, str) or not template.strip():
            raise ArchitectureValidationError(
                f"{label}: prompt component needs a non-empty config 'template'"
            )
    elif kind is ArchitectureComponentKind.POST_PROCESSOR:
        # Structural only: no external refs to validate.
        return
    elif kind is ArchitectureComponentKind.ROUTER:
        raise ArchitectureValidationError(
            f"{label}: router components are not executable until Phase 7 "
            "(discovery); use a fixed execution_order instead"
        )
    else:  # pragma: no cover — enum is closed
        raise ArchitectureValidationError(f"{label}: unknown component kind {kind!r}")


def summarize_architecture(architecture: IntelligenceArchitecture) -> str:
    """One short human-readable line describing an architecture."""
    parts = [f"{c.kind.value}:{c.label or c.ref or '?'}" for c in architecture.components]
    return f"{architecture.kind} [{' -> '.join(parts)}]"


def _component_key(component: ArchitectureComponent) -> str:
    return f"{component.kind.value}|{component.ref or ''}|{component.label}"


def diff_architectures(
    old: IntelligenceArchitecture | None, new: IntelligenceArchitecture | None
) -> dict[str, Any]:
    """Component-level diff between two architecture snapshots."""
    old_components = {_component_key(c): c for c in (old.components if old else [])}
    new_components = {_component_key(c): c for c in (new.components if new else [])}
    added = [
        c.model_dump(mode="json") for k, c in new_components.items() if k not in old_components
    ]
    removed = [
        c.model_dump(mode="json") for k, c in old_components.items() if k not in new_components
    ]
    modified: list[dict[str, Any]] = []
    for key in old_components.keys() & new_components.keys():
        old_cfg = old_components[key].config
        new_cfg = new_components[key].config
        changed_keys = sorted(
            {k for k in set(old_cfg) | set(new_cfg) if old_cfg.get(k) != new_cfg.get(k)}
        )
        if changed_keys:
            modified.append(
                {
                    "label": new_components[key].label,
                    "kind": new_components[key].kind.value,
                    "changed_config_keys": changed_keys,
                    "old_values": {k: old_cfg.get(k) for k in changed_keys},
                    "new_values": {k: new_cfg.get(k) for k in changed_keys},
                }
            )
    return {
        "kind_changed": (old.kind if old else None) != (new.kind if new else None),
        "added": added,
        "removed": removed,
        "modified": modified,
    }
