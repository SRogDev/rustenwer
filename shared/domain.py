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
