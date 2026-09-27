"""Deterministic fixtures for the plan §7 termination example.

DETERMINISTIC FIXTURE — hard-coded example data used by the demo endpoint
and the agents demo. Not real training data.
"""

from __future__ import annotations

from typing import Any

from shared.domain import IntelligencePrimitive


def termination_spec_fields() -> dict[str, Any]:
    """Kwargs for IntelligenceSpec minus id/project_id (plan §7 example)."""
    return {
        "name": "Search termination intelligence",
        "description": (
            "Decide when a search loop should stop. "
            "Objective: maximize useful discoveries."
        ),
        "problem_statement": (
            "Predict whether continuing a search loop will lead to new useful "
            "discoveries, given the current search state, depth reached, and "
            "progress so far. State summaries are noisy and ambiguous, so the "
            "decision must generalize beyond exact matches."
        ),
        "input_schema": {"search_state": {"type": "object"}},
        "output_schema": {
            "decision": {"enum": ["continue", "stop"]},
            "confidence": {"type": "number"},
        },
        "intelligence_primitive": IntelligencePrimitive.TERMINATION,
        "latency_requirements": {"latency_budget_ms": 50},
        "evaluation_definition": (
            "Accuracy on held-out search states; p50 latency under 50ms."
        ),
    }


def termination_dataset_rows() -> list[dict[str, Any]]:
    """12 labeled search states.

    Crafted so the baselines form a believable bar:
    majority_class ≈ 0.67 (8/12), keyword_heuristic ≈ 0.83 (10/12),
    deterministic_rule ≈ 0.92 (11/12, progress_score < 0.21 -> stop).
    """
    return [
        {
            "state_summary": "Search stalled with no new leads; best to stop here.",
            "depth": 2,
            "progress_score": 0.10,
            "label": "stop",
        },
        {
            "state_summary": "Depth exhausted with duplicate results; stop the loop.",
            "depth": 3,
            "progress_score": 0.15,
            "label": "stop",
        },
        {
            "state_summary": "Results keep repeating; time to stop searching.",
            "depth": 4,
            "progress_score": 0.20,
            "label": "stop",
        },
        {
            "state_summary": "A promising new lead appeared; keep exploring.",
            "depth": 2,
            "progress_score": 0.22,
            "label": "continue",
        },
        {
            "state_summary": (
                "Steady stream of fresh candidates; nothing suggests we should stop now."
            ),
            "depth": 5,
            "progress_score": 0.40,
            "label": "continue",
        },
        {
            "state_summary": "Progress is solid; continue exploring this branch.",
            "depth": 6,
            "progress_score": 0.50,
            "label": "continue",
        },
        {
            "state_summary": "New cluster of results found; continue digging.",
            "depth": 7,
            "progress_score": 0.60,
            "label": "continue",
        },
        {
            "state_summary": "High-value documents surfacing; continue.",
            "depth": 8,
            "progress_score": 0.70,
            "label": "continue",
        },
        {
            "state_summary": "Marginal returns now; diminishing value in further pages.",
            "depth": 9,
            "progress_score": 0.75,
            "label": "stop",
        },
        {
            "state_summary": "Continue: the index just refreshed with new entries.",
            "depth": 9,
            "progress_score": 0.80,
            "label": "continue",
        },
        {
            "state_summary": "Keep going; continue the sweep of remaining shards.",
            "depth": 10,
            "progress_score": 0.85,
            "label": "continue",
        },
        {
            "state_summary": "Almost complete coverage; continue to the final shard.",
            "depth": 11,
            "progress_score": 0.95,
            "label": "continue",
        },
    ]
