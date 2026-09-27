"""Deterministic LLM stand-in for the agents.

**DETERMINISTIC FIXTURE — replace with a real LLM adapter when keys exist.**

No real LLM calls happen anywhere in the Phase-1 agents: this class maps a
problem statement to a primitive guess (and the detected keyword signals)
with pure keyword rules, so the graph is fully deterministic and testable
until an API key is available. The specification node uses it only when the
user did not pick an intelligence primitive explicitly.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Keyword → IntelligencePrimitive value, checked in order. First match wins.
_KEYWORD_PRIMITIVES: tuple[tuple[str, str], ...] = (
    ("stop", "termination"),
    ("terminate", "termination"),
    ("classify", "classification"),
    ("classification", "classification"),
    ("rank", "ranking"),
    ("sort", "ranking"),
    ("filter", "filtering"),
    ("search", "search"),
    ("retrieve", "retrieval"),
    ("route", "routing"),
    ("verify", "verification"),
    ("critique", "critique"),
    ("predict", "prediction"),
    ("anomaly", "anomaly_detection"),
    ("diagnos", "diagnosis"),
    ("plan", "planning"),
    ("optimiz", "optimization"),
    ("compress", "compression"),
    ("summariz", "compression"),
    ("remember", "memory_selection"),
    ("iterate", "iteration_control"),
    ("decide", "decision"),
    ("select", "selection"),
    ("explor", "exploration"),
)


class StubLLM:
    """**DETERMINISTIC FIXTURE — replace with a real LLM adapter when keys exist.**

    Keyword-based stand-in for the diagnostic LLM call. Deterministic:
    identical input always yields identical output.
    """

    def diagnose(self, problem_statement: str, primitive_hint: str | None = None) -> dict:
        """Map a problem statement to a primitive guess + detected signals.

        Args:
            problem_statement: free-text description of the desired behavior.
            primitive_hint: explicit primitive chosen by the user; when given
                it wins over the keyword guess.

        Returns:
            dict with `primitive` (str), `hint_used` (bool) and `signals`
            (list of matched keywords).
        """
        text = (problem_statement or "").lower()
        signals = [kw for kw, _ in _KEYWORD_PRIMITIVES if kw in text]
        guess = next(
            (prim for kw, prim in _KEYWORD_PRIMITIVES if kw in text),
            "decision",
        )
        if primitive_hint:
            logger.info("llm_stub.diagnose", hint=primitive_hint, guess=guess)
            return {"primitive": primitive_hint, "hint_used": True, "signals": signals}
        logger.info("llm_stub.diagnose", guess=guess, signals=signals)
        return {"primitive": guess, "hint_used": False, "signals": signals}
