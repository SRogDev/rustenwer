"""Phase-0 smoke test: build the supervisor graph and invoke it once.

Run from the `agents/` directory with its venv active:
    python smoke.py
"""

from __future__ import annotations

from supervisor import build_supervisor_graph


def main() -> None:
    graph = build_supervisor_graph()
    final_state = graph.invoke(
        {
            "messages": [],
            "problem_statement": "decide whether a support ticket should be escalated",
            "phase": "intake",
        }
    )
    print("final state:")
    for key, value in final_state.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
