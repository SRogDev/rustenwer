"""Test fixtures for the rustenwer API test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.projects import InMemoryProjectRepository, get_repository


@pytest.fixture
def repository() -> InMemoryProjectRepository:
    """A fresh, empty repository per test (no fake demo data, by design)."""
    return InMemoryProjectRepository()


@pytest.fixture
def client(repository: InMemoryProjectRepository) -> TestClient:
    """TestClient wired to a fresh repository via dependency override."""
    application = create_app()
    application.dependency_overrides[get_repository] = lambda: repository
    return TestClient(application)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Phase-0 stub auth: any well-formed bearer token is accepted."""
    return {"Authorization": "Bearer phase0-test-token"}
