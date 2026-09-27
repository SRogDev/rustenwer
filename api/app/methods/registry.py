"""Method→adapter registry (plan §2, §54).

The canonical seed catalog TRAINING_METHODS lives in
`shared/services/methods.py` (pure, importable from agents). This module
adds the execution linkage: which catalog method is runnable by which
TrainingMethodAdapter, plus `assert_registered()` — the consistency check
the tests pin:

- every VALIDATED method with locally_runnable=True has an adapter entry;
- every adapter key maps back to a method row.
"""

from __future__ import annotations

from shared.domain import MethodValidationStatus
from shared.services.methods import TRAINING_METHODS

from app.training.adapters import ADAPTERS

# method slug -> adapter key in app.training.adapters.ADAPTERS.
# Only locally registered adapters appear here; KNOWN methods (no adapter)
# are honestly vetoed by the recommendation engine instead.
METHOD_ADAPTERS: dict[str, str] = {
    "classifier": "classifier",
    "lora": "lora",
    "qlora": "qlora",
    "distillation": "distillation",
    "contrastive": "contrastive",
}


class RegistryInconsistencyError(RuntimeError):
    """The catalog and the adapter registry disagree — a build-time bug."""


def assert_registered() -> None:
    """Consistency check: catalog <-> adapter linkage.

    Raises RegistryInconsistencyError on any mismatch.
    """
    slugs = {m.slug for m in TRAINING_METHODS}
    for method in TRAINING_METHODS:
        if (
            method.status == MethodValidationStatus.VALIDATED
            and method.locally_runnable
            and method.slug not in METHOD_ADAPTERS
        ):
            raise RegistryInconsistencyError(
                f"VALIDATED + locally_runnable method {method.slug!r} "
                "has no adapter entry in METHOD_ADAPTERS"
            )
    for slug, adapter_key in METHOD_ADAPTERS.items():
        if slug not in slugs:
            raise RegistryInconsistencyError(
                f"METHOD_ADAPTERS[{slug!r}] has no method row in the catalog"
            )
        if adapter_key not in ADAPTERS:
            raise RegistryInconsistencyError(
                f"METHOD_ADAPTERS[{slug!r}] points to unknown adapter {adapter_key!r}"
            )
