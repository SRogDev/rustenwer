"""Intelligence package (Phase 4): architecture validation, version diff,
inference providers and deployment orchestration (plan §2, §31–§34, §43)."""

from app.intelligence.architectures import (
    KNOWN_BASELINES,
    ArchitectureValidationError,
    diff_architectures,
    summarize_architecture,
    validate_architecture,
)
from app.intelligence.diff import diff_versions
from app.intelligence.inference import (
    PROVIDERS,
    ComponentExecutionError,
    HostedInferenceProvider,
    InferenceContext,
    InferenceProviderBase,
    ProviderNotConfigured,
    SchemaValidationError,
    execute_pipeline,
    get_provider,
)
from app.intelligence.service import (
    ensure_model_backcompat_intelligence,
    resolve_deployment_target,
)

__all__ = [
    "KNOWN_BASELINES",
    "PROVIDERS",
    "ArchitectureValidationError",
    "ComponentExecutionError",
    "HostedInferenceProvider",
    "InferenceContext",
    "InferenceProviderBase",
    "ProviderNotConfigured",
    "SchemaValidationError",
    "diff_architectures",
    "diff_versions",
    "ensure_model_backcompat_intelligence",
    "execute_pipeline",
    "get_provider",
    "resolve_deployment_target",
    "summarize_architecture",
    "validate_architecture",
]
