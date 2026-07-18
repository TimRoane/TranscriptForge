"""FastAPI application factory and process entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from transcriptforge_api import __version__
from transcriptforge_api.config import get_settings
from transcriptforge_api.routers.analyses import router as analyses_router
from transcriptforge_api.routers.datasets import router as datasets_router
from transcriptforge_api.routers.external_validations import router as external_validations_router
from transcriptforge_api.routers.health import router as health_router
from transcriptforge_api.routers.projects import router as projects_router
from transcriptforge_api.routers.runs import router as runs_router
from transcriptforge_api.routers.signatures import router as signatures_router


def create_app() -> FastAPI:
    """Create a fully configured API application."""
    settings = get_settings()
    application = FastAPI(
        title="TranscriptForge API",
        summary="Orchestration API for reproducible transcriptomics workflows",
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(projects_router, prefix="/api")
    application.include_router(datasets_router, prefix="/api")
    application.include_router(external_validations_router, prefix="/api")
    application.include_router(runs_router, prefix="/api")
    application.include_router(analyses_router, prefix="/api")
    application.include_router(signatures_router, prefix="/api")
    return application


app = create_app()
