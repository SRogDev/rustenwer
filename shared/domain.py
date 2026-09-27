"""Rustenwer shared domain types — single source of truth for Python (api/, agents/).

Contract: this module is hand-synced with `shared/types.ts` (TypeScript).
Any change here MUST be mirrored there and noted in `shared/README.md`.
Source of truth for the shapes: product plan §7 (IntelligenceSpec),
§2.3 (IntelligencePrimitive), §17 (Candidate lifecycle), §42 (Job lifecycle).
"""

from enum import StrEnum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IntelligencePrimitive(StrEnum):
    """Intelligence Primitive — reusable cognitive operation categories (§2.3)."""

    DECISION = "decision"
    CLASSIFICATION = "classification"
    RANKING = "ranking"
    FILTERING = "filtering"
    SEARCH = "search"
    RETRIEVAL = "retrieval"
    ROUTING = "routing"
    VERIFICATION = "verification"
    CRITIQUE = "critique"
    PREDICTION = "prediction"
    ANOMALY_DETECTION = "anomaly_detection"
    DIAGNOSIS = "diagnosis"
    PLANNING = "planning"
    OPTIMIZATION = "optimization"
    COMPRESSION = "compression"
    MEMORY_SELECTION = "memory_selection"
    ITERATION_CONTROL = "iteration_control"
    TERMINATION = "termination"
    EXPLORATION = "exploration"
    SELECTION = "selection"


class CandidateLifecycle(StrEnum):
    """Candidate lifecycle (§17)."""

    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    TRAINING = "TRAINING"
    EVALUATING = "EVALUATING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    COMPARED = "COMPARED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class JobStatus(StrEnum):
    """Expensive-operation job lifecycle (§42)."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ProjectStatus(StrEnum):
    """Project lifecycle (Phase 0; extended in later phases)."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class IntelligenceSpecStatus(StrEnum):
    """IntelligenceSpec lifecycle status."""

    DRAFT = "DRAFT"
    DIAGNOSED = "DIAGNOSED"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class EvaluationStatus(StrEnum):
    """Evaluation lifecycle status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DeploymentStatus(StrEnum):
    """Deployment lifecycle status."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class DatasetFormat(StrEnum):
    """Dataset storage format."""

    JSONL = "jsonl"
    CSV = "csv"
    INLINE = "inline"


class UsageScope(StrEnum):
    """Usage accounting scope (§45)."""

    PROJECT = "project"
    EXPERIMENT = "experiment"
    CANDIDATE = "candidate"
    TRAINING_JOB = "training_job"
    MODEL = "model"
    DEPLOYMENT = "deployment"
    EVALUATION = "evaluation"
    INFERENCE = "inference"


class UsageKind(StrEnum):
    """Usage accounting kind (§45)."""

    TRAINING = "training"
    INFERENCE = "inference"
    EVALUATION = "evaluation"
    STORAGE = "storage"


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Organization(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: str


class ApiUser(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    display_name: str | None = None
    role: UserRole = UserRole.MEMBER
    created_at: str


class Project(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_by: UUID | None = None
    created_at: str
    updated_at: str


class IntelligenceSpec(BaseModel):
    """Intelligence Specification — the contract everything downstream
    operates against (§7)."""

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    problem_statement: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    intelligence_primitive: IntelligencePrimitive
    quality_requirements: dict[str, Any] | None = None
    latency_requirements: dict[str, Any] | None = None
    cost_requirements: dict[str, Any] | None = None
    memory_requirements: dict[str, Any] | None = None
    reliability_requirements: dict[str, Any] | None = None
    constraints: list[str] = Field(default_factory=list)
    available_data: str | None = None
    evaluation_definition: str | None = None
    deployment_requirements: dict[str, Any] | None = None
    human_review_policy: str | None = None
    status: IntelligenceSpecStatus = IntelligenceSpecStatus.DRAFT
    version: int = 1


# ---------------------------------------------------------------------------
# Phase 1 — MVP core entities (plan §41, §61 Phase 1)
# ---------------------------------------------------------------------------


class Dataset(BaseModel):
    """Dataset — a named collection of labeled examples owned by a project."""

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    format: DatasetFormat = DatasetFormat.INLINE
    row_count: int = 0
    created_at: str
    updated_at: str


class DatasetReport(BaseModel):
    """Deterministic dataset validation report (Dataset Agent, §14)."""

    dataset_id: UUID
    version: int
    row_count: int
    column_schema: dict[str, str] = Field(default_factory=dict)
    class_balance: dict[str, int] | None = None
    missing_values: dict[str, int] = Field(default_factory=dict)
    leakage_flags: list[str] = Field(default_factory=list)
    imbalance_detected: bool = False
    recommended_split: dict[str, float] = Field(
        default_factory=lambda: {"train": 0.7, "validation": 0.15, "test": 0.15}
    )
    ready_for_training: bool = False
    notes: list[str] = Field(default_factory=list)


class DatasetVersion(BaseModel):
    """DatasetVersion — immutable snapshot of dataset rows + computed stats."""

    id: UUID
    dataset_id: UUID
    version: int
    column_schema: dict[str, str] = Field(default_factory=dict)
    split_config: dict[str, float] = Field(
        default_factory=lambda: {"train": 0.7, "validation": 0.15, "test": 0.15}
    )
    stats: DatasetReport
    created_at: str


class DiagnosisResult(BaseModel):
    """Result of the Specification/Diagnostic Agent (§8)."""

    spec_id: UUID
    ml_necessary: bool  # Rule 13: the platform may conclude no ML is required.
    primitive: IntelligencePrimitive
    rationale: str  # Condensed answers to the 10 diagnostic questions (§8).
    candidate_approaches: list[str] = Field(default_factory=list)
    data_requirements: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    key_constraints: list[str] = Field(default_factory=list)
    diagnosed_at: str


class BaselineMetrics(BaseModel):
    """One cheap baseline measurement (Baseline-first principle, §16)."""

    name: str  # 'majority_class' | 'keyword_heuristic' | 'deterministic_rule'
    description: str
    accuracy: float | None = None
    latency_ms_p50: float = 0.0
    cost_usd_per_1k: float = 0.0
    size_bytes: int = 0
    predictions_evaluated: int = 0


class QualityBar(BaseModel):
    """Bar every trained candidate must beat (Rule 9)."""

    accuracy: float
    latency_ms_p50: float
    cost_usd_per_1k: float


class BaselineReport(BaseModel):
    """Baseline comparison report produced before any training is proposed."""

    spec_id: UUID
    dataset_version_id: UUID
    baselines: list[BaselineMetrics] = Field(default_factory=list)
    best_baseline: str = ""
    bar_to_beat: QualityBar
    evaluated_at: str


class TrainingStrategy(BaseModel):
    """Training strategy decided by the Training Strategy Agent (§12).

    The agent DECIDES; the executor (Phase 2) executes (Rule 3).
    """

    model_family: str | None = None  # Null when the strategy is "no training".
    # Structured architecture description (e.g. {"type": "text-classifier", ...}).
    architecture: dict[str, Any] | None = None
    # e.g. 'none-deterministic' | 'lora' | 'qlora' | 'distillation' | 'embedding-ft'
    training_method: str | None = None
    objective: str = ""
    dataset_ref: dict[str, Any] | None = None  # {dataset_id, version}
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    evaluation_plan: str = ""
    compute_budget: dict[str, float | None] = Field(
        default_factory=lambda: {"max_gpu_hours": None, "max_cost_usd": None}
    )
    baseline_bar: QualityBar | None = None
    rationale: str = ""
    no_training_justification: str | None = None  # Set when ml_necessary is False.


class TrainingJob(BaseModel):
    """Training Job — expensive operation with an explicit lifecycle (§42).

    Real GPU execution lands in Phase 2; Phase 1 records strategy + state.
    """

    id: UUID
    project_id: UUID
    spec_id: UUID | None = None
    dataset_version_id: UUID | None = None
    name: str
    status: JobStatus = JobStatus.CREATED
    strategy: TrainingStrategy | None = None
    compute_budget: dict[str, float | None] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class TrainingRun(BaseModel):
    """Training Run — one execution attempt of a job."""

    id: UUID
    job_id: UUID
    attempt: int = 1
    status: JobStatus = JobStatus.CREATED
    provider: str = "local"  # 'local' | 'digitalocean' — the ComputeProvider that ran it.
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    logs: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class CheckpointInfo(BaseModel):
    """One atomic training checkpoint (Phase 2)."""

    id: str  # e.g. 'ckpt-0003'
    epoch: int
    step: int
    bytes: int
    created_at: str


class ArtifactRecord(BaseModel):
    """One immutable, versioned artifact (plan §43)."""

    name: str
    version: int
    sha256: str
    bytes: int
    created_at: str


class MetricPoint(BaseModel):
    """One point of a metric time series."""

    step: int
    value: float
    ts: str


class MetricSeries(BaseModel):
    """A named metric time series (loss, lr, grad_norm, …)."""

    name: str
    points: list[MetricPoint] = Field(default_factory=list)


class RunMetrics(BaseModel):
    """All metric series of a run."""

    run_id: UUID
    series: list[MetricSeries] = Field(default_factory=list)
    latest: dict[str, float] = Field(default_factory=dict)


class RunCost(BaseModel):
    """Wall-time cost accounting for one run (plan §45)."""

    run_id: UUID
    provider: str
    seconds: float
    usd: float
    rate_usd_per_hour: float


class Model(BaseModel):
    """Model — a learned computational model (plan §2.1)."""

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    created_at: str


class ModelVersion(BaseModel):
    """ModelVersion — immutable version of a model (§43).

    Phase 3 adds the full lineage: which dataset version, which training
    strategy, which code/template version, which seed, and which base model
    produced it. Published versions are never mutated — a change means a
    new version (the repository offers no update path).
    """

    id: UUID
    model_id: UUID
    version: int = 1
    training_run_id: UUID | None = None
    architecture: dict[str, Any] | None = None
    size_bytes: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_uri: str | None = None
    # -- Phase 3 lineage (§43, §59) --------------------------------------
    dataset_version_id: UUID | None = None
    training_strategy: dict[str, Any] | None = None
    code_version: str | None = None  # git commit of the training code
    template_version: str | None = None  # validated template used
    seed: int | None = None
    base_model: str | None = None  # e.g. 'mlp-from-scratch' | HF id
    lineage_locked: bool = True  # published versions are immutable
    created_at: str


# ---------------------------------------------------------------------------
# Phase 3 — Evaluation & Registry (plan §61 Phase 3, §§30–33, 55–57)
# ---------------------------------------------------------------------------


class SubjectKind(StrEnum):
    """What an EvaluationRun evaluates (Rule 11: one interface for anything)."""

    BASELINE = "baseline"  # a Phase-1 cheap baseline, by name
    MODEL_VERSION = "model_version"  # a registered ModelVersion (torch artifact)
    REFERENCE = "reference"  # a precomputed QualityVector (e.g. the incumbent)


class EvaluationSubject(BaseModel):
    """The subject of an evaluation run."""

    kind: SubjectKind
    ref: str | None = None  # baseline name | model_version UUID | label
    quality_vector: Optional["QualityVector"] = None  # REFERENCE only


class QualityVector(BaseModel):
    """Multi-objective candidate quality (plan §30).

    No hard-coded global weights: the IntelligenceSpec defines the
    priorities, and `compare` orders subjects per those priorities.
    Higher is better for every field except latency_*, *_cost_*, and
    model_size_bytes (documented per field).
    """

    task_quality: float | None = None  # higher is better (e.g. accuracy)
    calibration: float | None = None  # higher is better (1 - ECE)
    robustness: float | None = None  # higher is better
    latency_ms_p50: float | None = None  # lower is better
    latency_ms_p99: float | None = None  # lower is better
    inference_cost_usd_per_1k: float | None = None  # lower is better
    training_cost_usd: float | None = None  # lower is better
    model_size_bytes: int | None = None  # lower is better
    reliability: float | None = None  # higher is better (1 - failure rate)


class Benchmark(BaseModel):
    """Benchmark — reusable across candidate architectures (plan §57)."""

    id: UUID
    project_id: UUID | None = None  # None = global seeded benchmark
    name: str
    description: str = ""
    input_spec: dict[str, Any] = Field(default_factory=dict)
    expected_output: dict[str, Any] = Field(default_factory=dict)
    evaluation_function: str = "classification_on_rows"
    dataset_version_id: UUID | None = None
    metrics: list[str] = Field(default_factory=list)
    cost_rules: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class EvaluationRun(BaseModel):
    """EvaluationRun — one async evaluation of a subject on a benchmark.

    Distinct from the Phase-1 `Evaluation` (synchronous baseline report).
    Follows the same job lifecycle as training runs: PENDING -> RUNNING ->
    COMPLETED / FAILED / CANCELLED (cancellable, observable).
    """

    id: UUID
    project_id: UUID
    benchmark_id: UUID
    spec_id: UUID | None = None
    name: str
    subject: EvaluationSubject
    status: EvaluationStatus = EvaluationStatus.PENDING
    quality_vector: QualityVector | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class ComparisonSubjectResult(BaseModel):
    """One subject's standing inside a ComparisonReport."""

    subject: EvaluationSubject
    quality_vector: QualityVector | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    beats_bar: bool | None = None  # vs the baseline QualityBar
    beats_incumbent: bool | None = None  # per spec priorities


class ComparisonReport(BaseModel):
    """Candidate vs baselines vs incumbent (promotion-gate data for Phase 6)."""

    benchmark_id: UUID
    generated_at: str
    results: list[ComparisonSubjectResult] = Field(default_factory=list)
    baseline_bar: QualityBar | None = None
    incumbent: ComparisonSubjectResult | None = None
    winner: str | None = None  # subject label, per spec priorities
    notes: list[str] = Field(default_factory=list)


class ArchitectureComponentKind(StrEnum):
    """Kinds of components an IntelligenceArchitecture can compose (plan §2.2,
    §31). A component is either learned (model_version), cheap/deterministic
    (baseline, deterministic_rule, threshold), behavioral (prompt) or
    structural (post_processor, router)."""

    MODEL_VERSION = "model_version"
    BASELINE = "baseline"
    DETERMINISTIC_RULE = "deterministic_rule"
    THRESHOLD = "threshold"
    PROMPT = "prompt"
    POST_PROCESSOR = "post_processor"
    ROUTER = "router"


# Recognized architecture shapes (IntelligenceArchitecture.kind). The list is
# open-ended — "custom" covers anything the discovery engine invents later.
ARCHITECTURE_KINDS: tuple[str, ...] = (
    "single_model",
    "deterministic_rule",
    "classifier_with_deterministic_rule",
    "embedding_knn_threshold",
    "llm_judge_threshold",
    "heuristic_pipeline",
    "model_ensemble",
    "custom",
)


class ArchitectureComponent(BaseModel):
    """One node of an intelligence architecture.

    kind=model_version → ref is a model version UUID (immutable).
    kind=baseline → ref is a baseline name (majority_class |
    keyword_heuristic | deterministic_rule).
    kind=deterministic_rule → config carries the fitted rule, e.g.
      {"column": "progress_score", "threshold": 0.21,
       "left_label": "stop", "right_label": "continue",
       "fallback_label": "continue"}.
    kind=threshold → config {"input_key": ..., "threshold": ...,
      "above": ..., "below": ...}.
    kind=prompt → config {"template": ..., "template_sha256": ...}.
    """

    kind: ArchitectureComponentKind
    ref: str | None = None
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class IntelligenceArchitecture(BaseModel):
    """How an intelligence's components compose into an executable system
    (plan §2.2, §31). Stored as an immutable snapshot inside each
    IntelligenceVersion — named drafts live in intelligence_architectures."""

    kind: str = "single_model"
    components: list[ArchitectureComponent] = Field(default_factory=list)
    execution_order: list[int] = Field(default_factory=list)
    notes: str | None = None

    def ordered_components(self) -> list[ArchitectureComponent]:
        """Components in execution order (defaults to declaration order)."""
        if not self.execution_order:
            return list(self.components)
        return [self.components[i] for i in self.execution_order]


# Programming constructs as intelligence primitives (plan §3). A conceptual
# map: traditional program parts that learned intelligence can replace.
# "try/catch" maps to verification; a dedicated recovery primitive is an
# emerging category, not one of the 20 catalogued primitives (§2.3).
PRIMITIVE_PROGRAMMING_MAP: dict[str, str] = {
    "if": IntelligencePrimitive.DECISION.value,
    "switch": IntelligencePrimitive.ROUTING.value,
    "filter": IntelligencePrimitive.FILTERING.value,
    "sort": IntelligencePrimitive.RANKING.value,
    "search": IntelligencePrimitive.SEARCH.value,
    "while": IntelligencePrimitive.ITERATION_CONTROL.value,
    "assert": IntelligencePrimitive.VERIFICATION.value,
    "try/catch": IntelligencePrimitive.VERIFICATION.value,
    "compress": IntelligencePrimitive.COMPRESSION.value,
    "optimize": IntelligencePrimitive.OPTIMIZATION.value,
    "predict": IntelligencePrimitive.PREDICTION.value,
    "debug": IntelligencePrimitive.DIAGNOSIS.value,
}


class Intelligence(BaseModel):
    """Intelligence — an executable system performing a cognitive function
    (plan §2.2, §31). SEPARATE from Model: one model may power multiple
    intelligences; one intelligence may use multiple models."""

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    primitive: IntelligencePrimitive | None = None
    created_at: str


class IntelligenceVersion(BaseModel):
    """IntelligenceVersion — immutable version referencing immutable
    component versions (§31, §43).

    Phase 4 deepens the version into the full intelligence abstraction: the
    architecture snapshot, the pinned input/output schemas (the §7 contract)
    and the locked flag are all part of the immutable record. There is no
    update path — publishing a change means publishing a new version.
    """

    id: UUID
    intelligence_id: UUID
    version: int = 1
    components: dict[str, Any] = Field(
        default_factory=dict
    )  # {model_version_ids: [...], baseline_refs: [...], harness: {...}}
    architecture: IntelligenceArchitecture | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    best_evaluation_run_id: UUID | None = None
    status: str = "DRAFT"  # DRAFT | PROMOTED (promotion logic lands in Phase 6)
    locked: bool = True  # set at publish; versions are never mutated
    created_at: str


class IntelligenceVersionDiff(BaseModel):
    """What changed between two intelligence versions (plan §32, §37).

    Mirrors the model lineage diff: component-level changes (added, removed,
    modified incl. threshold/prompt changes), architecture-kind changes and
    schema changes — the evidence a human reviewer needs to approve v2.
    """

    intelligence_id: UUID
    from_version: int
    to_version: int
    changed_fields: list[str] = Field(default_factory=list)
    components_added: list[dict[str, Any]] = Field(default_factory=list)
    components_removed: list[dict[str, Any]] = Field(default_factory=list)
    components_modified: list[dict[str, Any]] = Field(default_factory=list)
    architecture_kind_changed: bool = False
    schema_changed: bool = False
    notes: list[str] = Field(default_factory=list)


class InferenceProvider(StrEnum):
    """Unified inference abstraction (plan §34). The Intelligence Registry
    never depends on one provider; only RUSTENWER_HOSTED executes in
    Phase 4 — the others are honest capability entries."""

    RUSTENWER_HOSTED = "rustenwer_hosted"
    EXTERNAL_API = "external_api"
    LOCAL_GPU = "local_gpu"


class ProviderInfo(BaseModel):
    """Capability entry for one inference provider."""

    name: InferenceProvider
    functional: bool
    capabilities: list[str] = Field(default_factory=list)
    note: str = ""


class InferenceRequest(BaseModel):
    """Inputs for one intelligence invocation — validated against the
    intelligence version's input_schema before any component runs."""

    inputs: dict[str, Any] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    """Machine-readable intelligence output (plan §33)."""

    output: dict[str, Any]
    intelligence_id: UUID
    intelligence_version_id: UUID
    deployment_id: UUID
    primitive: IntelligencePrimitive | None = None
    latency_ms: float = 0.0
    provider: InferenceProvider = InferenceProvider.RUSTENWER_HOSTED


# Machine-readable output shapes per primitive (plan §33). The inference
# pipeline shapes every response to these keys so callers never parse
# free text.
OUTPUT_SHAPES: dict[str, list[str]] = {
    IntelligencePrimitive.DECISION.value: ["decision", "confidence"],
    IntelligencePrimitive.TERMINATION.value: ["decision", "confidence"],
    IntelligencePrimitive.CLASSIFICATION.value: ["label", "probabilities"],
    IntelligencePrimitive.RANKING.value: ["score"],
    IntelligencePrimitive.FILTERING.value: ["kept", "scores"],
    IntelligencePrimitive.PREDICTION.value: ["prediction", "confidence"],
    IntelligencePrimitive.VERIFICATION.value: ["verdict", "confidence"],
    IntelligencePrimitive.ROUTING.value: ["route", "confidence"],
}


def output_shape_for_primitive(
    primitive: IntelligencePrimitive | str | None,
) -> list[str]:
    """Expected output keys for a primitive; generic ["output"] fallback."""
    key = primitive.value if isinstance(primitive, IntelligencePrimitive) else primitive
    return OUTPUT_SHAPES.get(key or "", ["output"])


class EvaluationResults(BaseModel):
    baselines: list[BaselineMetrics] = Field(default_factory=list)
    bar_to_beat: QualityBar
    recommendation: str = ""
    evaluated_at: str


class Evaluation(BaseModel):
    """Evaluation — task-specific measurement (§15).

    The evaluator is independent of the training mechanism (Rule 11).
    """

    id: UUID
    project_id: UUID
    spec_id: UUID
    dataset_version_id: UUID
    name: str
    status: EvaluationStatus = EvaluationStatus.PENDING
    results: EvaluationResults | None = None
    created_at: str
    completed_at: str | None = None


class Deployment(BaseModel):
    """Deployment — an approved Intelligence served as an API endpoint.

    Phase 4: a deployment references an immutable intelligence_version_id
    (§31, §43). model_version_id remains as a back-compat path: creating a
    deployment with only a model_version_id auto-creates a single-model
    intelligence wrapping it.
    """

    id: UUID
    project_id: UUID
    spec_id: UUID
    model_version_id: UUID | None = None
    intelligence_version_id: UUID | None = None
    provider: InferenceProvider = InferenceProvider.RUSTENWER_HOSTED
    name: str
    status: DeploymentStatus = DeploymentStatus.DRAFT
    endpoint_url: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class UsageEvent(BaseModel):
    """UsageEvent — one cost/usage record (§45)."""

    id: UUID
    project_id: UUID
    scope: UsageScope
    scope_id: UUID
    kind: UsageKind
    quantity: float = 0.0
    unit: str = ""
    cost_usd: float = 0.0
    recorded_at: str


class UsageSummary(BaseModel):
    """Aggregated cost view for a project (§45)."""

    project_id: UUID
    total_cost_usd: float = 0.0
    by_scope: dict[str, float] = Field(default_factory=dict)
    by_kind: dict[str, float] = Field(default_factory=dict)
    event_count: int = 0


class ScopeRollup(BaseModel):
    """Per-scope cost breakdown (Phase 3 cost accounting)."""

    scope: str
    total_cost_usd: float = 0.0
    by_kind: dict[str, float] = Field(default_factory=dict)
    event_count: int = 0


class UsageRollups(BaseModel):
    """Per-scope cost rollups for a project (Phase 3, §45).

    Answers "how much did each model / deployment / training job /
    evaluation cost?" from the recorded UsageEvents.
    """

    project_id: UUID
    total_cost_usd: float = 0.0
    by_scope: dict[str, ScopeRollup] = Field(default_factory=dict)
    by_kind: dict[str, float] = Field(default_factory=dict)
    event_count: int = 0
