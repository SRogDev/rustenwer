"""Test fixtures for the rustenwer API test suite."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import datasets as datasets_module
from app import demo as demo_module
from app import deployments as deployments_module
from app import evaluations as evaluations_module
from app import models as models_module
from app import specs as specs_module
from app import training as training_module
from app import usage as usage_module
from app.main import create_app
from app.projects import InMemoryProjectRepository, get_repository


@pytest.fixture
def repository() -> InMemoryProjectRepository:
    """A fresh, empty repository per test (no fake demo data, by design)."""
    return InMemoryProjectRepository()


@pytest.fixture
def spec_repository() -> specs_module.InMemorySpecRepository:
    return specs_module.InMemorySpecRepository()


@pytest.fixture
def dataset_repository() -> datasets_module.InMemoryDatasetRepository:
    return datasets_module.InMemoryDatasetRepository()


@pytest.fixture
def training_job_repository() -> training_module.InMemoryTrainingJobRepository:
    return training_module.InMemoryTrainingJobRepository()


@pytest.fixture
def model_repository() -> models_module.InMemoryModelRepository:
    return models_module.InMemoryModelRepository()


@pytest.fixture
def evaluation_repository() -> evaluations_module.InMemoryEvaluationRepository:
    return evaluations_module.InMemoryEvaluationRepository()


@pytest.fixture
def deployment_repository() -> deployments_module.InMemoryDeploymentRepository:
    return deployments_module.InMemoryDeploymentRepository()


@pytest.fixture
def usage_repository() -> usage_module.InMemoryUsageRepository:
    return usage_module.InMemoryUsageRepository()


@pytest.fixture
def client(
    repository: InMemoryProjectRepository,
    spec_repository: specs_module.InMemorySpecRepository,
    dataset_repository: datasets_module.InMemoryDatasetRepository,
    training_job_repository: training_module.InMemoryTrainingJobRepository,
    model_repository: models_module.InMemoryModelRepository,
    evaluation_repository: evaluations_module.InMemoryEvaluationRepository,
    deployment_repository: deployments_module.InMemoryDeploymentRepository,
    usage_repository: usage_module.InMemoryUsageRepository,
) -> TestClient:
    """TestClient wired to fresh repositories via dependency overrides."""
    application = create_app()
    application.dependency_overrides[get_repository] = lambda: repository
    application.dependency_overrides[specs_module.get_spec_repository] = lambda: spec_repository
    application.dependency_overrides[datasets_module.get_dataset_repository] = (
        lambda: dataset_repository
    )
    application.dependency_overrides[training_module.get_training_job_repository] = (
        lambda: training_job_repository
    )
    application.dependency_overrides[models_module.get_model_repository] = (
        lambda: model_repository
    )
    application.dependency_overrides[evaluations_module.get_evaluation_repository] = (
        lambda: evaluation_repository
    )
    application.dependency_overrides[deployments_module.get_deployment_repository] = (
        lambda: deployment_repository
    )
    application.dependency_overrides[usage_module.get_usage_repository] = (
        lambda: usage_repository
    )
    # Cross-router lookups (org-scoping, evaluation/demo orchestration) reuse
    # the same per-test repositories: routers import each other's hooks
    # (e.g. evaluations/demo import get_spec_repository from app.specs), so
    # the overrides above already cover them.
    application.dependency_overrides[datasets_module.get_project_repository] = (
        lambda: repository
    )
    application.dependency_overrides[specs_module.get_project_repository] = lambda: repository
    application.dependency_overrides[training_module.get_project_repository] = (
        lambda: repository
    )
    application.dependency_overrides[models_module.get_project_repository] = (
        lambda: repository
    )
    application.dependency_overrides[evaluations_module.get_project_repository] = (
        lambda: repository
    )
    application.dependency_overrides[deployments_module.get_project_repository] = (
        lambda: repository
    )
    application.dependency_overrides[usage_module.get_project_repository] = lambda: repository
    application.dependency_overrides[demo_module.get_project_repository] = lambda: repository
    return TestClient(application)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Phase-0 stub auth: any well-formed bearer token is accepted."""
    return {"Authorization": "Bearer phase0-test-token"}


@pytest.fixture
def project_id(client: TestClient, auth_headers: dict[str, str]) -> UUID:
    """A project in the stub user's org, created through the API."""
    resp = client.post(
        "/api/v1/projects", json={"name": "Phase-1 test project"}, headers=auth_headers
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])
