"""Specification (diagnostic) agent node.

Orchestrates `shared.services.diagnosis.diagnose_spec` (Rule 3). Builds an
`IntelligenceSpec` from `state["spec"]` or synthesizes a minimal one from
`problem_statement` (primitive guessed by the deterministic `StubLLM` when
the user did not pick one). Stores the diagnosis as a JSON-safe dict and
sets `no_ml_path` (Rule 13: the platform may conclude no ML is needed).
"""

from __future__ import annotations

import structlog

from agents.llm_stub import StubLLM
from agents.nodes._common import append_note, spec_from_dict
from agents.state import SupervisorState

logger = structlog.get_logger(__name__)


def specification_node(state: SupervisorState) -> dict:
    """Run the diagnostic agent over the intelligence spec."""
    from shared.services.diagnosis import diagnose_spec  # lazy: backend builder delivers it

    spec_dict = dict(state.get("spec") or {})
    problem_statement = spec_dict.get("problem_statement") or state.get("problem_statement") or ""
    if not spec_dict.get("intelligence_primitive"):
        guess = StubLLM().diagnose(problem_statement, primitive_hint=None)
        spec_dict["intelligence_primitive"] = guess["primitive"]
        logger.info("specification.primitive_guess", guess=guess)

    spec = spec_from_dict(spec_dict, fallback_problem_statement=problem_statement)
    diagnosis = diagnose_spec(spec)
    logger.info(
        "specification.diagnosed",
        primitive=diagnosis.primitive.value,
        ml_necessary=diagnosis.ml_necessary,
    )
    return {
        "spec": spec.model_dump(mode="json"),
        "diagnosis": diagnosis.model_dump(mode="json"),
        "no_ml_path": not diagnosis.ml_necessary,
        "phase": "specification",
        **append_note(
            state,
            f"specification: diagnosed '{spec.name}' as primitive "
            f"'{diagnosis.primitive.value}' (ml_necessary={diagnosis.ml_necessary})",
        ),
    }
