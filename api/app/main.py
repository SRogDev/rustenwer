"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.datasets import router as datasets_router
from app.demo import router as demo_router
from app.deployments import router as deployments_router
from app.evaluations import router as evaluations_router
from app.logging_config import configure_logging, get_logger
from app.models import router as models_router
from app.projects import router as projects_router
from app.specs import router as specs_router
from app.training import router as training_router
from app.usage import router as usage_router

SERVICE_NAME = "rustenwer-api"
SERVICE_VERSION = "0.1.0"
WEB_ORIGIN = "http://localhost:3000"

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("api.startup", service=SERVICE_NAME, version=SERVICE_VERSION)
    yield
    logger.info("api.shutdown", service=SERVICE_NAME)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[WEB_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
        }

    app.include_router(projects_router)
    app.include_router(specs_router)
    app.include_router(datasets_router)
    app.include_router(training_router)
    app.include_router(models_router)
    app.include_router(evaluations_router)
    app.include_router(deployments_router)
    app.include_router(usage_router)
    app.include_router(demo_router)
    return app


app = create_app()
