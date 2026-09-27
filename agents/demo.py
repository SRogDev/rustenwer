"""End-to-end demo: run the Phase-1 supervisor graph on the termination fixture.

Builds a spec dict from `termination_spec_fields()`, rows from
`termination_dataset_rows()` (both `shared.services.fixtures`), runs the
graph, prints the trajectory, and asserts that diagnosis happened,
baselines ran, and a recommendation was produced. Exits non-zero on
assertion failure.

NOTE: `shared/services/` is delivered by the backend builder (parallel
track). If it is not importable yet, this script exits with a clear error
instead of pretending to work.

Run from the `agents/` directory with its venv active:
    python demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

# Make the monorepo importable (`agents.*` and `shared.*`) when run as
# `python demo.py` from the `agents/` directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.services import baselines as _baselines_mod  # noqa: F401
    from shared.services import datasets as _datasets_mod  # noqa: F401
    from shared.services import diagnosis as _diagnosis_mod  # noqa: F401
    from shared.services import strategy as _strategy_mod  # noqa: F401
    from shared.services.fixtures import (
        termination_dataset_rows,
        termination_spec_fields,
    )
except ImportError as exc:
    print(
        "demo.py: shared/services/ is not available yet "
        f"(backend builder delivers it in parallel): {exc}",
        file=sys.stderr,
    )
    sys.exit(2)

from agents.supervisor import build_supervisor_graph  # noqa: E402  (needs the path trick above)


def _check(condition: bool, message: str) -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {message}")
    if not condition:
        sys.exit(1)


def main() -> None:
    spec_fields = termination_spec_fields()
    spec_dict = {
        "id": str(uuid4()),
        "project_id": str(uuid4()),
        # The brief's fixture example omits problem_statement, but
        # IntelligenceSpec requires it — fall back to a plain description.
        "problem_statement": spec_fields.get(
            "problem_statement",
            "decide whether a search should continue or stop",
        ),
        **spec_fields,
    }
    rows = termination_dataset_rows()

    print("== Rustenwer Phase-1 demo: termination fixture ==")
    print(f"spec: {spec_dict['name']} (primitive={spec_dict.get('intelligence_primitive')})")
    print(f"dataset rows: {len(rows)}, label_column='label'\n")

    final = build_supervisor_graph().invoke(
        {
            "messages": [],
            "project_id": spec_dict["project_id"],
            "problem_statement": spec_dict["problem_statement"],
            "phase": "intake",
            "notes": [],
            "spec": spec_dict,
            "dataset_rows": rows,
            "label_column": "label",
            "dataset_id": str(uuid4()),
            "dataset_version": 1,
        }
    )

    print("-- trajectory --")
    for note in final.get("notes", []):
        print(f"  * {note}")

    print("\n-- artifacts --")
    diagnosis = final.get("diagnosis") or {}
    print(
        f"diagnosis: primitive={diagnosis.get('primitive')}, "
        f"ml_necessary={diagnosis.get('ml_necessary')}"
    )
    report = final.get("dataset_report") or {}
    print(
        f"dataset: rows={report.get('row_count')}, "
        f"ready_for_training={report.get('ready_for_training')}"
    )
    baseline_report = final.get("baseline_report") or {}
    print(
        f"baselines: best={baseline_report.get('best_baseline')}, "
        f"bar={baseline_report.get('bar_to_beat')}"
    )
    strategy = final.get("strategy")
    print(f"strategy: {strategy['training_method'] if strategy else 'skipped (no-ML path)'}")
    print(f"recommendation: {final.get('recommendation')}")

    print("\n-- assertions --")
    _check(bool(diagnosis), "diagnosis happened")
    _check(
        len(baseline_report.get("baselines", [])) == 3,
        f"baselines ran (3, got {len(baseline_report.get('baselines', []))})",
    )
    _check(bool(final.get("recommendation")), "a recommendation was produced")
    if final.get("no_ml_path"):
        _check(final.get("strategy") is None, "no-ML path short-circuited the strategy node")
    else:
        _check(bool(strategy), "strategy was proposed on the ML path")

    print("\ndemo passed")


if __name__ == "__main__":
    main()
