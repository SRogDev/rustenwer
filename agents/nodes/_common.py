"""Shared helpers for the Phase-1 node functions (plumbing only).

No domain logic here — Rule 3: deterministic logic lives in `shared/services/`.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from shared.domain import IntelligenceSpec


def append_note(state: dict, note: str) -> dict[str, list[str]]:
    """Return a state update with `note` appended to `notes`."""
    return {"notes": [*state.get("notes", []), note]}


def spec_from_dict(
    spec_dict: dict, fallback_problem_statement: str | None = None
) -> IntelligenceSpec:
    """Build an `IntelligenceSpec` from a state dict, filling required fields.

    `intelligence_primitive` must already be resolved (the specification node
    uses `StubLLM` for that when the user did not pick one explicitly).
    """
    data = dict(spec_dict)
    data.setdefault("id", uuid4())
    data.setdefault("project_id", uuid4())
    problem = data.get("problem_statement") or fallback_problem_statement or ""
    data["problem_statement"] = problem
    data.setdefault("name", (problem[:50] or "Untitled spec").strip() or "Untitled spec")
    # Normalize UUID-ish strings the state layer carries as plain strings.
    for key in ("id", "project_id"):
        if isinstance(data[key], str):
            data[key] = UUID(data[key])
    return IntelligenceSpec(**data)
