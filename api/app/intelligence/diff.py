"""Intelligence version diff (Phase 4, plan §32, §37).

Mirrors the model lineage diff: what changed between two immutable
intelligence versions — the evidence a human reviewer needs before
approving a promotion. Pure function over two IntelligenceVersions.
"""

from __future__ import annotations

from shared.domain import IntelligenceArchitecture, IntelligenceVersion, IntelligenceVersionDiff

from app.intelligence.architectures import diff_architectures


def _arch_of(version: IntelligenceVersion) -> IntelligenceArchitecture | None:
    arch = version.architecture
    if arch is None:
        return None
    if isinstance(arch, IntelligenceArchitecture):
        return arch
    return IntelligenceArchitecture.model_validate(arch)


def diff_versions(
    v_from: IntelligenceVersion, v_to: IntelligenceVersion
) -> IntelligenceVersionDiff:
    """Diff two versions of the same intelligence (ascending or not)."""
    if v_from.intelligence_id != v_to.intelligence_id:
        raise ValueError("diff_versions requires versions of the same intelligence")

    changed_fields: list[str] = []
    notes: list[str] = []

    for field in ("notes", "status", "best_evaluation_run_id"):
        old, new = getattr(v_from, field), getattr(v_to, field)
        if old != new:
            changed_fields.append(field)

    schema_changed = (
        v_from.input_schema != v_to.input_schema
        or v_from.output_schema != v_to.output_schema
    )
    if schema_changed:
        changed_fields.append("schemas")
        notes.append("Input/output schema changed — callers must re-check the contract.")

    arch_diff = diff_architectures(_arch_of(v_from), _arch_of(v_to))
    if arch_diff["kind_changed"]:
        changed_fields.append("architecture.kind")
        old_kind = _arch_of(v_from).kind if _arch_of(v_from) else None
        new_kind = _arch_of(v_to).kind if _arch_of(v_to) else None
        notes.append(f"Architecture kind changed: {old_kind} -> {new_kind}.")
    for comp in arch_diff["added"]:
        changed_fields.append(f"components.+{comp.get('label') or comp.get('kind')}")
        notes.append(
            f"Added component '{comp.get('label') or comp.get('kind')}' "
            f"({comp.get('kind')})."
        )
    for comp in arch_diff["removed"]:
        changed_fields.append(f"components.-{comp.get('label') or comp.get('kind')}")
        notes.append(
            f"Removed component '{comp.get('label') or comp.get('kind')}' "
            f"({comp.get('kind')})."
        )
    for comp in arch_diff["modified"]:
        changed_fields.append(f"components.~{comp['label']}")
        keys = ", ".join(comp["changed_config_keys"])
        notes.append(f"Component '{comp['label']}' changed config keys: {keys}.")

    return IntelligenceVersionDiff(
        intelligence_id=v_from.intelligence_id,
        from_version=v_from.version,
        to_version=v_to.version,
        changed_fields=changed_fields,
        components_added=arch_diff["added"],
        components_removed=arch_diff["removed"],
        components_modified=arch_diff["modified"],
        architecture_kind_changed=arch_diff["kind_changed"],
        schema_changed=schema_changed,
        notes=notes,
    )
