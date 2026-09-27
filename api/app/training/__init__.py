"""Phase 2 — training execution package.

`router.py` keeps the Phase-1 job CRUD router (import path `app.training`
is preserved: `from app import training as training_module` and
`from app.training import router` both keep working).

New Phase-2 modules:
  adapters   — TrainingMethodAdapter interface + real implementations
  queue      — persistent FIFO job queue (SQLite)
  providers  — ComputeProvider abstraction (local subprocess / DigitalOcean GPU)
  worker     — WorkerManager: queue draining, lifecycle, cost accounting
  runner     — worker subprocess entrypoint (`python -m app.training.runner`)
  runs       — read-model helpers (logs, metrics, cost) over a run's attempt dir
  checkpoints— atomic checkpoint write/read/list
  artifacts  — immutable versioned artifact store
  rates      — provider rate table (USD/hour)
"""

from app.training.adapters import (
    ADAPTERS,
    AdapterEnvironmentError,
    AdapterValidationError,
    get_adapter,
)
from app.training.router import (
    InMemoryTrainingJobRepository,
    JobTransitionRequest,
    TrainingJobCreate,
    TrainingJobRepository,
    get_project_repository,
    get_training_job_repository,
    router,
)
from app.training.worker import WorkerManager, get_worker_manager

__all__ = [
    "ADAPTERS",
    "AdapterEnvironmentError",
    "AdapterValidationError",
    "InMemoryTrainingJobRepository",
    "JobTransitionRequest",
    "TrainingJobCreate",
    "TrainingJobRepository",
    "WorkerManager",
    "get_adapter",
    "get_project_repository",
    "get_training_job_repository",
    "get_worker_manager",
    "router",
]
