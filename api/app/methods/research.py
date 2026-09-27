"""Research knowledge store (plan §52).

In-memory repository behind a Protocol — the same pattern as the Phase 1+
stores. The findings below are the Phase 5 seed knowledge: each one names
the technique, when it helps, what it needs, where it wins and where it
breaks. Migration 005 is canonical for the later Supabase swap.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.domain import ResearchFinding


@runtime_checkable
class ResearchFindingRepository(Protocol):
    """Storage contract for research findings."""

    def list_findings(self) -> list[ResearchFinding]:
        ...

    def add_finding(self, finding: ResearchFinding) -> ResearchFinding:
        ...


_SEED_FINDINGS: list[ResearchFinding] = [
    ResearchFinding(
        technique="LoRA init trick",
        useful_for=["peft", "lora", "qlora"],
        requires=["frozen base model", "rank r", "alpha scaling"],
        advantage=(
            "Kaiming-uniform A with zero B starts training at the identity "
            "(W_eff = W0), so the first steps never degrade the base model."
        ),
        weakness="rank too low underfits; too high overfits small datasets",
        source="validated: phase-2 e2e (LoRAAdapter)",
        version=1,
    ),
    ResearchFinding(
        technique="QLoRA 4-bit",
        useful_for=["peft", "qlora"],
        requires=["CUDA GPU", "unsloth", "bitsandbytes"],
        advantage=(
            "4-bit quantized base + trainable LoRA adapters fine-tunes "
            "multi-billion-parameter models on a single GPU."
        ),
        weakness=(
            "quantization noise on sensitive tasks; hard-fails without CUDA "
            "instead of silently degrading"
        ),
        source="validated: phase-2 e2e (guarded path)",
        version=1,
    ),
    ResearchFinding(
        technique="Distillation soft targets",
        useful_for=["distillation"],
        requires=["trained teacher", "labeled data", "temperature T", "alpha mix"],
        advantage=(
            "temperature-scaled soft targets transfer the teacher's "
            "generalization to a tiny student at a fraction of inference cost."
        ),
        weakness=(
            "a weak teacher teaches bad habits (student <= teacher); "
            "temperature too high washes out the signal"
        ),
        source="validated: phase-5 e2e (DistillationAdapter)",
        version=1,
    ),
    ResearchFinding(
        technique="Contrastive embeddings",
        useful_for=["contrastive", "ranking", "retrieval", "similarity"],
        requires=["pair/batch construction", "temperature", "enough negatives"],
        advantage=(
            "InfoNCE-style training over similar/dissimilar pairs learns "
            "embeddings where nearest-centroid retrieval is cheap and accurate."
        ),
        weakness=(
            "representation collapse without enough negatives; not a "
            "classifier — needs a retrieval head"
        ),
        source="validated: phase-5 e2e (ContrastiveAdapter)",
        version=1,
    ),
]


class InMemoryResearchRepository:
    """Process-wide in-memory finding store (seeded)."""

    def __init__(self, seed: list[ResearchFinding] | None = None) -> None:
        self._findings: list[ResearchFinding] = list(
            seed if seed is not None else _SEED_FINDINGS
        )

    def list_findings(self) -> list[ResearchFinding]:
        return list(self._findings)

    def add_finding(self, finding: ResearchFinding) -> ResearchFinding:
        self._findings.append(finding)
        return finding


_default_repository = InMemoryResearchRepository()


def get_research_repository() -> ResearchFindingRepository:
    """Dependency hook: returns the process-wide research repository."""
    return _default_repository
