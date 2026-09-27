"""Specification/Diagnostic agent logic (product plan §8).

Deterministic keyword-based diagnosis. Rule 2: never assume fine-tuning is
the answer — "no ML needed" is a first-class outcome (Rule 13).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from shared.domain import DiagnosisResult, IntelligencePrimitive, IntelligenceSpec

# Patterns that indicate the problem is solvable with plain deterministic
# code (no learning required).
_DETERMINISTIC_PATTERNS = (
    "sort by",
    "filter by",
    "lookup",
    "count",
    "deduplicate",
    "format",
    "threshold",
    "validate",
)

# Words that indicate a genuine learning problem.
_LEARNING_SIGNALS = ("learn", "predict", "classify", "fuzzy", "ambiguous")

# Keyword map: problem_statement.lower() -> primitive guess.
_PRIMITIVE_KEYWORDS: dict[str, list[str]] = {
    "classification": ["classify", "classification", "categorize", "categorization"],
    "termination": ["terminate", "termination", "stop", "halt", "when to stop", "when to end"],
    "ranking": ["rank", "ranking", "rerank"],
    "prediction": ["predict", "prediction", "forecast"],
    "filtering": ["filter", "filtering"],
    "search": ["search", "searching"],
    "retrieval": ["retrieve", "retrieval"],
    "routing": ["route", "routing", "triage"],
    "verification": ["verify", "verification", "fact-check"],
    "critique": ["critique"],
    "anomaly_detection": ["anomaly", "anomalies", "outlier"],
    "diagnosis": ["diagnose", "diagnosis", "root cause"],
    "planning": ["plan", "planning", "schedule"],
    "optimization": ["optimize", "optimization"],
    "decision": ["decide", "decision"],
    "exploration": ["explore", "exploration"],
    "selection": ["select", "selection", "choose"],
    "compression": ["compress", "summarize", "summarization"],
    "memory_selection": ["remember", "recall", "memory"],
    "iteration_control": ["iterate", "loop", "repeat"],
}


def _matches_any(text: str, words: tuple[str, ...] | list[str]) -> list[str]:
    """Word-boundary match so 'count' does not fire on 'encountered'."""
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", text)]


def _guess_primitive(text: str) -> IntelligencePrimitive | None:
    for primitive_value, keywords in _PRIMITIVE_KEYWORDS.items():
        if _matches_any(text, keywords):
            return IntelligencePrimitive(primitive_value)
    return None


def detect_primitive(problem_statement: str) -> IntelligencePrimitive:
    """Best-effort primitive detection from free text (the "auto-detect" path).

    Used when a spec is created without an explicit `intelligence_primitive`
    (e.g. the web wizard's "auto-detect" option). Falls back to `decision`
    when no keyword signal matches — the Diagnostic Agent refines this at
    `/diagnose` time.
    """
    return _guess_primitive(problem_statement.lower()) or IntelligencePrimitive.DECISION


def diagnose_spec(spec: IntelligenceSpec) -> DiagnosisResult:
    """Run the deterministic diagnosis over an IntelligenceSpec.

    The primitive is always the spec's own pick (the keyword map only
    informs the rationale — never override the user's choice). ML is deemed
    unnecessary when the problem matches deterministic patterns with no
    learning signal words; a learning signal always wins.
    """
    text = spec.problem_statement.lower()

    deterministic_hits = _matches_any(text, _DETERMINISTIC_PATTERNS)
    learning_hits = _matches_any(text, _LEARNING_SIGNALS)
    ml_necessary = bool(learning_hits) or not deterministic_hits

    primitive = spec.intelligence_primitive
    keyword_guess = _guess_primitive(text)

    input_keys = list(spec.input_schema.keys())
    output_keys = list(spec.output_schema.keys())

    candidate_approaches = [
        "majority_class baseline",
        "keyword_heuristic baseline",
        "deterministic_rule baseline",
    ]
    if ml_necessary:
        candidate_approaches += [
            "embedding-based fine-tune (small data)",
            "LoRA fine-tune",
            "distillation from a larger model",
        ]
    else:
        candidate_approaches.append("hand-written deterministic function (no model)")

    data_requirements = [
        (
            f"Labeled examples: ({', '.join(input_keys) or 'inputs'})"
            f" -> ({', '.join(output_keys) or 'outputs'})"
        ),
        "Train/validation/test split with no leakage between splits",
        "Label definitions reviewed by a human",
    ]
    if ml_necessary:
        data_requirements.append("Negative and edge-case examples for robustness")
    if spec.available_data:
        data_requirements.append(f"Start from available data: {spec.available_data}")

    success_metrics = (
        [spec.evaluation_definition]
        if spec.evaluation_definition
        else [
            "Accuracy on a held-out test split",
            "p50 latency within the stated budget",
            "Cost per 1k predictions within budget",
        ]
    )

    key_constraints = list(spec.constraints)
    if spec.latency_requirements:
        key_constraints.append(f"Latency: {spec.latency_requirements}")
    if spec.cost_requirements:
        key_constraints.append(f"Cost: {spec.cost_requirements}")

    if ml_necessary:
        ml_answer = (
            f"Yes — learning signals present ({', '.join(learning_hits)})"
            if learning_hits
            else "Yes — no purely-deterministic pattern matched; learning not ruled out"
        )
    else:
        ml_answer = (
            "No — matches deterministic patterns "
            f"({', '.join(deterministic_hits)}) with no learning signal words; "
            "no ML model is necessary (Rule 13)"
        )

    guess_note = ""
    if keyword_guess is not None and keyword_guess != primitive:
        guess_note = (
            f" (keyword signals suggest '{keyword_guess.value}', "
            f"but the user's pick '{primitive.value}' wins)"
        )

    rationale = "\n".join(
        [
            f"1. Problem: {spec.problem_statement[:220]}",
            f"2. Desired behavior: produce {', '.join(output_keys) or 'the specified outputs'}",
            f"3. Inputs: {', '.join(input_keys) or 'not specified'}",
            f"4. Outputs: {', '.join(output_keys) or 'not specified'}",
            f"5. Primitive: {primitive.value}{guess_note}",
            f"6. ML necessary: {ml_answer}",
            f"7. Candidate approaches: {', '.join(candidate_approaches)}",
            f"8. Data required: {'; '.join(data_requirements)}",
            f"9. Success measured by: {'; '.join(success_metrics)}",
            f"10. Constraints: {'; '.join(key_constraints) or 'none stated'}",
        ]
    )

    return DiagnosisResult(
        spec_id=spec.id,
        ml_necessary=ml_necessary,
        primitive=primitive,
        rationale=rationale,
        candidate_approaches=candidate_approaches,
        data_requirements=data_requirements,
        success_metrics=success_metrics,
        key_constraints=key_constraints,
        diagnosed_at=datetime.now(UTC).isoformat(),
    )
