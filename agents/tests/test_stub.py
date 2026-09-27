"""Tests for the deterministic LLM stand-in (agents/llm_stub.py)."""

from __future__ import annotations

from agents.llm_stub import StubLLM


def test_docstring_marks_deterministic_fixture() -> None:
    assert "DETERMINISTIC FIXTURE" in StubLLM.__doc__


def test_diagnose_returns_primitive_key() -> None:
    result = StubLLM().diagnose("classify incoming support tickets", None)
    assert isinstance(result, dict)
    assert result["primitive"] == "classification"


def test_diagnose_is_deterministic() -> None:
    stub = StubLLM()
    statement = "decide whether a search should continue or stop"
    assert stub.diagnose(statement, None) == stub.diagnose(statement, None)


def test_diagnose_keyword_mapping_termination() -> None:
    result = StubLLM().diagnose("decide when to stop a long-running search", None)
    assert result["primitive"] == "termination"


def test_diagnose_keyword_mapping_ranking() -> None:
    result = StubLLM().diagnose("sort and rank the results by relevance score", None)
    assert result["primitive"] == "ranking"


def test_primitive_hint_overrides_keyword_guess() -> None:
    result = StubLLM().diagnose("classify incoming support tickets", "diagnosis")
    assert result["primitive"] == "diagnosis"
    assert result["hint_used"] is True


def test_diagnose_lists_detected_signals() -> None:
    result = StubLLM().diagnose("classify incoming support tickets", None)
    assert "classify" in result["signals"]
    assert result["primitive"] == "classification"
