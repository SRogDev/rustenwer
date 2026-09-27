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
    display_name: Optional[str] = None
    role: UserRole = UserRole.MEMBER
    created_at: str


class Project(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_by: Optional[UUID] = None
    created_at: str
    updated_at: str


class IntelligenceSpec(BaseModel):
    """Intelligence Specification — the contract everything downstream
    operates against (§7)."""

    id: UUID
    project_id: UUID
    name: str
    description: Optional[str] = None
    problem_statement: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    intelligence_primitive: IntelligencePrimitive
    quality_requirements: Optional[dict[str, Any]] = None
    latency_requirements: Optional[dict[str, Any]] = None
    cost_requirements: Optional[dict[str, Any]] = None
    memory_requirements: Optional[dict[str, Any]] = None
    reliability_requirements: Optional[dict[str, Any]] = None
    constraints: list[str] = Field(default_factory=list)
    available_data: Optional[str] = None
    evaluation_definition: Optional[str] = None
    deployment_requirements: Optional[dict[str, Any]] = None
    human_review_policy: Optional[str] = None
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
    description: Optional[str] = None
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
    class_balance: Optional[dict[str, int]] = None
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
    accuracy: Optional[float] = None
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

    model_family: Optional[str] = None  # Null when the strategy is "no training".
    # Structured architecture description (e.g. {"type": "text-classifier", ...}).
    architecture: Optional[dict[str, Any]] = None
    # e.g. 'none-deterministic' | 'lora' | 'qlora' | 'distillation' | 'embedding-ft'
    training_method: Optional[str] = None
    objective: str = ""
    dataset_ref: Optional[dict[str, Any]] = None  # {dataset_id, version}
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    evaluation_plan: str = ""
    compute_budget: dict[str, Optional[float]] = Field(
        default_factory=lambda: {"max_gpu_hours": None, "max_cost_usd": None}
    )
    baseline_bar: Optional[QualityBar] = None
    rationale: str = ""
    no_training_justification: Optional[str] = None  # Set when ml_necessary is False.


class TrainingJob(BaseModel):
    """Training Job — expensive operation with an explicit lifecycle (§42).

    Real GPU execution lands in Phase 2; Phase 1 records strategy + state.
    """

    id: UUID
    project_id: UUID
    spec_id: Optional[UUID] = None
    dataset_version_id: Optional[UUID] = None
    name: str
    status: JobStatus = JobStatus.CREATED
    strategy: Optional[TrainingStrategy] = None
    compute_budget: Optional[dict[str, Optional[float]]] = None
    error: Optional[str] = None
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
    logs: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


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
    description: Optional[str] = None
    created_at: str


class ModelVersion(BaseModel):
    """ModelVersion — immutable version of a model (§43)."""

    id: UUID
    model_id: UUID
    version: int = 1
    training_run_id: Optional[UUID] = None
    architecture: Optional[dict[str, Any]] = None
    size_bytes: Optional[int] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_uri: Optional[str] = None
    created_at: str


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
    results: Optional[EvaluationResults] = None
    created_at: str
    completed_at: Optional[str] = None


class Deployment(BaseModel):
    """Deployment — an approved Intelligence/Model served as an API endpoint."""

    id: UUID
    project_id: UUID
    spec_id: UUID
    model_version_id: Optional[UUID] = None
    name: str
    status: DeploymentStatus = DeploymentStatus.DRAFT
    endpoint_url: Optional[str] = None
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
