"""FastAPI application factory and process entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from transcriptforge_api import __version__
from transcriptforge_api.config import get_settings
from transcriptforge_api.observability import RequestObservabilityMiddleware
from transcriptforge_api.routers.analyses import router as analyses_router
from transcriptforge_api.routers.datasets import router as datasets_router
from transcriptforge_api.routers.experiments import router as experiments_router
from transcriptforge_api.routers.external_validations import router as external_validations_router
from transcriptforge_api.routers.guided_assay import router as guided_assay_router
from transcriptforge_api.routers.health import router as health_router
from transcriptforge_api.routers.models import router as models_router
from transcriptforge_api.routers.projects import router as projects_router
from transcriptforge_api.routers.runs import router as runs_router
from transcriptforge_api.routers.signatures import router as signatures_router
from transcriptforge_api.routers.studies import router as studies_router
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.local import LocalStorage


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Perform bounded local housekeeping without deleting published objects."""
    settings = get_settings()
    storage = get_storage_backend()
    if isinstance(storage, LocalStorage):
        await run_in_threadpool(
            storage.cleanup_stale_temporary_files,
            settings.temporary_upload_retention_seconds,
        )
    yield


def create_app() -> FastAPI:
    """Create a fully configured API application."""
    settings = get_settings()
    application = FastAPI(
        title="TranscriptForge API",
        summary="Orchestration API for reproducible transcriptomics workflows",
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestObservabilityMiddleware)
    application.include_router(health_router, prefix="/api")
    application.include_router(guided_assay_router, prefix="/api")
    application.include_router(projects_router, prefix="/api")
    application.include_router(datasets_router, prefix="/api")
    application.include_router(external_validations_router, prefix="/api")
    application.include_router(experiments_router, prefix="/api")
    application.include_router(runs_router, prefix="/api")
    application.include_router(analyses_router, prefix="/api")
    application.include_router(models_router, prefix="/api")
    application.include_router(signatures_router, prefix="/api")
    application.include_router(studies_router, prefix="/api")
    return application


app = create_app()
